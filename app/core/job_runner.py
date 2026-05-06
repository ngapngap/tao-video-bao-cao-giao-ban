"""Job runner tuần tự với checkpoint/resume/retry."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from typing import Callable, Optional

from app.core.checkpoint import CheckpointManager
from app.core.models import EventLogEntry, JobState, JobStatus, StepRecord, StepResult, StepStatus
from app.core.retry_policy import RetryPolicy

StepHandler = Callable[[JobState, str], Optional[StepResult | dict]]


class JobRunner:
    """Chạy job tuần tự theo steps, có checkpoint/resume/retry."""

    def __init__(
        self,
        job_state: JobState,
        output_dir: str,
        retry_policy: Optional[RetryPolicy] = None,
    ):
        self.job_state = job_state
        self.output_dir = output_dir
        self.step_handlers: dict[str, StepHandler] = {}
        self._cancel_requested = False
        self.retry_policy = retry_policy or RetryPolicy()
        self.checkpoint = CheckpointManager(output_dir)

    def register_step(self, step_id: str, handler: StepHandler):
        """Đăng ký handler cho step. Handler nhận (job_state, output_dir) và trả StepResult."""
        self.step_handlers[step_id] = handler

    def run(self):
        """Chạy job từ đầu hoặc resume từ checkpoint."""
        if self._cancel_requested:
            self._mark_job_canceled()
            return self.job_state

        loaded_state = self.checkpoint.load_state()
        if loaded_state is not None:
            self.job_state = loaded_state

        job_started_at = time.time()
        self._set_job_status(JobStatus.RUNNING)
        self._append_event("INFO", None, "▶ Job bắt đầu", "JOB")
        self._save_checkpoint()

        for step in self.job_state.steps:
            if step.status == StepStatus.DONE:
                continue

            if self._cancel_requested:
                self._mark_job_canceled()
                return self.job_state

            self.job_state.current_step_id = step.step_id
            self._run_step_with_retry(step)

            if self._cancel_requested:
                self._mark_job_canceled()
                return self.job_state

            if step.status == StepStatus.FAILED:
                self._set_job_status(JobStatus.FAILED)
                self._append_event("ERROR", step.step_id, "Job failed because step hard-failed")
                self._save_checkpoint()
                return self.job_state

        self.job_state.current_step_id = None
        self._set_job_status(JobStatus.DONE)
        elapsed = time.time() - job_started_at
        done_steps = sum(1 for item in self.job_state.steps if item.status == StepStatus.DONE)
        total_steps = len(self.job_state.steps)
        self._append_event("INFO", None, f"✓ Job hoàn thành tổng cộng ({elapsed:.1f}s), {done_steps}/{total_steps} steps", "JOB")
        self._save_checkpoint()
        return self.job_state

    def cancel(self):
        """Yêu cầu cancel job."""
        self._cancel_requested = True

    def retry_failed_step(self, step_id: str):
        """Retry step cụ thể."""
        step = self._get_step(step_id)
        if step.status != StepStatus.FAILED:
            raise ValueError(f"Step {step_id} is not FAILED")

        step.status = StepStatus.PENDING
        step.error_code = None
        step.error_message = None
        step.ended_at = None
        self.job_state.current_step_id = step.step_id
        self._set_job_status(JobStatus.RUNNING)
        self._append_event("INFO", step.step_id, "Retry failed step requested")
        self._save_checkpoint()
        return self.run()

    def resume(self):
        """Resume từ checkpoint (step chưa DONE đầu tiên)."""
        return self.run()

    def _run_step_with_retry(self, step: StepRecord):
        handler = self.step_handlers.get(step.step_id)
        if handler is None:
            self._mark_step_failed(step, "HANDLER_NOT_FOUND", f"No handler registered for {step.step_id}")
            return

        while not self._cancel_requested:
            step_started_at = time.time()
            step.attempt += 1
            step.status = StepStatus.RUNNING
            step.started_at = _utc_now()
            step.ended_at = None
            step.error_code = None
            step.error_message = None
            self._set_job_status(JobStatus.RUNNING)
            self._append_event("INFO", step.step_id, f"▶ Bắt đầu {step.name}")
            self._save_checkpoint()

            result = self._execute_handler(handler)
            elapsed = time.time() - step_started_at
            if result.success:
                step.status = StepStatus.DONE
                step.ended_at = _utc_now()
                step.error_code = None
                step.error_message = None
                step.artifacts = result.artifacts
                self._append_event("INFO", step.step_id, f"✓ Hoàn thành ({elapsed:.1f}s)")
                self._save_checkpoint()
                return

            error_code = result.error_code or "STEP_FAILED"
            error_message = result.error_message or "Step failed"
            if self.retry_policy.should_retry(step.attempt, error_code):
                step.status = StepStatus.WAITING_RETRY
                step.error_code = error_code
                step.error_message = error_message
                step.ended_at = _utc_now()
                self._set_job_status(JobStatus.WAITING_RETRY)
                backoff = self.retry_policy.get_backoff(step.attempt)
                self._append_event(
                    "WARN",
                    step.step_id,
                    f"✗ Thất bại ({elapsed:.1f}s): {error_code}; retry/thử lại sau {backoff:.2f}s",
                )
                self._save_checkpoint()
                if backoff > 0:
                    time.sleep(backoff)
                continue

            self._mark_step_failed(step, error_code, error_message, elapsed)
            return

    def _execute_handler(self, handler: StepHandler) -> StepResult:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(handler, self.job_state, self.output_dir)
            try:
                raw_result = future.result(timeout=self.retry_policy.step_timeout)
            except FutureTimeoutError:
                future.cancel()
                return StepResult(
                    success=False,
                    error_code="TIMEOUT",
                    error_message=f"Step timed out after {self.retry_policy.step_timeout:.2f}s",
                )
            except Exception as exc:  # noqa: BLE001 - chuyển exception handler thành StepResult chuẩn
                return StepResult(success=False, error_code="STEP_FAILED", error_message=str(exc))

        if raw_result is None:
            return StepResult(success=True)
        if isinstance(raw_result, StepResult):
            return raw_result
        if isinstance(raw_result, dict):
            return StepResult.model_validate(raw_result)
        raise TypeError("Step handler must return StepResult, dict, or None")

    def _mark_step_failed(self, step: StepRecord, error_code: str, error_message: str, elapsed: float | None = None):
        step.status = StepStatus.FAILED
        step.ended_at = _utc_now()
        step.error_code = error_code
        step.error_message = error_message
        duration = "0.0" if elapsed is None else f"{elapsed:.1f}"
        self._append_event("ERROR", step.step_id, f"✗ Thất bại ({duration}s): {error_message}")
        self._save_checkpoint()

    def _mark_job_canceled(self):
        self._set_job_status(JobStatus.CANCELED)
        self._append_event("WARN", self.job_state.current_step_id, "Job canceled")
        self._save_checkpoint()

    def _get_step(self, step_id: str) -> StepRecord:
        for step in self.job_state.steps:
            if step.step_id == step_id:
                return step
        raise ValueError(f"Step {step_id} not found")

    def _set_job_status(self, status: JobStatus):
        self.job_state.status = status
        self.job_state.updated_at = _utc_now()

    def _save_checkpoint(self):
        self.job_state.updated_at = _utc_now()
        self.checkpoint.save_state(self.job_state)

    def _append_event(self, level: str, step_id: Optional[str], message: str, display_step_id: Optional[str] = None):
        self.checkpoint.append_event(
            EventLogEntry(
                timestamp=_utc_now(),
                level=level,
                step_id=display_step_id or step_id,
                message=message,
                job_id=self.job_state.job_id,
            )
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
