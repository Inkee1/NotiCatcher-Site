from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup  # type: ignore


DEFAULT_DOMAIN = "https://noticatcher.com"


LOCALE_DIR_RE = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$", re.IGNORECASE)


@dataclass(frozen=True)
class PatchStats:
    files_touched: int = 0
    files_changed: int = 0
    edits_subscription: int = 0
    edits_stripe_locale: int = 0
    edits_hreflang: int = 0


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _write_text(p: Path, s: str) -> None:
    p.write_text(s, encoding="utf-8")


def discover_locale_dirs(site_root: Path) -> list[str]:
    out: list[str] = []
    for child in site_root.iterdir():
        if not child.is_dir():
            continue
        name = child.name.strip()
        if not name or not LOCALE_DIR_RE.fullmatch(name):
            continue
        # Treat it as a locale only if it contains at least one HTML file.
        if any(child.rglob("*.html")):
            out.append(name.lower())
    out.sort()
    return out


def _page_path_from_file(site_root: Path, html_file: Path) -> str:
    rel = html_file.relative_to(site_root).as_posix()
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
    all_langs: list[str],
    x_default: str,
) -> tuple[str, bool]:
    soup = BeautifulSoup(html, "html.parser")
    head = soup.find("head")
    if head is None:
        return html, False

    canonical_url = f"{domain.rstrip('/')}/{page_rel_from_root.lstrip('/')}"
    if not canonical_url.endswith("/"):
        canonical_url += "/"

    # Remove existing alternate hreflang + canonical (we re-add)
    changed = False
    for link in list(head.find_all("link")):
        rel = link.get("rel") or []
        rel_str = " ".join(rel) if isinstance(rel, list) else str(rel)
        if rel_str.lower() == "canonical":
            link.decompose()
            changed = True
            continue
        if rel_str.lower() == "alternate" and link.get("hreflang"):
            link.decompose()
            changed = True
            continue

    canonical = soup.new_tag("link")
    canonical["rel"] = "canonical"
    canonical["href"] = canonical_url
    head.insert(0, canonical)
    changed = True

    # hreflang alternates
    for lang in all_langs:
        alt = soup.new_tag("link")
        alt["rel"] = "alternate"
        alt["hreflang"] = lang
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

    return str(soup), changed


def patch_price_subscription_state(js_or_html: str) -> tuple[str, int]:
    """
    Make CTA state robust:
    - Only treat `trialing/active` as "manage/upgrade" when grade is a paid tier (basic/pro).
    """
    edits = 0
    if "applyPricingUIFromUserDoc" not in js_or_html:
        return js_or_html, 0
    if "const isPaidGrade" in js_or_html and "isTrialingPaid" in js_or_html:
        return js_or_html, 0

    anchor = "const isActive = subStatus === 'active';"
    if anchor not in js_or_html:
        return js_or_html, 0

    insert = (
        "const isPaidGrade = grade === 'basic' || grade === 'pro';\n"
        "            const isTrialingPaid = isTrialing && isPaidGrade;\n"
        "            const isActivePaid = isActive && isPaidGrade;"
    )

    # Insert the new paid-check vars right after isActive line (matches formatting used in files).
    out, n = re.subn(
        re.escape(anchor),
        anchor + "\n            " + insert,
        js_or_html,
        count=1,
    )
    if n:
        js_or_html = out
        edits += 1

    # Switch outer conditions.
    out, n = re.subn(r"\bif\s*\(\s*isTrialing\s*\)\s*\{", "if (isTrialingPaid) {", js_or_html, count=1)
    if n:
        js_or_html = out
        edits += 1
    out, n = re.subn(r"\belse\s+if\s*\(\s*isActive\s*\)\s*\{", "else if (isActivePaid) {", js_or_html, count=1)
    if n:
        js_or_html = out
        edits += 1

    return js_or_html, edits


