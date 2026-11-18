"""Inject the home page hero copy and promo sections into every locale's index.html.

Copy comes from tools/home_promo/source.json (en, ko) and
tools/home_promo/locales/<site-dir>.json (generated). A locale without copy is
skipped and reported, so a page never shows another language's text.

The sections live between <!-- noticatcher-home-promo:start/end --> markers and
are replaced on every run, so the script is safe to re-run after copy edits.

Usage: python -I tools/home_promo/build.py [site-dir ...]
"""

import html
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = ROOT / "tools/home_promo"
PLAY_URL = "https://play.google.com/store/apps/details?id=com.flutterflow.noticatcher"
CSS_LINK = '<link href="/assets/home-promo.css" rel="stylesheet"/>'
START = "<!-- noticatcher-home-promo:start -->"
END = "<!-- noticatcher-home-promo:end -->"
RTL = {"ar", "fa", "he", "ur"}

FEED_ICONS = ["bx-shopping-bag", "bx-group", "bx-news", "bx-joystick"]
RING_ICON = "bx-message-rounded-dots"
PERSONA_ICONS = ["bx-home-alt", "bx-hash", "bx-line-chart", "bx-phone-call", "bx-package", "bx-credit-card"]


def e(text):
    return html.escape(text, quote=True)


def note_text(n):
    return f'{e(n["before"])}<mark>{e(n["keyword"])}</mark>{e(n["after"])}'


def render(lang, c):
    q, p, s, cta = c["quiet"], c["personas"], c["steps"], c["cta"]

    muted = [
        f'<li class="pn pn--muted"><i aria-hidden="true" class="bx {FEED_ICONS[i]} pn__icon"></i>'
        f'<span class="pn__app">{e(f["app"])}</span><span class="pn__text">{e(f["text"])}</span>'
        f'<span class="pn__state"><i aria-hidden="true" class="bx bx-bell-off"></i>{e(q["mutedLabel"])}</span></li>'
        for i, f in enumerate(q["feed"])
    ]
    r = q["ring"]
    ring = (
        f'<li class="pn pn--ring"><i aria-hidden="true" class="bx {RING_ICON} pn__icon"></i>'
        f'<span class="pn__app">{e(r["app"])}</span><span class="pn__text">{note_text(r)}</span>'
        f'<span class="pn__state"><i aria-hidden="true" class="bx bxs-bell-ring"></i>{e(q["ringLabel"])}</span></li>'
    )
    feed = muted[:2] + [ring] + muted[2:]

    personas = "".join(
        f'<article class="persona"><h3><i aria-hidden="true" class="bx {PERSONA_ICONS[i]}"></i>{e(it["title"])}</h3>'
        f'<p>{e(it["body"])}</p>'
        f'<div class="pn pn--ring pn--mini"><span class="pn__app">{e(it["app"])}</span>'
        f'<span class="pn__text">{note_text(it)}</span></div></article>'
        for i, it in enumerate(p["items"])
    )
    steps = "".join(f'<li><h3>{e(it["title"])}</h3><p>{e(it["body"])}</p></li>' for it in s["items"])
    dir_attr = ' dir="rtl"' if lang in RTL else ""

    return f"""{START}
<div class="promo"{dir_attr}>
<section aria-labelledby="promo-quiet-title" class="promo-quiet">
<div class="promo-quiet__copy">
<h2 id="promo-quiet-title">{e(q["title"])}</h2>
<p>{e(q["body"])}</p>
</div>
<figure class="promo-feed">
<ul class="promo-feed__list">{"".join(feed)}</ul>
<figcaption>{e(q["feedLabel"])}</figcaption>
</figure>
</section>
<section aria-labelledby="promo-personas-title" class="promo-personas">
<h2 id="promo-personas-title">{e(p["title"])}</h2>
<div class="persona-grid">{personas}</div>
<p class="promo-footnote">{e(p["note"])}</p>
</section>
<section aria-labelledby="promo-steps-title" class="promo-steps">
<h2 id="promo-steps-title">{e(s["title"])}</h2>
<ol class="step-list">{steps}</ol>
</section>
<section aria-labelledby="promo-cta-title" class="promo-cta">
<h2 id="promo-cta-title">{e(cta["title"])}</h2>
<p>{e(cta["body"])}</p>
<div class="promo-cta__actions">
<a class="btn btn-primary promo-play" href="{PLAY_URL}" rel="noopener noreferrer" target="_blank"><i aria-hidden="true" class="bx bxl-play-store"></i>{e(cta["play"])}</a>
<a class="btn btn-glass" href="/{lang}/price/">{e(cta["plans"])}</a>
</div>
<p class="promo-cta__privacy"><i aria-hidden="true" class="bx bx-lock-alt"></i>{e(cta["privacy"])}</p>
</section>
</div>
{END}
"""


