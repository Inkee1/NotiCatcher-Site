from __future__ import annotations

import re
from pathlib import Path


BLOCK_RE = re.compile(
    r"""
    if\s*\(\s*nextEl\s*\)\s*\{\s*
        //\s*__nextPayCanceledAware\s*
        const\s+_isCanceled\s*=\s*Boolean\(\s*data\s*&&\s*data\.isCanceled\s*\)\s*;\s*
        nextEl\.textContent\s*=\s*["']—["']\s*;\s*
        const\s+exp\s*=\s*data\s*\?\s*data\.expired\s*:\s*null\s*;\s*
        if\s*\(\s*!_isCanceled\s*&&\s*exp\s*&&\s*typeof\s+exp\.toDate\s*===\s*["']function["']\s*\)\s*\{\s*
            nextEl\.textContent\s*=\s*formatDate\(\s*exp\.toDate\(\)\s*\)\s*;\s*
        \}\s*
    \}\s*
    """,
    re.VERBOSE,
)


def replacement() -> str:
    return (
        "if (nextEl) {\n"
        "                // __nextPayCanceledAware\n"
        "                const _isCanceled = Boolean(data && data.isCanceled);\n"
        "                const _grade = String(grade || 'free').toLowerCase();\n"
        "                const _isPaid = _grade === 'basic' || _grade === 'pro';\n"
        "                nextEl.textContent = \"—\";\n"
        "                const exp = data ? data.expired : null;\n"
        "                if (_isPaid && exp && typeof exp.toDate === \"function\") {\n"
        "                    const _label = (() => {\n"
        "                        const l = String(document.documentElement.lang || '').toLowerCase();\n"
        "                        if (l === 'ko') return _isCanceled ? '종료일' : '갱신일';\n"
        "                        return _isCanceled ? 'End' : 'Renews';\n"
        "                    })();\n"
        "                    nextEl.textContent = formatDate(exp.toDate()) + \" (\" + _label + \")\";\n"
        "                }\n"
        "            }\n"
    )


def main() -> int:
    root = Path(__file__).resolve().parent
    files = sorted(root.rglob("myinfo/index.html"))
    changed = 0
    for f in files:
        s = f.read_text(encoding="utf-8")
        new, n = BLOCK_RE.subn(replacement(), s, count=1)
        if n:
            f.write_text(new, encoding="utf-8")
            changed += 1
    print(f"Done. Updated {changed}/{len(files)} myinfo pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

