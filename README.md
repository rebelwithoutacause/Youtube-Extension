# YouTube Content Research Tool

[![Latest release](https://img.shields.io/github/v/release/rebelwithoutacause/Youtube-Extension?label=download&color=e62117)](../../releases/latest)

Find **breakout video topics** from established YouTube channels — videos
whose view count significantly outperforms the channel's subscriber count,
which is a strong signal of a viral/trending topic worth studying.

> Unofficial, community-built tool. Not affiliated with, endorsed by, or
> sponsored by YouTube or Google LLC.

<p align="center">
  <img src="Screenshot/Interface.png" alt="Extension popup: on/off toggle, API key rotation list, and per-key quota" width="360" />
</p>

Three ways to use it:
- **Windows desktop app** — a one-click installer with a wizard, Start Menu
  shortcuts, and an uninstaller. See [Windows Desktop App](#windows-desktop-app) below.
- **CLI tool** (`main.py`) — run a search from the terminal, get a table of results.
- **Browser extension** (`extension/`) — overlays the filtered results directly on
  youtube.com while you search. See [`extension/README.md`](extension/README.md)
  for extension-specific setup and usage.

## 🎥 Demo

Watch the demo videos (presentation, API key setup, and a live search walkthrough):
[Google Drive folder](https://drive.google.com/drive/folders/16gBOkGv7wYI1ld6RiTO0lDYc2vCNjBTK)

## What it does

Given a keyword (e.g. `"fasting"`) or a channel name/handle, the tool finds
videos matching all of the following:

1. **No Shorts** — filtered by actual video duration, not by title text.
2. **Established channels only** — channel must have **≥100,000 subscribers**.
3. **Breakout performance** — views must exceed the channel's subscriber
   count (or be ≥1,000 for very small channels), i.e. the video clearly
   over-performed relative to the channel's usual reach.
4. **Recency, with automatic fallback** — tries the last 3 months first; if
   there are no results, automatically widens to 6 months, then 1 year,
   then no limit at all, stopping at the first tier with results.
5. **Sorted**: videos from the biggest channels first (by subscriber
   count), then the rest by `views / subscribers` ratio.

If the input matches an existing channel's exact name, handle (`@handle`),
or URL instead of a topic keyword, the tool switches to "channel mode" and
shows that channel's own top videos by views for the selected period
instead of doing a topic search.

Built entirely on the **standard, public YouTube Data API v3** — no
partner/proprietary API access required.

### Key rotation

**One API key is enough to run the tool** — `YOUTUBE_API_KEYS` (and the
installer wizard) accept a single key just fine. Extra keys are entirely
optional: if you configure more than one, the tool automatically switches
to the next key when the active one hits its daily quota, retrying the
same request transparently. This only increases your total effective
quota if each key comes from a **different** Google Cloud project (quota
is enforced per-project, not per-key).

## Getting a YouTube Data API v3 key

Every user runs this with their **own** free key — none is bundled with the
app, CLI, or extension.

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and sign in.
2. Create a new project (or select an existing one).
3. **APIs & Services → Library** → search **"YouTube Data API v3"** → **Enable**.
4. **APIs & Services → Credentials** → **+ Create Credentials → API key**.
5. Copy the generated key. (Recommended: restrict it to "YouTube Data API v3".)

> Free daily quota is 10,000 units **per API key** (i.e. per Google Cloud
> project). Configure multiple keys (from different projects) for key
> rotation to get a higher combined daily total.

## Windows Desktop App

Download the latest `YouTubeContentResearchSetup-*.exe` from the
[Releases](../../releases) page and run it. The installer:

- Walks you through an **installer wizard** with an optional page to enter
  your own YouTube API key(s) up front (or skip it — the app will ask on
  first run instead). One key is enough — the second and third key fields
  are only for optional quota rotation, not required to run the app.
- Installs a standalone `YouTubeContentResearch.exe` (no Python required)
  with a Start Menu group, optional desktop shortcut, and a proper
  uninstaller (Add/Remove Programs).
- Copies the browser extension source next to the app so you can load it in
  Chrome/Edge (see below) without a separate download.

Launching the app with no arguments opens an **interactive prompt**: type a
search query, pick a date range, and it prints a results table — press Enter
on an empty query to exit. It also still works as a scriptable CLI:

```
YouTubeContentResearch.exe "fasting"
YouTubeContentResearch.exe "movement" --range 6m
```

Chrome can't be configured to install an unpacked extension automatically
during setup (that requires publishing to the Chrome Web Store), so after
installing, load it manually:

1. Open `chrome://extensions` (or Edge's `edge://extensions`).
2. Enable **Developer mode** (top-right toggle).
3. Click **Load unpacked** and select the `extension` folder inside the
   app's install directory (a Start Menu shortcut opens it directly).

Your API key(s) are stored locally at
`%APPDATA%\YouTubeContentResearch\.env` — never bundled into the installer
or committed anywhere.

### Building the installer yourself

```
pip install -r requirements.txt -r requirements-build.txt
python scripts/build.py              # -> dist/YouTubeContentResearch.exe
python scripts/package_extension.py  # -> dist/*-extension-v*.zip
ISCC installer\setup.iss             # -> installer/Output/YouTubeContentResearchSetup-*.exe
```

Tagging a commit `vX.Y.Z` (matching the `VERSION` file) and pushing it runs
`.github/workflows/release.yml`, which builds all of the above on
`windows-latest` and publishes them to a GitHub Release automatically.

## CLI usage (from source)

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env and add your key(s)

python main.py "fasting"
python main.py "movement" --range 6m
python main.py "The Clashers"          # exact channel name -> channel mode
python main.py "@milkokukovbg"         # channel handle -> channel mode
python main.py                         # no query -> interactive mode
```

`--range` options: `auto` (default — cascades 3m → 6m → 1y → all), `3m`,
`6m`, `1y`, `1y+` (older than 1 year), `all` (no date limit).

Output is a table with: Title, Channel, Subscribers, Views,
Views/Subscribers, Published, Video URL.

## Browser extension

The `extension/` folder contains a Chrome/Edge extension that applies the
exact same logic live on youtube.com's own search results page, plus a
per-key quota tracker, key rotation, and an on/off toggle. See
[`extension/README.md`](extension/README.md) for installation and usage
instructions.

## Project structure

```
main.py                CLI entry point (also drives the packaged .exe)
requirements.txt       Runtime Python dependencies
requirements-build.txt Build-only dependencies (PyInstaller, Pillow)
.env.example            Config template (copy to .env and add your API key)
VERSION                 Single source of truth for the app version
youtube/
  api.py               YouTube Data API v3 client (batching, retry, quota errors)
  filters.py           Shorts detection, relevance & engagement rules
  models.py            VideoResult dataclass
  search.py            Orchestration: search -> filter -> sort, channel-mode detection, date cascade
  config.py            Settings (thresholds, multi-location .env lookup)
extension/             Browser extension (see its own README)
assets/                App icon source (app.ico / app.png)
scripts/
  build.py             Builds the exe (PyInstaller) + version metadata
  package_extension.py Zips the extension for distribution
  generate_icon.py         Extension icon generator
  generate_app_icon.py     Desktop app icon generator
installer/
  setup.iss            Inno Setup installer script
.github/workflows/
  sanity-check.yml     Syntax/lint checks on every push and PR
  release.yml          Builds & publishes installer + extension zip on version tags
```
