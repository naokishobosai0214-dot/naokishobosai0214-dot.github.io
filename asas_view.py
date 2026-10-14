"""気象庁の地上天気図(白黒)を並べて表示する。
48時間前・24時間前・最新のASAS と、24時間予想(FSAS24)・48時間予想(FSAS48)。最新は FSAS の初期値(00/12UTC)にそろえる。色は付けず気象庁の白黒図のまま。
使い方: python -X utf8 asas_view.py
"""
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta

import numpy as np
import pymupdf

BASE = "https://www.data.jma.go.jp/yoho/data/wxchart/quick/"
LIST = "https://www.jma.go.jp/bosai/weather_map/data/list.json"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "asas_view")
DPI = 130
LAND = (0.84, 0.95, 0.84)  # 陸地の薄い緑


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def valid_time(name):
    # ファイル名の2つ目の14桁が対象時刻(UTC)
    return datetime.strptime(re.findall(r"_(\d{14})_MET", name)[0], "%Y%m%d%H%M%S")


def jst(t):
    j = t + timedelta(hours=9)
    return f"{j.month}月{j.day}日 {j.hour}時 ({t:%d}日{t:%H}UTC)"


def color_layer(color_url):
    """カラー版PDFから、陸地(薄い緑)と H(青)・L(赤) の塗りだけを描いた画像を返す。"""
    src = pymupdf.open(stream=get(color_url), filetype="pdf")[0]
    doc = pymupdf.open()
    page = doc.new_page(width=src.rect.width, height=src.rect.height)
    shape = page.new_shape()
    for g in src.get_drawings():
        f = g.get("fill")
        if not f:
            continue
        f = tuple(round(x, 2) for x in f)
        if f[1] > 0.9 and f[0] < 0.8 and f[2] < 0.8:
            fill = LAND
        elif g["type"] == "f" and f in ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)):
            fill = f  # 高気圧のH=青、低気圧のL=赤
        else:
            continue
        for it in g["items"]:
            if it[0] == "l":
                shape.draw_line(it[1], it[2])
            elif it[0] == "c":
                shape.draw_bezier(it[1], it[2], it[3], it[4])
            elif it[0] == "re":
                shape.draw_rect(it[1])
            elif it[0] == "qu":
                shape.draw_quad(it[1])
        shape.finish(fill=fill, color=None, even_odd=True)
    shape.commit()
    return page.get_pixmap(dpi=DPI)


def to_array(pix):
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]


def render(url, png, color_url=None):
    """PDF を画像にする。color_url を渡したときだけ陸地とH・Lの色を重ねる(ならべて天気図は気象庁の白黒図のまま)。"""
    doc = pymupdf.open(stream=get(url), filetype="pdf")
    pix = doc[0].get_pixmap(dpi=DPI)
    if color_url is None:
        pix.save(os.path.join(OUT, png))
        return
    land = color_layer(color_url)
    # 白黒の図に陸地とH・Lの色を重ねる(線は黒のまま残る)
    out = np.minimum(to_array(pix), to_array(land))
    out = np.ascontiguousarray(out)
    pymupdf.Pixmap(pymupdf.csRGB, pix.width, pix.height, out.tobytes(), False).save(os.path.join(OUT, png))


def fsas_init(lst):
    """FSAS24・48 の初期値(UTC)。2枚の初期値がそろっていなければ None(FSAS48 は FSAS24 より約2時間遅れて出る)。"""
    i24, i48 = (valid_time(lst[f"ft{ft}"][-1]) for ft in (24, 48))
    return i48 if i24 == i48 else None


def fetch_charts():
    """5枚を描いて、(見出し, 時刻, ファイル名) のリストを返す。
    並びは ASAS 48時間前・24時間前・最新、FSAS24・48。ASAS の「最新」は FSAS の初期値(00UTC か 12UTC)と同じ時刻にそろえる。"""
    os.makedirs(OUT, exist_ok=True)
    lst = json.loads(get(LIST))["asia_monochrome"]
    init = fsas_init(lst)
    if init is None:
        raise RuntimeError("FSAS24 と FSAS48 の初期値がそろっていません(FSAS48 の掲載待ち)")
    charts = []
    for back, label in ((48, "48時間前"), (24, "24時間前"), (0, "最新")):
        t = init - timedelta(hours=back)
        png = f"asas_{t:%Y%m%d%H}.png"
        render(f"{BASE}{t:%Y%m}/ASAS_MONO_{t:%Y%m%d%H%M}.pdf", png)
        charts.append((f"ASAS {label}", jst(t), png))
    for ft in (24, 48):
        png = f"fsas{ft}_{init:%Y%m%d%H}.png"
        render(f"{BASE}FSAS{ft}_MONO_ASIA.pdf", png)
        charts.append((f"FSAS{ft} {ft}時間予想", jst(init + timedelta(hours=ft)) + f" 初期値 {init:%d}日{init:%H}UTC", png))
    return charts


def main():
    charts = fetch_charts()

    cells = "".join(
        f'<figure{" class=now" if "最新" in a else ""}><figcaption><b>{a}</b> {b}</figcaption>'
        f'<a href="{p}" target="_blank"><img src="{p}"></a></figure>'
        for a, b, p in charts
    )
    html = f"""<!doctype html><html lang="ja"><meta charset="utf-8"><title>地上天気図 ASAS</title>
<style>
body{{margin:8px;background:#fff;color:#000;font-family:"Yu Gothic UI",sans-serif}}
.g{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}
figure{{margin:0;border:1px solid #999}}
figure.now{{border:6px solid #d00}}
figcaption{{padding:4px 8px;background:#eee;font-size:15px}}
img{{width:100%;display:block}}
</style>
<div class="g">{cells}</div>
<p>画像をクリックすると1枚だけ大きく開きます。出典：気象庁ホームページ</p></html>"""
    path = os.path.join(OUT, "asas_view.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    for a, b, _ in charts:
        print(a, b)
    os.startfile(path)


if __name__ == "__main__":
    main()
