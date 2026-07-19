const keyList = document.getElementById("keyList");
const addKeyBtn = document.getElementById("addKey");
const status = document.getElementById("status");
const enabledOn = document.getElementById("enabledOn");
const enabledOff = document.getElementById("enabledOff");

function addKeyRow(value = "") {
  const row = document.createElement("div");
  row.className = "key-row";

  const input = document.createElement("input");
  input.type = "password";
  input.placeholder = "AIzaSy...";
  input.autocomplete = "off";
  input.value = value;

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.textContent = "×";
  removeBtn.title = "Remove key";
  removeBtn.addEventListener("click", () => {
    row.remove();
  });

  row.appendChild(input);
  row.appendChild(removeBtn);
  keyList.appendChild(row);
}

function getEnteredKeys() {
  return Array.from(keyList.querySelectorAll("input"))
    .map((input) => input.value.trim())
    .filter(Boolean);
}

addKeyBtn.addEventListener("click", () => addKeyRow());

// Key rotation работи с chrome.storage.local (не sync) — ключовете остават
// само на това устройство, не се синхронизират през Google акаунт.
// Миграция: ако вече има стар единичен ключ в chrome.storage.sync (от преди
// key rotation-а), пренасяме го автоматично в новия списък, за да не се
// губи вече конфигурираното.
async function loadKeys() {
  const { apiKeys } = await chrome.storage.local.get({ apiKeys: [] });
  if (apiKeys && apiKeys.length > 0) {
    apiKeys.forEach((key) => addKeyRow(key));
    return;
  }

  const { youtubeApiKey } = await chrome.storage.sync.get("youtubeApiKey");
  if (youtubeApiKey) {
    addKeyRow(youtubeApiKey);
    await chrome.storage.local.set({ apiKeys: [youtubeApiKey] });
    await chrome.storage.sync.remove("youtubeApiKey");
    return;
  }

  addKeyRow(); // at least one empty row to start with
}

loadKeys();

chrome.storage.sync.get({ extensionEnabled: true }).then(({ extensionEnabled }) => {
  (extensionEnabled ? enabledOn : enabledOff).checked = true;
});

function handleToggleChange() {
  chrome.storage.sync.set({ extensionEnabled: enabledOn.checked });
}

enabledOn.addEventListener("change", handleToggleChange);
enabledOff.addEventListener("change", handleToggleChange);

document.getElementById("save").addEventListener("click", async () => {
  const keys = getEnteredKeys();
  if (keys.length === 0) {
    status.textContent = "Enter at least one valid key.";
    status.className = "status status--err";
    return;
  }
  await chrome.storage.local.set({ apiKeys: keys });
  status.textContent = `Saved ${keys.length} key(s). Reload YouTube for changes to take effect.`;
  status.className = "status status--ok";
  loadQuota();
});

function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(value);
}

function loadQuota() {
  chrome.runtime.sendMessage({ type: "GET_QUOTA_STATUS" }, (quota) => {
    const quotaText = document.getElementById("quotaText");
    const quotaFill = document.getElementById("quotaFill");
    const perKeyQuota = document.getElementById("perKeyQuota");
    perKeyQuota.innerHTML = "";

    if (chrome.runtime.lastError || !quota || quota.keyCount === 0) {
      quotaText.textContent = "Quota: no data yet (add and save a key first).";
      quotaFill.style.width = "0%";
      return;
    }

    quotaText.textContent =
      `Quota today (${quota.keyCount} key${quota.keyCount === 1 ? "" : "s"}, extension-only): ` +
      `${formatNumber(quota.used)} / ${formatNumber(quota.limit)} units ` +
      `(~${formatNumber(quota.approxSearchesLeft)} searches left).`;

    const percentUsed = Math.min(100, (quota.used / quota.limit) * 100);
    quotaFill.style.width = `${percentUsed}%`;
    quotaFill.style.background = percentUsed >= 90 ? "#ff5252" : percentUsed >= 70 ? "#ffa726" : "#3ea6ff";

    quota.perKey.forEach((key, index) => {
      const line = document.createElement("div");
      line.className = "key-quota-line" + (key.exhausted ? " key-quota-line--exhausted" : "");
      line.textContent = key.exhausted
        ? `Key ${index + 1}: exhausted for today`
        : `Key ${index + 1}: ${formatNumber(key.used)} / ${formatNumber(key.limit)} units`;
      perKeyQuota.appendChild(line);
    });
  });
}

loadQuota();
