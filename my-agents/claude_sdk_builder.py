"""Build from the supplied case using the installed Claude Agent SDK and configured key."""
import argparse
import asyncio
import dataclasses
import json
import os
import pathlib
import sys
import time
import uuid

from claude_agent_sdk import ClaudeAgentOptions, query, AssistantMessage, TextBlock, ResultMessage
from submission import submission_metadata, snapshot_inputs, export_saved, write_submission, redact

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import freya


async def build(case, model):
    case = pathlib.Path(case).resolve()
    command = f'python my-agents/claude_sdk_builder.py "{case.relative_to(ROOT).as_posix()}" --model {model}'
    metadata = submission_metadata(ROOT, ROOT / "submission-config.json", command)
    folder = ROOT / "submissions" / (time.strftime("%Y%m%d-%H%M%S") + "-sdk-" + uuid.uuid4().hex[:6])
    folder.mkdir(parents=True)
    inputs = snapshot_inputs(ROOT, folder, [str(case)], None)
    journal = str(folder / "saves.jsonl")
    os.environ.update(FREYA_RUN_LOG=journal, FREYA_ENFORCE_AUDIT="1", FREYA_MOCK_URL=metadata["mock_url"])
    skill = (ROOT / "my-skills/build-phone-agent/SKILL.md").read_text(encoding="utf-8")
    options = ClaudeAgentOptions(cwd=ROOT, model=model, system_prompt=skill,
        allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"], permission_mode="dontAsk",
        setting_sources=[], max_turns=100, env={"FREYA_RUN_LOG": journal, "FREYA_ENFORCE_AUDIT": "1",
        "FREYA_MOCK_URL": metadata["mock_url"], "BASH_DEFAULT_TIMEOUT_MS": "900000", "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"})
    prompt = (f"Build one COMPLETE phone agent from case folder {case}. Mock base URL: {metadata['mock_url']}. "
        f"Save slot exactly {case.name!r} through freya.save_workflow. Read all supplied policy sources and its identified workflow PDF. "
        "Use tools/workflow_parts.py constructors. Never hardcode test customers. Do not read old traces/submissions. "
        "Urgent: prioritize creating and validating the complete graph now. If there is insufficient time for simulation, explicitly report tests not run. "
        "Do not edit builder source. FinishBuild is not available in this SDK runner: finish with your result after a successful validated save. "
        "The runner will export and package your saved agent automatically. Use python on Windows.")
    start = time.monotonic()
    with (folder / "trace.jsonl").open("w", encoding="utf-8") as trace, (folder / "console.log").open("w", encoding="utf-8") as console:
        def record(value):
            trace.write(redact(json.dumps(value, default=str)) + "\n")
            trace.flush()
        record({"start": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "model": model, "prompt": prompt})
        try:
            async for message in query(prompt=prompt, options=options):
                record({"type": type(message).__name__, "message": dataclasses.asdict(message)})
                if isinstance(message, AssistantMessage):
                    record({"type": "model_call", "model": model, "purpose": "Build, validate, or test the source-derived phone agent"})
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            text = redact(block.text)
                            console.write(text + "\n"); console.flush()
                            print(text.encode(sys.stdout.encoding or "utf-8", "backslashreplace").decode(sys.stdout.encoding or "utf-8"), flush=True)
                if isinstance(message, ResultMessage) and message.is_error:
                    raise RuntimeError(str(message))
            exports = export_saved(folder, [case.name], freya.export_workflow, record)
        except BaseException:
            (folder / "FAILED.txt").write_text("Incomplete SDK run. Do not submit.", encoding="utf-8")
            raise
        finally:
            record({"end": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "duration_s": time.monotonic() - start})
    write_submission(folder, inputs, exports, ROOT, metadata)
    print(f"Submission run: {folder}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case")
    parser.add_argument("--model", default="claude-sonnet-5-5")
    args = parser.parse_args()
    asyncio.run(asyncio.wait_for(build(args.case, args.model), 1800))
