"""Build a Freya phone agent using the OpenAI Agents SDK and the existing skill.

    pip install openai-agents
    # From build-the-builder, after source env.sh:
    python my-agents/agent_builder.py briefs/brief-a.md

Needs OPENAI_API_KEY, FREYA_API_KEY and FREYA_BANK_TEAM_KEY.
Messages and tool activity are written to traces/<start time>.jsonl.
"""
import asyncio, dataclasses, json, os, pathlib, re, shutil, subprocess, sys, time

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


async def main(briefs):
    trace = KIT / "traces" / (time.strftime("%Y%m%d-%H%M%S") + ".jsonl")
    trace.parent.mkdir(exist_ok=True)
    agent = Agent(
        name="Phone agent builder",
        model=os.environ.get("BUILDER_MODEL", "gpt-4.1"),
        instructions=(f"Work from {KIT}. The build-phone-agent skill follows. "
                      "Use python instead of python3 on Windows.\n\n" + SKILL.read_text(encoding="utf-8")),
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


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1:]))
