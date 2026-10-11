"""Check a deployed/local mock against every organizer response, including error statuses.

python verify_remote.py https://YOUR-WORKER.workers.dev
"""
import argparse
import concurrent.futures
import json
import pathlib
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent


def requests(fixtures):
    for customer in fixtures["customers"]:
        services = customer["services"]
        for service, records in services.items():
            if service in ("cards.list", "contact.email.get", "statement.pdf.send"):
                cards = services["cards.list"]["response"].get("data", {}).get("cards", [])
                card = cards[0]["cardNumber"] if cards else "not-used"
                balance = services.get("cards.balance", {}).get(card, {}).get("response", {}).get("data", {})
                data = {"customerNo": customer["customerNo"], "aiFlow": "CardOps", "intAddressInfoType": "E",
                        "cardNumber": card, "currencyType": "TL", "statementDate": balance.get("statementDate") or "01.01.2026",
                        "emailAddress": services.get("contact.email.get", {}).get("response", {}).get("data", {}).get("ibanEmail") or "test@example.com"}
                yield service, data, records
            else:
                for card, value in records.items():
                    if service in ("statement.week.decide", "statement.week.change"):
                        for week, entry in value.items():
                            day = services.get("statement.week.get", {}).get(card, {}).get("response", {}).get("data", {}).get("statementDay", 1)
                            yield service, {"cardNumber": card, "newStatementWeek": week, "statementDay": day}, entry
                    else:
                        yield service, {"cardNumber": card}, value


def check(base, row):
    service, data, expected = row
    started = time.monotonic()
    req = urllib.request.Request(base.rstrip("/") + "/voice/v1/" + service,
        data=json.dumps({"data": data, "call": {"lang": "tr"}}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (fixture verification)"}, method="POST")
    try:
        try:
            response = urllib.request.urlopen(req, timeout=max(40, expected.get("delaySeconds", 0) + 15))
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            status, body = response.code, json.load(response)
        if status != expected["http"] or body != expected["response"]:
            return {"service": service, "request": data, "error": "status/body mismatch", "actual_http": status}
        if time.monotonic() - started + 0.1 < expected.get("delaySeconds", 0):
            return {"service": service, "request": data, "error": "required delay missing"}
    except Exception as exc:
        return {"service": service, "request": data, "error": str(exc)}
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--fixtures", type=pathlib.Path, default=ROOT.parent / "cases/Build the Builder - Final Case/test-environment/test-customers.json")
    args = parser.parse_args()
    rows = list(requests(json.loads(args.fixtures.read_text(encoding="utf-8"))))
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        failures = [result for result in pool.map(lambda row: check(args.url, row), rows) if result]
    print(json.dumps({"total": len(rows), "passed": len(rows) - len(failures), "failures": failures}, indent=2, ensure_ascii=False))
    raise SystemExit(bool(failures))
