// Auto-open Distribte popup when nickets.xyz tab loads
chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
  if (msg && msg.action === 'openDistribtePopup') {
    chrome.tabs.create({
      url: chrome.runtime.getURL('popup.html?autoclose=1'),
      active: false
    });
    sendResponse({ok: true});
  }
});

// Import original Distribte background script
importScripts('background-original.js');
