"""
Zips extension/ into dist/<slug>-extension-v<manifest version>.zip with the
extension's files at the zip root (not nested in an extension/ folder), so
the archive can be unzipped and loaded directly via Chrome's "Load unpacked",
or uploaded as-is to the Chrome Web Store.

Usage: python scripts/package_extension.py
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTENSION_DIR = ROOT / "extension"
DIST_DIR = ROOT / "dist"

# Files/dirs from extension/ that are documentation, not part of the loadable
# extension package.
EXCLUDE_NAMES = {"README.md"}


def main() -> None:
    manifest_path = EXTENSION_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = manifest["version"]
    slug = "youtube-high-interest-filter"

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = DIST_DIR / f"{slug}-extension-v{version}.zip"
    if zip_path.exists():
        zip_path.unlink()

    files = [
        p
        for p in EXTENSION_DIR.rglob("*")
        if p.is_file() and p.name not in EXCLUDE_NAMES
    ]

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in files:
            arcname = file_path.relative_to(EXTENSION_DIR)
            zf.write(file_path, arcname)

    print(f"Packaged {len(files)} files into {zip_path}")


if __name__ == "__main__":
    main()
