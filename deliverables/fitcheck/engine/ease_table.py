"""松量模型常量表（v1）。

全部长度单位：cm。全部围度为「整圈」周长，不是平铺半围。

四笔账：有效松量 E = 成衣围度 − 净体围度 − 厚度惩罚 − 内衣占量
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CircRule:
    """围度类部位的松量判定规则。"""

    key: str
    label: str
    nature: str  # 骨性 / 软组织 / 混合
    min_ease: float  # 活动必需松量下限：低于它就不是"紧"，是不舒服
    comfort_ease: float  # 舒适区起点
    compress: float  # 可压缩量：靠压缩能硬撑过去多少
    loose_at: float  # 宽松阈值：达到即判宽松
    min_wearable: float  # 可穿性下限（对 E + 弹性可借），低于它直接穿不上
    note: str


# 围度类部位规则表
CIRC_RULES: dict[str, CircRule] = {
    "bust": CircRule(
        key="bust", label="胸围", nature="软组织",
        min_ease=8.0, comfort_ease=10.0, compress=2.5, loose_at=14.0, min_wearable=0.0,
        note="压了会勒，且影响呼吸；正常穿脱至少要 8cm",
    ),
    "waist": CircRule(
        key="waist", label="腰围", nature="软组织",
        min_ease=3.0, comfort_ease=4.5, compress=5.0, loose_at=10.0, min_wearable=-2.0,
        note="可压最大，所以最容易自欺——收腹撑住不等于合身",
    ),
    "hip": CircRule(
        key="hip", label="臀围", nature="混合",
        min_ease=5.0, comfort_ease=6.5, compress=2.5, loose_at=12.0, min_wearable=0.0,
        note="卡不卡胯，一眼就看出来",
    ),
    "upper_arm": CircRule(
        key="upper_arm", label="上臂围", nature="软组织",
        min_ease=5.0, comfort_ease=6.0, compress=2.5, loose_at=10.0, min_wearable=0.0,
        note="袖子显不显壮全看这一项",
    ),
    "neck": CircRule(
        key="neck", label="颈围", nature="骨性",
        min_ease=2.5, comfort_ease=3.5, compress=1.0, loose_at=8.0, min_wearable=0.0,
        note="几乎不可压，扣不上就是扣不上",
    ),
    "thigh": CircRule(
        key="thigh", label="大腿围", nature="软组织",
        min_ease=7.0, comfort_ease=8.0, compress=3.5, loose_at=14.0, min_wearable=0.0,
        note="大腿是最容易被忽略的卡点",
    ),
    "cuff": CircRule(
        key="cuff", label="袖口围", nature="混合",
        min_ease=0.0, comfort_ease=1.5, compress=1.5, loose_at=8.0, min_wearable=-1.5,
        note="瓶颈是手掌能不能过去；有罗纹或开襟时，紧一点也不影响穿",
    ),
    "hem": CircRule(
        key="hem", label="下摆围", nature="混合",
        min_ease=6.0, comfort_ease=7.5, compress=2.5, loose_at=16.0, min_wearable=0.0,
        note="下摆卡在胯上会翘起来",
    ),
    "trouser_leg": CircRule(
        key="trouser_leg", label="裤口围", nature="混合",
        min_ease=3.0, comfort_ease=4.5, compress=2.5, loose_at=12.0, min_wearable=0.0,
        note="裤口挂在脚踝附近，贴着小腿就是紧口裤",
    ),
}


# 面料厚度：mm → 围度惩罚。平铺量的是外沿，两层布厚被算进围度里，故惩罚 = 4 × 厚度
THICKNESS: dict[str, dict] = {
    "thin":  {"label": "薄（120–180 g/m²）",  "mm": 0.5, "example": "薄针织、雪纺、衬衫府绸"},
    "mid":   {"label": "中（200–280 g/m²）",  "mm": 0.9, "example": "常规针织、厚衬衫、薄牛仔"},
    "thick": {"label": "厚（300–400 g/m²）",  "mm": 1.5, "example": "卫衣毛圈、加厚牛仔"},
    "wool":  {"label": "呢类（羊毛呢）",       "mm": 3.0, "example": "大衣呢、粗花呢"},
    "padded": {"label": "膨胀类（加绒/羽绒）", "mm": 8.0, "example": "羽绒、棉服（估算，误差大）"},
}


def thickness_penalty(level: str) -> float:
    """厚度档位 → 围度惩罚（cm）。"""
    if level not in THICKNESS:
        raise KeyError(f"未知厚度档位：{level}")
    return round(4.0 * THICKNESS[level]["mm"] / 10.0, 2)


# 弹性可借量：面料能替你"顶"掉多少负松量
STRETCH: dict[str, dict] = {
    "none":   {"label": "无弹（纯棉/麻/毛梭织、牛仔）", "borrow": 0.0},
    "slight": {"label": "微弹（含 2–5% 氨纶）",        "borrow": 2.5},
    "medium": {"label": "中弹（针织罗纹、卫衣）",      "borrow": 5.0},
    "high":   {"label": "高弹（紧身打底、运动面料）",  "borrow": 7.0},
}


# 垂坠度：决定"必需松量"该定多高，不决定穿不穿得进。
# 挺括面料松量不够会硬顶出拉扯褶；垂坠面料会顺着身体流，同样的松量看着不紧、也不难受。
# 这一维是拿真实穿着照片校准出来的：170/88A 垂坠衬衫胸差 +3cm，实穿不勒，按挺括标准却判"勒"。
DRAPE: dict[str, dict] = {
    "structured": {"label": "挺括（正装衬衫、有骨架）", "min_shift": 0.0, "compress_shift": 0.0, "loose_shift": 0.0},
    "regular":    {"label": "常规（普通棉、混纺）",     "min_shift": -1.0, "compress_shift": 0.5, "loose_shift": 0.0},
    "fluid":      {"label": "垂坠（天丝/醋酸/丝感）",   "min_shift": -2.5, "compress_shift": 1.5, "loose_shift": -1.0},
}


def drape_thresholds(rule: "CircRule", drape: str) -> tuple[float, float, float]:
    """按垂坠度调整（必需松量, 可压缩量, 宽松线）。"""
    d = DRAPE.get(drape, DRAPE["regular"])
    return (
        max(0.0, rule.min_ease + d["min_shift"]),
        rule.compress + d["compress_shift"],
        rule.loose_at + d["loose_shift"],
    )


# 内衣占量：净体是裸体测量，实际穿着要扣掉内衣厚度
UNDERWEAR_TOP: dict[str, dict] = {
    "none":  {"label": "不穿 / 无胸衣",   "allow": 0.0},
    "thin":  {"label": "薄内衣",          "allow": 1.5},
    "sport": {"label": "运动内衣 / 厚杯",  "allow": 3.5},
}
UNDERWEAR_BOTTOM: dict[str, dict] = {
    "none":    {"label": "仅内裤",       "allow": 0.0},
    "thin":    {"label": "薄打底",       "allow": 1.5},
    "thermal": {"label": "秋裤 / 加绒",  "allow": 2.5},
}
# 下装默认按"仅内裤"计（内裤几乎不占围度）
UNDERWEAR_BOTTOM_DEFAULT = "none"


# 外套内搭：叠穿时内层会吃掉胸围松量
INNER_LAYER: dict[str, dict] = {
    "none":    {"label": "无（裸穿 / 薄T恤）", "allow": 0.0},
    "shirt":   {"label": "衬衫",              "allow": 2.0},
    "sweater": {"label": "毛衣 / 厚针织",      "allow": 6.0},
    "hoodie":  {"label": "厚卫衣 / 加绒",      "allow": 10.0},
}


# 版型意图：设计松量是设计师故意留的，判定阈值要跟着偏移
SILHOUETTE: dict[str, dict] = {
    "slim":     {"label": "修身",       "loose_shift": -4.0},
    "regular":  {"label": "标准",       "loose_shift": 0.0},
    "relaxed":  {"label": "宽松",       "loose_shift": 4.0},
    "oversize": {"label": "Oversize",   "loose_shift": 8.0},
}


# 目标效果：每件衣服可由用户指定"我想要它穿成什么样"（fit_goal 字段）。
# 判定分两层：事实层照实报松量分档；目标层对照这里的目标区，回答"达没达到你要的效果"。
# band = (净松量下限, 上限)，适用于软组织/混合类围度部位。
# 肩宽是骨性部位、袖口看手掌通过性，不进目标判定；绝对底线（穿不上）永远优先于任何目标。
FIT_GOALS: dict[str, dict] = {
    "tight":    {"label": "紧身 / 显线条",   "band": (0.0, 6.0)},
    "fitted":   {"label": "合身",            "band": (6.0, 14.0)},
    "relaxed":  {"label": "宽松",            "band": (14.0, 24.0)},
    "oversize": {"label": "廓形 / Oversize", "band": (24.0, 999.0)},
}


# 肩宽专用分档（骨性部位，不用通用松量逻辑）
SHOULDER_BANDS = [
    (-99.0, -1.0, "顶死", "肩部会鼓包，整件衣服的型跟着垮"),
    (-1.0, 0.5, "正肩", "正好，是最精神的肩线"),
    (0.5, 3.0, "微落肩", "略微松，日常最稳的一档"),
    (3.0, 6.0, "明显落肩", "肩线掉到上臂，风格化明显"),
    (6.0, 99.0, "Oversize 落肩", "肩线掉到手臂中段，属于设计不是失误"),
]

# 肩宽分档（健身体型偏好版）：body.json 里 fit_preference.shoulder = "muscle_fit" 时启用。
# 逻辑：−2~−1cm 的肩线略窄于肩峰，肌肉体 型刚好撑起来，判「微紧（显肩线）」而非顶死；
# −2 以下照样顶死——偏好不是魔法，布料不会凭空多出 3cm。
SHOULDER_MUSCLE_BANDS = [
    (-99.0, -2.0, "顶死", "肩部会鼓包，整件衣服的型跟着垮"),
    (-2.0, -1.0, "微紧（显肩线）", "肩线略窄，撑在肩上显健身痕迹——你的偏好区间"),
    (-1.0, 0.5, "正肩", "正好，是最精神的肩线"),
    (0.5, 3.0, "微落肩", "略微松，日常最稳的一档"),
    (3.0, 6.0, "明显落肩", "肩线掉到上臂，风格化明显"),
    (6.0, 99.0, "Oversize 落肩", "肩线掉到手臂中段，属于设计不是失误"),
]


# 置信度
CONFIDENCE_LABEL = {"high": "高", "mid": "中", "low": "低"}
