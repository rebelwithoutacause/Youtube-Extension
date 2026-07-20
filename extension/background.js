// Service worker: вика YouTube Data API v3 и прилага същите правила за
// филтриране като Python backend-а (youtube/filters.py, youtube/search.py).

const API_BASE = "https://www.googleapis.com/youtube/v3";
const SEARCH_MAX_RESULTS = 50;
const MIN_VIDEO_DURATION_SECONDS = 60;
const SUBSCRIBER_THRESHOLD = 100;
const MIN_VIEW_COUNT_LOW_SUBS = 1000;
const MIN_CHANNEL_SUBSCRIBER_COUNT = 100_000;
const LARGE_CHANNEL_SUBSCRIBER_THRESHOLD = 500_000;
const RELEVANCE_BYPASS_MIN_CANDIDATES = 5;
const MAX_RETRIES = 5;
const RETRY_BACKOFF_MS = 1000;
const BATCH_SIZE = 50;
const SEARCH_MAX_PAGES = 4; // 4 x 100 units = 400 units за search.list на търсене
const CHANNEL_MAX_PAGES = 5; // 5 x 50 = до 250 скорошни видеа от канал (евтино: 1 unit/страница)

// (afterDays, beforeDays) спрямо "сега". "1y+" няма долна граница — обхваща
// всичко по-старо от 1 година. "all" няма никакво ограничение по дата.
const DATE_RANGE_PRESETS = {
  "3m": { afterDays: 90, beforeDays: null },
  "6m": { afterDays: 180, beforeDays: null },
  "1y": { afterDays: 365, beforeDays: null },
  "1y+": { afterDays: null, beforeDays: 365 },
  all: { afterDays: null, beforeDays: null },
};
const DEFAULT_DATE_RANGE = "3m";

// Автоматична каскада (изискване на клиента): пробвай последните 3 месеца
// първо; ако няма резултати, разшири до 6 месеца, после 1 година, после без
// ограничение — спира на първото ниво с поне 1 резултат.
const AUTO_DATE_RANGE = "auto";
const AUTO_CASCADE_TIERS = ["3m", "6m", "1y", "all"];

const QUOTA_ERROR_REASONS = new Set([
  "quotaExceeded",
  "dailyLimitExceeded",
  "rateLimitExceeded",
  "userRateLimitExceeded",
]);

// YouTube не предоставя API за проверка на оставаща квота — следим сами
// приблизителния разход локално (chrome.storage.local), нулиран всеки ден в
// полунощ Pacific Time (моментът, в който Google нулира реалната квота).
// Проследяването е ПО КЛЮЧ (quotaByKey), за да поддържа key rotation — всеки
// ключ има собствен независим лимит от 10 000 units/ден (само ако идва от
// РАЗЛИЧЕН Google Cloud проект от останалите конфигурирани ключове).
const DAILY_QUOTA_LIMIT = 10_000;
const QUOTA_COSTS = { search: 100, videos: 1, channels: 1, playlistItems: 1 };

function currentPacificDate() {
  // "en-CA" форматира като YYYY-MM-DD — удобно за директно сравнение/пазене.
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Los_Angeles" }).format(new Date());
}

async function getApiKeys() {
  const { apiKeys } = await chrome.storage.local.get({ apiKeys: [] });
  return (apiKeys || []).filter(Boolean);
}

async function recordQuotaUsage(apiKey, units) {
  const today = currentPacificDate();
  const { quotaByKey } = await chrome.storage.local.get({ quotaByKey: {} });
  const entry = quotaByKey[apiKey];
  const used = (entry && entry.date === today ? entry.used : 0) + units;
  quotaByKey[apiKey] = { date: today, used };
  await chrome.storage.local.set({ quotaByKey });
  return used;
}

