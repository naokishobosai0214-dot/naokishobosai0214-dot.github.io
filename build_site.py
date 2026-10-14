"""「ならべて天気図」のページを作る(GitHub Actions から15分ごとに実行)。

python build_site.py --check   気象庁に新しい図が出たか調べるだけ(公開中の state.json と比べる)。
                               GitHub Actions では changed=true/false を出力に書く
python build_site.py           site\ に index.html・まとめ画像(JPG/PNG)・X投稿用画像・5枚の図・state.json を作る
"""
import html
import json
import os
import re
import shutil
import sys
import urllib.request
from datetime import timedelta

SITE_URL = os.environ.get("SITE_URL", "https://narabete-tenkizu.pages.dev/")
LINE_URL = "https://line.me/R/ti/p/@421edvfx"  # LINE公式アカウント「天気図配信」の友だち追加
HAISHIN = "https://naokishobosai0214-dot.github.io/tenkizu-haishin/"  # LINEで届く並べ図(tenkizu-haishin)
LIST = "https://www.jma.go.jp/bosai/weather_map/data/list.json"
HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def current_key():
    """FSAS24・48 のファイル名(初期値 00/12UTC)。2枚の初期値がそろったときだけ返し、そろっていなければ None。
    ASAS の「最新」はこの初期値と同じ時刻の図を使うので、1日2回(9時・21時の図)だけ作り直す。"""
    lst = json.loads(get(LIST))["asia_monochrome"]
    # ファイル名の2つ目の14桁が初期値(UTC)。check はライブラリを入れる前に動くので asas_view は使わない
    if len({re.findall(r"_(\d{14})_MET", lst[k][-1])[0] for k in ("ft24", "ft48")}) != 1:
        return None
    return {"ft24": lst["ft24"][-1], "ft48": lst["ft48"][-1]}


def published_key():
    try:
        return json.loads(get(SITE_URL + "state.json"))["key"]
    except Exception:
        return None


def check():
    key = current_key()
    changed = key is not None and (os.environ.get("FORCE") == "true" or key != published_key())
    print("changed:", changed)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"changed={'true' if changed else 'false'}\n")


def save_pdf(src, out, dpi=200, margin_mm=8):
    """まとめ画像を A4 横 1ページの PDF にする(余白 8mm・中央寄せ)"""
    from PIL import Image
    w, h = round(297 / 25.4 * dpi), round(210 / 25.4 * dpi)
    m = round(margin_mm / 25.4 * dpi)
    img = Image.open(src).convert("RGB")
    r = min((w - 2 * m) / img.width, (h - 2 * m) / img.height)
    img = img.resize((round(img.width * r), round(img.height * r)), Image.LANCZOS)
    page = Image.new("RGB", (w, h), "white")
    page.paste(img, ((w - img.width) // 2, (h - img.height) // 2))
    page.save(out, "PDF", resolution=dpi)


def line_samples():
    """LINEで届く並べ図(高層の実況 p2・数値予報 p3)の縮小版を site/line/ に置く。取れなくてもページは作る。"""
    from PIL import Image
    import io
    os.makedirs(os.path.join(SITE, "line"))
    try:
        for i, item in enumerate(json.loads(get(HAISHIN + "latest.json"))[1:3], 2):
            im = Image.open(io.BytesIO(get(HAISHIN + item["preview"]))).convert("RGB")
            im.thumbnail((360, 600))
            im.save(os.path.join(SITE, "line", f"p{i}.jpg"), quality=82)
    except Exception as e:
        print("LINEの見本画像を取れませんでした:", e)


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
    save_pdf(os.path.join(SITE, "latest.jpg"), os.path.join(SITE, "latest.pdf"))
    x_post.make_image(charts, os.path.join(SITE, "x_post.jpg"), cta="x")
    line_samples()
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
    page = PAGE.replace("__LINE_URL__", LINE_URL).replace("__STAMP__", stamp).replace("__V__", v).replace("__LINKS__", links)
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
<meta name="description" content="地上天気図の48時間前・24時間前・最新・24時間予想・48時間予想を1枚にまとめて、1日2回（9時・21時の図）お届け。1枚ずつ保存して見比べる手間をなくします。">
<meta property="og:title" content="ならべて天気図">
<meta property="og:description" content="地上天気図 5枚まとめ(最新 __STAMP__)">
<meta property="og:image" content="latest.jpg?v=__V__">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#7cc6f2">
<style>
:root{
  --sky1:#5fb4ec;--sky2:#a9dcf8;--sky3:#eaf7ff;
  --bg:#f6fbff;--card:#ffffff;--fg:#17324d;--muted:#5a7189;--line:#d7e9f6;
  --accent:#0f7fd0;--accent2:#ff9f1c;--now:#e0302b;--save:#06c755;
  --shadow:0 6px 24px rgba(23,80,140,.10);
  --sun:#ffd34d;--cloud:#ffffff;
}
@media (prefers-color-scheme:dark){:root{
  --sky1:#0b1b36;--sky2:#17335e;--sky3:#1d3f6e;
  --bg:#0e1828;--card:#16243a;--fg:#e6effa;--muted:#9fb3cc;--line:#26395a;
  --accent:#5db8ff;--accent2:#ffb648;--now:#ff6159;
  --shadow:0 6px 24px rgba(0,0,0,.35);
  --sun:#f3e6a8;--cloud:#c9d7ea;
}}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);font-family:"BIZ UDPGothic","Hiragino Sans","Yu Gothic UI",sans-serif;line-height:1.75;overflow-x:hidden}
a{color:var(--accent)}
.wrap{max-width:1080px;margin:0 auto;padding:0 16px}

