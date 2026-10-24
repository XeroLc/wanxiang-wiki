#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
万象客栈 · 专名组件工具

把世界观里的专有名词做成"组件"：
- 每个专名一个稳定 ID（如 domain.yunzhuanzhou）
- 名称、别名、类别、归属、备注、旧名都记在 terms.yaml
- 改名时一次替换 Markdown / 地图数据 / 站点配置 / SVG 标签
- 自动生成《专名总表.md》

用法：
    python tools/terms.py list --scope 云篆洲
    python tools/terms.py contexts person.banjie
    python tools/terms.py stats
    python tools/terms.py check
    python tools/terms.py rename domain.yunzhuanzhou --to 苍梧洲 --dry-run
    python tools/terms.py rename domain.yunzhuanzhou --to 苍梧洲 --rename-files
    python tools/terms.py plan tools/rename-plan.example.yaml
    python tools/terms.py export-md

设计约束：
- 正文不写占位符，保持可读；改名靠工具做全局替换。
- 替换按"长词优先"，避免"云篆洲"被"云篆"截断。
- 默认只替换可替换别名；keep_aliases 里的词（如"九州"）不动。
- 改名是原子操作：先算完所有替换，再统一写入。
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.exit("需要 PyYAML：pip install pyyaml")

ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = ROOT / "世界观" / "00_名词组件库"
REGISTRY_PATH = LIB_DIR / "terms.yaml"
GLOSSARY_PATH = LIB_DIR / "专名总表.md"
WORLD_DIR = ROOT / "世界观"

# 这些文件里的专名也要跟着改
SIDE_FILES = [
    ROOT / "tools" / "map.data.json",
    ROOT / "tools" / "site.config.json",
    ROOT / "tools" / "assets" / "map.svg",
]

# 生成物，不参与替换，改名后重新生成
GENERATED_FILES = {GLOSSARY_PATH}

CATEGORY_ORDER = [
    "世界层", "域", "地理区", "政体", "势力", "地点", "人物",
    "物件", "生物", "制度", "事件", "术语", "其他",
]


def load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        sys.exit(f"找不到注册表：{REGISTRY_PATH}")
    with REGISTRY_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if "components" not in data:
        sys.exit("注册表缺少 components 字段")
    return data


def save_registry(data: dict[str, Any]) -> None:
    data["updated"] = today()
    with REGISTRY_PATH.open("w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(
            data,
            f,
            allow_unicode=True,
            sort_keys=False,
            width=120,
            default_flow_style=False,
        )


def today() -> str:
    from datetime import date
    return date.today().isoformat()


def components(data: dict[str, Any]) -> list[dict[str, Any]]:
    return data["components"]


def by_id(data: dict[str, Any], cid: str) -> dict[str, Any]:
    for c in components(data):
        if c["id"] == cid:
            return c
    sys.exit(f"找不到组件：{cid}")


def replaceable_terms(c: dict[str, Any]) -> list[str]:
    """返回该组件参与替换的所有写法（名称 + 可替换别名）。"""
    keep = set(c.get("keep_aliases") or [])
    out = [c["name"]]
    for a in c.get("aliases") or []:
        if a not in keep:
            out.append(a)
    return [t for t in out if t]


def all_replacements(data: dict[str, Any]) -> dict[str, str]:
    """所有组件的旧写法 -> 名称。用于 check/stats 时识别文本。"""
    m: dict[str, str] = {}
    for c in components(data):
        for t in replaceable_terms(c):
            m.setdefault(t, c["name"])
    return m


def md_files() -> list[Path]:
    return sorted(
        p for p in WORLD_DIR.rglob("*.md")
        if p not in GENERATED_FILES
    )


def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return p.read_text(encoding="utf-8-sig")


def count_occurrences(text: str, terms: list[str]) -> int:
    """按长词优先、不重叠地计数。"""
    if not terms:
        return 0
    pattern = re.compile("|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True)))
    return sum(1 for _ in pattern.finditer(text))


def build_replacer(mapping: dict[str, str]):
    """建一个长词优先的单遍替换器，避免链式替换。"""
    if not mapping:
        return lambda s: s
    keys = sorted(mapping, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(k) for k in keys))
    return lambda s: pattern.sub(lambda m: mapping[m.group(0)], s)


