/**
 * inject.js - Content script (runs in ISOLATED world at document_start)
 *
 * Reads fingerprint config from chrome.storage.local and injects spoof.js
 * into the MAIN world so it can override page-visible browser APIs before
 * any page script executes.
 */

(function () {
  'use strict';

  const DEFAULT_CONFIG = {
    canvas_seed: 12345,
    webgl_vendor: 'Google Inc. (Intel)',
    webgl_renderer:
      'ANGLE (Intel, Intel(R) UHD Graphics 620, OpenGL 4.5)',
    audio_seed: 67890,
    hardware_concurrency: 8,
    device_memory: 16,
    platform: 'Win32',
    language: 'en-US',
    languages: ['en-US', 'en'],
    screen_width: 1920,
    screen_height: 1080,
    timezone_offset: -300,
    timezone_name: 'America/New_York',
  };

  function injectSpoof(config) {
    const script = document.createElement('script');
    script.src = chrome.runtime.getURL('spoof.js');
    script.dataset.fpConfig = JSON.stringify(config);
    // Insert as the very first child of <html> (or documentElement)
    // so it runs before any other script on the page.
    (document.documentElement || document.head || document.body).prepend(script);
    // Clean up after execution to reduce footprint
    script.addEventListener('load', () => script.remove());
  }

  // Attempt to read stored config; fall back to defaults.
  try {
    chrome.storage.local.get('fp_config', (result) => {
      const config = Object.assign({}, DEFAULT_CONFIG, result.fp_config || {});
      injectSpoof(config);
    });
  } catch (_) {
    // storage API unavailable (e.g. in certain restricted contexts) - use defaults
    injectSpoof(DEFAULT_CONFIG);
  }
})();
