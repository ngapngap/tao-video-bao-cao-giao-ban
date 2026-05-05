"""Unit tests cho AI Pass 2 video orchestrator."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from app.core.checkpoint import CheckpointManager
from app.core.models import JobState, JobStatus, StepRecord, StepStatus
from app.core.retry_policy import RetryPolicy
from app.video import STEP_ARTIFACTS, STEP_ORDER, VideoOrchestrator


class MockLLMClient:
    """Mock LLM client không gọi API thật."""

    def __init__(self, fail_once_step: str | None = None):
        self.calls: list[dict[str, str]] = []
        self.fail_once_step = fail_once_step
        self._failed_steps: set[str] = set()

    def chat(self, system_prompt: str, user_content: str, temperature: float = 0.1) -> dict:
        step_id = self._extract_step_id(user_content)
        self.calls.append({"step_id": step_id, "system_prompt": system_prompt})
        if self.fail_once_step == step_id and step_id not in self._failed_steps:
            self._failed_steps.add(step_id)
            raise RuntimeError("temporary llm error")
        return {"status": "ok", "step_id": step_id, "payload": {"temperature": temperature}}

    def _extract_step_id(self, user_content: str) -> str:
        payload = json.loads(user_content)
        return payload["job_context"]["step_id"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_job_state(job_id: str = "job-video") -> JobState:
    now = _now()
    return JobState(
        job_id=job_id,
        report_month="202605",
        created_at=now,
        updated_at=now,
    )


def _workflow_data() -> dict:
    return {
        "workflow_metadata": {"job_id": "job-video", "report_month": "202605"},
        "scenes": [
            {"scene_id": "scene_intro", "scene_type": "intro", "source_data_keys": []},
            {"scene_id": "scene_content_01", "scene_type": "content", "source_data_keys": ["metric_01"]},
            {"scene_id": "scene_closing", "scene_type": "closing", "source_data_keys": []},
        ],
    }


def _make_orchestrator(tmp_path, llm_client=None, on_step_update=None) -> VideoOrchestrator:
    return VideoOrchestrator(
        llm_client=llm_client or MockLLMClient(),
        output_dir=str(tmp_path),
        checkpoint=CheckpointManager(str(tmp_path)),
        retry_policy=RetryPolicy(max_retry=3, backoff_seconds=0, step_timeout=5),
        on_step_update=on_step_update,
    )


def test_run_pipeline_eight_steps_all_done_and_artifacts_exist(tmp_path):
    llm = MockLLMClient()
    orchestrator = _make_orchestrator(tmp_path, llm_client=llm)

    result = orchestrator.run_pipeline(_make_job_state(), _workflow_data())

    assert result.status == JobStatus.DONE
    assert result.current_step_id is None
    assert [step.step_id for step in result.steps] == STEP_ORDER
    assert [step.status for step in result.steps] == [StepStatus.DONE] * 8
    assert [call["step_id"] for call in llm.calls] == STEP_ORDER

    for step in result.steps:
        assert step.artifacts == [STEP_ARTIFACTS[step.step_id]]
        assert os.path.exists(tmp_path / STEP_ARTIFACTS[step.step_id])

    saved = CheckpointManager(str(tmp_path)).load_state()
    assert saved is not None
    assert saved.status == JobStatus.DONE


def test_resume_skips_done_steps_and_runs_from_step_four(tmp_path):
    existing_steps = []
    for step_id in STEP_ORDER[:3]:
        artifact = STEP_ARTIFACTS[step_id]
        artifact_path = tmp_path / artifact
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text('{"status":"ok"}', encoding="utf-8")
        existing_steps.append(
            StepRecord(
                step_id=step_id,
                name=step_id,
                status=StepStatus.DONE,
                attempt=1,
                artifacts=[artifact],
            )
        )

    job_state = _make_job_state("job-resume-video")
    job_state.steps = existing_steps
    llm = MockLLMClient()
    orchestrator = _make_orchestrator(tmp_path, llm_client=llm)

    result = orchestrator.run_pipeline(job_state, _workflow_data())

    assert result.status == JobStatus.DONE
    assert [call["step_id"] for call in llm.calls] == STEP_ORDER[3:]
    assert [step.status for step in result.steps] == [StepStatus.DONE] * 8
    for step_id in STEP_ORDER:
        assert os.path.exists(tmp_path / STEP_ARTIFACTS[step_id])


def test_retry_step_two_fails_once_then_succeeds(tmp_path):
    llm = MockLLMClient(fail_once_step="S2.2_visual_spec")
    orchestrator = _make_orchestrator(tmp_path, llm_client=llm)

    result = orchestrator.run_pipeline(_make_job_state("job-retry-video"), _workflow_data())

    assert result.status == JobStatus.DONE
    step_two = next(step for step in result.steps if step.step_id == "S2.2_visual_spec")
    assert step_two.status == StepStatus.DONE
    assert step_two.attempt == 2
    assert [call["step_id"] for call in llm.calls].count("S2.2_visual_spec") == 2
    assert os.path.exists(tmp_path / STEP_ARTIFACTS["S2.2_visual_spec"])


def test_cancel_between_steps_stops_pipeline(tmp_path):
    llm = MockLLMClient()
    orchestrator_holder: dict[str, VideoOrchestrator] = {}

    def on_step_update(job_state, step_id, status, detail):
        if step_id == "S2.2_visual_spec" and status == "done":
            orchestrator_holder["orchestrator"].cancel()

    orchestrator = _make_orchestrator(tmp_path, llm_client=llm, on_step_update=on_step_update)
    orchestrator_holder["orchestrator"] = orchestrator

    result = orchestrator.run_pipeline(_make_job_state("job-cancel-video"), _workflow_data())

    assert result.status == JobStatus.CANCELED
    assert [call["step_id"] for call in llm.calls] == STEP_ORDER[:2]
    assert result.steps[0].status == StepStatus.DONE
    assert result.steps[1].status == StepStatus.DONE
    assert len(result.steps) == 2
    assert os.path.exists(tmp_path / STEP_ARTIFACTS["S2.1_scene_planning"])
    assert os.path.exists(tmp_path / STEP_ARTIFACTS["S2.2_visual_spec"])
    assert not os.path.exists(tmp_path / STEP_ARTIFACTS["S2.3_narration_tts"])
