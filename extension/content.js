// Засича търсене в YouTube (включително SPA навигация) и презаписва
// резултатите с филтрирания/сортиран списък, върнат от background.js —
// но само на таба "Всички" (по подразбиране). Останалите нативни табове
// (Shorts, Гледани, Негледани, Видеоклипове, Наскоро качени, На живо)
// остават напълно функционални и непокътнати, за да работят нормално.
//
// Нативните резултати на таб "Всички" се крият чрез display:none на цялата
// обвивка (не на отделните секции), защото YouTube добавя съдържание (вкл.
// Shorts shelf-а) асинхронно след първоначалното зареждане — скриване само
// на секциите, видими в момента на рендериране, оставя по-късно добавени
// елементи неприкрити. MutationObserver следи за такива по-късни добавяния
// и презасича видимостта.

const PANEL_ID = "yt-filter-overlay-panel";
const BANNER_ID = "yt-filter-overlay-banner";
const HIDDEN_CLASS = "yt-filter-hidden-native";

const DATE_RANGE_OPTIONS = [
  { key: "auto", label: "Auto" },
  { key: "3m", label: "3 months" },
  { key: "6m", label: "6 months" },
  { key: "1y", label: "1 year" },
  { key: "1y+", label: "Over 1 year" },
];
const DEFAULT_DATE_RANGE = "auto";

// "video" винаги търси по думи (никога не разпознава канал от заявката, дори
// тя случайно да съвпада с точно име на канал). "channel" изрично търси по
// @handle/URL/точно име на канал (resolveChannel в background.js). Изборът е
// на потребителя — по подразбиране "video", за да не се "хваща" грешен канал
// без изричен избор.
const SEARCH_MODE_OPTIONS = [
  { key: "video", label: "Videos" },
  { key: "channel", label: "Channel" },
];
const DEFAULT_SEARCH_MODE = "video";

let lastProcessedKey = null;
let currentDateRange = DEFAULT_DATE_RANGE;
let currentSearchMode = DEFAULT_SEARCH_MODE;
let mutationObserver = null;
let extensionEnabled = true;
// Кеш на последно рендерирания панел — YouTube понякога изцяло презаписва
// контейнера с резултати (собствен re-render), което премахва панела ни от
// DOM-а. Периодичните проверки само преместват СЪЩЕСТВУВАЩ панел; ако той е
// изчезнал, го пресъздаваме от този кеш вместо да правим ново мрежово
// извикване.
let lastRenderedState = null;

function getSearchQuery() {
  return new URLSearchParams(location.search).get("search_query");
}

function isResultsPage() {
  return location.pathname === "/results" && Boolean(getSearchQuery());
}

// YouTube кодира избрания таб/филтър (Shorts, Гледани, Видеоклипове...) в
// параметъра "sp" — таб "Всички" (по подразбиране) го няма изобщо. Overlay-ят
// се прилага само на таб "Всички"; при всеки друг таб не пипаме нищо, за да
// работят табовете напълно нормално (нативно YouTube поведение).
function isDefaultAllTab() {
  return !new URLSearchParams(location.search).has("sp");
}

function rangeLabel(key) {
  return DATE_RANGE_OPTIONS.find((option) => option.key === key)?.label || key;
}

function findResultsWrapper() {
  const selectors = [
    "ytd-two-column-search-results-renderer ytd-section-list-renderer#contents",
    "ytd-two-column-search-results-renderer #primary #contents",
  ];
  for (const selector of selectors) {
    const el = document.querySelector(selector);
    if (el) {
      return el;
    }
  }
  const firstSection = document.querySelector(
    "ytd-two-column-search-results-renderer ytd-item-section-renderer"
  );
  return firstSection ? firstSection.parentElement : null;
}

