"""Data normalization helpers for parsed PDF content."""

from __future__ import annotations

import re


class DataNormalizer:
    """Chuẩn hoá text/numbers từ PDF parse result."""

    @staticmethod
    def normalize_number(text: str) -> float | None:
        """Chuẩn hoá số: 1.234.567,89 -> 1234567.89 hoặc 1,234,567.89 -> 1234567.89."""
        if not text or not text.strip():
            return None
        text = text.strip()
        text = re.sub(r"[₫$€£¥]", "", text)
        text = re.sub(r"(?<=\d)\s+(?=\d)", "", text)

        has_dot = "." in text
        has_comma = "," in text

        if has_dot and has_comma:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        elif has_comma:
            parts = text.split(",")
            if len(parts) == 2 and len(parts[1]) <= 2:
                text = text.replace(",", ".")
            else:
                text = text.replace(",", "")
        elif has_dot:
            parts = text.split(".")
            if len(parts) > 2:
                text = text.replace(".", "")

        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def normalize_date(text: str) -> str | None:
        """Chuẩn hoá ngày tháng: dd/mm/yyyy -> yyyy-mm-dd."""
        text = text.strip()
        patterns = [
            (
                r"(\d{1,2})/(\d{1,2})/(\d{4})",
                lambda m: f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}",
            ),
            (
                r"(\d{1,2})-(\d{1,2})-(\d{4})",
                lambda m: f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}",
            ),
            (
                r"(\d{4})/(\d{1,2})/(\d{1,2})",
                lambda m: f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}",
            ),
        ]
        for pattern, replacer in patterns:
            match = re.match(pattern, text)
            if match:
                return replacer(match)
        return None

    @staticmethod
    def normalize_percentage(text: str) -> float | None:
        """Chuẩn hoá phần trăm: 12,5% -> 0.125."""
        text = text.strip().replace("%", "")
        value = DataNormalizer.normalize_number(text)
        if value is not None:
            return value / 100.0
        return None

    @staticmethod
    def expand_abbreviation(text: str) -> str:
        """Mở rộng viết tắt phổ biến trong báo cáo BHXH."""
        abbreviations = {
            "BHXH": "Bảo hiểm xã hội",
            "BHYT": "Bảo hiểm y tế",
            "BHTN": "Bảo hiểm thất nghiệp",
            "TNCN": "Thu nhập cá nhân",
            "PCCC": "Phòng cháy chữa cháy",
            "ATVSLĐ": "An toàn vệ sinh lao động",
            "CNVCLĐ": "Công nhân viên chức lao động",
            "QĐ": "Quyết định",
            "TT": "Thông tư",
            "NĐ": "Nghị định",
        }
        result = text
        for abbr, full in abbreviations.items():
            result = result.replace(abbr, full)
        return result

    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalize whitespace và unicode."""
        text = re.sub(r"\s+", " ", text).strip()
        return text
