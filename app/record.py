"""Append-only session log with a hash chain, and the sealed acknowledgement record built from it.

Each entry's hash covers the previous hash and the entry, so changing or removing any line afterwards breaks
every hash after it. The seal is the last hash. verify() recomputes the chain from the entries alone.
"""

import hashlib
import json
import time

GENESIS = "0" * 64


def _canon(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _link(prev: str, entry: dict) -> str:
    return hashlib.sha256((prev + _canon(entry)).encode("utf-8")).hexdigest()


class Ledger:
    def __init__(self) -> None:
        self.entries: list[dict] = []
        self.hashes: list[str] = []

    @property
    def head(self) -> str:
        return self.hashes[-1] if self.hashes else GENESIS

    def append(self, kind: str, **data) -> dict:
        entry = {"seq": len(self.entries), "t": round(time.time(), 3), "kind": kind, **data}
        self.entries.append(entry)
        self.hashes.append(_link(self.head, entry))
        return entry


def verify(entries: list[dict], seal: str) -> bool:
    h = GENESIS
    for entry in entries:
        h = _link(h, entry)
    return h == seal
