const js = require("@eslint/js");

// The extension has no build step (plain scripts loaded via manifest.json),
// so this defines the browser/extension globals by hand instead of pulling
// in an extra globals package for a two-value list.
const browserExtensionGlobals = {
  chrome: "readonly",
  document: "readonly",
  window: "readonly",
  console: "readonly",
  fetch: "readonly",
  URL: "readonly",
  URLSearchParams: "readonly",
  Intl: "readonly",
  MutationObserver: "readonly",
  setInterval: "readonly",
  setTimeout: "readonly",
  clearInterval: "readonly",
  clearTimeout: "readonly",
  requestAnimationFrame: "readonly",
  location: "readonly",
};

module.exports = [
  js.configs.recommended,
  {
    files: ["extension/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: browserExtensionGlobals,
    },
    rules: {
      "no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" },
      ],
    },
  },
];
