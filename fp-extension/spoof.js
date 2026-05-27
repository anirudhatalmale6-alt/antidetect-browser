/**
 * spoof.js - Main-world fingerprint spoofing script.
 *
 * Injected via a <script> tag from inject.js.  Receives its configuration
 * through the data-fp-config attribute on its own <script> element.
 *
 * All overrides are wrapped in an IIFE that deletes itself from scope.
 * Native toString() is preserved so overridden functions report "[native code]".
 */
(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // 0. Read configuration
  // ---------------------------------------------------------------------------
  const scriptEl = document.currentScript;
  let CFG;
  try {
    CFG = JSON.parse(scriptEl.getAttribute('data-fp-config'));
  } catch (_) {
    CFG = {};
  }

  // ---------------------------------------------------------------------------
  // 1. Utility: deterministic PRNG (Mulberry32) seeded from config
  // ---------------------------------------------------------------------------
  function mulberry32(seed) {
    return function () {
      seed |= 0;
      seed = (seed + 0x6d2b79f5) | 0;
      var t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // ---------------------------------------------------------------------------
  // 2. Utility: native toString cloaking
  // ---------------------------------------------------------------------------
  const _toString = Function.prototype.toString;
  const _nativeStr = _toString.call(Array.prototype.forEach); // grab a real native string
  const _nativeSuffix = '{ [native code] }';
  const _cloaked = new WeakSet();

  function cloak(fn, nativeName) {
    _cloaked.add(fn);
    // Store the name so toString can reconstruct the expected output
    fn.__nativeName = nativeName || fn.name || '';
    return fn;
  }

  // Patch Function.prototype.toString itself
  const _origToString = Function.prototype.toString;
  Function.prototype.toString = function () {
    if (_cloaked.has(this)) {
      return 'function ' + (this.__nativeName || '') + '() ' + _nativeSuffix;
    }
    return _origToString.call(this);
  };
  cloak(Function.prototype.toString, 'toString');

  // Helper to define a non-enumerable property (mirrors native shape)
  function defineNonEnum(obj, prop, value) {
    Object.defineProperty(obj, prop, {
      value: value,
      writable: true,
      configurable: true,
      enumerable: false,
    });
  }

  // ---------------------------------------------------------------------------
  // 3. Canvas fingerprint spoofing
  // ---------------------------------------------------------------------------
  (function spoofCanvas() {
    const seed = CFG.canvas_seed || 0;
    if (!seed) return;

    const rng = mulberry32(seed);

    // --- toDataURL ---
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    defineNonEnum(HTMLCanvasElement.prototype, 'toDataURL', cloak(function toDataURL() {
      try {
        const ctx = this.getContext('2d');
        if (ctx) {
          const w = this.width;
          const h = this.height;
          if (w > 0 && h > 0) {
            const imageData = CanvasRenderingContext2D.prototype.getImageData.call(ctx, 0, 0, w, h);
            _noiseImageData(imageData, rng);
            CanvasRenderingContext2D.prototype.putImageData.call(ctx, imageData, 0, 0);
          }
        }
      } catch (_) { /* tainted canvas or other error - skip noise */ }
      return origToDataURL.apply(this, arguments);
    }, 'toDataURL'));

    // --- toBlob ---
    const origToBlob = HTMLCanvasElement.prototype.toBlob;
    defineNonEnum(HTMLCanvasElement.prototype, 'toBlob', cloak(function toBlob(callback) {
      try {
        const ctx = this.getContext('2d');
        if (ctx) {
          const w = this.width;
          const h = this.height;
          if (w > 0 && h > 0) {
            const imageData = CanvasRenderingContext2D.prototype.getImageData.call(ctx, 0, 0, w, h);
            _noiseImageData(imageData, rng);
            CanvasRenderingContext2D.prototype.putImageData.call(ctx, imageData, 0, 0);
          }
        }
      } catch (_) { }
      return origToBlob.apply(this, arguments);
    }, 'toBlob'));

    // --- getImageData ---
    const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
    defineNonEnum(CanvasRenderingContext2D.prototype, 'getImageData', cloak(function getImageData() {
      const imageData = origGetImageData.apply(this, arguments);
      _noiseImageData(imageData, rng);
      return imageData;
    }, 'getImageData'));

    // Deterministic per-pixel noise (subtle: +/- 1 per channel, skip alpha)
    function _noiseImageData(imageData, rngFn) {
      const d = imageData.data;
      // Use a local rng copy seeded from the base seed + dimensions to be
      // deterministic for same canvas size (avoids compounding mutations).
      const localRng = mulberry32(seed ^ (imageData.width * 7 + imageData.height * 13));
      for (let i = 0; i < d.length; i += 4) {
        // Only modify ~10% of pixels for subtlety
        if (localRng() < 0.1) {
          d[i] = Math.max(0, Math.min(255, d[i] + (localRng() < 0.5 ? -1 : 1)));       // R
          d[i + 1] = Math.max(0, Math.min(255, d[i + 1] + (localRng() < 0.5 ? -1 : 1))); // G
          d[i + 2] = Math.max(0, Math.min(255, d[i + 2] + (localRng() < 0.5 ? -1 : 1))); // B
          // Alpha untouched
        }
      }
    }
  })();

  // ---------------------------------------------------------------------------
  // 4. WebGL spoofing
  // ---------------------------------------------------------------------------
  (function spoofWebGL() {
    const vendor = CFG.webgl_vendor;
    const renderer = CFG.webgl_renderer;
    if (!vendor && !renderer) return;

    const UNMASKED_VENDOR = 0x9245;   // UNMASKED_VENDOR_WEBGL
    const UNMASKED_RENDERER = 0x9246; // UNMASKED_RENDERER_WEBGL

    function patchGetParameter(proto) {
      const origGetParameter = proto.getParameter;
      defineNonEnum(proto, 'getParameter', cloak(function getParameter(param) {
        if (param === UNMASKED_VENDOR && vendor) return vendor;
        if (param === UNMASKED_RENDERER && renderer) return renderer;
        return origGetParameter.call(this, param);
      }, 'getParameter'));
    }

    if (typeof WebGLRenderingContext !== 'undefined') {
      patchGetParameter(WebGLRenderingContext.prototype);
    }
    if (typeof WebGL2RenderingContext !== 'undefined') {
      patchGetParameter(WebGL2RenderingContext.prototype);
    }

    // Patch getExtension to ensure WEBGL_debug_renderer_info always works
    function patchGetExtension(proto) {
      const origGetExtension = proto.getExtension;
      defineNonEnum(proto, 'getExtension', cloak(function getExtension(name) {
        const ext = origGetExtension.call(this, name);
        if (name === 'WEBGL_debug_renderer_info' && !ext) {
          // Return a synthetic extension object
          return {
            UNMASKED_VENDOR_WEBGL: UNMASKED_VENDOR,
            UNMASKED_RENDERER_WEBGL: UNMASKED_RENDERER,
          };
        }
        return ext;
      }, 'getExtension'));
    }

    if (typeof WebGLRenderingContext !== 'undefined') {
      patchGetExtension(WebGLRenderingContext.prototype);
    }
    if (typeof WebGL2RenderingContext !== 'undefined') {
      patchGetExtension(WebGL2RenderingContext.prototype);
    }

    // Patch getSupportedExtensions to always include WEBGL_debug_renderer_info
    function patchGetSupported(proto) {
      const origGetSupported = proto.getSupportedExtensions;
      defineNonEnum(proto, 'getSupportedExtensions', cloak(function getSupportedExtensions() {
        const exts = origGetSupported.call(this) || [];
        if (exts.indexOf('WEBGL_debug_renderer_info') === -1) {
          exts.push('WEBGL_debug_renderer_info');
        }
        return exts;
      }, 'getSupportedExtensions'));
    }

    if (typeof WebGLRenderingContext !== 'undefined') {
      patchGetSupported(WebGLRenderingContext.prototype);
    }
    if (typeof WebGL2RenderingContext !== 'undefined') {
      patchGetSupported(WebGL2RenderingContext.prototype);
    }
  })();

  // ---------------------------------------------------------------------------
  // 5. Audio fingerprint spoofing
  // ---------------------------------------------------------------------------
  (function spoofAudio() {
    const audioSeed = CFG.audio_seed || 0;
    if (!audioSeed) return;

    const rng = mulberry32(audioSeed);

    // Wrap OfflineAudioContext and AudioContext to intercept createDynamicsCompressor
    function patchAudioContext(Ctx) {
      if (!Ctx) return;

      const origCreateDynamicsCompressor = Ctx.prototype.createDynamicsCompressor;
      defineNonEnum(Ctx.prototype, 'createDynamicsCompressor', cloak(function createDynamicsCompressor() {
        const compressor = origCreateDynamicsCompressor.call(this);
        // Slightly shift the threshold and knee to alter the audio fingerprint
        const origThreshold = compressor.threshold.value;
        const origKnee = compressor.knee.value;
        try {
          compressor.threshold.setValueAtTime(
            origThreshold + (rng() * 0.001 - 0.0005),
            0
          );
          compressor.knee.setValueAtTime(
            origKnee + (rng() * 0.001 - 0.0005),
            0
          );
        } catch (_) { }
        return compressor;
      }, 'createDynamicsCompressor'));

      // Patch createOscillator to add subtle frequency perturbation
      const origCreateOscillator = Ctx.prototype.createOscillator;
      defineNonEnum(Ctx.prototype, 'createOscillator', cloak(function createOscillator() {
        const osc = origCreateOscillator.call(this);
        const origFreqValue = osc.frequency.value;
        try {
          osc.frequency.setValueAtTime(
            origFreqValue + (rng() * 0.01 - 0.005),
            0
          );
        } catch (_) { }
        return osc;
      }, 'createOscillator'));

      // Intercept getChannelData on rendered buffers for OfflineAudioContext
      if (Ctx.name === 'OfflineAudioContext' || Ctx === window.OfflineAudioContext) {
        const origStartRendering = Ctx.prototype.startRendering;
        defineNonEnum(Ctx.prototype, 'startRendering', cloak(function startRendering() {
          return origStartRendering.call(this).then(function (buffer) {
            // Add micro-noise to rendered buffer channels
            const localRng = mulberry32(audioSeed);
            for (let ch = 0; ch < buffer.numberOfChannels; ch++) {
              const data = buffer.getChannelData(ch);
              for (let i = 0; i < data.length; i++) {
                // Very subtle noise: ~1e-7 magnitude
                data[i] += (localRng() - 0.5) * 0.0000002;
              }
            }
            return buffer;
          });
        }, 'startRendering'));
      }
    }

    if (typeof AudioContext !== 'undefined') patchAudioContext(AudioContext);
    if (typeof OfflineAudioContext !== 'undefined') patchAudioContext(OfflineAudioContext);
    if (typeof webkitAudioContext !== 'undefined') patchAudioContext(webkitAudioContext);
    if (typeof webkitOfflineAudioContext !== 'undefined') patchAudioContext(webkitOfflineAudioContext);
  })();

  // ---------------------------------------------------------------------------
  // 6. Navigator properties
  // ---------------------------------------------------------------------------
  (function spoofNavigator() {
    const overrides = {};
    if (CFG.hardware_concurrency != null) overrides.hardwareConcurrency = CFG.hardware_concurrency;
    if (CFG.device_memory != null) overrides.deviceMemory = CFG.device_memory;
    if (CFG.platform != null) overrides.platform = CFG.platform;
    if (CFG.language != null) overrides.language = CFG.language;
    if (CFG.languages != null) overrides.languages = Object.freeze([].concat(CFG.languages));

    for (const prop in overrides) {
      try {
        Object.defineProperty(Navigator.prototype, prop, {
          get: cloak(function () { return overrides[prop]; }, 'get ' + prop),
          configurable: true,
          enumerable: true,
        });
      } catch (_) {
        // Fallback: try directly on navigator
        try {
          Object.defineProperty(navigator, prop, {
            get: cloak(function () { return overrides[prop]; }, 'get ' + prop),
            configurable: true,
            enumerable: true,
          });
        } catch (_2) { }
      }
    }
  })();

  // ---------------------------------------------------------------------------
  // 7. Screen properties
  // ---------------------------------------------------------------------------
  (function spoofScreen() {
    const w = CFG.screen_width;
    const h = CFG.screen_height;
    if (!w && !h) return;

    const screenOverrides = {};
    if (w) {
      screenOverrides.width = w;
      screenOverrides.availWidth = w;
    }
    if (h) {
      screenOverrides.height = h;
      screenOverrides.availHeight = h;
    }
    // Always set colorDepth to 24 (standard)
    screenOverrides.colorDepth = 24;
    screenOverrides.pixelDepth = 24;

    for (const prop in screenOverrides) {
      const val = screenOverrides[prop];
      try {
        Object.defineProperty(Screen.prototype, prop, {
          get: cloak(function () { return val; }, 'get ' + prop),
          configurable: true,
          enumerable: true,
        });
      } catch (_) {
        try {
          Object.defineProperty(screen, prop, {
            get: cloak(function () { return val; }, 'get ' + prop),
            configurable: true,
            enumerable: true,
          });
        } catch (_2) { }
      }
    }
  })();

  // ---------------------------------------------------------------------------
  // 8. WebRTC local IP leak protection
  // ---------------------------------------------------------------------------
  (function spoofWebRTC() {
    if (typeof RTCPeerConnection === 'undefined') return;

    const OrigRTC = RTCPeerConnection;
    const _origRTCProto = OrigRTC.prototype;

    // Filter out local/private IP candidates
    const localIPPattern = /((^| )(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.|fd[0-9a-f]{2}:|fc[0-9a-f]{2}:))/;
    const mdnsPattern = /\.local$/;

    function RTCPeerConnectionWrapper(config, constraints) {
      // Force the ICE candidate policy to relay-only if we can
      if (config && typeof config === 'object') {
        config = Object.assign({}, config);
        // Don't force relay - too aggressive and breaks many sites.
        // Instead we filter candidates below.
      }
      const pc = new OrigRTC(config, constraints);

      // Wrap onicecandidate setter to filter local IPs
      let _userHandler = null;
      Object.defineProperty(pc, 'onicecandidate', {
        get: function () { return _userHandler; },
        set: function (fn) {
          _userHandler = fn;
        },
        configurable: true,
        enumerable: true,
      });

      // Listen internally and filter
      OrigRTC.prototype.addEventListener.call(pc, 'icecandidate', function (event) {
        if (event.candidate && event.candidate.candidate) {
          const c = event.candidate.candidate;
          // Filter out candidates containing local IPs
          if (localIPPattern.test(c)) {
            // Silently drop local IP candidates
            return;
          }
        }
        if (typeof _userHandler === 'function') {
          _userHandler(event);
        }
      });

      return pc;
    }

    // Copy static properties and prototype
    RTCPeerConnectionWrapper.prototype = _origRTCProto;
    Object.defineProperty(RTCPeerConnectionWrapper, 'name', { value: 'RTCPeerConnection', configurable: true });

    // Also handle generateCertificate
    if (OrigRTC.generateCertificate) {
      RTCPeerConnectionWrapper.generateCertificate = OrigRTC.generateCertificate;
    }

    cloak(RTCPeerConnectionWrapper, 'RTCPeerConnection');

    window.RTCPeerConnection = RTCPeerConnectionWrapper;
    if (window.webkitRTCPeerConnection) {
      window.webkitRTCPeerConnection = RTCPeerConnectionWrapper;
    }
  })();

  // ---------------------------------------------------------------------------
  // 9. Timezone spoofing
  // ---------------------------------------------------------------------------
  (function spoofTimezone() {
    const tzOffset = CFG.timezone_offset;
    const tzName = CFG.timezone_name;

    // --- Date.prototype.getTimezoneOffset ---
    if (tzOffset != null) {
      const origGetTimezoneOffset = Date.prototype.getTimezoneOffset;
      defineNonEnum(Date.prototype, 'getTimezoneOffset', cloak(function getTimezoneOffset() {
        return tzOffset;
      }, 'getTimezoneOffset'));
    }

    // --- Intl.DateTimeFormat ---
    if (tzName) {
      const OrigDTF = Intl.DateTimeFormat;

      function DateTimeFormatWrapper() {
        const args = Array.prototype.slice.call(arguments);
        const options = args[1] && typeof args[1] === 'object' ? Object.assign({}, args[1]) : {};
        if (!options.timeZone) {
          options.timeZone = tzName;
        }
        args[1] = options;
        return new OrigDTF(args[0], args[1]);
      }

      DateTimeFormatWrapper.prototype = OrigDTF.prototype;

      // Copy static methods
      Object.getOwnPropertyNames(OrigDTF).forEach(function (prop) {
        if (prop !== 'prototype' && prop !== 'length' && prop !== 'name') {
          try {
            DateTimeFormatWrapper[prop] = OrigDTF[prop];
          } catch (_) { }
        }
      });

      // Ensure supportedLocalesOf works
      if (OrigDTF.supportedLocalesOf) {
        DateTimeFormatWrapper.supportedLocalesOf = OrigDTF.supportedLocalesOf;
      }

      Object.defineProperty(DateTimeFormatWrapper, 'name', { value: 'DateTimeFormat', configurable: true });
      cloak(DateTimeFormatWrapper, 'DateTimeFormat');

      Intl.DateTimeFormat = DateTimeFormatWrapper;

      // Also patch resolvedOptions to show our timezone
      const origResolvedOptions = OrigDTF.prototype.resolvedOptions;
      defineNonEnum(OrigDTF.prototype, 'resolvedOptions', cloak(function resolvedOptions() {
        const result = origResolvedOptions.call(this);
        if (result.timeZone === undefined || result.timeZone === '') {
          result.timeZone = tzName;
        }
        return result;
      }, 'resolvedOptions'));
    }
  })();

  // ---------------------------------------------------------------------------
  // 10. Plugins & MimeTypes spoofing
  // ---------------------------------------------------------------------------
  (function spoofPlugins() {
    // Build realistic Chrome plugin list
    function createPlugin(name, description, filename, mimeTypes) {
      const plugin = Object.create(Plugin.prototype);
      const props = { name, description, filename, length: mimeTypes.length };
      for (const p in props) {
        Object.defineProperty(plugin, p, {
          value: props[p],
          writable: false,
          enumerable: true,
          configurable: true,
        });
      }
      mimeTypes.forEach(function (mt, i) {
        Object.defineProperty(plugin, i, {
          value: mt,
          writable: false,
          enumerable: true,
          configurable: true,
        });
      });
      return plugin;
    }

    function createMimeType(type, suffixes, description, plugin) {
      const mt = Object.create(MimeType.prototype);
      Object.defineProperty(mt, 'type', { value: type, writable: false, enumerable: true, configurable: true });
      Object.defineProperty(mt, 'suffixes', { value: suffixes, writable: false, enumerable: true, configurable: true });
      Object.defineProperty(mt, 'description', { value: description, writable: false, enumerable: true, configurable: true });
      Object.defineProperty(mt, 'enabledPlugin', { value: plugin, writable: false, enumerable: true, configurable: true });
      return mt;
    }

    // Chrome PDF Plugin
    var pdfPlugin1MimeTypes = [];
    var pdfPlugin1 = createPlugin(
      'Chrome PDF Plugin',
      'Portable Document Format',
      'internal-pdf-viewer',
      pdfPlugin1MimeTypes
    );
    var mt1 = createMimeType('application/x-google-chrome-pdf', 'pdf', 'Portable Document Format', pdfPlugin1);
    pdfPlugin1MimeTypes.push(mt1);

    // Chrome PDF Viewer
    var pdfPlugin2MimeTypes = [];
    var pdfPlugin2 = createPlugin(
      'Chrome PDF Viewer',
      'Portable Document Format',
      'internal-pdf-viewer',
      pdfPlugin2MimeTypes
    );
    var mt2 = createMimeType('application/pdf', 'pdf', 'Portable Document Format', pdfPlugin2);
    pdfPlugin2MimeTypes.push(mt2);

    // Native Client
    var nacl1MimeTypes = [];
    var naclPlugin = createPlugin(
      'Native Client',
      '',
      'internal-nacl-plugin',
      nacl1MimeTypes
    );
    var mt3 = createMimeType('application/x-nacl', '', 'Native Client Executable', naclPlugin);
    var mt4 = createMimeType('application/x-pnacl', '', 'Portable Native Client Executable', naclPlugin);
    nacl1MimeTypes.push(mt3, mt4);

    var allPlugins = [pdfPlugin1, pdfPlugin2, naclPlugin];
    var allMimeTypes = [mt1, mt2, mt3, mt4];

    // Build PluginArray-like object
    function buildPluginArray(plugins) {
      var arr = Object.create(PluginArray.prototype);
      Object.defineProperty(arr, 'length', { value: plugins.length, writable: false, enumerable: true, configurable: true });
      plugins.forEach(function (p, i) {
        Object.defineProperty(arr, i, { value: p, writable: false, enumerable: true, configurable: true });
      });
      defineNonEnum(arr, 'item', cloak(function item(index) { return plugins[index] || null; }, 'item'));
      defineNonEnum(arr, 'namedItem', cloak(function namedItem(name) {
        for (var i = 0; i < plugins.length; i++) {
          if (plugins[i].name === name) return plugins[i];
        }
        return null;
      }, 'namedItem'));
      defineNonEnum(arr, 'refresh', cloak(function refresh() { }, 'refresh'));
      // Make iterable
      defineNonEnum(arr, Symbol.iterator, function () {
        var idx = 0;
        return {
          next: function () {
            if (idx < plugins.length) return { value: plugins[idx++], done: false };
            return { value: undefined, done: true };
          }
        };
      });
      return arr;
    }

    function buildMimeTypeArray(mimeTypes) {
      var arr = Object.create(MimeTypeArray.prototype);
      Object.defineProperty(arr, 'length', { value: mimeTypes.length, writable: false, enumerable: true, configurable: true });
      mimeTypes.forEach(function (m, i) {
        Object.defineProperty(arr, i, { value: m, writable: false, enumerable: true, configurable: true });
      });
      defineNonEnum(arr, 'item', cloak(function item(index) { return mimeTypes[index] || null; }, 'item'));
      defineNonEnum(arr, 'namedItem', cloak(function namedItem(name) {
        for (var i = 0; i < mimeTypes.length; i++) {
          if (mimeTypes[i].type === name) return mimeTypes[i];
        }
        return null;
      }, 'namedItem'));
      defineNonEnum(arr, Symbol.iterator, function () {
        var idx = 0;
        return {
          next: function () {
            if (idx < mimeTypes.length) return { value: mimeTypes[idx++], done: false };
            return { value: undefined, done: true };
          }
        };
      });
      return arr;
    }

    var fakePlugins = buildPluginArray(allPlugins);
    var fakeMimeTypes = buildMimeTypeArray(allMimeTypes);

    try {
      Object.defineProperty(Navigator.prototype, 'plugins', {
        get: cloak(function () { return fakePlugins; }, 'get plugins'),
        configurable: true,
        enumerable: true,
      });
      Object.defineProperty(Navigator.prototype, 'mimeTypes', {
        get: cloak(function () { return fakeMimeTypes; }, 'get mimeTypes'),
        configurable: true,
        enumerable: true,
      });
    } catch (_) {
      try {
        Object.defineProperty(navigator, 'plugins', {
          get: cloak(function () { return fakePlugins; }, 'get plugins'),
          configurable: true,
          enumerable: true,
        });
        Object.defineProperty(navigator, 'mimeTypes', {
          get: cloak(function () { return fakeMimeTypes; }, 'get mimeTypes'),
          configurable: true,
          enumerable: true,
        });
      } catch (_2) { }
    }

    // Also make navigator.pdfViewerEnabled consistent
    try {
      Object.defineProperty(Navigator.prototype, 'pdfViewerEnabled', {
        get: cloak(function () { return true; }, 'get pdfViewerEnabled'),
        configurable: true,
        enumerable: true,
      });
    } catch (_) { }
  })();

})();
