from __future__ import annotations

import re
from pathlib import Path


H3_RE = re.compile(
    r"(<h3[^>]*>\s*<i[^>]*bx-calendar-check[^>]*></i>\s*)([^<]*?)(\s*</h3>)",
    re.IGNORECASE,
)

JS_BLOCK_RE = re.compile(
    r"(?ms)^(?P<indent>[ \t]*)if\s*\(\s*nextEl\s*\)\s*\{\s*\n(?P=indent)[ \t]*// __nextPayCanceledAware[\s\S]*?\n(?P=indent)\}\s*(?=\n[ \t]*// Show relevant plan-change buttons)",
)


def patch_header_span(html: str) -> tuple[str, int]:
    if 'id="next-payment-label"' in html or "id='next-payment-label'" in html:
        return html, 0

    def repl(m: re.Match) -> str:
        before, text, after = m.group(1), (m.group(2) or "").strip(), m.group(3)
        # Preserve original label as base; JS will store it in data-base and append (End/Renews).
        return f'{before}<span id="next-payment-label">{text}</span>{after}'

    new, n = H3_RE.subn(repl, html, count=1)
    return new, n


def patch_js_block(html: str) -> tuple[str, int]:
    m = JS_BLOCK_RE.search(html)
    if not m:
        return html, 0

    indent = m.group("indent") or ""
    inner = indent + "    "
    inner2 = inner + "    "

    block = (
        f"{indent}if (nextEl) {{\n"
        f"{inner}// __nextPayCanceledAware\n"
        f"{inner}const _isCanceled = Boolean(data && data.isCanceled);\n"
        f"{inner}const _grade = String(grade || 'free').toLowerCase();\n"
        f"{inner}const _isPaid = _grade === 'basic' || _grade === 'pro';\n"
        f"{inner}const _label = (() => {{\n"
        f"{inner2}const l = String(document.documentElement.lang || '').toLowerCase();\n"
        f"{inner2}if (l === 'ko') return _isCanceled ? '종료일' : '갱신일';\n"
        f"{inner2}return _isCanceled ? 'End' : 'Renews';\n"
        f"{inner}}})();\n"
        f"{inner}try {{\n"
        f"{inner2}const _labelEl = document.getElementById(\"next-payment-label\");\n"
        f"{inner2}if (_labelEl) {{\n"
        f"{inner2}    const _base = _labelEl.getAttribute(\"data-base\") || (_labelEl.textContent || \"\");\n"
        f"{inner2}    if (!_labelEl.getAttribute(\"data-base\")) _labelEl.setAttribute(\"data-base\", _base);\n"
        f"{inner2}    _labelEl.textContent = _isPaid ? (_base + \" (\" + _label + \")\") : _base;\n"
        f"{inner2}}}\n"
        f"{inner}}} catch (_) {{}}\n"
        f"{inner}nextEl.textContent = \"—\";\n"
        f"{inner}const exp = data ? data.expired : null;\n"
        f"{inner}if (_isPaid && exp && typeof exp.toDate === \"function\") {{\n"
        f"{inner2}nextEl.textContent = formatDate(exp.toDate()) + \" (\" + _label + \")\";\n"
        f"{inner}}}\n"
        f"{indent}}}\n"
    )

    new = html[: m.start()] + block + html[m.end() :]
    return new, 1


def main() -> int:
    root = Path(__file__).resolve().parent
    files = sorted(root.rglob("myinfo/index.html"))
    changed = 0
    edits = 0
    for f in files:
        s = f.read_text(encoding="utf-8")
        out = s
        out, n1 = patch_header_span(out)
        out, n2 = patch_js_block(out)
        if out != s:
            f.write_text(out, encoding="utf-8")
            changed += 1
            edits += n1 + n2
    print(f"Done. Updated {changed}/{len(files)} myinfo pages. edits={edits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

