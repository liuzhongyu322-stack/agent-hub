"""有效松量计算：四笔账 + 两个修正项。

E      = 成衣围度 − 净体围度 − 厚度惩罚 − 内衣占量 − 内搭占量
E_可穿 = E + 弹性可借量

前者是"看得见的松量"，后者是"撑得住的余量"。两个都要，因为弹力能帮你穿进去，
但改变不了镜子里的样子。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .ease_table import (
    DRAPE,
    INNER_LAYER,
    STRETCH,
    THICKNESS,
    UNDERWEAR_BOTTOM,
    UNDERWEAR_BOTTOM_DEFAULT,
    UNDERWEAR_TOP,
    thickness_penalty,
)

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "data" / "garment-schema.json"

# 这些字段是"围度"，填了 half:true 就要 ×2
CIRC_FIELDS = {
    "bust", "hem", "cuff", "waist", "hip",
    "trouser_leg", "thigh", "sweep", "neck",
}


@dataclass
class EaseResult:
    part: str
    label: str
    body_value: float | None
    garment_value: float | None
    thickness: float = 0.0
    underwear: float = 0.0
    inner_layer: float = 0.0
    borrow: float = 0.0
    ease: float | None = None          # 看得见的松量
    ease_wearable: float | None = None  # 撑得住的余量
    confidence: str = "high"           # high / mid / low
    problems: list[str] = field(default_factory=list)


def load_schema() -> dict:
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def normalise_garment(garment: dict) -> tuple[dict, list[str]]:
    """把衣服记录规整成统一口径：围度一律整圈，缺失档位补默认值并记账。"""
    g = dict(garment)
    g["params"] = dict(garment.get("params") or {})
    flags: list[str] = []

    if g.get("half"):
        for k in list(g["params"]):
            if k in CIRC_FIELDS and isinstance(g["params"][k], (int, float)):
                g["params"][k] = round(g["params"][k] * 2, 1)
        flags.append("按平铺半围录入，围度已 ×2")

    if g.get("thickness") not in THICKNESS:
        g["thickness"] = "mid"
        flags.append("面料厚度未填，按「中」估算（围度惩罚 0.4cm）")

    if g.get("stretch") not in STRETCH:
        g["stretch"] = "none"
        flags.append("弹性未填，按「无弹」估算（偏保守）")

    if g.get("silhouette") not in ("slim", "regular", "relaxed", "oversize"):
        g["silhouette"] = "regular"

    if g.get("drape") not in DRAPE:
        g["drape"] = "regular"
        flags.append("垂坠度未填，按「常规」面料估算（挺括/垂坠会各差一档松量底线）")

    if g.get("category") == "outerwear" and g.get("inner_layer") not in INNER_LAYER:
        g["inner_layer"] = "none"
        flags.append("外套未指定内搭档位，按「裸穿」算，结论会偏乐观")

    return g, flags


def _allowances(garment: dict) -> tuple[float, float, float, dict]:
    """返回（厚度惩罚, 内衣占量, 内搭占量, 明细）。"""
    thick = thickness_penalty(garment["thickness"])
    cat = garment["category"]

    if cat == "top":
        uw_key = garment.get("underwear", "thin")
        uw_key = uw_key if uw_key in UNDERWEAR_TOP else "thin"
        underwear = UNDERWEAR_TOP[uw_key]["allow"]
    elif cat in ("bottom", "skirt"):
        uw_key = garment.get("underwear", UNDERWEAR_BOTTOM_DEFAULT)
        uw_key = uw_key if uw_key in UNDERWEAR_BOTTOM else UNDERWEAR_BOTTOM_DEFAULT
        underwear = UNDERWEAR_BOTTOM[uw_key]["allow"]
    else:
        uw_key = garment.get("underwear", "thin")
        uw_key = uw_key if uw_key in UNDERWEAR_TOP else "thin"
        underwear = UNDERWEAR_TOP[uw_key]["allow"]

    inner = 0.0
    if cat == "outerwear":
        inner = INNER_LAYER.get(garment.get("inner_layer", "none"), INNER_LAYER["none"])["allow"]

    detail = {
        "thickness_level": garment["thickness"],
        "thickness_label": THICKNESS[garment["thickness"]]["label"],
        "underwear_label": (UNDERWEAR_TOP if cat in ("top", "outerwear") else UNDERWEAR_BOTTOM)[uw_key]["label"],
        "inner_label": INNER_LAYER[garment.get("inner_layer", "none")]["label"] if cat == "outerwear" else None,
        "stretch_label": STRETCH[garment["stretch"]]["label"],
    }
    return thick, underwear, inner, detail


def derive_body(body: dict) -> tuple[dict, list[str]]:
    """补齐可以合理推算的净体字段，并如实记账（推算值一律标记为估算）。"""
    b = dict(body)
    notes: list[str] = []

    if b.get("hand") is None:
        if b.get("wrist"):
            b["hand"] = round(b["wrist"] * 1.28, 1)
            notes.append(f"掌围未测，按腕围 ×1.28 推算为 {b['hand']}cm（估算）")
        elif b.get("neck"):
            b["hand"] = round(b["neck"] * 0.60, 1)
            notes.append(f"掌围与腕围均未测，按颈围 ×0.60 推算为 {b['hand']}cm（估算，误差较大）")

    if b.get("waist_height") is None and b.get("height") and b.get("back_length"):
        b["waist_height"] = round(0.84 * b["height"] - b["back_length"], 1)
        notes.append(f"腰高未填，按 0.84×身高 − 背长 推算为 {b['waist_height']}cm（估算）")

    return b, notes


def compute(garment: dict, body: dict, schema: dict | None = None) -> tuple[list[EaseResult], dict]:
    """算出这件衣服在你的身体上，每个部位的松量。"""
    schema = schema or load_schema()
    cat = garment.get("category")
    if cat not in schema["categories"]:
        raise KeyError(f"未知品类：{cat}")

    thick, underwear, inner, detail = _allowances(garment)
    borrow = STRETCH[garment["stretch"]]["borrow"]
    results: list[EaseResult] = []

    for pair in schema["categories"][cat]["ease_pairs"]:
        part = pair["part"]
        gv = garment["params"].get(pair["garment"])
        bv = body.get(pair["body"])
        r = EaseResult(part=part, label=pair["label"], body_value=bv, garment_value=gv)
        r.thickness = thick
        r.underwear = underwear
        r.inner_layer = inner if pair.get("inner_layer") else 0.0
        r.borrow = borrow

        if gv is None:
            r.confidence = "low"
            r.problems.append(f"缺少成衣「{pair['garment']}」参数")
            results.append(r)
            continue
        if bv is None:
            r.confidence = "low"
            r.problems.append(f"缺少净体「{pair['body']}」数据")
            results.append(r)
            continue

        r.ease = round(gv - bv - thick - underwear - (inner if pair.get("inner_layer") else 0.0), 2)
        r.ease_wearable = round(r.ease + borrow, 2)
        results.append(r)

    return results, detail
