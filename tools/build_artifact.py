"""Build the claude.ai artifact page from the standalone site.

site/index.html is the canonical, fully valid HTML document. The artifact host
wraps a page in its own <!DOCTYPE>/<html>/<head>/<body> skeleton (adding charset
and viewport), so the artifact copy keeps only the title, metadata, styles and
body content.

Usage: python3 tools/build_artifact.py   ->  out/siting/ui/index.html (+ data files)
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "site" / "index.html"
OUT = ROOT / "out" / "siting" / "ui"


def build() -> Path:
    html = SRC.read_text(encoding="utf-8")
    head = re.search(r"<head>(.*?)</head>", html, re.S).group(1)
    body = re.search(r"<body>(.*?)</body>", html, re.S).group(1)
    # the host adds charset + viewport; everything else in <head> is kept, title first
    head = re.sub(r'\s*<meta charset="utf-8">', "", head)
    head = re.sub(r'\s*<meta name="viewport"[^>]*>', "", head)
    page = head.strip() + "\n\n" + body.strip() + "\n"
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "index.html"
    out.write_text(page, encoding="utf-8")
    for data in (ROOT / "site").glob("data-*.json"):
        if not (OUT / data.name).exists() or (OUT / data.name).stat().st_mtime < data.stat().st_mtime:
            shutil.copy2(data, OUT / data.name)
    return out


if __name__ == "__main__":
    print("wrote", build())