// Реалният лимит на Google може да удари преди нашата собствена (приблизителна)
// бройка да достигне DAILY_QUOTA_LIMIT (напр. rateLimitExceeded с различен
// праг). Ако това се случи, трайно маркираме ключа като изчерпан ЗА ДНЕС —
// иначе всяко СЛЕДВАЩО търсене пробва отново същия ключ от нула и минава
// през пълните 5 опита с нарастващо изчакване (до ~31 сек) преди да
// превключи, правейки търсенето видимо бавно всеки път.
async function markKeyExhausted(apiKey) {
  const today = currentPacificDate();
  const { quotaByKey } = await chrome.storage.local.get({ quotaByKey: {} });
  quotaByKey[apiKey] = { date: today, used: DAILY_QUOTA_LIMIT };
  await chrome.storage.local.set({ quotaByKey });
}

async function getQuotaUsedForKey(apiKey) {
  const today = currentPacificDate();
  const { quotaByKey } = await chrome.storage.local.get({ quotaByKey: {} });
  const entry = quotaByKey[apiKey];
  return entry && entry.date === today ? entry.used : 0;
}

// Обобщена квота: сбор от всички конфигурирани ключове, плюс разбивка по
// ключ (за popup-а).
async function getQuotaStatus() {
  const apiKeys = await getApiKeys();
  if (apiKeys.length === 0) {
    return { used: 0, limit: DAILY_QUOTA_LIMIT, remaining: DAILY_QUOTA_LIMIT, approxSearchesLeft: 0, keyCount: 0, perKey: [] };
  }

  const perKey = [];
  let used = 0;
  for (const apiKey of apiKeys) {
    const keyUsed = await getQuotaUsedForKey(apiKey);
    used += keyUsed;
    perKey.push({ used: keyUsed, limit: DAILY_QUOTA_LIMIT, exhausted: keyUsed >= DAILY_QUOTA_LIMIT });
  }

  const limit = DAILY_QUOTA_LIMIT * apiKeys.length;
  const remaining = Math.max(0, limit - used);
  return {
    used,
    limit,
    remaining,
    approxSearchesLeft: Math.floor(remaining / (QUOTA_COSTS.search * SEARCH_MAX_PAGES)),
    keyCount: apiKeys.length,
    perKey,
  };
}

function chunk(items, size) {
  const chunks = [];
  for (let i = 0; i < items.length; i += size) {
    chunks.push(items.slice(i, i + size));
  }
  return chunks;
}

function daysAgoIso(days) {
  return new Date(Date.now() - days * 86400000).toISOString();
}

// Key rotation: обвивка около списъка с ключове, която помни кой е текущо
// активен и кои вече са маркирани като изчерпани ЗА ТОЗИ SEARCH RUN. При
// създаване прескача ключове, за които локално вече знаем, че са изчерпани
// днес (>= DAILY_QUOTA_LIMIT), за да не пилеем реална заявка за да го открием.
async function createKeyRotator(apiKeys) {
  const exhausted = new Set();
  for (let i = 0; i < apiKeys.length; i += 1) {
    const used = await getQuotaUsedForKey(apiKeys[i]);
    if (used >= DAILY_QUOTA_LIMIT) {
      exhausted.add(i);
    }
  }

  let index = 0;
  while (index < apiKeys.length && exhausted.has(index)) {
    index += 1;
  }

  return {
    hasAvailableKey() {
      return index < apiKeys.length;
    },
    current() {
      return apiKeys[index];
    },
    totalKeys() {
      return apiKeys.length;
    },
    rotate() {
      exhausted.add(index);
      for (let i = 0; i < apiKeys.length; i += 1) {
        if (!exhausted.has(i)) {
          index = i;
          return true;
        }
      }
      index = apiKeys.length;
      return false;
    },
  };
}

