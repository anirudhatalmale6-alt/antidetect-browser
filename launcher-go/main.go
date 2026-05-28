package main

import (
	"archive/zip"
	_ "embed"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"time"
)

// ---------------------------------------------------------------------------
// Embedded dashboard
// ---------------------------------------------------------------------------

//go:embed dashboard.html
var dashboardHTML string

// ---------------------------------------------------------------------------
// Data types
// ---------------------------------------------------------------------------

type Profile struct {
	ID           string          `json:"id"`
	Name         string          `json:"name"`
	FolderID     string          `json:"folder_id"`
	FolderName   string          `json:"folder_name"`
	Proxy        string          `json:"proxy"`
	WindowWidth  int             `json:"window_width"`
	WindowHeight int             `json:"window_height"`
	UserAgent    string          `json:"user_agent"`
	Notes        string          `json:"notes"`
	Fingerprint  json.RawMessage `json:"fingerprint"`
	CreatedAt    string          `json:"created_at"`
	UpdatedAt    string          `json:"updated_at"`
	LastLaunched string          `json:"last_launched"`
}

type Folder struct {
	ID           string `json:"id"`
	Name         string `json:"name"`
	ProfileCount int    `json:"profile_count"`
	CreatedAt    string `json:"created_at"`
	UpdatedAt    string `json:"updated_at"`
}

type RunningProfile struct {
	ProfileID string `json:"profile_id"`
	PID       int    `json:"pid"`
}

type StatusResponse struct {
	Running          []RunningProfile `json:"running"`
	ChromiumReady    bool             `json:"chromium_ready"`
	ChromiumPath     string           `json:"chromium_path"`
	Downloading      bool             `json:"downloading"`
	DownloadProgress float64          `json:"download_progress"`
	DownloadError    string           `json:"download_error"`
	ServerURL        string           `json:"server_url"`
	ServerConnected  bool             `json:"server_connected"`
}

type LaunchRequest struct {
	ProfileID string `json:"profile_id"`
}

type StopRequest struct {
	ProfileID string `json:"profile_id"`
}

type ConnectRequest struct {
	Server string `json:"server"`
}

// ---------------------------------------------------------------------------
// Global state
// ---------------------------------------------------------------------------

var (
	mu               sync.Mutex
	processes        = make(map[string]*os.Process)
	chromiumReady    bool
	chromiumPath     string
	downloading      bool
	downloadProgress float64
	downloadError    string
	dataDir          string
	serverURL        string
	httpClient       = &http.Client{Timeout: 20 * time.Second}
)

func init() {
	home := os.Getenv("USERPROFILE")
	if home == "" {
		home = os.Getenv("APPDATA")
	}
	if home == "" {
		home, _ = os.UserHomeDir()
	}
	dataDir = filepath.Join(home, ".antidetect")
}

// ---------------------------------------------------------------------------
// CORS middleware
// ---------------------------------------------------------------------------

func withCORS(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next(w, r)
	}
}

// ---------------------------------------------------------------------------
// Chromium management
// ---------------------------------------------------------------------------

func chromiumExePath() string {
	return filepath.Join(dataDir, "chromium", "chrome-win", "chrome.exe")
}

func checkChromium() {
	p := chromiumExePath()
	if _, err := os.Stat(p); err == nil {
		mu.Lock()
		chromiumReady = true
		chromiumPath = p
		mu.Unlock()
	}
}