HERO_RE = re.compile(r'(<div class="hero-badge">)[^<]*(</div>\s*<h1>.*?</h1>\s*)<p[^>]*>.*?</p>', re.S)


def render_hero(h):
    """Badge question and lead paragraph of the hero; one use case per line."""
    cases = "<br/>".join(
        f'{e(c["before"])}<strong class="hero-emphasis">{e(c["emphasis"])}</strong>{e(c["after"])}' for c in h["cases"]
    )
    i = h["intro"]
    lead = (
        f'<p class="hero-lead"><strong class="hero-emphasis">{e(i["before"])}'
        f'<span class="hero-silent">{e(i["highlight"])}</span>{e(i["after"])}</strong><br/>'
        f'{cases}<br/><strong>{e(h["outro"])}</strong></p>'
    )
    return e(h["badge"]), lead


def load_copy():
    source = json.loads((HERE / "source.json").read_text(encoding="utf-8"))
    copies = {k: v for k, v in source.items() if not k.startswith("_")}
    for path in sorted((HERE / "locales").glob("*.json")):
        copies.setdefault(path.stem, json.loads(path.read_text(encoding="utf-8"))["copy"])
    return copies


def inject(page, block, hero):
    with open(page, encoding="utf-8", newline="") as fh:
        text = fh.read()
    if hero:
        badge, lead = hero
        text, count = HERO_RE.subn(lambda m: m.group(1) + badge + m.group(2) + lead, text, count=1)
        if count != 1:
            raise RuntimeError(f"{page}: hero badge/h1/p not found")
    if page.parent.name in RTL:
        # The site has no page-level dir; at least make the hero read right to left.
        text = text.replace('<div class="hero-content">', '<div class="hero-content" dir="rtl">', 1)
    if "\r\n" in text:
        block = block.replace("\n", "\r\n")
    if START in text:
        text = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\r?\n?", lambda _: block, text, flags=re.S)
    else:
        if "<!-- Scripts -->" not in text:
            raise RuntimeError(f"{page}: no <!-- Scripts --> anchor")
        text = text.replace("<!-- Scripts -->", block + "<!-- Scripts -->", 1)
    if CSS_LINK not in text:
        anchor = '<link href="css/lang-widget.css" rel="stylesheet"/>'
        if anchor not in text:
            raise RuntimeError(f"{page}: no lang-widget.css link to anchor the stylesheet")
        text = text.replace(anchor, anchor + "\n" + CSS_LINK, 1)
    with open(page, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def main():
    copies = load_copy()
    dirs = sys.argv[1:] or sorted(p.parent.name for p in ROOT.glob("*/index.html") if (p.parent / "price").is_dir())
    missing = []
    for lang in dirs:
        if lang not in copies:
            missing.append(lang)
            continue
        copy = copies[lang]
        hero = render_hero(copy["hero"]) if "hero" in copy else None
        if hero is None:
            print(f"{lang}: no hero copy yet, hero left unchanged")
        inject(ROOT / lang / "index.html", render(lang, copy), hero)
    print(f"updated {len(dirs) - len(missing)} pages")
    if missing:
        print("no copy yet (skipped):", " ".join(missing))


if __name__ == "__main__":
    main()