async function apiGet(endpoint, params, keyRotator) {
  const url = new URL(`${API_BASE}/${endpoint}`);
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined) {
      url.searchParams.set(key, String(value));
    }
  }

  let attempt = 0;
  while (true) {
    attempt += 1;
    const apiKey = keyRotator.current();
    await recordQuotaUsage(apiKey, QUOTA_COSTS[endpoint] || 1);
    url.searchParams.set("key", apiKey);
    const response = await fetch(url.toString());

    if (response.status === 429 && attempt <= MAX_RETRIES) {
      const wait = RETRY_BACKOFF_MS * 2 ** (attempt - 1);
      await new Promise((resolve) => setTimeout(resolve, wait));
      continue;
    }

    if (!response.ok) {
      const bodyText = await response.text();
      let reason = null;
      try {
        reason = JSON.parse(bodyText)?.error?.errors?.[0]?.reason || null;
      } catch (_error) {
        // тялото не е JSON — игнорирай, ще хвърлим общата грешка по-долу
      }
      if (QUOTA_ERROR_REASONS.has(reason)) {
        // Трайно маркираме ключа изчерпан за деня (виж коментара при
        // markKeyExhausted) — иначе следващото търсене пак ще го пробва от
        // нула и пак ще чака през пълните retry-опити преди да превключи.
        await markKeyExhausted(apiKey);
        // Key rotation: превключваме на следващия наличен ключ и препробваме
        // СЪЩАТА заявка — прозрачно за извикващия код, вместо да провалим
        // цялото търсене заради 1 изчерпан ключ.
        if (keyRotator.rotate()) {
          attempt = 0;
          continue;
        }
        throw new Error("QUOTA_EXCEEDED");
      }
      throw new Error(`${endpoint} returned HTTP ${response.status}: ${bodyText}`);
    }

    return response.json();
  }
}

function parseIso8601Duration(duration) {
  const match = duration.match(/^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/);
  if (!match) {
    throw new Error(`Invalid ISO 8601 duration format: ${duration}`);
  }
  const [, days, hours, minutes, seconds] = match;
  return (
    (Number(days) || 0) * 86400 +
    (Number(hours) || 0) * 3600 +
    (Number(minutes) || 0) * 60 +
    (Number(seconds) || 0)
  );
}

function isShort(duration) {
  return parseIso8601Duration(duration) < MIN_VIDEO_DURATION_SECONDS;
}

function hasRequiredFields(video) {
  const snippet = video.snippet || {};
  const contentDetails = video.contentDetails || {};
  return Boolean(contentDetails.duration) && Boolean(snippet.title) && Boolean(snippet.channelId);
}

function passesEngagementFilter(subscriberCount, viewCount) {
  if (subscriberCount >= SUBSCRIBER_THRESHOLD) {
    return viewCount > subscriberCount;
  }
  return viewCount >= MIN_VIEW_COUNT_LOW_SUBS;
}

// Груб, независим от езика "корен" на дума — отрязва кратък суфикс, за да
// поглъща граматически форми (мн. число, род, падеж) без пълен morphology
// анализатор. Работи еднакво за латиница и кирилица (само по дължина).
function stem(word) {
  const length = word.length;
  if (length <= 4) return word;
  if (length <= 7) return word.slice(0, -1);
  return word.slice(0, -2);
}

// Прилага се към всички кандидати (виж searchTopicVideos) — но ако би
// изчистила абсолютно всички резултати ПРИ ДОСТАТЪЧНО ГОЛЯМ пул, се прескача
// изцяло за тази заявка, защото заглавия често описват съдържанието с
// различни думи от търсената фраза (напр. канал "NOVA" (латиница) за търсене
// "Нова телевизия" (кирилица) никога няма да съвпадне буквално).
function matchesQuery(title, description, query) {
  const haystack = `${title} ${description || ""}`.toLowerCase();
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;

  const mandatoryWords = words.filter((word) => word.length >= 5);
  const requiredWords = mandatoryWords.length > 0 ? mandatoryWords : words;

  return requiredWords.every((word) => haystack.includes(stem(word)));
}

// Две групи: (1) видеа от големи канали (>= threshold абонати), сортирани по
// subscriberCount низходящо; (2) останалите, сортирани по ratio низходящо.
// Групa 1 излиза първа.
function groupSort(results) {
  const topChannelVideos = results.filter(
    (r) => r.subscriberCount >= LARGE_CHANNEL_SUBSCRIBER_THRESHOLD
  );
  const otherVideos = results.filter(
    (r) => r.subscriberCount < LARGE_CHANNEL_SUBSCRIBER_THRESHOLD
  );
  topChannelVideos.sort((a, b) => b.subscriberCount - a.subscriberCount);
  otherVideos.sort((a, b) => b.ratio - a.ratio);
  return [...topChannelVideos, ...otherVideos];
}

