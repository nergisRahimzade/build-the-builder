"""Build a Freya phone agent using the OpenAI Agents SDK and the existing skill.

    pip install openai-agents
    # From build-the-builder, after source env.sh:
    python my-agents/agent_builder.py briefs/brief-a.md

Needs OPENAI_API_KEY and FREYA_API_KEY; practice ledger tests also need FREYA_BANK_TEAM_KEY.
Messages, tool activity, exports and console output are retained in submissions/<run-id>/.
"""
import argparse, asyncio, contextlib, dataclasses, json, os, pathlib, re, shlex, shutil, subprocess, sys, time, traceback, uuid
from submission import Tee, snapshot_inputs, export_saved, write_submission, submission_metadata, redact
from case_inputs import read_document, prepare_case, model_inputs, input_slot

from agents import Agent, ItemHelpers, ModelSettings, Runner, function_tool # type: ignore
from agents.agent import StopAtTools
from openai.types.shared import Reasoning

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
KIT = ROOT
SKILL = ROOT / "my-skills/build-phone-agent/SKILL.md"


def local_path(path):
    p = pathlib.Path(path)
    return p if p.is_absolute() else KIT / p


@function_tool
def Read(file_path: str, offset: int = 1, limit: int = 2000) -> str:
    """Read UTF-8 text with a one-based starting line and maximum line count."""
    lines = read_document(local_path(file_path)).splitlines()
    return "\n".join(f"{i + offset}: {line}" for i, line in enumerate(lines[offset - 1:offset - 1 + limit]))


@function_tool
def Write(file_path: str, content: str) -> str:
    """Create or overwrite a UTF-8 file."""
    path = local_path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if path.name.endswith(".workflow.json"):
        from tools.audit_workflow import audit
        return json.dumps({"file": str(path), "structural_audit": audit(json.loads(content), os.environ.get("FREYA_MOCK_URL") or None)})
    return f"Wrote {path}"


