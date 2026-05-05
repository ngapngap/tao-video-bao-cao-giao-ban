"""Tests cho PDF parser và normalizer."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.pdf import DataNormalizer, PDFParser


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample.pdf"


def test_parse_sample_pdf_extracts_text_chunks_and_tables():
    result = PDFParser(str(FIXTURE_PATH)).parse()

    assert result.file_path == str(FIXTURE_PATH)
    assert result.total_pages == 1
    assert result.text_chunks
    assert "BAO CAO GIAO BAN" in result.raw_text
    assert "BHXH" in result.raw_text
    assert result.table_chunks
    assert result.table_chunks[0].headers == ["Chi tieu", "Gia tri"]
    assert result.table_chunks[0].rows[0] == ["So thu", "1.234.567,89"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.234.567,89", 1234567.89),
        ("1,234,567.89", 1234567.89),
        ("1 234 567", 1234567.0),
        ("12,5", 12.5),
        ("1,234,567", 1234567.0),
        ("₫ 2.500", 2.5),
        ("", None),
        ("khong phai so", None),
    ],
)
def test_normalize_number_formats(value: str, expected: float | None):
    assert DataNormalizer.normalize_number(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("05/05/2026", "2026-05-05"),
        ("5/5/2026", "2026-05-05"),
        ("05-05-2026", "2026-05-05"),
        ("2026/05/05", "2026-05-05"),
        ("khong phai ngay", None),
    ],
)
def test_normalize_date_formats(value: str, expected: str | None):
    assert DataNormalizer.normalize_date(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("12,5%", 0.125),
        ("10%", 0.1),
        ("0,5%", 0.005),
        ("khong phai phan tram", None),
    ],
)
def test_normalize_percentage(value: str, expected: float | None):
    assert DataNormalizer.normalize_percentage(value) == expected


def test_expand_abbreviation():
    text = "BHXH, BHYT, BHTN va ATVSLĐ"

    expanded = DataNormalizer.expand_abbreviation(text)

    assert "Bảo hiểm xã hội" in expanded
    assert "Bảo hiểm y tế" in expanded
    assert "Bảo hiểm thất nghiệp" in expanded
    assert "An toàn vệ sinh lao động" in expanded


def test_normalize_text_whitespace():
    assert DataNormalizer.normalize_text("  Bao   cao\n giao\tban  ") == "Bao cao giao ban"
