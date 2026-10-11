"""Run case-supplied scenarios without the practice bank's sessions/ledger API.

python tools/run_scenarios.py AGENT_ID --cases out/scenarios.json --out results/scenarios.json
Each scenario: id, source, who, script, variables, checks (a list of requirements).
These are judge-based conversation checks, not the organizer's hidden score.
"""
import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import freya


def load_cases(path):
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("Expected a nonempty scenario list")
    ids = set()
    for case in cases:
        for field in ("id", "source", "who", "script", "variables", "checks"):
            if not case.get(field):
                raise ValueError(f"Missing {field} in scenario")
        if case["id"] in ids or not isinstance(case["variables"], dict) or not isinstance(case["checks"], list):
            raise ValueError("Unique IDs, variable objects and check lists required")
        ids.add(case["id"])
    return cases


def run(agent_id, cases, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    personas = [{"name": case["id"],
        "prompt": "Speak only as the customer, in the language required by this scenario. Do not reveal the evaluation criteria or coach the assistant.\n"
                  + case["who"] + "\n" + case["script"],
        "successCriteria": "Check the complete conversation and available tool calls/results. Do not count a claim as a completed action without tool success.\n"
                           + "\n".join(case["checks"]), "tags": ["builder-case-tests"]} for case in cases]
    created = freya.create_personas(personas)["personas"]
    if len(created) != len(cases):
        raise RuntimeError("Persona count mismatch")
    started = time.monotonic()
    sim, iteration, status = freya.run_simulation(agent_id, "case scenarios", {
        persona["id"]: case["variables"] for persona, case in zip(created, cases)})
    verdicts = {row["personaId"]: row for row in freya.get_iteration(sim, iteration)["runs"]}
    report = {"agent_id": agent_id, "simulation_id": sim, "iteration_id": iteration,
              "status": status, "seconds": time.monotonic() - started, "rows": [],
              "evaluation": "Conversation judge and captured tool transcript; not the organizer's hidden score"}
    for persona, case in zip(created, cases):
        verdict = verdicts.get(persona["id"], {})
        row = {"id": case["id"], "source": case["source"], "call_id": verdict.get("callId"),
               "pass": verdict.get("outcome") == "pass", "verdict": verdict,
               "failed": [] if verdict.get("outcome") == "pass" else [verdict.get("reason") or "No verdict"]}
        if row["call_id"]:
            try:
                row["call"] = freya.get_call(row["call_id"])
            except Exception as exc:
                row["pass"] = False
                row["failed"].append(f"Transcript unavailable: {exc}")
        else:
            row["pass"] = False
            row["failed"].append("No call ID; cannot verify transcript")
        report["rows"].append(row)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("PASS" if row["pass"] else "FAIL", case["id"], json.dumps(row["failed"], ensure_ascii=False), flush=True)
    report["passed"] = sum(row["pass"] for row in report["rows"])
    report["total"] = len(cases)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{report['passed']}/{len(cases)} passed; full reasons and transcripts: {output}", flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent_id")
    parser.add_argument("--cases", required=True, type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    args = parser.parse_args()
    run(args.agent_id, load_cases(args.cases), args.out)
