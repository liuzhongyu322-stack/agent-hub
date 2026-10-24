#!/usr/bin/env python3
"""验收断言。跑法：python3 tests/test_assertions.py

原则：不看"感觉对不对"，只看机器能不能断言。
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.ease import compute, derive_body, load_schema, normalise_garment  # noqa: E402
from engine.ease_table import thickness_penalty  # noqa: E402
from engine.rules import judge_all  # noqa: E402
from engine.validate import validate_garment  # noqa: E402

PASS, FAIL = "✓", "✗"
results: list[tuple[bool, str]] = []


def check(cond: bool, name: str, extra: str = ""):
    results.append((bool(cond), name))
    print(f"  {PASS if cond else FAIL} {name}" + (f"  —— {extra}" if extra else ""))


def load(p: str) -> dict:
    with open(ROOT / p, encoding="utf-8") as f:
        return json.load(f)


schema = load_schema()
body, _ = derive_body(load("data/body.sample.json"))
shirt = load("data/garments/demo-shirt-01.json")
hoodie = load("data/garments/demo-hoodie-01.json")


print("\n[1] 校验器必须拦住「平铺半围当整圈填」")
for name, patch in [
    ("胸围 52（典型半围）", {"bust": 52}),
    ("胸围 40（离谱）", {"bust": 40}),
    ("衣长 30（起量点写错）", {"length": 30}),
]:
    g = copy.deepcopy(shirt)
    g["params"].update(patch)
    ok, issues = validate_garment(g, schema)
    errs = [i.message for i in issues if i.level == "error"]
    check(not ok and errs, name, errs[0][:44] if errs else "没拦住")


print("\n[2] 弹性修正必须真的改变判定档位")
g_none = copy.deepcopy(shirt)
g_none["stretch"] = "none"
g_none["params"]["bust"] = 89.0  # 扣完是负松量，靠弹性才穿得进
g_mid = copy.deepcopy(shirt)
g_mid["stretch"] = "medium"
g_mid["params"]["bust"] = 89.0
res_n, _ = compute(normalise_garment(g_none)[0], body, schema)
res_m, _ = compute(normalise_garment(g_mid)[0], body, schema)
vn = [r for r in res_n if r.part == "bust"][0]
vm = [r for r in res_m if r.part == "bust"][0]
check(vn.ease == vm.ease, "两件净松量相同（只有弹性不同）", f"{vn.ease:+.1f}")
check(vn.ease_wearable != vm.ease_wearable, "可穿余量因弹性而不同",
      f"{vn.ease_wearable:+.1f} vs {vm.ease_wearable:+.1f}")
jn = [j for j in judge_all(normalise_garment(g_none)[0], body, res_n)[0] if j.part == "bust"][0]
jm = [j for j in judge_all(normalise_garment(g_mid)[0], body, res_m)[0] if j.part == "bust"][0]
check(jn.verdict != jm.verdict, "判定档位出现差异", f"{jn.verdict} → {jm.verdict}")


print("\n[3] 厚度四笔账不能写错")
check(abs(thickness_penalty("wool") - thickness_penalty("thin") - 1.0) < 0.001,
      "薄 → 呢 的围度惩罚差值为 1.0cm",
      f"{thickness_penalty('thin')} → {thickness_penalty('wool')}")
g_thin = copy.deepcopy(shirt)
g_thin["thickness"] = "thin"
g_wool = copy.deepcopy(shirt)
g_wool["thickness"] = "wool"
rt, _ = compute(normalise_garment(g_thin)[0], body, schema)
rw, _ = compute(normalise_garment(g_wool)[0], body, schema)
et = [r for r in rt if r.part == "bust"][0].ease
ew = [r for r in rw if r.part == "bust"][0].ease
check(abs((et - ew) - 1.0) < 0.001, "换厚料后胸围净松量同步少 1.0cm", f"{et:+.1f} → {ew:+.1f}")


print("\n[4] 外套的叠穿必须扣内搭")
coat = load("data/garments/demo-coat-01.json")
c0 = copy.deepcopy(coat)
c0["inner_layer"] = "none"
c1 = copy.deepcopy(coat)
c1["inner_layer"] = "sweater"
r0, _ = compute(normalise_garment(c0)[0], body, schema)
r1, _ = compute(normalise_garment(c1)[0], body, schema)
e0 = [r for r in r0 if r.part == "bust"][0].ease
e1 = [r for r in r1 if r.part == "bust"][0].ease
check(abs((e0 - e1) - 6.0) < 0.001, "内搭毛衣扣掉 6cm 胸围", f"{e0:+.1f} → {e1:+.1f}")


print("\n[5] 缺硬参数时不许编造落点")
g = copy.deepcopy(shirt)
g["params"].pop("length")
res, _ = compute(normalise_garment(g)[0], body, schema)
js, length, extras, overall, conf = judge_all(normalise_garment(g)[0], body, res)
check(length.verdict == "数据不足", "缺衣长 → 落点报「数据不足」", length.verdict)
check(length.position is None, "缺衣长 → 不给位置坐标（不会瞎画）")
check(conf in ("mid", "low"), "置信度相应下调", conf)


print("\n[6] 系统必须敢说「穿不上」，不许硬凑合身")
skirt = load("data/garments/demo-skirt-01.json")
gs = normalise_garment(skirt)[0]
rs, _ = compute(gs, body, schema)
js2, *_rest, overall2, _c = judge_all(gs, body, rs)
check(any(j.verdict == "穿不上" for j in js2), "偏小的裙子被判「穿不上」",
      [f"{j.label}:{j.verdict}" for j in js2 if j.verdict == "穿不上"])


print("\n[7] 净松量为负但面料有弹，不能直接判穿不上")
g = copy.deepcopy(hoodie)
g["params"]["bust"] = 88.0  # 比净体还小
g["stretch"] = "high"
gb = normalise_garment(g)[0]
rb, _ = compute(gb, body, schema)
jb = [j for j in judge_all(gb, body, rb)[0] if j.part == "bust"][0]
check(jb.verdict != "穿不上", "高弹面料负松量仍可穿（判偏紧）", f"{jb.ease:+.1f} → {jb.verdict}")


print("\n[8] 个人偏好：肩部 muscle_fit 档位必须生效且可关闭")
gh = copy.deepcopy(hoodie)
body_real, _ = derive_body(load("data/body.json"))  # 真实档案，含 fit_preference
gh["params"]["shoulder"] = body_real["shoulder"] - 2.0  # 构造肩差 −2cm
gb2 = normalise_garment(gh)[0]
rb2, _ = compute(gb2, body_real, schema)
# 启用偏好（body.json 已含 fit_preference）
j_on = [j for j in judge_all(gb2, body_real, rb2)[0] if j.part == "shoulder"][0]
# 关闭偏好
body_plain = copy.deepcopy(body_real)
body_plain.pop("fit_preference", None)
j_off = [j for j in judge_all(gb2, body_plain, rb2)[0] if j.part == "shoulder"][0]
check(j_off.verdict == "顶死", "不启偏好：肩差 -2cm 判顶死", j_off.verdict)
check(j_on.verdict == "微紧（显肩线）", "启用偏好：肩差 -2cm 判微紧（显肩线）", j_on.verdict)
g_far = copy.deepcopy(gh)
g_far["params"]["shoulder"] = (body_real["shoulder"] or 50) - 4.0  # 差 -4cm，偏好也救不了
rf, _ = compute(normalise_garment(g_far)[0], body_real, schema)
j_far = [j for j in judge_all(normalise_garment(g_far)[0], body_real, rf)[0] if j.part == "shoulder"][0]
check(j_far.verdict == "顶死", "偏好不是魔法：肩差 -4cm 仍判顶死", j_far.verdict)


print("\n[9] 目标效果层：同一件衣服，目标不同结论必须不同")
from engine.rules import judge_goal  # noqa: E402
gs = normalise_garment(shirt)[0]
rs, _ = compute(gs, body_real, schema)
js_shirt = judge_all(gs, body_real, rs)[0]
g_tight = judge_goal(js_shirt, "tight")
g_fit = judge_goal(js_shirt, "fitted")
check(g_tight is not None and "胸围比目标紧" not in g_tight[2],
      "衬衫胸松量 +2.1：目标「紧身」胸围达标", g_tight[2][-34:] if g_tight else "None")
check(g_fit is not None and g_fit[0] < g_fit[1],
      "同一件衣服目标「合身」不达标（比目标紧）", g_fit[2][-34:] if g_fit else "None")
check(judge_goal(js_shirt, None) is None, "不指定目标 → 不出目标层结论")
check(judge_goal(js_shirt, "乱填") is None, "不认识的目标 → 静默忽略（录入时另有警告）")


print("\n[10] 垂坠度必须改变判定：同样的松量，挺括判勒、垂坠判修身")
hai = load("data/garments/haiyijia-shirt-17088a.json")  # 真实数据：胸 103 vs 净体 100
g_str = copy.deepcopy(hai)
g_str["drape"] = "structured"
g_fl = copy.deepcopy(hai)
g_fl["drape"] = "fluid"
r_s, _ = compute(normalise_garment(g_str)[0], body_real, schema)
r_f, _ = compute(normalise_garment(g_fl)[0], body_real, schema)
j_s = [j for j in judge_all(normalise_garment(g_str)[0], body_real, r_s)[0] if j.part == "bust"][0]
j_f = [j for j in judge_all(normalise_garment(g_fl)[0], body_real, r_f)[0] if j.part == "bust"][0]
check(j_s.ease == j_f.ease, "垂坠度不改松量数字", f"{j_s.ease:+.1f} / {j_f.ease:+.1f}")
check(j_s.verdict == "偏紧（勒）", "挺括面料同松量判「勒」", j_s.verdict)
check(j_f.verdict == "修身（垂坠，不勒）", "垂坠面料同松量判「修身·不勒」", j_f.verdict)
g_nd = copy.deepcopy(hai)
g_nd.pop("drape", None)
_, flags_nd = normalise_garment(g_nd)
check(any("垂坠度未填" in f for f in flags_nd), "垂坠度缺失 → 默认常规并记账", flags_nd[:1])


failed = [n for ok, n in results if not ok]
print(f"\n{'-' * 52}")
print(f"{len(results) - len(failed)}/{len(results)} 通过" + (f"　失败：{failed}" if failed else "　全过"))
sys.exit(1 if failed else 0)
