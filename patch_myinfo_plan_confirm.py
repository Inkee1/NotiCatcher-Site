#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


RE_TARGET_BLOCK = re.compile(
    r"""
    const\s+btnPro\s*=\s*document\.getElementById\("btn-change-pro"\);\s*
    if\s*\(btnPro\)\s*btnPro\.addEventListener\("click",\s*\(\)\s*=>\s*changePlan\("pro"\)\);\s*
    const\s+btnBasic\s*=\s*document\.getElementById\("btn-change-basic"\);\s*
    if\s*\(btnBasic\)\s*btnBasic\.addEventListener\("click",\s*\(\)\s*=>\s*changePlan\("basic"\)\);\s*
    """,
    re.IGNORECASE | re.VERBOSE,
)

RE_EXISTING_CONFIRM_BLOCK = re.compile(
    r"""
    function\s+__planChangeLocale\s*\(\)\s*\{[\s\S]*?
    if\s*\(btnBasic\)\s*btnBasic\.addEventListener\("click",\s*\(\)\s*=>\s*confirmAndChangePlan\("basic"\)\);\s*
    """,
    re.IGNORECASE | re.VERBOSE,
)


CONFIRM_SNIPPET = r"""
        function __planChangeLocale() {
            const raw = (document.documentElement && document.documentElement.lang) ? document.documentElement.lang : "en";
            return String(raw || "en").toLowerCase();
        }

        function __planChangeCopy(lang) {
            const ko = {
                upgradeTitle: "Pro로 전환하시겠어요?",
                upgradeBody: [
                    "- Basic: 일반 앱 키워드 캐치 무제한 / 금융 & Telegram 하루 2회 제한",
                    "- Pro: 모든 앱 키워드 캐치 무제한",
                    "",
                    "업그레이드 시 즉시 결제(또는 차액 청구)가 발생할 수 있습니다."
                ].join("\\n"),
                downgradeTitle: "Basic으로 전환하시겠어요?",
                downgradeBody: [
                    "Basic으로 전환하면 '금융 & Telegram' 키워드 캐치가 하루 2회로 제한됩니다.",
                    "",
                    "다운그레이드는 보통 다음 결제일부터 적용됩니다."
                ].join("\\n"),
            };
            const en = {
                upgradeTitle: "Switch to Pro?",
                upgradeBody: [
                    "- Basic: Unlimited for general apps / Finance & Telegram limited (2/day)",
                    "- Pro: Unlimited for all apps",
                    "",
                    "Upgrading may charge immediately (or bill the prorated difference)."
                ].join("\\n"),
                downgradeTitle: "Switch to Basic?",
                downgradeBody: [
                    "Switching to Basic limits Finance & Telegram keyword catches to 2/day.",
                    "",
                    "Downgrades typically take effect on the next billing date."
                ].join("\\n"),
            };
            return (lang || "").startsWith("ko") ? ko : en;
        }

        async function confirmAndChangePlan(plan) {
            const lang = __planChangeLocale();
            const copy = __planChangeCopy(lang);
            const p = String(plan || "").toLowerCase();
            const isUpgrade = p === "pro";
            const title = isUpgrade ? copy.upgradeTitle : copy.downgradeTitle;
            const body = isUpgrade ? copy.upgradeBody : copy.downgradeBody;
            const ok = confirm(title + "\\n\\n" + body);
            if (!ok) return;
            return changePlan(p);
        }

        const btnPro = document.getElementById("btn-change-pro");
        if (btnPro) btnPro.addEventListener("click", () => confirmAndChangePlan("pro"));
        const btnBasic = document.getElementById("btn-change-basic");
        if (btnBasic) btnBasic.addEventListener("click", () => confirmAndChangePlan("basic"));
""".strip(
    "\n"
)


def patch_file(p: Path) -> bool:
    html = p.read_text(encoding="utf-8")
    # If confirm block already exists (possibly an older/broken version), replace it.
    if "function __planChangeLocale()" in html and "confirmAndChangePlan" in html:
        updated, n = RE_EXISTING_CONFIRM_BLOCK.subn(CONFIRM_SNIPPET, html, count=1)
        if n > 0:
            p.write_text(updated, encoding="utf-8")
            return True
        return False

    updated, n = RE_TARGET_BLOCK.subn(CONFIRM_SNIPPET, html, count=1)
    if n == 0:
        return False
    p.write_text(updated, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Add plan-change confirmation to all myinfo pages.")
    ap.add_argument("--site-root", type=Path, default=Path("."), help="Site root (default: .)")
    ap.add_argument("--dry-run", action="store_true", help="Don't write files")
    args = ap.parse_args(argv)

    root = args.site_root.resolve()
    targets = sorted(root.rglob("myinfo/index.html"))
    changed = 0
    skipped = 0
    for f in targets:
        try:
            if args.dry_run:
                html = f.read_text(encoding="utf-8")
                if RE_EXISTING_CONFIRM_BLOCK.search(html) or RE_TARGET_BLOCK.search(html):
                    print(f"[dry-run] would patch: {f.relative_to(root).as_posix()}")
                    changed += 1
                else:
                    skipped += 1
                continue

            did = patch_file(f)
            if did:
                changed += 1
            else:
                skipped += 1
        except UnicodeDecodeError:
            skipped += 1

    print(f"Done. Patched: {changed} | Skipped: {skipped} | Total: {len(targets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

