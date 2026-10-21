#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""地理总图生成器：map.data.json -> map.svg + 互动地图页。

数据与渲染分离：新增域 / 扩展槽只改 JSON，不改绘图代码。
"""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "tools" / "map.data.json"
ASSETS_SRC = ROOT / "tools" / "assets"

CANVAS = 1500
MARGIN = 150
GRID = 100

INK = "#2c261e"
INK_SOFT = "#5a5144"
PAPER = "#efe4cf"
PAPER_DARK = "#d9c9ad"
SEA = "#cfd9d2"
ACCENT = "#9c3f33"
GOLD = "#a9823f"

FONT = "'Noto Serif SC','Source Han Serif SC','Songti SC',SimSun,serif"


def load_data() -> dict:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def px(value: float) -> float:
    return MARGIN + value * GRID


def smooth_closed(points: list[list[float]]) -> str:
    pts = [(px(x), px(y)) for x, y in points]
    n = len(pts)
    d = f"M {pts[0][0]:.1f},{pts[0][1]:.1f} "
    for i in range(n):
        p0 = pts[(i - 1) % n]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += (
            f"C {c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} "
            f"{p2[0]:.1f},{p2[1]:.1f} "
        )
    return d + "Z"


def polyline(points: list[list[float]]) -> str:
    pts = [(px(x), px(y)) for x, y in points]
    d = f"M {pts[0][0]:.1f},{pts[0][1]:.1f} "
    for x, y in pts[1:]:
        d += f"L {x:.1f},{y:.1f} "
    return d.strip()


def text(x: float, y: float, value: str, size: int, *,
         fill: str = INK, weight: int = 400, anchor: str = "middle",
         opacity: float = 1.0, stroke: str | None = PAPER,
         stroke_width: int = 5, italic: bool = False, spacing: float = 0) -> str:
    style = f'font-family:{FONT};font-size:{size}px;font-weight:{weight};'
    if italic:
        style += "font-style:italic;"
    if spacing:
        style += f"letter-spacing:{spacing}px;"
    paint = ""
    if stroke:
        paint = f'stroke="{stroke}" stroke-width="{stroke_width}" paint-order="stroke fill" '
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'fill="{fill}" opacity="{opacity}" style="{style}" {paint}>'
        f"{html.escape(value)}</text>"
    )


def terrain_icon(kind: str, cx: float, cy: float) -> str:
    x, y = px(cx), px(cy)
    if kind == "peaks":
        return (
            f'<g transform="translate({x:.0f},{y:.0f})" opacity="0.30" '
            f'stroke="{INK}" fill="none" stroke-width="2">'
            '<path d="M-34,14 L-18,-14 L-2,14"/><path d="M-8,14 L8,-8 L24,14"/>'
            '<path d="M-44,14 L-44,20"/><path d="M30,14 L30,20"/></g>'
        )
    if kind == "chimneys":
        return (
            f'<g transform="translate({x:.0f},{y:.0f})" opacity="0.30" '
            f'stroke="{INK}" fill="none" stroke-width="2">'
            '<path d="M-26,16 L-26,-10 L-14,-10 L-14,16"/><path d="M-8,16 L-8,-4 L4,-4 L4,16"/>'
            '<path d="M14,16 L14,-16 L26,-16 L26,16"/>'
            '<path d="M-30,-14 q6,-6 12,0 q6,6 12,0"/><path d="M10,-20 q6,-6 12,0"/></g>'
        )
    if kind == "towers":
        return (
            f'<g transform="translate({x:.0f},{y:.0f})" opacity="0.30" '
            f'stroke="{INK}" fill="none" stroke-width="2">'
            '<path d="M-22,16 L-22,-18 L-10,-26 L2,-18 L2,16"/>'
            '<path d="M10,16 L10,-8 L20,-14 L30,-8 L30,16"/>'
            '<path d="M-18,4 L-2,4"/><path d="M14,2 L26,2"/></g>'
        )
    if kind == "city":
        return (
            f'<g transform="translate({x:.0f},{y:.0f})" opacity="0.28" '
            f'stroke="{INK}" fill="none" stroke-width="1.6">'
            '<rect x="-26" y="0" width="12" height="12"/><rect x="-10" y="-8" width="10" height="20"/>'
            '<rect x="4" y="2" width="14" height="10"/><rect x="20" y="-12" width="8" height="24"/>'
            '<path d="M-26,24 L32,24"/></g>'
        )
    if kind == "fog":
        return (
            f'<g transform="translate({x:.0f},{y:.0f})" opacity="0.30" '
            f'stroke="{INK}" fill="none" stroke-width="1.8" stroke-linecap="round">'
            '<path d="M-30,6 q10,-8 20,0 q10,8 20,0 q8,-6 18,0"/>'
            '<path d="M-22,-6 q8,-6 16,0 q8,6 16,0"/>'
            '<path d="M-26,-18 q9,-7 18,0 q9,7 18,0"/></g>'
        )
    if kind == "cracks":
        return (
            f'<g transform="translate({x:.0f},{y:.0f})" opacity="0.28" '
            f'stroke="{INK}" fill="none" stroke-width="2" stroke-linecap="round">'
            '<path d="M-34,6 L-14,-4 L2,10 L18,-6 L34,4"/>'
            '<path d="M-14,-4 L-8,-16"/><path d="M2,10 L6,22"/><path d="M18,-6 L22,-18"/></g>'
        )
    if kind == "clouds":
        return (
            f'<g transform="translate({x:.0f},{y:.0f})" opacity="0.28" '
            f'stroke="{INK}" fill="none" stroke-width="1.8" stroke-linecap="round">'
            '<path d="M-40,-22 q10,-8 20,0 q10,8 20,0"/><path d="M-30,28 q10,-8 20,0 q10,8 20,0"/>'
            '<path d="M28,-10 q8,-7 16,0"/></g>'
        )
    return ""


def render_domain(domain: dict) -> str:
    cx, cy = domain["center"]
    name = domain["name"]
    color = domain["color"]
    shape = smooth_closed(domain["shape"])
    small = name in ("畸城", "无言乡")

    parts = [
        f'<g class="domain" data-id="{html.escape(domain["id"])}" '
        f'data-name="{html.escape(name)}" data-sub="{html.escape(domain["sub"])}" '
        f'data-note="{html.escape(domain["note"])}" data-slug="{html.escape(domain["slug"])}" '
        f'data-cx="{cx}" data-cy="{cy}" tabindex="0" role="button" '
        f'aria-label="{html.escape(name)}">'
    ]
    if domain.get("layer") == "underground":
        parts.append(f'<path class="domain-shape" d="{shape}" fill="url(#hatch)" stroke="{INK}" stroke-width="2.4" stroke-dasharray="9 6" opacity="0.85"/>')
    elif domain.get("layer") == "fog":
        parts.append(f'<path class="domain-shape" d="{shape}" fill="{color}" fill-opacity="0.26" stroke="{INK_SOFT}" stroke-width="2" stroke-dasharray="4 5"/>')
    else:
        parts.append(f'<path class="domain-shape" d="{shape}" fill="{color}" fill-opacity="0.52" stroke="{INK_SOFT}" stroke-width="2.2"/>')

    for isle in domain.get("islets", []):
        ix, iy = isle[0], isle[1]
        r = isle[2] * GRID
        parts.append(
            f'<ellipse cx="{px(ix):.1f}" cy="{px(iy):.1f}" rx="{r*1.35:.1f}" ry="{r:.1f}" '
            f'fill="{color}" fill-opacity="0.35" stroke="{INK_SOFT}" stroke-width="1.4"/>'
        )

    icon_map = {
        "太荒": "peaks", "蒸枢": "chimneys", "云篆洲": "clouds", "铁枢": "city",
        "灰原": "cracks", "辉庭": "towers", "无言乡": "fog",
    }
    if name in icon_map:
        parts.append(terrain_icon(icon_map[name], cx, cy - (0.55 if small else 0.62)))

    label_size = 24 if small else 31
    parts.append(text(px(cx), px(cy) + (2 if small else 6), name, label_size, weight=700, spacing=2, stroke_width=7))
    parts.append(text(px(cx), px(cy) + (20 if small else 30), domain["sub"], 12 if small else 13, fill=INK_SOFT, stroke_width=4, spacing=1))
    parts.append("</g>")
    return "".join(parts)


def render_marker(marker: dict) -> str:
    x, y = px(marker["pos"][0]), px(marker["pos"][1])
    if marker["type"] == "inn":
        return (
            f'<g class="marker marker-inn" data-name="{html.escape(marker["name"])}" '
            f'data-sub="{html.escape(marker["sub"])}" data-note="{html.escape(marker["note"])}" '
            f'data-slug="" data-cx="{marker["pos"][0]}" data-cy="{marker["pos"][1]}" tabindex="0" role="button">'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="26" fill="none" stroke="{GOLD}" stroke-width="1.6" stroke-dasharray="4 4" opacity="0.9"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="17" fill="{ACCENT}" stroke="{PAPER}" stroke-width="2"/>'
            f'<path d="M{x-8:.1f},{y+2:.1f} L{x:.1f},{y-7:.1f} L{x+8:.1f},{y+2:.1f} L{x+8:.1f},{y+8:.1f} L{x-8:.1f},{y+8:.1f} Z" fill="{PAPER}" opacity="0.92"/>'
            f'<path d="M{x-2:.1f},{y+8:.1f} L{x-2:.1f},{y+1:.1f} L{x+2:.1f},{y+1:.1f} L{x+2:.1f},{y+8:.1f}" stroke="{ACCENT}" stroke-width="1.4" fill="none"/>'
            f'<path d="M{x+8:.1f},{y-16:.1f} L{x+8:.1f},{y-30:.1f} L{x+20:.1f},{y-25:.1f} L{x+8:.1f},{y-20:.1f}" fill="{ACCENT}" stroke="{ACCENT}" stroke-width="1.2"/>'
            f'<g transform="translate({x-34:.1f},{y-2:.1f})">'
            f'<rect x="-104" y="-20" width="100" height="30" rx="5" fill="{PAPER}" opacity="0.9"/>'
            + text(-98, -7, marker["name"], 15, weight=700, anchor="start", stroke=None)
            + text(-98, 7, marker["sub"], 10, fill=INK_SOFT, anchor="start", stroke=None)
            + "</g></g>"
        )
    # 无主墟
    star = []
    import math
    for i in range(16):
        r = 26 if i % 2 == 0 else 11
        a = math.pi / 2 + i * math.pi / 8
        star.append(f"{x + r * math.cos(a):.1f},{y - r * math.sin(a):.1f}")
    return (
        f'<g class="marker marker-void" data-name="{html.escape(marker["name"])}" '
        f'data-sub="{html.escape(marker["sub"])}" data-note="{html.escape(marker["note"])}" '
        f'data-slug="" data-cx="{marker["pos"][0]}" data-cy="{marker["pos"][1]}" tabindex="0" role="button">'
        f'<polygon points="{" ".join(star)}" fill="{INK}" opacity="0.8"/>'
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="40" fill="none" stroke="{INK}" stroke-width="1" opacity="0.45" stroke-dasharray="3 5"/>'
        + text(x, y + 58, marker["name"], 14, weight=700, fill=INK)
        + text(x, y + 73, marker["sub"], 10, fill=INK_SOFT, stroke_width=3)
        + "</g>"
    )


def render_svg(data: dict) -> str:
    domains = data.get("domains", [])
    cracks = data.get("cracks", [])
    routes = data.get("routes", [])
    markers = data.get("markers", [])
    slots = data.get("slots", [])

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CANVAS} {CANVAS}" '
        f'width="{CANVAS}" height="{CANVAS}" class="map-svg" role="img" '
        f'aria-label="万相界拼陆全图">'
    )

    # defs
    parts.append(f"""<defs>
  <radialGradient id="parchment" cx="48%" cy="42%" r="72%">
    <stop offset="0%" stop-color="#f6eeda"/>
    <stop offset="62%" stop-color="{PAPER}"/>
    <stop offset="100%" stop-color="{PAPER_DARK}"/>
  </radialGradient>
  <pattern id="noise" width="120" height="120" patternUnits="userSpaceOnUse">
    <filter id="noiseFilter"><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2"/>
      <feColorMatrix type="saturate" values="0"/></filter>
    <rect width="120" height="120" filter="url(#noiseFilter)" opacity="0.05"/>
  </pattern>
  <pattern id="sea" width="72" height="46" patternUnits="userSpaceOnUse">
    <path d="M0,18 q9,-7 18,0 q9,7 18,0 q9,-7 18,0 q9,7 18,0" fill="none" stroke="#7d948d" stroke-width="1" opacity="0.30"/>
    <path d="M-18,36 q9,-7 18,0 q9,7 18,0 q9,-7 18,0 q9,7 18,0" fill="none" stroke="#7d948d" stroke-width="1" opacity="0.20"/>
  </pattern>
  <pattern id="hatch" width="12" height="12" patternUnits="userSpaceOnUse" patternTransform="rotate(35)">
    <rect width="12" height="12" fill="#a03f63" fill-opacity="0.16"/>
    <line x1="0" y1="0" x2="0" y2="12" stroke="#7d2f4c" stroke-width="1.4" opacity="0.35"/>
  </pattern>
  <pattern id="stipple" width="18" height="18" patternUnits="userSpaceOnUse">
    <circle cx="3" cy="4" r="1" fill="{INK}" opacity="0.18"/>
    <circle cx="12" cy="13" r="1" fill="{INK}" opacity="0.12"/>
  </pattern>
  <filter id="softGlow" x="-60%" y="-60%" width="220%" height="220%">
    <feGaussianBlur stdDeviation="7"/>
  </filter>
  <filter id="shadow" x="-30%" y="-30%" width="160%" height="160%">
    <feDropShadow dx="0" dy="5" stdDeviation="6" flood-color="#3a2c18" flood-opacity="0.18"/>
  </filter>
