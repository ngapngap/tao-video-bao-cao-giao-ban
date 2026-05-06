"""Run real P1.1 chunk-by-chunk pipeline against a real PDF and LLM API.

Windows cmd.exe example:
  set LLM_EXTRACT_URL=http://10.48.240.50:20128/v1
  set LLM_EXTRACT_KEY=sk-...
  set LLM_EXTRACT_MODEL=minimax/MiniMax-M2.7
  python scripts/test_real_pipeline.py

This script intentionally does not hard-code API keys. Runtime output is written
under outputs/ which is ignored by git.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, ".")

from app.ai.llm_client import LLMClient
from app.ai.prompts import P1_1_CHUNK_EXTRACTION
from app.core.chunk_processor import ChunkProcessor
from app.pdf.normalizer import DataNormalizer
from app.pdf.parser import PDFParser
from app.workflow.validator import WorkflowValidator

PDF_PATH = os.environ.get(
    "REAL_PIPELINE_PDF",
    "outputs/202603/20260506-033202/input/2026 - Báo cáo tháng 3 fn.pdf",
)
URL = os.environ.get("LLM_EXTRACT_URL", "http://10.48.240.50:20128/v1")
KEY = os.environ.get("LLM_EXTRACT_KEY", "").strip()
MODEL = os.environ.get("LLM_EXTRACT_MODEL", "minimax/MiniMax-M2.7")
OUTPUT_DIR = Path(os.environ.get("REAL_PIPELINE_OUTPUT_DIR", "outputs/test-pipeline-run"))
REPORT_MONTH = os.environ.get("REAL_PIPELINE_REPORT_MONTH", "202603")
MAX_CHARS = int(os.environ.get("REAL_PIPELINE_CHUNK_CHARS", "6000"))
MAX_WORKERS = int(os.environ.get("REAL_PIPELINE_MAX_WORKERS", "4"))
MAX_TOKENS = int(os.environ.get("REAL_PIPELINE_MAX_TOKENS", "8000"))


def chunk_text(text: str, max_chars: int = 6000) -> list[str]:
    sections = re.split(r"\n(?=[IVX]+\.\s)", text)
    chunks: list[str] = []
    current = ""
    for section in sections:
        if len(section) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(
                section[i : i + max_chars].strip()
                for i in range(0, len(section), max_chars)
                if section[i : i + max_chars].strip()
            )
            continue
        if len(current) + len(section) + 1 > max_chars:
            if current:
                chunks.append(current.strip())
            current = section
        else:
            current = f"{current}\n{section}" if current else section
    if current:
        chunks.append(current.strip())
    return chunks if chunks else [text[:max_chars]]


def normalize_metric_item(item: dict[str, Any], fallback_key: str | None = None) -> dict[str, Any] | None:
    key = item.get("metric_key") or item.get("key") or fallback_key
    name = item.get("metric_name") or item.get("name") or (str(key).replace("_", " ").title() if key else "")
    if not key or "value" not in item:
        return None
    metric = {
        "metric_key": str(key),
        "metric_name": str(name),
        "value": str(item.get("value", "")),
        "unit": str(item.get("unit", "")),
    }
    citations = item.get("citations")
    if isinstance(citations, list):
        metric["citations"] = citations
    else:
        citation: dict[str, Any] = {}
        if item.get("page_no") is not None:
            citation["page_no"] = item.get("page_no")
        if item.get("source_snippet"):
            citation["source_snippet"] = item.get("source_snippet")
        if item.get("confidence") is not None:
            citation["confidence"] = item.get("confidence")
        if citation:
            metric["citations"] = [citation]
    comparison = item.get("comparison")
    if isinstance(comparison, dict):
        metric["comparison"] = comparison
    return metric


def collect_metrics_from_any(data: Any, prefix: str = "") -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    if isinstance(data, list):
        for index, item in enumerate(data):
            if isinstance(item, dict):
                metric = normalize_metric_item(item, f"{prefix}.item_{index}".strip("."))
                if metric:
                    metrics.append(metric)
                else:
                    metrics.extend(collect_metrics_from_any(item, f"{prefix}.item_{index}".strip(".")))
        return metrics
    if not isinstance(data, dict):
        return metrics
    metric = normalize_metric_item(data, prefix or None)
    if metric:
        metrics.append(metric)
        return metrics
    for key, value in data.items():
        if key in {"report_metadata", "sections", "warnings", "citations"}:
            continue
        next_prefix = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            nested_metric = normalize_metric_item(value, next_prefix)
            if nested_metric:
                metrics.append(nested_metric)
            else:
                metrics.extend(collect_metrics_from_any(value, next_prefix))
        elif isinstance(value, list):
            metrics.extend(collect_metrics_from_any(value, next_prefix))
    return metrics


def dedupe_metrics(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for metric in metrics:
        key = str(metric.get("metric_key", "")).strip()
        value = str(metric.get("value", "")).strip()
        unit = str(metric.get("unit", "")).strip()
        identity = (key, value, unit)
        if not key or identity in seen:
            continue
        seen.add(identity)
        deduped.append(metric)
    return deduped


def normalize_report(raw_data: dict[str, Any]) -> dict[str, Any]:
    rm = raw_data.get("report_metadata", {}) if isinstance(raw_data.get("report_metadata"), dict) else {}
    normalized = {
        "report_metadata": {
            "title": str(rm.get("report_title") or rm.get("title") or raw_data.get("report_title") or "Báo cáo giao ban"),
            "period": str(rm.get("period") or rm.get("report_month") or raw_data.get("report_month") or REPORT_MONTH),
            "organization": str(rm.get("owner_org") or rm.get("organization") or raw_data.get("owner_org") or ""),
        },
        "metrics": dedupe_metrics(collect_metrics_from_any(raw_data.get("metrics", [])) + collect_metrics_from_any(raw_data)),
        "sections": raw_data.get("sections", []) if isinstance(raw_data.get("sections"), list) else [],
        "warnings": raw_data.get("warnings", []) if isinstance(raw_data.get("warnings"), list) else [],
    }
    return normalized


def main() -> int:
    if not KEY:
        print("ERROR: Missing LLM_EXTRACT_KEY environment variable.")
        return 2

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timings: dict[str, Any] = {}
    chunk_timings: list[dict[str, Any]] = []

    print("=" * 60)
    print("STEP 1: Parse PDF")
    print("=" * 60)
    start = time.time()
    parse_result = PDFParser(PDF_PATH).parse()
    raw_text = DataNormalizer.normalize_text(parse_result.raw_text)
    timings["parse_seconds"] = round(time.time() - start, 2)
    print(f"  Pages: {parse_result.total_pages}")
    print(f"  Text chunks: {len(parse_result.text_chunks)}")
    print(f"  Table chunks: {len(parse_result.table_chunks)}")
    print(f"  Raw text length: {len(raw_text)} chars")
    print(f"  Time: {timings['parse_seconds']:.1f}s")

    print("\n" + "=" * 60)
    print("STEP 2: Chia chunks")
    print("=" * 60)
    chunks = chunk_text(raw_text, MAX_CHARS)
    print(f"  Chunks: {len(chunks)}")
    for i, chunk in enumerate(chunks):
        print(f"  Chunk {i + 1}: {len(chunk)} chars")

    print("\n" + "=" * 60)
    print("STEP 3: Gọi LLM cho từng chunk (song song)")
    print("=" * 60)
    llm = LLMClient(URL, KEY, MODEL)
    processor = ChunkProcessor(str(OUTPUT_DIR), "extract_chunks")

    def process_chunk(idx: int, chunk: str) -> dict[str, Any]:
        print(f"  Chunk {idx + 1}/{len(chunks)}: gửi {len(chunk)} chars...")
        chunk_start = time.time()
        payload = json.dumps(
            {
                "report_month": REPORT_MONTH,
                "chunk_index": idx,
                "total_chunks": len(chunks),
                "chunk_text": chunk,
            },
            ensure_ascii=False,
        )
        result = llm.chat_with_retry_parse(P1_1_CHUNK_EXTRACTION, payload, max_tokens=MAX_TOKENS)
        elapsed = round(time.time() - chunk_start, 2)
        chunk_timings.append(
            {
                "chunk_index": idx,
                "chars": len(chunk),
                "seconds": elapsed,
                "response_chars": len(json.dumps(result, ensure_ascii=False)),
                "metrics": len(result.get("metrics", [])) if isinstance(result.get("metrics"), list) else None,
            }
        )
        print(f"  Chunk {idx + 1}/{len(chunks)}: nhận {len(str(result))} chars ({elapsed:.1f}s)")
        return result

    start = time.time()
    try:
        chunk_results = processor.process_chunks(
            chunks,
            process_chunk,
            max_retry=2,
            parallel=True,
            max_workers=min(len(chunks), MAX_WORKERS),
            on_progress=lambda i, n, s: print(f"  Chunk {i + 1}/{n}: {s}"),
        )
        timings["llm_seconds"] = round(time.time() - start, 2)
        print(f"\n  Total chunks completed: {len(chunk_results)}")
        print(f"  Total time: {timings['llm_seconds']:.1f}s")
    except Exception as exc:  # noqa: BLE001 - smoke script should preserve partial evidence
        timings["llm_seconds"] = round(time.time() - start, 2)
        print(f"\n  ERROR: {exc}")
        print(f"  Time: {timings['llm_seconds']:.1f}s")
        chunk_results = []
        for i in range(len(chunks)):
            cached = processor.load_chunk_result(i)
            if cached:
                chunk_results.append(cached)
        print(f"  Cached results: {len(chunk_results)}")

    print("\n" + "=" * 60)
    print("STEP 4: Merge chunks")
    print("=" * 60)
    merged: dict[str, Any] = {"report_metadata": {}, "metrics": [], "sections": [], "warnings": []}
    for report in chunk_results:
        if not isinstance(report, dict):
            continue
        if isinstance(report.get("report_metadata"), dict):
            merged["report_metadata"].update({k: v for k, v in report["report_metadata"].items() if v})
        merged["metrics"].extend(collect_metrics_from_any(report.get("metrics", [])))
        if isinstance(report.get("sections"), list):
            merged["sections"].extend(report["sections"])
        if isinstance(report.get("warnings"), list):
            merged["warnings"].extend(report["warnings"])
        merged["metrics"].extend(
            collect_metrics_from_any(
                {
                    key: value
                    for key, value in report.items()
                    if key not in {"metrics", "sections", "warnings", "report_metadata"}
                }
            )
        )
    merged["metrics"] = dedupe_metrics(merged["metrics"])
    print(f"  Merged metrics: {len(merged['metrics'])}")
    print(f"  Merged sections: {len(merged['sections'])}")

    print("\n" + "=" * 60)
    print("STEP 5: Normalize")
    print("=" * 60)
    normalized = normalize_report(merged)
    print(f"  report_metadata: {normalized['report_metadata']}")
    print(f"  metrics count: {len(normalized['metrics'])}")
    if normalized["metrics"]:
        print("  Sample metrics:")
        for metric in normalized["metrics"][:10]:
            print(f"    - {metric.get('metric_key', '?')}: {metric.get('value', '?')} {metric.get('unit', '')}")

    print("\n" + "=" * 60)
    print("STEP 6: Validate")
    print("=" * 60)
    validation = WorkflowValidator().validate_extracted_report(normalized)
    print(f"  Passed: {validation.passed}")
    print(f"  Errors: {len(validation.errors)}")
    for err in validation.errors:
        print(f"    - {err}")

    print("\n" + "=" * 60)
    print("STEP 7: Save results")
    print("=" * 60)
    summary = {
        "pdf_path": PDF_PATH,
        "url": URL,
        "model": MODEL,
        "chunk_count": len(chunks),
        "chunk_chars": [len(chunk) for chunk in chunks],
        "timings": timings,
        "chunk_timings": sorted(chunk_timings, key=lambda item: item["chunk_index"]),
        "slowest_chunk": max(chunk_timings, key=lambda item: item["seconds"], default=None),
        "metrics_count": len(normalized["metrics"]),
        "sections_count": len(normalized["sections"]),
        "validation_passed": validation.passed,
        "validation_errors": validation.errors,
    }

    extracted_path = OUTPUT_DIR / "extracted-report.json"
    validation_path = OUTPUT_DIR / "validation.json"
    summary_path = OUTPUT_DIR / "summary.json"
    extracted_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    validation_path.write_text(json.dumps(validation.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Saved: {extracted_path.as_posix()}")
    print(f"  Saved: {validation_path.as_posix()}")
    print(f"  Saved: {summary_path.as_posix()}")

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)
    return 0 if validation.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