// Стандартна българска транслитерация кирилица -> латиница. Позволява
// заявка на кирилица ("милко атанасов") да съвпадне с канал, чието реално
// заглавие е изписано на латиница ("Milko Atanasov") — без нея, единственото
// "точно" съвпадение би бил различен, несвързан канал със същото име на
// кирилица (напр. открихме реален случай: обскурен канал с 4 абоната вместо
// истинския с 72 600, само защото писмеността на заявката и заглавието не
// съвпадат буквено, макар да звучат идентично).
const CYRILLIC_TO_LATIN = {
  а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ж: "zh", з: "z", и: "i",
  й: "y", к: "k", л: "l", м: "m", н: "n", о: "o", п: "p", р: "r", с: "s",
  т: "t", у: "u", ф: "f", х: "h", ц: "ts", ч: "ch", ш: "sh", щ: "sht",
  ъ: "a", ь: "y", ю: "yu", я: "ya",
};

function normalizeChannelText(text) {
  const transliterated = Array.from(text.toLowerCase())
    .map((ch) => CYRILLIC_TO_LATIN[ch] ?? ch)
    .join("");
  return transliterated.replace(/[^a-z0-9]/g, "");
}

// Търси дали заявката е име на съществуващ канал (напр. "Milko Kukov", "The
// Clashers"), не тематична ключова дума. Съвпадение се приема САМО при точно
// (нормализирано) съвпадение на цялото заглавие на канала — НЕ при частично/
// substring съвпадение. Substring съвпадение изглеждаше удобно за скъсени
// имена, но хващаше грешни случаи: заявка "fasting" (обща тема) съвпадаше с
// реален голям канал "Le Fasting" (456k абонати), защото "fasting" е
// substring на "lefasting" — превръщайки нормално тематично търсене в
// погрешен channel режим.
//
// Ако няколко канала съвпадат точно (рядко), избира този с най-много
// абонати — по-вероятно е "истинският"/търсеният канал, не празен дубликат.
async function findMatchingChannel(query, keyRotator) {
  const normalizedQuery = normalizeChannelText(query);
  if (!normalizedQuery) {
    return null;
  }

  const data = await apiGet(
    "search",
    { part: "snippet", q: query, type: "channel", maxResults: 5 },
    keyRotator
  );

  const matchingIds = (data.items || [])
    .filter((candidate) => normalizeChannelText(candidate.snippet.title) === normalizedQuery)
    .map((candidate) => candidate.snippet.channelId);

  if (matchingIds.length === 0) {
    return null;
  }

  const channels = [];
  for (const channelId of matchingIds) {
    const channelData = await apiGet(
      "channels",
      { part: "snippet,statistics", id: channelId },
      keyRotator
    );
    const channel = (channelData.items || [])[0];
    if (channel) {
      channels.push(channel);
    }
  }
  if (channels.length === 0) {
    return null;
  }

  return channels.reduce((best, channel) =>
    Number(channel.statistics.subscriberCount || 0) > Number(best.statistics.subscriberCount || 0)
      ? channel
      : best
  );
}

// Разпознава @handle (самостоятелно или в URL, напр.
// "https://www.youtube.com/@milkokukovbg") и channel ID URL-и.
const HANDLE_PATTERN = /(?:youtube\.com\/)?@([\w.-]+)/i;
const CHANNEL_ID_PATTERN = /youtube\.com\/channel\/(UC[\w-]{20,})/i;

