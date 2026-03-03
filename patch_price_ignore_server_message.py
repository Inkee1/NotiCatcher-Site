from __future__ import annotations

import re
from pathlib import Path


PAT = re.compile(r"alert\(\s*data\.message\s*\|\|\s*__WEB_SUB_COPY\.msgAlreadySubscribed\s*\)\s*;")


def main() -> int:
    root = Path(__file__).resolve().parent
    files = sorted(root.rglob("price/index.html"))
    changed = 0
    for f in files:
        s = f.read_text(encoding="utf-8")
        if "data.alreadySubscribed" not in s:
            continue
        new, n = PAT.subn("alert(__WEB_SUB_COPY.msgAlreadySubscribed);", s)
        if n:
            f.write_text(new, encoding="utf-8")
            changed += 1
    print(f"Done. Updated {changed} price pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

