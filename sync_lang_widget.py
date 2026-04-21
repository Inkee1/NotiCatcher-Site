from __future__ import annotations

from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent
    source = root / "en" / "js" / "lang-widget.js"
    if not source.exists():
        raise FileNotFoundError(f"Missing source file: {source}")

    expected = source.read_text(encoding="utf-8")
    targets = sorted(root.glob("*/js/lang-widget.js"))

    changed = 0
    for path in targets:
        if path.resolve() == source.resolve():
            continue

        current = path.read_text(encoding="utf-8")
        if current == expected:
            continue

        path.write_text(expected, encoding="utf-8")
        changed += 1

    print(f"Done. Updated {changed}/{max(len(targets) - 1, 0)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
