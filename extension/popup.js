const input = document.getElementById("apiKey");
const status = document.getElementById("status");
const enabledOn = document.getElementById("enabledOn");
const enabledOff = document.getElementById("enabledOff");

chrome.storage.sync.get("youtubeApiKey").then(({ youtubeApiKey }) => {
  if (youtubeApiKey) {
    input.value = youtubeApiKey;
  }
});

chrome.storage.sync.get({ extensionEnabled: true }).then(({ extensionEnabled }) => {
  (extensionEnabled ? enabledOn : enabledOff).checked = true;
});

function handleToggleChange() {
  chrome.storage.sync.set({ extensionEnabled: enabledOn.checked });
}

enabledOn.addEventListener("change", handleToggleChange);
enabledOff.addEventListener("change", handleToggleChange);

document.getElementById("save").addEventListener("click", async () => {
  const value = input.value.trim();
  if (!value) {
    status.textContent = "Въведете валиден ключ.";
    status.className = "status status--err";
    return;
  }
  await chrome.storage.sync.set({ youtubeApiKey: value });
  status.textContent = "Запазено. Презаредете YouTube, за да влезе в сила.";
  status.className = "status status--ok";
});

function formatNumber(value) {
  return new Intl.NumberFormat("bg-BG").format(value);
}

chrome.runtime.sendMessage({ type: "GET_QUOTA_STATUS" }, (quota) => {
  const quotaText = document.getElementById("quotaText");
  const quotaFill = document.getElementById("quotaFill");
  if (chrome.runtime.lastError || !quota) {
    quotaText.textContent = "Квота: няма данни (все още няма търсения днес).";
    return;
  }
  quotaText.textContent =
    `Квота днес (само от разширението): ${formatNumber(quota.used)} / ${formatNumber(quota.limit)} units ` +
    `(~${formatNumber(quota.approxSearchesLeft)} търсения остават). ` +
    "Реалната квота може да е по-ниска при споделен ключ (напр. с CLI).";
  const percentUsed = Math.min(100, (quota.used / quota.limit) * 100);
  quotaFill.style.width = `${percentUsed}%`;
  if (percentUsed >= 90) {
    quotaFill.style.background = "#ff5252";
  } else if (percentUsed >= 70) {
    quotaFill.style.background = "#ffa726";
  }
});
