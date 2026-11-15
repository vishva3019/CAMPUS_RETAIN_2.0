"""Photo storage.

Backends (``STORAGE_BACKEND``):

- ``r2``: Cloudflare R2 through its S3-compatible API. The bucket stays private; the
  app checks access and then redirects to a short-lived signed URL.
- ``local``: a folder on disk, for development.
- ``memory``: a dict, for tests.
- ``database``: no object storage; photos stay in ``item.image_data`` as in 2.0.

Keys look like ``colleges/<college_id>/items/<uuid>.jpg`` so a college's files can be
listed, exported or deleted together.
"""
import os
import uuid

from flask import current_app


class StorageError(RuntimeError):
    pass


def new_key(college_id, ext="jpg"):
    return f"colleges/{college_id}/items/{uuid.uuid4().hex}.{ext}"


class MemoryStorage:
    name = "memory"

    def __init__(self):
        self.objects = {}

    def put(self, key, data, content_type):
        self.objects[key] = (data, content_type)

    def get(self, key):
        try:
            return self.objects[key][0]
        except KeyError:
            raise StorageError(f"missing object {key}")

    def delete(self, key):
        self.objects.pop(key, None)

    def signed_url(self, key):
        return None   # served by the app


class LocalStorage:
    name = "local"

    def __init__(self, root):
        self.root = os.path.abspath(root)

    def _path(self, key):
        path = os.path.abspath(os.path.join(self.root, key))
        if not path.startswith(self.root + os.sep):
            raise StorageError("invalid key")
        return path

    def put(self, key, data, content_type):
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)

    def get(self, key):
        try:
            with open(self._path(key), "rb") as fh:
                return fh.read()
        except FileNotFoundError:
            raise StorageError(f"missing object {key}")

    def delete(self, key):
        try:
            os.remove(self._path(key))
        except FileNotFoundError:
            pass

    def signed_url(self, key):
        return None


class R2Storage:
    """Cloudflare R2 (S3 API). Needs R2_ACCOUNT_ID (or R2_ENDPOINT_URL),
    R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY and R2_BUCKET."""
    name = "r2"

    def __init__(self, cfg):
        import boto3
        from botocore.config import Config

        endpoint = cfg.get("R2_ENDPOINT_URL") or f"https://{cfg['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
        self.bucket = cfg["R2_BUCKET"]
        self.ttl = cfg["MEDIA_URL_TTL_SECONDS"]
        self.client = boto3.client(
            "s3", endpoint_url=endpoint, region_name="auto",
            aws_access_key_id=cfg["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=cfg["R2_SECRET_ACCESS_KEY"],
            config=Config(signature_version="s3v4", retries={"max_attempts": 3},
                          connect_timeout=5, read_timeout=15),
        )

    def put(self, key, data, content_type):
        from botocore.exceptions import BotoCoreError, ClientError
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
                                   CacheControl="private, max-age=31536000, immutable")
        except (BotoCoreError, ClientError) as exc:
            current_app.logger.error("R2 upload failed for %s: %s", key, exc)
            raise StorageError("upload failed")

    def get(self, key):
        from botocore.exceptions import BotoCoreError, ClientError
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"download failed: {exc}")

    def delete(self, key):
        from botocore.exceptions import BotoCoreError, ClientError
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            current_app.logger.warning("R2 delete failed for %s: %s", key, exc)

    def signed_url(self, key):
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=self.ttl)


def get_storage():
    """The configured backend, or None for ``database`` (2.0 behaviour)."""
    app = current_app
    if "photo_storage" not in app.extensions:
        backend = app.config["STORAGE_BACKEND"]
        if backend == "r2":
            store = R2Storage(app.config)
        elif backend == "local":
            store = LocalStorage(app.config["LOCAL_MEDIA_DIR"])
        elif backend == "memory":
            store = MemoryStorage()
        else:
            store = None
        app.extensions["photo_storage"] = store
    return app.extensions["photo_storage"]