def cmd_list(args: argparse.Namespace) -> None:
    data = load_registry()
    rows = components(data)
    if args.category:
        rows = [c for c in rows if c.get("category") == args.category]
    if args.scope:
        rows = [c for c in rows if args.scope in (c.get("scope") or "")]
    if not rows:
        print("没有匹配的组件。")
        return
    print(f"{'ID':38} {'名称':12} {'类别':6} {'归属':10} 备注")
    print("-" * 100)
    for c in rows:
        print(
            f"{c['id']:38} {c['name']:12} {c.get('category',''):6} "
            f"{c.get('scope',''):10} {c.get('note','')}"
        )
    print(f"\n共 {len(rows)} 个组件。")


def cmd_stats(args: argparse.Namespace) -> None:
    data = load_registry()
    files = md_files()
    texts = {p: read_text(p) for p in files}
    rows = []
    for c in components(data):
        terms = replaceable_terms(c)
        total = 0
        hits = []
        for p, t in texts.items():
            n = count_occurrences(t, terms)
            if n:
                total += n
                hits.append((p, n))
        rows.append((total, c, hits))
    rows.sort(key=lambda x: (-x[0], x[1]["id"]))
    if args.missing:
        rows = [r for r in rows if r[0] == 0]
    print(f"{'次数':>5}  {'ID':38} 名称")
    print("-" * 80)
    for total, c, _ in rows:
        print(f"{total:5}  {c['id']:38} {c['name']}")
    print(f"\n共 {len(rows)} 个组件；扫描 {len(files)} 个 Markdown 文件。")
    if args.verbose:
        for total, c, hits in rows:
            if not hits:
                continue
            print(f"\n[{c['name']}] {c['id']}  {total} 次")
            for p, n in sorted(hits, key=lambda x: -x[1]):
                print(f"  {n:4}  {p.relative_to(ROOT)}")


def cmd_check(args: argparse.Namespace) -> None:
    data = load_registry()
    errors: list[str] = []
    warnings: list[str] = []

    ids = Counter(c["id"] for c in components(data))
    for cid, n in ids.items():
        if n > 1:
            errors.append(f"ID 重复：{cid} × {n}")

    names = Counter(c["name"] for c in components(data))
    for name, n in names.items():
        if n > 1:
            errors.append(f"名称重复：{name} × {n}")

    alias_owner: dict[str, str] = {}
    for c in components(data):
        for a in c.get("aliases") or []:
            if a in alias_owner and alias_owner[a] != c["id"]:
                warnings.append(f"别名冲突：'{a}' 同时属于 {alias_owner[a]} 和 {c['id']}")
            alias_owner.setdefault(a, c["id"])

    # 名称是否在正文中出现
    texts = {p: read_text(p) for p in md_files()}
    zero = []
    for c in components(data):
        terms = replaceable_terms(c)
        total = sum(count_occurrences(t, terms) for t in texts.values())
        if total == 0:
            zero.append(c)

    print("== 结构检查 ==")
    if errors:
        for e in errors:
            print("  [错误]", e)
    else:
        print("  [通过] ID / 名称无重复")
    if warnings:
        for w in warnings:
            print("  [警告]", w)
    else:
        print("  [通过] 别名无跨组件冲突")

    print("\n== 覆盖检查 ==")
    print(f"  组件 {len(components(data))} 个；Markdown {len(texts)} 个")
    if zero:
        print(f"  正文中未出现 {len(zero)} 个：")
        for c in zero:
            print(f"    - {c['id']} {c['name']}")
    else:
        print("  [通过] 所有组件都在正文中出现")

    if errors:
        sys.exit(1)


def path_matches(path: Path, patterns: list[str]) -> bool:
    import fnmatch
    rel = path.relative_to(ROOT).as_posix()
    return any(
        fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(path.name, pat)
        for pat in patterns
    )


