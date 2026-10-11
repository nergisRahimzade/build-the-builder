"""Local submission artifacts. Export only agents saved by the current run."""
import hashlib
import json
import pathlib
import shutil
import subprocess
import os
import re


def redact(text):
    for key, value in os.environ.items():
        if value and len(value) >= 6 and any(word in key.upper() for word in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            text = text.replace(value, "[REDACTED]").replace(json.dumps(value)[1:-1], "[REDACTED]")
    return re.sub(r"(?i)(bearer\s+)[a-z0-9_.-]+", r"\1[REDACTED]", text)


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
    source_paths = ["my-agents", "my-skills", "freya.py", "tools", "docs", "examples/base-agent.json", "requirements-builder.txt", "cloudflare-worker"]
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
        text = redact(text)
        self.log.write(text)
        self.log.flush()
        try:
            self.stream.write(text)
        except UnicodeEncodeError:
            encoding = getattr(self.stream, "encoding", None) or "ascii"
            self.stream.write(text.encode(encoding, errors="backslashreplace").decode(encoding))
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
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git", "node_modules", ".wrangler", "__pycache__"))
        else:
            shutil.copyfile(source, target)
        inputs.append({"source": str(source), "snapshot": str(target.relative_to(folder))})
    for name in ("my-agents/agent_builder.py", "my-agents/claude_runner.py", "my-agents/submission.py", "my-agents/case_inputs.py",
                 "my-skills/build-phone-agent/SKILL.md", "freya.py",
                 "tools/run_cases.py", "tools/run_scenarios.py", "tools/test_evidence.py", "tools/audit_workflow.py", "tools/workflow_parts.py", "tools/score.py", "requirements-builder.txt",
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
        workflow = data["workflow"]
        item = {**saved, "file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "steps": len(workflow.get("nodes", {})), "global_steps": len(workflow.get("global_nodes", {})),
                "tools": len(workflow.get("tools", [])) + sum(len(node.get("tools", []))
                    for group in (workflow.get("nodes", {}), workflow.get("global_nodes", {})) for node in group.values())}
        record({"type": "workflow_export", **item})
        exports.append(item)
    return exports


def write_submission(folder, inputs, exports, root=None, metadata=None):
    if not exports or (folder / "FAILED.txt").exists():
        raise RuntimeError("Cannot package an empty or failed run")
    for name in ("trace.jsonl", "console.log", *(item["file"] for item in exports)):
        if not (folder / name).is_file():
            raise RuntimeError(f"Missing submission artifact: {name}")
    for name in ("trace.jsonl", "console.log"):
        path = folder / name
        path.write_text(redact(path.read_text(encoding="utf-8")), encoding="utf-8")
    for line in (folder / "trace.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("duration_s", 0) > 1800:
            raise RuntimeError("Run exceeded the 30-minute submission limit")
    for item in exports:
        text = (folder / item["file"]).read_text(encoding="utf-8")
        if redact(text) != text:
            raise RuntimeError("Export contains a credential; rebuild without it. The export was not modified.")
    hashes = {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in folder.rglob("*") if p.is_file() and p.name not in ("submission.json", "manifest.json")}
    submission = {"status": "exported", "inputs": inputs, "agents": exports,
                  "builder": "OpenAI Agents SDK", "trace": "trace.jsonl",
                  "console": "console.log", "sha256": hashes}
    if metadata:
        submission["run_command_template"] = metadata.get("_run_command_template")
    (folder / "manifest.json").write_text(json.dumps(submission, indent=2), encoding="utf-8")
    if metadata is not None:
        if len(exports) != 1:
            raise RuntimeError("The organizer schema requires exactly one workflow per submission.json")
        package = {**{k: v for k, v in metadata.items() if not k.startswith("_")},
                   "workflow": (folder / exports[0]["file"]).resolve().relative_to(root.resolve()).as_posix(),
                   "trace": (folder / "trace.jsonl").resolve().relative_to(root.resolve()).as_posix()}
        (folder / "submission.json").write_text(json.dumps(package, indent=2, ensure_ascii=False), encoding="utf-8")


def combine_submissions(root, selected, output):
    """Create the website's two-brief form without modifying any workflow or trace."""
    root = root.resolve()
    if len(selected) != 2:
        raise ValueError("Select exactly two brief runs")
    packages, manifests = [], []
    workflows, traces = {}, {}
    for label, run_folder in selected.items():
        folder = (root / run_folder).resolve()
        folder.relative_to(root)
        if (folder / "FAILED.txt").exists():
            raise ValueError("Cannot submit a failed run")
        package = json.loads((folder / "submission.json").read_text(encoding="utf-8"))
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if len(manifest["agents"]) != 1 or manifest["agents"][0]["slot"] != label:
            raise ValueError("Brief label must match the selected run's saved slot")
        for name, digest in manifest["sha256"].items():
            path = (folder / name).resolve()
            path.relative_to(folder)
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError(f"Run artifact changed after packaging: {name}")
        for field, name in (("workflow", manifest["agents"][0]["file"]), ("trace", manifest["trace"])):
            expected = (folder / name).relative_to(root).as_posix()
            if package[field] != expected:
                raise ValueError(f"Submission {field} does not match its run manifest")
        workflows[label], traces[label] = package["workflow"], package["trace"]
        packages.append(package)
        manifests.append(manifest)
    for key in ("team", "repo", "commit", "members", "mock_url"):
        if packages[0].get(key) != packages[1].get(key):
            raise ValueError(f"Selected runs disagree on {key}")
    if manifests[0].get("run_command_template") != manifests[1].get("run_command_template") or not manifests[0].get("run_command_template"):
        raise ValueError("Selected runs must share a reproducible builder command template")
    if len({m["agents"][0]["workflow_id"] for m in manifests}) != 2:
        raise ValueError("Select distinct workflows for the two briefs")
    combined = {k: packages[0][k] for k in ("team", "repo", "commit", "members", "mock_url") if k in packages[0]}
    combined.update(run_command=manifests[0]["run_command_template"], workflows=workflows, traces=traces)
    output = (root / output).resolve()
    output.relative_to(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(combined, indent=2, ensure_ascii=False))
    return output


def package_final_run(root, run_folder, output="submission.json", bundle=None):
    """Package the final case's singular schema without rebuilding or editing the agent."""
    import zipfile
    root = root.resolve()
    folder = (root / run_folder).resolve()
    folder.relative_to(root)
    if (folder / "FAILED.txt").exists():
        raise ValueError("Cannot package a failed run")
    package = json.loads((folder / "submission.json").read_text(encoding="utf-8"))
    required = {"team", "members", "repo", "commit", "run_command", "workflow", "trace", "mock_url"}
    if set(package) != required or any(not package[key] for key in required):
        raise ValueError("Incomplete final-case submission metadata")
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if len(manifest["agents"]) != 1:
        raise ValueError("Final case expects one workflow")
    for name, expected in manifest["sha256"].items():
        path = (folder / name).resolve()
        path.relative_to(folder)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Artifact changed after the run: {name}")
    for field, name in (("workflow", manifest["agents"][0]["file"]), ("trace", manifest["trace"])):
        if package[field] != (folder / name).relative_to(root).as_posix():
            raise ValueError(f"Wrong {field} for selected run")
    output = (root / output).resolve()
    output.relative_to(root)
    archive = (root / bundle).resolve() if bundle else None
    if archive:
        archive.relative_to(root)
        if archive.exists():
            raise FileExistsError(archive)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(package, indent=2, ensure_ascii=False))
    if archive:
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as zipped:
            zipped.write(output, "submission.json")
            for name in (package["workflow"], package["trace"], (folder / "console.log").relative_to(root).as_posix()):
                zipped.write(root / name, name)
    return output


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Package one final-case run or two website-format runs; no agent edits or API calls.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run", action="append", metavar="BRIEF=RUN_FOLDER")
    group.add_argument("--final-run", help="One completed run for the organizer's final case")
    parser.add_argument("--output", default="submission.json")
    parser.add_argument("--zip", help="Optional ZIP preserving repository-relative workflow/trace paths (final case only)")
    args = parser.parse_args()
    try:
        root = pathlib.Path(__file__).resolve().parent.parent
        if args.final_run:
            print(package_final_run(root, args.final_run, args.output, args.zip))
        else:
            if args.zip:
                raise ValueError("--zip is supported with --final-run")
            selected = dict(item.split("=", 1) for item in args.run)
            if len(selected) != len(args.run):
                raise ValueError("Duplicate brief labels")
            print(combine_submissions(root, selected, args.output))
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))