</defs>""")

    # 底图
    parts.append(f'<rect width="{CANVAS}" height="{CANVAS}" fill="url(#parchment)"/>')
    parts.append(f'<rect width="{CANVAS}" height="{CANVAS}" fill="url(#noise)"/>')
    parts.append(f'<rect x="{MARGIN}" y="{MARGIN}" width="{GRID*12}" height="{GRID*12}" fill="{SEA}" opacity="0.55"/>')
    parts.append(f'<rect x="{MARGIN}" y="{MARGIN}" width="{GRID*12}" height="{GRID*12}" fill="url(#sea)"/>')

    # 经纬网格
    grid_lines = []
    for i in range(13):
        v = MARGIN + i * GRID
        grid_lines.append(f'<line x1="{v}" y1="{MARGIN}" x2="{v}" y2="{MARGIN+GRID*12}" stroke="{INK}" stroke-width="0.6" opacity="0.07"/>')
        grid_lines.append(f'<line x1="{MARGIN}" y1="{v}" x2="{MARGIN+GRID*12}" y2="{v}" stroke="{INK}" stroke-width="0.6" opacity="0.07"/>')
    parts.append('<g class="grid">' + "".join(grid_lines) + "</g>")

    # 未探明底纹
    parts.append(f'<rect x="{MARGIN}" y="{MARGIN}" width="{GRID*12}" height="{GRID*12}" fill="url(#stipple)" opacity="0.5"/>')

    # 裂缝层
    crack_parts = ['<g id="layer-cracks" class="layer layer-cracks">']
    for crack in cracks:
        d = polyline(crack["path"])
        crack_parts.append(
            f'<path d="{d}" fill="none" stroke="{ACCENT}" stroke-width="20" opacity="0.13" '
            f'stroke-linecap="round" filter="url(#softGlow)"/>'
        )
        crack_parts.append(
            f'<path d="{d}" fill="none" stroke="#241c15" stroke-width="4.2" opacity="0.78" '
            f'stroke-linecap="round" stroke-linejoin="round"/>'
        )
        crack_parts.append(
            f'<path d="{d}" fill="none" stroke="{ACCENT}" stroke-width="1.4" opacity="0.55" '
            f'stroke-linecap="round" stroke-dasharray="7 9"/>'
        )
    crack_parts.append("</g>")
    parts.append("".join(crack_parts))

    # 域层
    parts.append('<g id="layer-domains" class="layer layer-domains">')
    for domain in domains:
        parts.append(render_domain(domain))
    parts.append("</g>")

    # 交通层
    route_parts = ['<g id="layer-routes" class="layer layer-routes">']
    for route in routes:
        d = polyline(route["path"])
        t = route["type"]
        if t == "rail":
            route_parts.append(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="5" opacity="0.55" stroke-linecap="round"/>')
            route_parts.append(f'<path d="{d}" fill="none" stroke="{PAPER}" stroke-width="1.6" stroke-dasharray="3 7" opacity="0.95"/>')
        elif t == "air":
            route_parts.append(f'<path d="{d}" fill="none" stroke="#4f7a68" stroke-width="2.4" stroke-dasharray="10 7" opacity="0.7"/>')
        elif t == "sea":
            route_parts.append(f'<path d="{d}" fill="none" stroke="#3f6f93" stroke-width="3" stroke-dasharray="1 9" stroke-linecap="round" opacity="0.75"/>')
        elif t == "pipe":
            route_parts.append(f'<path d="{d}" fill="none" stroke="#a03f63" stroke-width="5" stroke-dasharray="7 5" opacity="0.55"/>')
            route_parts.append(f'<path d="{d}" fill="none" stroke="{PAPER}" stroke-width="1.2" stroke-dasharray="2 10" opacity="0.9"/>')
        else:
            route_parts.append(f'<path d="{d}" fill="none" stroke="{INK_SOFT}" stroke-width="1.6" stroke-dasharray="2 6" opacity="0.7"/>')
    route_parts.append("</g>")
    parts.append("".join(route_parts))

    # 扩展槽
    slot_parts = ['<g id="layer-slots" class="layer layer-slots">']
    for slot in slots:
        x, y = px(slot["pos"][0]), px(slot["pos"][1])
        slot_parts.append(
            f'<g class="slot" data-name="{html.escape(slot["name"])}" data-note="{html.escape(slot["note"])}" '
            f'data-sub="{html.escape(slot["genre"])}" data-cx="{slot["pos"][0]}" data-cy="{slot["pos"][1]}" tabindex="0">'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="30" fill="{PAPER}" fill-opacity="0.5" '
            f'stroke="{INK_SOFT}" stroke-width="1.4" stroke-dasharray="5 5" opacity="0.85"/>'
            f'<path d="M{x-9:.1f},{y:.1f} L{x+9:.1f},{y:.1f} M{x:.1f},{y-9:.1f} L{x:.1f},{y+9:.1f}" '
            f'stroke="{INK_SOFT}" stroke-width="1.2" opacity="0.7"/>'
            + text(x, y + 47, slot["name"], 14, fill=INK_SOFT, italic=True, stroke_width=5)
            + "</g>"
        )
    slot_parts.append("</g>")
    parts.append("".join(slot_parts))

    # 标记
    parts.append('<g id="layer-markers" class="layer layer-markers">')
    for marker in markers:
        parts.append(render_marker(marker))
    parts.append("</g>")

    # 图框
    parts.append(
        f'<rect x="{MARGIN-14}" y="{MARGIN-14}" width="{GRID*12+28}" height="{GRID*12+28}" '
        f'fill="none" stroke="{INK}" stroke-width="2" opacity="0.65"/>'
    )
    parts.append(
        f'<rect x="{MARGIN-6}" y="{MARGIN-6}" width="{GRID*12+12}" height="{GRID*12+12}" '
        f'fill="none" stroke="{GOLD}" stroke-width="1" opacity="0.75"/>'
    )
    for cx, cy in [(MARGIN-14, MARGIN-14), (MARGIN+GRID*12+14, MARGIN-14),
                   (MARGIN-14, MARGIN+GRID*12+14), (MARGIN+GRID*12+14, MARGIN+GRID*12+14)]:
        sx = 1 if cx < CANVAS / 2 else -1
        sy = 1 if cy < CANVAS / 2 else -1
        parts.append(
            f'<path d="M{cx+sx*20},{cy} L{cx},{cy} L{cx},{cy+sy*20}" '
            f'fill="none" stroke="{GOLD}" stroke-width="2"/>'
        )

    # 标题
    parts.append(text(MARGIN, 86, data.get("title", "万相界"), 44, weight=700, anchor="start", spacing=3, stroke_width=0))
    parts.append(text(MARGIN + 2, 116, data.get("subtitle", ""), 14, fill=INK_SOFT, anchor="start", spacing=2, stroke_width=0))
    parts.append(f'<line x1="{MARGIN}" y1="130" x2="{MARGIN+330}" y2="130" stroke="{GOLD}" stroke-width="1.4" opacity="0.8"/>')

    # 罗盘
    compass_x, compass_y = 1300, 200
    parts.append(f'<g class="compass" transform="translate({compass_x},{compass_y})" opacity="0.85">')
    parts.append(f'<circle r="42" fill="none" stroke="{INK}" stroke-width="1.2" opacity="0.5"/>')
    parts.append(f'<circle r="30" fill="none" stroke="{INK}" stroke-width="0.8" opacity="0.35"/>')
    parts.append(f'<path d="M0,-34 L8,-4 L0,0 L-8,-4 Z" fill="{ACCENT}"/>')
    parts.append(f'<path d="M0,34 L8,4 L0,0 L-8,4 Z" fill="{INK}" opacity="0.55"/>')
    parts.append(f'<path d="M-34,0 L-4,-8 L0,0 L-4,8 Z" fill="{INK}" opacity="0.35"/>')
    parts.append(f'<path d="M34,0 L4,-8 L0,0 L4,8 Z" fill="{INK}" opacity="0.35"/>')
    parts.append(text(0, -50, "北", 14, weight=700, stroke_width=4))
    parts.append("</g>")

    # 图例
    lx, ly = MARGIN, CANVAS - 52
    parts.append(f'<g class="legend" transform="translate({lx},{ly})">')
    parts.append(text(0, 0, "图例", 11, fill=INK_SOFT, anchor="start", spacing=3, stroke_width=0))
    items = [
        ("域界", f'<line x1="0" y1="0" x2="24" y2="0" stroke="{INK_SOFT}" stroke-width="2"/>'),
        ("错律带", f'<line x1="0" y1="0" x2="24" y2="0" stroke="{ACCENT}" stroke-width="3" stroke-dasharray="6 4"/>'),
        ("商路", f'<line x1="0" y1="0" x2="24" y2="0" stroke="{INK}" stroke-width="2.4" stroke-dasharray="2 5"/>'),
        ("扩展槽", f'<circle cx="12" cy="0" r="8" fill="none" stroke="{INK_SOFT}" stroke-width="1.2" stroke-dasharray="4 3"/>'),
    ]
    for i, (label, icon) in enumerate(items):
        col = i % 4
        gx = col * 170
        parts.append(f'<g transform="translate({gx},20)">{icon}{text(34, 4, label, 11.5, fill=INK_SOFT, anchor="start", stroke_width=3)}</g>')
    parts.append("</g>")

    # 比例尺
    sx, sy = CANVAS - 300, CANVAS - 44
    parts.append(f'<g class="scalebar" transform="translate({sx},{sy})">')
    parts.append(f'<line x1="0" y1="0" x2="200" y2="0" stroke="{INK}" stroke-width="2"/>')
    for x in (0, 100, 200):
        parts.append(f'<line x1="{x}" y1="-5" x2="{x}" y2="5" stroke="{INK}" stroke-width="2"/>')
    parts.append(text(100, -12, "200 里", 11, fill=INK_SOFT, stroke_width=3))
    parts.append("</g>")

    # 角落注记
    parts.append(text(CANVAS - MARGIN, MARGIN - 26, "未标注之处，即为无人去过", 11, fill=INK_SOFT, anchor="end", italic=True, stroke_width=0, opacity=0.75))

    parts.append("</svg>")
    return "".join(parts)


def write_svg() -> Path:
    data = load_data()
    svg = render_svg(data)
    ASSETS_SRC.mkdir(parents=True, exist_ok=True)
    out = ASSETS_SRC / "map.svg"
    out.write_text(svg, encoding="utf-8")
    return out


def file_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()[:8]


def write_page(site_dir: Path) -> Path:
    data = load_data()
    svg = render_svg(data)
    css_ver = file_hash(site_dir / "assets" / "map.css") if (site_dir / "assets" / "map.css").exists() else "0"
    js_ver = file_hash(site_dir / "assets" / "map.js") if (site_dir / "assets" / "map.js").exists() else "0"

    index_items = []
    for d in sorted(data.get("domains", []), key=lambda item: item.get("id", "")):
        index_items.append(
            f'<button class="mi-item" data-target="{html.escape(d["id"])}" '
            f'style="--dot:{d["color"]}"><span class="mi-dot"></span>'
            f'<span class="mi-name">{html.escape(d["name"])}</span>'
            f'<span class="mi-sub">{html.escape(d["sub"])}</span></button>'
        )

    page = f"""<!doctype html>
