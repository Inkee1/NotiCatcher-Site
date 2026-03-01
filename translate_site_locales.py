#!/usr/bin/env python3
"""
Translate this static site into multiple locales.

Source:  NotiSite3/en/  (HTML + css/js assets)
Output:  NotiSite3/<lang>/...  (folder-per-language, same structure as /en/)

Languages are discovered from NotiCatcher Flutter ARB files:
  C:\\Users\\home\\Desktop\\DIV_ALARM\\NotiCatcher\\lib\\l10n\\app_*.arb

Requirements:
  pip install -r requirements.i18n.txt
  set OPENAI_API_KEY=YOUR_KEY

Examples:
  python translate_site_locales.py --languages all
  python translate_site_locales.py --languages ja zh-hans fr de
  python translate_site_locales.py --dry-run --languages all
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from bs4 import BeautifulSoup
from bs4.element import Tag

try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore


DEFAULT_DOMAIN = "https://noticatcher.com"
ROOT_INDEX_RELATIVE_PATH = Path("index.html")


RE_LOCALE_DIR = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$")


def discover_existing_site_locales(site_root: Path) -> List[str]:
    """
    Return locale folders that actually exist on disk and have <locale>/index.html.
    (This avoids emitting hreflang to locales that were not generated.)
    """
    out: List[str] = []
    for p in site_root.iterdir():
        if not p.is_dir():
            continue
        name = p.name.strip().lower()
        if not RE_LOCALE_DIR.fullmatch(name):
            continue
        if (p / "index.html").exists() and name not in out:
            out.append(name)
    out.sort()
    return out


def update_root_index_supported_languages(root_index_path: Path, locales: List[str], *, dry_run: bool) -> None:
    """
    Update `const SUPPORTED = [...]` inside the root index.html language redirect script.
    Uses only locales that currently exist (folders), so it won't redirect users into 404s.
    """
    if not root_index_path.exists():
        return

    html = root_index_path.read_text(encoding="utf-8")
    # Normalize and ensure 'en' present first (fallback behavior relies on it).
    uniq: List[str] = []
    for loc in ["en"] + locales:
        loc = (loc or "").strip().lower()
        if not loc:
            continue
        if loc not in uniq:
            uniq.append(loc)

    supported_js = ", ".join(json.dumps(x) for x in uniq)
    replacement = f"const SUPPORTED = [{supported_js}];"

    new_html, n = re.subn(r"const\s+SUPPORTED\s*=\s*\[[^\]]*\]\s*;", replacement, html, count=1, flags=re.DOTALL)
    if n == 0:
        # No SUPPORTED constant found; do nothing.
        return

    if dry_run:
        print(f"[dry-run] would update {root_index_path} SUPPORTED => {uniq}")
        return
    root_index_path.write_text(new_html, encoding="utf-8")


def generate_sitemap(site_root: Path, *, domain: str, include_locales: List[str], dry_run: bool) -> None:
    """
    Generate sitemap.xml from existing locale folders and their index.html pages.
    Only includes pages that exist on disk.
    """
    urls: List[str] = []
    domain = domain.rstrip("/")

    for loc in include_locales:
        base = site_root / loc
        if not (base / "index.html").exists():
            continue
        for f in sorted(base.rglob("index.html")):
            rel = _page_path_from_file(site_root, f)  # e.g. fr/price/
            loc_url = f"{domain}/{rel.lstrip('/')}"
            if not loc_url.endswith("/"):
                loc_url += "/"
            if loc_url not in urls:
                urls.append(loc_url)

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for u in urls:
        xml_lines.append("  <url>")
        xml_lines.append(f"    <loc>{u}</loc>")
        xml_lines.append("  </url>")
    xml_lines.append("</urlset>")
    xml = "\n".join(xml_lines) + "\n"

    sitemap_path = site_root / "sitemap.xml"
    if dry_run:
        print(f"[dry-run] would write {sitemap_path} with {len(urls)} urls")
        return
    sitemap_path.write_text(xml, encoding="utf-8")


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _copy_tree(source: Path, dest: Path, *, overwrite: bool) -> None:
    if dest.exists():
        if overwrite:
            shutil.rmtree(dest)
        else:
            return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, dest)


def _arb_to_folder_locale(arb_locale: str) -> str:
    # Flutter ARB uses underscore for region/script. Convert to URL-friendly BCP47-ish folder code.
    # Examples:
    #   pt_BR -> pt-br
    #   es_419 -> es-419
    #   zh_Hans -> zh-hans
    #   zh_Hant -> zh-hant
    s = arb_locale.strip()
    if not s:
        return ""
    s = s.replace("_", "-")
    return s.lower()


def discover_locales_from_arb(l10n_dir: Path) -> List[str]:
    # app_en.arb, app_ko.arb, app_pt_BR.arb, ...
    locales: List[str] = []
    for p in sorted(l10n_dir.glob("app_*.arb")):
        name = p.stem  # app_xx or app_xx_YY
        raw = name[len("app_") :]
        # Prefer @@locale inside ARB if present, else filename.
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("@@locale"), str) and data.get("@@locale"):
                raw = str(data["@@locale"])
        except Exception:
            pass
        loc = _arb_to_folder_locale(raw)
        if loc and loc not in locales:
            locales.append(loc)
    return locales


# --- Translation extraction rules (adapted from Site2 script) ---

RE_HAS_LATIN = re.compile(r"[A-Za-z]")
RE_URL_LIKE = re.compile(r"^(https?://|mailto:|tel:)", re.IGNORECASE)
RE_WHITESPACE = re.compile(r"\s+")
RE_ANY_TAG = re.compile(r"<[^>]+>")

SKIP_TEXT_PARENT_TAGS = {"script", "style", "noscript", "svg", "code", "pre", "textarea"}
TRANSLATABLE_ELEMENT_TAGS = {"title", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "p", "li", "a", "button", "label", "option", "div", "span"}
INLINE_ALLOWED_TAGS = {"br", "strong", "em", "b", "i", "u", "span", "small", "sup", "sub", "wbr"}
ATTRS_TO_TRANSLATE = {"title", "placeholder", "aria-label", "alt", "value"}
META_KEYS_TO_TRANSLATE = {"description", "og:title", "og:description", "twitter:title", "twitter:description"}

PROTECT_TERMS = [
    "NotiCatcher",
    "Google Play",
    "App Store",
    "Firebase",
    "Stripe",
    "TradingView",
    "RSI",
    "EMA",
    "USDT",
]

PLACEHOLDER_PATTERNS = [
    re.compile(r"\$\{[^}]+\}"),
    re.compile(r"\{\{[^}]+\}\}"),
    re.compile(r"\{[0-9]+\}"),
    re.compile(r"%\([^)]+\)s"),
    re.compile(r"%s"),
]


def _normalize_spaces(text: str) -> str:
    return RE_WHITESPACE.sub(" ", text).strip()


def _split_ws(text: str) -> Tuple[str, str, str]:
    m1 = re.match(r"^\s*", text)
    m2 = re.search(r"\s*$", text)
    pre = text[: m1.end()] if m1 else ""
    suf = text[m2.start() :] if m2 else ""
    core = text[len(pre) : len(text) - len(suf)]
    return pre, core, suf


def _inner_html(tag: Tag) -> str:
    return "".join(str(x) for x in tag.contents)


def _canonicalize_fragment(fragment: str) -> str:
    if not fragment:
        return ""
    parts: List[str] = []
    last = 0
    for m in RE_ANY_TAG.finditer(fragment):
        text_part = fragment[last : m.start()]
        if text_part:
            parts.append(RE_WHITESPACE.sub(" ", text_part))
        parts.append(m.group(0))
        last = m.end()
    tail = fragment[last:]
    if tail:
        parts.append(RE_WHITESPACE.sub(" ", tail))
    out = "".join(parts).strip()
    out = re.sub(r"\s{2,}", " ", out)
    return out


def _should_translate_text(text: str) -> bool:
    if not text:
        return False
    t = text.strip()
    if not t:
        return False
    if RE_URL_LIKE.match(t):
        return False
    if not RE_HAS_LATIN.search(t):
        return False
    return True


def _is_inside_skipped(tag: Tag) -> bool:
    p: Optional[Tag] = tag
    while p is not None:
        name = (p.name or "").lower()
        if name in SKIP_TEXT_PARENT_TAGS:
            return True
        p = p.parent if isinstance(p.parent, Tag) else None
    return False


def _is_leaf_translatable(tag: Tag) -> bool:
    name = (tag.name or "").lower()
    if name not in TRANSLATABLE_ELEMENT_TAGS:
        return False
    if _is_inside_skipped(tag):
        return False
    txt = tag.get_text(" ", strip=True)
    if not _should_translate_text(txt):
        return False
    # Leaf rule: only inline children
    for child in tag.find_all(True, recursive=False):
        if not isinstance(child, Tag):
            continue
        child_name = (child.name or "").lower()
        if child_name in INLINE_ALLOWED_TAGS:
            continue
        return False
    return True


def _iter_leaf_translatables(soup: BeautifulSoup) -> Iterable[Tag]:
    for tag in soup.find_all(True):
        if isinstance(tag, Tag) and _is_leaf_translatable(tag):
            yield tag


@dataclass(frozen=True)
class ItemRef:
    key: str
    src: str
    hint: str


def _protect_text(text: str, *, unique_prefix: str) -> Tuple[str, Dict[str, str]]:
    mapping: Dict[str, str] = {}
    protected = text
    counter = 0

    def add_token(original: str) -> str:
        nonlocal counter
        token = f"__K_{unique_prefix}_{counter}__"
        counter += 1
        mapping[token] = original
        return token

    for pattern in PLACEHOLDER_PATTERNS:
        while True:
            m = pattern.search(protected)
            if not m:
                break
            original = m.group(0)
            token = add_token(original)
            protected = protected[: m.start()] + token + protected[m.end() :]

    for term in PROTECT_TERMS:
        start = 0
        while True:
            idx = protected.find(term, start)
            if idx == -1:
                break
            token = add_token(term)
            protected = protected[:idx] + token + protected[idx + len(term) :]
            start = idx + len(token)

    return protected, mapping


def _unprotect_text(text: str, mapping: Dict[str, str]) -> str:
    out = text
    for token, original in mapping.items():
        out = out.replace(token, original)
    return out


def _ensure_all_tokens_present(translated: str, mapping: Dict[str, str]) -> bool:
    return all(token in translated for token in mapping.keys())


def _validate_allowed_inline_fragment(fragment_html: str) -> bool:
    if "<" not in fragment_html and ">" not in fragment_html:
        return True
    soup = BeautifulSoup(fragment_html, "html.parser")
    for t in soup.find_all(True):
        name = (t.name or "").lower()
        if name not in INLINE_ALLOWED_TAGS:
            return False
        for attr in list(t.attrs.keys()):
            if attr.lower().startswith("on"):
                return False
        if "href" in t.attrs or "src" in t.attrs:
            return False
    return True


def collect_items_from_html(html: str, *, file_hint: str) -> List[ItemRef]:
    soup = BeautifulSoup(html, "html.parser")
    items: Dict[str, ItemRef] = {}

    for tag in _iter_leaf_translatables(soup):
        name = (tag.name or "").lower()
        if name == "title":
            src = _normalize_spaces(tag.get_text(" ", strip=True))
            if src:
                key = _sha1(src)
                items.setdefault(key, ItemRef(key=key, src=src, hint=f"{file_hint} | <title>"))
            continue

        fragment = _canonicalize_fragment(_inner_html(tag))
        if not fragment:
            continue
        key = _sha1(fragment)
        if key not in items:
            hint = f"{file_hint} | <{name}>"
            items[key] = ItemRef(key=key, src=fragment, hint=hint)

    for tag in soup.find_all(True):
        if not isinstance(tag, Tag):
            continue
        tag_name = (tag.name or "").lower()

        if tag_name == "meta" and tag.has_attr("content"):
            meta_key = (tag.get("property") or tag.get("name") or "").strip().lower()
            if meta_key in META_KEYS_TO_TRANSLATE:
                raw_val = str(tag.get("content") or "")
                if _should_translate_text(raw_val):
                    _, core, _ = _split_ws(raw_val)
                    core_norm = _normalize_spaces(core)
                    if core_norm:
                        key = _sha1(core_norm)
                        items.setdefault(key, ItemRef(key=key, src=core_norm, hint=f"{file_hint} | meta[{meta_key}]"))

        for attr in ATTRS_TO_TRANSLATE:
            if not tag.has_attr(attr):
                continue
            raw_val = tag.get(attr)
            if raw_val is None:
                continue
            if isinstance(raw_val, list):
                raw_val = " ".join(str(x) for x in raw_val)
            raw_val = str(raw_val)
            if not _should_translate_text(raw_val):
                continue
            _, core, _ = _split_ws(raw_val)
            core_norm = _normalize_spaces(core)
            if not core_norm:
                continue
            key = _sha1(core_norm)
            items.setdefault(key, ItemRef(key=key, src=core_norm, hint=f"{file_hint} | <{tag_name}> @{attr}"))

    return list(items.values())


def apply_translations_to_html(html: str, *, lang_code: str, translations: Dict[str, str]) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in _iter_leaf_translatables(soup):
        name = (tag.name or "").lower()
        if name == "title":
            src = _normalize_spaces(tag.get_text(" ", strip=True))
            if not src:
                continue
            key = _sha1(src)
            dst = translations.get(key)
            if dst:
                tag.string = dst
            continue

        fragment = _canonicalize_fragment(_inner_html(tag))
        if not fragment:
            continue
        key = _sha1(fragment)
        dst = translations.get(key)
        if not dst:
            continue
        tag.clear()
        frag_soup = BeautifulSoup(dst, "html.parser")
        for child in list(frag_soup.contents):
            tag.append(child)

    for tag in soup.find_all(True):
        if not isinstance(tag, Tag):
            continue
        tag_name = (tag.name or "").lower()

        if tag_name == "meta" and tag.has_attr("content"):
            meta_key = (tag.get("property") or tag.get("name") or "").strip().lower()
            if meta_key in META_KEYS_TO_TRANSLATE:
                raw_val = str(tag.get("content") or "")
                if _should_translate_text(raw_val):
                    pre, core, suf = _split_ws(raw_val)
                    core_norm = _normalize_spaces(core)
                    if core_norm:
                        key = _sha1(core_norm)
                        dst = translations.get(key)
                        if dst:
                            tag["content"] = pre + dst + suf

        for attr in ATTRS_TO_TRANSLATE:
            if not tag.has_attr(attr):
                continue
            raw_val = tag.get(attr)
            if raw_val is None:
                continue
            if isinstance(raw_val, list):
                raw_val = " ".join(str(x) for x in raw_val)
            raw_val = str(raw_val)
            if not _should_translate_text(raw_val):
                continue
            pre, core, suf = _split_ws(raw_val)
            core_norm = _normalize_spaces(core)
            if not core_norm:
                continue
            key = _sha1(core_norm)
            dst = translations.get(key)
            if dst:
                tag[attr] = pre + dst + suf

    html_tag = soup.find("html")
    if isinstance(html_tag, Tag):
        html_tag["lang"] = lang_code  # folder code; close enough for most hreflang use

    return str(soup)


# --- Locale URL + hreflang helpers ---


def _page_path_from_file(site_root: Path, html_file: Path) -> str:
    rel = html_file.relative_to(site_root).as_posix()
    # e.g. en/index.html -> en/
    #      en/price/index.html -> en/price/
    if rel.endswith("/index.html"):
        return rel[: -len("index.html")]
    if rel.endswith("index.html"):
        return rel[: -len("index.html")]
    return rel


def _set_or_replace_canonical_and_hreflang(
    html: str,
    *,
    domain: str,
    page_rel_from_root: str,
    all_langs: List[str],
    x_default: str,
) -> str:
    """
    page_rel_from_root example: 'fr/price/' or 'en/'.
    """
    soup = BeautifulSoup(html, "html.parser")
    head = soup.find("head")
    if not isinstance(head, Tag):
        return html

    canonical_url = f"{domain.rstrip('/')}/{page_rel_from_root.lstrip('/')}"
    if not canonical_url.endswith("/"):
        canonical_url += "/"

    # Remove existing alternate hreflang + canonical (we re-add)
    for link in list(head.find_all("link")):
        if not isinstance(link, Tag):
            continue
        rel = (link.get("rel") or [])
        rel_str = " ".join(rel) if isinstance(rel, list) else str(rel)
        if rel_str.lower() == "canonical":
            link.decompose()
        if rel_str.lower() == "alternate" and link.get("hreflang"):
            link.decompose()

    canonical = soup.new_tag("link")
    canonical["rel"] = "canonical"
    canonical["href"] = canonical_url
    head.insert(0, canonical)

    # hreflang alternates
    for lang in all_langs:
        alt = soup.new_tag("link")
        alt["rel"] = "alternate"
        alt["hreflang"] = lang
        # swap leading locale in page path
        # page_rel_from_root begins with "<lang>/..."
        parts = page_rel_from_root.split("/", 1)
        rest = parts[1] if len(parts) > 1 else ""
        alt["href"] = f"{domain.rstrip('/')}/{lang}/{rest}"
        if not alt["href"].endswith("/"):
            alt["href"] += "/"
        head.insert(1, alt)

    xdef = soup.new_tag("link")
    xdef["rel"] = "alternate"
    xdef["hreflang"] = "x-default"
    parts = page_rel_from_root.split("/", 1)
    rest = parts[1] if len(parts) > 1 else ""
    xdef["href"] = f"{domain.rstrip('/')}/{x_default}/{rest}"
    if not xdef["href"].endswith("/"):
        xdef["href"] += "/"
    head.insert(1, xdef)

    return str(soup)


def _rewrite_base_and_absolute_locale_paths(html: str, *, src_lang: str, dst_lang: str) -> str:
    # base href="/en/" -> "/fr/"
    out = html.replace(f'<base href="/{src_lang}/">', f'<base href="/{dst_lang}/">')
    # absolute site paths: "/en/..." -> "/fr/..."
    out = out.replace(f'"/{src_lang}/', f'"/{dst_lang}/')
    out = out.replace(f"'/{src_lang}/", f"'/{dst_lang}/")
    return out


def openai_translate_items(
    client: "OpenAI",
    *,
    model: str,
    target_lang_code: str,
    items: List[ItemRef],
    max_retries: int,
) -> Dict[str, str]:
    base_system = (
        "You are a world-class localization translator for UI + marketing websites.\n"
        "Translate from English into the requested target language.\n"
        "Hard rules:\n"
        "- Return ONLY valid JSON. No markdown.\n"
        "- Preserve ALL placeholder/brand tokens exactly as-is. Tokens look like __K_x_y__.\n"
        "- Do NOT add scripts/styles/URLs.\n"
        "- Keep short UI labels short.\n"
    )

    user_prefix = (
        f"Target language code: {target_lang_code}.\n"
        "The site is for the NotiCatcher app (keyword alerts; can bypass silent mode).\n"
        "Items may include simple inline HTML (e.g., <strong>, <em>, <br>, <span>). Preserve tags.\n"
        "Allowed inline tags: br, strong, em, b, i, u, span, small, sup, sub, wbr.\n"
        "Return JSON schema:\n"
        '{ "items": [ { "id": "<same id>", "translation": "<translated text or HTML fragment>" } ] }\n'
    )

    api_retries = max(1, min(10, int(max_retries)))

    protected_payload: List[dict] = []
    protections: Dict[str, Dict[str, str]] = {}
    for idx, item in enumerate(items):
        protected_text, mapping = _protect_text(item.src, unique_prefix=f"{target_lang_code}_{idx}")
        protections[item.key] = mapping
        protected_payload.append({"id": item.key, "text": protected_text, "context": item.hint})

    user = user_prefix + "\nInput items JSON:\n" + json.dumps(protected_payload, ensure_ascii=False)

    last_err: Optional[Exception] = None
    for attempt in range(api_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": base_system}, {"role": "user", "content": user}],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content or ""
            data = json.loads(content)
            out_items = data.get("items")
            if not isinstance(out_items, list) or len(out_items) != len(items):
                raise ValueError("Unexpected response: items length mismatch.")

            out: Dict[str, str] = {}
            for obj in out_items:
                if not isinstance(obj, dict):
                    raise ValueError("Unexpected response: items must be objects.")
                item_id = str(obj.get("id") or "")
                translation = str(obj.get("translation") or "")
                if item_id not in protections:
                    raise ValueError("Unexpected response: unknown id.")
                mapping = protections[item_id]
                if mapping and not _ensure_all_tokens_present(translation, mapping):
                    raise ValueError("Token(s) missing in translation.")
                translation = _unprotect_text(translation, mapping).strip()
                if not translation:
                    translation = next(i.src for i in items if i.key == item_id)
                if not _validate_allowed_inline_fragment(translation):
                    raise ValueError("Unsafe inline HTML in translation.")
                out[item_id] = translation

            for item in items:
                out.setdefault(item.key, item.src)
            return out

        except Exception as exc:
            last_err = exc
            time.sleep(min(15.0, 2.0**attempt))

    raise RuntimeError(f"OpenAI translation failed after retries: {last_err}")


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Translate NotiSite3/en into locale folders.")
    p.add_argument("--source", type=Path, default=Path("en"), help="Source folder (default: en)")
    p.add_argument("--site-root", type=Path, default=Path("."), help="Site root (default: .)")
    p.add_argument(
        "--arb-l10n",
        type=Path,
        default=Path(r"C:\Users\home\Desktop\DIV_ALARM\NotiCatcher\lib\l10n"),
        help="NotiCatcher ARB l10n directory (default points to your machine path).",
    )
    p.add_argument("--languages", "-l", nargs="+", default=["all"], help="Locale codes (e.g. ko ja fr) or 'all'.")
    p.add_argument("--model", default="gpt-5.2", help="OpenAI model (default: gpt-5.2)")
    p.add_argument("--batch-size", type=int, default=30, help="Items per API call (default: 30)")
    p.add_argument("--max-retries", type=int, default=6, help="OpenAI retry attempts (default: 6)")
    p.add_argument("--timeout", type=float, default=90.0, help="OpenAI request timeout seconds (default: 90)")
    p.add_argument("--cache", type=Path, default=Path(".i18n_cache.site.json"), help="Cache JSON path.")
    p.add_argument("--no-cache", action="store_true", help="Disable cache read/write.")
    p.add_argument("--keep-existing", action="store_true", help="Skip locales that already exist.")
    p.add_argument("--dry-run", action="store_true", help="Show actions without writing.")
    p.add_argument("--domain", default=DEFAULT_DOMAIN, help="Canonical/hreflang domain.")
    p.add_argument("--x-default", default="en", help="x-default locale (default: en).")
    p.add_argument("--update-root-index", action="store_true", help="Update root index.html SUPPORTED languages.")
    p.add_argument("--update-sitemap", action="store_true", help="Regenerate sitemap.xml from existing locale folders.")
    return p.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    source: Path = (args.site_root / args.source).resolve()
    site_root: Path = args.site_root.resolve()

    if not source.exists() or not source.is_dir():
        print(f"❌ Source folder not found: {source}", file=sys.stderr)
        return 2

    all_from_arb = discover_locales_from_arb(args.arb_l10n)
    if not all_from_arb:
        print(f"❌ No locales discovered from ARB dir: {args.arb_l10n}", file=sys.stderr)
        return 2

    raw_langs: List[str] = []
    for chunk in args.languages:
        raw_langs.extend([x.strip().lower() for x in chunk.split(",") if x.strip()])
    if not raw_langs:
        print("❌ No languages provided.", file=sys.stderr)
        return 2

    if "all" in raw_langs:
        target_langs = [x for x in all_from_arb if x != "en"]
    else:
        target_langs = [x for x in raw_langs if x != "en"]

    # Build hreflang set from what will actually exist:
    # - existing locales already present on disk (en/ko included if they exist)
    # - plus locales we will generate in this run
    existing_locales_before = discover_existing_site_locales(site_root)
    hreflang_set = []
    for x in existing_locales_before + ["en"] + target_langs:
        x = (x or "").strip().lower()
        if not x:
            continue
        if x not in hreflang_set:
            hreflang_set.append(x)

    cache: dict = {}
    if not args.no_cache:
        cache = _load_json(args.cache)
        if not isinstance(cache, dict):
            cache = {}

    # Only require OpenAI + API key if we will actually generate locales.
    if target_langs and not args.dry_run:
        if OpenAI is None:
            print("❌ Missing dependency: openai. Run: pip install -r requirements.i18n.txt", file=sys.stderr)
            return 2
        if not os.environ.get("OPENAI_API_KEY"):
            print("❌ OPENAI_API_KEY is not set.", file=sys.stderr)
            return 2

    client = OpenAI(timeout=float(args.timeout), max_retries=0) if (target_langs and not args.dry_run) else None

    # Gather source HTML once
    source_html_files = sorted(source.rglob("*.html"))
    source_html_map: Dict[Path, str] = {}
    for f in source_html_files:
        try:
            source_html_map[f] = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

    # Build translation item set from source/en
    items_by_key: Dict[str, ItemRef] = {}
    for src_path, html in source_html_map.items():
        rel = src_path.relative_to(source).as_posix()
        for item in collect_items_from_html(html, file_hint=rel):
            items_by_key.setdefault(item.key, item)
    all_items = list(items_by_key.values())

    print(f"Source: {source}")
    print(f"Site root: {site_root}")
    print(f"Discovered locales (ARB): {', '.join(all_from_arb)}")
    print(f"Target locales: {', '.join(target_langs)}")
    print(f"Items to translate: {len(all_items)}")

    for lang in target_langs:
        dest = (site_root / lang).resolve()
        if dest.exists() and args.keep_existing:
            print(f"- {lang}: exists, skipping (--keep-existing)")
            continue

        print(f"- {lang}: creating folder {dest}")
        if args.dry_run:
            continue

        _copy_tree(source, dest, overwrite=not args.keep_existing)

        lang_cache = cache.get(lang) if isinstance(cache.get(lang), dict) else {}
        if not isinstance(lang_cache, dict):
            lang_cache = {}
            cache[lang] = lang_cache

        resolved: Dict[str, str] = {}
        missing: List[ItemRef] = []
        for item in all_items:
            cached = lang_cache.get(item.key)
            if isinstance(cached, dict) and cached.get("src") == item.src and isinstance(cached.get("dst"), str):
                resolved[item.key] = str(cached["dst"])
            else:
                missing.append(item)

        print(f"  cached: {len(resolved)} | missing: {len(missing)}")

        batch_size = max(1, int(args.batch_size))
        for i in range(0, len(missing), batch_size):
            batch = missing[i : i + batch_size]
            if client is None:
                raise RuntimeError("OpenAI client not initialized.")
            out = openai_translate_items(
                client,
                model=args.model,
                target_lang_code=lang,
                items=batch,
                max_retries=max(1, int(args.max_retries)),
            )
            for item in batch:
                dst = out[item.key]
                lang_cache[item.key] = {"src": item.src, "dst": dst}
                resolved[item.key] = dst
            print(f"  translated batch {i // batch_size + 1}/{(len(missing) + batch_size - 1) // batch_size}")
            if not args.no_cache:
                _save_json(args.cache, cache)

        # Apply rewrites + translations + hreflang/canonical to each HTML file
        dest_html_files = sorted(dest.rglob("*.html"))
        for f in dest_html_files:
            try:
                original = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            updated = _rewrite_base_and_absolute_locale_paths(original, src_lang="en", dst_lang=lang)
            updated = apply_translations_to_html(updated, lang_code=lang, translations=resolved)

            page_rel = _page_path_from_file(site_root, f)  # e.g. fr/price/
            updated = _set_or_replace_canonical_and_hreflang(
                updated,
                domain=str(args.domain),
                page_rel_from_root=page_rel,
                all_langs=hreflang_set,
                x_default=str(args.x_default),
            )

            f.write_text(updated, encoding="utf-8")

        print(f"  -> {lang}: done ({len(dest_html_files)} html files)")

    # Post-step: update root index SUPPORTED + sitemap based on what exists now.
    existing_locales_after = discover_existing_site_locales(site_root)
    if args.update_root_index:
        update_root_index_supported_languages(site_root / ROOT_INDEX_RELATIVE_PATH, existing_locales_after, dry_run=bool(args.dry_run))
    if args.update_sitemap:
        generate_sitemap(site_root, domain=str(args.domain), include_locales=existing_locales_after, dry_run=bool(args.dry_run))

    if not args.no_cache and not args.dry_run:
        _save_json(args.cache, cache)
        print(f"Saved cache: {args.cache}")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