func downloadChromium() {
	mu.Lock()
	if downloading {
		mu.Unlock()
		return
	}
	downloading = true
	downloadProgress = 0
	downloadError = ""
	mu.Unlock()

	go func() {
		defer func() {
			mu.Lock()
			downloading = false
			mu.Unlock()
		}()

		setErr := func(msg string) {
			mu.Lock()
			downloadError = msg
			mu.Unlock()
			log.Printf("Chromium download error: %s", msg)
		}

		// 1. Get latest revision
		log.Println("Fetching latest Chromium revision...")
		resp, err := http.Get("https://storage.googleapis.com/chromium-browser-snapshots/Win_x64/LAST_CHANGE")
		if err != nil {
			setErr(fmt.Sprintf("Failed to fetch revision: %v", err))
			return
		}
		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			setErr(fmt.Sprintf("Failed to read revision: %v", err))
			return
		}
		revision := strings.TrimSpace(string(body))
		log.Printf("Latest Chromium revision: %s", revision)

		mu.Lock()
		downloadProgress = 5
		mu.Unlock()

		// 2. Download the zip
		zipURL := fmt.Sprintf("https://storage.googleapis.com/chromium-browser-snapshots/Win_x64/%s/chrome-win.zip", revision)
		log.Printf("Downloading: %s", zipURL)

		resp, err = http.Get(zipURL)
		if err != nil {
			setErr(fmt.Sprintf("Download failed: %v", err))
			return
		}
		defer resp.Body.Close()

		if resp.StatusCode != 200 {
			setErr(fmt.Sprintf("Download returned HTTP %d", resp.StatusCode))
			return
		}

		totalSize := resp.ContentLength
		destDir := filepath.Join(dataDir, "chromium")
		os.MkdirAll(destDir, 0755)
		zipPath := filepath.Join(destDir, "chrome-win.zip")

		out, err := os.Create(zipPath)
		if err != nil {
			setErr(fmt.Sprintf("Cannot create zip file: %v", err))
			return
		}

		var downloaded int64
		buf := make([]byte, 256*1024)
		for {
			n, readErr := resp.Body.Read(buf)
			if n > 0 {
				_, writeErr := out.Write(buf[:n])
				if writeErr != nil {
					out.Close()
					setErr(fmt.Sprintf("Write error: %v", writeErr))
					return
				}
				downloaded += int64(n)
				if totalSize > 0 {
					pct := 5.0 + (float64(downloaded)/float64(totalSize))*80.0
					mu.Lock()
					downloadProgress = pct
					mu.Unlock()
				}
			}
			if readErr != nil {
				if readErr == io.EOF {
					break
				}
				out.Close()
				setErr(fmt.Sprintf("Read error: %v", readErr))
				return
			}
		}
		out.Close()
		log.Printf("Downloaded %d bytes", downloaded)

		// 3. Extract zip
		mu.Lock()
		downloadProgress = 87
		mu.Unlock()
		log.Println("Extracting Chromium...")

		if err := extractZip(zipPath, destDir); err != nil {
			setErr(fmt.Sprintf("Extract failed: %v", err))
			return
		}

		os.Remove(zipPath)

		mu.Lock()
		downloadProgress = 100
		mu.Unlock()

		checkChromium()
		log.Println("Chromium ready!")
	}()
}

func extractZip(zipPath, destDir string) error {
	r, err := zip.OpenReader(zipPath)
	if err != nil {
		return err
	}
	defer r.Close()

	for _, f := range r.File {
		target := filepath.Join(destDir, f.Name)

		// Prevent zip slip
		if !strings.HasPrefix(filepath.Clean(target), filepath.Clean(destDir)+string(os.PathSeparator)) {
			continue
		}

		if f.FileInfo().IsDir() {
			os.MkdirAll(target, 0755)
			continue
		}

		os.MkdirAll(filepath.Dir(target), 0755)

		rc, err := f.Open()
		if err != nil {
			return err
		}

		w, err := os.OpenFile(target, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, f.Mode())
		if err != nil {
			rc.Close()
			return err
		}
		io.Copy(w, rc)
		w.Close()
		rc.Close()
	}
	return nil
}

// ---------------------------------------------------------------------------
// Fingerprint extension (MV3)
// ---------------------------------------------------------------------------