def plan_mapping_for_path(
    path: Path,
    plans: list[dict[str, Any]],
    force: bool,
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for plan in plans:
        if plan["policy"] == "manual" and not force:
            continue
        if plan["only_in"] and not path_matches(path, plan["only_in"]):
            continue
        mapping.update(plan["term_map"])
    return mapping


def apply_rename(
    data: dict[str, Any],
    rename_map: dict[str, str],
    *,
    dry_run: bool,
    rename_files: bool,
    update_aliases: bool,
    force: bool = False,
) -> None:
    """rename_map: id -> new name。原子替换所有文件。"""
    plans: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    existing_names = {c["name"] for c in components(data)}
    for cid, new_name in rename_map.items():
        c = by_id(data, cid)
        old_name = c["name"]
        if old_name == new_name:
            continue
        other_names = existing_names - {old_name}
        if new_name in other_names:
            sys.exit(f"新名与已有组件重名：{new_name}")
        if new_name in (c.get("keep_aliases") or []):
            print(f"[警告] 新名 '{new_name}' 是该组件的 keep_alias；改名后会出现同名别名。")
        terms = replaceable_terms(c)
        new_aliases = []
        for a in c.get("aliases") or []:
            if a in (c.get("keep_aliases") or []):
                new_aliases.append(a)
                continue
            # 别名里如果含旧名，跟着换；否则默认保留
            if update_aliases and old_name in a:
                new_aliases.append(a.replace(old_name, new_name))
            else:
                new_aliases.append(a)
        term_map = {
            t: (new_name if t == old_name else t.replace(old_name, new_name))
            for t in terms
        }
        policy = c.get("replace_policy") or "auto"
        plan = {
            "component": c,
            "old": old_name,
            "new": new_name,
            "aliases": new_aliases,
            "policy": policy,
            "only_in": c.get("only_in") or [],
            "term_map": term_map,
        }
        plans.append(plan)
        if policy == "manual" and not force:
            skipped.append(plan)

    if not plans:
        print("没有需要改的名。")
        return

    # 2. 收集文件变更（每个文件用各自的映射，支持 only_in）
    changes: list[tuple[Path, str, str, dict[str, str]]] = []
    occ_by_plan: dict[int, int] = {id(p): 0 for p in plans}
    for p in md_files() + [x for x in SIDE_FILES if x.exists()]:
        old = read_text(p)
        mapping = plan_mapping_for_path(p, plans, force)
        if not mapping:
            continue
        new = build_replacer(mapping)(old)
        if new != old:
            changes.append((p, old, new, mapping))
            for plan in plans:
                if plan["policy"] == "manual" and not force:
                    continue
                if plan["only_in"] and not path_matches(p, plan["only_in"]):
                    continue
                occ_by_plan[id(plan)] += count_occurrences(old, list(plan["term_map"]))

    # 3. 打印预览
    print("== 替换计划 ==")
    for plan in plans:
        c = plan["component"]
        extra = ""
        if plan["policy"] == "manual" and not force:
            extra = "  [人工确认，跳过]"
        elif plan["only_in"]:
            extra = f"  [仅限：{', '.join(plan['only_in'])}]"
        print(f"  {plan['old']} -> {plan['new']}  ({c['id']}){extra}")
    if skipped:
        print("\n== 跳过的组件（普通词/歧义名）==")
        for plan in skipped:
            print(f"  {plan['old']}  ({plan['component']['id']})：加 --force 才会自动替换；先跑 contexts 看上下文")
    print("\n== 文件变更 ==")
    if not changes:
        print("  没有文件包含这些写法。")
    for p, old, new, mapping in changes:
        n = len(re.findall(
            "|".join(re.escape(k) for k in sorted(mapping, key=len, reverse=True)),
            old,
        ))
        print(f"  {n:4} 处  {p.relative_to(ROOT)}")

    file_renames = []
    if rename_files:
        for plan in plans:
            c = plan["component"]
            if c.get("category") == "域":
                for p in WORLD_DIR.rglob(f"{plan['old']}.md"):
                    file_renames.append((p, p.with_name(f"{plan['new']}.md")))
    if file_renames:
        print("\n== 文件改名 ==")
        for a, b in file_renames:
            print(f"  {a.relative_to(ROOT)} -> {b.relative_to(ROOT)}")

    if dry_run:
        print("\n[dry-run] 未写入。去掉 --dry-run 生效。")
        return

    # 4. 写文件
    for p, old, new, _ in changes:
        p.write_text(new, encoding="utf-8", newline="\n")
    for a, b in file_renames:
        if b.exists():
            sys.exit(f"目标文件已存在，停止：{b}")
        a.rename(b)

    # 5. 更新注册表：只更新真正有替换的组件；manual 未 force 的不动
    for plan in plans:
        if plan["policy"] == "manual" and not force:
            continue
        if occ_by_plan[id(plan)] == 0:
            continue
        c = plan["component"]
        c.setdefault("former_names", [])
        if plan["old"] not in c["former_names"]:
            c["former_names"].append(plan["old"])
        c["name"] = plan["new"]
        c["aliases"] = plan["aliases"]
    save_registry(data)

    # 6. 重新生成总表
    export_glossary(data)
    print("\n[完成] 文件、注册表、专名总表已更新。")
    print("建议：python tools/build_site.py && python tools/check_site.py")


def cmd_rename(args: argparse.Namespace) -> None:
    data = load_registry()
    apply_rename(
        data,
        {args.id: args.to},
        dry_run=args.dry_run,
        rename_files=args.rename_files,
        update_aliases=not args.keep_aliases,
        force=args.force,
    )


def cmd_plan(args: argparse.Namespace) -> None:
    data = load_registry()
    with Path(args.path).open(encoding="utf-8") as f:
        plan = yaml.safe_load(f) or {}
    renames = {}
    rename_files = False
    for item in plan.get("renames") or []:
        renames[item["id"]] = item["to"]
        rename_files = rename_files or bool(item.get("rename_files"))
    if not renames:
        sys.exit("计划里没有 renames")
    apply_rename(
        data,
        renames,
        dry_run=args.dry_run,
        rename_files=rename_files,
        update_aliases=True,
        force=args.force,
    )


def cmd_contexts(args: argparse.Namespace) -> None:
    data = load_registry()
    c = by_id(data, args.id)
    terms = replaceable_terms(c)
    pattern = re.compile("|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True)))
    n = 0
    for p in md_files():
        for i, line in enumerate(read_text(p).splitlines(), 1):
            if pattern.search(line):
                n += 1
                print(f"{p.relative_to(ROOT)}:{i}: {line.strip()}")
    print(f"\n共 {n} 行；组件 {c['id']} {c['name']}")


def display_note(c: dict[str, Any]) -> str:
    note = c.get("note", "")
    if c.get("replace_policy") == "manual":
        note += " ｜ 人工确认"
    if c.get("only_in"):
        note += " ｜ 仅限 " + "、".join(c["only_in"])
    return note


def export_glossary(data: dict[str, Any] | None = None) -> None:
    if data is None:
        data = load_registry()
    texts = {p: read_text(p) for p in md_files()}
    rows = []
    for c in components(data):
        terms = replaceable_terms(c)
        total = sum(count_occurrences(t, terms) for t in texts.values())
        rows.append((c, total))

    groups: dict[str, list[tuple[dict[str, Any], int]]] = defaultdict(list)
    for c, n in rows:
        groups[c.get("category") or "其他"].append((c, n))

    lines: list[str] = []
    lines.append("# 专名总表（名词组件库）")
    lines.append("")
    lines.append("> 版本：v1.0 ｜ 自动生成，请勿手改；改 `terms.yaml` 后运行 `python tools/terms.py export-md`")
    lines.append("> 用途：每个专有名词是一个组件，有稳定 ID；改名用 `python tools/terms.py rename <id> --to <新名>`。")
    lines.append("> 正文不写占位符；工具会同时改 Markdown、地图数据、站点配置和 SVG 标签。")
    lines.append("")
    lines.append(f"共 **{len(rows)}** 个组件。")
    lines.append("")
    lines.append("## 0. 怎么改名")
    lines.append("")
    lines.append("```bash")
    lines.append("# 看某个域的所有组件")
    lines.append("python tools/terms.py list --scope 云篆洲")
    lines.append("# 看一个组件的所有出现行（普通词/歧义名先看这个）")
    lines.append("python tools/terms.py contexts person.banjie")
    lines.append("# 预览改名")
    lines.append("python tools/terms.py rename domain.yunzhuanzhou --to 苍梧洲 --dry-run")
    lines.append("# 生效（同时改文件名、站点配置、地图）")
    lines.append("python tools/terms.py rename domain.yunzhuanzhou --to 苍梧洲 --rename-files")
    lines.append("# 批量改名")
    lines.append("python tools/terms.py plan tools/rename-plan.example.yaml")
    lines.append("```")
    lines.append("")
    lines.append("## 1. 组件表")
    lines.append("")

    for cat in CATEGORY_ORDER:
        if cat not in groups:
            continue
        lines.append(f"### {cat}")
        lines.append("")
        lines.append("| ID | 名称 | 别名 | 归属 | 出现 | 备注 |")
        lines.append("|---|---|---|---|---:|---|")
        for c, n in sorted(groups[cat], key=lambda x: (-x[1], x[0]["id"])):
            aliases = "、".join(c.get("aliases") or []) or "—"
            keep = c.get("keep_aliases") or []
            if keep:
                aliases += f"（不替换：{'、'.join(keep)}）"
            lines.append(
                f"| `{c['id']}` | **{c['name']}** | {aliases} | "
                f"{c.get('scope','—')} | {n} | {display_note(c)} |"
            )
        lines.append("")

    # 未归类
    other = [cat for cat in groups if cat not in CATEGORY_ORDER]
    for cat in sorted(other):
        lines.append(f"### {cat}")
        lines.append("")
        lines.append("| ID | 名称 | 别名 | 归属 | 出现 | 备注 |")
        lines.append("|---|---|---|---|---:|---|")
        for c, n in sorted(groups[cat], key=lambda x: (-x[1], x[0]["id"])):
            aliases = "、".join(c.get("aliases") or []) or "—"
            lines.append(
                f"| `{c['id']}` | **{c['name']}** | {aliases} | "
                f"{c.get('scope','—')} | {n} | {display_note(c)} |"
            )
        lines.append("")

    lines.append("## 2. 改名纪律")
    lines.append("")
    lines.append("1. **先查 ID，再改名。** 不要直接全局搜索替换；同名词可能是不同组件。")
    lines.append("2. **长词优先。** 工具已处理；手改时注意「云篆洲」与「云篆」、「骨山」与「骨山祖庭」。")
    lines.append("3. **别名分两类。** 可替换别名跟着改；`keep_aliases`（如「九州」）不动。")
    lines.append("4. **改完重建站点。** `python tools/build_site.py`；再跑 `python tools/check_site.py`。")
    lines.append("5. **旧名留档。** 工具会自动写入 `former_names`，方便回溯。")
    lines.append("")
    lines.append("## 3. 版本记录")
    lines.append("")
    lines.append("| 版本 | 日期 | 变更 |")
    lines.append("|---|---|---|")
    lines.append(f"| v1.0 | {today()} | 建立组件库；覆盖世界层、八域、云篆洲/太荒专名、政体总表政体 |")
    lines.append("")

    GLOSSARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    GLOSSARY_PATH.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"[ok] 已生成 {GLOSSARY_PATH.relative_to(ROOT)}（{len(rows)} 个组件）")


def cmd_export(args: argparse.Namespace) -> None:
    export_glossary()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="专名组件工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="列出组件")
    p.add_argument("--category")
    p.add_argument("--scope")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("stats", help="统计出现次数")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--missing", action="store_true")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("check", help="检查注册表与覆盖")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("rename", help="改一个专名")
    p.add_argument("id")
    p.add_argument("--to", required=True, dest="to")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--rename-files", action="store_true")
    p.add_argument("--keep-aliases", action="store_true")
    p.add_argument("--force", action="store_true", help="连人工确认的普通词/歧义名也替换")
    p.set_defaults(func=cmd_rename)

    p = sub.add_parser("plan", help="批量改名")
    p.add_argument("path")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("contexts", help="查看一个组件的所有出现行")
    p.add_argument("id")
    p.set_defaults(func=cmd_contexts)

    p = sub.add_parser("export-md", help="生成专名总表")
    p.set_defaults(func=cmd_export)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
