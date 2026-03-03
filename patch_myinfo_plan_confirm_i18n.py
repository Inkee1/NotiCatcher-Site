#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def arb_to_folder_locale(arb_locale: str) -> str:
    s = (arb_locale or "").strip()
    if not s:
        return ""
    return s.replace("_", "-").lower()


def load_arb_map(arb_dir: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in sorted(arb_dir.glob("app_*.arb")):
        raw = p.stem[len("app_") :]
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        arb_locale = str(data.get("@@locale") or raw)
        loc = arb_to_folder_locale(arb_locale)
        if loc:
            out[loc] = data
    return out


RE_MYINFO_BTN_BLOCK = re.compile(
    r"""
    const\s+btnPro\s*=\s*document\.getElementById\("btn-change-pro"\)\s*;\s*
    if\s*\(btnPro\)\s*btnPro\.addEventListener\("click",\s*\(\)\s*=>\s*[^;]+;\s*
    const\s+btnBasic\s*=\s*document\.getElementById\("btn-change-basic"\)\s*;\s*
    if\s*\(btnBasic\)\s*btnBasic\.addEventListener\("click",\s*\(\)\s*=>\s*[^;]+;\s*
    (?=onAuthStateChanged\s*\()
    """,
    re.IGNORECASE | re.VERBOSE,
)

RE_EXISTING_I18N_SECTION = re.compile(
    r"""
    \s*const\s+__PLAN_CHANGE_I18N\s*=\s*\{[\s\S]*?
    (?=onAuthStateChanged\s*\()
    """,
    re.IGNORECASE | re.VERBOSE,
)

RE_OLD_CONFIRM_HELPERS = re.compile(
    r"""
    \s*function\s+__planChangeLocale\s*\(\)\s*\{[\s\S]*?
    (?=const\s+__PLAN_CHANGE_I18N\s*=)
    """,
    re.IGNORECASE | re.VERBOSE,
)

RE_MANAGE_BTN_LISTENER = re.compile(
    r"""
    const\s+manageBtn\s*=\s*document\.getElementById\("btn-manage-subscription"\)\s*;\s*
    if\s*\(manageBtn\)\s*manageBtn\.addEventListener\("click",\s*openBillingPortal\)\s*;\s*
    """,
    re.IGNORECASE | re.VERBOSE,
)

RE_GRADE_LINE = re.compile(
    r"""const\s+grade\s*=\s*\(data\s*&&\s*data\.grade\)\s*\?\s*data\.grade\s*:\s*["']free["']\s*;\s*""",
    re.IGNORECASE,
)


def build_injected_js(i18n: dict[str, str]) -> str:
    # Keep this minimal and fully translatable via ARB values already available.
    # We intentionally avoid adding new sentences that aren't translated.
    payload = json.dumps(i18n, ensure_ascii=False)
    return (
        "\n"
        "        const __PLAN_CHANGE_I18N = "
        + payload
        + ";\n\n"
        "        function __planLabel(key, fallback) {\n"
        "            try {\n"
        "                const v = __PLAN_CHANGE_I18N && __PLAN_CHANGE_I18N[key];\n"
        "                return (typeof v === 'string' && v.trim()) ? v : fallback;\n"
        "            } catch (_) {\n"
        "                return fallback;\n"
        "            }\n"
        "        }\n\n"
        "        function __planBullet(key, fallback) {\n"
        "            try {\n"
        "                const v = __PLAN_CHANGE_I18N && __PLAN_CHANGE_I18N[key];\n"
        "                return (typeof v === 'string' && v.trim()) ? v : fallback;\n"
        "            } catch (_) {\n"
        "                return fallback;\n"
        "            }\n"
        "        }\n\n"
        "        function __buildPlanConfirmMessage(targetPlan) {\n"
        "            const basicLabel = __planLabel('tierLabelBasic', 'Basic');\n"
        "            const proLabel = __planLabel('tierLabelPro', 'Pro');\n"
        "            const basicNonFin = __planBullet('tierBasicBulletNonFinancialUnlimited', \"'General apps' keyword catches: Unlimited\");\n"
        "            const basicFin = __planBullet('tierBasicBulletFinancialLimit', \"'Financial apps & Telegram' keyword catches: 2/day\");\n"
        "            const proAll = __planBullet('tierProBulletUnlimitedIncludingFinancial', \"'All apps (incl. financial & Telegram)' keyword catches: Unlimited\");\n"
        "\n"
        "            const parts = [];\n"
        "            const t = String(targetPlan || '').toLowerCase();\n"
        "            const targetLabel = (t === 'pro') ? proLabel : basicLabel;\n"
        "            parts.push(targetLabel);\n"
        "            parts.push('');\n"
        "            parts.push(basicLabel);\n"
        "            parts.push('- ' + basicNonFin);\n"
        "            parts.push('- ' + basicFin);\n"
        "            parts.push('');\n"
        "            parts.push(proLabel);\n"
        "            parts.push('- ' + proAll);\n"
        "            return parts.join('\\n');\n"
        "        }\n\n"
        "        function __t(key, fallback) {\n"
        "            try {\n"
        "                const v = __PLAN_CHANGE_I18N && __PLAN_CHANGE_I18N[key];\n"
        "                return (typeof v === 'string' && v.trim()) ? v : fallback;\n"
        "            } catch (_) {\n"
        "                return fallback;\n"
        "            }\n"
        "        }\n\n"
        "        async function confirmAndChangePlan(plan) {\n"
        "            const msg = __buildPlanConfirmMessage(plan);\n"
        "            const ok = confirm(msg);\n"
        "            if (!ok) return;\n"
        "            return changePlan(String(plan || '').toLowerCase());\n"
        "        }\n\n"
        "        const btnPro = document.getElementById(\"btn-change-pro\");\n"
        "        if (btnPro) btnPro.addEventListener(\"click\", () => confirmAndChangePlan(\"pro\"));\n"
        "        const btnBasic = document.getElementById(\"btn-change-basic\");\n"
        "        if (btnBasic) btnBasic.addEventListener(\"click\", () => confirmAndChangePlan(\"basic\"));\n\n"
        "        // Localize existing English alerts without changing behavior.\n"
        "        (function () {\n"
        "            try {\n"
        "                if (typeof window.alert !== 'function') return;\n"
        "                const _alert = window.alert;\n"
        "                window.alert = function (msg) {\n"
        "                    const m = String(msg || '');\n"
        "                    if (m === 'Plan updated. It may take a few seconds to reflect.') {\n"
        "                        return _alert(__t('tierRefreshUpdated', 'Tier updated.'));\n"
        "                    }\n"
        "                    if (m === 'Failed to change plan.') {\n"
        "                        return _alert(__t('authRequestFailed', 'Request failed. Please try again.'));\n"
        "                    }\n"
        "                    return _alert(msg);\n"
        "                };\n"
        "            } catch (_) {}\n"
        "        })();\n\n"
        "        function __syncManageButtonUI() {\n"
        "            try {\n"
        "                const manageBtn = document.getElementById('btn-manage-subscription');\n"
        "                if (!manageBtn) return;\n"
        "                const g = String(window.__currentGrade || 'free').toLowerCase();\n"
        "                if (g === 'free') {\n"
        "                    manageBtn.classList.remove('btn-cancel');\n"
        "                    manageBtn.classList.add('btn-upgrade');\n"
        "                    manageBtn.innerHTML = `<i class='bx bx-crown'></i> ${__t('subscribePro', 'Subscribe')}`;\n"
        "                } else {\n"
        "                    manageBtn.classList.remove('btn-upgrade');\n"
        "                    manageBtn.classList.add('btn-cancel');\n"
        "                    // Keep existing localized label in HTML for subscribed users.\n"
        "                }\n"
        "            } catch (_) {}\n"
        "        }\n\n"
        "        __syncManageButtonUI();\n\n"
    )


def pick_i18n(arb: dict, fallback: dict) -> dict[str, str]:
    keys = [
        "tierLabelBasic",
        "tierLabelPro",
        "tierBasicBulletNonFinancialUnlimited",
        "tierBasicBulletFinancialLimit",
        "tierProBulletUnlimitedIncludingFinancial",
        "tierRefreshUpdated",
        "authRequestFailed",
        "subscribePro",
    ]
    out: dict[str, str] = {}
    for k in keys:
        v = arb.get(k)
        if not isinstance(v, str) or not v.strip():
            v = fallback.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v
    return out


def patch_myinfo_file(path: Path, *, locale: str, arb_map: dict[str, dict], fallback_arb: dict) -> bool:
    html = path.read_text(encoding="utf-8")

    arb = arb_map.get(locale) or fallback_arb
    i18n = pick_i18n(arb, fallback_arb)
    injected = build_injected_js(i18n)

    # If older (ko/en-only) confirm helpers exist, remove them to avoid duplicate declarations.
    html = RE_OLD_CONFIRM_HELPERS.sub("\n\n", html, count=1)

    # Ensure grade is mirrored into a global so the manage button can switch to "subscribe" on Free.
    def _grade_repl(m: re.Match) -> str:
        return (
            m.group(0)
            + "\n                window.__currentGrade = String(grade || 'free').toLowerCase();\n"
            + "                if (typeof __syncManageButtonUI === 'function') __syncManageButtonUI();\n"
        )

    html = RE_GRADE_LINE.sub(_grade_repl, html, count=1)

    # Replace manage button click handler: Free => go to pricing, otherwise open billing portal.
    manage_snippet = (
        '        const manageBtn = document.getElementById("btn-manage-subscription");\n'
        '        async function __handleManageSubscriptionClick() {\n'
        "            try {\n"
        "                const g = String(window.__currentGrade || 'free').toLowerCase();\n"
        "                if (g === 'free') {\n"
        "                    // base href is set (e.g., /ko/), so this resolves to /<lang>/price/\n"
        "                    window.location.href = 'price/';\n"
        "                    return;\n"
        "                }\n"
        "            } catch (_) {}\n"
        "            return openBillingPortal();\n"
        "        }\n"
        '        if (manageBtn) manageBtn.addEventListener("click", __handleManageSubscriptionClick);\n\n'
    )
    html = RE_MANAGE_BTN_LISTENER.sub(manage_snippet, html, count=1)

    # Use a function replacement so backslashes are treated literally (avoid \n becoming a real newline).
    if RE_EXISTING_I18N_SECTION.search(html):
        new_html, n = RE_EXISTING_I18N_SECTION.subn(lambda _m: injected, html, count=1)
    else:
        new_html, n = RE_MYINFO_BTN_BLOCK.subn(lambda _m: injected, html, count=1)
    if n == 0:
        return False
    path.write_text(new_html, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Localize myinfo plan-change confirmation using app ARB strings.")
    ap.add_argument("--site-root", type=Path, default=Path("."), help="NotiSite3 root.")
    ap.add_argument(
        "--arb-dir",
        type=Path,
        default=Path(r"C:\Users\home\Desktop\DIV_ALARM\NotiCatcher\lib\l10n"),
        help="Directory containing app_*.arb files.",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    root = args.site_root.resolve()
    arb_dir = args.arb_dir.resolve()
    arb_map = load_arb_map(arb_dir)
    fallback_arb = arb_map.get("en") or {}

    targets = sorted(root.rglob("myinfo/index.html"))
    changed = 0
    skipped = 0

    for f in targets:
        # locale folder is the first segment under site root (e.g., ko/myinfo/index.html)
        try:
            rel = f.relative_to(root)
        except Exception:
            skipped += 1
            continue

        parts = rel.parts
        locale = (parts[0] if len(parts) >= 3 else "en").strip().lower()

        try:
            if args.dry_run:
                html = f.read_text(encoding="utf-8")
                if RE_MYINFO_BTN_BLOCK.search(html):
                    print(f"[dry-run] would patch: {rel.as_posix()} (locale={locale})")
                    changed += 1
                else:
                    skipped += 1
                continue

            did = patch_myinfo_file(f, locale=locale, arb_map=arb_map, fallback_arb=fallback_arb)
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

