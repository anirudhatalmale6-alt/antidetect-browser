// Distribte Auto Login Script
// This script runs when the popup opens and auto-fills the login form
// Also handles auto-logout if wrong account is detected

(function() {
  // Check if config exists and is enabled
  if (typeof AUTOLOGIN_CONFIG === 'undefined' || !AUTOLOGIN_CONFIG.enabled) {
    console.log('[AutoLogin] Disabled or config not found');
    return;
  }

  if (AUTOLOGIN_CONFIG.email === "YOUR_EMAIL_HERE" || AUTOLOGIN_CONFIG.password === "YOUR_PASSWORD_HERE") {
    console.log('[AutoLogin] Please configure your credentials in autologin-config.js');
    return;
  }

  console.log('[AutoLogin] Starting...');

  // Check if running in a tab (opened by wake-bg.js via window.open) - we'll close it after login
  const isInTab = window.location.href.includes('chrome-extension://') && (!!window.opener || new URLSearchParams(window.location.search).has('autoclose'));

  // Function to close tab after successful login
  function closeTabAfterLogin() {
    if (isInTab) {
      console.log('[AutoLogin] Login successful, closing tab in 2 seconds...');
      setTimeout(() => {
        window.close();
      }, 1000);
    }
  }

  // Function to simulate proper input for Vue.js
  function setInputValue(input, value) {
    // Set native value
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    nativeInputValueSetter.call(input, value);

    // Trigger events that Vue listens to
    input.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
    input.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
    input.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, cancelable: true }));
  }

  // Function to check if logged in as wrong account and logout
  function checkAndLogout() {
    // Look for "You are logged in as [email]" text
    const bodyText = document.body.innerText || document.body.textContent || '';
    const loggedInMatch = bodyText.match(/logged in as\s+([^\s]+@[^\s]+)/i);

    if (loggedInMatch) {
      const currentEmail = loggedInMatch[1].toLowerCase().trim();
      const configEmail = AUTOLOGIN_CONFIG.email.toLowerCase().trim();

      console.log('[AutoLogin] Currently logged in as:', currentEmail);

      if (currentEmail !== configEmail) {
        console.log('[AutoLogin] Wrong account! Need to logout first...');

        // Find logout button - try multiple selectors
        const buttons = document.querySelectorAll('button');
        for (const btn of buttons) {
          const text = btn.textContent.trim().toUpperCase();
          if (text === 'LOGOUT' || text === 'LOG OUT') {
            console.log('[AutoLogin] Found logout button, clicking...');

            // Use mousedown + mouseup + click for better compatibility
            btn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
            btn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
            btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

            return true; // Logged out
          }
        }
        console.log('[AutoLogin] Logout button not found');
      } else {
        console.log('[AutoLogin] Already logged in with correct account');
        closeTabAfterLogin(); // Close tab since already logged in correctly
        return 'correct_account';
      }
    }

    return false;
  }

  // Function to fill and submit the login form
  function tryAutoLogin() {
    // First check if logged in as wrong account
    const logoutResult = checkAndLogout();
    if (logoutResult === true) {
      console.log('[AutoLogin] Logout clicked, waiting for form...');
      // Continue checking for login form after logout
    }
    if (logoutResult === 'correct_account') {
      return true;
    }

    // Look for email input - try multiple selectors
    let emailInput = document.querySelector('input[type="email"]');
    if (!emailInput) emailInput = document.querySelector('input[placeholder*="Email" i]');
    if (!emailInput) emailInput = document.querySelector('input[placeholder*="mail" i]');
    if (!emailInput) {
      // Try to find first text input that might be email
      const textInputs = document.querySelectorAll('input[type="text"]');
      for (const inp of textInputs) {
        if (!inp.value || inp.placeholder.toLowerCase().includes('email')) {
          emailInput = inp;
          break;
        }
      }
    }

    const passwordInput = document.querySelector('input[type="password"]');

    // Look for login button
    const buttons = document.querySelectorAll('button');
    let loginBtn = null;
    for (const btn of buttons) {
      const text = btn.textContent.trim().toUpperCase();
      if (text === 'LOGIN' || text === 'LOG IN' || text === 'SIGN IN') {
        loginBtn = btn;
        break;
      }
    }

    // Check if we have a login form
    if (emailInput && passwordInput && loginBtn) {
      console.log('[AutoLogin] Login form found!');
      console.log('[AutoLogin] Email input:', emailInput);
      console.log('[AutoLogin] Password input:', passwordInput);
      console.log('[AutoLogin] Login button:', loginBtn.textContent);

      // Focus and fill email
      emailInput.focus();
      setInputValue(emailInput, AUTOLOGIN_CONFIG.email);

      // Small delay between fields
      setTimeout(() => {
        // Focus and fill password
        passwordInput.focus();
        setInputValue(passwordInput, AUTOLOGIN_CONFIG.password);

        // Wait a bit more then click login
        setTimeout(() => {
          console.log('[AutoLogin] Clicking login button...');
          loginBtn.focus();

          // Multiple click methods for Vue compatibility
          loginBtn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
          loginBtn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
          loginBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));

          // Also try direct click
          setTimeout(() => {
            loginBtn.click();

            // Watch for successful login, then close tab
            watchForLoginSuccess();
          }, 100);
        }, 500);
      }, 200);

      return true;
    }

    // Check if already logged in (look for logout button)
    for (const btn of buttons) {
      const text = btn.textContent.trim().toUpperCase();
      if (text === 'LOGOUT' || text === 'LOG OUT') {
        // If we get here without detecting email mismatch, we're probably logged in correctly
        console.log('[AutoLogin] Logout button found - checking account...');
        return false; // Let checkAndLogout handle it next iteration
      }
    }

    return false;
  }

  // Watch for successful login (logout button appears with correct email)
  function watchForLoginSuccess() {
    let checkCount = 0;
    const maxChecks = 20;

    const checkInterval = setInterval(() => {
      checkCount++;
      const bodyText = document.body.innerText || document.body.textContent || '';
      const loggedInMatch = bodyText.match(/logged in as\s+([^\s]+@[^\s]+)/i);

      if (loggedInMatch) {
        const currentEmail = loggedInMatch[1].toLowerCase().trim();
        const configEmail = AUTOLOGIN_CONFIG.email.toLowerCase().trim();

        if (currentEmail === configEmail) {
          console.log('[AutoLogin] Login successful! Logged in as:', currentEmail);
          clearInterval(checkInterval);
          closeTabAfterLogin();
        }
      }

      if (checkCount >= maxChecks) {
        clearInterval(checkInterval);
        console.log('[AutoLogin] Login check timed out');
      }
    }, 500);
  }

  // Wait longer for Vue to mount (2 seconds initial wait)
  console.log('[AutoLogin] Waiting for Vue to mount...');

  setTimeout(() => {
    console.log('[AutoLogin] Starting login attempts...');

    // Try immediately
    if (tryAutoLogin()) return;

    // If form not found, keep retrying
    let attempts = 0;
    const maxAttempts = 30; // More attempts

    const interval = setInterval(() => {
      attempts++;
      console.log('[AutoLogin] Attempt', attempts);

      if (tryAutoLogin() || attempts >= maxAttempts) {
        clearInterval(interval);
        if (attempts >= maxAttempts) {
          console.log('[AutoLogin] Form not found after', maxAttempts, 'attempts');
        }
      }
    }, 500); // Slower interval
  }, 2000); // Wait 2 seconds for Vue to fully mount
})();
