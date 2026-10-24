#!/usr/bin/env python3
"""合身判定系统 v1 —— 量法 + 判定卡。

用法：
    python3 run.py                         # 跑 data/garments/ 下所有衣服
    python3 run.py demo-shirt-01           # 只跑一件（id 或文件名）
    python3 run.py --body data/body.json   # 指定净体档案
    python3 run.py --calibrate             # 看个人松量标定结果
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine import calibrate as calib_mod  # noqa: E402
from engine.ease import compute, derive_body, load_schema, normalise_garment  # noqa: E402
from engine.rules import judge_all, judge_goal  # noqa: E402
from engine.validate import validate_body, validate_garment  # noqa: E402
from render.card import render  # noqa: E402

ICON = {
    "穿不上": "×", "偏紧（勒）": "!", "偏紧": "!", "合身": "✓", "宽松": "·", "廓形": "·",
    "数据不足": "?", "顶死": "!", "正肩": "✓", "微紧（显肩线）": "✓",
    "修身（垂坠，不勒）": "✓", "微落肩": "·", "明显落肩": "·", "Oversize 落肩": "·",
}


def load_json(p: Path) -> dict:
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def print_issues(issues, prefix="  "):
    for i in issues:
        mark = "✗" if i.level == "error" else "!"
        print(f"{prefix}{mark} [{i.field}] {i.message}")


def analyse(garment: dict, body: dict, schema: dict, out_dir: Path,
            body_notes: list[str] | None = None, quiet=False) -> dict | None:
    g, flags = normalise_garment(garment)
    flags = list(body_notes or []) + flags
    ok, issues = validate_garment(g, schema)
    if not ok:
        print(f"\n■ {garment.get('name', garment.get('id'))} —— 录入有错，先修数据")
        print_issues(issues)
        return None

    results, detail = compute(g, body, schema)
    judgements, length, extras, overall, confidence = judge_all(g, body, results)
    goal_info = judge_goal(judgements, g.get("fit_goal"), g.get("drape", "regular"))

    out_path = render(g, body, judgements, length, extras, overall, confidence, flags,
                      out_dir / f"{g.get('id', 'garment')}.html", goal_info=goal_info)

    if not quiet:
        print(f"\n■ {g.get('name')}  [{g.get('size', '-')}]  {schema['categories'][g['category']]['label']}")
        print(f"  总体：{ICON.get(overall, '·')} {overall}    置信度：{confidence}")
        if goal_info:
            print(f"  目标：{goal_info[2]}")
            print(f"  你的描述：{g.get('vibe') or '（未填）'}")
        for j in judgements:
            e = f"{j.ease:+.1f}" if j.ease is not None else "  —"
            print(f"    {j.label:<8}{e:>7}cm   {j.verdict}")
        if length:
            print(f"    {length.name:<6} {length.verdict} —— {length.detail}")
        for ex in extras:
            print(f"    {ex.name:<6} {ex.verdict} —— {ex.detail}")
        warns = [i for i in issues if i.level == "warn"]
        if warns:
            print_issues(warns, "    ")
        print(f"  → {out_path.relative_to(ROOT)}")

    return {
        "id": g.get("id"), "name": g.get("name"), "category": g["category"],
        "overall": overall, "confidence": confidence,
        "judgements": judgements, "length": length, "extras": extras,
        "detail": detail, "issues": issues, "flags": flags,
    }


def main():
    ap = argparse.ArgumentParser(description="合身判定系统 v1")
    ap.add_argument("target", nargs="?", help="衣服 id 或文件名；省略则跑全部")
    ap.add_argument("--body", default="data/body.json")
    ap.add_argument("--out", default="out")
    ap.add_argument("--calibrate", action="store_true", help="输出个人松量标定结果")
    args = ap.parse_args()

    body = load_json(ROOT / args.body)
    ok, issues = validate_body(body)
    if not ok:
        print("■ 净体档案还不能用：")
        print_issues(issues)
        print(
            "\n请先填 data/body.json 里这 6 项（单位 cm）："
            "\n  height 身高 / bust 胸围 / waist 腰围 / hip 臀围 / shoulder 肩宽 / weight 体重"
            "\n填完把 _filled 改成 true。量法见 01-量法规范.html。"
            "\n想先看效果可以跑：python3 run.py --body data/body.sample.json"
        )
        return 1
    for i in issues:
        if i.level == "warn":
            print(f"! [{i.field}] {i.message}")

    body, body_notes = derive_body(body)
    for n in body_notes:
        print(f"! {n}")

    schema = load_schema()
    garment_dir = ROOT / "data" / "garments"
    files = sorted(garment_dir.glob("*.json"))
    if args.target:
        files = [f for f in files if args.target in f.stem]
        if not files:
            print(f"找不到匹配「{args.target}」的衣服记录")
            return 1

    out_dir = ROOT / args.out
    records = []
    for f in files:
        r = analyse(load_json(f), body, schema, out_dir, body_notes)
        if r:
            records.append(r)

    if args.calibrate:
        samples = calib_mod.collect([load_json(f) for f in files], body)
        print("\n" + calib_mod.report(calib_mod.calibrate(samples)))

    print(f"\n共 {len(records)} 件完成，判定卡在 {out_dir.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