def patch_stripe_locale_persistence_price(html: str, *, locale: str) -> tuple[str, int]:
    edits = 0

    # Ensure portal + hosted invoice persist preferred lang before leaving site.
    if "notiCreatePortalSession" in html and 'localStorage.setItem("lang"' not in html:
        html, n = re.subn(
            r'(if\s*\(\s*!data\.url\s*\)\s*throw new Error\("Missing portal URL"\);\s*)\n(\s*)window\.location\.href\s*=\s*data\.url;',
            r'\1\n\2try { localStorage.setItem("lang", document.documentElement.lang || "' + locale + r'"); } catch (_) {}\n\2window.location.href = data.url;',
            html,
            count=1,
        )
        edits += n

    if "hostedInvoiceUrl" in html:
        # Insert right before redirect, but only if not already present in that block.
        pattern = r"(if\s*\(\s*data\.hostedInvoiceUrl\s*\)\s*\{\s*)([\s\S]*?)(\n\s*window\.location\.href\s*=\s*data\.hostedInvoiceUrl;)"
        m = re.search(pattern, html)
        if m and 'localStorage.setItem("lang"' not in m.group(0):
            repl = m.group(1) + m.group(2) + f'\n                    try {{ localStorage.setItem("lang", document.documentElement.lang || "{locale}"); }} catch (_) {{}}' + m.group(3)
            html = html[: m.start()] + repl + html[m.end() :]
            edits += 1

    # Checkout session: persist lang; pass returnUrl/cancelUrl/locale for backend to keep locale.
    if "notiCreateCheckoutSession" in html:
        # Insert lang persist at start of try-block if missing nearby.
        html, n = re.subn(
            r"(\n\s*try\s*\{\s*\n)(\s*const idToken = await auth\.currentUser\.getIdToken\(true\);\s*\n)",
            r'\1                try { localStorage.setItem("lang", document.documentElement.lang || "' + locale + r'"); } catch (_) {}\n\2',
            html,
            count=1,
        )
        edits += n

        # Ensure returnUrl const exists before fetch.
        if "const returnUrl =" not in html:
            html, n = re.subn(
                r"(const idToken = await auth\.currentUser\.getIdToken\(true\);\s*\n)",
                r"\1                const returnUrl = new URL(window.location.pathname, location.origin).toString();\n",
                html,
                count=1,
            )
            edits += n

        # Expand JSON body if it's still { plan } only.
        html, n = re.subn(
            r"body:\s*JSON\.stringify\(\s*\{\s*plan\s*\}\s*\)",
            r'body: JSON.stringify({ plan, returnUrl, cancelUrl: returnUrl, locale: document.documentElement.lang || "' + locale + r'" })',
            html,
            count=1,
        )
        edits += n

    return html, edits


def patch_stripe_locale_persistence_myinfo(html: str, *, locale: str) -> tuple[str, int]:
    edits = 0
    if "notiCreatePortalSession" in html and 'localStorage.setItem("lang"' not in html:
        html, n = re.subn(
            r'(if\s*\(\s*!data\.url\s*\)\s*throw new Error\("Missing portal URL"\);\s*)\n(\s*)window\.location\.href\s*=\s*data\.url;',
            r'\1\n\2try { localStorage.setItem("lang", document.documentElement.lang || "' + locale + r'"); } catch (_) {}\n\2window.location.href = data.url;',
            html,
            count=1,
        )
        edits += n

    if "hostedInvoiceUrl" in html:
        pattern = r"(if\s*\(\s*data\.hostedInvoiceUrl\s*\)\s*\{\s*)([\s\S]*?)(\n\s*window\.location\.href\s*=\s*data\.hostedInvoiceUrl;)"
        m = re.search(pattern, html)
        if m and 'localStorage.setItem("lang"' not in m.group(0):
            repl = m.group(1) + m.group(2) + f'\n                    try {{ localStorage.setItem("lang", document.documentElement.lang || "{locale}"); }} catch (_) {{}}' + m.group(3)
            html = html[: m.start()] + repl + html[m.end() :]
            edits += 1

    return html, edits


