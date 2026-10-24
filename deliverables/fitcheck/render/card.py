"""把判定结果渲染成一张可打印的单页判定卡。"""

from __future__ import annotations

import html
from pathlib import Path

from engine.ease_table import DRAPE, INNER_LAYER, SILHOUETTE, STRETCH, THICKNESS

VERDICT_STYLE = {
    "穿不上": ("v-bad", "穿不上"),
    "偏紧（勒）": ("v-warn", "偏紧（勒）"),
    "偏紧": ("v-warn", "偏紧"),
    "合身": ("v-good", "合身"),
    "宽松": ("v-ok", "宽松"),
    "廓形": ("v-ok", "廓形"),
    "数据不足": ("v-none", "数据不足"),
    "顶死": ("v-bad", "顶死"),
    "正肩": ("v-good", "正肩"),
    "微紧（显肩线）": ("v-good", "微紧·显肩线"),
    "修身（垂坠，不勒）": ("v-good", "修身·垂坠"),
    "微落肩": ("v-ok", "微落肩"),
    "明显落肩": ("v-ok", "明显落肩"),
    "Oversize 落肩": ("v-ok", "Oversize 落肩"),
}

CONF_LABEL = {"high": "高", "mid": "中", "low": "低"}

FALLBACK_POS = {
    "下摆": 0.62, "腰线": 0.55, "臀线": 0.52, "袖口": 0.72,
}


def _tag(verdict: str) -> str:
    cls, label = VERDICT_STYLE.get(verdict, ("v-none", verdict))
    return f'<span class="tag {cls}">{html.escape(label)}</span>'


def _num(v, suffix="", signed=False) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        s = f"{v:+.1f}" if signed else f"{v:.1f}"
        if not signed and s.endswith(".0"):
            s = s[:-2]
        if signed and s in ("+0.0", "-0.0"):
            s = "0.0"
        return s + suffix
    return f"{v}{suffix}"


def _one_liner(judgements, length, garment) -> str:
    """只说问题，不堆好话。偏松不算问题，除非整体就偏松。"""
    problems = {"穿不上", "偏紧（勒）", "偏紧", "顶死"}
    ranked = sorted(
        [j for j in judgements if j.verdict in problems],
        key=lambda j: 0 if j.verdict in ("穿不上", "顶死") else 1,
    )
    if ranked:
        base = "、".join(f"{j.label}{j.verdict}" for j in ranked[:2]) + "，其余正常"
    else:
        loose = [j for j in judgements if j.verdict in ("宽松", "廓形")]
        base = f"{loose[0].label}偏松，整体是宽松取向" if loose else "各部位松量都在合身区"

    if length and length.verdict != "数据不足":
        word = "裙摆" if "裙" in length.name else ("裤口" if "内长" in length.name else "下摆")
        base += f"；{word}{length.verdict}"
    return base