// Опитва да открие канал от заявката по (в ред на приоритет): @handle
// (директен, еднозначен lookup — работи дори когато реалното заглавие на
// канала е на друга писменост от заявката, напр. канал "Милко Куков" на
// кирилица за заявка "@milkokukovbg"), директен channel ID, после точно
// съвпадение по заглавие (findMatchingChannel).
async function resolveChannel(query, keyRotator) {
  const handleMatch = query.match(HANDLE_PATTERN);
  if (handleMatch) {
    const channel = await getChannelByHandle(handleMatch[1], keyRotator);
    if (channel) {
      return channel;
    }
  }

  const channelIdMatch = query.match(CHANNEL_ID_PATTERN);
  if (channelIdMatch) {
    const data = await apiGet(
      "channels",
      { part: "snippet,statistics", id: channelIdMatch[1] },
      keyRotator
    );
    const channel = (data.items || [])[0];
    if (channel) {
      return channel;
    }
  }

  return findMatchingChannel(query, keyRotator);
}

async function getChannelByHandle(handle, keyRotator) {
  const handleWithAt = handle.startsWith("@") ? handle : `@${handle}`;
  const data = await apiGet(
    "channels",
    { part: "snippet,statistics", forHandle: handleWithAt },
    keyRotator
  );
  return (data.items || [])[0] || null;
}

// Канал-режим: заявката съвпада с име на канал — показваме НЕГОВИТЕ видеа от
// избрания период, сортирани по гледания (без Shorts), БЕЗ engagement
// филтъра (viewCount > subscriberCount), защото целта тук е топ съдържанието
// на конкретния канал, не откриване на "подценени" видеа.
// Забележка: не ползваме channels.contentDetails.relatedPlaylists.uploads +
// playlistItems.list — тази "uploads playlist" връща playlistNotFound
// (HTTP 404) за част от каналите (позната особеност на YouTube API), докато
// search.list с channelId работи надеждно за всички канали и директно
// поддържа publishedAfter/Before + order=viewCount на ниво API.
async function searchChannelVideos(channel, keyRotator, publishedAfter, publishedBefore) {
  const channelId = channel.id;
  const channelTitle = channel.snippet.title;
  const subscriberCount = Number(channel.statistics.subscriberCount || 0);

  const videoIds = [];
  let pageToken;
  for (let page = 0; page < CHANNEL_MAX_PAGES; page += 1) {
    const data = await apiGet(
      "search",
      {
        part: "id",
        channelId,
        type: "video",
        order: "viewCount",
        publishedAfter,
        publishedBefore,
        maxResults: 50,
        pageToken,
      },
      keyRotator
    );
    videoIds.push(
      ...(data.items || []).map((item) => item.id && item.id.videoId).filter(Boolean)
    );
    pageToken = data.nextPageToken;
    if (!pageToken) {
      break;
    }
  }

  const uniqueVideoIds = [...new Set(videoIds)];
  if (uniqueVideoIds.length === 0) {
    return [];
  }

  const videos = [];
  for (const idsChunk of chunk(uniqueVideoIds, BATCH_SIZE)) {
    const data = await apiGet(
      "videos",
      { part: "snippet,statistics,contentDetails", id: idsChunk.join(",") },
      keyRotator
    );
    videos.push(...(data.items || []));
  }

  const results = videos
    .filter(hasRequiredFields)
    .filter((video) => !isShort(video.contentDetails.duration))
    .map((video) => {
      const viewCount = Number(video.statistics.viewCount || 0);
      const divisor = subscriberCount > 0 ? subscriberCount : 1;
      return {
        videoId: video.id,
        title: video.snippet.title,
        channelId,
        channelTitle,
        subscriberCount,
        viewCount,
        publishedAt: video.snippet.publishedAt,
        ratio: viewCount / divisor,
        url: `https://www.youtube.com/watch?v=${video.id}`,
        thumbnail:
          (video.snippet.thumbnails &&
            (video.snippet.thumbnails.medium || video.snippet.thumbnails.default || {}).url) ||
          "",
      };
    });

  results.sort((a, b) => b.viewCount - a.viewCount);
  return results;
}

