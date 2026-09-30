from __future__ import annotations

import io
import re
from collections import Counter
from zipfile import BadZipFile, ZipFile

from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.knowledge.settings import KnowledgeSettings

PARSER_VERSION = "1.1"
SUPPORTED = {".md", ".txt", ".pdf", ".docx"}


class IngestionError(Exception):
    def __init__(self, code: str, *, review: bool = False):
        super().__init__(code)
        self.code, self.review = code, review


def block(text: str, location: dict, *, table: bool = False, header: str = "") -> dict:
    return {"text": text.strip(), "location": location, "table": table, "header": header}


def parse(data: bytes, suffix: str, settings: KnowledgeSettings) -> list[dict]:
    if suffix not in SUPPORTED:
        raise IngestionError("UNSUPPORTED_FORMAT")
    if len(data) > settings.max_file_bytes:
        raise IngestionError("FILE_TOO_LARGE")
    try:
        if suffix == ".pdf":
            blocks = parse_pdf(data, settings)
        elif suffix == ".docx":
            blocks = parse_docx(data)
        else:
            text = data.decode("utf-8-sig")
            if "\x00" in text:
                raise IngestionError("INVALID_TEXT")
            blocks = parse_text(text, markdown=suffix == ".md")
    except IngestionError:
        raise
    except (ValueError, KeyError, UnicodeError, BadZipFile, PdfReadError) as exc:
        raise IngestionError("PARSE_FAILED") from exc
    blocks = [b for b in blocks if b["text"]]
    if not blocks:
        raise IngestionError("EMPTY_TEXT", review=True)
    if sum(len(b["text"]) for b in blocks) > settings.max_text_chars:
        raise IngestionError("TEXT_TOO_LARGE")
    return blocks


def parse_text(text: str, *, markdown: bool) -> list[dict]:
    lines = text.splitlines()
    out, headings = [], []
    i = 0
    while i < len(lines):
        line = lines[i]
        heading = re.match(r"^(#{1,6})\s+(.+)$", line) if markdown else None
        if heading:
            level = len(heading[1])
            headings = headings[:level-1] + [heading[2]]
            i += 1
            continue
        if not line.strip():
            i += 1
            continue
        section = " / ".join(headings)
        if markdown and i + 1 < len(lines) and "|" in line and re.fullmatch(
            r"[\s|:\-]+", lines[i+1]
        ):
            header = line.strip()
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                out.append(block(lines[i], {"section":section, "line_start":i+1,
                                            "line_end":i+1}, table=True, header=header))
                i += 1
            continue
        start = i
        fenced = markdown and line.lstrip().startswith("```")
        i += 1
        while i < len(lines):
            if fenced:
                if lines[i].lstrip().startswith("```"):
                    i += 1
                    break
            elif not lines[i].strip() or (markdown and re.match(r"^#{1,6}\s", lines[i])):
                break
            i += 1
        out.append(block("\n".join(lines[start:i]), {"section":section,
                         "line_start":start+1, "line_end":i}))
    return out


def parse_pdf(data: bytes, settings: KnowledgeSettings) -> list[dict]:
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise IngestionError("ENCRYPTED_PDF", review=True)
    if len(reader.pages) > settings.max_pdf_pages:
        raise IngestionError("PDF_TOO_MANY_PAGES")
    pages, total = [], 0
    for page in reader.pages:
        text = page.extract_text() or ""
        if len(re.sub(r"\s", "", text)) < 20:
            raise IngestionError("NEEDS_OCR", review=True)
        total += len(text)
        if total > settings.max_text_chars:
            raise IngestionError("TEXT_TOO_LARGE")
        pages.append(text.splitlines())
    # Only repeated edge lines, never arbitrary repeated sentences in the body.
    def normalized(line):
        return re.sub(r"\d+", "#", line.strip())
    counts = Counter(key for page in pages
                     for key in {normalized(s) for s in page[:3] + page[-3:]})
    repeated = {k for k, n in counts.items() if len(pages) > 1 and n >= max(2, len(pages)*.8)}
    out = []
    for n, lines in enumerate(pages, 1):
        kept = [s for i, s in enumerate(lines)
                if not ((i < 3 or i >= len(lines)-3) and normalized(s) in repeated)]
        out.append(block("\n".join(kept), {"page":n, "section":""}))
    return out


def parse_docx(data: bytes) -> list[dict]:
    with ZipFile(io.BytesIO(data)) as archive:
        if sum(item.file_size for item in archive.infolist()) > 64 * 1024 * 1024:
            raise IngestionError("DOCX_EXPANDED_TOO_LARGE")
    doc = Document(io.BytesIO(data))
    out, section = [], ""
    paragraph, table = 0, 0
    for element in doc.element.body:
        if isinstance(element, CT_P):
            paragraph += 1
            p = Paragraph(element, doc)
            if p.style.name.startswith("Heading") or p.style.name == "Title":
                section = p.text
            elif p.text.strip():
                out.append(block(p.text, {"section":section, "paragraph":paragraph}))
        elif isinstance(element, CT_Tbl):
            table += 1
            t = Table(element, doc)
            header = " | ".join(c.text for c in t.rows[0].cells)
            for row, record in enumerate(t.rows[1:], 2):
                out.append(block(" | ".join(c.text for c in record.cells),
                                 {"section":section, "table":table, "row":row},
                                 table=True, header=header))
    return out
