"""录入校验：在算之前先把错拦下来。

最常见的灾难不是算法错，是数据口径错——平铺半围没 ×2、衣长起量点搞错、
单位混了英寸。这些错算出来的结果看起来一样"专业"，但全错。
"""

from __future__ import annotations

from dataclasses import dataclass

from .ease_table import DRAPE, FIT_GOALS

# 各字段的"量级下限"：低于它几乎一定是半围或单位错
CIRC_MIN = {
    "bust": 55.0, "hem": 55.0, "waist": 45.0, "hip": 65.0,
    "thigh": 30.0, "sweep": 55.0, "neck": 25.0,
}


@dataclass
class Issue:
    level: str  # error / warn
    field: str
    message: str


def validate_garment(garment: dict, schema: dict) -> tuple[bool, list[Issue]]:
    issues: list[Issue] = []
    cat = garment.get("category")
    if cat not in schema["categories"]:
        return False, [Issue("error", "category", f"未知品类「{cat}」，可选：{'、'.join(schema['categories'])}")]
    spec = schema["categories"][cat]
    p = garment.get("params") or {}

    if garment.get("unit") not in (None, "cm"):
        issues.append(Issue("error", "unit", f"单位是「{garment['unit']}」，本系统只接受 cm"))

    fg = garment.get("fit_goal")
    if fg is not None and fg not in FIT_GOALS:
        issues.append(Issue(
            "warn", "fit_goal",
            f"目标效果「{fg}」不认识，可选：{'、'.join(FIT_GOALS)}；忽略后只出事实判定",
        ))

    dp = garment.get("drape")
    if dp is not None and dp not in DRAPE:
        issues.append(Issue(
            "warn", "drape",
            f"垂坠度「{dp}」不认识，可选：{'、'.join(DRAPE)}；按「常规」计会差一档松量底线",
        ))

    # 逐字段范围校验
    for name, fdef in spec["fields"].items():
        if name not in p:
            continue
        v = p[name]
        if not isinstance(v, (int, float)):
            issues.append(Issue("error", name, f"{fdef['label']} 不是数字：{v!r}"))
            continue
        if v <= 0:
            issues.append(Issue("error", name, f"{fdef['label']} 为 {v}，必须大于 0"))
            continue
        if not (fdef["min"] <= v <= fdef["max"]):
            issues.append(Issue(
                "error", name,
                f"{fdef['label']} {v}cm 超出合理范围 {fdef['min']}–{fdef['max']}cm",
            ))

    # 半围陷阱：胸围小于肩宽两倍，几乎一定是把平铺半围当整圈填了
    bust, shoulder = p.get("bust"), p.get("shoulder")
    if isinstance(bust, (int, float)) and isinstance(shoulder, (int, float)):
        if bust < shoulder * 2:
            hint = "（若详情页给的是平铺半围，请填 half: true 或直接填整圈）"
            issues.append(Issue(
                "warn" if garment.get("half") else "error",
                "bust",
                f"胸围 {bust}cm 小于肩宽 {shoulder}cm 的两倍，疑似把平铺半围当整圈填了{hint}",
            ))

    # 围度量级检查
    for name, low in CIRC_MIN.items():
        v = p.get(name)
        if isinstance(v, (int, float)) and v < low:
            issues.append(Issue(
                "warn", name,
                f"{name} {v}cm 偏小，确认是整圈周长而不是平铺半围",
            ))

    # 长度量级检查
    length = p.get(spec.get("length_field", ""))
    if isinstance(length, (int, float)) and isinstance(shoulder, (int, float)) and length < shoulder:
        issues.append(Issue(
            "error", spec["length_field"],
            f"衣长/裙长 {length}cm 小于肩宽 {shoulder}cm，量级明显不对（起量点写错了？）",
        ))

    # 硬参数缺失只警告，不算错——缺了照样能出降级结论
    for name in spec["hard"]:
        if p.get(name) is None:
            issues.append(Issue("warn", name, f"缺硬参数「{spec['fields'][name]['label']}」，对应落点结论会降级"))

    # 外套未指定内搭
    if spec.get("requires_inner_layer") and not garment.get("inner_layer"):
        issues.append(Issue("warn", "inner_layer", "外套未指定内搭档位，胸围结论会偏乐观"))

    ok = not any(i.level == "error" for i in issues)
    return ok, issues


def validate_body(body: dict) -> tuple[bool, list[Issue]]:
    issues: list[Issue] = []
    if not body.get("_filled"):
        issues.append(Issue("error", "_filled", "净体档案还没填（_filled 为 false）"))

    required = ["height", "bust", "waist", "hip", "shoulder"]
    for k in required:
        if body.get(k) is None:
            issues.append(Issue("warn", k, f"缺「{k}」，相关结论会降级"))

    h, w = body.get("height"), body.get("weight")
    if h and not (130 <= h <= 220):
        issues.append(Issue("error", "height", f"身高 {h}cm 超出合理范围"))
    if w and not (30 <= w <= 200):
        issues.append(Issue("error", "weight", f"体重 {w}kg 超出合理范围"))

    bust, shoulder = body.get("bust"), body.get("shoulder")
    if bust and shoulder and bust < shoulder * 2:
        issues.append(Issue("error", "bust", f"净体胸围 {bust} 小于肩宽 {shoulder} 的两倍，数值不对"))

    # 常识校验：胸围应当大于腰围
    waist = body.get("waist")
    if bust and waist and bust < waist:
        issues.append(Issue("warn", "bust", f"胸围 {bust} 小于腰围 {waist}，两项可能填反了"))

    ok = not any(i.level == "error" for i in issues)
    return ok, issues
