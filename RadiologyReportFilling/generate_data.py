"""Generate sample request payloads for both endpoints, derived from xray_test_examples.json.

Writes one .json file per test case into ./sample_requests/ for easy Postman import.
"""
import json
import os
import sys


def main() -> int:
    """Read xray_test_examples.json and write per-case Postman payloads."""
    root = os.path.dirname(os.path.abspath(__file__))
    source = os.path.join(root, "xray_test_examples.json")
    if not os.path.isfile(source):
        print(f"ERROR: {source} not found.")
        return 1

    out_dir = os.path.join(root, "sample_requests")
    os.makedirs(out_dir, exist_ok=True)

    with open(source, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    for case in data.get("endpoint_1_report_correction", []):
        payload = case["inputs"]
        out = os.path.join(out_dir, f"correction_{case['id']}.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        print(f"wrote {out}")

    for case in data.get("endpoint_2_analysis_matching", []):
        payload = case["inputs"]
        out = os.path.join(out_dir, f"matching_{case['id']}.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        print(f"wrote {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
