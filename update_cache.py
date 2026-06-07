from __future__ import annotations

import argparse
import re
from datetime import UTC, datetime
from pathlib import Path


STATIC_DIR = Path("app/web/static")
ASSET_EXTENSIONS = {".css", ".html", ".js"}
VERSION_RE = re.compile(r"(?P<prefix>[?&]v=)[A-Za-z0-9_.-]+")


def default_version() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def iter_static_files(static_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in static_dir.rglob("*")
        if path.is_file() and path.suffix in ASSET_EXTENSIONS
    )


def update_file(path: Path, version: str, dry_run: bool) -> bool:
    content = path.read_text()
    new_content = VERSION_RE.sub(rf"\g<prefix>{version}", content)
    if new_content == content:
        return False

    if not dry_run:
        path.write_text(new_content)
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="refresh static asset cache-busting versions",
    )
    parser.add_argument(
        "version",
        nargs="?",
        default=default_version(),
        help="version to write after ?v=, defaults to a utc timestamp",
    )
    parser.add_argument(
        "--static-dir",
        default=STATIC_DIR,
        type=Path,
        help="static directory to scan",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show files that would change without writing them",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    changed = [
        path
        for path in iter_static_files(args.static_dir)
        if update_file(path, args.version, args.dry_run)
    ]

    action = "would update" if args.dry_run else "updated"
    for path in changed:
        print(f"{action} {path}")
    print(f"{len(changed)} file(s) {action}")


if __name__ == "__main__":
    main()
