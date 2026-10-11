import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

from case_inputs import prepare_case, read_document, model_inputs, confirmed_workflow_files
from submission import snapshot_inputs, write_submission, package_final_run

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from audit_workflow import audit
from run_scenarios import load_cases, run


class CaseInputTests(unittest.TestCase):
    def test_original_pdf_requires_explicit_workflow_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            case = pathlib.Path(temp)
            (case / "drawing.pdf").write_bytes(b"synthetic PDF input")
            entry = case / "README.md"
            entry.write_text("Supporting document: `drawing.pdf`", encoding="utf-8")
            messages, manifest = model_inputs([case], "Build from sources")
            self.assertFalse(any(c["type"] == "input_file" for c in messages[0]["content"]))
            entry.write_text("`drawing.pdf`: a call-flow drawing of the step.", encoding="utf-8")
            messages, manifest = model_inputs([case], "Build from sources")
            self.assertEqual(sum(c["type"] == "input_file" for c in messages[0]["content"]), 1)
            attached = next(item for item in manifest if item["delivery"] == "original_pdf")
            self.assertEqual(attached["workflow_confirmed_by"]["line"], 1)

    def test_brief_without_drawing_does_not_inherit_another_briefs_drawing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "flow.pdf").write_bytes(b"synthetic")
            first, second = root / "first.md", root / "second.md"
            first.write_text("Workflow: [drawing](flow.pdf)", encoding="utf-8")
            second.write_text("Use the supplied API.", encoding="utf-8")
            self.assertTrue(confirmed_workflow_files(first))
            self.assertFalse(confirmed_workflow_files(second))

    def test_case_folder_inventory_and_pdf_extraction(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            case = root / "case"
            case.mkdir()
            (case / "policy.md").write_text("policy", encoding="utf-8")
            (case / "flow.pdf").write_bytes(b"placeholder")
            with patch("case_inputs.read_document", return_value="diagram text"):
                inventory = prepare_case(case, root / "run")
            self.assertIn("policy.md", inventory)
            self.assertIn("flow.pdf", inventory)
            self.assertEqual((root / "run/documents/flow.pdf.txt").read_text(), "diagram text")

    def test_snapshot_preserves_entire_case_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            case = root / "case"
            (case / "sources").mkdir(parents=True)
            (case / "sources/source.txt").write_text("input")
            output = root / "run"
            output.mkdir()
            # Source snapshots come from the real kit; case input can be an absolute path.
            inputs = snapshot_inputs(ROOT, output, [str(case)], None)
            self.assertEqual((output / inputs[0]["snapshot"] / "sources/source.txt").read_text(), "input")
            self.assertTrue((output / "source/tools/run_scenarios.py").is_file())

    def test_schema_audit_catches_stripped_actions_and_wrong_server(self):
        workflow = {"initial_node": "start", "nodes": {"start": {
            "node_type": "conversation", "pre_actions": [{"a": 1}],
            "transitions": [{"target_node": "missing"}], "tools": [{"type": "function", "function": {
                "handler": "__function__:api_call", "parameters": {"properties": {"url": {"default": "https://wrong.test/api"}}}}}]}}}
        result = audit(workflow, "https://correct.test")
        for expected in ("pre_actions", "transition target", "outside the supplied mock", "HTTP method", "no executable"):
            self.assertTrue(any(expected in error for error in result["errors"]), result)
        self.assertEqual(result["tools"], 1)

    def test_final_package_paths_and_zip(self):
        import zipfile
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            folder = root / "submissions/run"
            folder.mkdir(parents=True)
            for name in ("trace.jsonl", "console.log", "agent-1.workflow.json"):
                (folder / name).write_text("{}")
            metadata = {"team": "Team", "members": [{"name": "N", "email": "n@example.com"}],
                        "repo": "https://example.com/repo", "commit": "123", "run_command": "python builder case",
                        "mock_url": "https://mock.example.com"}
            write_submission(folder, [], [{"file": "agent-1.workflow.json"}], root, metadata)
            package_final_run(root, "submissions/run", bundle="package.zip")
            package = json.loads((root / "submission.json").read_text())
            with zipfile.ZipFile(root / "package.zip") as archive:
                self.assertIn("submission.json", archive.namelist())
                self.assertIn(package["workflow"], archive.namelist())
                self.assertIn(package["trace"], archive.namelist())

    def test_scenario_runner_retains_full_reason_and_tool_transcript(self):
        with tempfile.TemporaryDirectory() as temp:
            output = pathlib.Path(temp) / "results.json"
            cases = [{"id": "case-1", "source": "examples.md", "who": "caller", "script": "request",
                      "variables": {"caller": "synthetic"}, "checks": ["Follow the source policy"]}]
            with patch("run_scenarios.freya.create_personas", return_value={"personas": [{"id": "p1"}]}), \
                    patch("run_scenarios.freya.run_simulation", return_value=("s1", "i1", "completed")), \
                    patch("run_scenarios.freya.get_iteration", return_value={"runs": [{"personaId": "p1", "callId": "c1", "outcome": "fail", "reason": "wrong tool result"}]}), \
                    patch("run_scenarios.freya.get_call", return_value={"messages": [{"role": "tool", "content": "failure"}]}):
                report = run("agent", cases, output)
            self.assertEqual(report["passed"], 0)
            self.assertEqual(report["rows"][0]["failed"], ["wrong tool result"])
            self.assertTrue(report["rows"][0]["call"]["messages"])


if __name__ == "__main__":
    unittest.main()
