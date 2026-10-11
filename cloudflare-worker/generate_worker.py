"""Embed the organizer's complete fixture table in a standalone Worker file."""
import argparse
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("fixtures", type=pathlib.Path)
args = parser.parse_args()
records = json.loads(args.fixtures.read_text(encoding="utf-8-sig"))
if not isinstance(records.get("customers"), list):
    parser.error("Expected customers array")
worker = "// Generated from organizer fixtures; do not edit individual records.\nconst RECORDS = "
worker += json.dumps(records, ensure_ascii=False, indent=2) + ";\n"
worker += (ROOT / "handler.mjs").read_text(encoding="utf-8")
worker += "\nexport default createWorker(RECORDS);\n"
(ROOT / "worker.js").write_text(worker, encoding="utf-8")
print(f"Embedded {len(records['customers'])} customers in {ROOT / 'worker.js'}")
