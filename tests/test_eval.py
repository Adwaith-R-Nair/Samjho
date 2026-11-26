from pathlib import Path

from eval.run_eval import load, run


def test_no_false_passes_on_any_phrase_set():
    rows = load(sorted((Path(__file__).resolve().parent.parent / "eval").glob("*.jsonl")))
    report = run(rows)
    assert report["phrases"] >= 50
    assert report["false_passes"] == 0, report["misses"]
    assert report["accuracy"] >= 0.95, report["misses"]
