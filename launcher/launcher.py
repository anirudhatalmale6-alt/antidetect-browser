#!/usr/bin/env python3
"""
Anti-Detect Browser Profile Launcher
=====================================
Standalone launcher for managing and launching Chromium browser profiles with
fingerprint spoofing, proxy support, and isolated user data directories.

Connects to a dashboard API to fetch profile configurations, downloads/manages
a bundled Chromium installation, and launches profiles with full anti-detection.

Requirements: Python 3.8+ with tkinter (stdlib only, no pip dependencies).
Primary target: Windows. Also runs on Linux/macOS for development.
"""

import argparse
import json
import logging
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_NAME = "AntiDetect Launcher"
APP_VERSION = "1.0.0"
BASE_DIR = Path.home() / ".antidetect"
CONFIG_PATH = BASE_DIR / "config.json"
CHROMIUM_DIR = BASE_DIR / "chromium"
PROFILES_DIR = BASE_DIR / "profiles"
FP_EXTENSION_DIR = BASE_DIR / "fp-extension"
PROXY_AUTH_DIR = BASE_DIR / "proxy-auth"

CHROMIUM_SNAPSHOT_BASE = "https://storage.googleapis.com/chromium-browser-snapshots"
CHROMIUM_PLATFORM = "Win_x64"
LAST_CHANGE_URL = f"{CHROMIUM_SNAPSHOT_BASE}/{CHROMIUM_PLATFORM}/LAST_CHANGE"
CHROME_ZIP_URL = f"{CHROMIUM_SNAPSHOT_BASE}/{CHROMIUM_PLATFORM}/{{revision}}/chrome-win.zip"

DEFAULT_SERVER_URL = "https://nickets.xyz/ad"
UPDATE_CHECK_INTERVAL = 86400  # seconds (24h)

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger("launcher")

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def ensure_dirs() -> None:
    """Create the directory tree on first run."""
    for d in (BASE_DIR, CHROMIUM_DIR, PROFILES_DIR, FP_EXTENSION_DIR, PROXY_AUTH_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_config() -> Dict[str, Any]:
    """Load or initialise the persisted config."""
    defaults: Dict[str, Any] = {
        "server_url": DEFAULT_SERVER_URL,
        "chromium_revision": None,
        "auto_update": True,
        "last_update_check": 0,
    }
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                stored = json.load(fh)
            defaults.update(stored)
        except (json.JSONDecodeError, OSError):
            pass
    return defaults


def save_config(cfg: Dict[str, Any]) -> None:
    ensure_dirs()
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)


