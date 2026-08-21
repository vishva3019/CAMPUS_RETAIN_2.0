"""Image storage.

Replaces the previous approach of base64-encoding uploads into a ``Text`` column.
That design had three compounding problems: the database grew by ~1.37x the size
of every photo uploaded, the homepage inlined every image into its own HTML (so
page weight grew without bound and would eventually exceed Vercel's ~4.5 MB
response cap), and there was no way to serve a small thumbnail in the grid.

Two backends are provided behind one interface:

* :class:`CloudinaryStorage` for production. Cloudinary generates resized,
  re-compressed, format-negotiated derivatives on its own CDN, so the app needs
  no image-processing dependency and spends no compute on thumbnails.
* :class:`LocalStorage` for development and tests. Writes under
  ``app/static/uploads``. Not viable on Vercel, whose filesystem is read-only
  apart from ``/tmp`` and is discarded between invocations.

Which one is used is decided solely by whether ``CLOUDINARY_URL`` is set.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from flask import current_app
from werkzeug.datastructures import FileStorage

# Thumbnail geometry for the browse grid, matching the card's 4:3 aspect ratio.
THUMB_WIDTH = 600
THUMB_HEIGHT = 450

# Enough bytes to identify every format we accept.
_MAGIC_HEAD_BYTES = 32


class StorageError(RuntimeError):
    """Raised when an upload is rejected or a backend fails."""


@dataclass(frozen=True)
class StoredImage:
    """Where an uploaded image ended up."""

    url: str
    thumbnail_url: str | None = None
    public_id: str | None = None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def sniff_image_type(head: bytes) -> str | None:
    """Identify an image from its leading bytes, or return ``None``.

    Deliberately does not trust the ``Content-Type`` header or the filename
    extension, both of which are attacker-controlled. The old code interpolated
    the client-supplied ``content_type`` straight into a ``data:`` URI that was
    then emitted into an ``<img src>`` attribute.
    """
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "webp"
    return None


def read_validated_image(file: FileStorage | None) -> tuple[bytes, str] | None:
    """Read and validate an optional upload.

    Returns ``(data, extension)``, or ``None`` when no file was supplied.
    Raises :class:`StorageError` with a user-safe message when the upload is
    present but unacceptable.
    """
    if file is None or not file.filename:
        return None

    max_bytes = current_app.config["MAX_CONTENT_LENGTH"]

    file.stream.seek(0)
    head = file.stream.read(_MAGIC_HEAD_BYTES)
    kind = sniff_image_type(head)
    if kind is None:
        raise StorageError(
            "That file does not look like an image. "
            "Please upload a PNG, JPEG, GIF or WebP."
        )

    rest = file.stream.read(max_bytes - len(head) + 1)
    data = head + rest
    file.stream.seek(0)

    if len(data) > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        raise StorageError(f"Image is too large. Maximum size is {limit_mb} MB.")

    if kind not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        raise StorageError(f"{kind.upper()} images are not accepted.")

    return data, kind


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------

class BaseStorage:
    name = "base"

    def save(self, data: bytes, extension: str) -> StoredImage:
        raise NotImplementedError

    def delete(self, public_id: str | None) -> bool:
        """Remove a stored image. Missing or unsupported: return ``False``."""
        return False


class LocalStorage(BaseStorage):
    """Filesystem-backed storage for local development."""

    name = "local"

    def __init__(self, root: Path, url_prefix: str = "/static/uploads") -> None:
        self.root = root
        self.url_prefix = url_prefix.rstrip("/")
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes, extension: str) -> StoredImage:
        filename = f"{secrets.token_hex(16)}.{extension}"
        (self.root / filename).write_bytes(data)
        url = f"{self.url_prefix}/{filename}"
        # No resizing without an image library; the grid uses the full file.
        return StoredImage(url=url, thumbnail_url=url, public_id=filename)

    def delete(self, public_id: str | None) -> bool:
        if not public_id:
            return False
        # Guard against traversal via a tampered database value.
        candidate = (self.root / public_id).resolve()
        if self.root.resolve() not in candidate.parents:
            current_app.logger.warning("Refusing to delete outside upload root")
            return False
        try:
            candidate.unlink()
        except OSError:
            return False
        return True


class CloudinaryStorage(BaseStorage):
    """Cloudinary-backed storage with CDN-side derivatives."""

    name = "cloudinary"

    def __init__(self, cloudinary_url: str, folder: str) -> None:
        self.folder = folder
        self._configure(cloudinary_url)

    @staticmethod
    def parse_url(cloudinary_url: str) -> dict[str, str]:
        """Split ``cloudinary://key:secret@cloud_name`` into components.

        Parsed explicitly rather than relying on the SDK's environment-variable
        auto-configuration, so a misconfiguration fails loudly here instead of
        surfacing as a confusing error at upload time.
        """
        parsed = urlparse(cloudinary_url)
        if parsed.scheme != "cloudinary":
            raise StorageError(
                "CLOUDINARY_URL must start with 'cloudinary://'. "
                "Expected cloudinary://<api_key>:<api_secret>@<cloud_name>"
            )
        if not (parsed.username and parsed.password and parsed.hostname):
            raise StorageError(
                "CLOUDINARY_URL is incomplete. "
                "Expected cloudinary://<api_key>:<api_secret>@<cloud_name>"
            )
        return {
            "api_key": parsed.username,
            "api_secret": parsed.password,
            "cloud_name": parsed.hostname,
        }

    def _configure(self, cloudinary_url: str) -> None:
        try:
            import cloudinary
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise StorageError(
                "CLOUDINARY_URL is set but the 'cloudinary' package is not "
                "installed. Run: pip install -r requirements.txt"
            ) from exc

        creds = self.parse_url(cloudinary_url)
        cloudinary.config(secure=True, **creds)

    def save(self, data: bytes, extension: str) -> StoredImage:
        import cloudinary.uploader
        import cloudinary.utils

        try:
            result = cloudinary.uploader.upload(
                data,
                folder=self.folder,
                resource_type="image",
                # Strip EXIF (which can carry the finder's GPS coordinates) and
                # cap stored dimensions so an 8000px phone photo is not kept at
                # full size.
                transformation=[
                    {"width": 1600, "height": 1600, "crop": "limit"},
                    {"quality": "auto"},
                ],
                overwrite=False,
                unique_filename=True,
            )
        except Exception as exc:
            current_app.logger.exception("Cloudinary upload failed")
            raise StorageError(
                "Could not store the image right now. Please try again."
            ) from exc

        public_id = result.get("public_id")
        full_url = result.get("secure_url") or result.get("url")
        if not full_url or not public_id:
            raise StorageError("Image storage returned an unexpected response.")

        thumb_url, _ = cloudinary.utils.cloudinary_url(
            public_id,
            width=THUMB_WIDTH,
            height=THUMB_HEIGHT,
            crop="fill",
            gravity="auto",
            quality="auto",
            fetch_format="auto",
            secure=True,
        )

        return StoredImage(
            url=full_url, thumbnail_url=thumb_url, public_id=public_id
        )

    def delete(self, public_id: str | None) -> bool:
        if not public_id:
            return False
        try:
            import cloudinary.uploader

            cloudinary.uploader.destroy(public_id, resource_type="image")
        except Exception:
            # An orphaned remote file is untidy but must not block the delete.
            current_app.logger.exception("Cloudinary delete failed")
            return False
        return True


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def build_storage(app) -> BaseStorage:
    """Choose a backend from configuration. Called once by the app factory."""
    cloudinary_url = app.config.get("CLOUDINARY_URL")
    if cloudinary_url:
        app.logger.info("Image storage: Cloudinary")
        return CloudinaryStorage(
            cloudinary_url, app.config["CLOUDINARY_FOLDER"]
        )

    upload_root = Path(app.static_folder) / "uploads"
    if not app.debug and not app.testing:
        app.logger.warning(
            "CLOUDINARY_URL is not set, falling back to local disk storage. "
            "On a serverless host this will lose every upload. Set "
            "CLOUDINARY_URL in the deployment environment."
        )
    else:
        app.logger.info("Image storage: local disk (%s)", upload_root)
    return LocalStorage(upload_root)


def get_storage() -> BaseStorage:
    """The active backend for the running application."""
    return current_app.extensions["campusretain_storage"]