func ensureFPExtension() (string, error) {
	extDir := filepath.Join(dataDir, "fp-extension")
	os.MkdirAll(extDir, 0755)

	manifest := `{
  "manifest_version": 3,
  "name": "Fingerprint Guard",
  "version": "1.0",
  "description": "Browser fingerprint management",
  "permissions": ["storage"],
  "content_scripts": [{
    "matches": ["<all_urls>"],
    "js": ["inject.js"],
    "run_at": "document_start",
    "world": "MAIN"
  }]
}`

	inject := `(function() {
  'use strict';
  try {
    var cfgEl = document.getElementById('__fp_config__');
    var config;
    if (cfgEl) {
      config = JSON.parse(cfgEl.textContent);
    } else {
      var xhr = new XMLHttpRequest();
      xhr.open('GET', chrome.runtime.getURL ? chrome.runtime.getURL('config.json') : 'config.json', false);
      try { xhr.send(); config = JSON.parse(xhr.responseText); } catch(e) {}
    }
    if (!config) {
      try {
        var fs = require('fs');
        config = JSON.parse(fs.readFileSync(__dirname + '/config.json', 'utf8'));
      } catch(e2) {}
    }
    if (!config) return;

    // Utility: cloak function toString
    var nativeToString = Function.prototype.toString;
    function cloak(fn, original) {
      var str = 'function ' + (original || fn.name || '') + '() { [native code] }';
      fn.toString = function() { return str; };
      return fn;
    }

    // Canvas fingerprint noise
    if (config.canvas && config.canvas.noise_seed) {
      var seed = config.canvas.noise_seed;
      function mulberry32(a) {
        return function() {
          a |= 0; a = a + 0x6D2B79F5 | 0;
          var t = Math.imul(a ^ a >>> 15, 1 | a);
          t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
          return ((t ^ t >>> 14) >>> 0) / 4294967296;
        };
      }
      var rng = mulberry32(seed);

      var origToDataURL = HTMLCanvasElement.prototype.toDataURL;
      HTMLCanvasElement.prototype.toDataURL = cloak(function() {
        var ctx = this.getContext('2d');
        if (ctx) {
          var imageData = ctx.getImageData(0, 0, this.width, this.height);
          var d = imageData.data;
          for (var i = 0; i < d.length; i += 4) {
            d[i] = d[i] + Math.floor((rng() - 0.5) * 2);
          }
          ctx.putImageData(imageData, 0, 0);
        }
        return origToDataURL.apply(this, arguments);
      }, 'toDataURL');

      var origToBlob = HTMLCanvasElement.prototype.toBlob;
      HTMLCanvasElement.prototype.toBlob = cloak(function(cb, type, quality) {
        var ctx = this.getContext('2d');
        if (ctx) {
          var imageData = ctx.getImageData(0, 0, this.width, this.height);
          var d = imageData.data;
          for (var i = 0; i < d.length; i += 4) {
            d[i] = d[i] + Math.floor((rng() - 0.5) * 2);
          }
          ctx.putImageData(imageData, 0, 0);
        }
        return origToBlob.call(this, cb, type, quality);
      }, 'toBlob');
    }

    // WebGL spoofing
    if (config.webgl) {
      var origGetParam = WebGLRenderingContext.prototype.getParameter;
      WebGLRenderingContext.prototype.getParameter = cloak(function(param) {
        var ext = this.getExtension('WEBGL_debug_renderer_info');
        if (ext) {
          if (param === ext.UNMASKED_VENDOR_WEBGL && config.webgl.vendor) return config.webgl.vendor;
          if (param === ext.UNMASKED_RENDERER_WEBGL && config.webgl.renderer) return config.webgl.renderer;
        }
        return origGetParam.call(this, param);
      }, 'getParameter');

      if (typeof WebGL2RenderingContext !== 'undefined') {
        var origGetParam2 = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = cloak(function(param) {
          var ext = this.getExtension('WEBGL_debug_renderer_info');
          if (ext) {
            if (param === ext.UNMASKED_VENDOR_WEBGL && config.webgl.vendor) return config.webgl.vendor;
            if (param === ext.UNMASKED_RENDERER_WEBGL && config.webgl.renderer) return config.webgl.renderer;
          }
          return origGetParam2.call(this, param);
        }, 'getParameter');
      }
    }

    // Audio context noise
    if (config.audio && config.audio.noise_seed) {
      var audioSeed = config.audio.noise_seed;
      var audioRng = mulberry32(audioSeed);
      var origCreateAnalyser = AudioContext.prototype.createAnalyser || (typeof webkitAudioContext !== 'undefined' && webkitAudioContext.prototype.createAnalyser);
      if (AudioContext.prototype.createAnalyser) {
        var _origCA = AudioContext.prototype.createAnalyser;
        AudioContext.prototype.createAnalyser = cloak(function() {
          var analyser = _origCA.call(this);
          var origGetFloat = analyser.getFloatFrequencyData.bind(analyser);
          analyser.getFloatFrequencyData = cloak(function(array) {
            origGetFloat(array);
            for (var i = 0; i < array.length; i++) {
              array[i] = array[i] + (audioRng() * 0.0001);
            }
          }, 'getFloatFrequencyData');
          return analyser;
        }, 'createAnalyser');
      }
    }

    // Navigator properties
    if (config.navigator) {
      var navProps = config.navigator;
      if (navProps.hardware_concurrency !== undefined) {
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: cloak(function() { return navProps.hardware_concurrency; }, 'get hardwareConcurrency') });
      }
      if (navProps.device_memory !== undefined) {
        Object.defineProperty(navigator, 'deviceMemory', { get: cloak(function() { return navProps.device_memory; }, 'get deviceMemory') });
      }
      if (navProps.platform !== undefined) {
        Object.defineProperty(navigator, 'platform', { get: cloak(function() { return navProps.platform; }, 'get platform') });
      }
      if (navProps.language !== undefined) {
        Object.defineProperty(navigator, 'language', { get: cloak(function() { return navProps.language; }, 'get language') });
      }
      if (navProps.languages !== undefined) {
        Object.defineProperty(navigator, 'languages', { get: cloak(function() { return Object.freeze(navProps.languages.slice()); }, 'get languages') });
      }
    }

    // Screen override
    if (config.screen) {
      var scr = config.screen;
      if (scr.width !== undefined) {
        Object.defineProperty(screen, 'width', { get: cloak(function() { return scr.width; }, 'get width') });
        Object.defineProperty(screen, 'availWidth', { get: cloak(function() { return scr.width; }, 'get availWidth') });
      }
      if (scr.height !== undefined) {
        Object.defineProperty(screen, 'height', { get: cloak(function() { return scr.height; }, 'get height') });
        Object.defineProperty(screen, 'availHeight', { get: cloak(function() { return scr.height - 40; }, 'get availHeight') });
      }
      if (scr.color_depth !== undefined) {
        Object.defineProperty(screen, 'colorDepth', { get: cloak(function() { return scr.color_depth; }, 'get colorDepth') });
        Object.defineProperty(screen, 'pixelDepth', { get: cloak(function() { return scr.color_depth; }, 'get pixelDepth') });
      }
    }

    // Timezone override
    if (config.timezone && config.timezone.name) {
      var tz = config.timezone;
      var OrigDate = Date;
      var origDTF = Intl.DateTimeFormat;
      Intl.DateTimeFormat = cloak(function(loc, opts) {
        opts = opts || {};
        if (!opts.timeZone) opts.timeZone = tz.name;
        return new origDTF(loc, opts);
      }, 'DateTimeFormat');
      Intl.DateTimeFormat.prototype = origDTF.prototype;
      Intl.DateTimeFormat.supportedLocalesOf = origDTF.supportedLocalesOf;

      var origResolvedOptions = origDTF.prototype.resolvedOptions;
      origDTF.prototype.resolvedOptions = cloak(function() {
        var r = origResolvedOptions.call(this);
        r.timeZone = tz.name;
        return r;
      }, 'resolvedOptions');
    }

    // WebRTC IP leak protection
    if (config.webrtc !== false) {
      var origRTCPC = window.RTCPeerConnection || window.webkitRTCPeerConnection;
      if (origRTCPC) {
        var patchedRTC = cloak(function(cfg, constraints) {
          cfg = cfg || {};
          cfg.iceServers = [];
          var pc = new origRTCPC(cfg, constraints);
          var origCreateOffer = pc.createOffer.bind(pc);
          pc.createOffer = cloak(function(opts) {
            return origCreateOffer(opts).then(function(offer) {
              offer.sdp = offer.sdp.replace(/a=candidate:.+typ srflx.+\r\n/g, '');
              offer.sdp = offer.sdp.replace(/a=candidate:.+typ relay.+\r\n/g, '');
              return offer;
            });
          }, 'createOffer');
          return pc;
        }, 'RTCPeerConnection');
        window.RTCPeerConnection = patchedRTC;
        if (window.webkitRTCPeerConnection) window.webkitRTCPeerConnection = patchedRTC;
      }
    }

    // Plugin/mimeType masking — report a standard set
    try {
      Object.defineProperty(navigator, 'plugins', {
        get: cloak(function() {
          return { length: 5,
            0: { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
            1: { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
            2: { name: 'Native Client', filename: 'internal-nacl-plugin' },
            3: { name: 'Chromium PDF Plugin', filename: 'internal-pdf-viewer' },
            4: { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer' },
            item: function(i) { return this[i] || null; },
            namedItem: function(n) { for (var i=0;i<this.length;i++) if(this[i].name===n) return this[i]; return null; },
            refresh: function() {}
          };
        }, 'get plugins')
      });
    } catch(e) {}

    // Hide automation flags
    try {
      Object.defineProperty(navigator, 'webdriver', { get: cloak(function() { return false; }, 'get webdriver') });
    } catch(e) {}
    delete navigator.__proto__.webdriver;

    console.log('[FP Guard] Fingerprint spoofing active');
  } catch(err) {
    console.error('[FP Guard] Init error:', err);
  }
})();`

	if err := os.WriteFile(filepath.Join(extDir, "manifest.json"), []byte(manifest), 0644); err != nil {
		return "", err
	}
	if err := os.WriteFile(filepath.Join(extDir, "inject.js"), []byte(inject), 0644); err != nil {
		return "", err
	}
	return extDir, nil
}