/* ヒーロー */
.hero{position:relative;overflow:hidden;background:linear-gradient(180deg,var(--sky1) 0%,var(--sky2) 55%,var(--sky3) 100%);color:#fff;padding:22px 0 88px}
.brand{display:flex;align-items:center;gap:8px;font-weight:bold;font-size:18px;letter-spacing:.05em;position:relative;z-index:2}
.brand svg{width:28px;height:28px}
.sun{position:absolute;top:-60px;right:-40px;width:260px;height:260px;z-index:0}
.sun circle{fill:var(--sun)}
.sun .rays{stroke:var(--sun);stroke-width:6;stroke-linecap:round;opacity:.55;transform-origin:130px 130px;animation:spin 60s linear infinite}
.cloud{position:absolute;fill:var(--cloud);opacity:.9;z-index:1;animation:drift linear infinite}
.cloud.a{width:180px;top:110px;left:-200px;animation-duration:70s}
.cloud.b{width:120px;top:40px;left:-140px;animation-duration:95s;animation-delay:-40s;opacity:.7}
.cloud.c{width:220px;bottom:24px;left:-240px;animation-duration:85s;animation-delay:-20s;opacity:.8}
@keyframes drift{from{transform:translateX(0)}to{transform:translateX(calc(100vw + 260px))}}
@keyframes spin{to{transform:rotate(360deg)}}
.hero-body{position:relative;z-index:2;margin-top:48px;max-width:640px}
.hero h1{font-size:clamp(28px,6vw,46px);line-height:1.3;margin:0 0 14px;text-shadow:0 2px 12px rgba(10,60,110,.25)}
.hero .lead{font-size:clamp(15px,2.6vw,18px);margin:0 0 22px;text-shadow:0 1px 8px rgba(10,60,110,.25)}
.badge{display:inline-block;background:rgba(255,255,255,.92);color:#17324d;border-radius:999px;padding:4px 14px;font-size:14px;margin-bottom:18px}
.badge b{color:var(--now)}
.cta{display:inline-block;background:var(--accent2);color:#fff;font-weight:bold;font-size:17px;padding:14px 28px;border-radius:999px;text-decoration:none;box-shadow:0 6px 18px rgba(255,140,0,.35)}
.cta:hover{filter:brightness(1.05)}

/* セクション */
section{padding:56px 0 8px}
h2{font-size:clamp(21px,4vw,28px);text-align:center;margin:0 0 6px}
.sub{text-align:center;color:var(--muted);margin:0 0 26px}
.card{background:var(--card);border-radius:18px;box-shadow:var(--shadow);border:1px solid var(--line)}

/* 今日の図 */
#today{margin-top:-56px;position:relative;z-index:3;padding-top:0}
#today .card{padding:18px}
#today h2{text-align:left;font-size:20px;margin:0 0 4px}
#today .stamp{margin:0 0 12px;color:var(--muted);font-size:14px}
#today .stamp b{color:var(--now)}
.main-img{display:block;width:100%;height:auto;border-radius:10px;background:#fff;border:1px solid var(--line)}
.btns{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0 8px}
.btns a,.btns button{flex:1 1 160px;padding:13px;border:0;border-radius:12px;font-size:16px;font-weight:bold;font-family:inherit;text-align:center;text-decoration:none;cursor:pointer;color:#fff;background:var(--accent)}
.btns .png{background:var(--save)}
.hint{font-size:13px;color:var(--muted);margin:0 0 14px}
#today h3{font-size:16px;margin:14px 0 8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px}
.c{display:block;padding:10px 12px;border-radius:12px;background:var(--bg);color:var(--fg);text-decoration:none;border:2px solid var(--line)}
.c.now{border-color:var(--now)}
.c b{display:block}
.c span{font-size:13px;color:var(--muted)}

/* 悩みと解決 */
.pair{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.pair .card{padding:22px}
.pair h3{margin:0 0 12px;font-size:18px}
.pair ul{list-style:none;margin:0;padding:0}
.pair li{position:relative;padding:8px 0 8px 34px;border-top:1px dashed var(--line)}
.pair li:first-child{border-top:0}
.pair li::before{position:absolute;left:0;top:8px;width:24px;height:24px;border-radius:50%;text-align:center;line-height:24px;font-size:13px;font-weight:bold;color:#fff}
.before li::before{content:"！";background:#9aa9b9}
.after{border-color:var(--accent)!important}
.after h3{color:var(--accent)}
.after li::before{content:"✓";background:var(--accent)}

/* こんな方に */
.who{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
.who .card{padding:22px;text-align:center}
.who svg{width:56px;height:56px;margin-bottom:8px}
.who h3{margin:0 0 6px;font-size:17px}
.who p{margin:0;color:var(--muted);font-size:15px;text-align:left}

/* 使い方 */
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;counter-reset:s}
.steps .card{padding:22px;position:relative}
.steps .card::before{counter-increment:s;content:counter(s);position:absolute;top:-14px;left:18px;width:32px;height:32px;border-radius:50%;background:var(--accent2);color:#fff;font-weight:bold;text-align:center;line-height:32px}
.steps h3{margin:6px 0 6px;font-size:17px}
.steps p{margin:0;color:var(--muted);font-size:15px}
.again{text-align:center;margin:34px 0 0}

footer{margin-top:56px;background:linear-gradient(180deg,var(--bg),var(--sky3));padding:28px 0 36px;font-size:12px;color:var(--muted)}
footer .brand{color:var(--fg);font-size:15px;margin-bottom:6px}

/* メニュー(無料→LINE→有料→ツール) */
.plans{display:grid;grid-template-columns:1fr 2fr 1fr;gap:16px;align-items:stretch}
.stack{display:flex;flex-direction:column;gap:16px}
.stack .plan{flex:1}
.plan{padding:22px 18px;display:flex;flex-direction:column}
.plan .tag{align-self:flex-start;font-size:12px;font-weight:bold;border-radius:999px;padding:2px 12px;margin-bottom:10px;color:#fff;background:var(--muted)}
.plan h3{margin:0 0 8px;font-size:17px}
.plan p{margin:0 0 14px;color:var(--muted);font-size:14px;flex:1}
.plan.free .tag{background:var(--accent)}
.plan.line{border:2px solid var(--save)!important;flex-direction:row;gap:18px;align-items:center}
.plan.line .txt{flex:1;display:flex;flex-direction:column;align-self:stretch}
.plan.line .tag{background:var(--save)}
.plan.line ul{margin:0 0 14px;padding:0;list-style:none;font-size:14px;color:var(--muted);flex:1}
.plan.line li{padding:3px 0 3px 22px;position:relative}
.plan.line li::before{content:"✓";position:absolute;left:0;color:var(--save);font-weight:bold}
.plan.paid .tag{background:var(--accent2)}
.stack p{flex:0;margin-bottom:10px}
.plan.free p{flex:0}
.thumb{flex:1;display:flex;align-items:center;margin:0 0 14px}
.thumb img{display:block;width:100%;height:auto;border-radius:10px;border:1px solid var(--line);box-shadow:0 4px 14px rgba(23,80,140,.12);background:#fff}
.plan .go{display:block;text-align:center;padding:11px;border-radius:12px;font-weight:bold;text-decoration:none;color:#fff;background:var(--accent)}
.plan.line .go{background:var(--save)}
.plan .soon{display:block;text-align:center;padding:8px;border-radius:12px;font-size:13px;font-weight:bold;color:var(--muted);background:var(--bg);border:1px dashed var(--line)}
.line-btn{display:inline-block;background:var(--save);color:#fff;font-weight:bold;font-size:17px;padding:14px 28px;border-radius:999px;text-decoration:none;box-shadow:0 6px 18px rgba(6,199,85,.3)}
.again{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}

/* LINEで届くイメージ(スマホのトーク画面) */
.phone{flex:0 0 210px;width:210px;height:380px;border-radius:30px;background:#1d2633;padding:9px;box-shadow:0 10px 28px rgba(10,40,80,.25);position:relative}
.phone .scr{height:100%;border-radius:22px;overflow:hidden;background:#8cabd8;display:flex;flex-direction:column;font-size:10.5px;line-height:1.5;color:#1a1a1a}
.ph-head{background:#2b3a55;color:#fff;font-weight:bold;padding:12px 12px 8px;font-size:11.5px}
.ph-body{flex:1;padding:8px;display:flex;flex-direction:column;gap:7px;overflow:hidden}
.msg{display:flex;gap:5px;align-items:flex-start}
.av{flex:0 0 22px;height:22px;border-radius:50%;background:#fff;display:grid;place-items:center;font-size:12px}
.av.blank{visibility:hidden}
.bub{background:#fff;border-radius:12px;padding:6px 9px;max-width:150px}
.pics{display:flex;gap:4px}
.pics img{display:block;height:118px;border-radius:9px;background:#fff;object-fit:cover;object-position:top}
.pics img.tall{width:38px}
.pics img.wide{width:100px}
.bub.link{color:#0b63c4;font-weight:bold}
.ph-menu{display:grid;grid-template-columns:repeat(3,1fr);background:#fff;border-top:1px solid #ddd}
.ph-menu span{text-align:center;padding:9px 0 12px;font-size:10px;font-weight:bold;color:#2b3a55;border-left:1px solid #eee}
.ph-menu span:first-child{border-left:0}
@media (prefers-color-scheme:dark){.phone{background:#000}}
@media (max-width:960px){.plans{grid-template-columns:1fr 1fr}.plan.line{grid-column:1 / -1}.stack{grid-column:1 / -1;flex-direction:row}}
@media (max-width:560px){.plans{grid-template-columns:1fr}.plan.line{flex-direction:column}.phone{flex-basis:auto;margin:4px auto 0}.stack{flex-direction:column}}

@media (max-width:760px){
  .pair,.who,.steps{grid-template-columns:1fr}
  .steps{gap:26px}
  .sun{width:190px;height:190px;top:-50px;right:-50px}
  .hero{padding-bottom:76px}
  .hero-body{margin-top:30px}
}
@media (prefers-reduced-motion:reduce){
  html{scroll-behavior:auto}
  .cloud,.sun .rays{animation:none}
  .cloud.a{left:8%}.cloud.b{left:45%}.cloud.c{left:62%}
}
</style>
</head>
<body>

<header class="hero">
  <svg class="sun" viewBox="0 0 260 260" aria-hidden="true">
    <g class="rays">
      <line x1="130" y1="10" x2="130" y2="40"/><line x1="130" y1="220" x2="130" y2="250"/>
      <line x1="10" y1="130" x2="40" y2="130"/><line x1="220" y1="130" x2="250" y2="130"/>
      <line x1="45" y1="45" x2="66" y2="66"/><line x1="194" y1="194" x2="215" y2="215"/>
      <line x1="45" y1="215" x2="66" y2="194"/><line x1="194" y1="66" x2="215" y2="45"/>
    </g>
    <circle cx="130" cy="130" r="62"/>
  </svg>
  <svg class="cloud a" viewBox="0 0 200 100" aria-hidden="true"><path d="M50 90h110a30 30 0 0 0 0-60 42 42 0 0 0-78-8A34 34 0 0 0 50 90z"/></svg>
  <svg class="cloud b" viewBox="0 0 200 100" aria-hidden="true"><path d="M50 90h110a30 30 0 0 0 0-60 42 42 0 0 0-78-8A34 34 0 0 0 50 90z"/></svg>
  <svg class="cloud c" viewBox="0 0 200 100" aria-hidden="true"><path d="M50 90h110a30 30 0 0 0 0-60 42 42 0 0 0-78-8A34 34 0 0 0 50 90z"/></svg>
  <div class="wrap">
    <div class="brand">
      <svg viewBox="0 0 32 32" aria-hidden="true"><rect x="2" y="7" width="8" height="18" rx="2" fill="#fff" opacity=".7"/><rect x="12" y="7" width="8" height="18" rx="2" fill="#fff"/><rect x="22" y="7" width="8" height="18" rx="2" fill="#fff" opacity=".7"/></svg>
      ならべて天気図
    </div>
    <div class="hero-body">
      <span class="badge">最新の実況：<b>__STAMP__</b></span>
      <h1>天気図、もう<br>1枚ずつ並べなくていい。</h1>
      <p class="lead">地上天気図の 48時間前・24時間前・最新・24時間予想・48時間予想 を、左から右へ時間の流れどおり1枚にまとめて、1日2回お届けします。集めて並べる準備はおまかせ、あなたは解析に集中するだけ。</p>
      <a class="cta" href="#today">今日のならべて天気図を見る</a>
    </div>
  </div>
</header>

<main>
<section id="today">
  <div class="wrap"><div class="card">
    <h2>今日のならべて天気図</h2>
    <p class="stamp">最新の実況：<b>__STAMP__</b>　9時・21時（数値予報の初期値と同じ時刻）の図で、予想図がそろいしだい自動で新しくなります</p>
    <a href="latest.jpg?v=__V__" target="_blank"><img class="main-img" src="latest.jpg?v=__V__" alt="地上天気図5枚まとめ（ASAS 48時間前・24時間前・最新、FSAS24・FSAS48）"></a>
    <div class="btns">
      <a class="png" href="latest.png?v=__V__" download="narabete_tenkizu___V__.png">PNGで保存</a>
      <a class="pdf" href="latest.pdf?v=__V__" download="narabete_tenkizu___V__.pdf">PDFで保存</a>
    </div>
    <p class="hint">LINEの中で保存できないときは、画像を長押しして保存するか、右上のメニューから「ブラウザで開く」を選んでください。</p>
    <h3>1枚ずつ大きく見る</h3>
    <div class="grid">__LINKS__</div>
  </div></div>
</section>

<section class="pr">
  <div class="wrap">
    <h2>集めて、並べる。その準備に時間を取られていませんか？</h2>
    <p class="sub">本当に時間をかけたいのは、天気図を読み解くこと。準備はならべて天気図にまかせてください。</p>
    <div class="pair">
      <div class="card before">
        <h3>これまで</h3>
        <ul>
          <li>気象庁のホームページから、実況図と予想図を1枚ずつ開いて取り寄せている</li>
          <li>48時間前・24時間前の図までさかのぼって探し、集めるだけでひと手間</li>
          <li>集めた図を時刻の順に並べ替えて、ようやく解析を始められる</li>
        </ul>
      </div>
      <div class="card after">
        <h3>ならべて天気図なら</h3>
        <ul>
          <li>取り寄せ・並べ替えはおまかせ。ページを開いた瞬間から解析に入れる</li>
          <li>過去 → 最新 → 予想 が左から右へ、矢印つきで1枚に並んでいる</li>
          <li>最新の実況は数値予報の初期値（9時・21時）にそろえてあるので、予想図とそのまま読み比べられる</li>
        </ul>
      </div>
    </div>
  </div>
</section>

<section class="pr">
  <div class="wrap">
    <h2>こんな方に</h2>
    <p class="sub">準備の時間を、天気図を読む時間に。</p>
    <div class="who">
      <div class="card">
        <svg viewBox="0 0 56 56" aria-hidden="true"><circle cx="28" cy="28" r="26" fill="var(--sky3)"/><circle cx="22" cy="24" r="9" fill="var(--accent2)"/><path d="M20 40h18a7 7 0 0 0 0-14 10 10 0 0 0-18 3 6 6 0 0 0 0 11z" fill="var(--accent)"/></svg>
        <h3>天気が好きな方</h3>
        <p>図を集める手間なしで、低気圧や前線がどう動いてきたか、どこへ向かうのかを追うことに集中できます。</p>
      </div>
      <div class="card">
        <svg viewBox="0 0 56 56" aria-hidden="true"><circle cx="28" cy="28" r="26" fill="var(--sky3)"/><path d="M14 18h12a4 4 0 0 1 4 4v18a3 3 0 0 0-3-3H14z" fill="var(--accent)"/><path d="M42 18H30a4 4 0 0 0-4 4v18a3 3 0 0 1 3-3h13z" fill="var(--accent)" opacity=".7"/></svg>
        <h3>予報士試験を受ける方</h3>
        <p>実況図と予想図を読み解く練習を、毎日の習慣に。図を集める時間を、解析の勉強の時間に変えられます。</p>
      </div>
      <div class="card">
        <svg viewBox="0 0 56 56" aria-hidden="true"><circle cx="28" cy="28" r="26" fill="var(--sky3)"/><rect x="15" y="17" width="26" height="22" rx="3" fill="var(--accent)"/><path d="M19 33l6-6 4 4 8-8" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <h3>予報士・気象のお仕事の方</h3>
        <p>天気図を集めて並べる下準備を省いて、解析と判断に力を注げます。</p>
      </div>
    </div>
  </div>
</section>

<section class="pr" id="menu">
  <div class="wrap">
    <h2>ならべて天気図のメニュー</h2>
    <p class="sub">まずは地上天気図から。もっと読み込みたい方には、高層・数値予報の並べ図を自動でお届けします。</p>
    <div class="plans">
      <div class="card plan free">
        <span class="tag">無料・このページ</span>
        <h3>地上天気図の並べ図</h3>
        <p>ASAS 48時間前・24時間前・最新、FSAS 24・48時間予想の5枚。ページを開くだけで見られます。</p>
        <a class="thumb" href="#today"><img src="latest.jpg?v=__V__" alt="地上天気図の並べ図のイメージ" loading="lazy"></a>
        <a class="go" href="#today">今日の図を見る</a>
      </div>
      <div class="card plan line">
        <div class="txt">
          <span class="tag">LINE登録で無料</span>
          <h3>高層・数値予報の並べ図が、LINEに自動で届く</h3>
          <ul>
            <li>高層天気図の実況の並べ図（200hPa → 地上）</li>
            <li>数値予報天気図の並べ図（12〜48時間予想）</li>
            <li>1日2回、図がそろうと自動で届く</li>
            <li>PDFでまとめて保存。メニューからいつでも開ける</li>
          </ul>
          <a class="go" href="__LINE_URL__" target="_blank" rel="noopener">LINEで友だち追加</a>
        </div>
        <div class="phone" aria-label="LINEに届くイメージ" role="img">
          <div class="scr">
            <div class="ph-head">‹　天気図配信</div>
            <div class="ph-body">
              <div class="msg"><span class="av">☀</span><div class="bub">最新の天気図がそろいました。高層の実況と数値予報の並べ図です。</div></div>
              <div class="msg"><span class="av blank"></span><div class="pics"><img class="tall" src="line/p2.jpg" alt="" onerror="this.style.visibility='hidden'"><img class="wide" src="line/p3.jpg" alt="" onerror="this.style.visibility='hidden'"></div></div>
              <div class="msg"><span class="av blank"></span><div class="bub link">PDFでまとめて保存 ›</div></div>
            </div>
            <div class="ph-menu"><span>地上</span><span>実況</span><span>数値予報</span></div>
          </div>
        </div>
      </div>
      <div class="stack">
        <div class="card plan paid">
          <span class="tag">有料・準備中</span>
          <h3>解析の補助つき</h3>
          <p>特定の等高度線をなぞる、相当温位(K)に色を付けるなど、解析の手がかりを書き込んだ並べ図。</p>
          <span class="soon">LINEで先行してご案内します</span>
        </div>
        <div class="card plan">
          <span class="tag">今後</span>
          <h3>自分で描けるツール</h3>
          <p>線の引き方や色分けを、自分の思うように設定して描けるツール。</p>
          <span class="soon">準備中</span>
        </div>
      </div>
    </div>
  </div>
</section>

<section class="pr">
  <div class="wrap">
    <h2>使い方は 3ステップ</h2>
    <p class="sub">登録もアプリも要りません。</p>
    <div class="steps">
      <div class="card"><h3>ページを開く</h3><p>このページをブックマークしておけば、いつでも最新のまとめが開きます。</p></div>
      <div class="card"><h3>見比べる</h3><p>左の列が48時間前・24時間前、真ん中が最新（赤枠）、右の列が24時間予想・48時間予想。矢印に沿って見るだけです。</p></div>
      <div class="card"><h3>保存する</h3><p>「PNGで保存」か「PDFで保存」を押すだけ。タブレットに入れて、解析の書き込みにも。</p></div>
    </div>
    <p class="again"><a class="cta" href="#today">今日のならべて天気図を見る</a><a class="line-btn" href="__LINE_URL__" target="_blank" rel="noopener">高層・数値予報はLINEで自動で届く</a></p>
  </div>
</section>
</main>

<footer>
  <div class="wrap">
    <div class="brand">ならべて天気図</div>
    出典：気象庁ホームページ（地上天気図）を加工して作成。編集・加工の責任はならべて天気図にあります。天気図は気象庁の発表内容をそのまま並べたもので、独自の予報ではありません。
  </div>
</footer>
</body>
</html>
"""

if __name__ == "__main__":
    check() if "--check" in sys.argv else build()
