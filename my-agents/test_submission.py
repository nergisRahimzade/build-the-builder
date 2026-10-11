import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from submission import export_saved, write_submission, submission_metadata

METADATA = {"team": "Test", "members": [{"name": "Tester", "email": "test@example.com"}],
            "repo": "https://example.com/repo", "mock_url": "https://example.com/mock",
            "commit": "abc123", "run_command": "python my-agents/agent_builder.py brief.md"}

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("freya", ROOT / "freya.py")
freya = importlib.util.module_from_spec(spec)
spec.loader.exec_module(freya)


class SubmissionTests(unittest.TestCase):
    def test_runner_produces_three_required_artifacts_without_live_api(self):
        import agent_builder as builder
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "brief.md").write_text("Test brief")
            (root / "api.json").write_text("{}")
            class Result:
                context_wrapper = SimpleNamespace(usage=SimpleNamespace(requests=1, total_tokens=10))

                async def stream_events(self):
                    pathlib.Path(os.environ["FREYA_RUN_LOG"]).write_text(json.dumps(
                        {"slot": "brief", "workflow_id": "w", "agent_id": "a"}))
                    yield SimpleNamespace(type="raw_response_event", data="test event")

            def export(workflow_id, path):
                pathlib.Path(path).write_text(json.dumps({"workflow_id": workflow_id, "agent_id": "a", "workflow": {}}))

            with patch.object(builder, "KIT", root), \
                    patch.object(builder, "submission_metadata", return_value=METADATA), \
                    patch.object(builder, "snapshot_inputs", return_value=[]), \
                    patch.object(builder, "Agent", return_value=SimpleNamespace(model="mock")), \
                    patch.object(builder.Runner, "run_streamed", return_value=Result()), \
                    patch.dict("sys.modules", {"freya": freya}), \
                    patch.object(freya, "export_workflow", side_effect=export), \
                    patch("sys.argv", ["agent_builder.py", "brief.md", "--tool-api", "api.json", "--submission"]):
                builder.run_cli()
            folder, = (root / "submissions").iterdir()
            metadata = json.loads((folder / "submission.json").read_text())
            self.assertTrue((root / metadata["trace"]).is_file())
            self.assertTrue((root / metadata["workflow"]).is_file())
            self.assertEqual(set(metadata), {"team", "members", "repo", "commit", "run_command", "workflow", "trace", "mock_url"})
            self.assertIn("done:", (folder / "console.log").read_text())
            self.assertIn('"end":', (folder / "trace.jsonl").read_text())

    def test_successful_save_is_exported_and_hashed(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = pathlib.Path(temp)
            state = folder / "state.json"
            with patch.dict(os.environ, {"FREYA_RUN_LOG": str(folder / "saves.jsonl")}), \
                    patch.object(freya, "create_workflow", return_value={"workflow_id": "w", "agent_id": "a"}), \
                    patch.object(freya, "update_workflow", return_value=2):
                freya.save_workflow("brief", {}, str(state))
                freya.save_workflow("brief", {"updated": True}, str(state))
            calls = []
            def export(workflow_id, path):
                calls.append(workflow_id)
                pathlib.Path(path).write_text(json.dumps({"workflow_id": "w", "agent_id": "a", "workflow": {}}))
            records = []
            exports = export_saved(folder, ["brief"], export, records.append)
            self.assertEqual(calls, ["w"])
            self.assertEqual(exports[0]["version"], 2)
            (folder / "trace.jsonl").write_text("trace")
            (folder / "console.log").write_text("output")
            write_submission(folder, [], exports)
            manifest = json.loads((folder / "manifest.json").read_text())
            self.assertEqual(manifest["sha256"][exports[0]["file"]], exports[0]["sha256"])
            self.assertIn("trace.jsonl", manifest["sha256"])
            self.assertFalse((folder / "submission.json").exists())

    def test_metadata_captures_start_commit_and_rejects_dirty_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            config = root / "config.json"
            config.write_text(json.dumps(METADATA))
            with patch("submission.subprocess.check_output", side_effect=["abc123\n", ""]):
                result = submission_metadata(root, config, "python builder.py")
            self.assertEqual(result["commit"], "abc123")
            self.assertEqual(result["run_command"], "python builder.py")
            with patch("submission.subprocess.check_output", side_effect=["abc123\n", " M freya.py\n"]):
                with self.assertRaisesRegex(ValueError, "Commit builder"):
                    submission_metadata(root, config, "python builder.py")

    def test_metadata_rejects_missing_team_details(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            config = root / "config.json"
            config.write_text('{"team": ""}')
            with self.assertRaisesRegex(ValueError, "team"):
                submission_metadata(root, config, "python builder.py")

    def test_missing_current_run_save_does_not_export_stale_state(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = pathlib.Path(temp)
            (folder / ".freya-agents.json").write_text('{"brief": {"workflow_id": "stale"}}')
            with self.assertRaises(RuntimeError):
                export_saved(folder, ["brief"], lambda *args: self.fail("Must not export"), lambda _: None)

    def test_wrong_agent_export_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = pathlib.Path(temp)
            (folder / "saves.jsonl").write_text(json.dumps({"slot": "brief", "workflow_id": "w", "agent_id": "a"}))
            def export(workflow_id, path):
                pathlib.Path(path).write_text('{"workflow_id": "w", "agent_id": "wrong"}')
            with self.assertRaises(RuntimeError):
                export_saved(folder, ["brief"], export, lambda _: None)
            self.assertFalse((folder / "submission.json").exists())

    def test_package_requires_matching_trace(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = pathlib.Path(temp)
            (folder / "agent-1.workflow.json").write_text("{}")
            with self.assertRaisesRegex(RuntimeError, "trace.jsonl"):
                write_submission(folder, [], [{"file": "agent-1.workflow.json"}])
            self.assertFalse((folder / "submission.json").exists())

    def test_failed_save_is_not_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = pathlib.Path(temp)
            with patch.dict(os.environ, {"FREYA_RUN_LOG": str(folder / "saves.jsonl")}), \
                    patch.object(freya, "create_workflow", side_effect=RuntimeError("API error")):
                with self.assertRaises(RuntimeError):
                    freya.save_workflow("brief", {}, str(folder / "state.json"))
            self.assertFalse((folder / "saves.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
