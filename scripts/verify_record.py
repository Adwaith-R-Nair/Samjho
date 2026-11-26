"""Check a downloaded Samjho record against its seal.

Usage: python scripts/verify_record.py samjho-record-<id>.json
Prints VALID if every log entry is intact and in order, else TAMPERED.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.record import verify  # noqa: E402


def main() -> int:
    record = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    ok = verify(record["entries"], record["seal_sha256"])
    print("VALID" if ok else "TAMPERED", record["seal_sha256"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