async function waitForWrapper(retries = 15, delayMs = 300) {
  for (let i = 0; i < retries; i += 1) {
    const wrapper = findResultsWrapper();
    if (wrapper) {
      return wrapper;
    }
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  return null;
}

function hideNativeResults() {
  const wrapper = findResultsWrapper();
  if (!wrapper) {
    return;
  }
  wrapper.classList.add(HIDDEN_CLASS);

  const panel = document.getElementById(PANEL_ID);
  const banner = document.getElementById(BANNER_ID);
  const parent = wrapper.parentElement;
  if (!parent) {
    return;
  }
  // Панелът/банерът трябва да са преди скритата обвивка, за да се виждат.
  if (panel && panel.nextSibling !== wrapper) {
    parent.insertBefore(panel, wrapper);
  }
  if (banner && banner.nextSibling !== wrapper && !panel) {
    parent.insertBefore(banner, wrapper);
  }
}

function showNativeResults() {
  document.querySelectorAll(`.${HIDDEN_CLASS}`).forEach((el) => {
    el.classList.remove(HIDDEN_CLASS);
  });
}

let hidePassScheduled = false;

// YouTube-ска страница генерира десетки/стотици DOM мутации в секунда
// (lazy-loading на thumbnail-и, брояч на гледания, reels shelf-ове...).
// Изпълнение на hideNativeResults() синхронно за ВСЯКА от тях блокира main
// thread-а достатъчно, за да предизвика "страницата не отговаря" в Chrome.
// requestAnimationFrame коалесцира произволен брой мутации в рамките на един
// кадър в едно-единствено (евтино) презасичане.
function scheduleHidePass() {
  if (hidePassScheduled) {
    return;
  }
  hidePassScheduled = true;
  requestAnimationFrame(() => {
    hidePassScheduled = false;
    // extensionEnabled се проверява отново тук (не само в MutationObserver
    // callback-а) — rAF е асинхронен, разширението може да е било изключено
    // между планирането и изпълнението на този кадър.
    if (extensionEnabled && isResultsPage() && isDefaultAllTab()) {
      hideNativeResults();
      ensurePanelPresent();
    }
  });
}

function ensureObserver() {
  if (mutationObserver) {
    return;
  }
  mutationObserver = new MutationObserver(() => {
    if (isResultsPage() && isDefaultAllTab()) {
      scheduleHidePass();
    }
  });
  // attributes: true (с filter) хваща и случаите, в които YouTube не добавя
  // нов DOM елемент, а само разкрива вече съществуващ (напр. чрез премахване
  // на "hidden" атрибут или смяна на inline style) — обикновен childList
  // observer пропуска точно такива "reveal" действия.
  mutationObserver.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["hidden", "style", "class"],
  });
}

function removePanel() {
  document.getElementById(PANEL_ID)?.remove();
}

function removeBanner() {
  document.getElementById(BANNER_ID)?.remove();
}

async function showBanner(text, kind) {
  removeBanner();
  const banner = document.createElement("div");
  banner.id = BANNER_ID;
  banner.className = `yt-filter-banner yt-filter-banner--${kind}`;
  banner.textContent = text;

  const wrapper = await waitForWrapper();
  if (wrapper && wrapper.parentElement) {
    wrapper.parentElement.insertBefore(banner, wrapper);
  } else {
    document.body.prepend(banner);
  }
  hideNativeResults();
}

