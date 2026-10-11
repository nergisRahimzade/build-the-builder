"""Local submission artifacts. Export only agents saved by the current run."""
import hashlib
import json
import pathlib
import shutil
import subprocess


def submission_metadata(root, config_path, run_command):
    config = json.loads(config_path.read_text(encoding="utf-8"))
    for key in ("team", "repo", "mock_url"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ValueError(f"Submission configuration needs {key}")
    members = config.get("members")
    if not isinstance(members, list) or not members or any(
        not isinstance(member, dict) or any(
            not isinstance(member.get(key), str) or not member[key].strip()
            for key in ("name", "email")) for member in members
    ):
        raise ValueError("Submission configuration needs member names and emails")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    # Generated workflows and traces may be dirty, but the builder must match the recorded commit.
    source_paths = ["my-agents", "my-skills", "freya.py", "tools", "docs", "examples/base-agent.json"]
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", *source_paths], cwd=root, text=True)
    dirty = "\n".join(line for line in dirty.splitlines() if "__pycache__/" not in line)
    if dirty:
        raise ValueError("Commit builder source changes before a submission run so 'commit' identifies the code used")
    return {key: config[key] for key in ("team", "members", "repo", "mock_url")} | {
        "commit": commit, "run_command": run_command}


class Tee:
    def __init__(self, stream, log):
        self.stream, self.log = stream, log

    def write(self, text):
        self.stream.write(text)
        self.log.write(text)
        self.log.flush()
        return len(text)

    def flush(self):
        self.stream.flush()
        self.log.flush()


def snapshot_inputs(root, folder, briefs, tool_api):
    inputs = []
    for i, name in enumerate([*briefs, *([tool_api] if tool_api else [])]):
        source = pathlib.Path(name)
        if not source.is_absolute():
            source = root / source
        target = folder / "inputs" / f"{i + 1}-{source.name}"
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, target)
        inputs.append({"source": str(source), "snapshot": str(target.relative_to(folder))})
    for name in ("my-agents/agent_builder.py", "my-agents/submission.py",
                 "my-skills/build-phone-agent/SKILL.md", "freya.py",
                 "tools/run_cases.py", "tools/score.py",
                 "docs/workflow-format.md", "docs/tools-and-code.md",
                 "examples/base-agent.json", "tools/openapi.json", "public-test-set.json"):
        target = folder / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    return inputs


def export_saved(folder, expected_slots, export_workflow, record):
    log = folder / "saves.jsonl"
    saves = {}
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            saved = json.loads(line)
            saves[saved["slot"]] = saved
    if set(saves) != set(expected_slots):
        raise RuntimeError(f"Expected saves for {expected_slots}, got {list(saves)}; submission incomplete")
    if len({s["workflow_id"] for s in saves.values()}) != len(saves):
        raise RuntimeError("Each brief must have its own workflow")
    exports = []
    for i, slot in enumerate(expected_slots, 1):
        saved = saves[slot]
        path = folder / f"agent-{i}.workflow.json"
        export_workflow(saved["workflow_id"], str(path))
        data = json.loads(path.read_text())
        if data["workflow_id"] != saved["workflow_id"] or data["agent_id"] != saved["agent_id"]:
            raise RuntimeError("Exported agent does not match the run's saved agent")
        item = {**saved, "file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        record({"type": "workflow_export", **item})
        exports.append(item)
    return exports


def write_submission(folder, inputs, exports, root=None, metadata=None):
    if not exports or (folder / "FAILED.txt").exists():
        raise RuntimeError("Cannot package an empty or failed run")
    for name in ("trace.jsonl", "console.log", *(item["file"] for item in exports)):
        if not (folder / name).is_file():
            raise RuntimeError(f"Missing submission artifact: {name}")
    hashes = {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in folder.rglob("*") if p.is_file() and p.name not in ("submission.json", "manifest.json")}
    submission = {"status": "exported", "inputs": inputs, "agents": exports,
                  "builder": "OpenAI Agents SDK", "trace": "trace.jsonl",
                  "console": "console.log", "sha256": hashes}
    (folder / "manifest.json").write_text(json.dumps(submission, indent=2), encoding="utf-8")
    if metadata is not None:
        if len(exports) != 1:
            raise RuntimeError("The organizer schema requires exactly one workflow per submission.json")
        package = {**metadata,
                   "workflow": (folder / exports[0]["file"]).resolve().relative_to(root.resolve()).as_posix(),
                   "trace": (folder / "trace.jsonl").resolve().relative_to(root.resolve()).as_posix()}
        (folder / "submission.json").write_text(json.dumps(package, indent=2, ensure_ascii=False), encoding="utf-8")
