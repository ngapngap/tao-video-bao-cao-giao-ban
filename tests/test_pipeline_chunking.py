"""Tests cho merge extraction chunks và prompt screen planning."""

from __future__ import annotations

from app.ai.prompts import P1_1B_SCREEN_PLANNING, P1_1_CHUNK_EXTRACTION
from app.main import App


def test_merge_llm_extracts_combines_metrics_sections_and_warnings():
    app = App.__new__(App)
    merged = app._merge_llm_extracts(
        [
            {
                "report_metadata": {"title": "Báo cáo", "period": "202605"},
                "metrics": [{"metric_key": "m1", "value": "1"}],
                "sections": [{"section_key": "s1", "summary": "A"}],
                "warnings": ["w1"],
            },
            {
                "report_metadata": {"organization": "Đơn vị"},
                "metrics": [{"metric_key": "m2", "value": "2"}],
                "sections": [{"section_key": "s2", "summary": "B"}],
                "warnings": ["w2"],
            },
        ]
    )

    assert merged["report_metadata"] == {"title": "Báo cáo", "period": "202605", "organization": "Đơn vị"}
    assert [metric["metric_key"] for metric in merged["metrics"]] == ["m1", "m2"]
    assert [section["section_key"] for section in merged["sections"]] == ["s1", "s2"]
    assert merged["warnings"] == ["w1", "w2"]


def test_prompt_contracts_include_chunk_resume_and_screen_planning_requirements():
    assert "MỘT PHẦN" in P1_1_CHUNK_EXTRACTION
    assert "chunk {chunk_index}/{total_chunks}" in P1_1_CHUNK_EXTRACTION
    assert "Không bịa số liệu" in P1_1_CHUNK_EXTRACTION
    assert "metrics=[]" in P1_1_CHUNK_EXTRACTION
    assert "citations là list" in P1_1_CHUNK_EXTRACTION
    assert "source_snippet" in P1_1_CHUNK_EXTRACTION
    assert "confidence" in P1_1_CHUNK_EXTRACTION
    assert "screen đầu tiên là intro" in P1_1B_SCREEN_PLANNING
    assert "screen cuối cùng là closing" in P1_1B_SCREEN_PLANNING


def test_chunk_workflow_sections_splits_metrics_and_keeps_screen_plan():
    app = App.__new__(App)
    extracted_report = {
        "report_metadata": {"title": "Báo cáo"},
        "metrics": [{"metric_key": f"m{i}"} for i in range(6)],
        "sections": [{"section_key": f"s{i}"} for i in range(3)],
    }
    screen_plan = {"screens": [{"screen_id": "intro"}, {"screen_id": "closing"}]}

    chunks = app._chunk_workflow_sections(extracted_report, screen_plan, max_items=5)

    assert len(chunks) == 2
    assert [metric["metric_key"] for metric in chunks[0]["metrics"]] == ["m0", "m1", "m2", "m3", "m4"]
    assert [metric["metric_key"] for metric in chunks[1]["metrics"]] == ["m5"]
    assert chunks[0]["screens"] == screen_plan["screens"]


def test_merge_workflow_chunks_dedupes_scene_ids():
    app = App.__new__(App)
    merged = app._merge_workflow_chunks(
        [
            {"scenes": [{"scene_id": "scene_intro", "scene_type": "intro"}, {"scene_id": "scene_content_01", "scene_type": "content"}]},
            {"scenes": [{"scene_id": "scene_content_01", "scene_type": "content"}, {"scene_id": "scene_closing", "scene_type": "closing"}]},
        ],
        "202605",
        "job-001",
    )

    assert [scene["scene_id"] for scene in merged["scenes"]] == ["scene_intro", "scene_content_01", "scene_closing"]
    assert merged["workflow_metadata"]["report_month"] == "202605"
    assert merged["workflow_metadata"]["job_id"] == "job-001"
