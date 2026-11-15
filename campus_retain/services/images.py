"""Image validation, compression and storage.

Photos go to object storage (Cloudflare R2) as ``ItemImage`` rows. With
``STORAGE_BACKEND=database`` the first photo is kept in ``item.image_data`` as in 2.0.
"""
import base64
import io

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


class ImageError(ValueError):
    pass


def process_upload(file_storage):
    """Validate a real image by decoding it, strip metadata (EXIF/GPS), resize and
    re-encode as JPEG. Returns (bytes, content_type, width, height)."""
    cfg = current_app.config
    raw = file_storage.read(cfg["MAX_IMAGE_BYTES"] + 1)
    if len(raw) > cfg["MAX_IMAGE_BYTES"]:
        raise ImageError(f"Photos must be under {cfg['MAX_IMAGE_BYTES'] // (1024 * 1024)} MB.")
    if not raw:
        raise ImageError("The photo is empty.")
    try:
        probe = Image.open(io.BytesIO(raw))
        fmt = probe.format
        probe.verify()
        if fmt not in ALLOWED_FORMATS:
            raise ImageError("Photos must be JPEG, PNG, WebP or GIF.")
        img = Image.open(io.BytesIO(raw))
        if img.width * img.height > 40_000_000:
            raise ImageError("That photo is too large.")
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        img.thumbnail((cfg["IMAGE_MAX_DIMENSION"], cfg["IMAGE_MAX_DIMENSION"]))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=82, optimize=True)  # re-encode drops EXIF
    except ImageError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ImageError("That file is not a valid image.")
    return out.getvalue(), "image/jpeg", img.width, img.height


def store_item_photos(item, files):
    """Validate and store up to MAX_PHOTOS_PER_ITEM photos for a new or existing item.
    Returns the storage keys written, so the caller can delete them if its commit fails."""
    from ..models import ItemImage
    from .storage import StorageError, get_storage, new_key

    files = [f for f in files if f and f.filename]
    limit = current_app.config["MAX_PHOTOS_PER_ITEM"] - len(item.images)
    if len(files) > limit:
        raise ImageError(f"You can add up to {current_app.config['MAX_PHOTOS_PER_ITEM']} photos.")
    processed = [process_upload(f) for f in files]   # validate all before storing any
    store = get_storage()
    if store is None:
        if processed:
            data, content_type, _w, _h = processed[0]
            item.image_data = f"data:{content_type};base64,{base64.b64encode(data).decode()}"
        return []

    written = []
    try:
        for data, content_type, width, height in processed:
            key = new_key(item.college_id)
            store.put(key, data, content_type)
            written.append(key)
            item.images.append(ItemImage(college_id=item.college_id, storage_key=key,
                                         content_type=content_type, size_bytes=len(data),
                                         width=width, height=height, position=len(item.images)))
    except StorageError:
        delete_objects(written)
        raise ImageError("The photo couldn't be saved. Please try again.")
    return written


def delete_objects(keys):
    from .storage import get_storage
    store = get_storage()
    if store is not None:
        for key in keys:
            store.delete(key)
