"""Keep simulation reports associated with this run's saved workflow version."""
import json
import os
import pathlib
import time


def record_test(report):
    journal = os.environ.get("FREYA_RUN_LOG")
    if not journal:
        return
    journal = pathlib.Path(journal)
    saves = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    saved = next((row for row in reversed(saves) if row["agent_id"] == report["agent_id"]), None)
    if not saved:
        raise ValueError("Tested agent was not saved by this builder run")
    folder = journal.parent / "tests"
    folder.mkdir(exist_ok=True)
    path = folder / f"{report['agent_id']}-{time.time_ns()}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (journal.parent / "tests.jsonl").open("a", encoding="utf-8") as output:
        output.write(json.dumps({**saved, "report": str(path.relative_to(journal.parent)),
            "passed": report["passed"], "total": report["total"]}) + "\n")