def api_get(url: str, timeout: int = 30) -> Any:
    """GET JSON from *url*, return parsed object."""
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": f"{APP_NAME}/{APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download_file(url: str, dest: Path, progress_cb=None) -> None:
    """Download *url* to *dest* with optional progress callback(downloaded, total)."""
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        with open(dest, "wb") as fh:
            while True:
                chunk = resp.read(1 << 16)  # 64 KiB
                if not chunk:
                    break
                fh.write(chunk)
                downloaded += len(chunk)
                if progress_cb:
                    progress_cb(downloaded, total)


def kill_process_tree(pid: int) -> None:
    """Kill a process and all its children (best-effort)."""
    if platform.system() == "Windows":
        try:
            subprocess.call(["taskkill", "/F", "/T", "/PID", str(pid)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            os.kill(pid, signal.SIGTERM)
    else:
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass


# ---------------------------------------------------------------------------
# ChromiumManager
# ---------------------------------------------------------------------------


class ChromiumManager:
    """Download, update, and locate the bundled Chromium build."""

    def __init__(self, config: Dict[str, Any], progress_cb=None):
        self.config = config
        self.progress_cb = progress_cb  # (message: str, pct: float|None)

    def _report(self, msg: str, pct: Optional[float] = None) -> None:
        log.info(msg)
        if self.progress_cb:
            self.progress_cb(msg, pct)

    def get_latest_revision(self) -> str:
        req = urllib.request.Request(LAST_CHANGE_URL,
                                     headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8").strip()

    def executable_path(self) -> Optional[Path]:
        """Return the path to the chrome executable if it exists."""
        chrome_dir = CHROMIUM_DIR / "chrome-win"
        if platform.system() == "Windows":
            exe = chrome_dir / "chrome.exe"
        else:
            exe = chrome_dir / "chrome"
        return exe if exe.exists() else None

    def needs_download(self) -> bool:
        return self.executable_path() is None

    def needs_update(self) -> bool:
        if not self.config.get("auto_update"):
            return False
        last_check = self.config.get("last_update_check", 0)
        if time.time() - last_check < UPDATE_CHECK_INTERVAL:
            return False
        try:
            latest = self.get_latest_revision()
            current = self.config.get("chromium_revision")
            return latest != current
        except Exception:
            return False

    def download_chromium(self, revision: Optional[str] = None) -> str:
        """Download and extract Chromium. Returns the revision installed."""
        if revision is None:
            self._report("Fetching latest Chromium revision...")
            revision = self.get_latest_revision()

        url = CHROME_ZIP_URL.format(revision=revision)
        zip_path = CHROMIUM_DIR / "chrome-win.zip"
        extract_dir = CHROMIUM_DIR / "chrome-win"

        # Clean previous
        if extract_dir.exists():
            self._report("Removing previous Chromium installation...")
            shutil.rmtree(extract_dir, ignore_errors=True)

        self._report(f"Downloading Chromium r{revision}...", 0.0)

        def _dl_progress(downloaded: int, total: int) -> None:
            if total > 0:
                pct = downloaded / total
                mb_done = downloaded / (1 << 20)
                mb_total = total / (1 << 20)
                self._report(f"Downloading: {mb_done:.1f} / {mb_total:.1f} MB", pct)

        download_file(url, zip_path, progress_cb=_dl_progress)

        self._report("Extracting Chromium...", None)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(CHROMIUM_DIR)
        zip_path.unlink(missing_ok=True)

        # On Linux/macOS, mark executable
        if platform.system() != "Windows":
            chrome = extract_dir / "chrome"
            if chrome.exists():
                chrome.chmod(0o755)

        self.config["chromium_revision"] = revision
        self.config["last_update_check"] = time.time()
        save_config(self.config)

        self._report(f"Chromium r{revision} ready.", 1.0)
        return revision

    def ensure_chromium(self) -> Path:
        """Ensure Chromium is available; download if necessary. Returns exe path."""
        if self.needs_download():
            self.download_chromium()
        elif self.needs_update():
            try:
                self.download_chromium()
            except Exception as exc:
                log.warning("Chromium update check failed: %s", exc)
        exe = self.executable_path()
        if exe is None:
            raise RuntimeError("Chromium executable not found after download.")
        return exe


# ---------------------------------------------------------------------------
# ExtensionManager
# ---------------------------------------------------------------------------


class ExtensionManager:
    """Create and manage the fingerprint injection extension and proxy auth extensions."""

    # -- Fingerprint extension -----------------------------------------------

    MANIFEST_JSON = json.dumps({
        "manifest_version": 3,
        "name": "FP Guard",
        "version": "1.0",
        "description": "Fingerprint configuration loader",
        "permissions": ["storage"],
        "content_scripts": [{
            "matches": ["<all_urls>"],
            "js": ["inject.js"],
            "run_at": "document_start",
            "all_frames": True,
            "world": "MAIN"
        }]
    }, indent=2)

    # inject.js -- runs in MAIN world at document_start. Reads config pushed
    # via Preferences and calls the spoofing payload.
    INJECT_JS = r"""
(function () {
  'use strict';
  /* The launcher writes fp_config into the extension's stored prefs before
     each launch. In MV3 MAIN-world content scripts we cannot use
     chrome.storage, so the config is embedded directly by the launcher
     into this file at build time as a JSON object. */
  var _fpConfig = null;
  try {
    _fpConfig = JSON.parse(document.currentScript
      ? document.currentScript.getAttribute('data-fpconfig')
      : null);
  } catch (_) {}
  if (!_fpConfig && typeof __ANTIDETECT_FP_CONFIG__ !== 'undefined') {
    _fpConfig = __ANTIDETECT_FP_CONFIG__;
  }
  if (_fpConfig) {
    window.__fpConfig = _fpConfig;
  }
})();
"""

    SPOOF_JS = r"""
(function () {
  'use strict';

  var cfg = window.__fpConfig;
  if (!cfg) return;

  /* ---- helpers ---- */
  function cloak(fn, name) {
    var orig = fn;
    Object.defineProperty(fn, 'toString', {
      value: function () { return 'function ' + (name || orig.name || '') + '() { [native code] }'; },
      writable: false, configurable: false
    });
    Object.defineProperty(fn, 'name', { value: name || orig.name, configurable: true });
    return fn;
  }

  function defineProp(obj, prop, value) {
    try {
      Object.defineProperty(obj, prop, {
        get: cloak(function () { return value; }, 'get ' + prop),
        configurable: true
      });
    } catch (_) {}
  }

  /* ---- Navigator ---- */
  if (cfg.navigator) {
    var nav = cfg.navigator;
    if (nav.hardwareConcurrency) defineProp(navigator, 'hardwareConcurrency', nav.hardwareConcurrency);
    if (nav.deviceMemory) defineProp(navigator, 'deviceMemory', nav.deviceMemory);
    if (nav.platform) defineProp(navigator, 'platform', nav.platform);
    if (nav.language) {
      defineProp(navigator, 'language', nav.language);
      defineProp(navigator, 'languages', [nav.language]);
    }
  }

  /* ---- Screen ---- */
  if (cfg.screen) {
    var scr = cfg.screen;
    if (scr.width) { defineProp(screen, 'width', scr.width); defineProp(screen, 'availWidth', scr.width); }
    if (scr.height) { defineProp(screen, 'height', scr.height); defineProp(screen, 'availHeight', scr.height); }
    if (scr.colorDepth) defineProp(screen, 'colorDepth', scr.colorDepth);
  }

  /* ---- Canvas ---- */
  if (cfg.canvas && cfg.canvas.noise) {
    var noise = cfg.canvas.noise;
    var origToBlob = HTMLCanvasElement.prototype.toBlob;
    var origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    var origGetImageData = CanvasRenderingContext2D.prototype.getImageData;

    function applyNoise(imageData) {
      var d = imageData.data;
      /* Deterministic seeded PRNG (mulberry32) keyed on the noise value */
      var seed = 0;
      for (var i = 0; i < noise.length; i++) seed = (seed + noise.charCodeAt(i) * 31) | 0;
      function rng() { seed |= 0; seed = seed + 0x6D2B79F5 | 0; var t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }
      for (var j = 0; j < d.length; j += 4) {
        d[j]   = Math.max(0, Math.min(255, d[j]   + Math.floor((rng() - 0.5) * 2)));
        d[j+1] = Math.max(0, Math.min(255, d[j+1] + Math.floor((rng() - 0.5) * 2)));
        d[j+2] = Math.max(0, Math.min(255, d[j+2] + Math.floor((rng() - 0.5) * 2)));
      }
      return imageData;
    }

    CanvasRenderingContext2D.prototype.getImageData = cloak(function () {
      var imgData = origGetImageData.apply(this, arguments);
      return applyNoise(imgData);
    }, 'getImageData');

    HTMLCanvasElement.prototype.toDataURL = cloak(function () {
      var ctx = this.getContext('2d');
      if (ctx) {
        var imgData = origGetImageData.call(ctx, 0, 0, this.width, this.height);
        ctx.putImageData(applyNoise(imgData), 0, 0);
      }
      return origToDataURL.apply(this, arguments);
    }, 'toDataURL');

    HTMLCanvasElement.prototype.toBlob = cloak(function () {
      var ctx = this.getContext('2d');
      if (ctx) {
        var imgData = origGetImageData.call(ctx, 0, 0, this.width, this.height);
        ctx.putImageData(applyNoise(imgData), 0, 0);
      }
      return origToBlob.apply(this, arguments);
    }, 'toBlob');
  }

  /* ---- WebGL ---- */
  if (cfg.webgl) {
    var wgl = cfg.webgl;
    var origGetParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = cloak(function (param) {
      var ext = this.getExtension('WEBGL_debug_renderer_info');
      if (ext) {
        if (param === ext.UNMASKED_VENDOR_WEBGL && wgl.vendor) return wgl.vendor;
        if (param === ext.UNMASKED_RENDERER_WEBGL && wgl.renderer) return wgl.renderer;
      }
      return origGetParam.call(this, param);
    }, 'getParameter');
    if (typeof WebGL2RenderingContext !== 'undefined') {
      var origGetParam2 = WebGL2RenderingContext.prototype.getParameter;
      WebGL2RenderingContext.prototype.getParameter = cloak(function (param) {
        var ext = this.getExtension('WEBGL_debug_renderer_info');
        if (ext) {
          if (param === ext.UNMASKED_VENDOR_WEBGL && wgl.vendor) return wgl.vendor;
          if (param === ext.UNMASKED_RENDERER_WEBGL && wgl.renderer) return wgl.renderer;
        }
        return origGetParam2.call(this, param);
      }, 'getParameter');
    }
  }

  /* ---- AudioContext ---- */
  if (cfg.audio && cfg.audio.noise) {
    var audioNoise = cfg.audio.noise;
    var OrigAudioCtx = window.AudioContext || window.webkitAudioContext;
    if (OrigAudioCtx) {
      var origCreateOscillator = OrigAudioCtx.prototype.createOscillator;
      OrigAudioCtx.prototype.createOscillator = cloak(function () {
        var osc = origCreateOscillator.apply(this, arguments);
        var origConnect = osc.connect.bind(osc);
        osc.connect = cloak(function (dest) {
          if (dest && dest.gain !== undefined) {
            dest.gain.value = dest.gain.value + audioNoise * 0.0001;
          }
          return origConnect.apply(this, arguments);
        }, 'connect');
        return osc;
      }, 'createOscillator');
    }
  }

  /* ---- Timezone ---- */
  if (cfg.timezone) {
    var tzCfg = cfg.timezone;
    if (typeof tzCfg.offset === 'number') {
      var origGetTZOffset = Date.prototype.getTimezoneOffset;
      Date.prototype.getTimezoneOffset = cloak(function () {
        return tzCfg.offset;
      }, 'getTimezoneOffset');
    }
    if (tzCfg.zone) {
      var OrigDateTimeFormat = Intl.DateTimeFormat;
      Intl.DateTimeFormat = cloak(function (locale, opts) {
        opts = opts || {};
        if (!opts.timeZone) opts.timeZone = tzCfg.zone;
        return new OrigDateTimeFormat(locale, opts);
      }, 'DateTimeFormat');
      Intl.DateTimeFormat.prototype = OrigDateTimeFormat.prototype;
      Intl.DateTimeFormat.supportedLocalesOf = OrigDateTimeFormat.supportedLocalesOf;
    }
  }

  /* ---- WebRTC ---- */
  if (cfg.webrtc && cfg.webrtc.blockLocal) {
    var origRTC = window.RTCPeerConnection;
    if (origRTC) {
      window.RTCPeerConnection = cloak(function () {
        var pc = new origRTC(...arguments);
        var origCreateOffer = pc.createOffer.bind(pc);
        pc.createOffer = cloak(function (opts) {
          opts = opts || {};
          opts.offerToReceiveAudio = false;
          opts.offerToReceiveVideo = false;
          return origCreateOffer(opts);
        }, 'createOffer');
        var origOnIce = null;
        Object.defineProperty(pc, 'onicecandidate', {
          get: function () { return origOnIce; },
          set: function (fn) {
            origOnIce = function (e) {
              if (e && e.candidate && e.candidate.candidate) {
                var c = e.candidate.candidate;
                /* Filter out local/private IPs */
                if (/((^|\s)(10|172\.(1[6-9]|2\d|3[01])|192\.168)\.\d+\.\d+)/.test(c)) return;
              }
              if (fn) fn(e);
            };
          }
        });
        return pc;
      }, 'RTCPeerConnection');
      window.RTCPeerConnection.prototype = origRTC.prototype;
    }
  }

  /* ---- Plugins ---- */
  if (cfg.plugins) {
    var pluginList = cfg.plugins;
    defineProp(navigator, 'plugins', Object.create(PluginArray.prototype, {
      length: { value: pluginList.length },
      item: { value: cloak(function (i) { return pluginList[i] || null; }, 'item') },
      namedItem: { value: cloak(function (n) { return pluginList.find(function (p) { return p.name === n; }) || null; }, 'namedItem') },
    }));
  }

})();
"""

    @classmethod
    def ensure_fp_extension(cls) -> Path:
        """Create the fingerprint injection extension if missing. Returns its path."""
        FP_EXTENSION_DIR.mkdir(parents=True, exist_ok=True)
        manifest_path = FP_EXTENSION_DIR / "manifest.json"
        inject_path = FP_EXTENSION_DIR / "inject.js"
        spoof_path = FP_EXTENSION_DIR / "spoof.js"

        # Always rewrite to ensure latest version
        manifest_path.write_text(cls.MANIFEST_JSON, encoding="utf-8")
        spoof_path.write_text(cls.SPOOF_JS, encoding="utf-8")
        # inject.js is a template; the config gets baked in per-launch
        inject_path.write_text(cls.INJECT_JS, encoding="utf-8")

        log.info("Fingerprint extension ready at %s", FP_EXTENSION_DIR)
        return FP_EXTENSION_DIR

    @classmethod
    def write_fp_config(cls, fp_config: Dict[str, Any]) -> Path:
        """
        Bake the fingerprint config into inject.js so the MAIN-world content
        script can read it without needing chrome.storage access.
        Returns the extension directory.
        """
        cls.ensure_fp_extension()
        config_json = json.dumps(fp_config, separators=(",", ":"))
        inject_code = f"var __ANTIDETECT_FP_CONFIG__ = {config_json};\n" + cls.INJECT_JS + cls.SPOOF_JS
        (FP_EXTENSION_DIR / "inject.js").write_text(inject_code, encoding="utf-8")
        return FP_EXTENSION_DIR

    # -- Proxy auth extension ------------------------------------------------

    PROXY_MANIFEST = json.dumps({
        "manifest_version": 2,
        "name": "Proxy Auth",
        "version": "1.0",
        "permissions": ["proxy", "webRequest", "webRequestBlocking", "<all_urls>"],
        "background": {
            "scripts": ["background.js"],
            "persistent": True
        }
    }, indent=2)

    @classmethod
    def create_proxy_auth_extension(cls, profile_id: str, host: str, port: str,
                                     username: str, password: str) -> Path:
        """Create a per-profile proxy auth extension. Returns extension dir."""
        ext_dir = PROXY_AUTH_DIR / profile_id
        ext_dir.mkdir(parents=True, exist_ok=True)

        (ext_dir / "manifest.json").write_text(cls.PROXY_MANIFEST, encoding="utf-8")

        background_js = f"""
var config = {{
    mode: "fixed_servers",
    rules: {{
        singleProxy: {{
            scheme: "http",
            host: {json.dumps(host)},
            port: parseInt({json.dumps(port)})
        }},
        bypassList: ["localhost"]
    }}
}};
chrome.proxy.settings.set({{value: config, scope: "regular"}}, function(){{}});

chrome.webRequest.onAuthRequired.addListener(
    function(details) {{
        return {{
            authCredentials: {{
                username: {json.dumps(username)},
                password: {json.dumps(password)}
            }}
        }};
    }},
    {{urls: ["<all_urls>"]}},
    ["blocking"]
);
"""
        (ext_dir / "background.js").write_text(background_js, encoding="utf-8")
        log.info("Proxy auth extension created for profile %s", profile_id)
        return ext_dir

    @classmethod
    def parse_proxy(cls, proxy_str: str) -> Tuple[str, str, Optional[str], Optional[str]]:
        """
        Parse proxy string in formats:
          ip:port
          ip:port:user:pass
        Returns (host, port, username_or_None, password_or_None).
        """
        if not proxy_str:
            return ("", "", None, None)
        parts = proxy_str.split(":")
        if len(parts) == 2:
            return (parts[0], parts[1], None, None)
        elif len(parts) == 4:
            return (parts[0], parts[1], parts[2], parts[3])
        elif len(parts) > 4:
            # ip:port:user:pass_with_colons
            return (parts[0], parts[1], parts[2], ":".join(parts[3:]))
        else:
            raise ValueError(f"Invalid proxy format: {proxy_str}")


# ---------------------------------------------------------------------------
# ProfileLauncher
# ---------------------------------------------------------------------------


class ProfileLauncher:
    """Fetch profile configs from API, set up extensions, launch Chromium."""

    def __init__(self, config: Dict[str, Any], chromium_mgr: ChromiumManager):
        self.config = config
        self.chromium_mgr = chromium_mgr
        self.running: Dict[str, subprocess.Popen] = {}  # profile_id -> Popen
        self._lock = threading.Lock()

    @property
    def server_url(self) -> str:
        return self.config.get("server_url", DEFAULT_SERVER_URL).rstrip("/")

    def fetch_profiles(self) -> List[Dict[str, Any]]:
        """Fetch the list of all profiles from the dashboard API."""
        url = f"{self.server_url}/api/profiles"
        return api_get(url)

    def fetch_profile(self, profile_id: str) -> Dict[str, Any]:
        """Fetch a single profile configuration."""
        url = f"{self.server_url}/api/profiles/{profile_id}"
        return api_get(url)

    def profile_data_dir(self, profile_id: str) -> Path:
        d = PROFILES_DIR / profile_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def is_running(self, profile_id: str) -> bool:
        with self._lock:
            proc = self.running.get(profile_id)
            if proc is None:
                return False
            if proc.poll() is not None:
                del self.running[profile_id]
                return False
            return True

    def launch(self, profile_id: str, profile_config: Optional[Dict[str, Any]] = None) -> int:
        """
        Launch a browser profile. Returns the PID.
        If *profile_config* is None, it will be fetched from the API.
        """
        if self.is_running(profile_id):
            raise RuntimeError(f"Profile {profile_id} is already running.")

        chrome_exe = self.chromium_mgr.ensure_chromium()

        if profile_config is None:
            profile_config = self.fetch_profile(profile_id)

        data_dir = self.profile_data_dir(profile_id)

        # -- Fingerprint extension --
        fp_config = profile_config.get("fingerprint", {})
        fp_ext_dir = ExtensionManager.write_fp_config(fp_config)

        # -- Build Chrome flags --
        extensions = [str(fp_ext_dir)]
        flags = [
            str(chrome_exe),
            f"--user-data-dir={data_dir}",
            "--disable-background-networking",
            "--disable-client-side-phishing-detection",
            "--disable-default-apps",
            "--disable-hang-monitor",
            "--disable-popup-blocking",
            "--disable-prompt-on-repost",
            "--disable-sync",
            "--disable-translate",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
        ]

        # Window size from fingerprint screen config
        screen_cfg = fp_config.get("screen", {})
        width = screen_cfg.get("width", 1920)
        height = screen_cfg.get("height", 1080)
        flags.append(f"--window-size={width},{height}")

        # -- Proxy --
        proxy_str = profile_config.get("proxy", "")
        if proxy_str:
            host, port, user, passwd = ExtensionManager.parse_proxy(proxy_str)
            if user and passwd:
                proxy_ext = ExtensionManager.create_proxy_auth_extension(
                    profile_id, host, port, user, passwd)
                extensions.append(str(proxy_ext))
            if host and port:
                flags.append(f"--proxy-server={host}:{port}")

        # Extensions
        ext_list = ",".join(extensions)
        flags.append(f"--load-extension={ext_list}")
        flags.append(f"--disable-extensions-except={ext_list}")

        log.info("Launching profile %s: %s", profile_id, " ".join(flags[:3]) + " ...")

        # -- Spawn --
        kwargs: Dict[str, Any] = {}
        if platform.system() == "Windows":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["preexec_fn"] = os.setsid

        proc = subprocess.Popen(flags, **kwargs)

        with self._lock:
            self.running[profile_id] = proc

        log.info("Profile %s launched (PID %d).", profile_id, proc.pid)
        return proc.pid

    def stop(self, profile_id: str) -> None:
        """Stop a running profile's browser process."""
        with self._lock:
            proc = self.running.pop(profile_id, None)
        if proc is None:
            return
        log.info("Stopping profile %s (PID %d)...", profile_id, proc.pid)
        kill_process_tree(proc.pid)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    def stop_all(self) -> None:
        with self._lock:
            ids = list(self.running.keys())
        for pid in ids:
            self.stop(pid)

    def cleanup(self) -> None:
        """Called on launcher exit."""
        self.stop_all()


# ---------------------------------------------------------------------------
# LauncherGUI
# ---------------------------------------------------------------------------


class LauncherGUI:
    """Tkinter-based dark-themed GUI for the launcher."""

    # Color palette
    BG = "#1a1a2e"
    BG_SECONDARY = "#16213e"
    BG_INPUT = "#0f3460"
    FG = "#e0e0e0"
    FG_DIM = "#888888"
    ACCENT = "#7c3aed"
    ACCENT_HOVER = "#6d28d9"
    SUCCESS = "#22c55e"
    DANGER = "#ef4444"
    WARNING = "#f59e0b"
    BORDER = "#2d2d5e"

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.profiles: List[Dict[str, Any]] = []
        self.profile_rows: Dict[str, Dict] = {}

        self.chromium_mgr = ChromiumManager(config, progress_cb=self._on_chromium_progress)
        self.launcher = ProfileLauncher(config, self.chromium_mgr)

        self._build_ui()
        self._poll_process_status()

    # -- UI Construction -----------------------------------------------------

    def _build_ui(self) -> None:
        import tkinter as tk
        from tkinter import ttk, messagebox

        self.tk = tk
        self.messagebox = messagebox

        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("960x620")
        self.root.minsize(800, 500)
        self.root.configure(bg=self.BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # -- Style --
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=self.BG, foreground=self.FG, fieldbackground=self.BG_INPUT)
        style.configure("TFrame", background=self.BG)
        style.configure("TLabel", background=self.BG, foreground=self.FG, font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 14, "bold"), foreground=self.ACCENT)
        style.configure("Status.TLabel", font=("Segoe UI", 9), foreground=self.FG_DIM)
        style.configure("Header.TLabel", font=("Segoe UI", 10, "bold"), foreground=self.FG)
        style.configure("TButton", background=self.ACCENT, foreground="#ffffff",
                         font=("Segoe UI", 10), borderwidth=0, padding=(12, 6))
        style.map("TButton",
                  background=[("active", self.ACCENT_HOVER), ("disabled", self.BG_SECONDARY)])
        style.configure("Danger.TButton", background=self.DANGER)
        style.map("Danger.TButton", background=[("active", "#dc2626")])
        style.configure("TEntry", fieldbackground=self.BG_INPUT, foreground=self.FG,
                         insertcolor=self.FG, borderwidth=1, padding=6)
        style.configure("Treeview", background=self.BG_SECONDARY, foreground=self.FG,
                         fieldbackground=self.BG_SECONDARY, borderwidth=0, rowheight=36,
                         font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background=self.BG, foreground=self.ACCENT,
                         font=("Segoe UI", 10, "bold"), borderwidth=0)
        style.map("Treeview", background=[("selected", self.ACCENT)])
        style.configure("TProgressbar", troughcolor=self.BG_SECONDARY,
                         background=self.ACCENT, borderwidth=0, thickness=8)

        # -- Top bar --
        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=16, pady=(12, 4))

        ttk.Label(top_frame, text="Server URL:", style="Header.TLabel").pack(side=tk.LEFT)
        self.server_var = tk.StringVar(value=self.config.get("server_url", DEFAULT_SERVER_URL))
        self.server_entry = ttk.Entry(top_frame, textvariable=self.server_var, width=45)
        self.server_entry.pack(side=tk.LEFT, padx=(8, 8))

        self.connect_btn = ttk.Button(top_frame, text="Connect", command=self._on_connect)
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(top_frame, text=APP_NAME, style="Title.TLabel").pack(side=tk.RIGHT)

        # -- Separator --
        sep = tk.Frame(self.root, height=1, bg=self.BORDER)
        sep.pack(fill=tk.X, padx=16, pady=4)

        # -- Profile list --
        list_frame = ttk.Frame(self.root)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(4, 4))

        cols = ("name", "proxy", "fingerprint", "status")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("name", text="Profile Name")
        self.tree.heading("proxy", text="Proxy")
        self.tree.heading("fingerprint", text="Fingerprint")
        self.tree.heading("status", text="Status")
        self.tree.column("name", width=200, minwidth=120)
        self.tree.column("proxy", width=200, minwidth=100)
        self.tree.column("fingerprint", width=250, minwidth=120)
        self.tree.column("status", width=100, minwidth=80)

        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # -- Action bar --
        action_frame = ttk.Frame(self.root)
        action_frame.pack(fill=tk.X, padx=16, pady=(0, 4))

        self.launch_btn = ttk.Button(action_frame, text="Launch Selected", command=self._on_launch)
        self.launch_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.stop_btn = ttk.Button(action_frame, text="Stop Selected",
                                    command=self._on_stop, style="Danger.TButton")
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.refresh_btn = ttk.Button(action_frame, text="Refresh", command=self._on_connect)
        self.refresh_btn.pack(side=tk.LEFT)

        self.stop_all_btn = ttk.Button(action_frame, text="Stop All",
                                        command=self._on_stop_all, style="Danger.TButton")
        self.stop_all_btn.pack(side=tk.RIGHT)

        # -- Progress bar --
        self.progress = ttk.Progressbar(self.root, mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X, padx=16, pady=(0, 2))
        self.progress.pack_forget()  # hidden initially

        # -- Status bar --
        status_frame = tk.Frame(self.root, bg=self.BG_SECONDARY, height=28)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        status_frame.pack_propagate(False)

        self.status_var = tk.StringVar(value="Ready. Enter server URL and click Connect.")
        self.status_label = tk.Label(status_frame, textvariable=self.status_var,
                                      bg=self.BG_SECONDARY, fg=self.FG_DIM,
                                      font=("Segoe UI", 9), anchor="w", padx=16)
        self.status_label.pack(fill=tk.X, expand=True)

    def run(self) -> None:
        self.root.mainloop()

    # -- Callbacks -----------------------------------------------------------

    def _set_status(self, msg: str) -> None:
        self.status_var.set(msg)
        log.info("UI: %s", msg)

    def _show_progress(self, pct: Optional[float] = None) -> None:
        """Show the progress bar. If pct is None, go indeterminate."""
        self.progress.pack(fill=self.tk.X, padx=16, pady=(0, 2), before=self.root.children.get(
            list(self.root.children.keys())[-1]))
        if pct is not None:
            self.progress.configure(mode="determinate")
            self.progress["value"] = pct * 100
        else:
            self.progress.configure(mode="indeterminate")
            self.progress.start(15)

    def _hide_progress(self) -> None:
        self.progress.stop()
        self.progress.pack_forget()

    def _on_chromium_progress(self, msg: str, pct: Optional[float]) -> None:
        """Called from ChromiumManager (may be in a thread)."""
        self.root.after(0, lambda: self._set_status(msg))
        if pct is not None:
            self.root.after(0, lambda: self._show_progress(pct))

    def _on_connect(self) -> None:
        server = self.server_var.get().strip()
        if not server:
            self.messagebox.showwarning("Input required", "Please enter a server URL.")
            return
        self.config["server_url"] = server
        save_config(self.config)
        self._set_status(f"Connecting to {server}...")
        self.connect_btn.configure(state="disabled")

        def _worker():
            try:
                profiles = self.launcher.fetch_profiles()
                self.root.after(0, lambda: self._populate_profiles(profiles))
                self.root.after(0, lambda: self._set_status(
                    f"Connected. {len(profiles)} profile(s) loaded."))
            except Exception as exc:
                self.root.after(0, lambda: self._set_status(f"Connection failed: {exc}"))
                self.root.after(0, lambda: self.messagebox.showerror(
                    "Connection Error", str(exc)))
            finally:
                self.root.after(0, lambda: self.connect_btn.configure(state="normal"))

        threading.Thread(target=_worker, daemon=True).start()

    def _populate_profiles(self, profiles: List[Dict[str, Any]]) -> None:
        self.profiles = profiles
        for item in self.tree.get_children():
            self.tree.delete(item)
        for p in profiles:
            pid = p.get("id", p.get("profile_id", ""))
            name = p.get("name", pid)
            proxy = p.get("proxy", "none")
            fp = p.get("fingerprint", {})
            fp_os = fp.get("navigator", {}).get("platform", "?")
            fp_browser = fp.get("browser", "Chromium")
            fp_label = f"{fp_os} / {fp_browser}"
            status = "Running" if self.launcher.is_running(str(pid)) else "Stopped"
            self.tree.insert("", self.tk.END, iid=str(pid),
                             values=(name, proxy if proxy else "direct", fp_label, status))

    def _selected_profile_id(self) -> Optional[str]:
        sel = self.tree.selection()
        if not sel:
            self.messagebox.showinfo("Select profile", "Please select a profile first.")
            return None
        return sel[0]

    def _on_launch(self) -> None:
        pid = self._selected_profile_id()
        if pid is None:
            return
        if self.launcher.is_running(pid):
            self.messagebox.showinfo("Already running", f"Profile {pid} is already running.")
            return

        self._set_status(f"Launching profile {pid}...")
        self._show_progress(None)

        # Find the profile config from our cached list
        pcfg = None
        for p in self.profiles:
            if str(p.get("id", p.get("profile_id", ""))) == pid:
                pcfg = p
                break

        def _worker():
            try:
                self.launcher.launch(pid, pcfg)
                self.root.after(0, lambda: self._set_status(f"Profile {pid} launched."))
                self.root.after(0, lambda: self._update_row_status(pid, "Running"))
            except Exception as exc:
                self.root.after(0, lambda: self._set_status(f"Launch failed: {exc}"))
                self.root.after(0, lambda: self.messagebox.showerror("Launch Error", str(exc)))
            finally:
                self.root.after(0, self._hide_progress)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_stop(self) -> None:
        pid = self._selected_profile_id()
        if pid is None:
            return
        if not self.launcher.is_running(pid):
            self.messagebox.showinfo("Not running", f"Profile {pid} is not running.")
            return
        self.launcher.stop(pid)
        self._update_row_status(pid, "Stopped")
        self._set_status(f"Profile {pid} stopped.")

    def _on_stop_all(self) -> None:
        self.launcher.stop_all()
        for item in self.tree.get_children():
            self._update_row_status(item, "Stopped")
        self._set_status("All profiles stopped.")

    def _update_row_status(self, profile_id: str, status: str) -> None:
        try:
            vals = list(self.tree.item(profile_id, "values"))
            if len(vals) >= 4:
                vals[3] = status
                self.tree.item(profile_id, values=vals)
        except Exception:
            pass

    def _poll_process_status(self) -> None:
        """Periodic check: update tree rows to reflect actual process state."""
        for item in self.tree.get_children():
            running = self.launcher.is_running(item)
            self._update_row_status(item, "Running" if running else "Stopped")
        self.root.after(3000, self._poll_process_status)

    def _on_close(self) -> None:
        running_count = sum(1 for p in self.profiles
                            if self.launcher.is_running(
                                str(p.get("id", p.get("profile_id", "")))))
        if running_count > 0:
            choice = self.messagebox.askyesnocancel(
                "Exit",
                f"{running_count} profile(s) still running.\n\n"
                "Yes = Stop all and exit\n"
                "No = Leave them running and exit\n"
                "Cancel = Stay")
            if choice is None:
                return
            if choice:
                self.launcher.stop_all()
        self.root.destroy()


# ---------------------------------------------------------------------------
# CLI Mode
# ---------------------------------------------------------------------------


def cli_launch(server_url: str, profile_id: str) -> None:
    """Launch a single profile from the command line (no GUI)."""
    config = load_config()
    config["server_url"] = server_url
    save_config(config)

    def progress(msg, pct):
        if pct is not None:
            print(f"\r  {msg} [{pct*100:.0f}%]", end="", flush=True)
        else:
            print(f"  {msg}")

    chromium_mgr = ChromiumManager(config, progress_cb=progress)
    launcher = ProfileLauncher(config, chromium_mgr)

    print(f"[*] Fetching profile {profile_id} from {server_url}...")
    profile = launcher.fetch_profile(profile_id)
    print(f"[*] Profile: {profile.get('name', profile_id)}")

    print("[*] Ensuring Chromium is available...")
    chromium_mgr.ensure_chromium()

    print(f"[*] Launching profile {profile_id}...")
    pid = launcher.launch(profile_id, profile)
    print(f"[+] Browser launched (PID {pid}). Press Ctrl+C to stop.")

    try:
        while launcher.is_running(profile_id):
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Stopping...")
        launcher.stop(profile_id)
    print("[*] Done.")


def cli_list(server_url: str) -> None:
    """List profiles from the command line."""
    config = load_config()
    config["server_url"] = server_url
    save_config(config)

    launcher = ProfileLauncher(config, ChromiumManager(config))
    print(f"[*] Fetching profiles from {server_url}...")
    profiles = launcher.fetch_profiles()
    print(f"\n{'ID':<20} {'Name':<25} {'Proxy':<25} {'Fingerprint':<20}")
    print("-" * 90)
    for p in profiles:
        pid = p.get("id", p.get("profile_id", "?"))
        name = p.get("name", "unnamed")
        proxy = p.get("proxy", "direct") or "direct"
        fp = p.get("fingerprint", {})
        fp_os = fp.get("navigator", {}).get("platform", "?")
        print(f"{pid:<20} {name:<25} {proxy:<25} {fp_os:<20}")
    print(f"\nTotal: {len(profiles)} profile(s)")


def cli_download_chromium() -> None:
    """Download/update Chromium from the command line."""
    config = load_config()

    def progress(msg, pct):
        if pct is not None:
            bar_len = 40
            filled = int(bar_len * pct)
            bar = "#" * filled + "-" * (bar_len - filled)
            print(f"\r  [{bar}] {pct*100:.0f}%  {msg}", end="", flush=True)
        else:
            print(f"  {msg}")

    mgr = ChromiumManager(config, progress_cb=progress)
    print("[*] Downloading latest Chromium...")
    rev = mgr.download_chromium()
    print(f"\n[+] Chromium r{rev} installed at {CHROMIUM_DIR}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    ensure_dirs()

    parser = argparse.ArgumentParser(
        prog="launcher",
        description=f"{APP_NAME} v{APP_VERSION} - Anti-detect browser profile manager",
    )
    parser.add_argument("--server", "-s", default=None,
                        help=f"Dashboard API server URL (default: last used or {DEFAULT_SERVER_URL})")
    parser.add_argument("--profile", "-p", default=None,
                        help="Profile ID to launch (CLI mode)")
    parser.add_argument("--launch", "-l", action="store_true",
                        help="Launch the specified profile immediately (CLI mode)")
    parser.add_argument("--list", action="store_true",
                        help="List available profiles from server and exit")
    parser.add_argument("--download-chromium", action="store_true",
                        help="Download/update Chromium and exit")
    parser.add_argument("--no-gui", action="store_true",
                        help="Run without GUI (requires --profile --launch or --list)")

    args = parser.parse_args()
    config = load_config()

    server_url = args.server or config.get("server_url", DEFAULT_SERVER_URL)

    # CLI: download chromium
    if args.download_chromium:
        cli_download_chromium()
        return

    # CLI: list profiles
    if args.list:
        cli_list(server_url)
        return

    # CLI: launch specific profile
    if args.launch:
        if not args.profile:
            parser.error("--launch requires --profile PROFILE_ID")
        cli_launch(server_url, args.profile)
        return

    if args.no_gui:
        parser.error("--no-gui requires one of: --launch --profile ID, --list, --download-chromium")

    # GUI mode
    try:
        gui = LauncherGUI(config)
        gui.run()
    except ImportError:
        print("ERROR: tkinter is not available. Install python3-tk or use --no-gui mode.")
        sys.exit(1)


if __name__ == "__main__":
    main()