func writeFPConfig(extDir string, fingerprint json.RawMessage) error {
	// Parse the raw fingerprint JSON to extract individual fields
	var fpData map[string]interface{}
	if err := json.Unmarshal(fingerprint, &fpData); err != nil {
		// If fingerprint is empty or invalid, write an empty config
		return os.WriteFile(filepath.Join(extDir, "config.json"), []byte("{}"), 0644)
	}

	cfg := make(map[string]interface{})
	for _, key := range []string{"canvas", "webgl", "audio", "navigator", "screen", "timezone"} {
		if val, ok := fpData[key]; ok {
			cfg[key] = val
		}
	}

	data, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(extDir, "config.json"), data, 0644)
}

// ---------------------------------------------------------------------------
// Proxy auth extension (MV2 — webRequest.onAuthRequired needs MV2)
// ---------------------------------------------------------------------------

func ensureProxyAuthExtension(profileID, proxyStr string) (string, error) {
	parts := strings.SplitN(proxyStr, ":", 4)
	if len(parts) < 4 {
		return "", nil // No auth needed
	}
	user := parts[2]
	pass := parts[3]

	extDir := filepath.Join(dataDir, "proxy-auth", profileID)
	os.MkdirAll(extDir, 0755)

	manifest := `{
  "manifest_version": 2,
  "name": "Proxy Auth Helper",
  "version": "1.0",
  "permissions": ["proxy", "webRequest", "webRequestBlocking", "<all_urls>"],
  "background": {
    "scripts": ["background.js"],
    "persistent": true
  }
}`

	bg := fmt.Sprintf(`chrome.webRequest.onAuthRequired.addListener(
  function(details) {
    return {
      authCredentials: {
        username: %q,
        password: %q
      }
    };
  },
  { urls: ["<all_urls>"] },
  ["blocking"]
);`, user, pass)

	if err := os.WriteFile(filepath.Join(extDir, "manifest.json"), []byte(manifest), 0644); err != nil {
		return "", err
	}
	if err := os.WriteFile(filepath.Join(extDir, "background.js"), []byte(bg), 0644); err != nil {
		return "", err
	}
	return extDir, nil
}