function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatDate(iso) {
  return new Date(iso).toISOString().slice(0, 10);
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function renderControls(query, activeRange, activeSearchMode) {
  const wrap = document.createElement("div");
  wrap.className = "yt-filter-controls";

  for (const option of DATE_RANGE_OPTIONS) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = option.label;
    button.className =
      "yt-filter-control" + (option.key === activeRange ? " yt-filter-control--active" : "");
    button.addEventListener("click", () => {
      if (currentDateRange === option.key) {
        return;
      }
      currentDateRange = option.key;
      runSearch(query, currentDateRange);
    });
    wrap.appendChild(button);
  }

  const divider = document.createElement("div");
  divider.className = "yt-filter-divider";
  wrap.appendChild(divider);

  const modeGroup = document.createElement("div");
  modeGroup.className = "yt-filter-mode-toggle";
  modeGroup.setAttribute("role", "radiogroup");
  modeGroup.setAttribute("aria-label", "Search scope");
  for (const option of SEARCH_MODE_OPTIONS) {
    const label = document.createElement("label");
    label.className = "yt-filter-radio";

    const input = document.createElement("input");
    input.type = "radio";
    input.name = "yt-filter-search-mode";
    input.value = option.key;
    input.checked = option.key === activeSearchMode;
    input.addEventListener("change", () => {
      if (currentSearchMode === option.key) {
        return;
      }
      currentSearchMode = option.key;
      runSearch(query, currentDateRange);
    });

    const text = document.createElement("span");
    text.textContent = option.label;

    label.appendChild(input);
    label.appendChild(text);
    modeGroup.appendChild(label);
  }
  wrap.appendChild(modeGroup);

  return wrap;
}

function renderQuotaLine(quota) {
  const line = document.createElement("div");
  line.className = "yt-filter-quota";
  if (!quota) {
    line.textContent = "Quota: no data";
    return line;
  }
  line.textContent =
    `Quota today (extension-only): ${formatNumber(quota.used)} / ${formatNumber(quota.limit)} units ` +
    `· ~${formatNumber(quota.approxSearchesLeft)} searches left. ` +
    "The real quota may be lower if the same API key is also used elsewhere (e.g. CLI).";
  return line;
}

async function renderResults(
  results,
  query,
  dateRange,
  quota,
  usedTier,
  isChannelMode,
  channelTitle,
  searchMode,
  channelNotFound
) {
  removePanel();
  removeBanner();

  const panel = document.createElement("div");
  panel.id = PANEL_ID;
  panel.className = "yt-filter-panel";

  panel.appendChild(renderControls(query, dateRange, searchMode));
  panel.appendChild(renderQuotaLine(quota));

  const header = document.createElement("div");
  header.className = "yt-filter-panel__header";
  header.textContent = `Filtered results with high organic interest (${results.length})`;
  panel.appendChild(header);

  if (channelNotFound) {
    const note = document.createElement("div");
    note.className = "yt-filter-panel__empty";
    note.textContent =
      `"Channel" mode is selected, but no channel matches "${query}" exactly (by name, @handle, or ` +
      'URL). Switch to "Videos" to search it as a regular keyword instead.';
    panel.appendChild(note);
  }

  // Channel-mode (user explicitly picked "Channel" and the query matched a
  // channel by name/handle/URL) scopes the search to that one channel's
  // videos, but still applies the same breakout filter as topic search —
  // make the scoping explicit so a low result count isn't mistaken for the
  // filter being broken.
  if (isChannelMode) {
    const note = document.createElement("div");
    note.className = "yt-filter-panel__empty";
    note.textContent =
      `"${query}" matched channel "${channelTitle}" exactly — results are scoped to that channel's ` +
      "videos, still filtered by the breakout (views > subscribers) rule.";
    panel.appendChild(note);
  }

  // With "Auto", the cascade may have widened the range beyond 3 months
  // (requirement: 3m -> 6m -> 1y -> all, stopping at the first tier with
  // results) — explicitly explain why a wider range is shown.
  if (dateRange === "auto" && usedTier && usedTier !== "3m") {
    const note = document.createElement("div");
    note.className = "yt-filter-panel__empty";
    note.textContent =
      `Not enough results in shorter ranges — automatically widened to "${rangeLabel(usedTier)}".`;
    panel.appendChild(note);
  }

  if (results.length === 0 && !channelNotFound) {
    const empty = document.createElement("div");
    empty.className = "yt-filter-panel__empty";
    empty.textContent = "No videos match the given criteria.";
    panel.appendChild(empty);
  }

  for (const item of results) {
    const card = document.createElement("a");
    card.className = "yt-filter-card";
    card.href = item.url;
    card.innerHTML = `
      <img class="yt-filter-card__thumb" src="${item.thumbnail}" alt="" loading="lazy">
      <div class="yt-filter-card__body">
        <div class="yt-filter-card__title">${escapeHtml(item.title)}</div>
        <div class="yt-filter-card__channel">${escapeHtml(item.channelTitle)}</div>
        <div class="yt-filter-card__stats">
          <span>Views: ${formatNumber(item.viewCount)}</span>
          <span>Subs: ${formatNumber(item.subscriberCount)}</span>
          <span>Ratio: ${item.ratio.toFixed(2)}x</span>
          <span>${formatDate(item.publishedAt)}</span>
        </div>
      </div>
    `;
    panel.appendChild(card);
  }

  const wrapper = await waitForWrapper();
  if (wrapper && wrapper.parentElement) {
    wrapper.parentElement.insertBefore(panel, wrapper);
  } else {
    document.body.prepend(panel);
  }
  hideNativeResults();

  lastRenderedState = {
    results,
    query,
    dateRange,
    quota,
    usedTier,
    isChannelMode,
    channelTitle,
    searchMode,
    channelNotFound,
  };
}

