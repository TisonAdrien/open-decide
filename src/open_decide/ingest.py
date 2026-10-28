"""Multimodal ingestion: turn PDFs, images or text files into plain text.

The engine is a pure text-in / decision-out component. Ingestion happens
upstream: an API handler receives a file, calls :func:`extract_text`, and
hands the resulting string to :class:`DecisionEngine`.

Supported formats:

- ``.txt`` / ``.md``: read as UTF-8 text.
- ``.pdf``: extracted with ``pypdf``. If no native text layer is found
  (scanned PDF), falls back to OCR via ``pdf2image`` + ``pytesseract``.
- ``.png`` / ``.jpg`` / ``.jpeg`` / ``.tif`` / ``.tiff`` / ``.bmp`` / ``.webp``:
  OCR with ``pytesseract`` (requires the ``tesseract`` binary on the system).

Every optional dependency is imported lazily. If one is missing, a
``IngestionDependencyMissing`` is raised with an actionable message.
"""

from __future__ import annotations

import io
from pathlib import Path

# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class IngestionError(Exception):
    """Base class for ingestion errors."""


class UnsupportedFileType(IngestionError):
    """Raised when the file extension is not supported."""


class IngestionDependencyMissing(IngestionError):
    """Raised when an optional dependency is not installed."""


class EmptyDocument(IngestionError):
    """Raised when extraction produced no text."""


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

_TEXT_EXTS = {".txt", ".md", ".markdown"}
_PDF_EXTS = {".pdf"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}

MAX_BYTES = 5 * 1024 * 1024  # 5 MB


def extract_text(data: bytes, filename: str) -> str:
    """Extract plain text from ``data`` based on the file extension."""
    if not data:
        raise EmptyDocument("empty file")
    if len(data) > MAX_BYTES:
        raise IngestionError(f"file too large: {len(data)} bytes (max {MAX_BYTES} bytes)")

    ext = Path(filename).suffix.lower()
    if ext in _TEXT_EXTS:
        text = _extract_plain_text(data)
    elif ext in _PDF_EXTS:
        text = _extract_pdf(data)
    elif ext in _IMAGE_EXTS:
        text = _extract_image(data)
    else:
        raise UnsupportedFileType(
            f"unsupported extension {ext!r}; "
            f"supported: {sorted(_TEXT_EXTS | _PDF_EXTS | _IMAGE_EXTS)}"
        )

    text = text.strip()
    if not text:
        raise EmptyDocument(
            f"no text could be extracted from {filename!r} "
            "(blank images and empty documents are not supported)"
        )
    return text


# --------------------------------------------------------------------------- #
# Per-format extractors
# --------------------------------------------------------------------------- #


def _extract_plain_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")


def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise IngestionDependencyMissing(
            "PDF ingestion requires the 'ingest' extra. "
            "Install it with: uv sync --extra ingest "
            "(or: pip install -e '.[ingest]')"
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise IngestionError(f"failed to parse PDF: {exc}") from exc

    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            page_text = page.extract_text() or ""
        except Exception as exc:
            raise IngestionError(f"failed to extract text from page {i + 1}: {exc}") from exc
        if page_text:
            parts.append(page_text)

    joined = "\n\n".join(parts).strip()
    if not joined:
        # No native text layer: this is a scanned PDF.
        return _ocr_pdf(data)
    return joined


def _ocr_pdf(data: bytes) -> str:
    """OCR a scanned PDF page by page (no native text layer)."""
    try:
        from pdf2image import convert_from_bytes
    except ImportError as exc:
        raise IngestionDependencyMissing(
            "Scanned PDF ingestion requires pdf2image. "
            "Install it with: uv sync --extra ingest "
            "(and poppler-utils on the system)"
        ) from exc

    try:
        images = convert_from_bytes(data, dpi=200)
    except Exception as exc:
        raise IngestionDependencyMissing(
            "OCR of scanned PDFs requires poppler-utils on the system. "
            "On Debian/Ubuntu/WSL: sudo apt-get install -y poppler-utils"
        ) from exc

    parts: list[str] = []
    for i, image in enumerate(images):
        try:
            page_text = _ocr_image(image)
        except IngestionError as exc:
            raise IngestionError(f"OCR failed on page {i + 1}: {exc}") from exc
        if page_text:
            parts.append(page_text)

    return "\n\n".join(parts)


def _extract_image(data: bytes) -> str:
    try:
        from PIL import Image
    except ImportError as exc:
        raise IngestionDependencyMissing(
            "Image OCR requires the 'ingest' extra. "
            "Install it with: uv sync --extra ingest "
            "(or: pip install -e '.[ingest]')"
        ) from exc

    # Pre-flight: fail fast if pytesseract is missing, before attempting to
    # decode the image (which may itself fail on malformed data).
    try:
        import pytesseract  # noqa: F401
    except ImportError as exc:
        raise IngestionDependencyMissing(
            "Image OCR requires the 'ingest' extra. "
            "Install it with: uv sync --extra ingest "
            "(or: pip install -e '.[ingest]')"
        ) from exc

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        raise IngestionError(f"failed to open image: {exc}") from exc

    return _ocr_image(image)


def _ocr_image(image: object) -> str:
    """OCR a PIL image and return the text (shared by image and PDF paths)."""
    try:
        import pytesseract
    except ImportError as exc:
        raise IngestionDependencyMissing(
            "Image OCR requires the 'ingest' extra. Install it with: uv sync --extra ingest"
        ) from exc

    try:
        return str(pytesseract.image_to_string(image))
    except pytesseract.TesseractNotFoundError as exc:
        raise IngestionDependencyMissing(
            "OCR requires the 'tesseract' binary on the system. "
            "On Debian/Ubuntu/WSL: sudo apt-get install -y tesseract-ocr"
        ) from exc
    except Exception as exc:
        raise IngestionError(f"OCR failed: {exc}") from exc
