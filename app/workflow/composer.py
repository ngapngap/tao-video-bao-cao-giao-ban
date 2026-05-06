"""Workflow composer cho AI Pass 1."""

from __future__ import annotations

import os
import sys
from pathlib import Path


class WorkflowComposer:
    """Tạo workflow từ extracted data + template."""

    def __init__(self, template_path: str = "workflow.md"):
        self.template_path = template_path

    def _find_template_path(self) -> str:
        """Tìm workflow.md từ nhiều vị trí runtime/dev/portable."""
        configured_path = Path(self.template_path or "workflow.md")
        app_data_root = Path(os.environ.get("APPDATA") or "") / "TaoVideoBaoCaoGiaoBan" if os.environ.get("APPDATA") else None
        candidates = [
            configured_path,
            Path.cwd() / configured_path,
            Path(__file__).resolve().parents[2] / "workflow.md",
            Path(getattr(sys, "_MEIPASS", Path.cwd())) / "workflow.md",
            Path(sys.executable).resolve().parent / "workflow.md" if getattr(sys, "frozen", False) else Path.cwd() / "workflow.md",
        ]
        if app_data_root is not None:
            candidates.append(app_data_root / "workflow.md")

        seen: set[Path] = set()
        for path in candidates:
            normalized = path.resolve() if not path.is_absolute() else path
            if normalized in seen:
                continue
            seen.add(normalized)
            if normalized.exists() and normalized.is_file():
                return str(normalized)
        return ""

    def load_template(self) -> str:
        """Đọc workflow template hoặc trả template mặc định khi file không có trong portable."""
        template_path = self._find_template_path()
        if template_path:
            return Path(template_path).read_text(encoding="utf-8")
        return self.default_template()

    @staticmethod
    def default_template() -> str:
        """Template workflow tối thiểu dùng khi portable không có workflow.md cạnh executable."""
        return """# Workflow mặc định - Báo cáo giao ban

## Metadata
- template_version: wf.v2
- resolution: 1920x1080
- fps: 30
- aspect_ratio: 16:9

## Scene rules
1. Bắt buộc có đúng một scene intro ở đầu video.
2. Bắt buộc có đúng một scene closing ở cuối video.
3. Scene content phải map source_data_keys về metric/section hợp lệ.
4. TTS mặc định dùng voice vi-VN-NamMinhNeural và duration_policy tts_first.
5. Không thêm số liệu ngoài extracted report.
"""

    def compose_from_ai_output(self, workflow_data: dict, report_month: str, job_id: str) -> dict:
        """Nhận output từ AI, đảm bảo metadata đúng, trả workflow dict."""
        if "workflow_metadata" not in workflow_data:
            workflow_data["workflow_metadata"] = {
                "template_version": "wf.v2",
                "report_month": report_month,
                "job_id": job_id,
            }
        return workflow_data

    def compose_from_extracted_report(self, extracted_report: dict, report_month: str, job_id: str) -> dict:
        """Tạo workflow cơ bản từ extracted report mà không cần AI (fallback/mock)."""
        scenes = [
            {
                "scene_id": "scene_intro",
                "scene_type": "intro",
                "title": f"Giới thiệu báo cáo tháng {report_month}",
                "objective": "Mở đầu video báo cáo giao ban",
                "source_data_keys": [],
                "tts": {"enabled": True, "text": f"Xin chào, đây là báo cáo giao ban tháng {report_month}."},
                "duration_policy": {"mode": "tts_first", "min_seconds": 4, "max_seconds": 12},
            }
        ]

        metrics = extracted_report.get("metrics", [])
        for i, metric in enumerate(metrics, 1):
            scenes.append(
                {
                    "scene_id": f"scene_content_{i:02d}",
                    "scene_type": "content",
                    "title": metric.get("metric_name", f"Metric {i}"),
                    "objective": f"Trình bày {metric.get('metric_name', '')}",
                    "source_data_keys": [metric.get("metric_key", "")],
                    "tts": {
                        "enabled": True,
                        "text": f"{metric.get('metric_name', '')}: {metric.get('value', '')} {metric.get('unit', '')}",
                    },
                    "duration_policy": {"mode": "tts_first", "min_seconds": 5, "max_seconds": 20},
                }
            )

        scenes.append(
            {
                "scene_id": "scene_closing",
                "scene_type": "closing",
                "title": "Kết thúc",
                "objective": "Kết thúc video",
                "source_data_keys": [],
                "tts": {"enabled": False, "text": ""},
                "duration_policy": {"mode": "fixed", "min_seconds": 4, "max_seconds": 8},
            }
        )

        return {
            "workflow_metadata": {
                "template_version": "wf.v2",
                "report_month": report_month,
                "job_id": job_id,
            },
            "video_settings": {"fps": 30, "resolution": "1920x1080", "aspect_ratio": "16:9"},
            "scenes": scenes,
        }
