from __future__ import annotations

import re
from pathlib import Path


def patch_css(css: str) -> tuple[str, bool]:
    if "max-height:" in css and "overflow-y:" in css and ".lang-fab__menu" in css:
        return css, False

    # Find the .lang-fab__menu block and inject scroll styles near the end of that block.
    m = re.search(r"\.lang-fab__menu\s*\{([\s\S]*?)\n\}", css)
    if not m:
        return css, False

    block = m.group(0)
    if "overflow-y" in block or "max-height" in block:
        return css, False

    injection = (
        "\n"
        "  /* Allow long language lists to scroll */\n"
        "  max-height: min(60vh, 420px);\n"
        "  overflow-y: auto;\n"
        "  overscroll-behavior: contain;\n"
        "  -webkit-overflow-scrolling: touch;\n"
    )

    # Insert right before the closing brace of the menu block.
    patched_block = re.sub(r"\n\}$", injection + "\n}", block, count=1)
    if patched_block == block:
        return css, False

    out = css[: m.start()] + patched_block + css[m.end() :]
    return out, True


def main() -> int:
    root = Path(__file__).resolve().parent
    files = sorted(root.rglob("css/lang-widget.css"))
    changed = 0
    for f in files:
        original = f.read_text(encoding="utf-8")
        updated, did = patch_css(original)
        if did:
            f.write_text(updated, encoding="utf-8")
            changed += 1
    print(f"Done. Updated {changed}/{len(files)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

