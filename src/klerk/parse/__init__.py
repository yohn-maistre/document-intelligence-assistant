"""Document parsing — unified entry point.

`parse(path)` returns a `ParsedDocument` regardless of source format. Routes:
  - .pdf, .docx, .pptx, .xlsx → Docling (or PyMuPDF for PDFs if KLERK_PARSER=pymupdf)
  - .md, .markdown, .txt       → native UTF-8 read
  - .html, .htm                → Docling

A graceful PyMuPDF fallback exists for environments where Docling's torch /
easyocr extras failed to install (some Linux wheel ecosystems).
"""

from __future__ import annotations

from klerk.parse.unified import ParsedDocument, parse

__all__ = ["ParsedDocument", "parse"]
