"""Build a Freya phone agent using the OpenAI Agents SDK and the existing skill.

    pip install openai-agents
    # From build-the-builder, after source env.sh:
    python my-agents/agent_builder.py briefs/brief-a.md

Needs OPENAI_API_KEY, FREYA_API_KEY and FREYA_BANK_TEAM_KEY.
Messages, tool activity, exports and console output are retained in submissions/<run-id>/.
"""
import argparse, asyncio, contextlib, dataclasses, json, os, pathlib, re, shlex, shutil, subprocess, sys, time, traceback, uuid
from submission import Tee, snapshot_inputs, export_saved, write_submission, submission_metadata

from agents import Agent, ItemHelpers, ModelSettings, Runner, function_tool # type: ignore

ROOT = pathlib.Path(__file__).resolve().parent.parent
KIT = ROOT
SKILL = ROOT / "my-skills/build-phone-agent/SKILL.md"


def local_path(path):
    p = pathlib.Path(path)
    return p if p.is_absolute() else KIT / p


@function_tool
def Read(file_path: str, offset: int = 1, limit: int = 2000) -> str:
    """Read UTF-8 text with a one-based starting line and maximum line count."""
    lines = local_path(file_path).read_text(encoding="utf-8").splitlines()
    return "\n".join(f"{i + offset}: {line}" for i, line in enumerate(lines[offset - 1:offset - 1 + limit]))


@function_tool
def Write(file_path: str, content: str) -> str:
    """Create or overwrite a UTF-8 file."""
    path = local_path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
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


async def main(briefs, folder, tool_api=None, submission=False):
    trace = folder / "trace.jsonl"
    extra = (f"\nUse the supplied tool API at {tool_api}; it overrides tools/openapi.json."
             if tool_api else "")
    if submission:
        extra += ("\nThis is a hidden-brief submission run. Build exactly one agent for the supplied brief. "
                  "Do not use practice briefs, practice API rules, or public-test-set.json for this brief. "
                  "Only run customer tests if matching cases were supplied; otherwise report tests not run. "
                  "Validate the workflow with freya.validate_workflow before saving.")
    extra += ("\nSave every final workflow with freya.save_workflow using the brief filename stem as slot. "
              "The runner exports the saved agents automatically when you finish. "
              "Do not edit an agent after the run. Before each tool call, state its purpose in one sentence.")
    agent = Agent(
        name="Phone agent builder",
        model=os.environ.get("BUILDER_MODEL", "gpt-4.1"),
        instructions=(f"Work from {KIT}. The build-phone-agent skill follows. "
                      "Use python instead of python3 on Windows.\n\n" + SKILL.read_text(encoding="utf-8") + extra),
        tools=[Read, Write, Edit, Glob, Grep, Bash],
        model_settings=ModelSettings(parallel_tool_calls=False),
    )
    prompt = "Use the build-phone-agent skill to build a phone agent for: " + " ".join(briefs)
    started = time.monotonic()
    result = None
    with trace.open("w", encoding="utf-8") as out:
        def record(data):
            out.write(json.dumps(data, default=serialize) + "\n")
            out.flush()
        record({"start": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "briefs": briefs, "model": agent.model})
        try:
            result = Runner.run_streamed(agent, input=prompt, max_turns=150)
            async for event in result.stream_events():
                record({"type": event.type, "event": event})
                if event.type == "run_item_stream_event":
                    if event.item.type == "message_output_item":
                        print(ItemHelpers.text_message_output(event.item), flush=True)
                    elif event.item.type == "tool_call_item":
                        call = event.item.raw_item
                        print(f"  [{call.name}] {call.arguments[:120]}", flush=True)
                    elif event.item.type == "tool_call_output_item":
                        print(str(event.item.output), flush=True)
            sys.path.insert(0, str(KIT))
            import freya
            exports = export_saved(folder, [pathlib.Path(b).stem for b in briefs], freya.export_workflow, record)
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
    parser.add_argument("--submission", action="store_true", help="One hidden brief and its own API")
    parser.add_argument("--submission-config", default="submission-config.json", help="Team, members, repo and mock URL JSON")
    args = parser.parse_args()
    if args.submission and (len(args.briefs) != 1 or not args.tool_api):
        parser.error("--submission requires exactly one brief and --tool-api")
    if len({pathlib.Path(b).stem for b in args.briefs}) != len(args.briefs):
        parser.error("Brief filename stems must be unique")
    for name in [*args.briefs, *([args.tool_api] if args.tool_api else [])]:
        if not local_path(name).is_file():
            parser.error(f"Input file does not exist: {name}")
    metadata = None
    if args.submission:
        try:
            command = ["python", "my-agents/agent_builder.py",
                *[local_path(b).resolve().relative_to(KIT.resolve()).as_posix() for b in args.briefs],
                "--tool-api", local_path(args.tool_api).resolve().relative_to(KIT.resolve()).as_posix(),
                "--submission", "--submission-config",
                local_path(args.submission_config).resolve().relative_to(KIT.resolve()).as_posix()]
            metadata = submission_metadata(KIT, local_path(args.submission_config),
                shlex.join(command))
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            parser.error(str(exc))
    folder = KIT / "submissions" / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    inputs = snapshot_inputs(KIT, folder, args.briefs, args.tool_api)
    previous_log = os.environ.get("FREYA_RUN_LOG")
    os.environ["FREYA_RUN_LOG"] = str(folder / "saves.jsonl")
    try:
        with (folder / "console.log").open("w", encoding="utf-8") as log:
            with contextlib.redirect_stdout(Tee(sys.stdout, log)), contextlib.redirect_stderr(Tee(sys.stderr, log)):
                try:
                    exports = asyncio.run(main(args.briefs, folder, args.tool_api, args.submission))
                except BaseException:
                    traceback.print_exc()
                    (folder / "FAILED.txt").write_text("Run failed. Do not submit this folder.\n", encoding="utf-8")
                    raise
        write_submission(folder, inputs, exports, KIT, metadata)
    finally:
        if previous_log is None:
            os.environ.pop("FREYA_RUN_LOG", None)
        else:
            os.environ["FREYA_RUN_LOG"] = previous_log


if __name__ == "__main__":
    run_cli()
