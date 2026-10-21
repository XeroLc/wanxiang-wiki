#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
万象客栈 · 设定集静态站生成器

职责边界（单向依赖）：
    世界观/*.md  ──┐
    tools/site.config.json ──> build_site.py ──> site/*.html + assets
    tools/assets/* ──┘

设计约束：
- 内容（Markdown）与展示（assets）解耦，生成器是唯一耦合点。
- 文档自动发现：新增 .md 自动进入站点；配置只负责排序与分组。
- 配置缺失、文档读取失败时降级而不是整体崩溃。
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import markdown

ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = ROOT / "世界观"
TOOLS_DIR = ROOT / "tools"
SITE_DIR = ROOT / "site"
ASSETS_SRC = TOOLS_DIR / "assets"
ASSETS_OUT = SITE_DIR / "assets"
CONFIG_PATH = TOOLS_DIR / "site.config.json"

MD_EXTENSIONS = [
    "tables",
    "fenced_code",
    "toc",
    "attr_list",
    "sane_lists",
    "nl2br",
]
MD_EXT_CONFIG = {"toc": {"toc_depth": "2-3", "permalink": False}}


# ---------------------------------------------------------------- utilities

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"[warn] 缺少配置 {CONFIG_PATH}，使用空配置")
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[error] 配置不是合法 JSON：{exc}")
        return {}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def first_h1(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def first_blockquote(text: str) -> str | None:
    """只取标题下方的导语引用，避免把正文深处的引用块当成副标题。"""
    lines = text.splitlines()
    seen_h1 = False
    for i, line in enumerate(lines[:40]):
        s = line.strip()
        if s.startswith("# "):
            seen_h1 = True
            continue
        if not seen_h1:
            continue
        if s.startswith("## "):
            return None
        if s.startswith(">"):
            value = s.lstrip(">").strip()
            if value and not value.startswith("版本") and "｜" not in value:
                return value
    return None


def plain_text(md: str) -> str:
    t = re.sub(r"```.*?```", " ", md, flags=re.S)
    t = re.sub(r"`[^`]*`", " ", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    # 表格分隔行
    t = re.sub(r"(?m)^\s*\|?[\s:|-]{4,}\|?\s*$", " ", t)
    # 表格行转为可读片段
    t = re.sub(
        r"(?m)^\s*\|(.+)\|\s*$",
        lambda m: " · " + m.group(1).replace("|", " · ") + " · ",
        t,
    )
    t = re.sub(r"[#>*_~|]", " ", t)
    t = re.sub(r"-{3,}", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def word_count(md: str) -> int:
    cjk = len(re.findall(r"[\u4e00-\u9fff]", md))
    latin = len(re.findall(r"[A-Za-z0-9]+", md))
    return cjk + latin


def description_of(md: str, fallback: str = "") -> str:
    subtitle = first_blockquote(md)
    if subtitle:
        return clean_subtitle(subtitle)
    body = strip_leading_meta(md)
    for block in re.split(r"\n\s*\n", body):
        s = block.strip()
        if not s or s.startswith("#") or s.startswith(">") or s.startswith("|"):
            continue
        if s.startswith("```") or s.startswith("---"):
            continue
        text = plain_text(s)
        if len(text) >= 20:
            return text[:110] + ("…" if len(text) > 110 else "")
    return fallback


def strip_leading_meta(md: str) -> str:
    """去掉首个 H1 与其后紧随的引用块，避免标题重复展示。"""
    lines = md.splitlines()
    out: list[str] = []
    skipped_h1 = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if not skipped_h1 and line.startswith("# "):
            skipped_h1 = True
            i += 1
            continue
        out.append(line)
        i += 1

    # 跳过开头的空行与引用块
    j = 0
    while j < len(out) and not out[j].strip():
        j += 1
    if j < len(out) and out[j].lstrip().startswith(">"):
        while j < len(out) and (out[j].lstrip().startswith(">") or not out[j].strip()):
            j += 1

    # 去掉标题与正文之间用于分隔的 ---
    while j < len(out) and (not out[j].strip() or out[j].strip() == "---"):
        j += 1
    return "\n".join(out[j:])


def clean_subtitle(text: str) -> str:
    value = plain_text(text)
    return re.sub(r"^(一句话|定位|用途|原则)[：:]\s*", "", value)


def slugify(stem: str, used: set[str]) -> str:
    base = re.sub(r"\s+", "-", stem.strip())
    slug = base
    n = 2
    while slug in used:
        slug = f"{base}-{n}"
        n += 1
    used.add(slug)
    return slug


def file_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()[:8]


# ---------------------------------------------------------------- content

def discover_documents(config: dict) -> tuple[list[dict], dict[str, str]]:
    """扫描全部 Markdown；返回文档列表与 相对路径 -> slug 映射。"""
    used: set[str] = set()
    docs: list[dict] = []
    by_rel: dict[str, str] = {}

    files = sorted(CONTENT_DIR.rglob("*.md"), key=lambda p: p.as_posix())
    for path in files:
        rel = path.relative_to(CONTENT_DIR).as_posix()
        text = read_text(path)
        title = first_h1(text) or path.stem
        slug = slugify(path.stem, used)
        by_rel[rel] = slug
        override = config.get("descriptions", {}).get(rel)
        docs.append(
            {
                "rel": rel,
                "slug": slug,
                "title": title,
                "subtitle": clean_subtitle(first_blockquote(text) or ""),
                "description": override or description_of(text, title),
                "text": text,
                "words": word_count(text),
                "updated": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d"),
                "group": "未分类",
                "group_id": "misc",
                "order": 10_000,
            }
        )
    return docs, by_rel


def apply_groups(docs: list[dict], config: dict) -> list[dict]:
    by_rel = {d["rel"]: d for d in docs}
    ordered: list[dict] = []
    seen: set[str] = set()

    for gi, group in enumerate(config.get("groups", [])):
        gid = group.get("id", f"g{gi}")
        gtitle = group.get("title", "未命名分组")
        for di, rel in enumerate(group.get("docs", [])):
            doc = by_rel.get(rel)
            if not doc:
                print(f"[warn] 配置中的文档不存在：{rel}")
                continue
            if rel in seen:
                continue
            doc["group"] = gtitle
            doc["group_id"] = gid
            doc["order"] = gi * 1000 + di
            ordered.append(doc)
            seen.add(rel)

    for doc in docs:
        if doc["rel"] not in seen:
            doc["order"] = 90_000 + len(ordered)
            ordered.append(doc)
            print(f"[info] 自动纳入未分组文档：{doc['rel']}")

    ordered.sort(key=lambda d: d["order"])
    return ordered


# ---------------------------------------------------------------- markdown

def render_markdown(md_text: str) -> tuple[str, list[dict]]:
    md = markdown.Markdown(extensions=MD_EXTENSIONS, extension_configs=MD_EXT_CONFIG)
    body = md.convert(md_text)
    # 宽表格统一加横向滚动容器，避免撑破正文
    body = re.sub(
        r"<table>(.*?)</table>",
        r'<div class="table-wrap"><table>\1</table></div>',
        body,
        flags=re.S,
    )
    toc = getattr(md, "toc_tokens", [])
    return body, toc


def rewrite_links(body: str, rel_to_slug: dict[str, str]) -> str:
    by_name: dict[str, str] = {}
    for rel, slug in rel_to_slug.items():
        by_name.setdefault(Path(rel).name, slug)

    def resolve(href: str) -> str | None:
        path, _, frag = href.partition("#")
        path = path.replace("\\", "/").lstrip("./")
        slug = rel_to_slug.get(path) or by_name.get(Path(path).name)
        if not slug:
            return None
        suffix = f"#{frag}" if frag else ""
        return f"{quote(slug)}.html{suffix}"

    def repl(match: re.Match[str]) -> str:
        href = match.group(1)
        if href.startswith(("http://", "https://", "mailto:", "#", "javascript:")):
            return f'href="{href}"'
        resolved = resolve(href)
        if resolved:
            return f'href="{resolved}" data-internal="1"'
        return f'href="{href}"'

    body = re.sub(r'href="([^"]+)"', repl, body)
    body = re.sub(
        r'<a href="(https?://[^"]+)"',
        r'<a href="\1" target="_blank" rel="noopener noreferrer"',
        body,
    )
    return body


def rewrite_assets(body: str, prefix: str) -> str:
    """把 Markdown 里的 assets/ 与 map.html 转成页面相对路径。"""
    body = re.sub(r'src="assets/([^"]+)"', rf'src="{prefix}assets/\1"', body)
    body = re.sub(r'href="assets/([^"]+)"', rf'href="{prefix}assets/\1"', body)
    body = re.sub(r'href="map\.html"', f'href="{prefix}map.html"', body)
    return body


def flatten_toc(tokens: list[dict]) -> list[dict]:
    out: list[dict] = []
    for token in tokens:
        if token.get("level") in (2, 3):
            out.append(token)
        out.extend(flatten_toc(token.get("children", [])))
    return out


def render_toc(tokens: list[dict]) -> str:
    items = flatten_toc(tokens)
    if not items:
        return '<p class="toc-empty">本篇没有分节</p>'
    parts = ['<ul class="toc-list">']
    for token in items:
        level = token.get("level", 2)
        parts.append(
            f'<li class="toc-item toc-l{level}">'
            f'<a href="#{token["id"]}">{html.escape(token["name"])}</a></li>'
        )
    parts.append("</ul>")
    return "".join(parts)


# ---------------------------------------------------------------- templates

def theme_bootstrap() -> str:
    return (
        "<script>(function(){try{var t=localStorage.getItem('wx-theme');"
        "if(!t){t=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}"
        "document.documentElement.setAttribute('data-theme',t);}catch(e){}})();</script>"
    )


def nav_html(docs: list[dict], active_slug: str | None, prefix: str, config: dict) -> str:
    colors = config.get("domainColors", {})
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for doc in docs:
        gid = doc["group_id"]
        if gid not in groups:
            groups[gid] = []
            order.append(gid)
        groups[gid].append(doc)

    titles = {g.get("id", f"g{i}"): g.get("title", "未命名") for i, g in enumerate(config.get("groups", []))}
    parts: list[str] = []
    for gid in order:
        parts.append(f'<div class="nav-group"><div class="nav-group-title">{html.escape(titles.get(gid, "未分类"))}</div>')
        for doc in groups[gid]:
            active = " is-active" if doc["slug"] == active_slug else ""
            dot = ""
            stem = Path(doc["rel"]).stem
            if stem in colors:
                dot = f'<span class="nav-dot" style="background:{colors[stem]}"></span>'
            num = re.match(r"\d+", stem)
            num_html = f'<span class="nav-num">{num.group(0)}</span>' if num else '<span class="nav-num">·</span>'
            parts.append(
                f'<a class="nav-item{active}" href="{prefix}{quote(doc["slug"])}.html">'
                f'{num_html}{dot}<span class="nav-label">{html.escape(doc["title"])}</span></a>'
            )
        parts.append("</div>")
    return "".join(parts)


def search_modal_html(root: str) -> str:
    return f"""
<div class="search-modal" id="searchModal" aria-hidden="true">
  <div class="search-backdrop" data-close-search></div>
  <div class="search-panel" role="dialog" aria-modal="true" aria-label="全文检索">
    <div class="search-box">
      <span class="search-icon" aria-hidden="true">⌕</span>
      <input id="searchInput" type="search" placeholder="搜索设定、域、人物、术语…" autocomplete="off" spellcheck="false">
      <button class="search-close" data-close-search aria-label="关闭">Esc</button>
    </div>
    <div class="search-results" id="searchResults" data-doc-root="{root}"></div>
    <div class="search-hint">↑ ↓ 选择 · Enter 打开 · / 唤起 · Esc 关闭</div>
  </div>
</div>
"""


def topbar_html(prefix: str) -> str:
    return f"""
<header class="topbar">
  <button class="icon-btn menu-btn" id="menuBtn" aria-label="打开目录">☰</button>
  <a class="brand" href="{prefix}index.html">
    <span class="brand-mark">萬</span>
    <span class="brand-text"><b>万象客栈</b><small>世界观设定集</small></span>
  </a>
  <div class="topbar-actions">
    <a class="map-link" href="{prefix}map.html">地图</a>
    <button class="search-trigger" id="searchTrigger">
      <span class="search-icon" aria-hidden="true">⌕</span>
      <span>搜索设定</span>
      <kbd>/</kbd>
    </button>
    <button class="icon-btn theme-btn" id="themeBtn" aria-label="切换主题" title="切换明暗">
      <span class="theme-sun">☀</span><span class="theme-moon">☾</span>
    </button>
  </div>
</header>
"""


def footer_html(doc_count: int) -> str:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f'<footer class="site-footer">共 {doc_count} 篇设定 · 构建于 {stamp} · '
        f'内容源为 Markdown，新增文档后重新构建即可自动出现</footer>'
    )


def page_shell(
    *,
    title: str,
    description: str,
    prefix: str,
    nav_prefix: str,
    body_class: str,
    content: str,
    docs: list[dict],
    active_slug: str | None,
    config: dict,
    css_ver: str,
    js_ver: str,
    doc_root: str,
) -> str:
    site_title = config.get("siteTitle", "设定集")
    return f"""<!doctype html>
<html lang="zh-CN" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · {html.escape(site_title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="stylesheet" href="{prefix}assets/style.css?v={css_ver}">
<link rel="icon" type="image/svg+xml" href="{prefix}assets/favicon.svg">
{theme_bootstrap()}
</head>
<body class="{body_class}" data-doc-root="{doc_root}">
<div class="reading-progress" id="readingProgress"></div>
{topbar_html(prefix)}
<div class="app">
  <aside class="sidebar" id="sidebar">
    <nav class="nav" aria-label="文档目录">
      {nav_html(docs, active_slug, nav_prefix, config)}
    </nav>
    <div class="sidebar-foot">
      <span class="dot-live"></span> {len(docs)} 篇 · 可持续扩展
    </div>
  </aside>
  <div class="sidebar-scrim" id="sidebarScrim"></div>
  {content}
</div>
{search_modal_html(doc_root)}
<script src="{prefix}assets/search-index.js"></script>
<script src="{prefix}assets/app.js?v={js_ver}"></script>
</body>
</html>"""


def render_index(docs: list[dict], config: dict, css_ver: str, js_ver: str) -> str:
    total_words = sum(d["words"] for d in docs)
    colors = config.get("domainColors", {})

    featured = [d for rel in config.get("featured", []) for d in docs if d["rel"] == rel]
    if not featured:
        featured = docs[:3]

    group_map: dict[str, list[dict]] = {}
    group_order: list[str] = []
    for doc in docs:
        if doc["group_id"] not in group_map:
            group_map[doc["group_id"]] = []
            group_order.append(doc["group_id"])
        group_map[doc["group_id"]].append(doc)

    group_titles = {
        g.get("id", f"g{i}"): (g.get("title", "未命名"), g.get("description", ""))
        for i, g in enumerate(config.get("groups", []))
    }

    cards: list[str] = []
    for gid in group_order:
        gtitle, gdesc = group_titles.get(gid, ("未分类", ""))
        items = group_map[gid]
        links = []
        for doc in items:
            stem = Path(doc["rel"]).stem
            dot = f'<span class="card-dot" style="background:{colors[stem]}"></span>' if stem in colors else ""
            links.append(
                f'<a class="doc-card" href="docs/{quote(doc["slug"])}.html">'
                f'<span class="doc-card-top">{dot}<span class="doc-card-title">{html.escape(doc["title"])}</span></span>'
                f'<span class="doc-card-desc">{html.escape(doc["description"])}</span>'
                f'<span class="doc-card-meta">{doc["words"]:,} 字</span></a>'
            )
        cards.append(
            f'<section class="group-block" id="{gid}">'
            f'<div class="group-head"><h2>{html.escape(gtitle)}</h2>'
            f'<p>{html.escape(gdesc)}</p><span class="group-count">{len(items)} 篇</span></div>'
            f'<div class="doc-grid">{"".join(links)}</div></section>'
        )

    feature_links = "".join(
        f'<a class="feature" href="docs/{quote(d["slug"])}.html">'
        f'<span class="feature-num">{i + 1:02d}</span>'
        f'<span class="feature-body"><b>{html.escape(d["title"])}</b>'
        f'<small>{html.escape(d["description"])}</small></span>'
        f'<span class="feature-arrow">→</span></a>'
        for i, d in enumerate(featured)
    )

    site_title = config.get("siteTitle", "设定集")
    subtitle = config.get("siteSubtitle", "设定集")
    site_desc = config.get("siteDescription", "")

    content = f"""
<main class="home">
  <section class="hero">
    <div class="hero-kicker">{html.escape(subtitle)}</div>
    <h1 class="hero-title">{html.escape(site_title)}</h1>
    <p class="hero-desc">{html.escape(site_desc)}</p>
    <div class="hero-stats">
      <div class="stat"><b>{len(docs)}</b><span>篇设定</span></div>
      <div class="stat"><b>{len(colors)}</b><span>个域</span></div>
      <div class="stat"><b>{total_words:,}</b><span>总字数</span></div>
    </div>
    <div class="hero-actions">
      <a class="btn primary" href="docs/{quote(featured[0]["slug"])}.html">开始阅读 →</a>
      <button class="btn ghost" id="searchTriggerHero">⌕ 检索全部设定 <kbd>/</kbd></button>
    </div>
  </section>

  <section class="featured-block">
    <h2 class="section-label">建议从这里开始</h2>
    <div class="feature-list">{feature_links}</div>
  </section>

  <section class="groups">{''.join(cards)}</section>

  {footer_html(len(docs))}
</main>
"""

    return page_shell(
        title="首页",
        description=site_desc,
        prefix="",
        nav_prefix="docs/",
        body_class="home-page",
        content=content,
        docs=docs,
        active_slug=None,
        config=config,
        css_ver=css_ver,
        js_ver=js_ver,
        doc_root="docs/",
    )


def render_doc(doc: dict, docs: list[dict], config: dict, rel_to_slug: dict[str, str], css_ver: str, js_ver: str) -> str:
    raw_body = strip_leading_meta(doc["text"])
    try:
        body_html, toc_tokens = render_markdown(raw_body)
        body_html = rewrite_links(body_html, rel_to_slug)
        body_html = rewrite_assets(body_html, "../")
    except Exception as exc:  # 单篇失败不拖垮整站
        print(f"[error] 渲染失败 {doc['rel']}：{exc}")
        body_html = (
            '<div class="render-error">本篇渲染失败，请检查 Markdown 语法。'
            f"<pre>{html.escape(str(exc))}</pre></div>"
        )
        toc_tokens = []

    idx = docs.index(doc)
    prev_doc = docs[idx - 1] if idx > 0 else None
    next_doc = docs[idx + 1] if idx < len(docs) - 1 else None

    def pager_link(item: dict | None, direction: str) -> str:
        if not item:
            return '<span class="pager-empty"></span>'
        arrow = "←" if direction == "prev" else "→"
        label = "上一篇" if direction == "prev" else "下一篇"
        content = (
            f'<span class="pager-label">{label}</span>'
            f'<span class="pager-title">{html.escape(item["title"])}</span>'
            if direction == "prev"
            else f'<span class="pager-label">{label}</span>'
            f'<span class="pager-title">{html.escape(item["title"])}</span>'
        )
        if direction == "prev":
            inner = f'<span class="pager-arrow">{arrow}</span>{content}'
        else:
            inner = f'{content}<span class="pager-arrow">{arrow}</span>'
        return f'<a class="pager-item {direction}" href="{quote(item["slug"])}.html">{inner}</a>'

    content = f"""
<main class="content">
  <nav class="breadcrumb" aria-label="位置">
    <a href="../index.html">设定集</a><span class="sep">/</span>
    <span>{html.escape(doc["group"])}</span><span class="sep">/</span>
    <span class="current">{html.escape(doc["title"])}</span>
  </nav>
  <article class="prose">
    <header class="doc-header">
      <p class="eyebrow">{html.escape(doc["group"])}</p>
      <h1>{html.escape(doc["title"])}</h1>
      {f'<p class="lead">{html.escape(doc["subtitle"])}</p>' if doc["subtitle"] else ''}
      <div class="doc-meta">
        <span>{doc["words"]:,} 字</span><span class="meta-dot">·</span>
        <span>更新 {doc["updated"]}</span><span class="meta-dot">·</span>
        <span>{html.escape(doc["rel"])}</span>
      </div>
    </header>
    <div class="markdown-body">{body_html}</div>
  </article>
  <nav class="pager" aria-label="翻页">
    {pager_link(prev_doc, "prev")}
    {pager_link(next_doc, "next")}
  </nav>
  {footer_html(len(docs))}
</main>
<aside class="toc" aria-label="本页目录">
  <div class="toc-title">本篇目录</div>
  {render_toc(toc_tokens)}
  <a class="toc-top" href="#top">↑ 回到顶部</a>
</aside>
"""

    return page_shell(
        title=doc["title"],
        description=doc["description"],
        prefix="../",
        nav_prefix="",
        body_class="doc-page",
        content=content,
        docs=docs,
        active_slug=doc["slug"],
        config=config,
        css_ver=css_ver,
        js_ver=js_ver,
        doc_root="",
    )


def render_search_index(docs: list[dict]) -> str:
    payload = []
    for doc in docs:
        body_plain = plain_text(doc["text"])[:5000]
        payload.append(
            {
                "title": doc["title"],
                "group": doc["group"],
                "url": f'{quote(doc["slug"])}.html',
                "subtitle": doc["subtitle"],
                "text": body_plain,
            }
        )
    return "window.__SEARCH_INDEX__ = " + json.dumps(payload, ensure_ascii=False) + ";\n"


# ---------------------------------------------------------------- build

def main() -> int:
    config = load_config()
    docs, rel_to_slug = discover_documents(config)
    docs = apply_groups(docs, config)

    try:
        import build_map
        build_map.write_svg()
        print("[ok] 地图 SVG 已更新")
    except Exception as exc:
        print(f"[warn] 地图生成失败，继续构建站点：{exc}")

    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    (SITE_DIR / "docs").mkdir(parents=True, exist_ok=True)
    ASSETS_OUT.mkdir(parents=True, exist_ok=True)

    if not ASSETS_SRC.exists():
        print(f"[error] 缺少资源目录 {ASSETS_SRC}")
        return 1
    for asset in ASSETS_SRC.iterdir():
        if asset.is_file():
            shutil.copy2(asset, ASSETS_OUT / asset.name)

    css_ver = file_hash(ASSETS_OUT / "style.css") if (ASSETS_OUT / "style.css").exists() else "0"
    js_ver = file_hash(ASSETS_OUT / "app.js") if (ASSETS_OUT / "app.js").exists() else "0"

    errors = 0
    for doc in docs:
        try:
            page = render_doc(doc, docs, config, rel_to_slug, css_ver, js_ver)
        except Exception as exc:
            errors += 1
            print(f"[error] 生成失败 {doc['rel']}：{exc}")
            continue
        out = SITE_DIR / "docs" / f"{doc['slug']}.html"
        out.write_text(page, encoding="utf-8")

    index_page = render_index(docs, config, css_ver, js_ver)
    (SITE_DIR / "index.html").write_text(index_page, encoding="utf-8")
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")
    (ASSETS_OUT / "search-index.js").write_text(render_search_index(docs), encoding="utf-8")

    manifest = {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "docCount": len(docs),
        "docs": [
            {
                "title": d["title"],
                "rel": d["rel"],
                "slug": d["slug"],
                "group": d["group"],
                "words": d["words"],
                "description": d["description"],
            }
            for d in docs
        ],
    }
    (SITE_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    try:
        import build_map
        build_map.write_page(SITE_DIR)
        print("[ok] 互动地图页已生成")
    except Exception as exc:
        print(f"[warn] 互动地图页生成失败：{exc}")

    print(f"[ok] 生成 {len(docs)} 篇文档 -> {SITE_DIR}")
    print(f"[ok] 入口：{SITE_DIR / 'index.html'}")
    if errors:
        print(f"[warn] {errors} 篇渲染失败")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
