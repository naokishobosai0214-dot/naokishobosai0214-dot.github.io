"""「ならべて天気図」のページを作る(GitHub Actions から15分ごとに実行)。

python build_site.py --check   気象庁に新しい図が出たか調べるだけ(公開中の state.json と比べる)。
                               GitHub Actions では changed=true/false を出力に書く
python build_site.py           site\ に index.html・まとめ画像(JPG/PNG)・X投稿用画像・5枚の図・state.json を作る
"""
import html
import json
import os
import shutil
import sys
import urllib.request
from datetime import timedelta

SITE_URL = os.environ.get("SITE_URL", "https://naokishobosai0214-dot.github.io/")
LIST = "https://www.jma.go.jp/bosai/weather_map/data/list.json"
HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def current_key():
    """最新ASAS・FSAS24・FSAS48 のファイル名。どれかが変われば作り直す。"""
    lst = json.loads(get(LIST))["asia_monochrome"]
    return {"asas": lst["now"][-1], "ft24": lst["ft24"][-1], "ft48": lst["ft48"][-1]}


def published_key():
    try:
        return json.loads(get(SITE_URL + "state.json"))["key"]
    except Exception:
        return None


def check():
    changed = os.environ.get("FORCE") == "true" or current_key() != published_key()
    print("changed:", changed)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"changed={'true' if changed else 'false'}\n")


def build():
    import asas_view
    import x_post
    from PIL import Image

    key = current_key()
    work = os.path.join(HERE, "work")
    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(SITE, ignore_errors=True)
    os.makedirs(os.path.join(SITE, "charts"))
    asas_view.OUT = work
    charts = asas_view.fetch_charts()

    latest = x_post.make_image(charts, os.path.join(SITE, "latest.jpg"), cta="page", url=SITE_URL.replace("https://", ""))
    Image.open(os.path.join(SITE, "latest.jpg")).save(os.path.join(SITE, "latest.png"), optimize=True)
    x_post.make_image(charts, os.path.join(SITE, "x_post.jpg"), cta="x")
    items = []
    for title, when, png in charts:
        name = png.replace(".png", ".jpg")
        Image.open(os.path.join(work, png)).convert("RGB").save(os.path.join(SITE, "charts", name), quality=88)
        items.append((title, when, name))

    j = latest + timedelta(hours=9)
    stamp = f"{j.year}年{j.month}月{j.day}日 {j.hour}時"
    v = latest.strftime("%Y%m%d%H") + key["ft24"][-20:-4]
    links = "".join(
        f'<a class="c{" now" if "最新" in t else ""}" href="charts/{n}?v={v}" target="_blank">'
        f'<b>{html.escape(t)}</b><span>{html.escape(w)}</span></a>'
        for t, w, n in items
    )
    page = PAGE.replace("__STAMP__", stamp).replace("__V__", v).replace("__LINKS__", links)
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    with open(os.path.join(SITE, "state.json"), "w", encoding="utf-8") as f:
        json.dump({"key": key, "latest_utc": latest.strftime("%Y-%m-%d %H:00")}, f, ensure_ascii=False)
    with open(os.path.join(SITE, ".nojekyll"), "w") as f:
        pass
    print("built", stamp, key)


PAGE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ならべて天気図</title>
<meta name="description" content="気象予報士・受験生のための地上天気図5枚まとめ(ASAS・FSAS)。毎日3:40/15:40ごろ更新。">
<meta property="og:title" content="ならべて天気図">
<meta property="og:description" content="地上天気図 5枚まとめ(最新 __STAMP__)">
<meta property="og:image" content="latest.jpg?v=__V__">
<meta name="twitter:card" content="summary_large_image">
<style>
:root{--navy:#102a54;--red:#d00000;--bg:#f3f5f8;--fg:#1a1a1a;--card:#fff;--muted:#555}
@media (prefers-color-scheme:dark){:root{--bg:#10151d;--fg:#e8ecf2;--card:#1b2330;--muted:#a8b2c0}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:"BIZ UDPGothic","Hiragino Sans","Yu Gothic UI",sans-serif;line-height:1.6}
header{background:var(--navy);color:#fff;padding:12px 16px}
header h1{margin:0;font-size:22px}
header p{margin:2px 0 0;font-size:14px;opacity:.85}
main{max-width:1200px;margin:0 auto;padding:16px}
.stamp{font-size:15px;margin:0 0 10px}
.stamp b{color:var(--red)}
.main-img{display:block;width:100%;height:auto;border-radius:6px;box-shadow:0 1px 6px rgba(0,0,0,.25);background:#fff}
.btns{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}
.btns a,.btns button{flex:1 1 140px;padding:12px;border:0;border-radius:8px;font-size:16px;font-weight:bold;text-align:center;text-decoration:none;cursor:pointer;color:#fff;background:var(--navy)}
.btns .png{background:#06c755}
.hint{font-size:13px;color:var(--muted);margin:0 0 18px}
h2{font-size:17px;margin:22px 0 8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px}
.c{display:block;padding:10px;border-radius:8px;background:var(--card);color:var(--fg);text-decoration:none;border:2px solid transparent}
.c.now{border-color:var(--red)}
.c b{display:block}
.c span{font-size:13px;color:var(--muted)}
footer{font-size:12px;color:var(--muted);padding:16px;max-width:1200px;margin:0 auto}
@media print{
  @page{size:A4 landscape;margin:8mm}
  body{background:#fff}
  header,.btns,.hint,h2,.grid,footer,.stamp{display:none}
  main{padding:0;max-width:none}
  .main-img{box-shadow:none;border-radius:0}
}
</style>
</head>
<body>
<header><h1>ならべて天気図</h1><p>気象予報士・受験生のための 地上天気図5枚まとめ</p></header>
<main>
<p class="stamp">最新の実況：<b>__STAMP__</b>（毎日 3:40 / 15:40 ごろ自動更新）</p>
<a href="latest.jpg?v=__V__" target="_blank"><img class="main-img" src="latest.jpg?v=__V__" alt="地上天気図5枚まとめ（ASAS 24時間前・12時間前・最新、FSAS24・FSAS48）"></a>
<div class="btns">
  <a class="png" href="latest.png?v=__V__" download="narabete_tenkizu___V__.png">PNGで保存</a>
  <button type="button" onclick="window.print()">印刷する（A4横）</button>
</div>
<p class="hint">LINEの中で保存できないときは、画像を長押しして保存するか、右上のメニューから「ブラウザで開く」を選んでください。</p>
<h2>1枚ずつ大きく見る</h2>
<div class="grid">__LINKS__</div>
</main>
<footer>出典：気象庁ホームページ（地上天気図）を加工して作成。編集・加工の責任はならべて天気図にあります。天気図は気象庁の発表内容をそのまま並べたもので、独自の予報ではありません。</footer>
</body>
</html>
"""

if __name__ == "__main__":
    check() if "--check" in sys.argv else build()
