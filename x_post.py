"""X 投稿用の画像(地上天気図5枚まとめ + LINE への誘導)を1枚作る。
ASAS 24時間前・12時間前・最新、FSAS24・48 を 3×2 に並べ、6マス目を LINE 案内にする。
使い方: python -X utf8 x_post.py
出力: C:\\Users\\endo-\\Documents\\kishobosai\\tenkizu\\x_post_YYYYMMDDHH.jpg (最新ASASの時刻・UTC)
"""
import os
import re
from datetime import datetime, timedelta

from PIL import Image, ImageDraw, ImageFont

import asas_view

# ---- ここを書き換える(決まるまでは仮) ----
BRAND = "ならべて天気図"           # サービス名
LINE_ID = "@xxxxxxxx"            # LINE 公式アカウントのID
EDITOR = "ならべて天気図"          # 加工・編集の責任者として出典に書く名前
# ----------------------------------------

OUT_DIR = r"C:\Users\endo-\Documents\kishobosai\tenkizu"
W, H = 2400, 1350                # 16:9。X のタイムラインで切れずに出る比率
PAD, GAP = 24, 18
HEAD, FOOT, CAP = 118, 64, 46    # 見出し帯・出典帯・各図のキャプションの高さ
NAVY, RED, GRAY = (16, 42, 84), (208, 0, 0), (235, 238, 242)
# フォントは BIZ UDゴシック。このフォルダの fonts\ (クラウド用) → Windows の順に探す
_here = os.path.dirname(os.path.abspath(__file__))
FONT_B, FONT_R = next(
    (b, r) for b, r in (
        (os.path.join(_here, "fonts", "BIZUDGothic-Bold.ttf"), os.path.join(_here, "fonts", "BIZUDGothic-Regular.ttf")),
        (r"C:\Windows\Fonts\BIZ-UDGothicB.ttc", r"C:\Windows\Fonts\BIZ-UDGothicR.ttc"),
    ) if os.path.exists(b)
)


def font(size, bold=True):
    return ImageFont.truetype(FONT_B if bold else FONT_R, size)


def cell_boxes():
    cw = (W - PAD * 2 - GAP * 2) // 3
    ch = (H - HEAD - FOOT - PAD - GAP) // 2
    return [(PAD + c * (cw + GAP), HEAD + r * (ch + GAP), cw, ch) for r in range(2) for c in range(3)], cw, ch


def utc_of(png):
    return datetime.strptime(re.findall(r"_(\d{10})\.png$", png)[0], "%Y%m%d%H")


def draw_chart(img, d, box, title, when, png, now):
    x, y, w, h = box
    d.rectangle([x, y, x + w, y + CAP], fill=RED if now else GRAY)
    d.text((x + 12, y + CAP // 2), title, font=font(26), fill="white" if now else NAVY, anchor="lm")
    d.text((x + w - 12, y + CAP // 2), when, font=font(20, False), fill="white" if now else (40, 40, 40), anchor="rm")
    chart = Image.open(os.path.join(asas_view.OUT, png)).convert("RGB")
    ih = h - CAP
    iw = round(chart.width * ih / chart.height)
    if iw > w:
        iw, ih = w, round(chart.height * w / chart.width)
    img.paste(chart.resize((iw, ih), Image.LANCZOS), (x + (w - iw) // 2, y + CAP))
    d.rectangle([x, y, x + w, y + h], outline=RED if now else (150, 150, 150), width=6 if now else 2)


def draw_cta(d, box):
    x, y, w, h = box
    d.rounded_rectangle([x, y, x + w, y + h], radius=18, fill=NAVY)
    cx = x + w // 2
    d.text((cx, y + 58), "気象予報士・受験生のための", font=font(28, False), fill=(200, 215, 240), anchor="mm")
    d.text((cx, y + 112), "最新の天気図を1枚で", font=font(44), fill="white", anchor="mm")
    lines = ["・毎日 3:40 / 15:40 の更新後すぐ", "・LINEで「最新の天気図」を押すだけ", "・印刷・PNG保存OK",
             "・実況と予想図の見比べに（実技対策にも）"]
    for i, t in enumerate(lines):
        d.text((x + 44, y + 180 + i * 46), t, font=font(28, False), fill="white", anchor="lm")
    d.rounded_rectangle([x + 40, y + h - 100, x + w - 40, y + h - 30], radius=35, fill=(6, 199, 85))
    d.text((cx, y + h - 65), f"LINE 友だち追加  {LINE_ID}", font=font(32), fill="white", anchor="mm")


def draw_info(d, box, url):
    """LINE で開くページ用の6マス目(案内)。"""
    x, y, w, h = box
    d.rounded_rectangle([x, y, x + w, y + h], radius=18, fill=NAVY)
    cx = x + w // 2
    d.text((cx, y + 70), BRAND, font=font(56), fill="white", anchor="mm")
    d.text((cx, y + 132), "気象予報士・受験生のための地上天気図まとめ", font=font(26, False), fill=(200, 215, 240), anchor="mm")
    lines = ["・毎日 3:40 / 15:40 ごろ自動で更新", "・赤枠が最新の実況(ASAS)", "・FSASは初期値も確認を", "・実況と予想図の見比べに"]
    for i, t in enumerate(lines):
        d.text((x + 44, y + 200 + i * 46), t, font=font(28, False), fill="white", anchor="lm")
    if url:
        d.text((cx, y + h - 50), url, font=font(26, False), fill=(200, 215, 240), anchor="mm")


def make_image(charts, path, cta="x", url=""):
    """charts = asas_view.fetch_charts() の結果。cta="x" は X 投稿用(LINE 案内)、"page" は LINE で開くページ用。"""
    latest = next(utc_of(p) for a, _, p in charts if "最新" in a)
    j = latest + timedelta(hours=9)

    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, HEAD - 22], fill=NAVY)
    d.text((PAD, (HEAD - 22) // 2), "地上天気図 5枚まとめ", font=font(50), fill="white", anchor="lm")
    d.text((PAD + 540, (HEAD - 22) // 2), f"最新 {j.year}年{j.month}月{j.day}日 {j.hour}時 ({latest:%H}UTC)",
           font=font(34, False), fill=(220, 230, 245), anchor="lm")
    d.text((W - PAD, (HEAD - 22) // 2), "24h前 → 12h前 → 最新 → 24h予想 → 48h予想", font=font(28, False),
           fill=(220, 230, 245), anchor="rm")

    boxes, _, _ = cell_boxes()
    for box, (title, when, png) in zip(boxes, charts):
        when = re.sub(r"\s*\(.*?\)", "", when).replace("初期値", "/ 初期値")
        draw_chart(img, d, box, title.replace("時間予想", "h予想"), when, png, "最新" in title)
    if cta == "x":
        draw_cta(d, boxes[5])
    else:
        draw_info(d, boxes[5], url)

    d.text((PAD, H - FOOT // 2), f"出典：気象庁ホームページ（地上天気図）を加工して作成。編集・加工の責任は{EDITOR}にあります。",
           font=font(22, False), fill=(60, 60, 60), anchor="lm")
    d.text((W - PAD, H - FOOT // 2), BRAND, font=font(26), fill=NAVY, anchor="rm")
    img.save(path, quality=90)
    return latest


def main():
    charts = asas_view.fetch_charts()
    latest = next(utc_of(p) for a, _, p in charts if "最新" in a)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"x_post_{latest:%Y%m%d%H}.jpg")
    make_image(charts, path)
    print(path, round(os.path.getsize(path) / 1024), "KB")
    return path


if __name__ == "__main__":
    os.startfile(main())