def _figure(garment: dict, body: dict, length, extras) -> str:
    """画一张示意图：身体轮廓 + 腰线 / 臀线 / 下摆 / 袖口 的位置。"""
    H = body.get("height") or 172
    top, bottom = 16, 300
    scale = (bottom - top) / H
    y = lambda cm: bottom - cm * scale  # noqa: E731

    waist_h = body.get("waist_height") or (0.84 * H - (body.get("back_length") or 0.24 * H))
    hip_h = 0.48 * H
    knee_h = 0.285 * H
    ankle_h = 0.04 * H
    shoulder_h = 0.84 * H - 4
    arm = body.get("arm_length") or 0.35 * H

    cx = 72
    sy, wy, hy, ky, ay = y(shoulder_h), y(waist_h), y(hip_h), y(knee_h), y(ankle_h)

    parts = [
        f'<circle cx="{cx}" cy="{top + 14}" r="13" fill="#F1EFE8" stroke="#B4B2A9" stroke-width="0.8"/>'
        f'<rect x="{cx - 6}" y="{top + 24}" width="12" height="{max(sy - top - 24, 6):.0f}" fill="#F1EFE8" stroke="#B4B2A9" stroke-width="0.8"/>',
        f'<path d="M{cx - 27} {sy:.0f} L{cx + 27} {sy:.0f} L{cx + 21} {hy:.0f} L{cx - 21} {hy:.0f} Z" fill="#F6F5F0" stroke="#B4B2A9" stroke-width="0.8"/>',
        f'<rect x="{cx - 37}" y="{sy:.0f}" width="9" height="{max(min(arm, shoulder_h - ankle_h) * scale, 10):.0f}" rx="4.5" fill="#F6F5F0" stroke="#B4B2A9" stroke-width="0.8"/>',
        f'<rect x="{cx + 28}" y="{sy:.0f}" width="9" height="{max(min(arm, shoulder_h - ankle_h) * scale, 10):.0f}" rx="4.5" fill="#F6F5F0" stroke="#B4B2A9" stroke-width="0.8"/>',
        f'<rect x="{cx - 19}" y="{hy:.0f}" width="16" height="{max(ay - hy, 10):.0f}" fill="#F6F5F0" stroke="#B4B2A9" stroke-width="0.8"/>',
        f'<rect x="{cx + 3}" y="{hy:.0f}" width="16" height="{max(ay - hy, 10):.0f}" fill="#F6F5F0" stroke="#B4B2A9" stroke-width="0.8"/>',
    ]

    # 参考线：腰 / 臀
    for label, yy in (("腰线", wy), ("臀线", hy)):
        parts.append(
            f'<line x1="{cx - 46}" y1="{yy:.0f}" x2="{cx + 46}" y2="{yy:.0f}" stroke="#D3D1C7" stroke-width="0.8" stroke-dasharray="2 3"/>'
            f'<text x="{cx + 52}" y="{yy + 3:.0f}" font-size="10" fill="#8A877E" font-family="var(--f)">{label}</text>'
        )

    # 下摆落点
    if length and length.position is not None:
        pos = length.position
        hem_y = top + pos * (bottom - top)
        parts.append(
            f'<line x1="{cx - 52}" y1="{hem_y:.0f}" x2="{cx + 48}" y2="{hem_y:.0f}" stroke="#0F6E56" stroke-width="1.4"/>'
            f'<circle cx="{cx - 52}" cy="{hem_y:.0f}" r="2.6" fill="#0F6E56"/>'
            f'<text x="{cx + 52}" y="{hem_y + 3:.0f}" font-size="10.5" font-weight="600" fill="#0F6E56" font-family="var(--f)">下摆</text>'
        )

    # 袖口落点
    for ex in extras:
        if ex.name == "袖长落点" and ex.position is not None:
            cy = top + ex.position * (bottom - top)
            parts.append(
                f'<line x1="{cx + 24}" y1="{cy:.0f}" x2="{cx + 42}" y2="{cy:.0f}" stroke="#185FA5" stroke-width="1.4"/>'
                f'<text x="{cx + 46}" y="{cy + 3:.0f}" font-size="10.5" fill="#185FA5" font-family="var(--f)">袖口</text>'
            )

    return (
        '<svg viewBox="0 0 240 320" width="100%" role="img" aria-label="落点示意图" '
        'style="--f:-apple-system,BlinkMacSystemFont,\'PingFang SC\',sans-serif">'
        + "".join(parts)
        + "</svg>"
    )