// ---------------------------------------------------------------------------
// Profile launching
// ---------------------------------------------------------------------------

func launchProfile(profileID string) error {
	mu.Lock()
	if _, ok := processes[profileID]; ok {
		mu.Unlock()
		return fmt.Errorf("profile %s is already running", profileID)
	}
	if !chromiumReady {
		mu.Unlock()
		return fmt.Errorf("chromium is not downloaded yet")
	}
	srvURL := serverURL
	mu.Unlock()

	if srvURL == "" {
		return fmt.Errorf("not connected to server")
	}

	// Fetch the full profile from the remote server
	profileURL := srvURL + "/api/profiles/" + profileID
	log.Printf("Fetching profile from %s", profileURL)

	resp, err := httpClient.Get(profileURL)
	if err != nil {
		return fmt.Errorf("failed to fetch profile: %v", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("failed to read profile response: %v", err)
	}

	if resp.StatusCode != 200 {
		return fmt.Errorf("server returned %d: %s", resp.StatusCode, string(body))
	}

	// Server returns {"profile": {...}}
	var envelope struct {
		Profile Profile `json:"profile"`
	}
	if err := json.Unmarshal(body, &envelope); err != nil {
		return fmt.Errorf("invalid profile JSON: %v", err)
	}
	profile := envelope.Profile
	if profile.ID == "" {
		// Fallback: try parsing as bare profile
		if err := json.Unmarshal(body, &profile); err != nil {
			return fmt.Errorf("could not parse profile: %v", err)
		}
	}

	// Create profile data directory
	profileDir := filepath.Join(dataDir, "profiles", profile.ID)
	os.MkdirAll(profileDir, 0755)

	// Fingerprint extension
	fpDir, err := ensureFPExtension()
	if err != nil {
		return fmt.Errorf("fp extension: %v", err)
	}
	if len(profile.Fingerprint) > 0 && string(profile.Fingerprint) != "null" {
		if err := writeFPConfig(fpDir, profile.Fingerprint); err != nil {
			return fmt.Errorf("fp config: %v", err)
		}
	}

	// Build chrome args
	args := []string{
		"--user-data-dir=" + profileDir,
		"--no-first-run",
		"--no-default-browser-check",
		"--disable-blink-features=AutomationControlled",
		"--disable-background-networking",
		"--disable-sync",
		"--disable-translate",
	}

	if profile.WindowWidth > 0 && profile.WindowHeight > 0 {
		args = append(args, fmt.Sprintf("--window-size=%d,%d", profile.WindowWidth, profile.WindowHeight))
	}

	if profile.UserAgent != "" {
		args = append(args, "--user-agent="+profile.UserAgent)
	}

	extensions := []string{fpDir}

	// Proxy
	if profile.Proxy != "" {
		parts := strings.SplitN(profile.Proxy, ":", 4)
		if len(parts) >= 2 {
			args = append(args, fmt.Sprintf("--proxy-server=%s:%s", parts[0], parts[1]))
		}
		if len(parts) == 4 {
			proxyAuthDir, err := ensureProxyAuthExtension(profile.ID, profile.Proxy)
			if err != nil {
				return fmt.Errorf("proxy auth extension: %v", err)
			}
			if proxyAuthDir != "" {
				extensions = append(extensions, proxyAuthDir)
			}
		}
	}

	args = append(args, "--load-extension="+strings.Join(extensions, ","))

	// Write initial preferences to avoid first-run dialogs
	prefsDir := filepath.Join(profileDir, "Default")
	os.MkdirAll(prefsDir, 0755)
	prefs := `{
  "profile": { "default_content_setting_values": { "notifications": 2 } },
  "credentials_enable_service": false,
  "autofill": { "profile_enabled": false },
  "translate": { "enabled": false },
  "browser": { "check_default_browser": false }
}`
	prefsPath := filepath.Join(prefsDir, "Preferences")
	if _, err := os.Stat(prefsPath); os.IsNotExist(err) {
		os.WriteFile(prefsPath, []byte(prefs), 0644)
	}

	log.Printf("Launching profile %s (%s): %s %v", profile.ID, profile.Name, chromiumPath, args)

	cmd := exec.Command(chromiumPath, args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("start chrome: %v", err)
	}

	mu.Lock()
	processes[profile.ID] = cmd.Process
	mu.Unlock()

	// Wait for process in background to clean up on exit
	go func() {
		cmd.Wait()
		mu.Lock()
		delete(processes, profile.ID)
		mu.Unlock()
		log.Printf("Profile %s (%s) exited", profile.ID, profile.Name)
	}()

	return nil
}

func stopProfile(profileID string) error {
	mu.Lock()
	proc, ok := processes[profileID]
	mu.Unlock()
	if !ok {
		return fmt.Errorf("profile %s is not running", profileID)
	}

	// On Windows use taskkill /F /T /PID to kill the process tree
	if runtime.GOOS == "windows" {
		kill := exec.Command("taskkill", "/F", "/T", "/PID", strconv.Itoa(proc.Pid))
		kill.Stdout = os.Stdout
		kill.Stderr = os.Stderr
		if err := kill.Run(); err != nil {
			// Fallback: direct kill
			proc.Kill()
		}
	} else {
		proc.Kill()
	}

	mu.Lock()
	delete(processes, profileID)
	mu.Unlock()
	return nil
}

// ---------------------------------------------------------------------------
// HTTP handlers — local endpoints
// ---------------------------------------------------------------------------

func handleIndex(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Write([]byte(dashboardHTML))
}

func handleConnect(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		jsonError(w, "POST required", 405)
		return
	}

	var req ConnectRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		jsonError(w, "Invalid request body", 400)
		return
	}

	server := strings.TrimRight(req.Server, "/")
	if server == "" {
		jsonError(w, "server field required", 400)
		return
	}

	// Test connection by fetching /api/stats from the server
	statsURL := server + "/api/stats"
	log.Printf("Testing connection to %s", statsURL)

	resp, err := httpClient.Get(statsURL)
	if err != nil {
		jsonError(w, fmt.Sprintf("Failed to connect: %v", err), 502)
		return
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		jsonError(w, fmt.Sprintf("Failed to read response: %v", err), 502)
		return
	}

	if resp.StatusCode != 200 {
		jsonError(w, fmt.Sprintf("Server returned %d: %s", resp.StatusCode, string(body)), resp.StatusCode)
		return
	}

	// Parse stats for the response
	var stats interface{}
	json.Unmarshal(body, &stats)

	// Save the server URL
	mu.Lock()
	serverURL = server
	mu.Unlock()

	log.Printf("Connected to server: %s", server)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"ok":    true,
		"stats": stats,
	})
}

