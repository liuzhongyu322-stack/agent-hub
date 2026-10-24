"""判定规则：松量分档、肩宽分档、长度落点、总体结论。

原则：每个部位独立判，不汇总成一个总分；总体结论取"最短板"。
一件衣服胸围穿不上，别处再合也没用——所以不允许用平均分掩盖硬伤。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .ease import EaseResult, load_schema
from .ease_table import (
    CIRC_RULES,
    DRAPE,
    FIT_GOALS,
    SHOULDER_BANDS,
    SHOULDER_MUSCLE_BANDS,
    SILHOUETTE,
    drape_thresholds,
)

# 身体部位高度的推算系数（缺少实测值时使用，并标记为估值）
COEF = {
    "neck_point": 0.840,  # 后颈点距地
    "hip": 0.480,         # 臀最丰满处距地
    "knee": 0.285,        # 膝盖骨中点距地
    "ankle": 0.040,       # 脚踝距地
    "head_neck": 0.160,   # 头顶到后颈点占身高
}
SHOULDER_DROP = 4.0  # 肩点比后颈点低约 4cm

SEVERITY = {
    "穿不上": 4,
    "偏紧（勒）": 3,
    "顶死": 3,
    "偏紧": 2,
    "数据不足": 2,
    "合身": 1,
    "正肩": 1,
    "微紧（显肩线）": 1,
    "修身（垂坠，不勒）": 1,
    "微落肩": 1,
    "明显落肩": 1,
    "Oversize 落肩": 1,
    "宽松": 0,
    "廓形": 0,
}
# 袖口偏紧不等于衣服不合身——有开襟或罗纹时几乎无影响，所以不让它主导总体结论
DEMOTED = {("cuff", "偏紧"), ("cuff", "偏紧（勒）")}


@dataclass
class Judgement:
    part: str
    label: str
    verdict: str
    detail: str
    ease: float | None = None
    confidence: str = "high"
    visual_note: str = ""
    problems: list[str] = field(default_factory=list)
    body_value: float | None = None
    garment_value: float | None = None
    breakdown: str = ""


@dataclass
class Landmark:
    name: str
    verdict: str
    detail: str
    position: float | None = None  # 0=头顶, 1=脚底，用于绘图
    confidence: str = "high"


# 下半身 / 上半身部位分组（用于偏好标注，不影响数值）
LOWER_PARTS = {"waist", "hip", "thigh", "trouser_leg"}
UPPER_PARTS = {"bust", "hem", "upper_arm"}

# 进目标判定的部位（软组织/混合类围度）。肩宽骨性、袖口看手掌，不进。
GOAL_PARTS = {"bust", "waist", "hip", "upper_arm", "thigh", "hem", "trouser_leg"}


# 目标区容差：软尺本身有 ±1cm 噪声，贴着目标区边缘 ±1cm 内不算脱靶
GOAL_TOL = 1.0


def judge_goal(judgements: list[Judgement], fit_goal: str | None,
               drape: str = "regular") -> tuple[int, int, str] | None:
    """对照用户指定的目标效果（fit_goal），回答"达没达到"。

    返回 (达标部位数, 参与判定部位数, 一句话)；没指定目标返回 None。
    事实层（合身/宽松分档）不动，这一层只回答"和你想要的效果差多远"。
    目标区同样按垂坠度平移：垂坠面料的"合身"本来就比挺括面料低 2-3cm。
    """
    goal = FIT_GOALS.get(fit_goal) if fit_goal else None
    if goal is None:
        return None
    d = DRAPE.get(drape, DRAPE["regular"])
    lo = goal["band"][0] + d["min_shift"]
    hi = goal["band"][1] + d["loose_shift"]
    ok: list[Judgement] = []
    tighter: list[tuple[Judgement, float | str]] = []
    looser: list[tuple[Judgement, float]] = []
    for j in judgements:
        if j.part not in GOAL_PARTS or j.ease is None:
            continue
        if j.verdict == "穿不上":
            tighter.append((j, "穿不上"))
        elif j.ease < lo - GOAL_TOL:
            tighter.append((j, lo - j.ease))
        elif j.ease > hi + GOAL_TOL:
            looser.append((j, j.ease - hi))
        else:
            ok.append(j)

    n = len(ok) + len(tighter) + len(looser)
    if n == 0:
        return 0, 0, f"目标「{goal['label']}」→ 没有可比对的围度数据"

    if any(t[1] == "穿不上" for t in tighter):
        names = "、".join(j.label for j, t in tighter if t == "穿不上")
        text = f"未达目标：{names}根本穿不上，别谈效果"
    elif not tighter and not looser:
        text = f"达标：{n} 个部位全部落在「{goal['label']}」目标区"
    else:
        bits = [f"{j.label}比目标紧 {d:.1f}cm" for j, d in tighter if d != "穿不上"]
        bits += [f"{j.label}比目标松 {d:.1f}cm" for j, d in looser]
        head = "部分达标" if ok else "未达目标"
        text = f"{head}：{'；'.join(bits)}" + (f"；{len(ok)} 个部位达标" if ok else "")
    return len(ok), n, f"你要求的效果「{goal['label']}」→ {text}"


def judge_circumference(r: EaseResult, pref: dict | None = None,
                        drape: str = "regular") -> Judgement:
    """围度类部位的松量判定。

    pref 是个人偏好、drape 是面料垂坠度，两者都只改"门槛"或"注解"，不改松量本身。
    """
    rule = CIRC_RULES.get(r.part)
    if rule is None:
        return Judgement(r.part, r.label, "数据不足", "该部位暂未定义判定规则", r.ease, "low")

    if r.ease is None:
        return Judgement(
            r.part, r.label, "数据不足",
            "；".join(r.problems) or "参数缺失",
            None, "low", problems=list(r.problems),
        )

    e, ew = r.ease, r.ease_wearable
    min_ease, compress, loose_at = drape_thresholds(rule, drape)
    fluid = drape == "fluid"

    if ew < rule.min_wearable:
        verdict = "穿不上"
        detail = f"可穿余量 {ew:+.1f}cm，低于下限 {rule.min_wearable:+.1f}cm。{rule.note}"
    elif e < min_ease - compress:
        verdict = "偏紧（勒）"
        detail = (
            f"松量 {e:+.1f}cm，比必需值 {min_ease:.1f}cm 少了 {min_ease - e:.1f}cm，"
            f"超出自带可压缩量 {compress:.1f}cm。{rule.note}"
        )
    elif e < min_ease:
        if fluid and e >= 0:
            verdict = "修身（垂坠，不勒）"
            detail = (
                f"松量 {e:+.1f}cm，低于挺括面料的必需值 {min_ease:.1f}cm，"
                f"但垂坠面料会顺着身体走，不顶不勒——实穿是修身档。{rule.note}"
            )
        else:
            verdict = "偏紧"
            detail = (
                f"松量 {e:+.1f}cm，低于必需值 {min_ease:.1f}cm，"
                f"靠压缩 {min_ease - e:.1f}cm 勉强撑住。{rule.note}"
            )
    elif e < loose_at:
        verdict = "合身"
        detail = f"松量 {e:+.1f}cm，落在 {min_ease:.1f}–{loose_at:.0f}cm 的合身区。"
    elif e < loose_at + 8:
        verdict = "宽松"
        detail = f"松量 {e:+.1f}cm，超过宽松线 {loose_at:.0f}cm。"
    else:
        verdict = "廓形"
        detail = f"松量 {e:+.1f}cm，属于廓形/oversize 的量。"

    # 观感提示：围度 → 单侧视觉宽度
    visual = f"单侧视觉余量约 {e / (2 * math.pi):.1f}cm"
    if 0 <= e < 6:
        visual += "，看着接近贴身"
    elif e >= 10:
        visual += "，看得出宽松"
    if drape in DRAPE and drape != "structured":
        visual += f"；面料按「{DRAPE[drape]['label']}」计，必需松量取 {min_ease:.1f}cm（挺括标准 {rule.min_ease:.0f}cm）"

    # 偏好标注：宽松本身是事实，是否算"问题"由偏好决定
    pref = pref or {}
    if verdict in ("宽松", "廓形"):
        if r.part in LOWER_PARTS and pref.get("lower") == "relaxed":
            detail += "（在你的偏好内：下半身宽松可接受）"
        elif r.part in UPPER_PARTS and pref.get("upper") == "fitted":
            detail += "（上半身你偏好合身，这件偏松）"

    conf = r.confidence
    if r.borrow > 0 and verdict in ("偏紧", "偏紧（勒）"):
        visual += f"；本件弹性可借 {r.borrow:.1f}cm，穿得进但不等于好看"

    pieces = [
        f"成衣 {r.garment_value:.0f}",
        f"净体 {r.body_value:.0f}",
        f"厚度 −{r.thickness:.1f}",
        f"内衣 −{r.underwear:.1f}",
    ]
    if r.inner_layer:
        pieces.append(f"内搭 −{r.inner_layer:.1f}")
    breakdown = " · ".join(pieces) + f" → 净松量 {e:+.1f}"

    return Judgement(
        r.part, r.label, verdict, detail, e, conf, visual, list(r.problems),
        r.body_value, r.garment_value, breakdown,
    )


def judge_shoulder(
    garment_shoulder: float | None,
    body_shoulder: float | None,
    pref: str | None = None,
) -> Judgement:
    if garment_shoulder is None or body_shoulder is None:
        return Judgement("shoulder", "肩宽", "数据不足", "缺肩宽数据", None, "low")
    diff = garment_shoulder - body_shoulder
    bands = SHOULDER_MUSCLE_BANDS if pref == "muscle_fit" else SHOULDER_BANDS
    for lo, hi, label, reason in bands:
        if lo <= diff < hi:
            note = "肩宽是骨性指标，可压缩量为 0，差 1cm 就是差 1cm"
            if pref == "muscle_fit" and label == "微紧（显肩线）":
                note = "按你的偏好（肩部微紧显健身痕迹）判定；不启偏好时这一档是「顶死」"
            if pref == "muscle_fit" and diff <= -3.5 and label == "顶死":
                note = (
                    "肩缝是缝在肩峰骨点附近的，不是缝在三角肌最鼓处。"
                    "若净体 50 是贴着肌肉量的，骨点直线宽通常小 2–4cm，"
                    "按骨点算真实肩差会小 2–4cm——这一条值得复核一次"
                )
            return Judgement(
                "shoulder", "肩宽", label,
                f"差 {diff:+.1f}cm。{reason}",
                round(diff, 1), "high",
                note,
                [], body_shoulder, garment_shoulder,
                f"成衣 {garment_shoulder:.0f} · 净体 {body_shoulder:.0f} → 差 {diff:+.1f}",
            )
    return Judgement("shoulder", "肩宽", "数据不足", "超出分档范围", round(diff, 1), "low")


def _heights(body: dict) -> dict:
    h = body.get("height")
    if not h:
        return {}
    neck = 0.84 * h
    waist = body.get("waist_height") or (neck - (body.get("back_length") or 0.24 * h))
    return {
        "neck_point": round(neck, 1),
        "waist": round(waist, 1),
        "hip": round(COEF["hip"] * h, 1),
        "knee": round(COEF["knee"] * h, 1),
        "ankle": round(COEF["ankle"] * h, 1),
        "height": h,
    }


def length_landmark(garment: dict, body: dict) -> Landmark:
    """衣长 / 裙长 / 裤内长的落点。"""
    cat = garment["category"]
    p = garment["params"]
    hs = _heights(body)
    if not hs:
        return Landmark("长度落点", "数据不足", "缺身高，无法换算落点", None, "low")

    H = hs["height"]
    if cat in ("top", "outerwear"):
        L = p.get("length")
        if L is None:
            return Landmark("衣长落点", "数据不足", "缺衣长参数，不编造落点", None, "low")
        start = garment.get("length_from", "back_neck")
        base = hs["neck_point"] - (SHOULDER_DROP if start == "shoulder_point" else 0.0)
        hem = base - L
        pos = 1 - hem / H
        if hem > hs["waist"] + 3:
            v, d = "短款（露腰）", f"下摆在腰线上方 {hem - hs['waist']:.0f}cm"
        elif abs(hem - hs["waist"]) <= 3:
            v, d = "齐腰", "下摆与腰线基本齐平"
        elif hem > hs["hip"] + 6:
            v, d = "盖胯上部", f"下摆在腰下 {hs['waist'] - hem:.0f}cm，还没到臀最丰满处"
        elif abs(hem - hs["hip"]) <= 6:
            v, d = "齐胯", "下摆落在臀最丰满处，最不显胯的一档"
        elif hem > hs["knee"] + 10:
            v, d = "盖臀/大腿中", f"下摆在臀下 {hs['hip'] - hem:.0f}cm"
        else:
            v, d = "长款（过膝）", f"下摆在膝下 {hs['knee'] - hem:.0f}cm"
        return Landmark("衣长落点", v, f"{d}（下摆距地约 {hem:.0f}cm，占身高 {pos * 100:.0f}%）", round(pos, 3))

    if cat == "skirt":
        L = p.get("length")
        if L is None:
            return Landmark("裙长落点", "数据不足", "缺裙长参数", None, "low")
        hem = hs["waist"] - L
        pos = 1 - hem / H
        k, a = hs["knee"], hs["ankle"]
        if hem > k + 20:
            v = "膝上（短裙）"
        elif hem > k + 5:
            v = "膝上"
        elif hem >= k - 5:
            v = "及膝"
        elif hem > k - 25:
            v = "膝下 / 小腿中"
        elif hem > a + 10:
            v = "小腿下"
        else:
            v = "脚踝 / 拖地"
        return Landmark("裙长落点", v, f"裙摆距地约 {hem:.0f}cm（占身高 {pos * 100:.0f}%）", round(pos, 3))

    # 下装：内长
    L = p.get("inseam")
    body_inseam = body.get("inseam")
    if L is None:
        return Landmark("内长落点", "数据不足", "缺内长参数", None, "low")
    if not body_inseam:
        return Landmark("内长落点", "数据不足", "缺净体内长", None, "low")
    diff = L - body_inseam
    if diff > 2:
        v, d = "盖脚面 / 需卷边", f"比你的内长长 {diff:.0f}cm"
    elif diff >= -2:
        v, d = "到脚踝（正码）", "内长与你基本一致"
    elif diff >= -8:
        v, d = "九分", f"比你的内长短 {abs(diff):.0f}cm，露出脚踝"
    elif diff >= -18:
        v, d = "七分 / 小腿中", f"比你的内长短 {abs(diff):.0f}cm"
    else:
        v, d = "五分以上", f"比你的内长短 {abs(diff):.0f}cm"
    pos = 1 - (hs["ankle"] + max(diff, 0)) / H
    return Landmark("内长落点", v, d, round(pos, 3))


def sleeve_landmark(garment: dict, body: dict) -> Landmark:
    p = garment["params"]
    arm = body.get("arm_length")
    L = p.get("sleeve_length")
    if L is None:
        return Landmark("袖长落点", "数据不足", "缺袖长参数", None, "low")
    if not arm:
        return Landmark("袖长落点", "数据不足", "缺净体臂长", None, "low")
    ratio = L / arm
    if ratio < 0.35:
        v, d = "短袖（上臂上）", f"盖住臂长 {ratio * 100:.0f}%"
    elif ratio < 0.55:
        v, d = "上臂中", f"盖住臂长 {ratio * 100:.0f}%"
    elif ratio < 0.80:
        v, d = "肘 / 前臂上", f"盖住臂长 {ratio * 100:.0f}%"
    elif ratio <= 1.02:
        v, d = "到手腕", f"盖住臂长 {ratio * 100:.0f}%，正码"
    else:
        v, d = "盖手背", f"盖住臂长 {ratio * 100:.0f}%，袖子偏长"
    # 手臂从肩点垂下，用比例映射到身体高度坐标
    hs = _heights(body)
    pos = None
    if hs:
        shoulder_h = hs["neck_point"] - SHOULDER_DROP
        wrist_h = shoulder_h - arm
        cuff_h = shoulder_h - L
        pos = round(1 - max(cuff_h, wrist_h - 12) / hs["height"], 3)
    return Landmark("袖长落点", v, d, pos)


def judge_all(garment: dict, body: dict, results: list[EaseResult]) -> tuple[list[Judgement], Landmark | None, list[Landmark], str, str]:
    """返回（围度判定列表, 长度落点, 附属落点, 总体结论, 总体置信度）。"""
    pref = body.get("fit_preference") or {}
    judgements = [judge_circumference(r, pref, garment.get("drape", "regular")) for r in results]

    if garment["category"] in ("top", "outerwear"):
        judgements.append(
            judge_shoulder(
                garment["params"].get("shoulder"),
                body.get("shoulder"),
                pref.get("shoulder"),
            )
        )

    length = length_landmark(garment, body)
    extras: list[Landmark] = []
    if garment["category"] in ("top", "outerwear"):
        extras.append(sleeve_landmark(garment, body))

    # 总体：取最短板，不用平均分掩盖硬伤
    def _sev(j) -> int:
        if (j.part, j.verdict) in DEMOTED:
            return 1
        return SEVERITY.get(j.verdict, 0)

    sev = {j.part: _sev(j) for j in judgements}
    worst_sev = max(sev.values()) if sev else 0
    worst_pool = [j for j in judgements if _sev(j) == worst_sev]
    if worst_sev == 0 and worst_pool:
        # 全部偏松时，报最松的那一档，而不是含糊地说"合身"
        order = {"廓形": 2, "宽松": 1}
        overall = max(worst_pool, key=lambda j: order.get(j.verdict, 0)).verdict
    elif worst_pool:
        overall = worst_pool[0].verdict
    else:
        overall = "数据不足"

    if overall == "数据不足":
        known = [j for j in judgements if j.verdict != "数据不足"]
        if known:
            overall = max(known, key=_sev).verdict

    low = sum(1 for j in judgements if j.confidence == "low") + sum(1 for l in [length] + extras if l.confidence == "low")
    total = len(judgements) + 1 + len(extras)
    confidence = "high" if low == 0 else ("mid" if low <= total / 2 else "low")

    return judgements, length, extras, overall, confidence
