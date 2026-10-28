"""Tests for the ingestion module."""

from __future__ import annotations

import shutil

import pytest

from open_decide.ingest import (
    EmptyDocument,
    IngestionDependencyMissing,
    IngestionError,
    UnsupportedFileType,
    extract_text,
)


def test_plain_text() -> None:
    assert extract_text(b"Hello, world!", "note.txt") == "Hello, world!"


def test_markdown() -> None:
    assert extract_text(b"# Title\n\nBody.", "readme.md") == "# Title\n\nBody."


def test_empty_bytes_raises() -> None:
    with pytest.raises(EmptyDocument):
        extract_text(b"", "empty.txt")


def test_whitespace_only_raises() -> None:
    with pytest.raises(EmptyDocument):
        extract_text(b"   \n\n   ", "blank.txt")


def test_unsupported_extension() -> None:
    with pytest.raises(UnsupportedFileType):
        extract_text(b"data", "movie.mp4")


def test_file_too_large() -> None:
    huge = b"a" * (6 * 1024 * 1024)
    with pytest.raises(IngestionError, match=r"too large"):
        extract_text(huge, "big.txt")


def test_pdf_without_pypdf_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """If pypdf is missing, a clean error is raised."""
    import sys

    monkeypatch.setitem(sys.modules, "pypdf", None)
    with pytest.raises(IngestionDependencyMissing, match=r"ingest.*extra"):
        extract_text(b"%PDF-1.4\n%", "doc.pdf")


def test_image_without_pytesseract_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "pytesseract", None)
    with pytest.raises(IngestionDependencyMissing, match=r"ingest.*extra"):
        extract_text(b"\x89PNG\r\n\x1a\n", "scan.png")


@pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="tesseract binary not installed",
)
def test_image_ocr_end_to_end() -> None:
    """OCR a simple generated image, if tesseract is available."""
    pytest.importorskip("PIL")
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (400, 100), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 30), "urgent invoice", fill="black")

    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG")

    text = extract_text(buf.getvalue(), "image.png")
    assert "urgent" in text.lower() or "invoice" in text.lower()


def test_scanned_pdf_without_pdf2image_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A PDF without text layer and without pdf2image -> clean error."""
    import sys

    pytest.importorskip("pypdf")
    monkeypatch.setitem(sys.modules, "pdf2image", None)
    # A minimal PDF with no extractable text
    minimal_pdf = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n"
        b"0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
    )
    with pytest.raises(IngestionDependencyMissing, match=r"pdf2image"):
        extract_text(minimal_pdf, "scanned.pdf")
