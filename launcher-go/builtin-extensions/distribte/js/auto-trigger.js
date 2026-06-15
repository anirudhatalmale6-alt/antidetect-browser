// Content script for whoerip.com - auto opens Distribte popup
// This runs when the profile opens and whoerip.com loads

(function() {
  // Only run once per session
  const storageKey = 'distribte_auto_triggered_' + Date.now().toString().slice(0, -4); // Resets every ~10 seconds
  if (sessionStorage.getItem('distribte_auto_triggered')) return;
  sessionStorage.setItem('distribte_auto_triggered', 'true');

  console.log('[Distribte AutoTrigger] Profile opened, will open popup in 2 seconds...');

  // Wait a bit for page to load, then simulate clicking the extension
  setTimeout(() => {
    // Create a small notification to let user know
    const notice = document.createElement('div');
    notice.style.cssText = 'position:fixed;top:10px;right:10px;background:#f7931e;color:white;padding:10px 15px;border-radius:5px;z-index:99999;font-family:Arial;font-size:14px;box-shadow:0 2px 10px rgba(0,0,0,0.2);';
    notice.textContent = 'Opening Distribte... Press Alt+Shift+X';
    document.body.appendChild(notice);

    // Auto-remove after 5 seconds
    setTimeout(() => notice.remove(), 5000);

    // Try to open popup via keyboard shortcut simulation (won't work, but worth trying)
    // The real solution is user presses Alt+Shift+X

    // Alternative: Open popup.html in a new tab
    chrome.runtime.sendMessage({ action: 'openPopupTab' });

  }, 2000);
})();