def patch_hreflang_for_file(html: str, *, site_root: Path, file_path: Path, all_locales: list[str]) -> tuple[str, int]:
    page_rel = _page_path_from_file(site_root, file_path)
    new_html, changed = _set_or_replace_canonical_and_hreflang(
        html,
        domain=DEFAULT_DOMAIN,
        page_rel_from_root=page_rel,
        all_langs=all_locales,
        x_default="en",
    )
    return new_html, 1 if changed else 0


def main() -> int:
    site_root = Path(__file__).resolve().parent
    locales = discover_locale_dirs(site_root)
    if not locales:
        print("No locale folders found.")
        return 2

    stats = PatchStats()

    # Subscription/Stripe patches on price + myinfo pages
    for loc in locales:
        price = site_root / loc / "price" / "index.html"
        if price.exists():
            stats = PatchStats(
                files_touched=stats.files_touched + 1,
                files_changed=stats.files_changed,
                edits_subscription=stats.edits_subscription,
                edits_stripe_locale=stats.edits_stripe_locale,
                edits_hreflang=stats.edits_hreflang,
            )
            original = _read_text(price)
            updated = original

            updated, n1 = patch_price_subscription_state(updated)
            updated, n2 = patch_stripe_locale_persistence_price(updated, locale=loc)

            if updated != original:
                _write_text(price, updated)
                stats = PatchStats(
                    files_touched=stats.files_touched,
                    files_changed=stats.files_changed + 1,
                    edits_subscription=stats.edits_subscription + n1,
                    edits_stripe_locale=stats.edits_stripe_locale + n2,
                    edits_hreflang=stats.edits_hreflang,
                )

        myinfo = site_root / loc / "myinfo" / "index.html"
        if myinfo.exists():
            stats = PatchStats(
                files_touched=stats.files_touched + 1,
                files_changed=stats.files_changed,
                edits_subscription=stats.edits_subscription,
                edits_stripe_locale=stats.edits_stripe_locale,
                edits_hreflang=stats.edits_hreflang,
            )
            original = _read_text(myinfo)
            updated = original
            updated, n = patch_stripe_locale_persistence_myinfo(updated, locale=loc)
            if updated != original:
                _write_text(myinfo, updated)
                stats = PatchStats(
                    files_touched=stats.files_touched,
                    files_changed=stats.files_changed + 1,
                    edits_subscription=stats.edits_subscription,
                    edits_stripe_locale=stats.edits_stripe_locale + n,
                    edits_hreflang=stats.edits_hreflang,
                )

    # Hreflang expansion across *all* locale HTML files so en pages show all languages in lang-widget.
    html_files: list[Path] = []
    for loc in locales:
        loc_dir = site_root / loc
        html_files.extend(sorted(loc_dir.rglob("*.html")))

    for f in html_files:
        original = _read_text(f)
        updated, n = patch_hreflang_for_file(original, site_root=site_root, file_path=f, all_locales=locales)
        if updated != original:
            _write_text(f, updated)
            stats = PatchStats(
                files_touched=stats.files_touched,
                files_changed=stats.files_changed + 1,
                edits_subscription=stats.edits_subscription,
                edits_stripe_locale=stats.edits_stripe_locale,
                edits_hreflang=stats.edits_hreflang + n,
            )

    print(
        "Done.\n"
        f"- locales: {len(locales)}\n"
        f"- files_touched(price+myinfo): {stats.files_touched}\n"
        f"- files_changed(total): {stats.files_changed}\n"
        f"- subscription_edits: {stats.edits_subscription}\n"
        f"- stripe_locale_edits: {stats.edits_stripe_locale}\n"
        f"- hreflang_edits: {stats.edits_hreflang}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