// dateRange="auto" пуска клиентската каскада: 3 месеца -> 6 месеца ->
// 1 година -> без ограничение, спирайки на първото ниво с поне 1 резултат
// (изискване: "Priority: Last 3 months, then 6 months, then 1 year, then
// all"). Конкретна стойност прави еднократно търсене само с този период.
async function searchQualifyingVideos(query, keyRotator, dateRange) {
  const matchingChannel = await resolveChannel(query, keyRotator);
  const tiers = dateRange === AUTO_DATE_RANGE ? AUTO_CASCADE_TIERS : [dateRange];

  for (let i = 0; i < tiers.length; i += 1) {
    const preset = DATE_RANGE_PRESETS[tiers[i]] || DATE_RANGE_PRESETS[DEFAULT_DATE_RANGE];
    const publishedAfter = preset.afterDays ? daysAgoIso(preset.afterDays) : null;
    const publishedBefore = preset.beforeDays ? daysAgoIso(preset.beforeDays) : null;

    const results = matchingChannel
      ? await searchChannelVideos(matchingChannel, keyRotator, publishedAfter, publishedBefore)
      : await searchTopicVideos(query, keyRotator, publishedAfter, publishedBefore);

    if (results.length > 0) {
      return { results, usedTier: tiers[i] };
    }
  }
  return { results: [], usedTier: tiers[tiers.length - 1] };
}

async function searchTopicVideos(query, keyRotator, publishedAfter, publishedBefore) {
  // Обхожда до SEARCH_MAX_PAGES страници (по SEARCH_MAX_RESULTS всяка) чрез
  // pageToken пагинация — за по-голям пул кандидати преди филтриране, вместо
  // само първите 50 (всяка страница е отделна search.list заявка = 100 units).
  const videoIds = [];
  let pageToken;
  for (let page = 0; page < SEARCH_MAX_PAGES; page += 1) {
    const searchData = await apiGet(
      "search",
      {
        part: "id",
        q: query,
        type: "video",
        order: "relevance",
        publishedAfter,
        publishedBefore,
        maxResults: SEARCH_MAX_RESULTS,
        pageToken,
      },
      keyRotator
    );
    videoIds.push(
      ...(searchData.items || []).map((item) => item.id && item.id.videoId).filter(Boolean)
    );
    pageToken = searchData.nextPageToken;
    if (!pageToken) {
      break;
    }
  }

  // YouTube понякога връща едно и също видео на повече от една страница
  // (напр. при разместване на relevance класирането между заявките) —
  // премахваме дубликатите, запазвайки реда.
  const uniqueVideoIds = [...new Set(videoIds)];

  if (uniqueVideoIds.length === 0) {
    return [];
  }

  const videos = [];
  for (const idsChunk of chunk(uniqueVideoIds, BATCH_SIZE)) {
    const data = await apiGet(
      "videos",
      { part: "snippet,statistics,contentDetails", id: idsChunk.join(",") },
      keyRotator
    );
    videos.push(...(data.items || []));
  }

  // Някои резултати (напр. livestream-и/premiere-и в нестандартно състояние,
  // или видеа, изтрити/направени private между search.list и videos.list) се
  // връщат без пълен contentDetails/snippet — пропускаме ги вместо да гръмнем.
  const completeVideos = videos.filter(hasRequiredFields);

  const longVideos = completeVideos.filter((video) => !isShort(video.contentDetails.duration));

  const channelIds = [...new Set(longVideos.map((video) => video.snippet.channelId))];
  const channels = [];
  for (const idsChunk of chunk(channelIds, BATCH_SIZE)) {
    const data = await apiGet("channels", { part: "statistics", id: idsChunk.join(",") }, keyRotator);
    channels.push(...(data.items || []));
  }
  const subscriberByChannel = new Map(
    channels.map((channel) => [channel.id, Number(channel.statistics.subscriberCount || 0)])
  );

  // Твърд филтър: само канали с >= MIN_CHANNEL_SUBSCRIBER_COUNT абонати
  // (изискване на клиента — търсим пробивни видеа на established канали,
  // не "hidden gems" от произволен размер канал).
  const bigChannelVideos = longVideos.filter(
    (video) => (subscriberByChannel.get(video.snippet.channelId) || 0) >= MIN_CHANNEL_SUBSCRIBER_COUNT
  );

  const engagementQualified = [];
  for (const video of bigChannelVideos) {
    const channelId = video.snippet.channelId;
    const subscriberCount = subscriberByChannel.get(channelId) || 0;
    const viewCount = Number(video.statistics.viewCount || 0);

    if (!passesEngagementFilter(subscriberCount, viewCount)) {
      continue;
    }

    const divisor = subscriberCount > 0 ? subscriberCount : 1;
    engagementQualified.push({
      video,
      result: {
        videoId: video.id,
        title: video.snippet.title,
        channelId,
        channelTitle: video.snippet.channelTitle,
        subscriberCount,
        viewCount,
        publishedAt: video.snippet.publishedAt,
        ratio: viewCount / divisor,
        url: `https://www.youtube.com/watch?v=${video.id}`,
        thumbnail:
          (video.snippet.thumbnails &&
            (video.snippet.thumbnails.medium || video.snippet.thumbnails.default || {}).url) ||
          "",
      },
    });
  }

  const relevantResults = engagementQualified
    .filter(({ video }) => matchesQuery(video.snippet.title, video.snippet.description, query))
    .map(({ result }) => result);

  let results;
  if (relevantResults.length > 0) {
    results = relevantResults;
  } else if (engagementQualified.length >= RELEVANCE_BYPASS_MIN_CANDIDATES) {
    // Релевантността би изчистила абсолютно всички кандидати, но пулът е
    // достатъчно голям, за да е правдоподобно, че причината е бранд/скрипт
    // разлика (напр. "Нова телевизия" срещу канал "NOVA" на латиница, ~40-200
    // кандидата, всички провалени) — не че всеки от толкова много резултати
    // е случайно ирелевантен.
    results = engagementQualified.map(({ result }) => result);
  } else {
    // Малък пул и никой не минава релевантността — много по-вероятно е
    // кандидатите просто да са ирелевантни (напр. едно случайно видео на
    // хинди за заявка "мини книжка за личните финанси"), не системна
    // бранд/скрипт разлика. Доверяваме се на филтъра, връщаме празно.
    results = [];
  }

  return groupSort(results);
}

