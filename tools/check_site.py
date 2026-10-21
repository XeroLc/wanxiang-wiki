#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""站点自检：链接完整性、页面结构、搜索索引一致性。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"

HREF_RE = re.compile(r'(?:href|src)="([^"]+)"')


def main() -> int:
    if not SITE.exists():
        print("[error] site/ 不存在，请先运行 tools/build_site.py")
        return 1

    pages = list(SITE.rglob("*.html"))
    broken: list[tuple[str, str]] = []
    empty_pages: list[str] = []

    for page in pages:
        raw = page.read_text(encoding="utf-8")
        if 'class="markdown-body"' in raw and len(raw) < 3000:
            empty_pages.append(page.name)
        for href in HREF_RE.findall(raw):
            if href.startswith(("http://", "https://", "mailto:", "javascript:", "#", "data:")):
                continue
            clean = unquote(urlparse(href).path)
            if not clean:
                continue
            target = (page.parent / clean).resolve()
            if not target.exists():
                broken.append((page.relative_to(SITE).as_posix(), href))

    manifest_path = SITE / "manifest.json"
    doc_count = 0
    if manifest_path.exists():
        doc_count = json.loads(manifest_path.read_text(encoding="utf-8")).get("docCount", 0)

    index_path = SITE / "assets" / "search-index.js"
    indexed = 0
    if index_path.exists():
        text = index_path.read_text(encoding="utf-8")
        try:
            indexed = len(json.loads(text.split("=", 1)[1].strip().rstrip(";")))
        except (IndexError, json.JSONDecodeError):
            print("[error] search-index.js 无法解析")

    print(f"[info] 页面 {len(pages)} 个 · 文档 {doc_count} 篇 · 索引 {indexed} 条")
    if empty_pages:
        print(f"[warn] 疑似空页：{', '.join(empty_pages)}")
    if indexed != doc_count:
        print(f"[warn] 搜索索引与文档数不一致：{indexed} != {doc_count}")

    if broken:
        print(f"[error] 断链 {len(broken)} 处：")
        for page, href in broken[:40]:
            print(f"    {page} -> {href}")
        return 1

    print("[ok] 链接完整，结构正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
