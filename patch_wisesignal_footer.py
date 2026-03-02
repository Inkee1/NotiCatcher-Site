#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


FOOTER_ID = "wisesignal-legal-footer"

FOOTER_HTML = f"""
<footer id="{FOOTER_ID}" style="margin-top: 4rem; padding: 3rem 5% 2.5rem; color: rgba(148,163,184,0.90); font-size: 0.82rem; line-height: 1.7; text-align: center;">
  <div style="max-width: 1100px; margin: 0 auto;">
    <div style="height: 1px; background: rgba(148,163,184,0.22); margin: 0 0 1.5rem;"></div>
    <div>© 2026 WiseSignal Ltd.</div>
    <div>WiseSignal Ltd is registered in England and Wales (No. 16253236).</div>
    <div>Registered Office: 71-75 Shelton Street, London, WC2H 9JQ, UK.</div>
    <div>Contact: <a href="mailto:info@wise-signal.com" style="color: inherit; text-decoration: underline; text-underline-offset: 3px;">info@wise-signal.com</a></div>
  </div>
</footer>
""".strip(
    "\n"
)


RE_BODY_CLOSE = re.compile(r"</body\s*>", re.IGNORECASE)
RE_EXISTING_FOOTER = re.compile(
    r'<footer\b[^>]*\bid\s*=\s*["\']' + re.escape(FOOTER_ID) + r'["\'][^>]*>.*?</footer\s*>',
    re.IGNORECASE | re.DOTALL,
)


def patch_html(html: str) -> tuple[str, bool]:
    # Update existing footer (style tweaks, copy changes, etc.)
    if FOOTER_ID in html:
        updated = RE_EXISTING_FOOTER.sub(FOOTER_HTML, html, count=1)
        return (updated, updated != html)

    m = RE_BODY_CLOSE.search(html)
    if not m:
        return html, False

    insert_at = m.start()
    before = html[:insert_at].rstrip()
    after = html[insert_at:]
    patched = before + "\n\n" + FOOTER_HTML + "\n\n" + after.lstrip()
    return patched, True


def iter_target_html_files(site_root: Path) -> list[Path]:
    out: list[Path] = []
    for p in site_root.rglob("*.html"):
        # Skip the root redirect index.html (layout intentionally centered loader).
        if p.parent.resolve() == site_root.resolve() and p.name.lower() == "index.html":
            continue
        out.append(p)
    return sorted(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Insert WiseSignal legal footer into all NotiSite3 HTML pages.")
    ap.add_argument("--site-root", type=Path, default=Path("."), help="Site root (default: current directory).")
    ap.add_argument("--dry-run", action="store_true", help="Print what would change without writing files.")
    args = ap.parse_args(argv)

    site_root = args.site_root.resolve()
    if not site_root.exists():
        raise SystemExit(f"Site root not found: {site_root}")

    targets = iter_target_html_files(site_root)
    changed = 0
    skipped = 0

    for f in targets:
        try:
            original = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            skipped += 1
            continue

        updated, did = patch_html(original)
        if not did:
            skipped += 1
            continue

        changed += 1
        if args.dry_run:
            rel = f.relative_to(site_root).as_posix()
            print(f"[dry-run] would patch: {rel}")
            continue
        f.write_text(updated, encoding="utf-8")

    print(f"Done. Patched: {changed} | Skipped: {skipped} | Total: {len(targets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