func handleLaunch(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		jsonError(w, "POST required", 405)
		return
	}

	var req LaunchRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		jsonError(w, "Invalid request body", 400)
		return
	}

	if req.ProfileID == "" {
		jsonError(w, "profile_id required", 400)
		return
	}

	if err := launchProfile(req.ProfileID); err != nil {
		jsonError(w, err.Error(), 500)
		return
	}

	jsonOK(w, map[string]string{"status": "launched", "profile_id": req.ProfileID})
}

func handleStop(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		jsonError(w, "POST required", 405)
		return
	}

	var req StopRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		jsonError(w, "Invalid request body", 400)
		return
	}

	if err := stopProfile(req.ProfileID); err != nil {
		jsonError(w, err.Error(), 500)
		return
	}

	jsonOK(w, map[string]string{"status": "stopped", "profile_id": req.ProfileID})
}

func handleStatus(w http.ResponseWriter, r *http.Request) {
	mu.Lock()
	running := make([]RunningProfile, 0, len(processes))
	for id, proc := range processes {
		running = append(running, RunningProfile{ProfileID: id, PID: proc.Pid})
	}
	status := StatusResponse{
		Running:          running,
		ChromiumReady:    chromiumReady,
		ChromiumPath:     chromiumPath,
		Downloading:      downloading,
		DownloadProgress: downloadProgress,
		DownloadError:    downloadError,
		ServerURL:        serverURL,
		ServerConnected:  serverURL != "",
	}
	mu.Unlock()

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(status)
}

