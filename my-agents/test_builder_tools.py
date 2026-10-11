import asyncio
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

import agent_builder as builder


class BuilderToolTests(unittest.TestCase):
    def test_search_excludes_old_run_logs_and_bounds_results(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "traces").mkdir()
            (root / "traces/old.jsonl").write_text("needle PRIVATE_OLD_RUN")
            (root / "policy.md").write_text("needle " + "x" * 40000)
            with patch.object(builder, "KIT", root):
                result = asyncio.run(builder.Grep.on_invoke_tool(None, json.dumps({"pattern": "needle", "path": ".", "glob": "**/*"})))
            self.assertNotIn("PRIVATE_OLD_RUN", result)
            self.assertIn("policy.md", result)
            self.assertLess(len(result), builder.MAX_TOOL_CHARS)

    def test_rate_limit_resumes_completed_history_without_replaying_tool(self):
        class Result:
            def __init__(self, error): self.error = error
            async def stream_events(self):
                if self.error: raise RuntimeError("Rate limit; try again in 0.1s")
                yield "completed"
            def to_input_list(self): return [{"role": "user", "content": "completed history"}]
        async def run():
            return [event async for _, event in builder.builder_events(None, [], lambda _: None)]
        with patch.object(builder.Runner, "run_streamed", side_effect=[Result(True), Result(False)]) as runner, patch.object(builder.asyncio, "sleep"):
            self.assertEqual(asyncio.run(run()), ["completed"])
            self.assertEqual(runner.call_args_list[1].kwargs["input"], [{"role": "user", "content": "completed history"}])
