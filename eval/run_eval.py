"""Grade a fixed set of spoken answers and report how often the grader is right.

Each line of a phrase file is JSON: {"text": ..., "target": fact or null, "expect": {fact: status}, "source": ...}.
"source" says where the phrase came from: "synthetic" (written by us) or "field" (heard in a consented test).

The number that matters most is false passes: a fact graded green when the expected status is not green. That is
the one mistake Samjho must never make, because it would record that she understood when she did not.

Usage: python -m eval.run_eval [phrase files...]   (defaults to every eval/*.jsonl)
"""

import json
import sys
from collections import Counter
from pathlib import Path

from app.grade import grade
from app.loan import SAMPLE_LOAN

HERE = Path(__file__).resolve().parent


def load(paths: list[Path]) -> list[dict]:
    rows = []
    for p in paths:
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                row = json.loads(line)
                row["_where"] = f"{p.name}:{i}"
                rows.append(row)
    return rows


def run(rows: list[dict]) -> dict:
    checks = correct = false_pass = false_fail = 0
    misses = []
    by_source = Counter()
    for row in rows:
        got = grade(row["text"], SAMPLE_LOAN, row.get("target"))
        by_source[row.get("source", "synthetic")] += 1
        for fact, want in row["expect"].items():
            have = got[fact].status if fact in got else "grey"
            checks += 1
            if have == want:
                correct += 1
                continue
            if have == "green" and want != "green":
                false_pass += 1
            if want == "green" and have != "green":
                false_fail += 1
            misses.append(f'{row["_where"]}  {fact}: want {want}, got {have}  "{row["text"]}"')
    return {
        "phrases": len(rows),
        "by_source": dict(by_source),
        "checks": checks,
        "correct": correct,
        "accuracy": round(correct / checks, 4) if checks else None,
        "false_passes": false_pass,
        "false_fails": false_fail,
        "misses": misses,
    }


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv] or sorted(HERE.glob("*.jsonl"))
    report = run(load(paths))
    print(json.dumps({k: v for k, v in report.items() if k != "misses"}, ensure_ascii=False, indent=2))
    for m in report["misses"]:
        print("MISS", m)
    return 1 if report["false_passes"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
