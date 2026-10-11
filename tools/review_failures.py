"""Collect each recorded failure without inventing causes from truncated judge reasons."""
import argparse
import json
import pathlib


def collect(folder):
    result = []
    for path in sorted(folder.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        batches = data.get("all_rows") or [data.get("rows", [])]
        if batches and isinstance(batches[0], dict):
            batches = [batches]
        for iteration, rows in enumerate(batches, 1):
            for row in rows:
                if row.get("pass") is False:
                    result.append({"result_file": str(path), "iteration": iteration, "scenario": row.get("id"),
                        "call_id": row.get("call_id"), "reasons": row.get("failed", []),
                        "tools": row.get("tools"), "transcript_available_in_result": bool(row.get("call")),
                        "review_status": "Requires source-policy and full transcript review before claiming a root cause"})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()
    result = collect(args.folder)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Collected {len(result)} failed runs in {args.out}")