<html lang="zh-CN" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>万相界 · 拼陆全图</title>
<meta name="description" content="万象客栈世界观互动地图：八域、错律带、商路与扩展槽。">
<link rel="stylesheet" href="assets/style.css">
<link rel="stylesheet" href="assets/map.css?v={css_ver}">
<link rel="icon" type="image/svg+xml" href="assets/favicon.svg">
<script>(function(){{try{{var t=localStorage.getItem('wx-theme');if(!t){{t=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}}document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}}})();</script>
</head>
<body class="map-page">
<header class="topbar map-topbar">
  <a class="brand" href="index.html">
    <span class="brand-mark">萬</span>
    <span class="brand-text"><b>万象客栈</b><small>世界观设定集</small></span>
  </a>
  <div class="topbar-actions">
    <a class="icon-btn" href="docs/07_%E5%9C%B0%E7%90%86%E6%80%BB%E5%9B%BE.html" title="返回地理总图" aria-label="返回地理总图">←</a>
    <button class="icon-btn theme-btn" id="themeBtn" aria-label="切换主题" title="切换明暗">
      <span class="theme-sun">☀</span><span class="theme-moon">☾</span>
    </button>
  </div>
</header>

<div class="map-shell">
  <aside class="map-side">
    <div class="map-title">
      <p class="map-kicker">碎历 3600 年</p>
      <h1>拼陆全图</h1>
      <p class="map-desc">八域、五裂、商路，以及尚未探明的槽位。</p>
    </div>

    <div class="map-section">
      <div class="map-section-title">图层</div>
      <label class="map-toggle"><input type="checkbox" data-layer-toggle="cracks" checked><span>错律带</span></label>
      <label class="map-toggle"><input type="checkbox" data-layer-toggle="routes" checked><span>商路</span></label>
      <label class="map-toggle"><input type="checkbox" data-layer-toggle="slots" checked><span>扩展槽</span></label>
    </div>

    <div class="map-section">
      <div class="map-section-title">八域</div>
      <div class="map-index">
        {''.join(index_items)}
      </div>
    </div>

    <div class="map-hint">滚轮缩放 · 拖拽平移 · 点击查看</div>
    <a class="map-back" href="docs/07_%E5%9C%B0%E7%90%86%E6%80%BB%E5%9B%BE.html">← 返回地理总图</a>
  </aside>

  <main class="map-stage">
    <div class="map-viewport" id="mapViewport">
      <div class="map-canvas" id="mapCanvas">
        {svg}
      </div>
    </div>
    <div class="map-toolbar">
      <button id="zoomOut" aria-label="缩小">−</button>
      <button id="zoomReset" aria-label="复位">100%</button>
      <button id="zoomIn" aria-label="放大">＋</button>
    </div>
    <div class="map-card" id="mapCard">
      <p class="mc-kicker">点击地图</p>
      <h2>万相界</h2>
      <p class="mc-note">选择任意域、无籍驿或扩展槽，查看详情。</p>
    </div>
  </main>
</div>

<script src="assets/app.js"></script>
<script src="assets/map.js?v={js_ver}"></script>
</body>
</html>"""
    out = site_dir / "map.html"
    out.write_text(page, encoding="utf-8")
    return out


def main() -> None:
    svg = write_svg()
    print(f"[ok] 地图 SVG -> {svg}")


if __name__ == "__main__":
    main()
