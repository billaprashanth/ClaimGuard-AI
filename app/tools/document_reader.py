"""Document ingestion tools: read text + forensic metadata from PDF / TXT / JSON / images."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

SUPPORTED = {".pdf", ".txt", ".md", ".json", ".png", ".jpg", ".jpeg"}
EDITING_TOOLS = (
    "photoshop", "gimp", "canva", "ilovepdf", "pdf-xchange", "sejda", "smallpdf",
    "pdfescape", "foxit phantom", "nitro pro", "paint", "pixlr", "inkscape",
)


def _pdf_date(value) -> Optional[datetime]:
    """Parse PDF date strings like D:20261028101500+05'30'."""
    if not value:
        return None
    m = re.match(r"D?:?(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?", str(value))
    if not m:
        return None
    parts = [int(p) if p else 0 for p in m.groups()]
    try:
        return datetime(*parts)
    except ValueError:
        return None


def read_pdf(path: Path) -> dict:
    import pdfplumber
    from pypdf import PdfReader

    text_pages = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text_pages.append(page.extract_text() or "")
    meta = {}
    try:
        info = PdfReader(str(path)).metadata or {}
        meta = {
            "producer": str(info.get("/Producer", "") or ""),
            "creator": str(info.get("/Creator", "") or ""),
            "created": _pdf_date(info.get("/CreationDate")),
            "modified": _pdf_date(info.get("/ModDate")),
        }
    except Exception as exc:  # corrupted metadata is itself a signal
        meta = {"error": str(exc)}
    return {"text": "\n".join(text_pages), "pages": len(text_pages), "metadata": meta}


def read_image(path: Path) -> dict:
    """Optional OCR. Requires `pytesseract` + the Tesseract binary; skipped gracefully otherwise."""
    try:
        import pytesseract
        from PIL import Image

        text = pytesseract.image_to_string(Image.open(path))
        return {"text": text, "pages": 1, "metadata": {"ocr": True}}
    except Exception as exc:
        return {"text": "", "pages": 1, "metadata": {"ocr": False, "error": f"OCR unavailable: {exc}"}}


def read_document(path: str | Path) -> dict:
    path = Path(path)
    ext = path.suffix.lower()
    base = {"file": path.name, "path": str(path), "ext": ext}
    if ext not in SUPPORTED:
        return {**base, "text": "", "pages": 0, "metadata": {}, "error": f"Unsupported file type {ext}"}
    try:
        if ext == ".pdf":
            return {**base, **read_pdf(path)}
        if ext in {".txt", ".md"}:
            return {**base, "text": path.read_text(encoding="utf-8", errors="ignore"), "pages": 1, "metadata": {}}
        if ext == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            return {**base, "text": json.dumps(data, indent=1), "json": data, "pages": 1, "metadata": {}}
        return {**base, **read_image(path)}
    except Exception as exc:
        return {**base, "text": "", "pages": 0, "metadata": {}, "error": f"Could not read file: {exc}"}


def forensic_flags(meta: dict) -> list[str]:
    """Signals that a PDF was edited after it was produced by the hospital system."""
    flags = []
    tool = f"{meta.get('producer', '')} {meta.get('creator', '')}".lower()
    hit = next((t for t in EDITING_TOOLS if t in tool), None)
    if hit:
        flags.append(f"PDF produced/edited with image-editing software ('{hit}')")
    c, m = meta.get("created"), meta.get("modified")
    if c and m and (m - c).total_seconds() > 24 * 3600:
        flags.append(f"PDF modified {(m - c).days} day(s) after creation ({c:%d-%b-%Y} -> {m:%d-%b-%Y})")
    if meta.get("error"):
        flags.append("PDF metadata unreadable / corrupted")
    return flags