func handleDownloadChromium(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		jsonError(w, "POST required", 405)
		return
	}
	downloadChromium()
	jsonOK(w, map[string]string{"status": "download_started"})
}

// ---------------------------------------------------------------------------
// Proxy handler — forwards unmatched /api/* requests to remote server
// ---------------------------------------------------------------------------

func handleProxy(w http.ResponseWriter, r *http.Request) {
	mu.Lock()
	srvURL := serverURL
	mu.Unlock()

	if srvURL == "" {
		jsonError(w, "Not connected to server", 503)
		return
	}

	// Build the target URL: serverURL + original path + query string
	targetURL := srvURL + r.URL.Path
	if r.URL.RawQuery != "" {
		targetURL += "?" + r.URL.RawQuery
	}

	log.Printf("Proxy %s %s -> %s", r.Method, r.URL.Path, targetURL)

	// Create the outgoing request
	var bodyReader io.Reader
	if r.Method == http.MethodPost || r.Method == http.MethodPut {
		bodyReader = r.Body
	}

	proxyReq, err := http.NewRequest(r.Method, targetURL, bodyReader)
	if err != nil {
		jsonError(w, fmt.Sprintf("Proxy request error: %v", err), 500)
		return
	}

	// Forward Content-Type header
	if ct := r.Header.Get("Content-Type"); ct != "" {
		proxyReq.Header.Set("Content-Type", ct)
	}

	resp, err := httpClient.Do(proxyReq)
	if err != nil {
		jsonError(w, fmt.Sprintf("Proxy error: %v", err), 502)
		return
	}
	defer resp.Body.Close()

	// Copy response headers
	for key, vals := range resp.Header {
		for _, val := range vals {
			w.Header().Add(key, val)
		}
	}

	w.WriteHeader(resp.StatusCode)
	io.Copy(w, resp.Body)
}

