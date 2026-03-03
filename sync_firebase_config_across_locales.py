#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


def main() -> int:
    site_root = Path(__file__).resolve().parent
    source = site_root / "en" / "js" / "firebase-config.js"
    if not source.exists():
        raise SystemExit(f"Missing source file: {source}")

    content = source.read_text(encoding="utf-8")
    updated = 0

    for target in sorted(site_root.glob("*/js/firebase-config.js")):
        # Keep `en/` as the source-of-truth.
        if target.parts[-3].lower() == "en":
            continue
        target.write_text(content, encoding="utf-8")
        updated += 1

    print(f"Synced firebase-config.js to {updated} locale folders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

