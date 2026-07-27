# YouTube High-Interest Filter

A Chrome/Edge extension (Manifest V3) that filters YouTube search results
directly on the page — instead of the normal results, it shows only videos
with **high organic interest**: views significantly exceeding their
channel's subscriber count, excluding Shorts.

## What it does

When you search for something on YouTube (e.g. "fasting"), the normal
results mix everything together — viral clips, ads, random small channels,
Shorts. This extension overwrites the "All" tab of the search results page
with your own filtered list, matching only videos that meet all of the
following:

1. **Only normal videos** — no YouTube Shorts (detected via the video's
   actual duration, not by text in the title).
2. **Breakout performance** — the video must have "broken out" relative to
   its channel's size, regardless of the channel's size:
   - if the channel has ≥100 subscribers → views must exceed the
     subscriber count (`views > subscribers`);
   - if the channel has <100 subscribers → views must be at least 2500.
3. **Recency** — only videos published within a selected time window. By
   default, an **automatic cascade** runs: it tries the last 3 months
   first; if there are no results, it widens to 6 months, then 1 year, then
   no date limit at all — stopping at the first tier that has at least one
   result. You can also manually pick a fixed range (3 months / 6 months /
   1 year / older than 1 year).
4. **Sorting**: sorted by `views / subscribers` ratio.

### Videos vs. Channel mode

Next to the date-range buttons, the panel has a **Videos / Channel**
toggle:

- **Videos** (default) — always a plain keyword search. The query is never
  auto-matched against channel names, so a topic word that happens to
  coincide with a real channel's name (e.g. "movement") is still searched
  as a topic across all channels, not silently narrowed to that one
  channel.
- **Channel** — only when explicitly selected: if the query is the
  **exact name of a channel** (e.g. "The Clashers"), an **@handle** (e.g.
  `@milkokukovbg`), or a direct channel link, the search is scoped to
  **that channel's own videos** for the selected time range. The same
  breakout filter and `views / subscribers` sorting from above still
  apply — only the candidate pool is narrowed to that one channel, so a
  channel whose videos never exceed its own subscriber count correctly
  yields zero results (and the automatic date-range cascade widens the
  window, same as a topic search). If no channel matches the query
  exactly, the panel says so instead of silently falling back to a topic
  search.

Matching also transliterates Cyrillic ⇄ Latin, so a query like
`"милко атанасов"` correctly matches a channel titled `"Milko Atanasov"`
(and vice versa) instead of a different, unrelated channel that happens to
share the same name in the same script.

### Key rotation

You can add multiple API keys in the popup. When the active key hits its
daily quota, the extension automatically switches to the next one and
retries the same request — transparent to you, mid-search. This only
increases your total effective quota if each key comes from a
**different** Google Cloud project (quota is enforced per-project, not
per-key). Keys are stored in `chrome.storage.local` — only on this device,
never synced through your Google account.

## Installation

### 1. Get a YouTube Data API v3 key

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and sign in with a Google account (requires 2-step verification to be enabled).
2. Create a new project (or select an existing one).
3. **APIs & Services → Library** → search for **"YouTube Data API v3"** → **Enable**.
4. **APIs & Services → Credentials** → **+ Create Credentials → API key**.
5. Copy the generated key.
6. (Recommended) Restrict the key: **Edit API key → API restrictions → Restrict key** → check only "YouTube Data API v3". Leave "Application restrictions" set to **None** — the key is used by a browser extension, not a public website.

> The free daily quota is 10,000 units **per API key** (i.e. per Google
> Cloud project). Each search costs roughly 5–500 units depending on the
> number of candidates and whether the date-range cascade kicks in — check
> the quota counter inside the extension. Add multiple keys (see
> [Key rotation](#key-rotation) above) for a higher combined daily total.

### 2. Load the extension in your browser

1. Open `chrome://extensions` (or `edge://extensions`).
2. Enable **"Developer mode"** (top right).
3. Click **"Load unpacked"** and select the `extension/` folder from this project.
4. The extension appears in the toolbar (click the puzzle-piece icon → pin it for convenience).

### 3. Set your API key(s)

1. Click the extension's icon.
2. Paste your API key into the field and click **"Save"**.
3. (Optional, for key rotation) Click **"+ Add key"** to add more keys —
   each from a **different** Google Cloud project — then **"Save"** again.
4. Reload (F5) any open youtube.com tab.

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
see the approximate combined daily quota used across all configured keys
(in units) and how many searches are left. The popup also shows a
per-key breakdown (used units, or "exhausted for today").

> **Note:** the counter only tracks requests made **through the extension
> itself**. If the same API key is also used elsewhere (e.g. via the CLI
> tool in the main project), the real Google-side quota may be lower than
> what's shown here — YouTube provides no way to directly check the actual
> remaining quota.

## File structure

| File | Role |
|---|---|
| `manifest.json` | Manifest V3 configuration — permissions, content script, background worker, popup |
| `background.js` | Service worker: calls the YouTube Data API (search/videos/channels), applies all filters/sorting, rotates between API keys, tracks per-key quota usage |
| `content.js` | Injected into youtube.com/results — detects the search, hides the native results on the "All" tab, renders the filtered panel, auto-heals it if YouTube's own re-render removes it |
| `content.css` | Styles for the banner, panel, result cards, and range buttons (light/dark theme) |
| `popup.html` / `popup.js` | UI for managing API keys (add/remove, key rotation), turning the extension on/off, viewing combined + per-key quota |
| `icons/` | Extension icon (16/32/48/128 px) — a white funnel on a YouTube-red background |

## Known limitations

- The overlay relies on YouTube's current HTML structure (`ytd-two-column-search-results-renderer` and others). A future YouTube redesign may require updating the selectors in `content.js`.
- The relevance/spam filter isn't perfect for every language or brand name — see the comments in `background.js` for details on the trade-offs.
- The quota counter is a local estimate, not official data from Google (see the note above).
- Cyrillic transliteration covers standard Bulgarian letters only — other Cyrillic-using languages with extra letters (e.g. Russian "ы"/"э", Ukrainian "і"/"ї") aren't mapped.
- Key rotation only increases your effective quota if each key belongs to a different Google Cloud project — multiple keys on the same project share one quota pool.
