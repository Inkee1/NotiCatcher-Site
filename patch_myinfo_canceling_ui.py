from __future__ import annotations

import re
from pathlib import Path


RE_MANAGE_ELSE = re.compile(
    r"""
    (\belse\s*\{\s*
        (?:\s*manageBtn\.classList\.remove\(\s*['"]btn-upgrade['"]\s*\)\s*;\s*)?
        \s*manageBtn\.classList\.add\(\s*['"]btn-cancel['"]\s*\)\s*;\s*
    )
    (\s*\}\s*)
    """,
    re.VERBOSE,
)

RE_NEXT_PAYMENT_BLOCK = re.compile(
    r"""
    if\s*\(\s*nextEl\s*\)\s*\{\s*
      nextEl\.textContent\s*=\s*["']—["']\s*;\s*
      const\s+exp\s*=\s*data\s*\?\s*data\.expired\s*:\s*null\s*;\s*
      if\s*\(\s*exp\s*&&\s*typeof\s+exp\.toDate\s*===\s*["']function["']\s*\)\s*\{\s*
        nextEl\.textContent\s*=\s*formatDate\(\s*exp\.toDate\(\)\s*\)\s*;\s*
      \}\s*
    \}\s*
    """,
    re.VERBOSE,
)


def patch_manage_button(html: str) -> tuple[str, int]:
    """
    Fix bug where the manage button label stays as "Subscribe" after upgrading.
    Always set a paid-state label.
    """
    if "__syncManageButtonUI" not in html:
        return html, 0

    def repl(m: re.Match) -> str:
        head = m.group(1)
        tail = m.group(2)
        # Use the localized manage label; keep btn-cancel styling for paid users.
        injection = (
            "manageBtn.innerHTML = "
            "`<i class='bx bx-cog'></i> ${__WEB_SUB_COPY.manage}`;"
        )
        return head + "        " + injection + "\n" + tail

    new, n = RE_MANAGE_ELSE.subn(repl, html, count=1)
    return new, n


def patch_next_payment_when_canceling(html: str) -> tuple[str, int]:
    """
    When the subscription is canceling, 'expired' is the period end (not a next charge).
    To avoid confusion, hide the date (keep '—') when isCanceled=true.
    """
    if "next-payment-val" not in html:
        return html, 0
    if "__nextPayCanceledAware" in html:
        return html, 0

    def repl(_: re.Match) -> str:
        return (
            "if (nextEl) {\n"
            "                // __nextPayCanceledAware\n"
            "                const _isCanceled = Boolean(data && data.isCanceled);\n"
            '                nextEl.textContent = "—";\n'
            "                const exp = data ? data.expired : null;\n"
            "                if (!_isCanceled && exp && typeof exp.toDate === \"function\") {\n"
            "                    nextEl.textContent = formatDate(exp.toDate());\n"
            "                }\n"
            "            }\n"
        )

    new, n = RE_NEXT_PAYMENT_BLOCK.subn(repl, html, count=1)
    return new, n


def main() -> int:
    root = Path(__file__).resolve().parent
    files = sorted(root.rglob("myinfo/index.html"))
    changed = 0
    edits = 0
    for f in files:
        s = f.read_text(encoding="utf-8")
        out = s
        out, n1 = patch_manage_button(out)
        out, n2 = patch_next_payment_when_canceling(out)
        if out != s:
            f.write_text(out, encoding="utf-8")
            changed += 1
            edits += n1 + n2
    print(f"Done. Updated {changed}/{len(files)} myinfo pages. edits={edits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