// Ако YouTube е презаписал контейнера с резултати и е отнесъл панела ни
// заедно с него (document.getElementById вече не го намира), го
// пресъздаваме от последно кешираното състояние — без нова мрежова заявка.
async function ensurePanelPresent() {
  if (!lastRenderedState || document.getElementById(PANEL_ID)) {
    return;
  }
  const {
    results,
    query,
    dateRange,
    quota,
    usedTier,
    isChannelMode,
    channelTitle,
    searchMode,
    channelNotFound,
  } = lastRenderedState;
  await renderResults(
    results,
    query,
    dateRange,
    quota,
    usedTier,
    isChannelMode,
    channelTitle,
    searchMode,
    channelNotFound
  );
}

// YouTube зарежда допълнително съдържание асинхронно, на талази, известно
// време след първоначалната навигация — обикновеният 800ms интервал понякога
// изостава с до ~800ms, през които непокрито съдържание проблясва видимо.
// Този "burst" скрива на много по-кратки интервали за няколко секунди веднага
// след ново търсене, за да затвори прозореца без клик от потребителя.
function burstHideNativeContent(durationMs = 5000, intervalMs = 150) {
  const stopAt = Date.now() + durationMs;
  const intervalId = setInterval(() => {
    if (Date.now() > stopAt || !extensionEnabled || !isResultsPage() || !isDefaultAllTab()) {
      clearInterval(intervalId);
      return;
    }
    hideNativeResults();
  }, intervalMs);
}

