"""PDF parsing utilities for extracting text blocks and tables."""

from __future__ import annotations

from dataclasses import dataclass

import pdfplumber
import pymupdf


@dataclass
class TextChunk:
    page_no: int
    text: str
    block_no: int = 0


@dataclass
class TableChunk:
    page_no: int
    table_no: int
    headers: list[str]
    rows: list[list[str]]


@dataclass
class PDFParseResult:
    file_path: str
    total_pages: int
    text_chunks: list[TextChunk]
    table_chunks: list[TableChunk]
    raw_text: str


class PDFParser:
    """Parse PDF dùng pymupdf chính, pdfplumber fallback cho bảng."""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def parse(self) -> PDFParseResult:
        """Parse toàn bộ PDF, trả text chunks + table chunks."""
        text_chunks = self._extract_text_pymupdf()
        table_chunks = self._extract_tables_pdfplumber()
        raw_text = "\n".join(chunk.text for chunk in text_chunks)
        total_pages = max(
            [chunk.page_no for chunk in text_chunks] + [chunk.page_no for chunk in table_chunks],
            default=0,
        )
        return PDFParseResult(
            file_path=self.file_path,
            total_pages=total_pages,
            text_chunks=text_chunks,
            table_chunks=table_chunks,
            raw_text=raw_text,
        )

    def _extract_text_pymupdf(self) -> list[TextChunk]:
        """Dùng pymupdf extract text từng page."""
        doc = pymupdf.open(self.file_path)
        chunks: list[TextChunk] = []
        try:
            for page_no, page in enumerate(doc, 1):
                blocks = page.get_text("blocks")
                for block_no, block in enumerate(blocks):
                    text = block[4].strip()
                    if text:
                        chunks.append(TextChunk(page_no=page_no, text=text, block_no=block_no))
        finally:
            doc.close()
        return chunks

    def _extract_tables_pdfplumber(self) -> list[TableChunk]:
        """Dùng pdfplumber extract tables (fallback cho bảng)."""
        chunks: list[TableChunk] = []
        with pdfplumber.open(self.file_path) as pdf:
            for page_no, page in enumerate(pdf.pages, 1):
                tables = page.extract_tables()
                for table_no, table in enumerate(tables):
                    if not table or len(table) < 2:
                        continue
                    headers = [str(h or "") for h in table[0]]
                    rows = [[str(cell or "") for cell in row] for row in table[1:]]
                    chunks.append(
                        TableChunk(
                            page_no=page_no,
                            table_no=table_no,
                            headers=headers,
                            rows=rows,
                        )
                    )
        return chunks
