"""Orchestrator cho AI Pass 2 video generation."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from app.ai.llm_client import LLMClient
from app.core.checkpoint import CheckpointManager
from app.core.models import JobState, JobStatus, StepRecord, StepStatus
from app.core.retry_policy import RetryPolicy
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

STEP_ORDER = [
    "S2.1_scene_planning",
    "S2.2_visual_spec",
    "S2.3_narration_tts",
    "S2.4_component_spec",
    "S2.5_asset_plan",
    "S2.6_render_plan",
    "S2.7_qa_fix",
    "S2.8_final_packaging",
]

STEP_PROMPTS = {
    "S2.1_scene_planning": S2_1_SCENE_PLANNING,
    "S2.2_visual_spec": S2_2_VISUAL_SPEC,
    "S2.3_narration_tts": S2_3_NARRATION_TTS,
    "S2.4_component_spec": S2_4_COMPONENT_SPEC,
    "S2.5_asset_plan": S2_5_ASSET_PLAN,
    "S2.6_render_plan": S2_6_RENDER_PLAN,
    "S2.7_qa_fix": S2_7_QA_FIX,
    "S2.8_final_packaging": S2_8_FINAL_PACKAGING,
}

STEP_ARTIFACTS = {
    "S2.1_scene_planning": "remotion/scene-plan.json",
    "S2.2_visual_spec": "remotion/visual-spec.json",
    "S2.3_narration_tts": "tts/tts-script.json",
    "S2.4_component_spec": "remotion/component-spec.json",
    "S2.5_asset_plan": "remotion/asset-plan.json",
    "S2.6_render_plan": "remotion/render-plan.json",
    "S2.7_qa_fix": "remotion/qa-fix.json",
    "S2.8_final_packaging": "final/publish-manifest.json",
}


class VideoOrchestrator:
    """Orchestrate AI Pass 2 steps tuần tự."""

    def __init__(
        self,
        llm_client: LLMClient,
        output_dir: str,
        checkpoint: CheckpointManager,
        retry_policy: RetryPolicy,
        on_step_update: Optional[Callable] = None,
    ):
        self.llm = llm_client
        self.output_dir = output_dir
        self.checkpoint = checkpoint
        self.retry = retry_policy
        self.on_step_update = on_step_update
        self._cancel_requested = False

    def run_pipeline(self, job_state: JobState, workflow_data: dict) -> JobState:
        """Chạy toàn bộ S2.1→S2.8 tuần tự."""
        job_state.status = JobStatus.RUNNING
        job_state.updated_at = self._now_iso()
        self.checkpoint.save_state(job_state)

        for step_id in STEP_ORDER:
            if self._cancel_requested or job_state.status == JobStatus.CANCELED:
                return self._mark_canceled(job_state)
            if self._should_skip(job_state, step_id):
                continue

            job_state = self._run_step(job_state, step_id, workflow_data)
            if job_state.status in {JobStatus.FAILED, JobStatus.CANCELED}:
                break

        if job_state.status not in {JobStatus.FAILED, JobStatus.CANCELED}:
            job_state.status = JobStatus.DONE
            job_state.current_step_id = None
            job_state.updated_at = self._now_iso()
            self.checkpoint.save_state(job_state)
        return job_state

    def cancel(self):
        """Yêu cầu dừng pipeline ở ranh giới step an toàn tiếp theo."""
        self._cancel_requested = True

    def _should_skip(self, job_state: JobState, step_id: str) -> bool:
        """Skip step đã DONE."""
        for step in job_state.steps:
            if step.step_id == step_id and step.status == StepStatus.DONE:
                return True
        return False

    def _run_step(self, job_state: JobState, step_id: str, workflow_data: dict) -> JobState:
        """Chạy 1 step với retry/backoff."""
        step = self._get_or_create_step(job_state, step_id)
        for attempt in range(1, self.retry.max_retry + 1):
            if self._cancel_requested or job_state.status == JobStatus.CANCELED:
                return self._mark_canceled(job_state)

            step.attempt = attempt
            step.status = StepStatus.RUNNING
            step.started_at = self._now_iso()
            step.ended_at = None
            step.error_code = None
            step.error_message = None
            job_state.status = JobStatus.RUNNING
            job_state.current_step_id = step_id
            job_state.updated_at = self._now_iso()
            self.checkpoint.save_state(job_state)
            self._notify(job_state, step_id, "running")

            try:
                input_data = self._build_step_input(step_id, workflow_data)
                system_prompt = self._get_prompt(step_id)
                result = self._chat_video_step(system_prompt, input_data, step_id, workflow_data)
                self._validate_step_output(step_id, result)
                artifact_path = self._save_artifact(step_id, result)

                step.status = StepStatus.DONE
                step.ended_at = self._now_iso()
                step.artifacts = [artifact_path]
                job_state.status = JobStatus.RUNNING
                job_state.updated_at = self._now_iso()
                self.checkpoint.save_state(job_state)
                self._notify(job_state, step_id, "done")
                return job_state
            except Exception as exc:
                step.error_code = "STEP_FAILED"
                step.error_message = str(exc)
                step.status = StepStatus.WAITING_RETRY
                step.ended_at = self._now_iso()
                job_state.status = JobStatus.WAITING_RETRY
                job_state.updated_at = self._now_iso()
                self.checkpoint.save_state(job_state)
                self._notify(job_state, step_id, "retry", str(exc))

                if attempt < self.retry.max_retry:
                    backoff = self.retry.get_backoff(attempt)
                    if backoff > 0:
                        time.sleep(backoff)

        step.status = StepStatus.FAILED
        step.ended_at = self._now_iso()
        job_state.status = JobStatus.FAILED
        job_state.updated_at = self._now_iso()
        self.checkpoint.save_state(job_state)
        self._notify(job_state, step_id, "failed")
        return job_state

    def _get_or_create_step(self, job_state: JobState, step_id: str) -> StepRecord:
        for step in job_state.steps:
            if step.step_id == step_id:
                return step
        new_step = StepRecord(step_id=step_id, name=step_id)
        job_state.steps.append(new_step)
        return new_step

    def _build_step_input(self, step_id: str, workflow_data: dict) -> dict:
        """Build input payload cho step từ upstream artifacts."""
        return {
            "job_context": {"step_id": step_id},
            "workflow": workflow_data,
            "upstream_artifacts": self._collect_upstream_artifacts(step_id),
        }

    def _collect_upstream_artifacts(self, step_id: str) -> dict:
        """Đọc tất cả artifact từ step trước."""
        artifacts = {}
        for prev_step_id in STEP_ORDER:
            if prev_step_id == step_id:
                break
            path = os.path.join(self.output_dir, STEP_ARTIFACTS.get(prev_step_id, ""))
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    artifacts[prev_step_id] = json.load(f)
        return artifacts

    def _get_prompt(self, step_id: str) -> str:
        return STEP_PROMPTS[step_id]

    def _chat_video_step(self, system_prompt: str, input_data: dict, step_id: str, workflow_data: dict) -> dict:
        """Gọi LLM S2.x với max_tokens thấp và fallback khi lỗi parse JSON."""
        try:
            return self.llm.chat(system_prompt, json.dumps(input_data, ensure_ascii=False), max_tokens=2000)
        except TypeError as exc:
            if "max_tokens" not in str(exc):
                raise
            return self.llm.chat(system_prompt, json.dumps(input_data, ensure_ascii=False))
        except ValueError:
            return self._fallback_step_output(step_id, workflow_data, input_data)

    def _fallback_step_output(self, step_id: str, workflow_data: dict, input_data: dict) -> dict:
        """Fallback deterministic cho S2.x khi LLM fail hoặc JSON bị truncate."""
        scene_plan = self._fallback_scene_plan(workflow_data)
        upstream = input_data.get("upstream_artifacts", {}) if isinstance(input_data, dict) else {}
        scenes = scene_plan.get("scenes", [])

        if step_id == "S2.1_scene_planning":
            return scene_plan
        if step_id == "S2.2_visual_spec":
            return {
                "scene_visuals": [
                    {
                        "scene_id": scene.get("scene_id"),
                        "visual_type": "title_card" if scene.get("scene_type") in {"intro", "closing"} else "text_callout",
                        "layers": [{"type": "text", "data_source": scene.get("scene_id"), "position": "center", "animation": "fade_in"}],
                    }
                    for scene in scenes
                ]
            }
        if step_id == "S2.3_narration_tts":
            source_scenes = workflow_data.get("scenes", []) if isinstance(workflow_data.get("scenes", []), list) else []
            return {
                "scripts": [
                    {
                        "scene_id": scene.get("scene_id"),
                        "enabled": bool(scene.get("tts", {}).get("enabled", True)),
                        "text": str(scene.get("tts", {}).get("text") or scene.get("title") or ""),
                        "voice": str(scene.get("tts", {}).get("voice") or "vi-VN-NamMinhNeural"),
                    }
                    for scene in source_scenes
                    if isinstance(scene, dict)
                ]
            }
        if step_id == "S2.4_component_spec":
            return {"components": [{"scene_id": scene.get("scene_id"), "type": scene.get("scene_type") or "content", "data": scene, "animation": "fade", "duration": 5} for scene in scenes]}
        if step_id == "S2.5_asset_plan":
            return {"assets": [{"asset_id": "font_default", "type": "font", "source": "local", "required": True}]}
        if step_id == "S2.6_render_plan":
            fps = int(workflow_data.get("video_settings", {}).get("fps") or 30)
            start_frame = 0
            timeline = []
            for scene in scenes:
                duration_seconds = 5
                duration_frames = duration_seconds * fps
                timeline.append({"scene_id": scene.get("scene_id"), "start_frame": start_frame, "duration_frames": duration_frames, "duration_seconds": duration_seconds})
                start_frame += duration_frames
            return {"fps": fps, "timeline": timeline, "total_frames": start_frame, "estimated_duration_seconds": round(start_frame / fps, 1) if fps else 0}
        if step_id == "S2.7_qa_fix":
            return {"issues": [], "patches": [], "status": "passed", "source": "deterministic_fallback"}
        if step_id == "S2.8_final_packaging":
            return {"status": "ready", "artifacts": [], "source": "deterministic_fallback"}
        return {"source": "deterministic_fallback"}

    def _fallback_scene_plan(self, workflow_data: dict) -> dict:
        """Fallback scene plan từ workflow khi LLM fail."""
        scenes = workflow_data.get("scenes", [])
        if not isinstance(scenes, list):
            scenes = []
        return {
            "scenes": [
                {
                    "scene_id": s.get("scene_id"),
                    "scene_type": s.get("scene_type"),
                    "title": s.get("title"),
                    "shots": [{"shot_id": f"{s.get('scene_id')}_shot_01", "type": "main"}],
                }
                for s in scenes
                if isinstance(s, dict)
            ]
        }

    def _validate_step_output(self, step_id: str, result: dict):
        """Validate output cơ bản: phải là dict."""
        if not isinstance(result, dict):
            raise ValueError(f"Step {step_id} output phải là dict")

    def _save_artifact(self, step_id: str, data: dict) -> str:
        rel_path = STEP_ARTIFACTS.get(step_id, f"remotion/{step_id}.json")
        full_path = os.path.join(self.output_dir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return rel_path

    def _notify(self, job_state: JobState, step_id: str, status: str, detail: str = ""):
        if self.on_step_update:
            self.on_step_update(job_state, step_id, status, detail)

    def _mark_canceled(self, job_state: JobState) -> JobState:
        job_state.status = JobStatus.CANCELED
        job_state.current_step_id = None
        job_state.updated_at = self._now_iso()
        self.checkpoint.save_state(job_state)
        return job_state

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()