// ---------------------------------------------------------------------------
// JSON helpers
// ---------------------------------------------------------------------------

func jsonError(w http.ResponseWriter, msg string, code int) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(map[string]string{"error": msg})
}

func jsonOK(w http.ResponseWriter, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(data)
}

// ---------------------------------------------------------------------------
// Open browser
// ---------------------------------------------------------------------------

func openBrowser(url string) {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "windows":
		cmd = exec.Command("rundll32", "url.dll,FileProtocolHandler", url)
	case "darwin":
		cmd = exec.Command("open", url)
	default:
		cmd = exec.Command("xdg-open", url)
	}
	cmd.Start()
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

func main() {
	log.SetFlags(log.LstdFlags | log.Lshortfile)
	log.Println("AntiDetect Browser Launcher starting...")
	log.Printf("Data directory: %s", dataDir)

	os.MkdirAll(dataDir, 0755)
	checkChromium()

	mux := http.NewServeMux()

	// Local handlers (registered first — specific paths take priority)
	mux.HandleFunc("/api/connect", withCORS(handleConnect))
	mux.HandleFunc("/api/launch", withCORS(handleLaunch))
	mux.HandleFunc("/api/stop", withCORS(handleStop))
	mux.HandleFunc("/api/status", withCORS(handleStatus))
	mux.HandleFunc("/api/download-chromium", withCORS(handleDownloadChromium))
	mux.HandleFunc("/", handleIndex)

	// Catch-all proxy for /api/* (anything not matched above)
	mux.HandleFunc("/api/", withCORS(handleProxy))

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		log.Fatalf("Failed to bind: %v", err)
	}
	addr := listener.Addr().String()
	url := "http://" + addr
	log.Printf("GUI available at %s", url)

	// Open browser after a brief delay
	go func() {
		time.Sleep(300 * time.Millisecond)
		openBrowser(url)
	}()

	fmt.Printf("\n  AntiDetect Launcher is running.\n  Open your browser to: %s\n  Press Ctrl+C to quit.\n\n", url)

	server := &http.Server{Handler: mux}
	if err := server.Serve(listener); err != nil {
		log.Fatalf("Server error: %v", err)
	}
}
