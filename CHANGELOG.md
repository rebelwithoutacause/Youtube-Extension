# Changelog

All notable changes to this project are documented here.

## [1.0.1] - 2026-07-20

### Fixed
- Installer now bundles and silently installs the Microsoft Visual C++
  2015-2022 x64 Redistributable if it isn't already present, before
  launching the app. The PyInstaller-built exe depends on
  `VCRUNTIME140.dll` / `VCRUNTIME140_1.dll` / `ucrtbase.dll` / `msvcp_win.dll`,
  which are present on most Windows 10/11 machines (usually installed by
  some other app) but are not guaranteed on a truly bare install — a real
  install/uninstall test confirmed the rest of the installer works
  correctly, but this closes the one remaining gap for a genuinely clean
  machine. Detected via the registry (skipped if already installed), adds
  ~25 MB to the installer only when needed at install time.

## [1.0.0] - 2026-07-20

### Added
- Windows desktop app: Inno Setup installer with a wizard page for entering
  your own YouTube API key(s), Start Menu shortcuts, optional desktop icon,
  and a proper uninstaller.
- Standalone `YouTubeContentResearch.exe` built with PyInstaller — no Python
  installation required to run the CLI.
- Interactive mode: launching the app/CLI with no query prompts for a search
  in a loop instead of requiring command-line arguments.
- First-run prompt to configure a YouTube API key when none is found, saved
  to `%APPDATA%\YouTubeContentResearch\.env`.
- Multi-location `.env` lookup (next to the executable, per-user AppData,
  then current working directory) so the same config code works both from
  source and from the packaged exe.
- Dedicated desktop app icon (`assets/app.ico`), consistent with the
  browser extension's icon design.
- `scripts/build.py` and `scripts/package_extension.py` — single-command
  build tooling for the exe and the extension zip, shared between local
  development and CI.
- `.github/workflows/release.yml` — builds the installer and extension
  package on `windows-latest` and publishes them to a GitHub Release on
  version tags (`vX.Y.Z`), with SHA256 checksums.
- `LICENSE` (MIT).

### Existing (carried over from the original CLI/extension)
- YouTube Data API v3 based search with Shorts filtering, established-channel
  filtering, breakout-performance filtering, automatic date-range cascade,
  and multi-key rotation.
- Chrome/Edge browser extension applying the same filtering live on
  youtube.com.