@function_tool
def Edit(file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """Replace exact text; require a unique match unless replace_all is true."""
    path = local_path(file_path)
    content = path.read_text(encoding="utf-8")
    count = content.count(old_string)
    if not old_string or count == 0 or (count > 1 and not replace_all):
        raise ValueError("Provide nonempty matching text that is unique, or use replace_all.")
    path.write_text(content.replace(old_string, new_string, -1 if replace_all else 1), encoding="utf-8")
    return f"Updated {path}"


@function_tool
def Glob(pattern: str, path: str = ".") -> str:
    """Find files using a glob pattern relative to a directory; ** searches recursively."""
    return "\n".join(str(p) for p in local_path(path).glob(pattern) if p.is_file())


@function_tool
def Grep(pattern: str, path: str = ".", glob: str = "**/*") -> str:
    """Search text files for a regular expression; return file names, lines and matches."""
    root = local_path(path)
    files = [root] if root.is_file() else root.glob(glob)
    regex = re.compile(pattern)
    matches = []
    for file in files:
        if not file.is_file():
            continue
        try:
            lines = file.read_text(encoding="utf-8").splitlines()
        except (UnicodeError, OSError):
            continue
        matches.extend(f"{file}:{i}: {line}" for i, line in enumerate(lines, 1) if regex.search(line))
    return "\n".join(matches)


def bash_executable():
    # Prefer Git Bash over the Windows WSL launcher.
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles", "C:/Program Files"), os.environ.get("LOCALAPPDATA", "")):
            for suffix in ("Git/bin/bash.exe", "Programs/Git/bin/bash.exe"):
                candidate = pathlib.Path(base) / suffix
                if candidate.is_file():
                    return str(candidate)
    executable = shutil.which("bash")
    if not executable:
        raise RuntimeError("Bash was not found. Install Git Bash and add it to PATH.")
    return executable


@function_tool
async def Bash(command: str, timeout: int = 900000) -> str:
    """Run a foreground Bash command in the kit folder. Timeout is milliseconds, at most 1200000. Wait for tests; never background them."""
    env = {**os.environ, "BASH_DEFAULT_TIMEOUT_MS": "900000", "BASH_MAX_TIMEOUT_MS": "1200000", "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"}
    def run():
        try:
            result = subprocess.run(
                [bash_executable(), "-c", command], cwd=KIT, env=env,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=max(1, min(timeout, 1200000)) / 1000,
            )
            return json.dumps({"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        except subprocess.TimeoutExpired as exc:
            return f"Command timed out after {exc.timeout} seconds.\n{exc.stdout or ''}\n{exc.stderr or ''}"
    return await asyncio.to_thread(run)


def serialize(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if dataclasses.is_dataclass(value):
        return {field.name: getattr(value, field.name) for field in dataclasses.fields(value) if field.name != "agent"}
    return str(value)


async def builder_events(agent, run_input, record):
    """Resume completed tool history after a model rate limit, without rerunning tools."""
    for retry in range(5):
        result = Runner.run_streamed(agent, input=run_input, max_turns=150)
        try:
            async for event in result.stream_events():
                yield result, event
            return
        except Exception as exc:
            if "rate limit" not in str(exc).lower() or retry == 4:
                raise
            history = result.to_input_list()
            called = {item.get("call_id") for item in history if item.get("type") == "function_call"}
            returned = {item.get("call_id") for item in history if item.get("type") == "function_call_output"}
            if called - returned:
                # Do not replay an action whose completion is uncertain.
                raise
            match = re.search(r"try again in ([0-9.]+)s", str(exc), re.I)
            delay = min(60, max(10, float(match.group(1)) + 1 if match else 30))
            record({"type": "model_rate_limit_retry", "attempt": retry + 1, "delay_s": delay})
            print(f"Model rate limit; resuming completed history after {delay:g} seconds.", flush=True)
            await asyncio.sleep(delay)
            run_input = history


async def main(briefs, folder, tool_api=None, submission=False, mock_url=None, model=None):
    trace = folder / "trace.jsonl"
    finished = False
    @function_tool
    def FinishBuild(summary: str, tests_unavailable_reason: str = "") -> str:
        """Finish only after all workflows have been saved successfully and matching tests reviewed."""
        nonlocal finished
        journal = folder / "saves.jsonl"
        saved = {json.loads(line)["slot"] for line in journal.read_text().splitlines()} if journal.exists() else set()
        missing = {input_slot(local_path(b)) for b in briefs} - saved
        if missing:
            raise ValueError(f"Cannot finish: validated saves missing for {sorted(missing)}. Implement the repairs now.")
        sys.path.insert(0, str(KIT))
        import freya
        from tools.audit_workflow import audit, compare_deployment
        latest = {row["slot"]: row for row in (json.loads(line) for line in journal.read_text().splitlines())}
        tests_path = folder / "tests.jsonl"
        tests = [json.loads(line) for line in tests_path.read_text(encoding="utf-8").splitlines()] if tests_path.exists() else []
        for slot in saved:
            source = json.loads((KIT / "out" / f"{slot}.workflow.json").read_text(encoding="utf-8"))
            deployed = freya.api("GET", f"/api/v2/workflow/{latest[slot]['workflow_id']}", workspaceId=freya.workspace_id())["workflow"]["workflow"]
            errors = audit(source, mock_url)["errors"] + compare_deployment(source, deployed)
            if errors:
                raise ValueError(f"Cannot finish {slot}: " + "; ".join(errors))
            matching_tests = [test for test in tests if test["agent_id"] == latest[slot]["agent_id"] and test.get("version") == latest[slot].get("version")]
            if not matching_tests and not tests_unavailable_reason.strip():
                raise ValueError(f"No matching test report for the current saved version of {slot}. Run the matching test runner or state why tests are unavailable.")
        (folder / "completion.json").write_text(json.dumps({"summary": summary, "tests": tests,
            "tests_unavailable_reason": tests_unavailable_reason}, indent=2), encoding="utf-8")
        finished = True
        return summary
    extra = (f"\nUse the supplied tool API at {tool_api}; it overrides tools/openapi.json."
             if tool_api else "")
    for brief in briefs:
        if local_path(brief).is_dir():
            extra += "\n" + prepare_case(local_path(brief), folder)
            extra += "\nRead ALL policy and contract documents in this folder. No practice API fallback. The save slot is the case folder's name."
    if mock_url:
        extra += f"\nThe deployed mock base URL is {mock_url}. Replace only the contract's server base URL; keep paths and request/response shapes."
    if submission:
        extra += ("\nThis is a hidden-brief submission run. Build exactly one agent for the supplied brief. "
                  "Do not use practice briefs, practice API rules, or public-test-set.json for this brief. "
                  "Use supplied example scenarios to create test-only scenario JSON for tools/run_scenarios.py. "
                  "Do not use test fixture values as workflow constants. If no matching scenarios exist, report tests not run. "
                  "Validate the workflow with freya.validate_workflow before saving.")
    extra += ("\nSave every final workflow with freya.save_workflow using the brief filename stem (or folder name) as slot. "
              "The runner exports the saved agents automatically when you finish. "
              "Do not edit an agent after the run. Before each tool call, state its purpose in one sentence.")
    extra += ("\nPolicy text is attached to the initial input. Original diagrams are attached only when this brief explicitly identifies an accompanying workflow drawing; do not assume every brief has one. Build an explicit source-to-node flow map from the supplied evidence, "
              "including each decision, retry, failure and exit branch. Retain drawing behavior except where an accepted "
              "source explicitly supersedes it; record those overrides. The file inventory alone is not a workflow specification.")
    selected_model = model or os.environ.get("BUILDER_MODEL", "gpt-5.4")
    agent = Agent(
        name="Phone agent builder",
        model=selected_model,
        instructions=(f"Work from {KIT}. The build-phone-agent skill follows. "
                      "Use python instead of python3 on Windows.\n\n" + SKILL.read_text(encoding="utf-8") + extra),
        tools=[Read, Write, Edit, Glob, Grep, Bash, FinishBuild],
        model_settings=ModelSettings(parallel_tool_calls=False, tool_choice="required",
            reasoning=Reasoning(effort="high") if selected_model.startswith("gpt-5") else None),
        reset_tool_choice=False,
        tool_use_behavior=StopAtTools(stop_at_tool_names=["FinishBuild"]),
    )
    prompt = "Use the build-phone-agent skill to build a phone agent for: " + " ".join(briefs)
    run_input, source_manifest = model_inputs([local_path(p) for p in [*briefs, *([tool_api] if tool_api else [])]], prompt)
    (folder / "source-manifest.json").write_text(json.dumps(source_manifest, indent=2), encoding="utf-8")
    started = time.monotonic()
    result = None
    with trace.open("w", encoding="utf-8") as out:
        def record(data):
            out.write(redact(json.dumps(data, default=serialize)) + "\n")
            out.flush()
        record({"start": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "briefs": briefs, "model": agent.model})
        record({"type": "run_inputs", "tool_api": tool_api, "mock_url": mock_url,
                "instructions": getattr(agent, "instructions", ""), "prompt": prompt})
        purpose = prompt
        calls = {}
        try:
            for attempt in range(4):
                async for result, event in builder_events(agent, run_input, record):
                    record({"type": event.type, "event": event})
                    if event.type == "raw_response_event" and getattr(event.data, "type", None) == "response.created":
                        response = event.data.response
                        record({"type": "model_call", "model": getattr(response, "model", None) or agent.model,
                                "response_id": response.id, "purpose": " ".join(purpose.split())[:500]})
                    if event.type == "run_item_stream_event":
                        if event.item.type == "message_output_item":
                            print(ItemHelpers.text_message_output(event.item), flush=True)
                        elif event.item.type == "tool_call_item":
                            call = event.item.raw_item
                            calls[call.call_id] = {"tool": call.name, "arguments": call.arguments}
                            print(f"  [{call.name}] {call.arguments}", flush=True)
                        elif event.item.type == "tool_call_output_item":
                            print(str(event.item.output), flush=True)
                            raw = event.item.raw_item
                            call_id = raw.get("call_id") if isinstance(raw, dict) else getattr(raw, "call_id", None)
                            call = calls.get(call_id, {})
                            record({"type": "tool_result", **call, "output": event.item.output})
                            purpose = f"Review result of {call.get('tool', 'tool')} {call.get('arguments', '')} and continue building, validating or testing the brief's agent"
                journal = folder / "saves.jsonl"
                saved = {json.loads(line)["slot"] for line in journal.read_text().splitlines()} if journal.exists() else set()
                missing = {input_slot(local_path(b)) for b in briefs} - saved
                if finished or attempt == 3 or time.monotonic() - started > 1500:
                    break
                feedback = (f"Run incomplete: no validated save for {sorted(missing)}. Continue implementing and testing now; "
                            "a repair plan is not a completed build. Read the validation errors and repair all incomplete branches. "
                            "Bank record APIs belong in api_request pre_actions, followed by a separate end_call node whose "
                            "terminal handler is __function__:end_call. Do not use an api_call as the hang-up terminal. "
                            "Preserve every requirement from the supplied sources; do not remove required branches to pass validation.")
                record({"type": "incomplete_run_continuation", "attempt": attempt + 1, "feedback": feedback})
                run_input = result.to_input_list() + [{"role": "user", "content": feedback}]
            if not finished:
                raise RuntimeError("Builder did not complete verified FinishBuild; this run cannot be submitted")
            sys.path.insert(0, str(KIT))
            import freya
            exports = export_saved(folder, [input_slot(local_path(b)) for b in briefs], freya.export_workflow, record)
            print(f"Exported {len(exports)} agent(s) to {folder}", flush=True)
        except Exception as exc:
            record({"error": str(exc)})
            raise
        finally:
            usage = result.context_wrapper.usage if result else None
            elapsed = time.monotonic() - started
            record({"end": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "duration_s": elapsed, "usage": usage})
            # The SDK reports token usage, not a dollar cost.
            print(f"\ndone: {usage.requests if usage else 0} model calls, {elapsed:.0f} s, "
                  f"{usage.total_tokens if usage else 0} tokens. Trace: {trace}")
    return exports


def run_cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("briefs", nargs="+")
    parser.add_argument("--tool-api", help="Tool API belonging to this brief")
    parser.add_argument("--submission", action="store_true", help="One case folder, or a brief with its own --tool-api")
    parser.add_argument("--submission-config", default="submission-config.json", help="Team, members, repo and mock URL JSON")
    parser.add_argument("--mock-url", help="Deployed service base URL; submission mode defaults to the config's mock_url")
    parser.add_argument("--model", default=os.environ.get("BUILDER_MODEL", "gpt-5.4"), help="Builder model only; does not change the phone agent model")
    args = parser.parse_args()
    folder_mode = len(args.briefs) == 1 and local_path(args.briefs[0]).is_dir()
    if args.submission and (len(args.briefs) != 1 or (not folder_mode and not args.tool_api)):
        parser.error("--submission requires one case folder or one brief with --tool-api")
    if len({input_slot(local_path(b)) for b in args.briefs}) != len(args.briefs):
        parser.error("Brief filename stems must be unique")
    for name in [*args.briefs, *([args.tool_api] if args.tool_api else [])]:
        if not local_path(name).is_file() and not (name in args.briefs and local_path(name).is_dir()):
            parser.error(f"Input file does not exist: {name}")
    metadata = None
    if args.submission:
        try:
            command = ["python", "my-agents/agent_builder.py",
                *[local_path(b).resolve().relative_to(KIT.resolve()).as_posix() for b in args.briefs]]
            if args.tool_api:
                command += ["--tool-api", local_path(args.tool_api).resolve().relative_to(KIT.resolve()).as_posix()]
            command += ["--submission", "--submission-config", local_path(args.submission_config).resolve().relative_to(KIT.resolve()).as_posix()]
            command += ["--model", args.model]
            if args.mock_url:
                command += ["--mock-url", args.mock_url]
            metadata = submission_metadata(KIT, local_path(args.submission_config),
                shlex.join(command))
            template = command.copy()
            template[2] = "{case_folder}" if folder_mode else "{brief_path}"
            if args.tool_api:
                template[template.index("--tool-api") + 1] = "{tool_api_path}"
            metadata["_run_command_template"] = shlex.join(template)
            if args.mock_url and args.mock_url.rstrip("/") != metadata["mock_url"].rstrip("/"):
                parser.error("--mock-url and submission-config mock_url must match")
            args.mock_url = args.mock_url or metadata["mock_url"]
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            parser.error(str(exc))
    folder = KIT / "submissions" / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    inputs = snapshot_inputs(KIT, folder, args.briefs, args.tool_api)
    previous_log = os.environ.get("FREYA_RUN_LOG")
    audit_env = {"FREYA_ENFORCE_AUDIT": "1", "FREYA_MOCK_URL": args.mock_url or ""}
    previous_audit_env = {key: os.environ.get(key) for key in audit_env}
    os.environ.update(audit_env)
    os.environ["FREYA_RUN_LOG"] = str(folder / "saves.jsonl")
    try:
        with (folder / "console.log").open("w", encoding="utf-8") as log:
            with contextlib.redirect_stdout(Tee(sys.stdout, log)), contextlib.redirect_stderr(Tee(sys.stderr, log)):
                try:
                    exports = asyncio.run(asyncio.wait_for(main(args.briefs, folder, args.tool_api, args.submission, args.mock_url, args.model), timeout=1800))
                except BaseException:
                    traceback.print_exc()
                    (folder / "FAILED.txt").write_text("Run failed. Do not submit this folder.\n", encoding="utf-8")
                    raise
        write_submission(folder, inputs, exports, KIT, metadata)
    finally:
        for key, value in previous_audit_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if previous_log is None:
            os.environ.pop("FREYA_RUN_LOG", None)
        else:
            os.environ["FREYA_RUN_LOG"] = previous_log


if __name__ == "__main__":
    run_cli()
