"""
Single entry point for building the standalone Windows executable. Used both
locally and by .github/workflows/release.yml, so the exe/version metadata can
never drift between a dev machine and CI.

Reads VERSION (single source of truth), renders:
  - build/version_info.txt   (Windows VSVersionInfo, consumed by PyInstaller)
  - installer/version.iss    (#define AppVersion "X.Y.Z", consumed by Inno Setup)
then runs PyInstaller to produce dist/YouTubeContentResearch.exe.

Usage: python scripts/build.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "YouTubeContentResearch"
PRODUCT_NAME = "YouTube Content Research Tool"
COMPANY_NAME = "YouTube Content Research Tool (open source, unofficial)"
COPYRIGHT = "MIT License. Not affiliated with YouTube or Google."

VERSION_INFO_TEMPLATE = """# UTF-8
#
# For explanation of the fields see PyInstaller's Version-info file docs.
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({v_tuple}),
    prodvers=({v_tuple}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'{company}'),
        StringStruct(u'FileDescription', u'{product} - CLI'),
        StringStruct(u'FileVersion', u'{v_dotted}'),
        StringStruct(u'InternalName', u'{app_name}'),
        StringStruct(u'LegalCopyright', u'{copyright}'),
        StringStruct(u'OriginalFilename', u'{app_name}.exe'),
        StringStruct(u'ProductName', u'{product}'),
        StringStruct(u'ProductVersion', u'{v_dotted}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""

VERSION_ISS_TEMPLATE = '#define AppVersion "{version}"\n'


def read_version() -> str:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    parts = version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise SystemExit(f"VERSION file must be X.Y.Z (got {version!r})")
    return version


def render_version_info(version: str) -> Path:
    major, minor, patch = version.split(".")
    v_tuple = f"{major}, {minor}, {patch}, 0"
    v_dotted = f"{major}.{minor}.{patch}.0"

    build_dir = ROOT / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    out_path = build_dir / "version_info.txt"
    out_path.write_text(
        VERSION_INFO_TEMPLATE.format(
            v_tuple=v_tuple,
            v_dotted=v_dotted,
            company=COMPANY_NAME,
            product=PRODUCT_NAME,
            app_name=APP_NAME,
            copyright=COPYRIGHT,
        ),
        encoding="utf-8",
    )
    return out_path


def render_installer_version(version: str) -> Path:
    installer_dir = ROOT / "installer"
    installer_dir.mkdir(parents=True, exist_ok=True)
    out_path = installer_dir / "version.iss"
    out_path.write_text(VERSION_ISS_TEMPLATE.format(version=version), encoding="utf-8")
    return out_path


def run_pyinstaller(version_info_path: Path) -> None:
    icon = ROOT / "assets" / "app.ico"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--console",
        "--noconfirm",
        "--clean",
        "--name",
        APP_NAME,
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build" / "pyinstaller"),
        "--specpath",
        str(ROOT / "build"),
        "--version-file",
        str(version_info_path),
    ]
    if icon.is_file():
        cmd += ["--icon", str(icon)]
    cmd.append(str(ROOT / "main.py"))

    print("Running:", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> None:
    version = read_version()
    print(f"Building {PRODUCT_NAME} v{version}")

    version_info_path = render_version_info(version)
    installer_version_path = render_installer_version(version)
    print(f"Wrote {version_info_path}")
    print(f"Wrote {installer_version_path}")

    run_pyinstaller(version_info_path)

    exe_path = ROOT / "dist" / f"{APP_NAME}.exe"
    if not exe_path.is_file():
        raise SystemExit(f"Expected build output not found: {exe_path}")
    print(f"Built {exe_path} ({exe_path.stat().st_size / 1_000_000:.1f} MB)")


if __name__ == "__main__":
    main()
