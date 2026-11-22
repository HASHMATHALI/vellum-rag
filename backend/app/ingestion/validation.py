"""Upload validation: size cap, extension allow-list, MIME sanity check, magic bytes, archive-bomb limits."""
import io
import re
import unicodedata
import zipfile

from fastapi import HTTPException, UploadFile, status

from app.config.settings import settings

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "md", "csv"}
# Browsers are inconsistent for text formats, so the declared MIME type is only used to reject clear mismatches;
# the magic-byte check below is authoritative.
ALLOWED_MIME = {
    "pdf": {"application/pdf", "application/x-pdf", "application/octet-stream"},
    "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip",
             "application/octet-stream"},
    "txt": {"text/plain", "application/octet-stream"},
    "md": {"text/markdown", "text/x-markdown", "text/plain", "application/octet-stream"},
    "csv": {"text/csv", "application/csv", "application/vnd.ms-excel", "text/plain", "application/octet-stream"},
}
MAX_ZIP_ENTRIES = 2000
MAX_ZIP_UNCOMPRESSED = 200 * 1024 * 1024
MAX_ZIP_RATIO = 200

_UNSAFE_CHARS = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]')


def _bad(detail: str, code: int = status.HTTP_400_BAD_REQUEST):
    raise HTTPException(status_code=code, detail=detail)


def sanitize_filename(name: str) -> str:
    """Display-safe base name. Never used to build storage paths (those are random UUIDs)."""
    name = unicodedata.normalize("NFKC", name or "")
    name = name.replace("\\", "/").split("/")[-1]
    name = _UNSAFE_CHARS.sub("_", name).strip(" .")
    name = re.sub(r"\s+", " ", name)
    if len(name) > 150:
        stem, dot, ext = name.rpartition(".")
        name = (stem[: 150 - len(ext) - 1] + "." + ext) if dot else name[:150]
    return name or "document"


def extension_of(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


async def read_upload_limited(file: UploadFile) -> bytes:
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    buf = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > max_bytes:
            _bad(f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB limit.", status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    if not buf:
        _bad("The uploaded file is empty.")
    return bytes(buf)


def _check_text(data: bytes) -> None:
    head = data[:65536]
    if b"\x00" in head:
        _bad("File does not look like text (binary content detected).")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            head.decode(enc)
            return
        except UnicodeDecodeError as e:
            # A multi-byte sequence may be cut at the 64 KiB boundary.
            if enc.startswith("utf") and e.start >= len(head) - 4:
                return
    # latin-1 decodes anything; accept but only if it is mostly printable.
    printable = sum(1 for b in head if b in (9, 10, 13) or 32 <= b)
    if printable / max(1, len(head)) < 0.95:
        _bad("File does not look like text.")


def _check_docx(data: bytes) -> None:
    if not data.startswith(b"PK\x03\x04"):
        _bad("File content does not match the .docx format.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ZIP_ENTRIES:
                _bad("DOCX archive has too many entries.")
            names = {i.filename for i in infos}
            if "word/document.xml" not in names or "[Content_Types].xml" not in names:
                _bad("File is not a valid Word document.")
            total = 0
            for i in infos:
                total += i.file_size
                if i.compress_size and i.file_size / i.compress_size > MAX_ZIP_RATIO and i.file_size > 10 * 1024 * 1024:
                    _bad("DOCX archive compression ratio is suspicious (possible zip bomb).")
                if i.filename.startswith("/") or ".." in i.filename.split("/"):
                    _bad("DOCX archive contains unsafe paths.")
            if total > MAX_ZIP_UNCOMPRESSED:
                _bad("DOCX archive expands beyond the allowed size.")
            if any(n.lower().endswith(".bin") and "vbaproject" in n.lower() for n in names):
                _bad("Macro-enabled documents are not accepted.")
    except zipfile.BadZipFile:
        _bad("File is not a valid Word document.")


def validate_upload(filename: str, content_type: str, data: bytes) -> str:
    """Returns the normalised extension or raises HTTP 400/415."""
    ext = extension_of(filename)
    if ext not in ALLOWED_EXTENSIONS:
        _bad(f"Unsupported file format. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}.",
             status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
    ctype = (content_type or "application/octet-stream").split(";")[0].strip().lower()
    if ctype not in ALLOWED_MIME[ext]:
        _bad(f"Declared content type '{ctype}' does not match .{ext}.", status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
    if ext == "pdf":
        if not data[:1024].lstrip().startswith(b"%PDF-"):
            _bad("File content does not match the PDF format.")
    elif ext == "docx":
        _check_docx(data)
    else:
        _check_text(data)
    return ext
