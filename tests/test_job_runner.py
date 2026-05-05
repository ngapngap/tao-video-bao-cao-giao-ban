"""Unit tests cho job engine core."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core import (
    CheckpointManager,
    JobRunner,
    JobState,
    JobStatus,
    RetryPolicy,
    StepRecord,
    StepResult,
    StepStatus,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_job_state(job_id: str = "job-test") -> JobState:
    now = _now()
    return JobState(
        job_id=job_id,
        report_month="202605",
        created_at=now,
        updated_at=now,
        steps=[
            StepRecord(step_id="S1", name="Step 1"),
            StepRecord(step_id="S2", name="Step 2"),
            StepRecord(step_id="S3", name="Step 3"),
            StepRecord(step_id="S4", name="Step 4"),
            StepRecord(step_id="S5", name="Step 5"),
        ],
    )


def _register_success_handlers(runner: JobRunner, calls: list[str]):
    for step_id in ["S1", "S2", "S3", "S4", "S5"]:
        runner.register_step(step_id, lambda job_state, output_dir, sid=step_id: calls.append(sid) or StepResult())


def test_job_runs_sequentially_through_five_steps(tmp_path):
    calls: list[str] = []
    runner = JobRunner(
        _make_job_state(),
        str(tmp_path),
        retry_policy=RetryPolicy(max_retry=3, backoff_seconds=0, step_timeout=5),
    )
    _register_success_handlers(runner, calls)

    result = runner.run()

    assert calls == ["S1", "S2", "S3", "S4", "S5"]
    assert result.status == JobStatus.DONE
    assert result.current_step_id is None
    assert [step.status for step in result.steps] == [StepStatus.DONE] * 5

    saved = CheckpointManager(str(tmp_path)).load_state()
    assert saved is not None
    assert saved.status == JobStatus.DONE


def test_checkpoint_save_load_and_resume_from_failed_step(tmp_path):
    first_calls: list[str] = []
    first_runner = JobRunner(
        _make_job_state("job-resume"),
        str(tmp_path),
        retry_policy=RetryPolicy(max_retry=1, backoff_seconds=0, step_timeout=5),
    )
    first_runner.register_step("S1", lambda job_state, output_dir: first_calls.append("S1") or StepResult())
    first_runner.register_step("S2", lambda job_state, output_dir: first_calls.append("S2") or StepResult())
    first_runner.register_step(
        "S3",
        lambda job_state, output_dir: first_calls.append("S3")
        or StepResult(success=False, error_code="VALIDATION_ERROR", error_message="hard fail"),
    )
    first_runner.register_step("S4", lambda job_state, output_dir: first_calls.append("S4") or StepResult())
    first_runner.register_step("S5", lambda job_state, output_dir: first_calls.append("S5") or StepResult())

    failed_state = first_runner.run()

    assert failed_state.status == JobStatus.FAILED
    assert first_calls == ["S1", "S2", "S3"]
    assert failed_state.steps[2].status == StepStatus.FAILED

    loaded = CheckpointManager(str(tmp_path)).load_state()
    assert loaded is not None
    assert loaded.steps[0].status == StepStatus.DONE
    assert loaded.steps[1].status == StepStatus.DONE
    assert loaded.steps[2].status == StepStatus.FAILED

    resume_calls: list[str] = []
    resume_runner = JobRunner(
        _make_job_state("job-resume"),
        str(tmp_path),
        retry_policy=RetryPolicy(max_retry=3, backoff_seconds=0, step_timeout=5),
    )
    resume_runner.register_step("S1", lambda job_state, output_dir: resume_calls.append("S1") or StepResult())
    resume_runner.register_step("S2", lambda job_state, output_dir: resume_calls.append("S2") or StepResult())
    resume_runner.register_step("S3", lambda job_state, output_dir: resume_calls.append("S3") or StepResult())
    resume_runner.register_step("S4", lambda job_state, output_dir: resume_calls.append("S4") or StepResult())
    resume_runner.register_step("S5", lambda job_state, output_dir: resume_calls.append("S5") or StepResult())

    resumed_state = resume_runner.resume()

    assert resume_calls == ["S3", "S4", "S5"]
    assert resumed_state.status == JobStatus.DONE
    assert [step.status for step in resumed_state.steps] == [StepStatus.DONE] * 5


def test_retry_s3_fails_once_then_succeeds(tmp_path):
    calls: list[str] = []
    s3_attempts = {"count": 0}

    def s3_handler(job_state, output_dir):
        calls.append("S3")
        s3_attempts["count"] += 1
        if s3_attempts["count"] == 1:
            return StepResult(success=False, error_code="NETWORK_ERROR", error_message="temporary network error")
        return StepResult(artifacts=["artifact-s3.json"])

    runner = JobRunner(
        _make_job_state("job-retry"),
        str(tmp_path),
        retry_policy=RetryPolicy(max_retry=3, backoff_seconds=0, step_timeout=5),
    )
    runner.register_step("S1", lambda job_state, output_dir: calls.append("S1") or StepResult())
    runner.register_step("S2", lambda job_state, output_dir: calls.append("S2") or StepResult())
    runner.register_step("S3", s3_handler)
    runner.register_step("S4", lambda job_state, output_dir: calls.append("S4") or StepResult())
    runner.register_step("S5", lambda job_state, output_dir: calls.append("S5") or StepResult())

    result = runner.run()

    assert calls == ["S1", "S2", "S3", "S3", "S4", "S5"]
    assert result.status == JobStatus.DONE
    assert result.steps[2].attempt == 2
    assert result.steps[2].status == StepStatus.DONE
    assert result.steps[2].artifacts == ["artifact-s3.json"]

    events = CheckpointManager(str(tmp_path)).read_events(level_filter="WARN")
    assert any("retry" in event.message.lower() for event in events)


def test_cancel_between_steps_marks_job_canceled(tmp_path):
    calls: list[str] = []
    runner = JobRunner(
        _make_job_state("job-cancel"),
        str(tmp_path),
        retry_policy=RetryPolicy(max_retry=3, backoff_seconds=0, step_timeout=5),
    )

    def s2_handler(job_state, output_dir):
        calls.append("S2")
        runner.cancel()
        return StepResult()

    runner.register_step("S1", lambda job_state, output_dir: calls.append("S1") or StepResult())
    runner.register_step("S2", s2_handler)
    runner.register_step("S3", lambda job_state, output_dir: calls.append("S3") or StepResult())
    runner.register_step("S4", lambda job_state, output_dir: calls.append("S4") or StepResult())
    runner.register_step("S5", lambda job_state, output_dir: calls.append("S5") or StepResult())

    result = runner.run()

    assert calls == ["S1", "S2"]
    assert result.status == JobStatus.CANCELED
    assert result.steps[0].status == StepStatus.DONE
    assert result.steps[1].status == StepStatus.DONE
    assert result.steps[2].status == StepStatus.PENDING

    events = CheckpointManager(str(tmp_path)).read_events(level_filter="WARN")
    assert any("canceled" in event.message.lower() for event in events)


def test_retry_policy_backoff_and_retryable_codes():
    policy = RetryPolicy(max_retry=3, backoff_seconds=2.0, step_timeout=10.0)

    assert policy.get_backoff(1) == pytest.approx(2.0)
    assert policy.get_backoff(2) == pytest.approx(4.0)
    assert policy.get_backoff(3) == pytest.approx(8.0)
    assert policy.should_retry(1, "TIMEOUT") is True
    assert policy.should_retry(1, "UPSTREAM_UNAVAILABLE") is True
    assert policy.should_retry(1, "NETWORK_ERROR") is True
    assert policy.should_retry(1, "VALIDATION_ERROR") is False
    assert policy.should_retry(3, "TIMEOUT") is False
