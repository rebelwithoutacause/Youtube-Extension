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
  { key: "auto", label: "Автоматично" },
  { key: "3m", label: "3 месеца" },
  { key: "6m", label: "6 месеца" },
  { key: "1y", label: "1 година" },
  { key: "1y+", label: "Над 1 година" },
];
const DEFAULT_DATE_RANGE = "auto";

let lastProcessedKey = null;
let currentDateRange = DEFAULT_DATE_RANGE;
let mutationObserver = null;
let extensionEnabled = true;

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
  return new Intl.NumberFormat("bg-BG").format(value);
}

function formatDate(iso) {
  return new Date(iso).toISOString().slice(0, 10);
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function renderControls(query, activeRange) {
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

  return wrap;
}

function renderQuotaLine(quota) {
  const line = document.createElement("div");
  line.className = "yt-filter-quota";
  if (!quota) {
    line.textContent = "Квота: няма данни";
    return line;
  }
  line.textContent =
    `Квота днес (само от разширението): ${formatNumber(quota.used)} / ${formatNumber(quota.limit)} units ` +
    `· ~${formatNumber(quota.approxSearchesLeft)} търсения остават. ` +
    "Реалната квота може да е по-ниска, ако същият API ключ се ползва и другаде (напр. CLI).";
  return line;
}

async function renderResults(results, query, dateRange, quota, usedTier) {
  removePanel();
  removeBanner();

  const panel = document.createElement("div");
  panel.id = PANEL_ID;
  panel.className = "yt-filter-panel";

  panel.appendChild(renderControls(query, dateRange));
  panel.appendChild(renderQuotaLine(quota));

  const header = document.createElement("div");
  header.className = "yt-filter-panel__header";
  header.textContent = `Филтрирани резултати с висок органичен интерес (${results.length})`;
  panel.appendChild(header);

  // При "Автоматично" каскадата може да е разширила периода отвъд 3 месеца
  // (изискване: 3м -> 6м -> 1г -> всички, спирайки на първото ниво с
  // резултати) — обясняваме изрично защо се вижда по-широк период.
  if (dateRange === "auto" && usedTier && usedTier !== "3m") {
    const note = document.createElement("div");
    note.className = "yt-filter-panel__empty";
    note.textContent =
      `Няма достатъчно резултати в по-кратки периоди — автоматично разширено до "${rangeLabel(usedTier)}".`;
    panel.appendChild(note);
  }

  if (results.length === 0) {
    const empty = document.createElement("div");
    empty.className = "yt-filter-panel__empty";
    empty.textContent = "Няма видеа, отговарящи на зададените критерии.";
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
  ensureObserver();
  burstHideNativeContent();
  await showBanner(`Филтриране на резултати за "${query}" (${rangeLabel(dateRange)})…`, "loading");

  chrome.runtime.sendMessage({ type: "FILTERED_SEARCH", query, dateRange }, async (response) => {
    // Ако разширението е било изключено, докато чакахме отговор от
    // background.js (асинхронна мрежова заявка), този callback все пак ще
    // "изгърми" по-късно — без тази проверка той презаписва панела/банера,
    // сякаш нищо не е изключено. Late-response се игнорира изцяло.
    if (!extensionEnabled) {
      return;
    }
    if (chrome.runtime.lastError) {
      await showBanner(`Грешка: ${chrome.runtime.lastError.message}`, "error");
      return;
    }
    if (!response) {
      await showBanner("Няма отговор от разширението.", "error");
      return;
    }
    if (response.error === "NO_API_KEY") {
      await showBanner(
        "Няма зададен YouTube API ключ. Отворете иконата на разширението горе вдясно в браузъра и го въведете.",
        "error"
      );
      return;
    }
    if (response.error === "QUOTA_EXCEEDED") {
      const used = response.quota ? formatNumber(response.quota.used) : "?";
      const limit = response.quota ? formatNumber(response.quota.limit) : "10 000";
      await showBanner(
        `Дневната квота на YouTube Data API е изчерпана (${used} / ${limit} units). ` +
          "Изчакайте до утре или използвайте друг API ключ — това НЕ означава, че няма подходящи видеа.",
        "error"
      );
      return;
    }
    if (response.error) {
      await showBanner(`Грешка от YouTube API: ${response.error}`, "error");
      return;
    }
    await renderResults(response.results, query, dateRange, response.quota, response.usedTier);
  });
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
