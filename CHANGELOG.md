# Changelog

All notable changes to this project are documented here.

## [1.0.4] - 2026-07-28

### Fixed
- Installer wizard now always shows the "Select Destination Location" page
  (`DisableDirPage=no`), so you can choose where the app installs instead
  of only using the default path.
- The desktop app's console window no longer closes instantly when no
  YouTube API key is configured and it's launched with no arguments
  (Start Menu/double-click) — it now pauses so the error message and the
  key-entry prompt are actually readable before exiting.

### Documented
- README: why the "Windows protected your PC" SmartScreen warning appears
  on the installer download (unsigned exe, not malware) and how to
  proceed.
- README: how to add a YouTube API key after installation if you skipped
  it during setup (the automatic first-run prompt, or editing
  `%APPDATA%\YouTubeContentResearch\.env` directly).

## [1.0.3] - 2026-07-28

### Fixed
- Channel mode ("exact channel name/@handle/URL" search) now applies the
  same breakout (`views > subscribers`) filter and ratio sort as topic
  search, instead of showing the channel's raw top-by-views videos
  unfiltered. Previously a channel's videos could appear labeled "high
  organic interest" even with a views/subscribers ratio well under 1x.
- Removed the relevance "bypass" that returned every breakout-qualifying
  candidate, unfiltered by text relevance, whenever the candidate pool was
  large enough (>=5) and none matched the query textually. This produced
  false positives (e.g. a search for a person's name returning unrelated
  videos from random channels). Script/brand-mismatch searches (the
  original reason for the bypass, e.g. "Нова телевизия" vs. channel
  "NOVA") should use the new explicit channel mode instead.
- Relevance matching now checks only the video title, not the
  description — descriptions are noisy (hashtags, generic boilerplate)
  and were producing false-positive matches on generic query words that
  happened to appear somewhere in unrelated text (e.g. a diet-related
  query matching an unrelated recipe video).
- (Extension only) Fixed a race condition where switching search mode
  while a request was still in flight could render the response with the
  wrong (now-current) mode instead of the one it was actually sent with.

### Changed
- Channel-name matching is no longer automatic: both the CLI (`--mode
  channel`, interactive prompt) and the extension (a Videos/Channel
  toggle in the panel) now require explicitly requesting channel mode.
  Previously, any query that happened to exactly match a real channel's
  name was silently narrowed to that channel instead of being searched as
  a topic — e.g. searching the topic "movement" would only show the
  videos of a channel literally named "Movement".

## [1.0.2] - 2026-07-24

### Changed
- Breakout-video criteria loosened: channels of any size now qualify (the
  previous ≥100,000 subscriber gate is gone), the view floor for very small
  channels (<100 subscribers) is raised from 1,000 to 2,500, and results are
  sorted purely by views/subscribers ratio instead of grouping the largest
  channels first. Applies to both the CLI/desktop app and the browser
  extension (they share the same rules).

### Added
- `pytest` test suite for `youtube/filters.py` and `youtube/search.py`,
  backed by an in-memory fake YouTube client (no real API calls or key
  needed). Runs automatically in CI on every push/PR.

### Fixed
- Extension manifest description no longer references the removed
  "established channels only" requirement.

### Internal
- Bumped all GitHub Actions (`checkout`, `setup-python`, `setup-node`,
  `upload-artifact`, `action-gh-release`) off their Node.js 20 runtimes to
  Node.js 24, clearing GitHub's Node 20 deprecation warning.

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
