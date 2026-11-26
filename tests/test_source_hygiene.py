"""Guards against two mistakes that have already happened once in this build."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = [p for d in ("app", "web", "tests", "docs") for p in (ROOT / d).rglob("*") if p.suffix in {".py", ".js", ".html", ".css", ".md"}]


def test_no_control_characters_in_sources():
    # A scripted edit once turned the regex "\b" into a backspace byte, which silently disabled clause splitting.
    bad = [str(p.relative_to(ROOT)) for p in SOURCES if any(ord(c) < 32 and c not in "\n\r\t" for c in p.read_text(encoding="utf-8"))]
    assert bad == []


def test_no_em_dashes():
    bad = [str(p.relative_to(ROOT)) for p in SOURCES if chr(0x2014) in p.read_text(encoding="utf-8")]
    assert bad == []
