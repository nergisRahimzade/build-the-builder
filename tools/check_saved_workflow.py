"""Read and audit the deployed workflow without modifying it."""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import freya
from tools.audit_workflow import audit, compare_deployment

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slot")
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()
    state = json.loads(pathlib.Path(".freya-agents.json").read_text())[args.slot]
    remote = freya.api("GET", f"/api/v2/workflow/{state['workflow_id']}", workspaceId=freya.workspace_id())["workflow"]["workflow"]
    local = json.loads(pathlib.Path(f"out/{args.slot}.workflow.json").read_text())
    # The server fills agent_config itself; the source-only check does not apply here.
    report = {**state, "audit": audit({k: v for k, v in remote.items() if k != "agent_config"}), "differences": compare_deployment(local, remote), "workflow": remote}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "workflow"}, indent=2))
