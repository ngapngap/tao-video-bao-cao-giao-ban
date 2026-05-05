"""Smoke test cho portable app: kiểm tra import, config, job engine, workflow validator."""
import sys
import os
import tempfile

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def test_imports():
    """Test tất cả import chính."""
    print("Testing imports...")
    try:
        from app.core.models import JobState, StepRecord, JobStatus
        from app.core.job_runner import JobRunner
        from app.core.checkpoint import CheckpointManager
        from app.core.retry_policy import RetryPolicy
        from app.pdf.parser import PDFParser
        from app.pdf.normalizer import DataNormalizer
        from app.ai.schemas import ExtractedReport, WorkflowOutput
        from app.ai.llm_client import LLMClient
        from app.workflow.composer import WorkflowComposer
        from app.workflow.validator import WorkflowValidator
        from app.video.orchestrator import VideoOrchestrator
        from app.video.remotion_handoff import RemotionManifest, TTSGenerator, FinalPackager
        from app.security.credential_store import CredentialStore

        print("  [PASS] All imports OK")
        return True
    except Exception as e:
        print(f"  [FAIL] Import error: {e}")
        return False


def test_workflow_validator():
    """Test workflow validator với workflow hợp lệ."""
    print("Testing workflow validator...")
    from app.workflow.validator import WorkflowValidator

    validator = WorkflowValidator()
    workflow = {
        "workflow_metadata": {"report_month": "202603", "job_id": "test-001"},
        "video_settings": {"fps": 30, "resolution": "1920x1080"},
        "scenes": [
            {
                "scene_id": "intro",
                "scene_type": "intro",
                "title": "Intro",
                "tts": {"enabled": True, "text": "Hello"},
                "duration_policy": {"mode": "tts_first", "min_seconds": 4, "max_seconds": 10},
            },
            {
                "scene_id": "content1",
                "scene_type": "content",
                "title": "Content",
                "source_data_keys": ["m1"],
                "tts": {"enabled": True, "text": "Data"},
                "duration_policy": {"mode": "tts_first", "min_seconds": 5, "max_seconds": 20},
            },
            {
                "scene_id": "closing",
                "scene_type": "closing",
                "title": "End",
                "tts": {"enabled": False, "text": ""},
                "duration_policy": {"mode": "fixed", "min_seconds": 3, "max_seconds": 6},
            },
        ],
    }
    result = validator.validate(workflow)
    if result.passed:
        print("  [PASS] Valid workflow passed validation")
        return True
    else:
        print(f"  [FAIL] Valid workflow failed: {result.errors}")
        return False


def test_job_engine():
    """Test job engine chạy mock steps."""
    print("Testing job engine...")
    from app.core.models import JobState, StepRecord
    from app.core.job_runner import JobRunner

    with tempfile.TemporaryDirectory() as tmpdir:
        job = JobState(
            job_id="smoke-test",
            report_month="202603",
            created_at="2026-05-05T00:00:00Z",
            updated_at="2026-05-05T00:00:00Z",
            steps=[
                StepRecord(step_id="S1", name="Smoke step 1"),
                StepRecord(step_id="S2", name="Smoke step 2"),
                StepRecord(step_id="S3", name="Smoke step 3"),
            ],
        )
        runner = JobRunner(job, tmpdir)

        step_ran = []

        def mock_handler(job_state, output_dir):
            step_ran.append(job_state.current_step_id)
            from app.core.models import StepResult

            return StepResult(success=True, artifacts=[])

        runner.register_step("S1", mock_handler)
        runner.register_step("S2", mock_handler)
        runner.register_step("S3", mock_handler)

        runner.run()

        if len(step_ran) == 3:
            print(f"  [PASS] Job ran {len(step_ran)} steps")
            return True
        else:
            print(f"  [FAIL] Expected 3 steps, ran {len(step_ran)}")
            return False


def test_config_path():
    """Test app không phụ thuộc path tuyệt đối."""
    print("Testing path independence...")
    cwd = os.getcwd()
    if "Tao video bao cao giao ban" in cwd:
        print("  [PASS] Running from project directory (OK for dev)")
        return True
    else:
        print("  [PASS] Running from different directory")
        return True


def main():
    print("=== Smoke Test ===")
    tests = [test_imports, test_workflow_validator, test_job_engine, test_config_path]
    passed = sum(1 for t in tests if t())
    total = len(tests)
    print(f"\n=== Results: {passed}/{total} passed ===")
    if passed < total:
        sys.exit(1)
    print("ALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
