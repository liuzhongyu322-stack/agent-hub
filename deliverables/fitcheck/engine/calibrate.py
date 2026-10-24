"""个人松量标定。

行业松量表是平均值，但松量偏好是私人的。你穿过、且知道合不合身的那几件衣服，
就是最好的标定数据——拿它的成衣参数反推「你的个人舒适松量」。

用法：在衣服记录里加 feedback 字段，例如
    "feedback": {"bust": "tight", "waist": "ok"}
取值 tight / ok / loose。攒够 5 条记录后，标定结果才会被采用。
"""

from __future__ import annotations

from statistics import median

from .ease_table import CIRC_RULES

MIN_SAMPLES_OVERALL = 5
MIN_SAMPLES_PER_PART = 2


def collect(garments: list[dict], body: dict) -> dict[str, list[tuple[float, str]]]:
    """从已穿过的衣服里提取（松量, 反馈）样本。"""
    from .ease import compute

    samples: dict[str, list[tuple[float, str]]] = {}
    for g in garments:
        fb = g.get("feedback") or {}
        if not fb:
            continue
        results, _ = compute(g, body)
        for r in results:
            part = r.part
            if part in fb and r.ease is not None:
                samples.setdefault(part, []).append((r.ease, fb[part]))
    return samples


def calibrate(samples: dict[str, list[tuple[float, str]]]) -> dict:
    total = sum(len(v) for v in samples.values())
    out = {
        "total_samples": total,
        "ready": total >= MIN_SAMPLES_OVERALL,
        "parts": {},
    }

    for part, rows in samples.items():
        if len(rows) < MIN_SAMPLES_PER_PART:
            out["parts"][part] = {"status": "样本不足", "n": len(rows)}
            continue

        tights = [e for e, f in rows if f == "tight"]
        oks = [e for e, f in rows if f == "ok"]
        default = CIRC_RULES[part].min_ease if part in CIRC_RULES else None

        if tights and oks:
            suggested = (max(tights) + min(oks)) / 2
            basis = f"偏紧样本最高 {max(tights):+.1f}，合身样本最低 {min(oks):+.1f}，取中值"
        elif oks:
            suggested = min(oks) - 1.0
            basis = f"无偏紧样本，按合身样本最低值 {min(oks):+.1f} 下浮 1cm"
        else:
            suggested = max(tights) + 2.0
            basis = f"全是偏紧样本，按最高值 {max(tights):+.1f} 上浮 2cm"
            oks = []

        out["parts"][part] = {
            "status": "已标定",
            "n": len(rows),
            "label": CIRC_RULES[part].label if part in CIRC_RULES else part,
            "suggested_min_ease": round(suggested, 1),
            "default_min_ease": default,
            "delta": round(suggested - default, 1) if default is not None else None,
            "median_ok_ease": round(median(oks), 1) if oks else None,
            "median_tight_ease": round(median(tights), 1) if tights else None,
            "basis": basis,
        }

    return out


def report(calib: dict) -> str:
    if not calib["ready"]:
        return (
            f"个人松量标定：样本 {calib['total_samples']}/{MIN_SAMPLES_OVERALL}，"
            f"还不够。继续录入穿过的衣服并在 feedback 里标注合身与否即可。"
        )
    lines = ["个人松量标定结果："]
    for part, d in calib["parts"].items():
        if d["status"] != "已标定":
            lines.append(f"  {part}：{d['status']}（{d['n']} 条）")
            continue
        delta = d["delta"]
        arrow = "比通用表更松" if delta and delta > 0 else ("比通用表更紧" if delta and delta < 0 else "与通用表一致")
        lines.append(
            f"  {d['label']}：建议必需松量 {d['suggested_min_ease']}cm"
            f"（通用表 {d['default_min_ease']}cm，{arrow} {delta:+.1f}）  依据：{d['basis']}"
        )
    return "\n".join(lines)
