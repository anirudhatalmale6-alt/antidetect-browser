// Distribte Auto-Login v8.3 - Content Script
// Runs on multiloginapp.com pages. Opens popup.html in a new tab once per session.
(async () => {
  const POPUP_URL = chrome.runtime.getURL('popup.html');

  // Don't run on extension pages
  if (window.location.href.startsWith('chrome-extension://')) return;

  try {
    // Use session storage flag - resets when profile closes
    const result = await chrome.storage.session.get('_distPopup');
    if (result._distPopup === true) return; // Already opened

    // Set flag IMMEDIATELY to block any other instances
    await chrome.storage.session.set({ _distPopup: true });

    // Wait for page to settle
    await new Promise(r => setTimeout(r, 1000));

    // Open popup in a new tab
    window.open(POPUP_URL + '?autoclose=1', '_blank');
  } catch(e) {
    // If session storage fails, try local storage with timestamp
    try {
      const r = await chrome.storage.local.get('_distPopupTs');
      const now = Date.now();
      if (r._distPopupTs && (now - r._distPopupTs) < 30000) return;
      await chrome.storage.local.set({ _distPopupTs: now });
      await new Promise(r => setTimeout(r, 1000));
      window.open(POPUP_URL + '?autoclose=1', '_blank');
    } catch(e2) {}
  }
})();