def render(garment: dict, body: dict, judgements, length, extras, overall: str,
           confidence: str, flags: list[str], out_path: Path,
           goal_info: tuple | None = None) -> Path:
    spec_th = THICKNESS.get(garment["thickness"], {}).get("label", "—")
    spec_st = STRETCH.get(garment["stretch"], {}).get("label", "—")
    spec_sil = SILHOUETTE.get(garment.get("silhouette", "regular"), {}).get("label", "标准")
    spec_dp = DRAPE.get(garment.get("drape", "regular"), {}).get("label", "常规")
    inner = INNER_LAYER.get(garment.get("inner_layer", "none"), {}).get("label", "—")

    meta_chips = [
        garment.get("brand") or "未填品牌",
        garment.get("size") and f"尺码 {garment['size']}" or "尺码未填",
        f"面料 {spec_th}",
        f"垂坠 {spec_dp}",
        f"弹性 {spec_st}",
        f"版型 {spec_sil}",
    ]
    if garment["category"] == "outerwear":
        meta_chips.append(f"内搭 {inner}")

    rows = []
    for j in judgements:
        rows.append(
            f'<tr><td class="c-part">{html.escape(j.label)}</td>'
            f'<td class="c-num">{_num(j.body_value)}</td>'
            f'<td class="c-num">{_num(j.garment_value)}</td>'
            f'<td class="c-num c-ease">{_num(j.ease, signed=True)}</td>'
            f'<td class="c-tag">{_tag(j.verdict)}</td></tr>'
            f'<tr class="r-detail"><td colspan="5">{html.escape(j.detail)}'
            + (f'<span class="hint">{html.escape(j.visual_note)}</span>' if j.visual_note else "")
            + (f'<span class="hint">{html.escape(j.breakdown)}</span>' if j.breakdown else "")
            + "</td></tr>"
        )

    # 围度表的净体/成衣值需要从 EaseResult 里取，Judgement 没带；由调用方补齐
    landmark_rows = "".join(
        f'<li><span class="lm-name">{html.escape(l.name)}</span>'
        f'<span class="lm-verdict">{html.escape(l.verdict)}</span>'
        f'<span class="lm-detail">{html.escape(l.detail)}</span></li>'
        for l in ([length] if length else []) + list(extras)
    )

    th_info = THICKNESS.get(garment["thickness"], THICKNESS["mid"])
    th_mm = th_info["mm"]
    th_pen = round(4.0 * th_mm / 10.0, 2)
    st_borrow = STRETCH.get(garment["stretch"], {}).get("borrow", 0.0)

    flags_html = "".join(f"<li>{html.escape(f)}</li>" for f in flags) or "<li>无</li>"

    # 目标效果层：用户指定 fit_goal 后，回答"达没达到你要的效果"
    goal_html = ""
    if goal_info:
        ok_n, n, text = goal_info
        good = n > 0 and ok_n == n
        color = "#0F6E56" if good else "#8A5A00"
        vibe = garment.get("vibe")
        vibe_line = f'你想要的感觉：「{html.escape(str(vibe))}」<br>' if vibe else ""
        goal_html = (
            f'<p class="callout" style="border-left:3px solid {color}; margin-top:10px">'
            f'{vibe_line}<strong>{html.escape(text)}</strong></p>'
        )
    warn_html = ""
    if confidence == "low":
        warn_html = (
            '<p class="callout">这张卡的置信度偏低：有多个关键参数缺失，'
            "结论只能当方向参考，不要当复核依据。</p>"
        )
    elif confidence == "mid":
        warn_html = (
            '<p class="callout">部分参数是估算值（已在下方列出），'
            "结论方向可信，具体数值不要抠到厘米。</p>"
        )

    one_line = _one_liner(judgements, length, garment)
    cls, big = VERDICT_STYLE.get(overall, ("v-none", overall))

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>合身判定 · {html.escape(garment.get('name', '未命名'))}</title>
<style>
  :root {{
    --ink:#1B1B19; --ink2:#55534C; --ink3:#8A877E; --line:#E4E1D8;
    --paper:#FFFFFF; --panel:#FBFAF7; --good:#0F6E56; --warn:#854F0B;
    --bad:#A32D2D; --ok:#185FA5;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{
    font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Helvetica Neue",sans-serif;
    color:var(--ink); background:var(--paper); line-height:1.6;
    -webkit-font-smoothing:antialiased;
  }}
  .page {{ max-width:760px; margin:0 auto; padding:44px 48px 32px; }}
  .kicker {{ font-size:11px; letter-spacing:.18em; color:var(--ink3); text-transform:uppercase; }}
  h1 {{ font-size:26px; font-weight:600; letter-spacing:-.01em; margin-top:10px; }}
  .chips {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:14px; }}
  .chip {{
    font-size:11.5px; color:var(--ink2); border:0.5px solid var(--line);
    padding:3px 9px; border-radius:99px; background:var(--panel);
  }}
  .band {{
    display:flex; align-items:center; gap:18px; margin-top:26px;
    padding:20px 22px; background:var(--panel); border:0.5px solid var(--line); border-radius:14px;
  }}
  .badge {{
    font-size:20px; font-weight:600; padding:8px 20px; border-radius:10px; white-space:nowrap;
  }}
  .v-bad {{ background:#FCEBEB; color:var(--bad); }}
  .v-warn {{ background:#FAEEDA; color:var(--warn); }}
  .v-good {{ background:#E1F5EE; color:var(--good); }}
  .v-ok {{ background:#E6F1FB; color:var(--ok); }}
  .v-none {{ background:#F1EFE8; color:var(--ink3); }}
  .band-note {{ font-size:13px; color:var(--ink2); }}
  .band-conf {{ margin-left:auto; font-size:12px; color:var(--ink3); text-align:right; white-space:nowrap; }}
  h2 {{ font-size:13px; font-weight:600; letter-spacing:.06em; color:var(--ink2);
        margin:34px 0 14px; padding-bottom:8px; border-bottom:0.5px solid var(--line); }}
  .grid {{ display:grid; grid-template-columns:210px 1fr; gap:28px; align-items:start; }}
  .landmark {{ list-style:none; }}
  .landmark li {{ padding:12px 0; border-bottom:0.5px solid var(--line); }}
  .landmark li:last-child {{ border-bottom:none; }}
  .lm-name {{ display:block; font-size:11px; color:var(--ink3); letter-spacing:.05em; }}
  .lm-verdict {{ display:block; font-size:16px; font-weight:600; margin-top:2px; }}
  .lm-detail {{ display:block; font-size:12px; color:var(--ink2); margin-top:3px; }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{
    font-size:11px; font-weight:500; color:var(--ink3); text-align:left;
    padding:0 8px 8px; border-bottom:0.5px solid var(--line); letter-spacing:.04em;
  }}
  th.num, td.c-num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  td {{ padding:11px 8px; font-size:14px; vertical-align:top; }}
  tr:not(.r-detail) td {{ border-bottom:0.5px solid var(--line); }}
  .c-part {{ font-weight:500; }}
  .c-ease {{ font-weight:600; }}
  .c-tag {{ text-align:right; }}
  .tag {{ display:inline-block; font-size:11.5px; padding:2px 9px; border-radius:6px; white-space:nowrap; }}
  .r-detail td {{
    padding:0 8px 13px; font-size:12px; color:var(--ink2); border-bottom:0.5px solid var(--line);
  }}
  .hint {{ display:block; color:var(--ink3); margin-top:3px; }}
  .calc {{
    background:var(--panel); border:0.5px solid var(--line); border-radius:12px;
    padding:16px 18px; font-size:12.5px; color:var(--ink2);
  }}
  .calc code {{ font-size:12.5px; color:var(--ink); letter-spacing:.01em; }}
  .calc .step {{ display:block; margin:4px 0; }}
  .callout {{
    margin-top:14px; font-size:12.5px; color:var(--warn);
    background:#FAEEDA; border-radius:10px; padding:12px 16px;
  }}
  ul.plain {{ list-style:none; font-size:12.5px; color:var(--ink2); }}
  ul.plain li {{ padding:5px 0 5px 14px; position:relative; }}
  ul.plain li::before {{ content:"·"; position:absolute; left:2px; color:var(--ink3); }}
  footer {{
    margin-top:36px; padding-top:14px; border-top:0.5px solid var(--line);
    font-size:11px; color:var(--ink3); display:flex; justify-content:space-between; gap:16px;
  }}
  @media print {{
    @page {{ size:A4 portrait; margin:14mm 12mm; }}
    body {{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
    .page {{ padding:0; max-width:none; }}
    h2 {{ break-after:avoid; }}
    .band, table, .calc {{ break-inside:avoid; }}
  }}
</style>
</head>
<body>
<div class="page">

  <div class="kicker">合身判定卡 · Fit Report</div>
  <h1>{html.escape(garment.get('name', '未命名'))}</h1>
  <div class="chips">{''.join(f'<span class="chip">{html.escape(str(c))}</span>' for c in meta_chips)}</div>

  <div class="band">
    <div class="badge {cls}">{html.escape(big)}</div>
    <div class="band-note">{html.escape(one_line)}</div>
    <div class="band-conf">置信度<br><strong>{CONF_LABEL.get(confidence, '—')}</strong></div>
  </div>
  {goal_html}
  {warn_html}

  <h2>落点</h2>
  <div class="grid">
    <div>{_figure(garment, body, length, extras)}</div>
    <ul class="landmark">{landmark_rows}</ul>
  </div>

  <h2>各部位松量</h2>
  <table>
    <thead><tr>
      <th>部位</th><th class="num">你的</th><th class="num">成衣</th><th class="num">净松量</th><th style="text-align:right">判定</th>
    </tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>

  <h2>计算过程</h2>
  <div class="calc">
    <span class="step">净松量 = 成衣围度 − 净体围度 − 厚度惩罚 − 内衣占量 − 内搭占量</span>
    <span class="step">可穿余量 = 净松量 + 弹性可借量（弹力能帮你穿进去，但改变不了镜子里的样子）</span>
    <span class="step">本件厚度惩罚 = 4 × {th_mm}mm = {th_pen}cm；弹性可借 = {st_borrow}cm</span>
    <span class="step">单侧视觉余量 = 净松量 ÷ 2π（松量 4cm 看着几乎贴身，10cm 才看得出宽松）</span>
  </div>

  <h2>数据口径提醒</h2>
  <ul class="plain">{flags_html}</ul>

  <footer>
    <span>判定依据：净体档案 + 成衣实测参数，未使用任何图像模型</span>
    <span>{html.escape(garment.get('id', ''))}</span>
  </footer>
</div>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    return out_path
