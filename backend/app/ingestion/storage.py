"""Document blob storage.

References stored in documents.filepath:
  local:<user_id>/<uuid>.<ext>          file under UPLOAD_DIR
  supabase:<bucket>/<user_id>/<uuid>.<ext>   object in a *private* Supabase bucket, accessed with the server key
Legacy rows created by the old code contain a public Supabase URL. Those are resolved to a bucket path and
fetched through the Supabase client as well. The app never performs a raw HTTP GET on a stored URL, which
removes the previous SSRF primitive.
"""
import logging
import os
import uuid
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import unquote, urlparse

from app.config.settings import settings

logger = logging.getLogger(__name__)


class StorageError(Exception):
    pass


_client = None


def _supabase():
    global _client
    if _client is None and settings.SUPABASE_URL and settings.SUPABASE_KEY:
        from supabase import create_client
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    return _client


def _upload_root() -> Path:
    return Path(settings.UPLOAD_DIR).resolve()


def _local_path(rel: str) -> Path:
    root = _upload_root()
    p = (root / rel).resolve()
    if root != p and root not in p.parents:
        raise StorageError("Path escapes upload directory")
    return p


def parse_legacy_public_url(url: str) -> Optional[Tuple[str, str]]:
    """Map https://<project>.supabase.co/storage/v1/object/public/<bucket>/<path> to (bucket, path).
    Only URLs on the configured Supabase host are accepted."""
    if not settings.SUPABASE_URL:
        return None
    u, cfg = urlparse(url), urlparse(settings.SUPABASE_URL)
    if u.scheme != "https" or not u.hostname or u.hostname != cfg.hostname:
        return None
    prefix = "/storage/v1/object/public/"
    if not u.path.startswith(prefix):
        return None
    rest = unquote(u.path[len(prefix):])
    bucket, _, path = rest.partition("/")
    if not bucket or not path or ".." in path.split("/"):
        return None
    return bucket, path


def save(user_id: int, data: bytes, ext: str, content_type: str) -> str:
    name = f"{user_id}/{uuid.uuid4().hex}.{ext}"
    client = _supabase()
    if client is not None:
        bucket = settings.SUPABASE_STORAGE_BUCKET
        try:
            client.storage.from_(bucket).upload(path=name, file=data, file_options={"content-type": content_type})
        except Exception as e:
            logger.error("Supabase upload failed: %s", type(e).__name__)
            raise StorageError("Could not store the file") from e
        return f"supabase:{bucket}/{name}"
    path = _local_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "xb") as f:
        f.write(data)
    return f"local:{name}"


def load(ref: str) -> bytes:
    if ref.startswith("local:"):
        return _local_path(ref[len("local:"):]).read_bytes()
    if ref.startswith("supabase:"):
        bucket, _, path = ref[len("supabase:"):].partition("/")
    elif ref.startswith("https://"):
        parsed = parse_legacy_public_url(ref)
        if not parsed:
            raise StorageError("Refusing to fetch an unrecognised remote URL")
        bucket, path = parsed
    elif os.path.isabs(ref) or ref.startswith(settings.UPLOAD_DIR):
        # Legacy local rows stored "uploads/<id>_<rand>_<name>"; keep them readable but confined to UPLOAD_DIR.
        p = Path(ref).resolve()
        if _upload_root() not in p.parents:
            raise StorageError("Path escapes upload directory")
        return p.read_bytes()
    else:
        raise StorageError("Unknown storage reference")
    client = _supabase()
    if client is None:
        raise StorageError("Supabase storage is not configured")
    try:
        return client.storage.from_(bucket).download(path)
    except Exception as e:
        raise StorageError("Could not download the stored file") from e


def delete(ref: str) -> None:
    try:
        if ref.startswith("local:"):
            p = _local_path(ref[len("local:"):])
            if p.exists():
                p.unlink()
            return
        if ref.startswith("supabase:"):
            bucket, _, path = ref[len("supabase:"):].partition("/")
        elif ref.startswith("https://") and (parsed := parse_legacy_public_url(ref)):
            bucket, path = parsed
        else:
            p = Path(ref).resolve()
            if _upload_root() in p.parents and p.exists():
                p.unlink()
            return
        client = _supabase()
        if client is not None:
            client.storage.from_(bucket).remove([path])
    except Exception as e:
        logger.error("Failed to delete stored file (%s)", type(e).__name__)
