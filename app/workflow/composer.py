"""Workflow composer cho AI Pass 1."""

from __future__ import annotations


class WorkflowComposer:
    """Tạo workflow từ extracted data + template."""

    def __init__(self, template_path: str = "workflow.md"):
        self.template_path = template_path

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
