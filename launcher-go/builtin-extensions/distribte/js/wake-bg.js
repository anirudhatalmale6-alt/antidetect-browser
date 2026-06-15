(async () => {
  if (window.location.href.startsWith('chrome-extension://')) return;
  try {
    const result = await chrome.storage.session.get('_distPopup');
    if (result._distPopup === true) return;
    await chrome.storage.session.set({ _distPopup: true });
    await new Promise(r => setTimeout(r, 1500));
    chrome.runtime.sendMessage({ action: 'openDistribtePopup' });
  } catch(e) {
    try {
      const r = await chrome.storage.local.get('_distPopupTs');
      const now = Date.now();
      if (r._distPopupTs && (now - r._distPopupTs) < 30000) return;
      await chrome.storage.local.set({ _distPopupTs: now });
      await new Promise(r => setTimeout(r, 1500));
      chrome.runtime.sendMessage({ action: 'openDistribtePopup' });
    } catch(e2) {}
  }
})();
