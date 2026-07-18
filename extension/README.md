# YouTube High-Interest Filter

A Chrome/Edge extension (Manifest V3) that filters YouTube search results
directly on the page — instead of the normal results, it shows only videos
with **high organic interest**: from established channels, with views
significantly exceeding their subscriber count, excluding Shorts.

## What it does

When you search for something on YouTube (e.g. "fasting", "movement"), the
normal results mix everything together — viral clips, ads, random small
channels, Shorts. This extension overwrites the "All" tab of the search
results page with your own filtered list, matching only videos that meet
all of the following:

1. **Only normal videos** — no YouTube Shorts (detected via the video's
   actual duration, not by text in the title).
2. **Only from established channels** — only channels with **≥100,000
   subscribers**.
3. **Breakout performance** — the video must have "broken out" relative to
   its channel's size:
   - if the channel has ≥100 subscribers → views must exceed the
     subscriber count (`views > subscribers`);
   - if the channel has <100 subscribers → views must be at least 1000.
4. **Recency** — only videos published within a selected time window. By
   default, an **automatic cascade** runs: it tries the last 3 months
   first; if there are no results, it widens to 6 months, then 1 year, then
   no date limit at all — stopping at the first tier that has at least one
   result. You can also manually pick a fixed range (3 months / 6 months /
   1 year / older than 1 year).
5. **Sorting**: videos from the largest channels (by subscriber count)
   first, then the rest — sorted by `views / subscribers` ratio.

### Recognizing a channel by name

If you type the **exact name of a channel** (e.g. "The Clashers"), an
**@handle** (e.g. `@milkokukovbg`), or a direct channel link, the extension
recognizes this and, instead of a general topic search, shows **that
channel's own videos** for the selected time range, sorted by views —
without the subscriber-count/organic-interest filter (since the goal here
is that specific channel, not discovering "breakout" topics).

## Installation

### 1. Get a YouTube Data API v3 key

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and sign in with a Google account (requires 2-step verification to be enabled).
2. Create a new project (or select an existing one).
3. **APIs & Services → Library** → search for **"YouTube Data API v3"** → **Enable**.
4. **APIs & Services → Credentials** → **+ Create Credentials → API key**.
5. Copy the generated key.
6. (Recommended) Restrict the key: **Edit API key → API restrictions → Restrict key** → check only "YouTube Data API v3". Leave "Application restrictions" set to **None** — the key is used by a browser extension, not a public website.

> The free daily quota is 10,000 units. Each search costs roughly 5–500
> units depending on the number of candidates and whether the date-range
> cascade kicks in — check the quota counter inside the extension.

### 2. Load the extension in your browser

1. Open `chrome://extensions` (or `edge://extensions`).
2. Enable **"Developer mode"** (top right).
3. Click **"Load unpacked"** and select the `extension/` folder from this project.
4. The extension appears in the toolbar (click the puzzle-piece icon → pin it for convenience).

### 3. Set the API key

1. Click the extension's icon.
2. Paste the API key into the field and click **"Запази" (Save)**.
3. Reload (F5) any open youtube.com tab.

## Usage

### Search by topic

1. Go to **youtube.com** and type a keyword into the search bar (e.g. "fasting").
2. On the **"All"** tab, the overlay automatically shows a filtered panel instead of the native results.
3. The **Shorts / Unwatched / Watched / Videos / Recently uploaded / Live** tabs remain completely normal (native YouTube behavior) — the overlay never touches them.

### Search by channel

Type the exact channel name, `@handle`, or a link to it instead of a
keyword — the extension automatically switches to "channel mode" and shows
that channel's own videos.

### Choosing a date range

Above the results there are buttons: **Auto** (default), **3 months**,
**6 months**, **1 year**, **Older than 1 year**. Clicking a button
re-fetches the results with the new range, without needing a new search.

### Turning it on/off

Click the extension's icon → radio buttons **On / Off**. Takes effect
instantly, no page reload needed — when turned off, the overlay disappears
and the native YouTube results are fully restored.

### Checking the quota

Below the range buttons in the panel, and in the extension's popup, you can
see the approximate daily quota used (in units) and how many searches are
left.

> **Note:** the counter only tracks requests made **through the extension
> itself**. If the same API key is also used elsewhere (e.g. via the CLI
> tool in the main project), the real Google-side quota may be lower than
> what's shown here — YouTube provides no way to directly check the actual
> remaining quota.

## File structure

| File | Role |
|---|---|
| `manifest.json` | Manifest V3 configuration — permissions, content script, background worker, popup |
| `background.js` | Service worker: calls the YouTube Data API (search/videos/channels), applies all filters and sorting, tracks quota usage |
| `content.js` | Injected into youtube.com/results — detects the search, hides the native results on the "All" tab, renders the filtered panel |
| `content.css` | Styles for the banner, panel, result cards, and range buttons (light/dark theme) |
| `popup.html` / `popup.js` | UI for setting the API key, turning the extension on/off, viewing the quota |
| `icons/` | Extension icon (16/32/48/128 px) — a white funnel on a YouTube-red background |

## Known limitations

- The overlay relies on YouTube's current HTML structure (`ytd-two-column-search-results-renderer` and others). A future YouTube redesign may require updating the selectors in `content.js`.
- The relevance/spam filter isn't perfect for every language or brand name — see the comments in `background.js` for details on the trade-offs.
- The quota counter is a local estimate, not official data from Google (see the note above).