// getQuotaStatus() никога не трябва да "проваля" отговор на съобщение — ако
// хвърли грешка (напр. проблем с chrome.storage), sendResponse не се
// извиква изобщо и Chrome показва "message channel closed before a
// response was received". Тази обвивка гарантира, че винаги връща нещо
// (или null), никога не отхвърля promise-а.
async function safeGetQuotaStatus() {
  try {
    return await getQuotaStatus();
  } catch (error) {
    console.error("getQuotaStatus() failed:", error);
    return null;
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message) {
    return false;
  }

  if (message.type === "GET_QUOTA_STATUS") {
    safeGetQuotaStatus().then(sendResponse);
    return true;
  }

  if (message.type !== "FILTERED_SEARCH") {
    return false;
  }

  (async () => {
    try {
      const apiKeys = await getApiKeys();
      if (apiKeys.length === 0) {
        sendResponse({ error: "NO_API_KEY", quota: await safeGetQuotaStatus() });
        return;
      }

      const keyRotator = await createKeyRotator(apiKeys);
      if (!keyRotator.hasAvailableKey()) {
        sendResponse({ error: "QUOTA_EXCEEDED", quota: await safeGetQuotaStatus() });
        return;
      }

      const dateRange = message.dateRange || AUTO_DATE_RANGE;
      const { results, usedTier } = await searchQualifyingVideos(
        message.query,
        keyRotator,
        dateRange
      );
      sendResponse({ results, usedTier, quota: await safeGetQuotaStatus() });
    } catch (error) {
      const messageText = error instanceof Error ? error.message : String(error);
      sendResponse({ error: messageText, quota: await safeGetQuotaStatus() });
    }
  })();

  return true; // асинхронен sendResponse
});