async function runSearch(query, dateRange) {
  removePanel();
  lastRenderedState = null; // ново търсене в ход — старият кеш вече не е валиден
  ensureObserver();
  burstHideNativeContent();
  await showBanner(`Filtering results for "${query}" (${rangeLabel(dateRange)})…`, "loading");

  // Прихванато тук, не прочетено от currentSearchMode вътре в callback-а: ако
  // потребителят превключи режима, докато тази заявка е в ход, response
  // callback-ът трябва да отрази режима, с който РЕАЛНО е пратена именно тази
  // заявка — не какъвто currentSearchMode се окаже да е в момента на отговора
  // (по-бавен "Channel" отговор, пристигнал след по-бърз следващ "Videos"
  // клик, иначе би се рендирал с грешно маркиран активен бутон).
  const requestedSearchMode = currentSearchMode;

  chrome.runtime.sendMessage(
    { type: "FILTERED_SEARCH", query, dateRange, searchMode: requestedSearchMode },
    async (response) => {
      // If the extension was turned off while we were waiting for a response
      // from background.js (async network request), this callback will still
      // fire later — without this check it would overwrite the panel/banner as
      // if nothing had been turned off. Late responses are ignored entirely.
      if (!extensionEnabled) {
        return;
      }
      if (chrome.runtime.lastError) {
        await showBanner(`Error: ${chrome.runtime.lastError.message}`, "error");
        return;
      }
      if (!response) {
        await showBanner("No response from the extension.", "error");
        return;
      }
      if (response.error === "NO_API_KEY") {
        await showBanner(
          "No YouTube API key set. Open the extension icon in the top-right of the browser and enter one.",
          "error"
        );
        return;
      }
      if (response.error === "QUOTA_EXCEEDED") {
        const used = response.quota ? formatNumber(response.quota.used) : "?";
        const limit = response.quota ? formatNumber(response.quota.limit) : "10,000";
        await showBanner(
          `The daily YouTube Data API quota is exhausted (${used} / ${limit} units). ` +
            "Wait until tomorrow or use another API key — this does NOT mean there are no matching videos.",
          "error"
        );
        return;
      }
      if (response.error) {
        await showBanner(`Error from YouTube API: ${response.error}`, "error");
        return;
      }
      await renderResults(
        response.results,
        query,
        dateRange,
        response.quota,
        response.usedTier,
        response.isChannelMode,
        response.channelTitle,
        requestedSearchMode,
        response.channelNotFound
      );
    }
  );
}

async function handleNavigation() {
  if (!extensionEnabled || !isResultsPage()) {
    return;
  }

  const query = getSearchQuery();
  const onAllTab = isDefaultAllTab();
  const key = `${query}::${onAllTab ? "all" : "native"}`;
  if (key === lastProcessedKey) {
    return;
  }
  lastProcessedKey = key;

  if (!onAllTab) {
    // Друг таб (Shorts, Гледани, Видеоклипове...) — не пипаме нищо, нека
    // YouTube си покаже нативните резултати за този таб напълно нормално.
    removePanel();
    removeBanner();
    showNativeResults();
    lastRenderedState = null;
    return;
  }

  await runSearch(query, currentDateRange);
}

document.addEventListener("yt-navigate-finish", handleNavigation);
window.addEventListener("popstate", handleNavigation);

setInterval(() => {
  if (!extensionEnabled || !isResultsPage()) {
    return;
  }
  const onAllTab = isDefaultAllTab();
  const key = `${getSearchQuery()}::${onAllTab ? "all" : "native"}`;
  if (key !== lastProcessedKey) {
    handleNavigation();
  } else if (onAllTab) {
    hideNativeResults();
    ensurePanelPresent();
  }
}, 800);

// Възстановява страницата в напълно нативно състояние (маха панел/банер и
// разкрива всичко скрито) — извиква се при изключване на разширението.
//
// ВАЖНО: спира и MutationObserver-а изцяло (не само проверка на флаг) —
// той реагира на почти всяка DOM промяна на YouTube (много чести), затова
// само проверка "if enabled" в callback-а му не е достатъчна: showNativeResults()
// щеше веднага да бъде обезсилен от следващото извикване на hideNativeResults()
// от observer-а, преди потребителят изобщо да види нативните резултати.
function disableOverlay() {
  if (mutationObserver) {
    mutationObserver.disconnect();
    mutationObserver = null;
  }
  removePanel();
  removeBanner();
  showNativeResults();
  lastProcessedKey = null; // форсира ново обработване, ако бъде включено пак
  lastRenderedState = null;
}

chrome.storage.sync.get({ extensionEnabled: true }).then(({ extensionEnabled: value }) => {
  extensionEnabled = value;
  if (extensionEnabled) {
    handleNavigation();
  }
});

// Реагира моментално на включване/изключване от popup-а, без да е нужно
// презареждане на страницата.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "sync" || !("extensionEnabled" in changes)) {
    return;
  }
  extensionEnabled = changes.extensionEnabled.newValue;
  if (extensionEnabled) {
    handleNavigation();
  } else {
    disableOverlay();
  }
});
