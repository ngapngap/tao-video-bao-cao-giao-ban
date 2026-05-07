"""Run a real-app-like E2E pipeline against the real PDF and LLM API.

Windows cmd.exe example:
  set PYTHONIOENCODING=utf-8
  set LLM_EXTRACT_URL=http://10.48.240.50:20128/v1
  set LLM_EXTRACT_KEY=sk-...
  set LLM_EXTRACT_MODEL=minimax/MiniMax-M2.7
  python scripts/test_real_app_flow.py

The script does not hard-code secrets. Outputs are written under outputs/YYYYMM/<job_id>/.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import asdict, is_dataclass
from typing import Any, Callable

sys.path.insert(0, ".")

from app.ai.llm_client import LLMClient
from app.ai.prompts import P1_1_CHUNK_EXTRACTION, P1_1B_SCREEN_PLANNING, P1_2_WORKFLOW_COMPOSITION
from app.ai.schemas import ExtractedReport, RawLLMExtractedReport
from app.core.chunk_processor import ChunkProcessor
from app.video.prompts import (
    S2_1_SCENE_PLANNING,
    S2_2_VISUAL_SPEC,
    S2_3_NARRATION_TTS,
    S2_4_COMPONENT_SPEC,
    S2_5_ASSET_PLAN,
    S2_6_RENDER_PLAN,
    S2_7_QA_FIX,
    S2_8_FINAL_PACKAGING,
)
from app.pdf.normalizer import DataNormalizer
from app.pdf.parser import PDFParser
from app.workflow.composer import WorkflowComposer
from app.workflow.validator import WorkflowValidator
from app.video.remotion_handoff import FinalPackager, RemotionManifest, RenderGate, TTSGenerator

PDF_PATH = Path(
    os.environ.get(
        "REAL_PIPELINE_PDF",
        "outputs/202603/20260506-033202/input/2026 - Báo cáo tháng 3 fn.pdf",
    )
)
REPORT_MONTH = os.environ.get("REAL_PIPELINE_REPORT_MONTH", "202603")
JOB_ID = os.environ.get("REAL_PIPELINE_JOB_ID", datetime.now().strftime("%Y%m%d-%H%M%S-real-app-flow"))
OUTPUT_DIR = Path(os.environ.get("REAL_PIPELINE_OUTPUT_DIR", f"outputs/{REPORT_MONTH}/{JOB_ID}"))
URL = os.environ.get("LLM_EXTRACT_URL", "http://10.48.240.50:20128/v1")
KEY = os.environ.get("LLM_EXTRACT_KEY", "").strip()
MODEL = os.environ.get("LLM_EXTRACT_MODEL", "minimax/MiniMax-M2.7")
MAX_CHARS = int(os.environ.get("REAL_PIPELINE_CHUNK_CHARS", "4000"))
MAX_WORKERS = int(os.environ.get("REAL_PIPELINE_MAX_WORKERS", "5"))
MAX_TOKENS = int(os.environ.get("REAL_PIPELINE_MAX_TOKENS", "6000"))
S2_MAX_TOKENS = int(os.environ.get("REAL_PIPELINE_S2_MAX_TOKENS", "700"))
STEP_TIMEOUTS = {
    "S1.1": 30.0,
    "S1.2": 30.0,
    "S1.3": 30.0,
    "P1.1": 600.0,  # 10 phút cho multi-chunk.
    "P1.1b": 120.0,
    "P1.2": 300.0,  # Workflow composition có thể mất lâu hơn 2 phút.
    "S2.1": 180.0,
    "S2.2": 180.0,
    "S2.3": 180.0,
    "S2.4": 120.0,
    "S2.5": 120.0,
    "S2.6": 120.0,
    "S2.7": 120.0,
    "S2.8": 180.0,
}
STEP_TIMEOUT_SECONDS = float(os.environ.get("REAL_PIPELINE_STEP_TIMEOUT_SECONDS", "180"))
S2_TIMEOUT_SECONDS = float(os.environ.get("REAL_PIPELINE_S2_TIMEOUT_SECONDS", "120"))
S2_LLM_TIMEOUT_SECONDS = float(os.environ.get("REAL_PIPELINE_S2_LLM_TIMEOUT_SECONDS", "115"))
METRICS_MIN_COUNT = int(os.environ.get("REAL_PIPELINE_MIN_METRICS", "30"))
PIPELINE_MAX_SECONDS = float(os.environ.get("REAL_PIPELINE_MAX_SECONDS", "900"))
P1_TOTAL_MAX_SECONDS = float(os.environ.get("REAL_PIPELINE_P1_TOTAL_MAX_SECONDS", "360"))
S2_TOTAL_MAX_SECONDS = float(os.environ.get("REAL_PIPELINE_S2_TOTAL_MAX_SECONDS", "240"))
S2_MODE = "llm"

STEP_DEFINITIONS = [
    ("S1.1", "Chuẩn bị thư mục"),
    ("S1.2", "Copy PDF"),
    ("S1.3", "Parse PDF"),
    ("P1.1", "Extract chunks"),
    ("P1.1b", "Screen planning"),
    ("P1.2", "Compose workflow"),
    ("S2.1", "Scene planning"),
    ("S2.2", "Visual spec"),
    ("S2.3", "TTS script"),
    ("S2.4", "Component spec"),
    ("S2.5", "Asset plan"),
    ("S2.6", "Render plan"),
    ("S2.7", "QA fix"),
    ("S2.8", "Final packaging"),
]

S2_ARTIFACTS = {
    "S2.1": "remotion/scene-plan.json",
    "S2.2": "remotion/visual-spec.json",
    "S2.3": "tts/tts-script.json",
    "S2.4": "remotion/component-spec.json",
    "S2.5": "remotion/asset-plan.json",
    "S2.6": "remotion/render-plan.json",
    "S2.7": "remotion/qa-fix.json",
    "S2.8": "final/publish-manifest.json",
}

S2_PROMPTS = {
    "S2.1": S2_1_SCENE_PLANNING,
    "S2.2": S2_2_VISUAL_SPEC,
    "S2.3": S2_3_NARRATION_TTS,
    "S2.4": S2_4_COMPONENT_SPEC,
    "S2.5": S2_5_ASSET_PLAN,
    "S2.6": S2_6_RENDER_PLAN,
    "S2.7": S2_7_QA_FIX,
    "S2.8": S2_8_FINAL_PACKAGING,
}

S2_REQUIRED_UPSTREAM = {
    "S2.1": ["workflow/workflow-validation.json"],
    "S2.2": ["remotion/scene-plan.json"],
    "S2.3": ["remotion/scene-plan.json"],
    "S2.4": ["remotion/scene-plan.json", "remotion/visual-spec.json", "tts/tts-script.json"],
    "S2.5": ["remotion/component-spec.json"],
    "S2.6": ["tts/tts-script.json", "remotion/component-spec.json"],
    "S2.7": ["remotion/render-plan.json"],
    "S2.8": ["remotion/qa-fix.json", "remotion/render-plan.json"],
}


def step_timeout(step_id: str) -> float:
    return float(os.environ.get(f"REAL_PIPELINE_{step_id.replace('.', '_')}_TIMEOUT_SECONDS", STEP_TIMEOUTS.get(step_id, STEP_TIMEOUT_SECONDS)))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mask_secret(text: str) -> str:
    return re.sub(r"sk-[A-Za-z0-9_-]+", "sk-****", text)


class RealAppFlow:
    def __init__(self) -> None:
        self.output_dir = OUTPUT_DIR
        self.llm = LLMClient(URL, KEY, MODEL, timeout=360.0)
        self.context: dict[str, Any] = {}
        self.state: dict[str, Any] = {
            "job_id": JOB_ID,
            "status": "DRAFT",
            "report_month": REPORT_MONTH,
            "current_step_id": None,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "steps": [
                {
                    "step_id": step_id,
                    "name": name,
                    "status": "PENDING",
                    "attempt": 0,
                    "started_at": None,
                    "ended_at": None,
                    "error_code": None,
                    "error_message": None,
                    "artifacts": [],
                    "duration_seconds": None,
                }
                for step_id, name in STEP_DEFINITIONS
            ],
        }

    @property
    def state_path(self) -> Path:
        return self.output_dir / "job_state.json"

    @property
    def events_path(self) -> Path:
        return self.output_dir / "logs" / "job-events.ndjson"

    def ensure_base_dirs(self) -> None:
        for rel in ["input", "parsed/chunks", "workflow/chunks", "tts", "remotion", "final", "logs"]:
            (self.output_dir / rel).mkdir(parents=True, exist_ok=True)

    def write_state(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.state["updated_at"] = now_iso()
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    def log(self, level: str, step_id: str | None, message: str) -> None:
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": now_iso(),
            "level": level,
            "step_id": step_id,
            "message": mask_secret(message),
            "job_id": JOB_ID,
        }
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"[{level}] [{step_id or 'JOB'}] {mask_secret(message)}")

    def step_record(self, step_id: str) -> dict[str, Any]:
        return next(item for item in self.state["steps"] if item["step_id"] == step_id)

    def run_step(self, step_id: str, handler: Callable[[], list[str]], timeout_seconds: float | None = None) -> None:
        step = self.step_record(step_id)
        step["attempt"] += 1
        step["status"] = "RUNNING"
        step["started_at"] = now_iso()
        step["ended_at"] = None
        step["error_code"] = None
        step["error_message"] = None
        self.state["status"] = "RUNNING"
        self.state["current_step_id"] = step_id
        self.write_state()
        self.log("INFO", step_id, f"START {step['name']}")
        start = time.time()
        try:
            if timeout_seconds is None:
                artifacts = handler()
            else:
                executor = ThreadPoolExecutor(max_workers=1)
                future = executor.submit(handler)
                try:
                    artifacts = future.result(timeout=timeout_seconds)
                finally:
                    executor.shutdown(wait=False, cancel_futures=True)
            elapsed = round(time.time() - start, 2)
            step["status"] = "DONE"
            step["ended_at"] = now_iso()
            step["duration_seconds"] = elapsed
            step["artifacts"] = artifacts
            self.write_state()
            self.log("INFO", step_id, f"DONE {step['name']} in {elapsed:.2f}s artifacts={artifacts}")
        except Exception as exc:  # noqa: BLE001 - smoke runner must persist failure evidence
            elapsed = round(time.time() - start, 2)
            step["status"] = "FAILED"
            step["ended_at"] = now_iso()
            step["duration_seconds"] = elapsed
            step["error_code"] = type(exc).__name__
            step["error_message"] = str(exc)
            self.state["status"] = "FAILED"
            self.write_state()
            self.log("ERROR", step_id, f"FAILED {step['name']} in {elapsed:.2f}s: {type(exc).__name__}: {exc}")
            raise

    def run(self) -> int:
        if not KEY:
            print("ERROR: Missing LLM_EXTRACT_KEY environment variable.")
            return 2
        start_total = time.time()
        self.run_step("S1.1", self.step_prepare_dirs, timeout_seconds=step_timeout("S1.1"))
        self.run_step("S1.2", self.step_copy_pdf, timeout_seconds=step_timeout("S1.2"))
        self.run_step("S1.3", self.step_parse_pdf, timeout_seconds=step_timeout("S1.3"))
        self.run_step("P1.1", self.step_extract_chunks, timeout_seconds=step_timeout("P1.1"))
        self.run_step("P1.1b", self.step_screen_plan, timeout_seconds=step_timeout("P1.1b"))
        self.run_step("P1.2", self.step_compose_workflow, timeout_seconds=step_timeout("P1.2"))
        for step_id in ["S2.1", "S2.2", "S2.3", "S2.4", "S2.5", "S2.6", "S2.7", "S2.8"]:
            self.run_step(step_id, lambda sid=step_id: self.step_video(sid), timeout_seconds=step_timeout(step_id))
        self.context["wall_clock_total_seconds"] = round(time.time() - start_total, 2)
        self.assert_final_acceptance()
        self.state["status"] = "DONE"
        self.state["current_step_id"] = None
        self.write_state()
        self.write_summary()
        self.log("INFO", None, "JOB DONE")
        return 0

    def step_prepare_dirs(self) -> list[str]:
        self.ensure_base_dirs()
        cache_dirs = [
            self.output_dir / "extract_chunks",
            self.output_dir / "parsed" / "chunks",
            self.output_dir / "workflow" / "chunks",
        ]
        for cache_dir in cache_dirs:
            if cache_dir.exists():
                shutil.rmtree(cache_dir)
                print(f"  Cleared chunk cache: {cache_dir}")
            cache_dir.mkdir(parents=True, exist_ok=True)
        for rel_dir in ["remotion", "tts", "final"]:
            target_dir = self.output_dir / rel_dir
            if target_dir.exists():
                shutil.rmtree(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
        return ["job_state.json", "logs/job-events.ndjson"]

    def step_copy_pdf(self) -> list[str]:
        if not PDF_PATH.exists():
            raise FileNotFoundError(PDF_PATH)
        dest = self.output_dir / "input" / "report-source.pdf"
        shutil.copy2(PDF_PATH, dest)
        self.context["input_pdf"] = dest
        return [dest.relative_to(self.output_dir).as_posix()]

    def step_parse_pdf(self) -> list[str]:
        pdf = self.context.get("input_pdf") or self.output_dir / "input" / "report-source.pdf"
        parse_result = PDFParser(str(pdf)).parse()
        raw_text = DataNormalizer.normalize_text(parse_result.raw_text)
        self.context["raw_text"] = raw_text
        pdf_text = {
            "source_pdf": str(pdf),
            "total_pages": parse_result.total_pages,
            "raw_text_length": len(raw_text),
            "text_chunks": [self.to_plain_data(chunk) for chunk in parse_result.text_chunks],
            "table_chunks": [self.to_plain_data(chunk) for chunk in parse_result.table_chunks],
            "raw_text": raw_text,
        }
        path = self.output_dir / "parsed" / "pdf-text.json"
        path.write_text(json.dumps(pdf_text, ensure_ascii=False, indent=2), encoding="utf-8")
        return [path.relative_to(self.output_dir).as_posix()]

    def chunk_text(self, text: str) -> list[str]:
        sections = re.split(r"\n(?=[IVX]+\.\s)", text)
        chunks: list[str] = []
        current = ""
        for section in sections:
            if len(section) > MAX_CHARS:
                if current:
                    chunks.append(current.strip())
                    current = ""
                chunks.extend(
                    section[i : i + MAX_CHARS].strip()
                    for i in range(0, len(section), MAX_CHARS)
                    if section[i : i + MAX_CHARS].strip()
                )
                continue
            if len(current) + len(section) + 1 > MAX_CHARS:
                if current:
                    chunks.append(current.strip())
                current = section
            else:
                current = f"{current}\n{section}" if current else section
        if current:
            chunks.append(current.strip())
        return chunks if chunks else [text[:MAX_CHARS]]

    def normalize_metric_item(self, item: dict[str, Any], fallback_key: str | None = None) -> dict[str, Any] | None:
        key = item.get("metric_key") or item.get("key") or fallback_key
        name = item.get("metric_name") or item.get("name") or (str(key).replace("_", " ").title() if key else "")
        if not key or "value" not in item:
            return None
        metric: dict[str, Any] = {
            "metric_key": str(key),
            "metric_name": str(name),
            "value": str(item.get("value", "")),
            "unit": str(item.get("unit", "")),
        }
        citations = item.get("citations")
        if isinstance(citations, list):
            normalized_citations = []
            for citation in citations:
                if not isinstance(citation, dict):
                    continue
                normalized_citations.append(
                    {
                        "page_no": citation.get("page_no"),
                        "source_snippet": str(citation.get("source_snippet", "")),
                        "confidence": self.normalize_confidence(citation.get("confidence", 0.0)),
                    }
                )
            metric["citations"] = normalized_citations
        return metric

    def normalize_confidence(self, value: Any) -> float:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return max(0.0, min(1.0, float(value)))
        normalized = str(value or "").strip().lower()
        if normalized in {"high", "cao", "very high"}:
            return 0.9
        if normalized in {"medium", "trung bình", "trung binh"}:
            return 0.6
        if normalized in {"low", "thấp", "thap"}:
            return 0.3
        try:
            return max(0.0, min(1.0, float(normalized)))
        except ValueError:
            return 0.0

    def collect_metrics_from_any(self, data: Any, prefix: str = "") -> list[dict[str, Any]]:
        metrics: list[dict[str, Any]] = []
        if isinstance(data, list):
            for index, item in enumerate(data):
                if isinstance(item, dict):
                    metric = self.normalize_metric_item(item, f"{prefix}.item_{index}".strip("."))
                    if metric:
                        metrics.append(metric)
                    else:
                        metrics.extend(self.collect_metrics_from_any(item, f"{prefix}.item_{index}".strip(".")))
            return metrics
        if not isinstance(data, dict):
            return metrics
        metric = self.normalize_metric_item(data, prefix or None)
        if metric:
            metrics.append(metric)
            return metrics
        for key, value in data.items():
            if key in {"report_metadata", "sections", "warnings", "citations"}:
                continue
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            metrics.extend(self.collect_metrics_from_any(value, next_prefix))
        return metrics

    def dedupe_metrics(self, metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str, str]] = set()
        deduped: list[dict[str, Any]] = []
        for metric in metrics:
            identity = (str(metric.get("metric_key", "")).strip(), str(metric.get("value", "")).strip(), str(metric.get("unit", "")).strip())
            if not identity[0] or identity in seen:
                continue
            seen.add(identity)
            deduped.append(metric)
        return deduped

    def normalize_sections(self, sections: Any) -> list[dict[str, Any]]:
        normalized_sections: list[dict[str, Any]] = []
        if not isinstance(sections, list):
            return normalized_sections
        for index, section in enumerate(sections):
            if not isinstance(section, dict):
                continue
            section_key = section.get("section_key") or section.get("key") or section.get("section_id") or f"section_{index + 1:02d}"
            summary = section.get("summary") or section.get("section_summary") or section.get("content") or section.get("text") or section.get("section_title") or ""
            normalized: dict[str, Any] = {
                "section_key": str(section_key),
                "summary": str(summary),
                "citations": section.get("citations", []) if isinstance(section.get("citations"), list) else [],
            }
            normalized_sections.append(normalized)
        return normalized_sections

    def merge_extract_results(self, chunk_results: list[dict[str, Any]]) -> dict[str, Any]:
        merged: dict[str, Any] = {"report_metadata": {}, "metrics": [], "sections": [], "warnings": []}
        for report in chunk_results:
            if not isinstance(report, dict):
                continue
            if isinstance(report.get("report_metadata"), dict):
                merged["report_metadata"].update({k: v for k, v in report["report_metadata"].items() if v})
            merged["metrics"].extend(self.collect_metrics_from_any(report.get("metrics", [])))
            if isinstance(report.get("sections"), list):
                merged["sections"].extend(report["sections"])
            if isinstance(report.get("warnings"), list):
                merged["warnings"].extend(str(w) for w in report["warnings"])
            merged["metrics"].extend(
                self.collect_metrics_from_any({k: v for k, v in report.items() if k not in {"metrics", "sections", "warnings", "report_metadata"}})
            )
        merged["metrics"] = self.dedupe_metrics(merged["metrics"])
        rm = merged.get("report_metadata") if isinstance(merged.get("report_metadata"), dict) else {}
        normalized = {
            "report_metadata": {
                "title": str(rm.get("title") or rm.get("report_title") or "Báo cáo giao ban"),
                "period": str(rm.get("period") or rm.get("report_month") or REPORT_MONTH),
                "organization": str(rm.get("organization") or rm.get("owner_org") or ""),
            },
            "metrics": merged["metrics"],
            "sections": self.normalize_sections(merged["sections"]),
            "warnings": merged["warnings"],
        }
        return normalized

    def step_extract_chunks(self) -> list[str]:
        raw_text = self.context.get("raw_text")
        if not raw_text:
            pdf_text = json.loads((self.output_dir / "parsed" / "pdf-text.json").read_text(encoding="utf-8"))
            raw_text = pdf_text["raw_text"]
        chunks = self.chunk_text(raw_text)
        self.context["extract_chunk_count"] = len(chunks)
        chunk_dir = self.output_dir / "parsed" / "chunks"
        chunk_dir.mkdir(parents=True, exist_ok=True)

        def process_one(index: int, chunk: str) -> tuple[int, dict[str, Any], float]:
            cache_path = chunk_dir / f"chunk_{index:03d}.json"
            start = time.time()
            if cache_path.exists():
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(cached, dict):
                    cached.setdefault("_chunk_runtime", {"chunk_index": index, "chars": len(chunk), "seconds": 0.0, "cached": True})
                    return index, cached, 0.0
            payload = json.dumps(
                {
                    "report_month": REPORT_MONTH,
                    "chunk_index": index,
                    "total_chunks": len(chunks),
                    "chunk_text": chunk,
                },
                ensure_ascii=False,
            )
            result = self.llm.chat_with_retry_parse(P1_1_CHUNK_EXTRACTION, payload, max_parse_retries=2, max_tokens=MAX_TOKENS, timeout=step_timeout("P1.1"))
            RawLLMExtractedReport.model_validate(result)
            elapsed = round(time.time() - start, 2)
            result["_chunk_runtime"] = {"chunk_index": index, "chars": len(chunk), "seconds": elapsed}
            return index, result, elapsed

        timings: list[dict[str, Any]] = []

        def processor(index: int, chunk: str) -> dict[str, Any]:
            chunk_index, result, elapsed = process_one(index, chunk)
            timings.append({"chunk_index": chunk_index, "seconds": elapsed, "metrics": len(result.get("metrics", []))})
            self.log("INFO", "P1.1", f"chunk {chunk_index + 1}/{len(chunks)} DONE in {elapsed:.2f}s")
            return result

        chunk_processor = ChunkProcessor(str(self.output_dir / "parsed"), "chunks")
        chunk_processor.clear_cache()
        results = chunk_processor.process_chunks(
            chunks,
            processor,
            max_retry=1,
            parallel=True,
            max_workers=min(MAX_WORKERS, len(chunks)),
        )
        normalized = self.merge_extract_results(results)
        ExtractedReport.model_validate(normalized)
        validation = WorkflowValidator().validate_extracted_report(normalized)
        extracted_path = self.output_dir / "parsed" / "extracted-report.json"
        validation_path = self.output_dir / "parsed" / "extracted-report.validation.json"
        extracted_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        validation_path.write_text(json.dumps(validation.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        self.context["extracted_report"] = normalized
        self.context["p1_1_chunk_timings"] = sorted(timings, key=lambda item: item["chunk_index"])
        metrics_count = len(normalized.get("metrics", []))
        self.context["metrics_count"] = metrics_count
        if metrics_count < METRICS_MIN_COUNT:
            raise ValueError(f"metrics count must be >= {METRICS_MIN_COUNT}, got {metrics_count}")
        if not validation.passed:
            raise ValueError(f"Extracted report validation failed: {validation.errors}")
        return [
            *[(Path("parsed/chunks") / f"chunk_{i:03d}.json").as_posix() for i in range(len(chunks))],
            "parsed/extracted-report.json",
            "parsed/extracted-report.validation.json",
        ]

    def step_screen_plan(self) -> list[str]:
        extracted = self.context.get("extracted_report") or json.loads((self.output_dir / "parsed" / "extracted-report.json").read_text(encoding="utf-8"))
        path = self.output_dir / "parsed" / "screen-plan.json"
        if path.exists():
            path.unlink()
        payload = json.dumps({"report_month": REPORT_MONTH, "extracted_report": self.compact_extracted_report(extracted, metric_limit=40)}, ensure_ascii=False)
        result = self.llm.chat_with_retry_parse(P1_1B_SCREEN_PLANNING, payload, max_parse_retries=2, max_tokens=MAX_TOKENS, timeout=step_timeout("P1.1b"))
        screens = result.get("screens", [])
        if not isinstance(screens, list):
            raise ValueError("screen-plan screens must be a list")
        if len(screens) > 10:
            self.log("WARN", "P1.1b", f"screen-plan returned {len(screens)} screens; trimming content screens to 10 total")
            screens = [screens[0], *screens[1:9], screens[-1]]
        if len(screens) < 6:
            raise ValueError(f"screen-plan must have 6-10 screens, got {len(screens)}")
        if screens[0].get("screen_type") != "intro" and screens[0].get("screen_id") != "intro":
            screens[0]["screen_type"] = "intro"
        if screens[-1].get("screen_type") != "closing" and screens[-1].get("screen_id") != "closing":
            screens[-1]["screen_type"] = "closing"
        screens = self.normalize_screen_data_keys(screens, extracted)
        self.validate_screen_plan({"screens": screens}, extracted)
        path.write_text(json.dumps({"screens": screens}, ensure_ascii=False, indent=2), encoding="utf-8")
        self.context["screen_plan"] = {"screens": screens}
        return ["parsed/screen-plan.json"]

    def step_compose_workflow(self) -> list[str]:
        extracted = self.context.get("extracted_report") or json.loads((self.output_dir / "parsed" / "extracted-report.json").read_text(encoding="utf-8"))
        screen_plan = self.context.get("screen_plan") or json.loads((self.output_dir / "parsed" / "screen-plan.json").read_text(encoding="utf-8"))
        for old_workflow in (self.output_dir / "workflow").glob("workflow-*.json"):
            old_workflow.unlink()
        for old_workflow_md in (self.output_dir / "workflow").glob("workflow-*.md"):
            old_workflow_md.unlink()
        validation_path = self.output_dir / "workflow" / "workflow-validation.json"
        if validation_path.exists():
            validation_path.unlink()
        payload = json.dumps(
            {
                "report_month": REPORT_MONTH,
                "job_id": JOB_ID,
                "screen_plan": screen_plan,
                "extracted_report": {
                    "report_metadata": extracted.get("report_metadata", {}),
                    "metrics": extracted.get("metrics", [])[:24],
                    "sections": extracted.get("sections", [])[:8],
                    "warnings": extracted.get("warnings", [])[:6],
                },
                "workflow_template_excerpt": WorkflowComposer("workflow.md").load_template()[:5000],
            },
            ensure_ascii=False,
        )
        result = self.llm.chat_with_retry_parse(P1_2_WORKFLOW_COMPOSITION, payload, max_parse_retries=2, max_tokens=MAX_TOKENS, timeout=step_timeout("P1.2"))
        result = WorkflowComposer("workflow.md").compose_from_ai_output(result, REPORT_MONTH, JOB_ID)
        result = self.normalize_workflow_result(result, screen_plan, extracted)
        scenes = result.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            raise ValueError("workflow must have scenes")
        return self.write_workflow_artifacts(result, extracted)

    def write_workflow_artifacts(self, result: dict[str, Any], extracted: dict[str, Any]) -> list[str]:
        chunk_path = self.output_dir / "workflow" / "chunks" / "chunk_000.json"
        workflow_json_path = self.output_dir / "workflow" / f"workflow-{REPORT_MONTH}-{JOB_ID}.json"
        workflow_md_path = self.output_dir / "workflow" / f"workflow-{REPORT_MONTH}-{JOB_ID}.md"
        validation_path = self.output_dir / "workflow" / "workflow-validation.json"
        validation = WorkflowValidator().validate(result, extracted)
        chunk_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        workflow_json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        workflow_md_path.write_text("# Workflow generated\n\n```json\n" + json.dumps(result, ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")
        validation_path.write_text(json.dumps(validation.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        self.context["workflow"] = result
        if not validation.passed:
            raise ValueError(f"workflow validation failed: {validation.errors}")
        return [
            "workflow/chunks/chunk_000.json",
            workflow_json_path.relative_to(self.output_dir).as_posix(),
            workflow_md_path.relative_to(self.output_dir).as_posix(),
            "workflow/workflow-validation.json",
        ]

    def normalize_workflow_result(self, result: dict[str, Any], screen_plan: dict[str, Any], extracted: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(result, dict):
            result = {}
        if "scenes" not in result or not isinstance(result.get("scenes"), list):
            result = self.build_workflow_from_screen_plan(screen_plan, extracted)
        result["workflow_metadata"] = {"template_version": "wf.v2", "report_month": REPORT_MONTH, "job_id": JOB_ID}
        video_settings = result.get("video_settings") if isinstance(result.get("video_settings"), dict) else {}
        resolution = video_settings.get("resolution", "1920x1080")
        if isinstance(resolution, dict):
            resolution = f"{resolution.get('width', 1920)}x{resolution.get('height', 1080)}"
        result["video_settings"] = {"fps": int(video_settings.get("fps", 30) or 30), "resolution": str(resolution), "aspect_ratio": str(video_settings.get("aspect_ratio", "16:9"))}
        result["scenes"] = [self.normalize_scene(scene, index, extracted) for index, scene in enumerate(result.get("scenes", [])) if isinstance(scene, dict)]
        if not result["scenes"]:
            result = self.build_workflow_from_screen_plan(screen_plan, extracted)
        result["scenes"][0]["scene_type"] = "intro"
        result["scenes"][-1]["scene_type"] = "closing"
        return result

    def normalize_scene(self, scene: dict[str, Any], index: int, extracted: dict[str, Any]) -> dict[str, Any]:
        scene_type = scene.get("scene_type") or ("intro" if index == 0 else "content")
        source_keys = scene.get("source_data_keys") or scene.get("data_keys") or []
        if not isinstance(source_keys, list):
            source_keys = []
        valid_keys = {metric.get("metric_key") for metric in extracted.get("metrics", []) if isinstance(metric, dict)}
        source_keys = [str(key) for key in source_keys if str(key) in valid_keys]
        tts = scene.get("tts") if isinstance(scene.get("tts"), dict) else {}
        duration = scene.get("duration_policy") if isinstance(scene.get("duration_policy"), dict) else {}
        return {
            "scene_id": str(scene.get("scene_id") or f"scene_{index + 1:02d}"),
            "scene_type": str(scene_type),
            "title": str(scene.get("title") or f"Scene {index + 1}"),
            "objective": str(scene.get("objective") or scene.get("title") or ""),
            "source_data_keys": source_keys,
            "visual_layers": scene.get("visual_layers", []) if isinstance(scene.get("visual_layers", []), list) else [],
            "motion": scene.get("motion", {}) if isinstance(scene.get("motion", {}), dict) else {},
            "tts": {"enabled": bool(tts.get("enabled", True)), "text": str(tts.get("text") or scene.get("tts_text") or scene.get("narration") or scene.get("title") or "")},
            "duration_policy": {
                "mode": duration.get("mode", "tts_first") if duration.get("mode") in {"tts_first", "fixed"} else "tts_first",
                "min_seconds": duration.get("min_seconds", 5) if isinstance(duration.get("min_seconds", 5), (int, float)) else 5,
                "max_seconds": duration.get("max_seconds", 20) if isinstance(duration.get("max_seconds", 20), (int, float)) else 20,
            },
        }

    def build_workflow_from_screen_plan(self, screen_plan: dict[str, Any], extracted: dict[str, Any]) -> dict[str, Any]:
        metrics_by_key = {metric.get("metric_key"): metric for metric in extracted.get("metrics", []) if isinstance(metric, dict)}
        screens = screen_plan.get("screens", []) if isinstance(screen_plan.get("screens"), list) else []
        scenes: list[dict[str, Any]] = []
        for index, screen in enumerate(screens):
            if not isinstance(screen, dict):
                continue
            screen_type = screen.get("screen_type") or ("intro" if index == 0 else "closing" if index == len(screens) - 1 else "content")
            data_keys = [str(key) for key in screen.get("data_keys", []) if str(key) in metrics_by_key]
            scenes.append(
                {
                    "scene_id": f"scene_{index + 1:02d}",
                    "scene_type": screen_type if screen_type in {"intro", "content", "closing"} else "content",
                    "title": str(screen.get("title") or f"Screen {index + 1}"),
                    "objective": str(screen.get("title") or ""),
                    "source_data_keys": data_keys,
                    "visual_layers": [{"type": screen.get("visual_type", "kpi"), "data_keys": data_keys}],
                    "motion": {},
                    "tts": {"enabled": screen_type != "closing", "text": str(screen.get("tts_text_draft") or screen.get("title") or "")},
                    "duration_policy": {"mode": "tts_first" if screen_type != "closing" else "fixed", "min_seconds": 5, "max_seconds": 20},
                }
            )
        return {"workflow_metadata": {"template_version": "wf.v2", "report_month": REPORT_MONTH, "job_id": JOB_ID}, "video_settings": {"fps": 30, "resolution": "1920x1080", "aspect_ratio": "16:9"}, "scenes": scenes}

    def step_video(self, step_id: str) -> list[str]:
        workflow = self.context.get("workflow") or json.loads(next((self.output_dir / "workflow").glob("workflow-*.json")).read_text(encoding="utf-8"))
        rel_path = S2_ARTIFACTS[step_id]
        path = self.output_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        result = self.llm.chat_with_retry_parse(
            S2_PROMPTS[step_id] + "\nBẮT BUỘC trả JSON object thuần, CỰC NGẮN theo envelope {status,step_id,data,warnings,error}; data chỉ gồm summary và tối đa 3 items. Không markdown. Không thêm số liệu ngoài workflow/upstream.",
            json.dumps(self.build_s2_input(step_id, workflow), ensure_ascii=False),
            max_parse_retries=2,
            max_tokens=S2_MAX_TOKENS,
            timeout=S2_LLM_TIMEOUT_SECONDS,
        )
        result = self.normalize_s2_result(step_id, result, workflow)
        self.validate_s2_result(step_id, result, workflow)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        artifacts = [rel_path]
        if step_id == "S2.8":
            tts_manifest = TTSGenerator(str(self.output_dir), mock_mode=True).generate_all(workflow.get("scenes", []))
            component_spec = self.load_optional_json("remotion/component-spec.json")
            render_plan = self.load_optional_json("remotion/render-plan.json")
            manifest = RemotionManifest(str(self.output_dir)).build_manifest(workflow, component_spec, render_plan, tts_manifest)
            ready, errors = RenderGate(str(self.output_dir)).check_final_ready(manifest, tts_manifest)
            if not ready:
                raise ValueError(f"Render gate failed: {errors}")
            RemotionManifest(str(self.output_dir)).save_manifest(manifest, "remotion-manifest.json")
            video_rel = FinalPackager(str(self.output_dir)).create_mock_video()
            FinalPackager(str(self.output_dir)).create_publish_manifest(JOB_ID, REPORT_MONTH, video_rel, manifest)
            artifacts.extend(["remotion/remotion-manifest.json", "final/video.mp4", "final/publish-manifest.json"])
        for artifact in artifacts:
            artifact_path = self.output_dir / artifact
            if not artifact_path.exists() or artifact_path.stat().st_size <= 0:
                raise ValueError(f"missing or empty artifact: {artifact}")
        return artifacts

    def mock_video_result(self, step_id: str, workflow: dict[str, Any]) -> dict[str, Any]:
        scenes = workflow.get("scenes", [])
        return {
            "step_id": step_id,
            "mode": "mock",
            "scene_count": len(scenes),
            "scenes": [{"scene_id": scene.get("scene_id"), "scene_type": scene.get("scene_type"), "title": scene.get("title")} for scene in scenes],
            "generated_at": now_iso(),
        }

    def compact_extracted_report(self, extracted: dict[str, Any], metric_limit: int = 24) -> dict[str, Any]:
        return {
            "report_metadata": extracted.get("report_metadata", {}),
            "metrics": [
                {
                    "metric_key": metric.get("metric_key"),
                    "metric_name": metric.get("metric_name"),
                    "value": metric.get("value"),
                    "unit": metric.get("unit"),
                }
                for metric in extracted.get("metrics", [])[:metric_limit]
                if isinstance(metric, dict)
            ],
            "sections": extracted.get("sections", [])[:6],
            "warnings": extracted.get("warnings", [])[:3],
        }

    def compact_workflow(self, workflow: dict[str, Any]) -> dict[str, Any]:
        return {
            "workflow_metadata": workflow.get("workflow_metadata", {}),
            "video_settings": workflow.get("video_settings", {}),
            "scenes": [
                {
                    "scene_id": scene.get("scene_id"),
                    "scene_type": scene.get("scene_type"),
                    "title": scene.get("title"),
                    "source_data_keys": scene.get("source_data_keys", []),
                    "tts": scene.get("tts", {}),
                    "duration_policy": scene.get("duration_policy", {}),
                }
                for scene in workflow.get("scenes", [])
                if isinstance(scene, dict)
            ],
        }

    def compact_upstream_artifact(self, data: Any) -> Any:
        if isinstance(data, dict):
            compact = {key: data[key] for key in ["status", "step_id", "warnings", "validation"] if key in data}
            source = data.get("data") if isinstance(data.get("data"), dict) else data
            if isinstance(source, dict):
                for key in ["scenes", "visuals", "tts", "components", "assets", "timeline", "fixes"]:
                    if key in source:
                        compact[key] = source[key]
            return compact or data
        return data

    def build_s2_input(self, step_id: str, workflow: dict[str, Any]) -> dict[str, Any]:
        upstream_payload: dict[str, Any] = {}
        for rel_path in S2_REQUIRED_UPSTREAM.get(step_id, []):
            artifact_path = self.output_dir / rel_path
            if artifact_path.exists() and artifact_path.suffix.lower() == ".json":
                upstream_payload[rel_path] = self.compact_upstream_artifact(json.loads(artifact_path.read_text(encoding="utf-8")))
        return {
            "job_context": {
                "job_id": JOB_ID,
                "report_month": REPORT_MONTH,
                "step_id": step_id,
                "attempt": self.step_record(step_id)["attempt"],
            },
            "upstream": {
                "required_artifacts": S2_REQUIRED_UPSTREAM.get(step_id, []),
                "payload": upstream_payload,
            },
            "workflow": self.compact_workflow(workflow),
            "runtime_policy": {"timeout_seconds": S2_LLM_TIMEOUT_SECONDS, "strict_json": True, "max_output_items": 3},
        }

    def normalize_s2_result(self, step_id: str, result: dict[str, Any], workflow: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(result, dict):
            result = {}
        if "status" not in result:
            result = {"status": "DONE", "step_id": step_id, "data": result, "warnings": [], "error": None}
        result["step_id"] = step_id
        result.setdefault("status", "DONE")
        result.setdefault("artifacts", [S2_ARTIFACTS[step_id]])
        result.setdefault("warnings", [])
        result.setdefault("error", None)
        if not isinstance(result.get("data"), dict):
            result["data"] = {"raw": result.get("data"), "scene_count": len(workflow.get("scenes", []))}
        return result

    def validate_s2_result(self, step_id: str, result: dict[str, Any], workflow: dict[str, Any]) -> None:
        if not isinstance(result, dict):
            raise ValueError(f"{step_id} output must be a JSON object")
        status = str(result.get("status", "")).upper()
        if status in {"OK", "WARN", "WARNING", "SUCCESS"}:
            result["status"] = "DONE"
            status = "DONE"
        if status not in {"DONE", "PARTIAL"}:
            raise ValueError(f"{step_id} returned non-success status: {result.get('status')}")
        if result.get("step_id") != step_id:
            raise ValueError(f"{step_id} output step_id mismatch: {result.get('step_id')}")
        scenes = workflow.get("scenes", [])
        if not isinstance(scenes, list) or len(scenes) < 2:
            raise ValueError("workflow scenes must contain intro and closing")
        if scenes[0].get("scene_type") != "intro" or scenes[-1].get("scene_type") != "closing":
            raise ValueError("workflow intro/closing ordering invalid before S2 step")

    def normalize_screen_data_keys(self, screens: list[dict[str, Any]], extracted: dict[str, Any]) -> list[dict[str, Any]]:
        valid_keys = {str(metric.get("metric_key")) for metric in extracted.get("metrics", []) if isinstance(metric, dict)}
        for screen in screens:
            if not isinstance(screen, dict):
                continue
            data_keys = screen.get("data_keys", [])
            if not isinstance(data_keys, list):
                screen["data_keys"] = []
                continue
            if screen.get("screen_type") in {"intro", "closing"}:
                screen["data_keys"] = [str(key) for key in data_keys if str(key) in valid_keys]
            else:
                screen["data_keys"] = [str(key) for key in data_keys if str(key) in valid_keys]
        return screens

    def validate_screen_plan(self, screen_plan: dict[str, Any], extracted: dict[str, Any]) -> None:
        screens = screen_plan.get("screens", [])
        if not isinstance(screens, list):
            raise ValueError("screen-plan screens must be a list")
        if not (6 <= len(screens) <= 10):
            raise ValueError(f"screen-plan must have 6-10 screens, got {len(screens)}")
        if screens[0].get("screen_type") != "intro":
            raise ValueError("first screen must be intro")
        if screens[-1].get("screen_type") != "closing":
            raise ValueError("last screen must be closing")
        valid_keys = {str(metric.get("metric_key")) for metric in extracted.get("metrics", []) if isinstance(metric, dict)}
        for index, screen in enumerate(screens):
            data_keys = screen.get("data_keys", [])
            if data_keys and not isinstance(data_keys, list):
                raise ValueError(f"screen {index} data_keys must be a list")
            invalid = [str(key) for key in data_keys if str(key) not in valid_keys]
            if invalid:
                raise ValueError(f"screen {index} has invalid data_keys: {invalid}")

    def load_optional_json(self, rel_path: str) -> dict[str, Any]:
        path = self.output_dir / rel_path
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            return data["data"]
        return data if isinstance(data, dict) else {}

    def assert_final_acceptance(self) -> None:
        durations = {step["step_id"]: float(step["duration_seconds"] or 0) for step in self.state["steps"]}
        p1_total = durations.get("P1.1", 0) + durations.get("P1.1b", 0) + durations.get("P1.2", 0)
        s2_total = sum(durations.get(step_id, 0) for step_id in S2_ARTIFACTS)
        pipeline_total = float(self.context.get("wall_clock_total_seconds") or sum(durations.values()))
        slow_steps = {step_id: seconds for step_id, seconds in durations.items() if seconds > step_timeout(step_id)}
        s2_slow = {step_id: durations.get(step_id, 0) for step_id in S2_ARTIFACTS if durations.get(step_id, 0) > step_timeout(step_id)}
        if p1_total > P1_TOTAL_MAX_SECONDS:
            raise ValueError(f"P1.1+P1.1b+P1.2 total must be <= {P1_TOTAL_MAX_SECONDS}s, got {p1_total:.2f}s")
        if s2_total > S2_TOTAL_MAX_SECONDS:
            raise ValueError(f"S2 total must be <= {S2_TOTAL_MAX_SECONDS}s, got {s2_total:.2f}s")
        if slow_steps:
            raise ValueError(f"steps exceeded per-step timeout: {slow_steps}")
        if pipeline_total > PIPELINE_MAX_SECONDS:
            raise ValueError(f"pipeline total must be <= {PIPELINE_MAX_SECONDS}s, got {pipeline_total:.2f}s")
        if s2_slow:
            raise ValueError(f"S2 steps exceeded per-step timeout: {s2_slow}")
        for step in self.state["steps"]:
            if step["status"] != "DONE":
                raise ValueError(f"hard-fail or incomplete step detected: {step['step_id']}={step['status']}")
            for artifact in step.get("artifacts", []):
                artifact_path = self.output_dir / artifact
                if not artifact_path.exists() or artifact_path.stat().st_size <= 0:
                    raise ValueError(f"missing or empty artifact: {artifact}")

    def to_plain_data(self, item: Any) -> Any:
        if hasattr(item, "model_dump"):
            return item.model_dump()
        if is_dataclass(item):
            return asdict(item)
        return item

    def write_summary(self) -> None:
        extracted = self.context.get("extracted_report") or json.loads((self.output_dir / "parsed" / "extracted-report.json").read_text(encoding="utf-8"))
        screen_plan = self.context.get("screen_plan") or json.loads((self.output_dir / "parsed" / "screen-plan.json").read_text(encoding="utf-8"))
        workflow = self.context.get("workflow") or json.loads(next((self.output_dir / "workflow").glob("workflow-*.json")).read_text(encoding="utf-8"))
        durations = {step["step_id"]: float(step["duration_seconds"] or 0) for step in self.state["steps"]}
        p1_total = durations.get("P1.1", 0) + durations.get("P1.1b", 0) + durations.get("P1.2", 0)
        s2_total = sum(durations.get(step_id, 0) for step_id in S2_ARTIFACTS)
        pipeline_total = sum(durations.values())
        workflow_validation = json.loads((self.output_dir / "workflow" / "workflow-validation.json").read_text(encoding="utf-8"))
        acceptance = {
            "metrics_count_gte_min": len(extracted.get("metrics", [])) >= METRICS_MIN_COUNT,
            "screen_count_6_to_10": 6 <= len(screen_plan.get("screens", [])) <= 10,
            "workflow_validation_pass": bool(workflow_validation.get("passed")),
            "metrics_count_gte_30": len(extracted.get("metrics", [])) >= 30,
            "final_video_exists": (self.output_dir / "final" / "video.mp4").exists() and (self.output_dir / "final" / "video.mp4").stat().st_size > 0,
            "each_step_lte_configured_timeout": all(float(step["duration_seconds"] or 0) <= step_timeout(step["step_id"]) for step in self.state["steps"]),
            "pipeline_total_lte_10_minutes": pipeline_total <= PIPELINE_MAX_SECONDS,
            "p1_total_lte_5_minutes": p1_total <= P1_TOTAL_MAX_SECONDS,
            "p1_1b_lte_2_minutes": durations.get("P1.1b", 0) <= step_timeout("P1.1b"),
            "p1_2_lte_configured_timeout": durations.get("P1.2", 0) <= step_timeout("P1.2"),
            "s2_each_lte_configured_timeout": all(durations.get(step_id, 0) <= step_timeout(step_id) for step_id in S2_ARTIFACTS),
            "s2_total_lte_budget": s2_total <= S2_TOTAL_MAX_SECONDS,
            "no_hard_fail": all(step["status"] == "DONE" for step in self.state["steps"]),
        }
        summary = {
            "job_id": JOB_ID,
            "output_dir": self.output_dir.as_posix(),
            "pdf_path": PDF_PATH.as_posix(),
            "url": URL,
            "model": MODEL,
            "s2_mode": S2_MODE,
            "metrics_count": len(extracted.get("metrics", [])),
            "screen_count": len(screen_plan.get("screens", [])),
            "scene_count": len(workflow.get("scenes", [])),
            "p1_1_chunk_timings": self.context.get("p1_1_chunk_timings", []),
            "timing": {"p1_total_seconds": p1_total, "s2_total_seconds": s2_total, "pipeline_total_seconds": pipeline_total},
            "acceptance": acceptance,
            "steps": [
                {
                    "step_id": step["step_id"],
                    "status": step["status"],
                    "duration_seconds": step["duration_seconds"],
                    "artifacts": step["artifacts"],
                    "error_code": step["error_code"],
                    "error_message": step["error_message"],
                }
                for step in self.state["steps"]
            ],
        }
        (self.output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    runner = RealAppFlow()
    try:
        return runner.run()
    except Exception as exc:  # noqa: BLE001 - CLI smoke test prints masked failure evidence
        print(mask_secret(f"ERROR: {type(exc).__name__}: {exc}"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
