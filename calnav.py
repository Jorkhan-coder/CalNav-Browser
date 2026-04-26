#!/usr/bin/env python3
"""CalNav Browser — Modern spirit, classic roots."""

__version__ = "1.1.11-alpha"

import json
import os
import re
import sys
from pathlib import Path

from typing import List, Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLineEdit, QPushButton, QStatusBar, QProgressBar, QLabel,
    QDialog, QDialogButtonBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QScrollArea, QMessageBox,
    QTabWidget, QTabBar, QMenu, QColorDialog, QInputDialog, QSlider,
    QSplitter, QListWidget, QListWidgetItem, QCheckBox, QComboBox,
    QSpinBox, QFormLayout,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile, QWebEngineSettings, QWebEngineScript, QWebEnginePage,
)
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import (
    QUrl, Qt, QObject, pyqtSlot, pyqtSignal, QFile, QIODevice,
    PYQT_VERSION_STR, QT_VERSION_STR, QTimer, QRect, QSize,
)
from PyQt6.QtGui import QFont, QIcon, QKeySequence, QShortcut, QPainter, QColor
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest

from calnav_profiles import ProfileManager, PROFILE_COLORS, DATA_DIR
from calnav_passwords import PasswordManager
from calnav_bookmarks import BookmarkManager, Bookmark, UNCATEGORIZED
from calnav_session import TabGroup, SavedTab, SessionManager

HOME_URL = "https://www.google.com"
GITHUB_API_URL = (
    "https://api.github.com/repos/Jorkhan-coder/CalNav-Browser/releases/latest"
)
GITHUB_RELEASES_URL = (
    "https://github.com/Jorkhan-coder/CalNav-Browser/releases/latest"
)
_SETTINGS_FILE = DATA_DIR / "settings.json"
_SETTINGS_DEFAULTS = {"homepage": HOME_URL, "theme": "dark"}


def _load_settings() -> dict:
    if _SETTINGS_FILE.exists():
        try:
            data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
            return {**_SETTINGS_DEFAULTS, **data}
        except Exception:
            pass
    return dict(_SETTINGS_DEFAULTS)


def _save_settings(s: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(
        json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8"
    )

# User-agent: byte-for-byte identical to Chrome 124 on Windows 10 x64.
# Deliberately no "CalNav" token — Twitch, Netflix and other streaming CDNs
# do exact-suffix checks like /Safari\/537\.36$/ and reject any extra tokens.
CALNAV_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

IE_UA = "Mozilla/5.0 (Windows NT 10.0; Trident/7.0; rv:11.0) like Gecko"

IE_SHIMS_JS = """
(function() {
    'use strict';

    if (!Element.prototype.attachEvent) {
        Element.prototype.attachEvent = function(ev, fn) {
            this.addEventListener(ev.replace(/^on/, ''), fn);
        };
        Element.prototype.detachEvent = function(ev, fn) {
            this.removeEventListener(ev.replace(/^on/, ''), fn);
        };
    }
    if (!window.attachEvent) {
        window.attachEvent = function(ev, fn) {
            window.addEventListener(ev.replace(/^on/, ''), fn);
        };
        window.detachEvent = function(ev, fn) {
            window.removeEventListener(ev.replace(/^on/, ''), fn);
        };
    }

    try {
        if (!document.all) {
            Object.defineProperty(document, 'all', {
                get: function() { return document.getElementsByTagName('*'); },
                configurable: true
            });
        }
    } catch(e) {}

    try {
        Object.defineProperty(document, 'documentMode', {
            value: 11, configurable: true, writable: true
        });
    } catch(e) {}

    ['click','dblclick','mousedown','mouseup','mousemove',
     'keydown','keyup','keypress','submit','change','focus','blur'
    ].forEach(function(type) {
        document.addEventListener(type, function(e) {
            try { window.event = e; } catch(x) {}
        }, true);
    });

    if (!window.XDomainRequest) {
        window.XDomainRequest = function() { return new XMLHttpRequest(); };
    }

    if (!window.ActiveXObject) {
        window.ActiveXObject = function(name) {
            console.warn('CalNav IE-compat: ActiveXObject("' + name + '") non supportato.');
            throw new Error('ActiveXObject non disponibile: ' + name);
        };
    }

    try {
        if (!Element.prototype.currentStyle) {
            Object.defineProperty(Element.prototype, 'currentStyle', {
                get: function() { return window.getComputedStyle(this); },
                configurable: true
            });
        }
    } catch(e) {}

    try {
        if (!navigator.userLanguage) {
            Object.defineProperty(navigator, 'userLanguage', {
                get: function() { return navigator.language || 'it-IT'; },
                configurable: true
            });
        }
    } catch(e) {}

    window.CollectGarbage = function() {};

    if (!window.execScript) {
        window.execScript = function(code) { eval(code); }; // eslint-disable-line
    }

    if (!window.showModalDialog) {
        window.showModalDialog = function(url) {
            window.open(url, '_blank', 'width=600,height=400');
        };
    }

    console.info('[CalNav] Modalita compatibilita IE11 attiva.');
})();
"""

# ── Chrome-compatibility shim (injected at DocumentCreation in every page) ────
# QtWebEngine is built on Chromium but does NOT expose window.chrome — that
# object is part of the Chrome browser layer, not the open-source Chromium
# engine.  Twitch, Netflix and similar services check for window.chrome (or
# specific sub-properties) to decide whether the browser is "compatible".
# Without it they show error #4000 / codec-not-supported screens even though
# the underlying Chromium is perfectly capable.
CHROME_COMPAT_JS = """
(function () {
    'use strict';
    if (window.chrome) return;
    var chrome = {
        app: {
            isInstalled: false,
            InstallState: {
                DISABLED: 'disabled', INSTALLED: 'installed',
                NOT_INSTALLED: 'not_installed'
            },
            RunningState: {
                CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run',
                RUNNING: 'running'
            },
            getDetails:      function () { return null; },
            getIsInstalled:  function () { return false; },
            installState:    function (cb) { cb('not_installed'); }
        },
        csi: function () {
            return { startE: Date.now(), onloadT: Date.now(), pageT: 0, tran: 15 };
        },
        loadTimes: function () {
            var t = Date.now() / 1000;
            return {
                commitLoadTime: t, connectionInfo: 'h2',
                finishDocumentLoadTime: t, finishLoadTime: t,
                firstPaintAfterLoadTime: 0, firstPaintTime: t,
                navigationType: 'Other', npnNegotiatedProtocol: 'h2',
                requestTime: t - 0.05, startLoadTime: t - 0.05,
                wasAlternateProtocolAvailable: false,
                wasFetchedViaSpdy: true, wasNpnNegotiated: true
            };
        },
        runtime: {
            id: undefined,
            connect:             function () { return { onMessage: { addListener: function(){} }, postMessage: function(){}, disconnect: function(){} }; },
            sendMessage:         function () {},
            onMessage:           { addListener: function(){}, removeListener: function(){} },
            onConnect:           { addListener: function(){}, removeListener: function(){} },
            onInstalled:         { addListener: function(){}, removeListener: function(){} },
            OnInstalledReason:   { CHROME_UPDATE:'chrome_update', INSTALL:'install', SHARED_MODULE_UPDATE:'shared_module_update', UPDATE:'update' },
            PlatformArch:        { X86_64:'x86-64', X86_32:'x86-32', ARM:'arm', MIPS:'mips', MIPS64:'mips64' },
            PlatformOs:          { WIN:'win', MAC:'mac', LINUX:'linux', ANDROID:'android', CROS:'cros', OPENBSD:'openbsd' }
        }
    };
    try {
        Object.defineProperty(window, 'chrome', {
            value: chrome, writable: false, enumerable: true, configurable: false
        });
    } catch (e) {
        window.chrome = chrome;
    }
})();
"""

DETECT_FORMS_JS = """
(function() {
    if (typeof QWebChannel === 'undefined' || typeof qt === 'undefined') return;

    new QWebChannel(qt.webChannelTransport, function(channel) {
        var bridge = channel.objects.calnav_bridge;
        if (!bridge) return;

        function getUserField(form) {
            var selectors = [
                'input[type="email"]',
                'input[autocomplete="username"]',
                'input[autocomplete="email"]',
                'input[name*="email" i]',
                'input[name*="user" i]',
                'input[name*="login" i]',
                'input[id*="email" i]',
                'input[id*="user" i]',
                'input[id*="login" i]',
                'input[type="text"]'
            ];
            for (var i = 0; i < selectors.length; i++) {
                var el = form.querySelector(selectors[i]);
                if (el && el.value) return el;
            }
            return null;
        }

        function watchForm(form) {
            if (form._cnWatched) return;
            form._cnWatched = true;
            form.addEventListener('submit', function() {
                var pw = form.querySelector('input[type="password"]');
                if (!pw || !pw.value) return;
                var usr = getUserField(form);
                if (usr && usr.value) {
                    try { bridge.offer_save_password(location.href, usr.value, pw.value); }
                    catch(e) {}
                }
            }, true);
        }

        function scanForms() {
            document.querySelectorAll('form').forEach(watchForm);
        }

        if (document.readyState !== 'loading') {
            scanForms();
        } else {
            document.addEventListener('DOMContentLoaded', scanForms);
        }

        new MutationObserver(function() { scanForms(); })
            .observe(document.documentElement, { childList: true, subtree: true });
    });
})();
"""

# ── Media detection & control JS (injected at DocumentReady in every page) ───
MEDIA_JS = r"""
(function() {
  if (window.__cn_media_init) return;
  window.__cn_media_init = true;

  var bridge = null;
  var lastReport = '';
  var reportPending = false;

  // Connect to the QWebChannel bridge (async – retried until ready)
  function tryConnect() {
    if (typeof QWebChannel === 'undefined' || typeof qt === 'undefined') {
      setTimeout(tryConnect, 600); return;
    }
    new QWebChannel(qt.webChannelTransport, function(ch) {
      bridge = ch.objects.calnav_bridge;
      scheduleReport(0);
    });
  }
  tryConnect();

  // Find the "most relevant" media element: prefer playing, else first found
  function getMedia() {
    var all = [].slice.call(document.querySelectorAll('video, audio'));
    return (
      all.find(function(m){ return !m.paused && !m.ended && m.readyState >= 2; }) ||
      all[0] || null
    );
  }

  function scheduleReport(delay) {
    if (reportPending) return;
    reportPending = true;
    setTimeout(function() { reportPending = false; doReport(); }, delay || 0);
  }

  // Returns true when the video is large enough to have its own visible player UI
  // (YouTube, Vimeo, Netflix, etc.).  In that case CalNav should NOT show its
  // own media bar, since it would be redundant.
  function hasVisiblePlayerUI(m) {
    if (!m || m.tagName !== 'VIDEO') return false;
    var r = m.getBoundingClientRect();
    return (
      r.width  >= 160 &&
      r.height >= 90  &&
      r.bottom >  0   &&
      r.top    <  window.innerHeight &&
      r.right  >  0   &&
      r.left   <  window.innerWidth
    );
  }

  function doReport() {
    if (!bridge) return;
    // Hidden tabs stop reporting — Python keeps the last known state so the
    // tab-bar dot remains lit even when you're on a different tab.
    if (document.hidden) return;
    var m = getMedia();
    var s;
    if (m && (m.currentSrc || m.src)) {
      s = JSON.stringify({
        hasMedia:      true,
        isVideo:       m.tagName === 'VIDEO',
        hasOwnPlayer:  hasVisiblePlayerUI(m),   // page already has a visible player
        src:           m.currentSrc || m.src || '',
        currentTime:   m.currentTime,
        duration:      isFinite(m.duration) ? m.duration : 0,
        paused:        m.paused,
        volume:        m.volume,
        muted:         m.muted,
        title:         document.title || location.hostname || ''
      });
    } else {
      s = '{"hasMedia":false}';
    }
    sendState(s);
  }

  function sendState(s) {
    if (s === lastReport) return;
    lastReport = s;
    try { bridge.on_media_state(s); } catch(e) {}
  }

  // Wire a single media element to auto-report on events
  function wire(el) {
    if (el.__cn_m) return; el.__cn_m = true;
    ['play','pause','ended','seeking','seeked',
     'volumechange','loadedmetadata','durationchange','emptied'
    ].forEach(function(e){ el.addEventListener(e, function(){ scheduleReport(80); }); });
  }

  function scan() { document.querySelectorAll('video,audio').forEach(wire); }

  if (document.body) scan();
  document.addEventListener('DOMContentLoaded', scan);
  // Report when tab becomes visible (user switches back to this tab)
  document.addEventListener('visibilitychange', function() {
    if (!document.hidden) scheduleReport(150);
    // When hidden: do NOT send — Python keeps last known state for the dot indicator
  });
  // Watch for dynamically inserted media (SPAs, YouTube, etc.)
  new MutationObserver(scan)
    .observe(document.documentElement, {childList: true, subtree: true});
  // Periodic heartbeat so seek position stays in sync
  setInterval(function(){ if (!document.hidden) doReport(); }, 2500);

  // ── Commands called from Python via page.runJavaScript ───────────────────
  // Exposed as window.__cn_* so Python can call them safely

  window.__cn_report = function() { lastReport = ''; doReport(); };

  window.__cn_play_pause = function() {
    var m = getMedia() || document.querySelector('video, audio');
    if (!m) return;
    if (m.paused) { m.play(); } else { m.pause(); }
  };

  window.__cn_seek_to = function(t) {
    var m = getMedia() || document.querySelector('video, audio');
    if (m) m.currentTime = parseFloat(t);
  };

  window.__cn_seek_rel = function(d) {
    var m = getMedia() || document.querySelector('video, audio');
    if (m) m.currentTime = Math.max(0, m.currentTime + parseFloat(d));
  };

  window.__cn_volume = function(v) {
    document.querySelectorAll('video,audio').forEach(function(m) {
      m.volume  = Math.min(1, Math.max(0, parseFloat(v)));
      m.muted   = (parseFloat(v) === 0);
    });
  };

  // Picture-in-Picture — works when called in response to a user action
  // (Python calls this from button/shortcut, which satisfies the gesture req)
  window.__cn_pip = function() {
    var v = [].slice.call(document.querySelectorAll('video'));
    var target = v.find(function(x){ return !x.paused; }) || v[0];
    if (!target) return;
    if (document.pictureInPictureElement === target) {
      document.exitPictureInPicture().catch(function(){});
    } else {
      target.requestPictureInPicture().catch(function(e){
        console.warn('[CalNav PiP]', e.message);
      });
    }
  };
})();
"""

# ── Palettes ──────────────────────────────────────────────────────────────────
_PALETTES = {
    "dark": {
        "NAVY_DEEP":   "#07111F",
        "NAVY_MID":    "#0D1F3C",
        "NAVY_LIGHT":  "#1C2B45",
        "TEAL":        "#00D4FF",
        "TEAL_DIM":    "#008EAA",
        "AMBER":       "#F5A623",
        "AMBER_DIM":   "#B87400",
        "TEXT_BRIGHT": "#E8F4FD",
        "TEXT_DIM":    "#4A7AB5",
        "BTN_HOVER":   "rgba(0,212,255,0.14)",
        "BTN_PRESS":   "rgba(0,212,255,0.28)",
    },
    "light": {
        "NAVY_DEEP":   "#F0F4F8",
        "NAVY_MID":    "#FFFFFF",
        "NAVY_LIGHT":  "#DDE6F0",
        "TEAL":        "#0077AA",
        "TEAL_DIM":    "#005577",
        "AMBER":       "#C07800",
        "AMBER_DIM":   "#9A5E00",
        "TEXT_BRIGHT": "#0D1F3C",
        "TEXT_DIM":    "#4A6A8A",
        "BTN_HOVER":   "rgba(0,119,170,0.10)",
        "BTN_PRESS":   "rgba(0,119,170,0.22)",
    },
}
_current_theme = "dark"


def set_theme(name: str) -> None:
    """Update all module-level palette globals to the given theme."""
    global _current_theme
    global NAVY_DEEP, NAVY_MID, NAVY_LIGHT, TEAL, TEAL_DIM
    global AMBER, AMBER_DIM, TEXT_BRIGHT, TEXT_DIM, BTN_HOVER, BTN_PRESS
    _current_theme = name
    p = _PALETTES.get(name, _PALETTES["dark"])
    NAVY_DEEP   = p["NAVY_DEEP"]
    NAVY_MID    = p["NAVY_MID"]
    NAVY_LIGHT  = p["NAVY_LIGHT"]
    TEAL        = p["TEAL"]
    TEAL_DIM    = p["TEAL_DIM"]
    AMBER       = p["AMBER"]
    AMBER_DIM   = p["AMBER_DIM"]
    TEXT_BRIGHT = p["TEXT_BRIGHT"]
    TEXT_DIM    = p["TEXT_DIM"]
    BTN_HOVER   = p["BTN_HOVER"]
    BTN_PRESS   = p["BTN_PRESS"]


def _global_qss() -> str:
    """Base QSS applied at QApplication level for transient widgets."""
    return f"""
        QMenu {{
            background: {NAVY_MID}; color: {TEXT_BRIGHT};
            border: 1px solid {TEAL_DIM}; border-radius: 6px;
        }}
        QMenu::item {{ padding: 5px 22px 5px 14px; }}
        QMenu::item:selected {{ background: rgba(0,212,255,0.18); color: {TEAL}; }}
        QMenu::separator {{ height: 1px; background: {NAVY_LIGHT}; margin: 3px 8px; }}
        QToolTip {{
            background: {NAVY_MID}; color: {TEXT_BRIGHT};
            border: 1px solid {TEAL_DIM}; border-radius: 4px; padding: 4px 8px;
        }}
        QScrollBar:vertical {{
            background: {NAVY_DEEP}; width: 8px; border: none; border-radius: 4px;
        }}
        QScrollBar::handle:vertical {{
            background: {TEAL_DIM}; border-radius: 4px; min-height: 20px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{
            background: {NAVY_DEEP}; height: 8px; border: none;
        }}
        QScrollBar::handle:horizontal {{
            background: {TEAL_DIM}; border-radius: 4px; min-width: 20px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    """


# Initialise globals from dark palette
set_theme("dark")


# ── Helpers ───────────────────────────────────────────────────────────────────
def _load_qwebchannel_js() -> str:
    f = QFile(":/qtwebchannel/qwebchannel.js")
    if f.open(QIODevice.OpenModeFlag.ReadOnly):
        content = bytes(f.readAll()).decode("utf-8", errors="replace")
        f.close()
        return content
    return ""


# ── Nav button ────────────────────────────────────────────────────────────────
class NavButton(QPushButton):
    def __init__(self, symbol: str, tooltip: str = "", parent=None):
        super().__init__(symbol, parent)
        self.setFixedSize(38, 38)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: #7AB8E8;
                border: none;
                border-radius: 19px;
                font-size: 17px;
            }}
            QPushButton:hover   {{ background: {BTN_HOVER}; color: {TEAL}; }}
            QPushButton:pressed {{ background: {BTN_PRESS}; }}
            QPushButton:disabled {{ color: #253852; }}
        """)


# ── Address bar ───────────────────────────────────────────────────────────────
class AddressBar(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Cerca o inserisci un URL…")
        self.setFixedHeight(38)
        self.setFont(QFont("Segoe UI", 11))
        self._set_normal()

    def _set_normal(self):
        self.setStyleSheet(f"""
            QLineEdit {{
                background: {NAVY_LIGHT};
                color: {TEXT_BRIGHT};
                border: 1.5px solid #253852;
                border-radius: 19px;
                padding: 0 18px;
                selection-background-color: {TEAL};
                selection-color: {NAVY_DEEP};
            }}
            QLineEdit:focus {{
                border: 1.5px solid {TEAL};
                background: #1E3050;
            }}
        """)

    def _set_ie_mode(self):
        self.setStyleSheet(f"""
            QLineEdit {{
                background: {NAVY_LIGHT};
                color: {TEXT_BRIGHT};
                border: 1.5px solid {AMBER_DIM};
                border-radius: 19px;
                padding: 0 18px;
                selection-background-color: {AMBER};
                selection-color: {NAVY_DEEP};
            }}
            QLineEdit:focus {{
                border: 1.5px solid {AMBER};
                background: #1E2B0A;
            }}
        """)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.selectAll()


# ── QWebChannel bridge ────────────────────────────────────────────────────────
class CalNavBridge(QObject):
    save_password_requested = pyqtSignal(str, str, str)
    # Emitted every time the active tab's media state changes.
    # Payload is a JSON string (see MEDIA_JS for schema).
    media_state_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    @pyqtSlot(str, str, str)
    def offer_save_password(self, url: str, username: str, password: str):
        self.save_password_requested.emit(url, username, password)

    @pyqtSlot(str)
    def on_media_state(self, state_json: str):
        """Receives media state from MEDIA_JS running in any tab."""
        self.media_state_changed.emit(state_json)


# ── Save-password notification bar ───────────────────────────────────────────
class SavePasswordBar(QWidget):
    save_requested = pyqtSignal(str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._url = self._username = self._password = ""
        self._build()
        self.hide()

    def _build(self):
        self.setFixedHeight(46)
        self._apply_style()
        h = QHBoxLayout(self)
        h.setContentsMargins(18, 0, 18, 0)
        h.setSpacing(12)

        self._icon = QLabel("[*]")
        self._icon.setStyleSheet(f"color: {TEAL}; font-size: 14px; font-weight: bold;")
        h.addWidget(self._icon)

        self._msg = QLabel("Vuoi salvare la password per questo sito?")
        self._msg.setStyleSheet(f"color: {TEXT_BRIGHT}; font-size: 12px;")
        h.addWidget(self._msg, stretch=1)

        self._btn_save = QPushButton("Salva")
        self._btn_save.setFixedSize(80, 30)
        self._btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_save.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._btn_save.setStyleSheet(f"""
            QPushButton {{ background: {TEAL}; color: {NAVY_DEEP}; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {TEAL}; filter: brightness(1.15); }}
        """)
        self._btn_save.clicked.connect(self._on_save)
        h.addWidget(self._btn_save)

        self._btn_dismiss = QPushButton("Non ora")
        self._btn_dismiss.setFixedSize(80, 30)
        self._btn_dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_dismiss.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT_DIM}; border: 1px solid {NAVY_LIGHT}; border-radius: 6px; }}
            QPushButton:hover {{ border-color: {TEAL_DIM}; color: {TEXT_BRIGHT}; }}
        """)
        self._btn_dismiss.clicked.connect(self.hide)
        h.addWidget(self._btn_dismiss)

    def _apply_style(self):
        self.setStyleSheet(
            f"background: {NAVY_MID}; border-bottom: 1px solid {TEAL_DIM};"
        )

    def retheme(self):
        self._apply_style()
        if hasattr(self, "_icon"):
            self._icon.setStyleSheet(f"color: {TEAL}; font-size: 14px; font-weight: bold;")
            self._msg.setStyleSheet(f"color: {TEXT_BRIGHT}; font-size: 12px;")
            self._btn_save.setStyleSheet(f"""
                QPushButton {{ background: {TEAL}; color: {NAVY_DEEP}; border: none; border-radius: 6px; }}
                QPushButton:hover {{ background: {TEAL}; filter: brightness(1.15); }}
            """)
            self._btn_dismiss.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {TEXT_DIM}; border: 1px solid {NAVY_LIGHT}; border-radius: 6px; }}
                QPushButton:hover {{ border-color: {TEAL_DIM}; color: {TEXT_BRIGHT}; }}
            """)

    def offer(self, url: str, username: str, password: str):
        self._url, self._username, self._password = url, username, password
        try:
            from urllib.parse import urlparse
            host = urlparse(url).netloc or url
        except Exception:
            host = url
        self._msg.setText(f"Salva la password per  {host}  ({username})?")
        self.show()

    def _on_save(self):
        self.hide()
        self.save_requested.emit(self._url, self._username, self._password)


# ── Profile avatar button ─────────────────────────────────────────────────────
class ProfileAvatarButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__("P", parent)
        self.setFixedSize(38, 38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Profili  Ctrl+Shift+P")
        self._color = PROFILE_COLORS[0]
        self._refresh_style()

    def update_profile(self, initial: str, color: str):
        self._color = color
        self._refresh_style()
        self.setText(initial)

    def _refresh_style(self):
        self.setStyleSheet(f"""
            QPushButton {{
                background: {self._color};
                color: {NAVY_DEEP};
                border: none;
                border-radius: 19px;
                font-size: 15px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: white; }}
            QPushButton:pressed {{ background: {self._color}; }}
        """)


# ── New-profile dialog ────────────────────────────────────────────────────────
class NewProfileDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nuovo Profilo")
        self.setFixedSize(380, 260)
        self.selected_color = PROFILE_COLORS[0]
        self._color_btns: list = []
        self._build()

    def _build(self):
        self.setStyleSheet(f"background: {NAVY_MID}; color: {TEXT_BRIGHT};")
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(24, 24, 24, 16)
        vbox.setSpacing(14)

        lbl = QLabel("Nome profilo:")
        lbl.setStyleSheet(f"color: {TEXT_BRIGHT}; font-size: 13px;")
        vbox.addWidget(lbl)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("es. Lavoro, Personale…")
        self.name_edit.setFixedHeight(38)
        self.name_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {NAVY_LIGHT}; color: {TEXT_BRIGHT};
                border: 1.5px solid #253852; border-radius: 8px;
                padding: 0 12px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {TEAL}; }}
        """)
        vbox.addWidget(self.name_edit)

        lbl2 = QLabel("Colore avatar:")
        lbl2.setStyleSheet(f"color: {TEXT_BRIGHT}; font-size: 13px;")
        vbox.addWidget(lbl2)

        row = QHBoxLayout()
        row.setSpacing(8)
        for c in PROFILE_COLORS:
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"background: {c}; border-radius: 14px; border: 2px solid transparent;")
            btn.clicked.connect(lambda _, col=c: self._select_color(col))
            row.addWidget(btn)
            self._color_btns.append((btn, c))
        row.addStretch()
        vbox.addLayout(row)
        self._select_color(PROFILE_COLORS[0])

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.setStyleSheet(f"""
            QPushButton {{
                background: {TEAL}; color: {NAVY_DEEP};
                border: none; border-radius: 6px;
                padding: 6px 18px; font-weight: bold; min-width: 80px;
            }}
            QPushButton:hover {{ background: #33DDFF; }}
        """)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        vbox.addWidget(btns)

    def _select_color(self, color: str):
        self.selected_color = color
        for btn, c in self._color_btns:
            border = "3px solid white" if c == color else "2px solid transparent"
            btn.setStyleSheet(f"background: {c}; border-radius: 14px; border: {border};")

    def get_values(self):
        return self.name_edit.text().strip(), self.selected_color


# ── Profile manager dialog ────────────────────────────────────────────────────
class ProfileDialog(QDialog):
    switched = pyqtSignal(str)

    def __init__(self, profile_manager: ProfileManager, parent=None):
        super().__init__(parent)
        self.pm = profile_manager
        self.setWindowTitle("Profili CalNav")
        self.setFixedSize(460, 420)
        self._list_layout = None
        self._build()

    def _build(self):
        self.setStyleSheet(f"background: {NAVY_MID}; color: {TEXT_BRIGHT};")
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(20, 20, 20, 16)
        vbox.setSpacing(12)

        hdr = QLabel("Gestione Profili")
        hdr.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {TEAL}; margin-bottom: 4px;")
        vbox.addWidget(hdr)

        list_container = QWidget()
        self._list_layout = QVBoxLayout(list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(list_container)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        vbox.addWidget(scroll, stretch=1)

        self._refresh_list()

        bottom = QHBoxLayout()
        btn_new = QPushButton("+ Nuovo profilo")
        btn_new.setFixedHeight(36)
        btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_new.setStyleSheet(f"""
            QPushButton {{ background: {TEAL}; color: {NAVY_DEEP}; border: none; border-radius: 8px; font-weight: bold; padding: 0 16px; }}
            QPushButton:hover {{ background: #33DDFF; }}
        """)
        btn_new.clicked.connect(self._create_profile)
        bottom.addWidget(btn_new)
        bottom.addStretch()

        btn_close = QPushButton("Chiudi")
        btn_close.setFixedHeight(36)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT_DIM}; border: 1px solid #253852; border-radius: 8px; padding: 0 16px; }}
            QPushButton:hover {{ color: {TEXT_BRIGHT}; border-color: {TEAL_DIM}; }}
        """)
        btn_close.clicked.connect(self.reject)
        bottom.addWidget(btn_close)
        vbox.addLayout(bottom)

    def _refresh_list(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        current = self.pm.current.name
        for profile in self.pm.profiles:
            row = self._make_profile_row(profile, profile.name == current)
            self._list_layout.addWidget(row)
        self._list_layout.addStretch()

    def _make_profile_row(self, profile, is_current: bool) -> QWidget:
        row = QWidget()
        row.setFixedHeight(58)
        border_css = (
            f"border: 1.5px solid {profile.color};"
            if is_current
            else "border: 1px solid #1C3050;"
        )
        row.setStyleSheet(
            f"background: {NAVY_DEEP}; border-radius: 10px; {border_css}"
        )

        h = QHBoxLayout(row)
        h.setContentsMargins(12, 0, 12, 0)
        h.setSpacing(12)

        avatar = QLabel(profile.initial)
        avatar.setFixedSize(36, 36)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            f"background: {profile.color}; color: {NAVY_DEEP}; "
            f"border-radius: 18px; font-weight: bold; font-size: 15px;"
        )
        h.addWidget(avatar)

        info = QVBoxLayout()
        info.setSpacing(1)
        name_lbl = QLabel(profile.display_name)
        name_lbl.setStyleSheet(
            f"color: {TEXT_BRIGHT}; font-size: 13px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        info.addWidget(name_lbl)
        if is_current:
            curr_lbl = QLabel("Attivo")
            curr_lbl.setStyleSheet(
                f"color: {profile.color}; font-size: 10px; background: transparent; border: none;"
            )
            info.addWidget(curr_lbl)
        h.addLayout(info, stretch=1)

        if not is_current:
            btn_switch = QPushButton("Usa")
            btn_switch.setFixedSize(56, 30)
            btn_switch.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_switch.setStyleSheet(f"""
                QPushButton {{ background: {TEAL}; color: {NAVY_DEEP}; border: none; border-radius: 6px; font-weight: bold; font-size: 11px; }}
                QPushButton:hover {{ background: #33DDFF; }}
            """)
            btn_switch.clicked.connect(lambda _, n=profile.name: self._switch_to(n))
            h.addWidget(btn_switch)

            btn_del = QPushButton("Elimina")
            btn_del.setFixedSize(64, 30)
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: #FF6B6B; border: 1px solid rgba(255,107,107,0.3); border-radius: 6px; font-size: 11px; }}
                QPushButton:hover {{ background: rgba(255,107,107,0.15); }}
            """)
            btn_del.clicked.connect(lambda _, n=profile.name: self._delete_profile(n))
            h.addWidget(btn_del)

        return row

    def _switch_to(self, name: str):
        self.pm.set_current(name)
        self.switched.emit(name)
        self.accept()

    def _create_profile(self):
        dlg = NewProfileDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            display, color = dlg.get_values()
            if display:
                self.pm.create(display, color)
                self._refresh_list()

    def _delete_profile(self, name: str):
        p = self.pm.get(name)
        if not p:
            return
        reply = QMessageBox.question(
            self,
            "Elimina profilo",
            f"Eliminare il profilo \"{p.display_name}\"?\n"
            "Le password salvate verranno rimosse.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.pm.delete(name)
            self._refresh_list()


# ── Password generator dialog ─────────────────────────────────────────────────
class PasswordGeneratorDialog(QDialog):
    """Floating dialog to create a random secure password."""

    password_accepted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Genera Password — CalNav")
        self.setFixedSize(420, 310)
        self.setStyleSheet(f"background: {NAVY_MID}; color: {TEXT_BRIGHT};")
        self._build()
        self._generate()

    def _build(self):
        _BTN_GHOST = f"""
            QPushButton {{
                background: {BTN_HOVER}; color: {TEAL};
                border: none; border-radius: 6px; padding: 0 14px;
                font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {BTN_PRESS}; }}
        """
        self._BTN_GHOST = _BTN_GHOST  # store for buttons added in same method

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(24, 20, 24, 18)
        vbox.setSpacing(14)

        hdr = QLabel("Genera Password")
        hdr.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {TEAL};")
        vbox.addWidget(hdr)

        res_row = QHBoxLayout()
        self._result = QLineEdit()
        self._result.setReadOnly(True)
        self._result.setFixedHeight(36)
        self._result.setStyleSheet(f"""
            QLineEdit {{
                background: {NAVY_DEEP}; color: {TEXT_BRIGHT};
                border: 1px solid #1C3050; border-radius: 7px;
                padding: 0 10px; font-size: 13px; font-family: Consolas, monospace;
            }}
        """)
        res_row.addWidget(self._result, stretch=1)
        btn_refresh = QPushButton("⟳")
        btn_refresh.setFixedSize(36, 36)
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh.setToolTip("Genera nuova")
        btn_refresh.setStyleSheet(self._BTN_GHOST)
        btn_refresh.clicked.connect(self._generate)
        res_row.addWidget(btn_refresh)
        vbox.addLayout(res_row)

        len_row = QHBoxLayout()
        len_row.addWidget(QLabel("Lunghezza:"))
        self._len_spin = QSpinBox()
        self._len_spin.setRange(8, 64)
        self._len_spin.setValue(16)
        self._len_spin.setFixedWidth(62)
        self._len_spin.setStyleSheet(f"""
            QSpinBox {{
                background: {NAVY_DEEP}; color: {TEXT_BRIGHT};
                border: 1px solid #1C3050; border-radius: 5px; padding: 2px 6px;
            }}
        """)
        self._len_spin.valueChanged.connect(self._generate)
        len_row.addWidget(self._len_spin)
        self._len_slider = QSlider(Qt.Orientation.Horizontal)
        self._len_slider.setRange(8, 64)
        self._len_slider.setValue(16)
        self._len_slider.valueChanged.connect(self._len_spin.setValue)
        self._len_spin.valueChanged.connect(self._len_slider.setValue)
        len_row.addWidget(self._len_slider, stretch=1)
        vbox.addLayout(len_row)

        opt_row = QHBoxLayout()
        self._cb_upper   = QCheckBox("Maiuscole")
        self._cb_digits  = QCheckBox("Cifre")
        self._cb_symbols = QCheckBox("Simboli")
        for cb in (self._cb_upper, self._cb_digits, self._cb_symbols):
            cb.setChecked(True)
            cb.setStyleSheet(f"color: {TEXT_BRIGHT}; spacing: 6px;")
            cb.stateChanged.connect(self._generate)
            opt_row.addWidget(cb)
        opt_row.addStretch()
        vbox.addLayout(opt_row)

        self._strength_label = QLabel("")
        self._strength_label.setStyleSheet("font-size: 11px;")
        vbox.addWidget(self._strength_label)
        vbox.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_copy = QPushButton("Copia")
        btn_copy.setFixedHeight(34)
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.setStyleSheet(self._BTN_GHOST)
        btn_copy.clicked.connect(self._copy)
        btn_row.addWidget(btn_copy)
        btn_use = QPushButton("Usa")
        btn_use.setFixedHeight(34)
        btn_use.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_use.setStyleSheet(f"""
            QPushButton {{ background: {TEAL}; color: {NAVY_DEEP};
                border: none; border-radius: 6px; padding: 0 18px; font-weight: bold; }}
            QPushButton:hover {{ background: #33DDFF; }}
        """)
        btn_use.clicked.connect(self._use)
        btn_row.addWidget(btn_use)
        btn_cancel = QPushButton("Annulla")
        btn_cancel.setFixedHeight(34)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(self._BTN_GHOST)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        vbox.addLayout(btn_row)

    def _generate(self):
        from calnav_passwords import PasswordManager as _PM
        pw = _PM.generate_password(
            length=self._len_spin.value(),
            uppercase=self._cb_upper.isChecked(),
            digits=self._cb_digits.isChecked(),
            symbols=self._cb_symbols.isChecked(),
        )
        self._result.setText(pw)
        score = sum([
            len(pw) >= 12, len(pw) >= 16,
            any(c.isupper() for c in pw),
            any(c.isdigit() for c in pw),
            any(not c.isalnum() for c in pw),
        ])
        labels = ["", "Molto debole", "Debole", "Discreta", "Forte", "Molto forte"]
        colors = ["", "#FF6B6B", "#FF922B", "#FFD43B", "#51CF66", "#00D4FF"]
        idx = min(score, 5)
        self._strength_label.setText(f"Forza: {labels[idx]}")
        self._strength_label.setStyleSheet(f"font-size: 11px; color: {colors[idx]};")

    def _copy(self):
        QApplication.clipboard().setText(self._result.text())

    def _use(self):
        self.password_accepted.emit(self._result.text())
        self.accept()

    def current_password(self) -> str:
        return self._result.text()


# ── Edit password entry dialog ────────────────────────────────────────────────
class EditPasswordEntryDialog(QDialog):
    """Edit username, password and category of a saved credential."""

    def __init__(self, entry: dict, categories: list, pm, parent=None):
        super().__init__(parent)
        self._entry = entry
        self._pm = pm
        self._all_cats = categories
        self.setWindowTitle("Modifica credenziale — CalNav")
        self.setFixedSize(400, 280)
        self.setStyleSheet(f"background: {NAVY_MID}; color: {TEXT_BRIGHT};")
        self._build()

    def _build(self):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(24, 20, 24, 18)
        vbox.setSpacing(10)

        hdr = QLabel(f"  {self._entry.get('host', '')}")
        hdr.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {TEAL};")
        vbox.addWidget(hdr)

        _field_ss = f"""
            QLineEdit, QComboBox {{
                background: {NAVY_DEEP}; color: {TEXT_BRIGHT};
                border: 1px solid #1C3050; border-radius: 6px; padding: 4px 8px;
            }}
        """
        form = QFormLayout()
        form.setSpacing(8)

        self._usr = QLineEdit(self._entry.get("username", ""))
        self._usr.setStyleSheet(_field_ss)
        form.addRow("Utente:", self._usr)

        self._pw = QLineEdit(self._entry.get("password", ""))
        self._pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw.setStyleSheet(_field_ss)

        _btn_ss = f"""
            QPushButton {{ background: rgba(0,212,255,0.12); color: {TEAL};
                border: none; border-radius: 5px; font-size: 13px; }}
            QPushButton:checked {{ background: rgba(0,212,255,0.28); }}
            QPushButton:hover {{ background: rgba(0,212,255,0.22); }}
        """
        pw_row = QHBoxLayout()
        pw_row.setSpacing(4)
        pw_row.addWidget(self._pw)
        btn_eye = QPushButton("\U0001f441")
        btn_eye.setFixedSize(30, 30)
        btn_eye.setCheckable(True)
        btn_eye.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_eye.setStyleSheet(_btn_ss)
        btn_eye.toggled.connect(lambda on: self._pw.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        pw_row.addWidget(btn_eye)
        btn_gen = QPushButton("\U0001f3b2")
        btn_gen.setFixedSize(30, 30)
        btn_gen.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_gen.setToolTip("Genera password")
        btn_gen.setStyleSheet(_btn_ss)
        btn_gen.clicked.connect(self._open_generator)
        pw_row.addWidget(btn_gen)
        pw_w = QWidget()
        pw_w.setLayout(pw_row)
        form.addRow("Password:", pw_w)

        self._cat_combo = QComboBox()
        self._cat_combo.setEditable(True)
        self._cat_combo.setStyleSheet(_field_ss)
        for c in self._all_cats:
            self._cat_combo.addItem(c)
        cur = self._entry.get("category", "Generale")
        idx = self._cat_combo.findText(cur)
        if idx >= 0:
            self._cat_combo.setCurrentIndex(idx)
        else:
            self._cat_combo.setCurrentText(cur)
        form.addRow("Categoria:", self._cat_combo)

        vbox.addLayout(form)
        vbox.addStretch()

        bot = QHBoxLayout()
        bot.addStretch()
        btn_save = QPushButton("Salva")
        btn_save.setFixedHeight(34)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet(f"""
            QPushButton {{ background: {TEAL}; color: {NAVY_DEEP};
                border: none; border-radius: 6px; padding: 0 20px; font-weight: bold; }}
            QPushButton:hover {{ background: #33DDFF; }}
        """)
        btn_save.clicked.connect(self._save)
        bot.addWidget(btn_save)
        btn_cancel = QPushButton("Annulla")
        btn_cancel.setFixedHeight(34)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{ background: rgba(0,212,255,0.15); color: {TEAL};
                border: none; border-radius: 6px; padding: 0 16px; }}
            QPushButton:hover {{ background: rgba(0,212,255,0.28); }}
        """)
        btn_cancel.clicked.connect(self.reject)
        bot.addWidget(btn_cancel)
        vbox.addLayout(bot)

    def _open_generator(self):
        dlg = PasswordGeneratorDialog(self)
        dlg.password_accepted.connect(self._pw.setText)
        dlg.exec()

    def _save(self):
        new_usr = self._usr.text().strip()
        new_pw  = self._pw.text()
        new_cat = self._cat_combo.currentText().strip() or "Generale"
        if not new_usr:
            return
        self._pm.update_entry(
            self._entry["host"], self._entry["username"],
            new_username=new_usr,
            new_password=new_pw if new_pw else None,
            new_category=new_cat,
        )
        self.accept()


# ── Password vault dialog ─────────────────────────────────────────────────────
class PasswordVaultDialog(QDialog):
    """Full vault: category sidebar, search bar, table, generator shortcut."""

    def __init__(self, password_manager, parent=None):
        super().__init__(parent)
        self.pm = password_manager
        self.setWindowTitle("Password Salvate — CalNav")
        self.resize(820, 520)
        self._current_category: str = "Tutte"
        self._build()

    def _build(self):
        _TABLE_SS = f"""
            QTableWidget {{
                background: {NAVY_DEEP}; gridline-color: {NAVY_LIGHT};
                color: {TEXT_BRIGHT}; border: 1px solid {NAVY_LIGHT}; border-radius: 8px;
            }}
            QHeaderView::section {{
                background: {NAVY_MID}; color: {TEAL};
                border: none; padding: 6px; font-weight: bold;
            }}
            QTableWidget::item {{ padding: 4px 8px; }}
            QTableWidget::item:selected {{ background: {BTN_HOVER}; }}
        """
        _BTN_TEAL = f"""
            QPushButton {{ background: {TEAL}; color: {NAVY_DEEP};
                border: none; border-radius: 7px; padding: 0 22px; font-weight: bold; }}
            QPushButton:hover {{ background: {TEAL}; opacity: 0.85; }}
        """
        _BTN_GHOST = f"""
            QPushButton {{ background: {BTN_HOVER}; color: {TEAL};
                border: none; border-radius: 7px; padding: 0 14px; font-size: 12px; }}
            QPushButton:hover {{ background: {BTN_PRESS}; }}
        """
        self.setStyleSheet(f"background: {NAVY_MID}; color: {TEXT_BRIGHT};")
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        hdr_row = QHBoxLayout()
        hdr = QLabel("Password Salvate")
        hdr.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {TEAL};")
        hdr_row.addWidget(hdr)
        hdr_row.addStretch()
        self._search = QLineEdit()
        self._search.setPlaceholderText("\U0001f50d  Cerca sito, utente o categoria…")
        self._search.setFixedHeight(32)
        self._search.setFixedWidth(280)
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: {NAVY_DEEP}; color: {TEXT_BRIGHT};
                border: 1px solid #1C3050; border-radius: 7px; padding: 0 10px;
            }}
        """)
        self._search.textChanged.connect(self._refresh_table)
        hdr_row.addWidget(self._search)
        root.addLayout(hdr_row)

        if not self.pm.available:
            warn = QLabel(
                "Il modulo 'cryptography' non è installato.\n"
                "Esegui:  pip install cryptography"
            )
            warn.setStyleSheet("color: #FF6B6B; padding: 20px; font-size: 13px;")
            root.addWidget(warn)
            root.addStretch()
            self._add_close_btn(root)
            return

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background: #1C3050; width: 1px; }")

        left = QWidget()
        left.setFixedWidth(170)
        left.setStyleSheet(f"background: {NAVY_DEEP}; border-radius: 8px;")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 8, 0, 0)
        lv.setSpacing(0)

        cat_hdr = QLabel("  Categorie")
        cat_hdr.setStyleSheet(
            f"color: {TEAL}; font-weight: bold; font-size: 11px; padding: 4px 0 6px 0;")
        lv.addWidget(cat_hdr)

        self._cat_list = QListWidget()
        self._cat_list.setStyleSheet(f"""
            QListWidget {{
                background: transparent; border: none;
                color: {TEXT_BRIGHT}; font-size: 12px;
            }}
            QListWidget::item {{ padding: 7px 12px; border-radius: 5px; }}
            QListWidget::item:selected {{ background: rgba(0,212,255,0.18); color: {TEAL}; }}
            QListWidget::item:hover:!selected {{ background: rgba(255,255,255,0.05); }}
        """)
        self._cat_list.currentItemChanged.connect(self._on_category_selected)
        self._cat_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._cat_list.customContextMenuRequested.connect(self._cat_context_menu)
        lv.addWidget(self._cat_list, stretch=1)

        btn_new_cat = QPushButton("＋  Nuova categoria")
        btn_new_cat.setFixedHeight(30)
        btn_new_cat.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_new_cat.setStyleSheet(f"""
            QPushButton {{
                background: rgba(0,212,255,0.10); color: {TEAL};
                border: none; border-radius: 0 0 8px 8px;
                font-size: 11px; padding: 0 12px;
            }}
            QPushButton:hover {{ background: rgba(0,212,255,0.22); }}
        """)
        btn_new_cat.clicked.connect(self._new_category)
        lv.addWidget(btn_new_cat)
        splitter.addWidget(left)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Sito", "Utente", "Password", "Categoria", "Azioni"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setStyleSheet(self._TABLE_SS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        splitter.addWidget(self.table)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)

        bot = QHBoxLayout()
        btn_gen = QPushButton("\U0001f3b2  Genera password")
        btn_gen.setFixedHeight(36)
        btn_gen.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_gen.setStyleSheet(self._BTN_GHOST)
        btn_gen.clicked.connect(self._open_generator)
        bot.addWidget(btn_gen)
        bot.addStretch()
        btn_close = QPushButton("Chiudi")
        btn_close.setFixedHeight(36)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(self._BTN_TEAL)
        btn_close.clicked.connect(self.accept)
        bot.addWidget(btn_close)
        root.addLayout(bot)

        self._rebuild_categories()
        self._refresh_table()

    def _add_close_btn(self, layout):
        bot = QHBoxLayout()
        bot.addStretch()
        btn = QPushButton("Chiudi")
        btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(self._BTN_TEAL)
        btn.clicked.connect(self.accept)
        bot.addWidget(btn)
        layout.addLayout(bot)

    def _rebuild_categories(self):
        self._cat_list.blockSignals(True)
        self._cat_list.clear()
        all_n = len(self.pm.all_entries())
        self._cat_list.addItem(QListWidgetItem(f"Tutte  ({all_n})"))
        for c in self.pm.categories():
            n = len(self.pm.search(category=c))
            self._cat_list.addItem(QListWidgetItem(f"{c}  ({n})"))
        for i in range(self._cat_list.count()):
            if self._cat_list.item(i).text().startswith(self._current_category):
                self._cat_list.setCurrentRow(i)
                break
        else:
            self._cat_list.setCurrentRow(0)
        self._cat_list.blockSignals(False)

    def _on_category_selected(self, item):
        if item is None:
            return
        self._current_category = item.text().rsplit("  (", 1)[0]
        self._refresh_table()

    def _cat_context_menu(self, pos):
        item = self._cat_list.itemAt(pos)
        if item is None:
            return
        name = item.text().rsplit("  (", 1)[0]
        if name == "Tutte":
            return
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background: {NAVY_MID}; color: {TEXT_BRIGHT};
                border: 1px solid #1C3050; }}
            QMenu::item:selected {{ background: rgba(0,212,255,0.18); }}
        """)
        act_rename = menu.addAction("✎  Rinomina")
        act_delete = menu.addAction("✕  Elimina (sposta in Generale)")
        act = menu.exec(self._cat_list.viewport().mapToGlobal(pos))
        if act == act_rename:
            self._rename_category(name)
        elif act == act_delete:
            self._delete_category(name)

    def _new_category(self):
        name, ok = QInputDialog.getText(self, "Nuova categoria", "Nome categoria:")
        if ok and name.strip():
            self._current_category = name.strip()
            self._rebuild_categories()

    def _rename_category(self, old_name: str):
        new_name, ok = QInputDialog.getText(
            self, "Rinomina categoria", "Nuovo nome:", text=old_name)
        if ok and new_name.strip() and new_name.strip() != old_name:
            self.pm.rename_category(old_name, new_name.strip())
            self._current_category = new_name.strip()
            self._rebuild_categories()
            self._refresh_table()

    def _delete_category(self, name: str):
        self.pm.delete_category(name)
        self._current_category = "Tutte"
        self._rebuild_categories()
        self._refresh_table()

    def _refresh_table(self):
        entries = self.pm.search(
            query=self._search.text(),
            category=self._current_category,
        )
        self.table.setRowCount(len(entries))

        _ss_act = f"""
            QPushButton {{
                background: rgba(0,212,255,0.12); color: {TEAL};
                border: none; border-radius: 5px;
                font-size: 12px; font-weight: 500;
            }}
            QPushButton:hover {{ background: rgba(0,212,255,0.28); }}
        """
        _ss_del = f"""
            QPushButton {{
                background: rgba(255,107,107,0.12); color: #FF6B6B;
                border: none; border-radius: 5px;
                font-size: 12px; font-weight: 500;
            }}
            QPushButton:hover {{ background: rgba(255,107,107,0.28); }}
        """
        # Fixed button sizes — explicit width prevents squishing
        BW, BH = 68, 30   # normal action button
        SW, SH = 58, 30   # shorter (Copia, Elimina)

        for r, e in enumerate(entries):
            self.table.setItem(r, 0, QTableWidgetItem(e.get("host", "")))
            self.table.setItem(r, 1, QTableWidgetItem(e.get("username", "")))
            self.table.setItem(r, 2, QTableWidgetItem("•" * 8))
            self.table.setItem(r, 3, QTableWidgetItem(e.get("category", "Generale")))
            self.table.setRowHeight(r, 50)

            cell = QWidget()
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(6, 8, 6, 8)
            cl.setSpacing(5)

            btn_show = QPushButton("Mostra")
            btn_show.setFixedSize(BW, BH)
            btn_show.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_show.setToolTip("Mostra / nascondi password")
            btn_show.setStyleSheet(_ss_act)
            btn_show.clicked.connect(
                lambda _, row=r, pw=e["password"]: self._toggle_pw(row, pw))
            cl.addWidget(btn_show)

            btn_copy = QPushButton("Copia")
            btn_copy.setFixedSize(SW, BH)
            btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_copy.setToolTip("Copia password negli appunti")
            btn_copy.setStyleSheet(_ss_act)
            btn_copy.clicked.connect(
                lambda _, pw=e["password"]: QApplication.clipboard().setText(pw))
            cl.addWidget(btn_copy)

            btn_edit = QPushButton("Modifica")
            btn_edit.setFixedSize(BW, BH)
            btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_edit.setToolTip("Modifica utente, password o categoria")
            btn_edit.setStyleSheet(_ss_act)
            btn_edit.clicked.connect(
                lambda _, entry=dict(e): self._edit_entry(entry))
            cl.addWidget(btn_edit)

            btn_del = QPushButton("Elimina")
            btn_del.setFixedSize(SW, BH)
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.setToolTip("Elimina questa credenziale")
            btn_del.setStyleSheet(_ss_del)
            btn_del.clicked.connect(
                lambda _, h=e["host"], u=e["username"]: self._delete_entry(h, u))
            cl.addWidget(btn_del)

            self.table.setCellWidget(r, 4, cell)

        # Force the Azioni column to fit the cell widgets exactly
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents)

    def _toggle_pw(self, row: int, password: str):
        item = self.table.item(row, 2)
        if item:
            item.setText(password if item.text() == "•" * 8 else "•" * 8)

    def _edit_entry(self, entry: dict):
        cats = self.pm.categories() or ["Generale"]
        dlg = EditPasswordEntryDialog(entry, cats, self.pm, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._rebuild_categories()
            self._refresh_table()

    def _delete_entry(self, host: str, username: str):
        self.pm.delete(host, username)
        self._rebuild_categories()
        self._refresh_table()

    def _open_generator(self):
        PasswordGeneratorDialog(self).exec()


# ── Autofill bar ──────────────────────────────────────────────────────────────
class AutofillBar(QWidget):
    """Thin bar shown when saved credentials are available for the current page."""

    fill_requested = pyqtSignal(str, str)  # username, password
    dismissed      = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("autofill_bar")
        self.setFixedHeight(38)
        self.setStyleSheet(self._bar_ss())
        self.hide()

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 0, 8, 0)
        row.setSpacing(8)

        icon = QLabel("\U0001f511")
        icon.setFixedWidth(20)
        row.addWidget(icon)

        self._msg = QLabel("")
        row.addWidget(self._msg)
        row.addStretch()

        self._combo = QComboBox()
        self._combo.setFixedHeight(26)
        self._combo.setStyleSheet(f"""
            QComboBox {{
                background: {NAVY_DEEP}; color: {TEXT_BRIGHT};
                border: 1px solid #1C3050; border-radius: 4px;
                padding: 0 6px; font-size: 12px;
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background: {NAVY_MID}; color: {TEXT_BRIGHT};
                selection-background-color: rgba(0,212,255,0.2);
            }}
        """)
        self._combo.hide()
        row.addWidget(self._combo)

        self._btn_fill = QPushButton("Compila")
        self._btn_fill.setFixedHeight(26)
        self._btn_fill.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_fill.setStyleSheet(self._fill_btn_ss())
        self._btn_fill.clicked.connect(self._on_fill)
        row.addWidget(self._btn_fill)

        self._btn_dismiss = QPushButton("Ignora")
        self._btn_dismiss.setFixedHeight(26)
        self._btn_dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_dismiss.setStyleSheet(self._dismiss_btn_ss())
        self._btn_dismiss.clicked.connect(self._dismiss)
        row.addWidget(self._btn_dismiss)

        self._entries: list = []

    def _bar_ss(self) -> str:
        return f"""
            QWidget#autofill_bar {{
                background: {NAVY_MID}; border-bottom: 1px solid {TEAL_DIM};
            }}
            QLabel {{ color: {TEXT_BRIGHT}; font-size: 12px; background: transparent; }}
        """

    def _fill_btn_ss(self) -> str:
        return f"""
            QPushButton {{ background: {TEAL}; color: {NAVY_DEEP};
                border: none; border-radius: 5px; padding: 2px 12px;
                font-weight: bold; font-size: 12px; }}
            QPushButton:hover {{ background: {TEAL}; opacity: 0.85; }}
        """

    def _dismiss_btn_ss(self) -> str:
        return f"""
            QPushButton {{ background: {BTN_HOVER}; color: {TEAL};
                border: none; border-radius: 5px; padding: 2px 10px; font-size: 12px; }}
            QPushButton:hover {{ background: {BTN_PRESS}; }}
        """

    def retheme(self):
        self.setStyleSheet(self._bar_ss())
        if hasattr(self, "_msg"):
            self._msg.setStyleSheet(f"color: {TEXT_BRIGHT}; font-size: 12px; background: transparent;")
        if hasattr(self, "_combo"):
            self._combo.setStyleSheet(f"""
                QComboBox {{
                    background: {NAVY_LIGHT}; color: {TEXT_BRIGHT};
                    border: 1px solid {TEAL_DIM}; border-radius: 4px;
                    padding: 0 6px; font-size: 12px;
                }}
                QComboBox::drop-down {{ border: none; }}
                QComboBox QAbstractItemView {{
                    background: {NAVY_MID}; color: {TEXT_BRIGHT};
                    selection-background-color: {BTN_HOVER};
                }}
            """)
        if hasattr(self, "_btn_fill"):
            self._btn_fill.setStyleSheet(self._fill_btn_ss())
            self._btn_dismiss.setStyleSheet(self._dismiss_btn_ss())

    def offer(self, entries: list):
        """Show the bar for a list of credential dicts (host already matched)."""
        if not entries:
            self.hide()
            return
        self._entries = entries
        if len(entries) == 1:
            e = entries[0]
            self._msg.setText(
                f"Credenziali salvate per  <b>{e['host']}</b>  ({e['username']})")
            self._combo.hide()
        else:
            self._msg.setText(
                f"Credenziali salvate per  <b>{entries[0]['host']}</b>:")
            self._combo.clear()
            for e in entries:
                self._combo.addItem(e["username"])
            self._combo.show()
        self.show()

    def _on_fill(self):
        if not self._entries:
            return
        idx = max(self._combo.currentIndex(), 0) if self._combo.isVisible() else 0
        e = self._entries[idx]
        self.fill_requested.emit(e["username"], e["password"])
        self.hide()
        self.dismissed.emit()

    def _dismiss(self):
        self.hide()
        self.dismissed.emit()



# ── Bookmark helpers ─────────────────────────────────────────────────────────
def _url_color(url: str) -> str:
    """Colore deterministico basato sul dominio."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc or url
    except Exception:
        host = url
    return PROFILE_COLORS[hash(host) % len(PROFILE_COLORS)]


def _url_initial(url: str) -> str:
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lstrip("www.") or url
        return host[0].upper() if host else "?"
    except Exception:
        return "?"


# ── Add / Edit bookmark dialog ────────────────────────────────────────────────
class AddBookmarkDialog(QDialog):
    def __init__(self, url: str, title: str, bm_manager: BookmarkManager,
                 bookmark: Bookmark = None, parent=None):
        super().__init__(parent)
        self._url = url
        self._bm  = bookmark
        self._mgr = bm_manager
        self.setWindowTitle("Modifica preferito" if bookmark else "Aggiungi ai preferiti")
        self.setFixedSize(400, 240)
        self._build(title)

    def _build(self, title: str):
        self.setStyleSheet(f"background: {NAVY_MID}; color: {TEXT_BRIGHT};")
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(24, 20, 24, 16)
        vbox.setSpacing(12)

        # Nome
        vbox.addWidget(self._lbl("Nome:"))
        self._name = QLineEdit(self._bm.title if self._bm else title)
        self._name.setFixedHeight(36)
        self._name.setStyleSheet(self._field_css())
        vbox.addWidget(self._name)

        # Categoria
        cat_row = QHBoxLayout()
        cat_row.setSpacing(8)
        vbox.addWidget(self._lbl("Categoria:"))
        self._cat_combo = self._build_combo()
        cat_row.addWidget(self._cat_combo, stretch=1)
        btn_new_cat = QPushButton("+ Nuova")
        btn_new_cat.setFixedHeight(34)
        btn_new_cat.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_new_cat.setStyleSheet(f"""
            QPushButton {{ background: rgba(0,212,255,0.12); color: {TEAL};
                border: 1px solid {TEAL_DIM}; border-radius: 8px; padding: 0 10px; font-size: 11px; }}
            QPushButton:hover {{ background: rgba(0,212,255,0.22); }}
        """)
        btn_new_cat.clicked.connect(self._new_category)
        cat_row.addWidget(btn_new_cat)
        vbox.addLayout(cat_row)

        # Pin
        self._pin_chk = QPushButton("  Fissa in alto")
        self._pin_chk.setCheckable(True)
        self._pin_chk.setChecked(self._bm.pinned if self._bm else False)
        self._pin_chk.setFixedHeight(32)
        self._pin_chk.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pin_chk.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT_DIM};
                border: 1px solid #253852; border-radius: 8px; text-align: left; padding: 0 12px; font-size: 12px; }}
            QPushButton:checked {{ color: {AMBER}; border-color: {AMBER_DIM}; background: rgba(245,166,35,0.08); }}
            QPushButton:hover {{ border-color: {TEAL_DIM}; }}
        """)
        self._pin_chk.setText(("📌" if self._pin_chk.isChecked() else "☆") + "  Fissa in alto")
        self._pin_chk.toggled.connect(
            lambda c: self._pin_chk.setText(("📌" if c else "☆") + "  Fissa in alto")
        )
        vbox.addWidget(self._pin_chk)

        vbox.addStretch()

        # Bottoni
        bottom = QHBoxLayout()
        if self._bm:
            btn_del = QPushButton("Rimuovi")
            btn_del.setFixedHeight(34)
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: #FF6B6B;
                    border: 1px solid rgba(255,107,107,0.4); border-radius: 8px; padding: 0 14px; }}
                QPushButton:hover {{ background: rgba(255,107,107,0.12); }}
            """)
            btn_del.clicked.connect(lambda: self.done(2))
            bottom.addWidget(btn_del)
        bottom.addStretch()

        btn_cancel = QPushButton("Annulla")
        btn_cancel.setFixedHeight(34)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT_DIM};
                border: 1px solid #253852; border-radius: 8px; padding: 0 16px; }}
            QPushButton:hover {{ color: {TEXT_BRIGHT}; border-color: {TEAL_DIM}; }}
        """)
        btn_cancel.clicked.connect(self.reject)
        bottom.addWidget(btn_cancel)

        btn_save = QPushButton("Salva")
        btn_save.setFixedHeight(34)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        btn_save.setStyleSheet(f"""
            QPushButton {{ background: {TEAL}; color: {NAVY_DEEP};
                border: none; border-radius: 8px; padding: 0 20px; }}
            QPushButton:hover {{ background: #33DDFF; }}
        """)
        btn_save.clicked.connect(self.accept)
        bottom.addWidget(btn_save)
        vbox.addLayout(bottom)

    def _lbl(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; letter-spacing: 1px;")
        return l

    def _field_css(self) -> str:
        return f"""
            QLineEdit {{ background: {NAVY_LIGHT}; color: {TEXT_BRIGHT};
                border: 1.5px solid #253852; border-radius: 8px;
                padding: 0 12px; font-size: 13px; }}
            QLineEdit:focus {{ border-color: {TEAL}; }}
        """

    def _build_combo(self):
        from PyQt6.QtWidgets import QComboBox
        combo = QComboBox()
        combo.setFixedHeight(34)
        combo.setStyleSheet(f"""
            QComboBox {{ background: {NAVY_LIGHT}; color: {TEXT_BRIGHT};
                border: 1.5px solid #253852; border-radius: 8px;
                padding: 0 12px; font-size: 12px; }}
            QComboBox:focus {{ border-color: {TEAL}; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox QAbstractItemView {{
                background: {NAVY_MID}; color: {TEXT_BRIGHT};
                border: 1px solid #253852; selection-background-color: {TEAL};
                selection-color: {NAVY_DEEP};
            }}
        """)
        combo.addItem(UNCATEGORIZED)
        for c in self._mgr.categories:
            combo.addItem(c)
        current = (self._bm.category if self._bm else UNCATEGORIZED)
        idx = combo.findText(current)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        return combo

    def _new_category(self):
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Nuova categoria", "Nome categoria:")
        if ok and name.strip():
            if self._mgr.add_category(name.strip()):
                self._cat_combo.addItem(name.strip())
                self._cat_combo.setCurrentText(name.strip())

    def get_values(self):
        return (
            self._name.text().strip(),
            self._cat_combo.currentText(),
            self._pin_chk.isChecked(),
        )


# ── Bookmarks management dialog ───────────────────────────────────────────────
class BookmarksDialog(QDialog):
    navigate = pyqtSignal(str)   # url to open

    def __init__(self, bm_manager: BookmarkManager, parent=None):
        super().__init__(parent)
        self._mgr = bm_manager
        self._sel_category = "__pinned__"   # default: Fissati
        self.setWindowTitle("Preferiti — CalNav")
        self.resize(780, 520)
        self._build()

    def _build(self):
        self.setStyleSheet(f"background: {NAVY_MID}; color: {TEXT_BRIGHT};")
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left panel ────────────────────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(200)
        left.setStyleSheet(f"background: {NAVY_DEEP}; border-right: 1px solid #1C3050;")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 16, 0, 12)
        lv.setSpacing(2)

        hdr = QLabel("  PREFERITI")
        hdr.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px; letter-spacing: 2px; font-weight: bold; padding-bottom: 8px;")
        lv.addWidget(hdr)

        # Categoria speciali
        self._cat_btns: list = []
        self._btn_pinned = self._make_cat_btn("📌  Fissati", "__pinned__",
                                               self._mgr.count_pinned())
        self._btn_all    = self._make_cat_btn("📁  Tutti",   "__all__",
                                               self._mgr.count())
        lv.addWidget(self._btn_pinned)
        lv.addWidget(self._btn_all)

        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: #1C3050; margin: 6px 12px;")
        lv.addWidget(sep)

        # Categorie utente (scrollabile)
        self._cat_list_widget = QWidget()
        self._cat_list_layout = QVBoxLayout(self._cat_list_widget)
        self._cat_list_layout.setContentsMargins(0, 0, 0, 0)
        self._cat_list_layout.setSpacing(2)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(self._cat_list_widget)
        sc.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        lv.addWidget(sc, stretch=1)

        # Nuova categoria
        btn_new_cat = QPushButton("  + Nuova categoria")
        btn_new_cat.setFixedHeight(36)
        btn_new_cat.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_new_cat.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEAL};
                border: none; text-align: left; font-size: 12px; padding: 0 12px; }}
            QPushButton:hover {{ color: #33DDFF; }}
        """)
        btn_new_cat.clicked.connect(self._add_category)
        lv.addWidget(btn_new_cat)

        root.addWidget(left)

        # ── Right panel ───────────────────────────────────────────────────────
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(16, 16, 16, 12)
        rv.setSpacing(10)

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("Cerca nei preferiti…")
        self._search.setFixedHeight(36)
        self._search.setStyleSheet(f"""
            QLineEdit {{ background: {NAVY_LIGHT}; color: {TEXT_BRIGHT};
                border: 1.5px solid #253852; border-radius: 10px;
                padding: 0 14px; font-size: 12px; }}
            QLineEdit:focus {{ border-color: {TEAL}; }}
        """)
        self._search.textChanged.connect(self._refresh_bookmarks)
        rv.addWidget(self._search)

        # Bookmark list
        self._bm_widget = QWidget()
        self._bm_layout = QVBoxLayout(self._bm_widget)
        self._bm_layout.setContentsMargins(0, 0, 0, 0)
        self._bm_layout.setSpacing(5)
        sc2 = QScrollArea()
        sc2.setWidgetResizable(True)
        sc2.setWidget(self._bm_widget)
        sc2.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        rv.addWidget(sc2, stretch=1)

        # Close
        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_close = QPushButton("Chiudi")
        btn_close.setFixedHeight(34)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(f"""
            QPushButton {{ background: {TEAL}; color: {NAVY_DEEP}; border: none;
                border-radius: 8px; padding: 0 24px; font-weight: bold; }}
            QPushButton:hover {{ background: #33DDFF; }}
        """)
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        rv.addLayout(bottom)

        root.addWidget(right, stretch=1)

        self._refresh_categories()
        self._refresh_bookmarks()

    def _make_cat_btn(self, label: str, key: str, count: int) -> QPushButton:
        btn = QPushButton(f"{label}  ({count})")
        btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setCheckable(True)
        btn.setChecked(key == self._sel_category)
        btn._cat_key = key
        self._cat_btns.append(btn)
        btn.clicked.connect(lambda _, k=key: self._select_category(k))
        self._apply_cat_style(btn)
        return btn

    def _apply_cat_style(self, btn: QPushButton):
        active = getattr(btn, "_cat_key", "") == self._sel_category
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {"rgba(0,212,255,0.1)" if active else "transparent"};
                color: {TEAL if active else TEXT_BRIGHT};
                border: none; text-align: left; font-size: 12px;
                padding: 0 16px; border-left: 3px solid {TEAL if active else "transparent"};
            }}
            QPushButton:hover {{ background: rgba(0,212,255,0.06); }}
        """)

    def _select_category(self, key: str):
        self._sel_category = key
        for btn in self._cat_btns:
            self._apply_cat_style(btn)
        self._refresh_bookmarks()

    def _refresh_categories(self):
        # Aggiorna contatori speciali
        self._btn_pinned.setText(f"📌  Fissati  ({self._mgr.count_pinned()})")
        self._btn_all.setText(f"📁  Tutti  ({self._mgr.count()})")

        # Svuota categoria lista
        while self._cat_list_layout.count():
            item = self._cat_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cat_btns = [self._btn_pinned, self._btn_all]

        # Categorie utente
        if self._mgr.categories:
            for cat in self._mgr.categories:
                row = self._make_cat_row(cat)
                self._cat_list_layout.addWidget(row)

        # Senza categoria
        unc_count = self._mgr.count_uncategorized()
        if unc_count > 0:
            btn = self._make_cat_btn(f"📂  {UNCATEGORIZED}", UNCATEGORIZED, unc_count)
            self._cat_list_layout.addWidget(btn)

        self._cat_list_layout.addStretch()

    def _make_cat_row(self, cat: str) -> QWidget:
        row = QWidget()
        row.setFixedHeight(36)
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 4, 0)
        h.setSpacing(0)

        count = self._mgr.count_by_category(cat)
        btn = self._make_cat_btn(f"🗂  {cat}  ({count})", cat, count)
        h.addWidget(btn, stretch=1)

        btn_ren = QPushButton("✏")
        btn_ren.setFixedSize(24, 24)
        btn_ren.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ren.setStyleSheet(f"QPushButton {{ background: transparent; color: {TEXT_DIM}; border: none; font-size: 11px; }} QPushButton:hover {{ color: {TEAL}; }}")
        btn_ren.clicked.connect(lambda _, c=cat: self._rename_category(c))
        h.addWidget(btn_ren)

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(24, 24)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setStyleSheet(f"QPushButton {{ background: transparent; color: {TEXT_DIM}; border: none; font-size: 11px; }} QPushButton:hover {{ color: #FF6B6B; }}")
        btn_del.clicked.connect(lambda _, c=cat: self._delete_category(c))
        h.addWidget(btn_del)

        return row

    def _refresh_bookmarks(self):
        query = self._search.text().strip().lower()

        if self._sel_category == "__pinned__":
            bookmarks = self._mgr.get_pinned()
        elif self._sel_category == "__all__":
            bookmarks = self._mgr.get_all()
        elif self._sel_category == UNCATEGORIZED:
            bookmarks = self._mgr.get_uncategorized()
        else:
            bookmarks = self._mgr.get_by_category(self._sel_category)

        if query:
            bookmarks = [b for b in bookmarks
                         if query in b.title.lower() or query in b.url.lower()]

        while self._bm_layout.count():
            item = self._bm_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not bookmarks:
            empty = QLabel("Nessun preferito qui." if not query else "Nessun risultato.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color: {TEXT_DIM}; font-size: 13px; padding: 40px;")
            self._bm_layout.addWidget(empty)
        else:
            for bm in bookmarks:
                card = self._make_bm_card(bm)
                self._bm_layout.addWidget(card)

        self._bm_layout.addStretch()

    def _make_bm_card(self, bm: Bookmark) -> QWidget:
        card = QWidget()
        card.setFixedHeight(54)
        card.setStyleSheet(f"""
            QWidget {{
                background: {NAVY_DEEP}; border-radius: 10px;
                border: 1px solid {"#B87400" if bm.pinned else "#1C3050"};
            }}
        """)
        h = QHBoxLayout(card)
        h.setContentsMargins(10, 0, 10, 0)
        h.setSpacing(10)

        # Avatar sito
        av = QLabel(_url_initial(bm.url))
        av.setFixedSize(34, 34)
        av.setAlignment(Qt.AlignmentFlag.AlignCenter)
        av.setStyleSheet(
            f"background: {_url_color(bm.url)}; color: {NAVY_DEEP}; "
            f"border-radius: 17px; font-weight: bold; font-size: 14px;"
        )
        h.addWidget(av)

        # Testo
        info = QVBoxLayout()
        info.setSpacing(1)
        title_lbl = QLabel(bm.title)
        title_lbl.setStyleSheet(f"color: {TEXT_BRIGHT}; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        info.addWidget(title_lbl)
        url_lbl = QLabel(bm.url[:60] + "…" if len(bm.url) > 60 else bm.url)
        url_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; background: transparent; border: none;")
        info.addWidget(url_lbl)
        h.addLayout(info, stretch=1)

        # Pin indicator
        if bm.pinned:
            pin_lbl = QLabel("📌")
            pin_lbl.setStyleSheet("background: transparent; border: none; font-size: 13px;")
            h.addWidget(pin_lbl)

        # Azioni
        btn_open = QPushButton("Apri")
        btn_open.setFixedSize(50, 28)
        btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open.setStyleSheet(f"""
            QPushButton {{ background: rgba(0,212,255,0.12); color: {TEAL};
                border: none; border-radius: 6px; font-size: 11px; font-weight: bold; }}
            QPushButton:hover {{ background: rgba(0,212,255,0.25); }}
        """)
        btn_open.clicked.connect(lambda _, u=bm.url: self._open_url(u))
        h.addWidget(btn_open)

        btn_pin = QPushButton("📍" if bm.pinned else "☆")
        btn_pin.setFixedSize(28, 28)
        btn_pin.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_pin.setToolTip("Rimuovi pin" if bm.pinned else "Fissa in alto")
        btn_pin.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {AMBER if bm.pinned else TEXT_DIM};
                border: none; border-radius: 5px; font-size: 14px; }}
            QPushButton:hover {{ color: {AMBER}; }}
        """)
        btn_pin.clicked.connect(lambda _, b=bm: self._toggle_pin(b))
        h.addWidget(btn_pin)

        btn_edit = QPushButton("✏")
        btn_edit.setFixedSize(28, 28)
        btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_edit.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT_DIM};
                border: none; border-radius: 5px; font-size: 13px; }}
            QPushButton:hover {{ color: {TEAL}; }}
        """)
        btn_edit.clicked.connect(lambda _, b=bm: self._edit_bookmark(b))
        h.addWidget(btn_edit)

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(28, 28)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT_DIM};
                border: none; border-radius: 5px; font-size: 13px; }}
            QPushButton:hover {{ color: #FF6B6B; }}
        """)
        btn_del.clicked.connect(lambda _, b=bm: self._delete_bookmark(b))
        h.addWidget(btn_del)

        return card

    def _open_url(self, url: str):
        self.navigate.emit(url)
        self.accept()

    def _toggle_pin(self, bm: Bookmark):
        self._mgr.update(bm.id, pinned=not bm.pinned)
        self._refresh_categories()
        self._refresh_bookmarks()

    def _edit_bookmark(self, bm: Bookmark):
        dlg = AddBookmarkDialog(bm.url, bm.title, self._mgr, bookmark=bm, parent=self)
        result = dlg.exec()
        if result == QDialog.DialogCode.Accepted:
            title, cat, pinned = dlg.get_values()
            self._mgr.update(bm.id, title=title, category=cat, pinned=pinned)
        elif result == 2:
            self._mgr.remove(bm.id)
        self._refresh_categories()
        self._refresh_bookmarks()

    def _delete_bookmark(self, bm: Bookmark):
        self._mgr.remove(bm.id)
        self._refresh_categories()
        self._refresh_bookmarks()

    def _add_category(self):
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Nuova categoria", "Nome categoria:")
        if ok and name.strip():
            self._mgr.add_category(name.strip())
            self._refresh_categories()

    def _rename_category(self, cat: str):
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Rinomina categoria", "Nuovo nome:", text=cat)
        if ok and name.strip():
            self._mgr.rename_category(cat, name.strip())
            if self._sel_category == cat:
                self._sel_category = name.strip()
            self._refresh_categories()
            self._refresh_bookmarks()

    def _delete_category(self, cat: str):
        reply = QMessageBox.question(
            self, "Elimina categoria",
            f"Eliminare \"{cat}\"?\nI preferiti verranno spostati in \"{UNCATEGORIZED}\".",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._mgr.delete_category(cat)
            if self._sel_category == cat:
                self._sel_category = "__all__"
            self._refresh_categories()
            self._refresh_bookmarks()


def _show_pip(pip: "CalNavPiPWindow") -> None:
    """Show the PiP window (first time: bottom-right of screen) or raise it."""
    if not pip.isVisible():
        pip.show_centered_bottom_right()
    else:
        pip.raise_()
        pip.activateWindow()


# ── Floating always-on-top PiP window ────────────────────────────────────────
class CalNavPiPWindow(QWidget):
    """
    A frameless, always-on-top, draggable mini-player window.
    Lives completely outside the tab hierarchy — survives tab switches,
    browser minimisation, and window focus changes.

    Content strategy
    ────────────────
    • YouTube / YouTube Music  → uses the official /embed/ URL so cookies
      (login, quality prefs) are shared via the same QWebEngineProfile.
    • Any direct http/https URL that is not a blob:  → loaded in a plain
      <video> element filling the mini window.
    • blob: / MSE streams where we cannot get a transferable URL → the
      native browser requestPictureInPicture() is tried as a last resort.
    """

    _W, _H = 400, 240          # default size
    _TITLE_H = 26              # draggable title bar height

    # Emitted when the user closes the PiP window — CalNavWindow uses this to
    # un-mute the source tab that was silenced when PiP was opened.
    pip_closed = pyqtSignal()

    def __init__(self, profile: "QWebEngineProfile", parent=None):
        super().__init__(
            None,                           # no Qt parent → truly independent OS window
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumSize(240, 160)
        self.resize(self._W, self._H)
        self._drag_pos = None
        self._profile = profile
        self._build()

    def closeEvent(self, event):
        super().closeEvent(event)
        self.pip_closed.emit()

    def _build(self):
        self.setStyleSheet(f"""
            CalNavPiPWindow {{
                background: {NAVY_DEEP};
                border: 1px solid {TEAL_DIM};
                border-radius: 8px;
            }}
        """)
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # ── Title / drag bar ──────────────────────────────────────────────
        bar = QWidget()
        bar.setFixedHeight(self._TITLE_H)
        bar.setStyleSheet(
            f"background: {NAVY_MID}; border-radius: 8px 8px 0 0;"
        )
        bh = QHBoxLayout(bar)
        bh.setContentsMargins(10, 0, 6, 0)
        bh.setSpacing(6)

        lbl_icon = QLabel("⧉")
        lbl_icon.setStyleSheet(f"color: {TEAL}; font-size: 12px;")
        bh.addWidget(lbl_icon)

        self._lbl_title = QLabel("CalNav PiP")
        self._lbl_title.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 10px;"
        )
        bh.addWidget(self._lbl_title, stretch=1)

        btn_close = QPushButton("×")
        btn_close.setFixedSize(20, 20)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT_DIM};
                           border: none; font-size: 14px; }}
            QPushButton:hover {{ color: #FF6B6B; }}
        """)
        btn_close.clicked.connect(self.close)
        bh.addWidget(btn_close)
        vbox.addWidget(bar)

        # ── Video view ────────────────────────────────────────────────────
        self._view = QWebEngineView()
        page = QWebEnginePage(self._profile, self._view)
        self._view.setPage(page)
        self._view.setStyleSheet("background: black;")
        vbox.addWidget(self._view, stretch=1)

    # ── Dragging ──────────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ── Content loading ───────────────────────────────────────────────────────
    def play_direct(self, src: str, current_time: float, title: str = ""):
        """Load a raw video/audio URL in a plain <video> element."""
        t = max(0.0, float(current_time))
        html = f"""<!DOCTYPE html>
<html><body style="margin:0;background:#000;overflow:hidden">
<video id="v" src="{src}"
       style="width:100%;height:100vh;object-fit:contain"
       autoplay></video>
<script>
  var v = document.getElementById('v');
  v.currentTime = {t:.3f};
  v.play().catch(function(){{}});
</script>
</body></html>"""
        self._view.setHtml(html, QUrl(src))
        self._set_title(title)

    def play_url(self, url: str, title: str = ""):
        """Navigate to an arbitrary URL inside the mini view."""
        self._view.load(QUrl(url))
        self._set_title(title)

    # JavaScript injected after the YouTube watch page loads.
    # Hides header / sidebar / comments and fixes the player to fill the window.
    _YT_PIP_JS = """
(function() {
    if (document.getElementById('__cn_pip_style')) return;
    var s = document.createElement('style');
    s.id = '__cn_pip_style';
    s.textContent =
        '#masthead-container, ytd-mini-guide-renderer, #guide, tp-yt-app-drawer,' +
        'ytd-watch-metadata, ytd-video-primary-info-renderer,' +
        'ytd-video-secondary-info-renderer, #secondary, #related, #above-the-fold,' +
        '#comments, ytd-item-section-renderer, .ytd-watch-flexy[is-two-columns_],' +
        '#chat-container, ytd-live-chat-frame' +
        '{ display: none !important; }' +
        'body, html { overflow: hidden !important; background: #000 !important; }' +
        '#primary, #primary-inner { padding: 0 !important; margin: 0 !important; }' +
        '#movie_player {' +
        '  width: 100vw !important; height: 100vh !important;' +
        '  position: fixed !important; top: 0 !important; left: 0 !important;' +
        '  z-index: 9999 !important;' +
        '}';
    document.head.appendChild(s);
})();
"""

    def play_youtube(self, video_id: str, start_time: float, title: str = ""):
        """Load youtube.com/watch (not embed) and strip the page UI via CSS.

        Using the full watch URL avoids embed error 153 entirely — the video
        plays exactly as it does in the main browser tab.  The injected CSS
        hides header / sidebar / comments and fixes the player to fill the
        PiP window.
        """
        url = (
            f"https://www.youtube.com/watch?v={video_id}"
            f"&t={int(max(0, start_time))}s"
        )
        # Inject CSS after the SPA has rendered (loadFinished fires on the
        # initial HTML load, before the SPA JS populates the DOM — wait 900 ms)
        def _on_loaded(ok):
            try:
                self._view.loadFinished.disconnect(_on_loaded)
            except Exception:
                pass
            QTimer.singleShot(900, lambda: self._view.page().runJavaScript(self._YT_PIP_JS))
        self._view.loadFinished.connect(_on_loaded)
        self._view.load(QUrl(url))
        self._set_title(title or "YouTube PiP")

    def _set_title(self, title: str):
        t = title[:40] + "…" if len(title) > 40 else title
        self._lbl_title.setText(t or "CalNav PiP")

    def show_centered_bottom_right(self):
        """First-time positioning: bottom-right of the primary screen."""
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.right()  - self.width()  - 24,
            screen.bottom() - self.height() - 48,
        )
        self.show()
        self.raise_()


# ── Persistent media control bar ─────────────────────────────────────────────
class CalNavMediaBar(QWidget):
    """
    A slim strip shown at the bottom of the browser whenever audio or video
    is playing in the active tab.  Persists across tab switches (clears and
    re-fills when the new tab reports its media state).

    Unique features
    ───────────────
    • Play / Pause, ±10 s seek buttons and a draggable seek slider
    • Volume wheel
    • ⧉ PiP button — requests Picture-in-Picture via the Web API
    • Small pulsing dot painted on the tab bar for tabs with active media
      (implemented in CalNavTabBar._paint_group_overlays via a resolver)
    """

    play_pause_requested = pyqtSignal()
    seek_requested       = pyqtSignal(float)   # absolute time in seconds
    seek_rel_requested   = pyqtSignal(float)   # relative offset in seconds
    volume_requested     = pyqtSignal(float)   # 0.0 – 1.0
    pip_requested        = pyqtSignal()

    _H = 48   # bar height in pixels

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self._H)
        self._state: dict = {}
        self._seeking = False
        self._build()
        self.hide()

    # ── UI construction ───────────────────────────────────────────────────────
    def retheme(self):
        self.setStyleSheet(f"""
            CalNavMediaBar {{
                background: {NAVY_MID};
                border-top: 2px solid {TEAL_DIM};
            }}
        """)

    def _build(self):
        self.setStyleSheet(f"""
            CalNavMediaBar {{
                background: {NAVY_MID};
                border-top: 2px solid {TEAL_DIM};
            }}
        """)
        h = QHBoxLayout(self)
        h.setContentsMargins(16, 0, 12, 0)
        h.setSpacing(8)

        # Type icon  (📺 / 🎵)
        self._lbl_icon = QLabel("🎵")
        self._lbl_icon.setFixedWidth(20)
        self._lbl_icon.setStyleSheet("font-size: 15px;")
        h.addWidget(self._lbl_icon)

        # Title
        self._lbl_title = QLabel("—")
        self._lbl_title.setStyleSheet(
            f"color: {TEXT_BRIGHT}; font-size: 11px;"
        )
        self._lbl_title.setMaximumWidth(200)
        self._lbl_title.setTextFormat(Qt.TextFormat.PlainText)
        h.addWidget(self._lbl_title)

        h.addSpacing(4)

        # ← −10 s
        self._btn_rew = self._mk_btn("⏪", "−10 s")
        self._btn_rew.clicked.connect(lambda: self.seek_rel_requested.emit(-10.0))
        h.addWidget(self._btn_rew)

        # ▶ / ⏸
        self._btn_pp = self._mk_btn("▶", "Play / Pausa  (Ctrl+Shift+Space)", accent=True)
        self._btn_pp.setFixedSize(36, 36)
        self._btn_pp.clicked.connect(self.play_pause_requested)
        h.addWidget(self._btn_pp)

        # +10 s →
        self._btn_fwd = self._mk_btn("⏩", "+10 s")
        self._btn_fwd.clicked.connect(lambda: self.seek_rel_requested.emit(10.0))
        h.addWidget(self._btn_fwd)

        h.addSpacing(6)

        # Seek bar
        self._seek = QSlider(Qt.Orientation.Horizontal)
        self._seek.setRange(0, 10000)
        self._seek.setFixedHeight(18)
        self._seek.setCursor(Qt.CursorShape.PointingHandCursor)
        self._seek.setStyleSheet(self._slider_css(TEAL, TEAL_DIM))
        self._seek.sliderPressed.connect(lambda: setattr(self, '_seeking', True))
        self._seek.sliderReleased.connect(self._on_seek_released)
        h.addWidget(self._seek, stretch=1)

        # Time label
        self._lbl_time = QLabel("0:00 / 0:00")
        self._lbl_time.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 10px; min-width: 76px;"
        )
        h.addWidget(self._lbl_time)

        h.addSpacing(4)

        # 🔊 Volume slider
        lbl_vol = QLabel("🔊")
        lbl_vol.setStyleSheet("font-size: 13px;")
        h.addWidget(lbl_vol)

        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 100)
        self._vol.setValue(100)
        self._vol.setFixedSize(72, 18)
        self._vol.setCursor(Qt.CursorShape.PointingHandCursor)
        self._vol.setStyleSheet(self._slider_css(TEAL_DIM, "#1A3A5C"))
        self._vol.valueChanged.connect(
            lambda v: self.volume_requested.emit(v / 100.0)
        )
        h.addWidget(self._vol)

        h.addSpacing(6)

        # ⧉ PiP
        self._btn_pip = self._mk_btn("⧉ PiP", "Picture-in-Picture  Ctrl+Shift+V")
        self._btn_pip.setFixedWidth(58)
        self._btn_pip.clicked.connect(self.pip_requested)
        h.addWidget(self._btn_pip)

        # × close
        btn_x = QPushButton("×")
        btn_x.setFixedSize(22, 22)
        btn_x.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_x.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT_DIM};
                           border: none; font-size: 15px; }}
            QPushButton:hover {{ color: {TEXT_BRIGHT}; }}
        """)
        btn_x.clicked.connect(self.hide)
        h.addWidget(btn_x)

    @staticmethod
    def _mk_btn(text: str, tip: str = "", accent: bool = False) -> QPushButton:
        bg = TEAL if accent else NAVY_LIGHT
        fg = NAVY_DEEP if accent else TEXT_BRIGHT
        hv = "#33DDFF" if accent else "#253852"
        b = QPushButton(text)
        b.setFixedSize(30, 30)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if tip:
            b.setToolTip(tip)
        b.setStyleSheet(f"""
            QPushButton {{
                background: {bg}; color: {fg};
                border: none; border-radius: 6px; font-size: 12px;
            }}
            QPushButton:hover {{ background: {hv}; }}
        """)
        return b

    @staticmethod
    def _slider_css(fill: str, track: str) -> str:
        return f"""
            QSlider::groove:horizontal {{
                background: {track}; height: 4px; border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {fill}; height: 4px; border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: white; width: 10px; height: 10px;
                margin: -3px 0; border-radius: 5px;
            }}
        """

    # ── State update ─────────────────────────────────────────────────────────
    def update_state(self, state: dict):
        """Called whenever the active tab reports a new media state."""
        self._state = state

        if not state.get("hasMedia"):
            self.hide()
            return

        if not self.isVisible():
            self.show()

        paused   = state.get("paused", True)
        is_video = state.get("isVideo", False)
        title    = state.get("title", "")
        current  = float(state.get("currentTime", 0))
        duration = float(state.get("duration", 0))
        volume   = float(state.get("volume", 1))
        muted    = bool(state.get("muted", False))

        self._lbl_icon.setText("📺" if is_video else "🎵")

        # Truncate title
        max_chars = 36
        if len(title) > max_chars:
            title = title[: max_chars - 1] + "…"
        self._lbl_title.setText(title)

        self._btn_pp.setText("⏸" if not paused else "▶")

        # Update seek without triggering seek_requested signal
        if not self._seeking and duration > 0:
            self._seek.blockSignals(True)
            self._seek.setValue(int((current / duration) * 10000))
            self._seek.blockSignals(False)

        def _fmt(s: float) -> str:
            s = int(s)
            return f"{s // 60}:{s % 60:02d}"

        self._lbl_time.setText(f"{_fmt(current)} / {_fmt(duration)}")

        # Volume
        self._vol.blockSignals(True)
        self._vol.setValue(0 if muted else int(volume * 100))
        self._vol.blockSignals(False)

        # PiP button visible only for video
        self._btn_pip.setVisible(is_video)

    def _on_seek_released(self):
        self._seeking = False
        duration = float(self._state.get("duration", 0))
        if duration > 0:
            t = (self._seek.value() / 10000.0) * duration
            self.seek_requested.emit(t)


# ── Update notification bar ──────────────────────────────────────────────────
class UpdateBar(QWidget):
    """Notification bar shown when a newer CalNav version is available."""

    download_clicked = pyqtSignal()   # caller connects this to open the releases page

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self.hide()

    def _build(self):
        self.setFixedHeight(40)
        self.setStyleSheet(
            f"background: #0A2A0A; border-bottom: 1px solid #51CF66;"
        )
        h = QHBoxLayout(self)
        h.setContentsMargins(18, 0, 18, 0)
        h.setSpacing(12)

        icon = QLabel("[+]")
        icon.setStyleSheet("color: #51CF66; font-size: 13px; font-weight: bold;")
        h.addWidget(icon)

        self._msg = QLabel()
        self._msg.setStyleSheet(f"color: {TEXT_BRIGHT}; font-size: 12px;")
        h.addWidget(self._msg, stretch=1)

        btn_dl = QPushButton("Scarica")
        btn_dl.setFixedSize(80, 28)
        btn_dl.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_dl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        btn_dl.setStyleSheet("""
            QPushButton { background: #51CF66; color: #07111F; border: none; border-radius: 6px; }
            QPushButton:hover { background: #69DB7C; }
        """)
        btn_dl.clicked.connect(self._on_download)
        h.addWidget(btn_dl)

        btn_x = QPushButton("X")
        btn_x.setFixedSize(28, 28)
        btn_x.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_x.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT_DIM}; border: none; font-size: 11px; border-radius: 5px; }}
            QPushButton:hover {{ color: {TEXT_BRIGHT}; }}
        """)
        btn_x.clicked.connect(self.hide)
        h.addWidget(btn_x)

    def retheme(self):
        self._msg.setStyleSheet(f"color: {TEXT_BRIGHT}; font-size: 12px;")

    def show_update(self, version: str):
        self._msg.setText(
            f"Disponibile CalNav {version}  —  stai usando la {__version__}"
        )
        self.show()

    def _on_download(self):
        self.download_clicked.emit()
        self.hide()


# ── Update checker ────────────────────────────────────────────────────────────
class UpdateChecker(QObject):
    update_available = pyqtSignal(str)   # nuova versione

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)

    def check(self):
        req = QNetworkRequest(QUrl(GITHUB_API_URL))
        req.setRawHeader(b"User-Agent", b"CalNav-Browser-UpdateChecker")
        req.setTransferTimeout(8000)
        reply = self._nam.get(req)
        reply.finished.connect(lambda: self._on_reply(reply))

    def _on_reply(self, reply):
        try:
            from PyQt6.QtNetwork import QNetworkReply
            if reply.error() != QNetworkReply.NetworkError.NoError:
                return
            data = json.loads(bytes(reply.readAll()).decode())
            tag = data.get("tag_name", "").lstrip("vV").strip()
            if tag and self._is_newer(tag, __version__):
                self.update_available.emit(tag)
        except Exception:
            pass
        finally:
            reply.deleteLater()

    @staticmethod
    def _is_newer(remote: str, current: str) -> bool:
        """Return True if *remote* version is strictly greater than *current*.

        Handles pre-release suffixes (e.g. "1.1.0-alpha", "1.2.0-rc1") by
        stripping everything after the first non-numeric character in each
        dotted component before comparing.
        """
        import re
        def parse(v: str):
            nums = []
            for part in v.strip().split("."):
                m = re.match(r"(\d+)", part)
                nums.append(int(m.group(1)) if m else 0)
            return tuple(nums)
        try:
            return parse(remote) > parse(current)
        except Exception:
            return False


# ── Settings dialog ───────────────────────────────────────────────────────────
class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self._settings = dict(settings)
        self.setWindowTitle("Impostazioni — CalNav")
        self.setFixedSize(520, 440)
        self._build()

    def _build(self):
        self.setStyleSheet(f"background: {NAVY_MID}; color: {TEXT_BRIGHT};")
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(28, 24, 28, 16)
        vbox.setSpacing(0)

        # Title
        hdr = QLabel("Impostazioni")
        hdr.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {TEAL}; margin-bottom: 18px;")
        vbox.addWidget(hdr)

        # ── Navigazione ──────────────────────────────────────────────────────
        self._add_section(vbox, "Navigazione")

        row_home = QHBoxLayout()
        lbl = QLabel("Homepage:")
        lbl.setFixedWidth(110)
        lbl.setStyleSheet(f"color: {TEXT_BRIGHT}; font-size: 13px;")
        row_home.addWidget(lbl)

        self._home_edit = QLineEdit(self._settings.get("homepage", HOME_URL))
        self._home_edit.setFixedHeight(34)
        self._home_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {NAVY_LIGHT}; color: {TEXT_BRIGHT};
                border: 1.5px solid #253852; border-radius: 8px;
                padding: 0 12px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {TEAL}; }}
        """)
        row_home.addWidget(self._home_edit, stretch=1)

        btn_cur = QPushButton("Usa pagina attuale")
        btn_cur.setFixedHeight(34)
        btn_cur.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cur.setStyleSheet(f"""
            QPushButton {{ background: rgba(0,212,255,0.12); color: {TEAL}; border: 1px solid {TEAL_DIM}; border-radius: 8px; padding: 0 10px; font-size: 11px; }}
            QPushButton:hover {{ background: rgba(0,212,255,0.22); }}
        """)
        btn_cur.clicked.connect(self._use_current_url)
        row_home.addWidget(btn_cur)
        vbox.addLayout(row_home)

        vbox.addSpacing(20)

        # ── Informazioni ─────────────────────────────────────────────────────
        self._add_section(vbox, "Informazioni")

        try:
            from PyQt6.QtWebEngineCore import qWebEngineChromiumVersion
            chromium_ver = qWebEngineChromiumVersion()
        except Exception:
            chromium_ver = "n/d"

        info_items = [
            ("Versione CalNav",  __version__),
            ("PyQt6",            PYQT_VERSION_STR),
            ("Qt",               QT_VERSION_STR),
            ("Chromium",         chromium_ver),
            ("Repository",       GITHUB_RELEASES_URL),
            ("Dati profili",     str(DATA_DIR)),
        ]
        for label, value in info_items:
            row = QHBoxLayout()
            lbl_k = QLabel(label + ":")
            lbl_k.setFixedWidth(110)
            lbl_k.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
            row.addWidget(lbl_k)

            if value.startswith("https://"):
                lbl_v = QLabel(f'<a href="{value}" style="color:{TEAL};">{value}</a>')
                lbl_v.setOpenExternalLinks(True)
            else:
                lbl_v = QLabel(value)
                lbl_v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl_v.setStyleSheet("font-size: 12px;")
            row.addWidget(lbl_v, stretch=1)
            vbox.addLayout(row)
            vbox.addSpacing(4)

        vbox.addStretch()

        # Bottom buttons
        bottom = QHBoxLayout()
        bottom.addStretch()

        btn_cancel = QPushButton("Annulla")
        btn_cancel.setFixedHeight(36)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT_DIM}; border: 1px solid #253852; border-radius: 8px; padding: 0 20px; }}
            QPushButton:hover {{ color: {TEXT_BRIGHT}; border-color: {TEAL_DIM}; }}
        """)
        btn_cancel.clicked.connect(self.reject)
        bottom.addWidget(btn_cancel)

        btn_save = QPushButton("Salva")
        btn_save.setFixedHeight(36)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        btn_save.setStyleSheet(f"""
            QPushButton {{ background: {TEAL}; color: {NAVY_DEEP}; border: none; border-radius: 8px; padding: 0 24px; }}
            QPushButton:hover {{ background: #33DDFF; }}
        """)
        btn_save.clicked.connect(self._on_save)
        bottom.addWidget(btn_save)
        vbox.addLayout(bottom)

    def _add_section(self, layout, title: str):
        lbl = QLabel(title.upper())
        lbl.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 10px; letter-spacing: 2px; "
            f"font-weight: bold; margin-bottom: 8px;"
        )
        layout.addWidget(lbl)

    def _use_current_url(self):
        parent = self.parent()
        if parent and hasattr(parent, "address_bar"):
            url = parent.address_bar.text().strip()
            if url:
                self._home_edit.setText(url)

    def _on_save(self):
        url = self._home_edit.text().strip()
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        self._settings["homepage"] = url or HOME_URL
        self.accept()

    def get_settings(self) -> dict:
        return self._settings


# ── Custom tab bar with group colours and collapse support ────────────────────
class CalNavTabBar(QTabBar):
    """
    Custom QTabBar:
    • Group header tabs ("linguette") painted as solid coloured chips with white text.
      Clicking them emits group_header_clicked — they are NEVER selected as current tab,
      so the web view underneath never goes dark.
    • Regular group tabs get a translucent tint + 4 px bottom stripe.
    • A special pseudo-tab with data == _PLUS_DATA acts as the "+" new-tab button.
      It is always kept at the end of the tab bar by CalNavWindow._ensure_plus_tab().
      Clicking it emits new_tab_requested without ever becoming the current tab.
    • Per-tab close buttons are added separately via setTabButton().
    """

    # Emits group_id when user left-clicks a linguetta header tab
    group_header_clicked = pyqtSignal(str)
    # Emits when "+" pseudo-tab is clicked
    new_tab_requested = pyqtSignal()
    # Emits after a drag-and-drop reorder is FULLY COMPLETE (mouse released).
    # Safe moment to call removeTab/insertTab without corrupting Qt's drag state.
    tabs_reordered = pyqtSignal()

    # tabData prefix for group-header "linguetta" tabs
    _HEADER_PREFIX = "__hdr__"
    # tabData sentinel for the "+" pseudo-tab
    _PLUS_DATA = "__plus__"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color_resolver = lambda gid: None   # group_id → str color | None
        self._media_resolver  = lambda idx: False  # tab index → bool (media playing)
        self._drag_in_progress = False             # True while user holds mouse during drag
        # Track whether any tab moved during the current drag gesture
        self.tabMoved.connect(self._on_tab_moved_internal)
        self.setDrawBase(False)
        self.setElideMode(Qt.TextElideMode.ElideRight)
        self.setExpanding(False)

    def set_color_resolver(self, fn):
        self._color_resolver = fn

    def set_media_resolver(self, fn):
        """fn(index: int) -> bool  — returns True if that tab has active media."""
        self._media_resolver = fn

    def _on_tab_moved_internal(self, _from: int, _to: int):
        """Record that a drag-reorder happened; actual rebuild waits for mouseRelease."""
        self._drag_in_progress = True

    # ── data helpers ─────────────────────────────────────────────────────────
    @classmethod
    def header_data(cls, group_id: str) -> str:
        return cls._HEADER_PREFIX + group_id

    @classmethod
    def is_header_data(cls, data) -> bool:
        return isinstance(data, str) and data.startswith(cls._HEADER_PREFIX)

    @classmethod
    def is_plus_data(cls, data) -> bool:
        return data == cls._PLUS_DATA

    @classmethod
    def real_gid(cls, data: str) -> Optional[str]:
        """Strip any prefix and return the bare group_id (or None if data is falsy)."""
        if not data:
            return None
        if cls.is_header_data(data):
            return data[len(cls._HEADER_PREFIX):]
        return data

    # ── size hints: make "+" pseudo-tab narrow ───────────────────────────────
    def tabSizeHint(self, index: int) -> QSize:
        if self.is_plus_data(self.tabData(index)):
            return QSize(36, super().tabSizeHint(index).height())
        return super().tabSizeHint(index)

    def minimumTabSizeHint(self, index: int) -> QSize:
        if self.is_plus_data(self.tabData(index)):
            return QSize(36, super().minimumTabSizeHint(index).height())
        return super().minimumTabSizeHint(index)

    # ── mouse ─────────────────────────────────────────────────────────────────
    def mouseReleaseEvent(self, event):
        """After a drag-and-drop reorder, emit tabs_reordered so the caller can
        rebuild header positions safely — AFTER Qt has fully committed the drag."""
        super().mouseReleaseEvent(event)
        if self._drag_in_progress:
            self._drag_in_progress = False
            # Defer one more tick so Qt finishes any post-release internal cleanup
            QTimer.singleShot(0, self.tabs_reordered.emit)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self.tabAt(event.pos())
            if idx >= 0:
                data = self.tabData(idx)
                if self.is_header_data(data):
                    gid = self.real_gid(data)
                    if gid:
                        self.group_header_clicked.emit(gid)
                    return          # do NOT call super — header stays unselected
                if self.is_plus_data(data):
                    self.new_tab_requested.emit()
                    return          # do NOT call super — "+" stays unselected
        super().mousePressEvent(event)

    # ── painting ─────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            self._paint_group_overlays(painter)
        finally:
            painter.end()

    def _paint_group_overlays(self, painter: QPainter):
        for idx in range(self.count()):
            raw = self.tabData(idx)

            # ── Tiny "▶" media-playing dot in the top-right of real tabs ──
            # NOTE: raw is None for un-grouped tabs — is_header_data/is_plus_data
            # both return False for None, so the raw-guard is intentionally absent.
            if (not self.is_header_data(raw) and not self.is_plus_data(raw)
                    and self._media_resolver(idx)):
                rect = self.tabRect(idx)
                dot_r = 5
                cx = rect.right() - dot_r - 4
                cy = rect.top()   + dot_r + 4
                painter.save()
                painter.setBrush(QColor(TEAL))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(cx - dot_r, cy - dot_r, dot_r * 2, dot_r * 2)
                painter.restore()

            if not raw:
                continue

            # ── "+" pseudo-tab ────────────────────────────────────────────
            if self.is_plus_data(raw):
                rect = self.tabRect(idx)
                # Erase Qt's default tab background by painting over it
                bg = QColor(NAVY_DEEP)
                painter.fillRect(rect, bg)
                # Draw the "+" symbol in teal
                painter.setPen(QColor(TEAL))
                f = self.font()
                f.setBold(True)
                f.setPointSize(f.pointSize() + 3)
                painter.setFont(f)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "+")
                continue

            is_header = self.is_header_data(raw)
            gid = self.real_gid(raw)
            color = self._color_resolver(gid)
            if not color:
                continue
            rect = self.tabRect(idx)
            qc = QColor(color)

            if is_header:
                # ── Group "linguetta": solid colored chip with white label ──
                chip = rect.adjusted(2, 3, -2, -3)
                painter.fillRect(chip, qc)
                painter.setPen(QColor("white"))
                f = self.font()
                f.setBold(True)
                f.setPointSize(max(8, f.pointSize() - 1))
                painter.setFont(f)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.tabText(idx))
            else:
                # ── Regular group tab: translucent tint + 4 px bottom stripe ──
                tint = QColor(qc)
                tint.setAlpha(45)
                painter.fillRect(rect.adjusted(1, 1, -1, 0), tint)
                painter.fillRect(rect.x() + 2, rect.bottom() - 3,
                                 rect.width() - 4, 4, qc)


# ── Group create / edit dialog ────────────────────────────────────────────────
class GroupDialog(QDialog):
    """Create or edit a tab group (name + color via color picker)."""

    def __init__(self, group: Optional[TabGroup] = None, parent=None):
        super().__init__(parent)
        self._group = group
        self.selected_color = group.color if group else PROFILE_COLORS[2]
        self.setWindowTitle("Modifica gruppo" if group else "Nuovo gruppo schede")
        self.setFixedSize(380, 210)
        self._build()

    def _build(self):
        self.setStyleSheet(f"background: {NAVY_MID}; color: {TEXT_BRIGHT};")
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(24, 20, 24, 16)
        vbox.setSpacing(12)

        lbl = QLabel("Nome gruppo:")
        lbl.setStyleSheet(f"color: {TEXT_BRIGHT}; font-size: 13px;")
        vbox.addWidget(lbl)

        self.name_edit = QLineEdit(self._group.name if self._group else "")
        self.name_edit.setPlaceholderText("es. Lavoro, Ricerca, Personale…")
        self.name_edit.setFixedHeight(36)
        self.name_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {NAVY_LIGHT}; color: {TEXT_BRIGHT};
                border: 1.5px solid #253852; border-radius: 8px;
                padding: 0 12px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {TEAL}; }}
        """)
        vbox.addWidget(self.name_edit)

        color_row = QHBoxLayout()
        color_row.setSpacing(12)
        color_lbl = QLabel("Colore:")
        color_lbl.setStyleSheet(f"color: {TEXT_BRIGHT}; font-size: 13px;")
        color_row.addWidget(color_lbl)

        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(40, 36)
        self._color_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._color_btn.setToolTip("Scegli colore…")
        self._refresh_color_btn()
        self._color_btn.clicked.connect(self._pick_color)
        color_row.addWidget(self._color_btn)
        color_row.addStretch()
        vbox.addLayout(color_row)

        vbox.addStretch()

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.setStyleSheet(f"""
            QPushButton {{
                background: {TEAL}; color: {NAVY_DEEP};
                border: none; border-radius: 6px;
                padding: 6px 18px; font-weight: bold; min-width: 80px;
            }}
            QPushButton:hover {{ background: #33DDFF; }}
            QPushButton[text="Cancel"] {{ background: transparent; color: {TEXT_DIM};
                border: 1px solid #253852; }}
        """)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        vbox.addWidget(btns)

    def _refresh_color_btn(self):
        self._color_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self.selected_color};
                border-radius: 8px;
                border: 2px solid rgba(255,255,255,0.25);
            }}
            QPushButton:hover {{ border-color: white; }}
        """)

    def _pick_color(self):
        color = QColorDialog.getColor(
            QColor(self.selected_color), self, "Scegli il colore del gruppo"
        )
        if color.isValid():
            self.selected_color = color.name()
            self._refresh_color_btn()

    def get_values(self):
        return self.name_edit.text().strip(), self.selected_color


# ── Main window ───────────────────────────────────────────────────────────────
class CalNavWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._ie_mode = False
        self.setWindowTitle("CalNav")
        self.setMinimumSize(900, 600)
        self.resize(1280, 820)

        self._settings = _load_settings()
        set_theme(self._settings.get("theme", "dark"))
        self.profile_manager = ProfileManager()
        self._groups: List[TabGroup] = []        # active tab groups
        self._collapsed_groups: set = set()      # group_ids currently collapsed
        # Media state: maps QWebEngineView → latest reported state dict
        self._media_states: dict = {}            # view -> {hasMedia, paused, ...}
        self._pip_window: Optional["CalNavPiPWindow"] = None  # floating mini-player
        self._pip_source_view: Optional[QWebEngineView] = None  # tab muted when PiP opened

        self._build_ui()   # builds tab widget + toolbar (no tabs yet)

        prof = self.profile_manager.current
        self.password_manager = PasswordManager(prof.passwords_file, prof.name)
        self.bookmark_manager = BookmarkManager(prof.bookmarks_file)

        # Shared bridge + channel (all tabs share the same bridge)
        self._bridge = CalNavBridge(self)
        self._bridge.save_password_requested.connect(self._on_save_request)
        self._bridge.media_state_changed.connect(self._on_media_state)
        self._channel = QWebChannel(self)
        self._channel.registerObject("calnav_bridge", self._bridge)

        # Wire the tab-bar media resolver (shows dot on tabs with active media)
        self._tab_bar.set_media_resolver(self._tab_index_has_media)

        # Named web profile (shared by all tabs)
        self._web_profile = QWebEngineProfile(prof.name, self)
        self._apply_profile_settings()

        self._setup_shortcuts()
        self._update_profile_button()
        self._restore_session()   # opens tabs from saved session (or homepage)

        # Controlla aggiornamenti 5 secondi dopo l'avvio
        self._updater = UpdateChecker(self)
        self._updater.update_available.connect(self._update_bar.show_update)
        QTimer.singleShot(5000, self._updater.check)

    # ── Current tab accessor ──────────────────────────────────────────────────
    @property
    def webview(self) -> Optional[QWebEngineView]:
        w = self._tab_widget.currentWidget()
        return w if isinstance(w, QWebEngineView) else None

    # ── Profile / password helpers ────────────────────────────────────────────
    @staticmethod
    def _build_chrome_ua() -> str:
        """Return a UA string identical to real Chrome for the actual Chromium
        version bundled with this Qt build.

        QtWebEngine's default UA looks like:
          Mozilla/5.0 (...) AppleWebKit/537.36 (KHTML, like Gecko)
          QtWebEngine/6.8.1 Chrome/124.0.6367.208 Safari/537.36

        We keep everything except the 'QtWebEngine/X.X.X' token.  This means
        the Chrome version number is always accurate — sites that do JS
        feature-detection (Twitch, Netflix) won't see mismatches.
        """
        raw = QWebEngineProfile.defaultProfile().httpUserAgent()
        # Strip the QtWebEngine/x.x.x token (with surrounding spaces)
        ua = re.sub(r"\s*QtWebEngine/[\d.]+\s*", " ", raw).strip()
        return ua

    def _apply_profile_settings(self):
        p = self._web_profile
        p.setHttpUserAgent(IE_UA if self._ie_mode else self._build_chrome_ua())

        s = p.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        # ── Media: allow autoplay + full codec/MSE support ───────────────────
        s.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.ScreenCaptureEnabled, True)
        # NOTE: WebRTCPublicInterfacesOnly is intentionally NOT set — setting it
        # to True blocks Twitch's low-latency WebRTC streams.
        # ─────────────────────────────────────────────────────────────────────
        s.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, self._ie_mode
        )
        s.setAttribute(
            QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, self._ie_mode
        )
        s.setAttribute(
            QWebEngineSettings.WebAttribute.AllowGeolocationOnInsecureOrigins,
            self._ie_mode,
        )

        scripts = p.scripts()
        for name in ("calnav_ie_shims", "calnav_qwebchannel", "calnav_forms",
                     "calnav_media", "calnav_chrome_compat"):
            for old in scripts.find(name):
                scripts.remove(old)

        # ── window.chrome shim — must run before any page JS (DocumentCreation)
        chrome_script = QWebEngineScript()
        chrome_script.setName("calnav_chrome_compat")
        chrome_script.setSourceCode(CHROME_COMPAT_JS)
        chrome_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        chrome_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        scripts.insert(chrome_script)

        qwc_js = _load_qwebchannel_js()
        if qwc_js:
            qwc_script = QWebEngineScript()
            qwc_script.setName("calnav_qwebchannel")
            qwc_script.setSourceCode(qwc_js)
            qwc_script.setInjectionPoint(
                QWebEngineScript.InjectionPoint.DocumentCreation
            )
            qwc_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            scripts.insert(qwc_script)

        form_script = QWebEngineScript()
        form_script.setName("calnav_forms")
        form_script.setSourceCode(DETECT_FORMS_JS)
        form_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        form_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        scripts.insert(form_script)

        # ── Media detection & control script ─────────────────────────────────
        media_script = QWebEngineScript()
        media_script.setName("calnav_media")
        media_script.setSourceCode(MEDIA_JS)
        media_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        media_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        scripts.insert(media_script)

        if self._ie_mode:
            shim = QWebEngineScript()
            shim.setName("calnav_ie_shims")
            shim.setSourceCode(IE_SHIMS_JS)
            shim.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            shim.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            scripts.insert(shim)

    def _update_profile_button(self):
        prof = self.profile_manager.current
        self.btn_profile.update_profile(prof.initial, prof.color)
        self.setWindowTitle(f"CalNav — {prof.display_name}")

    def _switch_profile(self, name: str):
        # Save session for old profile before switching
        self._save_session()

        self.profile_manager.set_current(name)
        prof = self.profile_manager.current

        self.password_manager = PasswordManager(prof.passwords_file, prof.name)
        self.bookmark_manager = BookmarkManager(prof.bookmarks_file)
        self._save_bar.hide()

        old_profile = self._web_profile
        self._web_profile = QWebEngineProfile(prof.name, self)
        self._apply_profile_settings()

        # Clear all existing tabs, then restore session for new profile
        self._clear_all_tabs()
        self._groups = []
        self._collapsed_groups = set()
        old_profile.deleteLater()

        self._update_profile_button()
        self._restore_session()
        self.statusBar().showMessage(f"Profilo: {prof.display_name}", 3000)

    def _open_profile_dialog(self):
        dlg = ProfileDialog(self.profile_manager, self)
        dlg.switched.connect(self._switch_profile)
        dlg.exec()

    def _open_password_vault(self):
        dlg = PasswordVaultDialog(self.password_manager, self)
        dlg.exec()

    def _toggle_bookmark(self):
        url   = self.address_bar.text().strip()
        title = (self.webview.title() if self.webview else None) or url
        existing = self.bookmark_manager.is_bookmarked(url)
        dlg = AddBookmarkDialog(url, title, self.bookmark_manager,
                                bookmark=existing, parent=self)
        result = dlg.exec()
        if result == QDialog.DialogCode.Accepted:
            name, cat, pinned = dlg.get_values()
            if existing:
                self.bookmark_manager.update(existing.id, title=name, category=cat, pinned=pinned)
            else:
                self.bookmark_manager.add(url, name, cat, pinned)
        elif result == 2 and existing:
            self.bookmark_manager.remove(existing.id)
        self._update_star_button(url)

    def _open_bookmarks(self):
        dlg = BookmarksDialog(self.bookmark_manager, self)
        dlg.navigate.connect(self.load)
        dlg.exec()
        self._update_star_button(self.address_bar.text().strip())

    def _update_star_button(self, url: str = ""):
        url = url or self.address_bar.text().strip()
        if self.bookmark_manager.is_bookmarked(url):
            self.btn_star.setText("\u2605")   # stella piena
            self.btn_star.setStyleSheet(self.btn_star.styleSheet().replace("#7AB8E8", AMBER))
            self.btn_star.setToolTip("Modifica preferito  Ctrl+D")
        else:
            self.btn_star.setText("\u2606")   # stella vuota
            self.btn_star.setToolTip("Aggiungi ai preferiti  Ctrl+D")
        # Ripristina style corretto
        self.btn_star.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {"#F5A623" if self.bookmark_manager.is_bookmarked(url) else "#7AB8E8"};
                border: none; border-radius: 19px; font-size: 18px;
            }}
            QPushButton:hover   {{ background: {BTN_HOVER}; color: {"#FFB84D" if self.bookmark_manager.is_bookmarked(url) else TEAL}; }}
            QPushButton:pressed {{ background: {BTN_PRESS}; }}
        """)

    def _open_settings(self):
        dlg = SettingsDialog(self._settings, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._settings = dlg.get_settings()
            _save_settings(self._settings)
            self.statusBar().showMessage("Impostazioni salvate.", 3000)

    def _on_save_request(self, url: str, username: str, password: str):
        self._save_bar.offer(url, username, password)

    def _on_save_bar_saved(self, url: str, username: str, password: str):
        self.password_manager.save(url, username, password)
        self.statusBar().showMessage("Password salvata.", 3000)

    def _on_autofill_fill(self, username: str, password: str):
        """Inject saved credentials into the current page's login form."""
        view = self.webview
        if not view:
            return
        # Escape strings for safe JS interpolation
        u = username.replace("\\", "\\\\").replace("'", "\\'")
        p = password.replace("\\", "\\\\").replace("'", "\\'")
        view.page().runJavaScript(f"""
(function(usr, pwd) {{
    function setNative(el, val) {{
        var d = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value');
        if (d && d.set) d.set.call(el, val);
        else el.value = val;
        el.dispatchEvent(new Event('input',  {{bubbles:true}}));
        el.dispatchEvent(new Event('change', {{bubbles:true}}));
    }}
    var pwFields = document.querySelectorAll('input[type="password"]');
    if (!pwFields.length) return;
    var userSelectors = [
        'input[type="email"]', 'input[autocomplete="username"]',
        'input[autocomplete="email"]', 'input[name*="email" i]',
        'input[name*="user" i]', 'input[name*="login" i]',
        'input[id*="email" i]', 'input[id*="user" i]',
        'input[type="text"]'
    ];
    pwFields.forEach(function(pw) {{
        var container = pw.closest('form') || document;
        var usrEl = null;
        for (var s = 0; s < userSelectors.length; s++) {{
            usrEl = container.querySelector
                ? container.querySelector(userSelectors[s])
                : null;
            if (usrEl) break;
        }}
        if (usrEl) setNative(usrEl, usr);
        setNative(pw, pwd);
    }});
}})('{u}', '{p}');
        """)

    # ── Shortcuts ─────────────────────────────────────────────────────────────
    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+L"),         self, self._focus_address_bar)
        QShortcut(QKeySequence("F5"),             self, lambda: self.webview.reload() if self.webview else None)
        QShortcut(QKeySequence("Escape"),         self, lambda: self.webview.stop()   if self.webview else None)
        QShortcut(QKeySequence("Alt+Left"),       self, lambda: self.webview.back()   if self.webview else None)
        QShortcut(QKeySequence("Alt+Right"),      self, lambda: self.webview.forward() if self.webview else None)
        QShortcut(QKeySequence("Ctrl+H"),         self, lambda: self.load(self._settings["homepage"]))
        QShortcut(QKeySequence("Ctrl+I"),         self, self._toggle_ie_mode)
        QShortcut(QKeySequence("F12"),            self, self._open_devtools)
        QShortcut(QKeySequence("Ctrl+D"),         self, self._toggle_bookmark)
        QShortcut(QKeySequence("Ctrl+Shift+B"),   self, self._open_bookmarks)
        QShortcut(QKeySequence("Ctrl+Shift+P"),   self, self._open_profile_dialog)
        QShortcut(QKeySequence("Ctrl+Shift+K"),   self, self._open_password_vault)
        QShortcut(QKeySequence("Ctrl+,"),         self, self._open_settings)
        # Tab management
        QShortcut(QKeySequence("Ctrl+T"),         self, lambda: self._new_tab(self._settings["homepage"]))
        QShortcut(QKeySequence("Ctrl+W"),         self, lambda: self._close_tab(self._tab_widget.currentIndex()))
        QShortcut(QKeySequence("Ctrl+Tab"),       self, self._next_tab)
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self, self._prev_tab)
        # Media shortcuts
        QShortcut(QKeySequence("Ctrl+Shift+V"),   self, self._media_pip)
        QShortcut(QKeySequence("Ctrl+Shift+Space"), self, self._media_play_pause)

    def _focus_address_bar(self):
        self.address_bar.setFocus()
        self.address_bar.selectAll()

    def _open_devtools(self):
        if self.webview:
            self.webview.page().triggerAction(
                self.webview.page().WebAction.InspectElement
            )

    # ── Media system ──────────────────────────────────────────────────────────
    def _on_media_state(self, state_json: str):
        """Receive media state update from MEDIA_JS running in the active tab."""
        try:
            state = json.loads(state_json)
        except Exception:
            state = {}
        # Associate state with the currently active view (for tab dot)
        view = self.webview
        if view is not None:
            self._media_states[view] = state
        # Show the media bar ONLY when the page has no visible player of its own.
        # Examples where we DO show it: audio streams, podcasts, background music,
        # videos with no controls attribute and small/off-screen rect.
        # Examples where we DON'T: YouTube, Vimeo, Spotify, any page with a
        # full-size embedded video player.
        if state.get("hasOwnPlayer"):
            self._media_bar.update_state({})   # hide bar — page has its own UI
        else:
            self._media_bar.update_state(state)
        # Refresh tab-bar dots (playing indicator)
        self._tab_bar.update()

    def _tab_index_has_media(self, index: int) -> bool:
        """Return True if the tab at *index* has non-paused media playing."""
        view = self._tab_widget.widget(index)
        if not isinstance(view, QWebEngineView):
            return False
        state = self._media_states.get(view, {})
        return bool(state.get("hasMedia") and not state.get("paused"))

    def _media_js(self, js: str):
        """Run a JS snippet on the currently active tab's page."""
        view = self.webview
        if view:
            view.page().runJavaScript(js)

    def _media_play_pause(self):
        self._media_js("if(window.__cn_play_pause) window.__cn_play_pause();")

    def _media_seek(self, t: float):
        self._media_js(f"if(window.__cn_seek_to) window.__cn_seek_to({t:.3f});")

    def _media_seek_rel(self, delta: float):
        self._media_js(f"if(window.__cn_seek_rel) window.__cn_seek_rel({delta:.1f});")

    def _media_volume(self, v: float):
        self._media_js(f"if(window.__cn_volume) window.__cn_volume({v:.3f});")

    def _ensure_pip_window(self) -> "CalNavPiPWindow":
        """Return the shared PiP window, creating it on first call."""
        if self._pip_window is None:
            self._pip_window = CalNavPiPWindow(self._web_profile, parent=None)
            self._pip_window.pip_closed.connect(self._on_pip_closed)
        return self._pip_window

    def _on_pip_closed(self):
        """Un-mute the source tab that was silenced when PiP was opened."""
        if self._pip_source_view is not None:
            try:
                self._pip_source_view.page().setAudioMuted(False)
            except RuntimeError:
                pass  # view was already deleted
            self._pip_source_view = None

    def _media_pip(self):
        """Open Picture-in-Picture for the active tab's video.

        Strategy
        ────────
        1. Qt 6.8+ TogglePictureInPicture WebAction — promotes the EXISTING
           <video> element into the OS PiP overlay.  No new page load, no ads,
           perfectly in sync with the original tab.  Works for YouTube, Twitch,
           and any other site with a <video> element.
        2. JS requestPictureInPicture() — same idea via the Web API.  Requires
           --disable-features=UserActivationV2 so runJavaScript() counts as a
           trusted user gesture.
        3. CalNavPiPWindow fallback — only for direct http/https video URLs
           (non-blob) where neither native approach succeeded.  blob: / MSE /
           DRM streams cannot be transferred to another renderer and are skipped.
        """
        view = self.webview
        if not view:
            return

        title = view.title() or ""

        # ── 1. Native Qt WebAction (Qt 6.8+, trusted context) ────────────────
        # triggerPageAction runs in a trusted renderer context, satisfying the
        # user-gesture requirement without any Chromium flag gymnastics.
        pip_action = getattr(QWebEnginePage.WebAction, "TogglePictureInPicture", None)
        if pip_action is not None:
            try:
                view.page().triggerPageAction(pip_action)
                return
            except Exception:
                pass

        # ── 2. JS requestPictureInPicture() ──────────────────────────────────
        # Works when --disable-features=UserActivationV2 is set (see main()).
        _PIP_JS = (
            "(function(){"
            "var v=document.querySelector('video');"
            "if(v&&document.pictureInPictureEnabled){"
            "  v.requestPictureInPicture().catch(function(){});"
            "  return true;"
            "}"
            "return false;"
            "})()"
        )

        def _after_js_pip(ok):
            if ok:
                return  # JS PiP accepted — done

            # ── 3. CalNavPiPWindow for direct transferable URLs ───────────────
            state = self._media_states.get(view, {})
            src = state.get("src", "")
            if not src or src.startswith("blob:"):
                return  # blob: / MSE cannot be transferred

            def _open_direct(t):
                pip = self._ensure_pip_window()
                pip.play_direct(src, t or 0, title)
                _show_pip(pip)

            view.page().runJavaScript(
                "(function(){"
                "var v=document.querySelector('video,audio');"
                "return v?v.currentTime:0;"
                "})()",
                _open_direct,
            )

        view.page().runJavaScript(_PIP_JS, _after_js_pip)

    def _toggle_theme(self):
        new_theme = "light" if _current_theme == "dark" else "dark"
        set_theme(new_theme)
        self._settings["theme"] = new_theme
        from calnav_profiles import DATA_DIR as _DD
        _save_settings(self._settings)
        self._retheme()

    def _retheme(self):
        """Rebuild toolbar and re-style all persistent chrome widgets."""
        from PyQt6.QtWidgets import QApplication as _QApp

        # Update app-level QSS (menus, scrollbars, tooltips)
        _QApp.instance().setStyleSheet(_global_qss())

        # Main window background
        self.setStyleSheet(f"QMainWindow {{ background: {NAVY_DEEP}; }}")

        # Rebuild toolbar in-place
        vbox = self.centralWidget().layout()
        old_toolbar = self.toolbar_widget
        self.toolbar_widget = self._build_toolbar()
        idx = vbox.indexOf(old_toolbar)
        if idx >= 0:
            vbox.insertWidget(idx, self.toolbar_widget)
            vbox.removeWidget(old_toolbar)
        old_toolbar.deleteLater()

        # Re-style persistent bars
        self._save_bar.retheme()
        self._autofill_bar.retheme()
        self._media_bar.retheme()
        self._update_bar.retheme()

        # Progress bar
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {NAVY_LIGHT}; border: none; height: 3px;
            }}
            QProgressBar::chunk {{ background: {TEAL}; }}
        """)

        # Status bar
        self.statusBar().setStyleSheet(
            f"background: {NAVY_MID}; color: {TEXT_DIM}; font-size: 11px;"
        )

        # Apply web color scheme to all open tabs
        self._apply_web_color_scheme()

    def _apply_web_color_scheme(self):
        """Tell QtWebEngine which color scheme pages should prefer."""
        try:
            from PyQt6.QtWebEngineCore import QWebEngineSettings
            scheme = (QWebEngineSettings.ColorScheme.Dark
                      if _current_theme == "dark"
                      else QWebEngineSettings.ColorScheme.Light)
            self._web_profile.settings().setColorScheme(scheme)
        except (AttributeError, ImportError):
            pass  # Qt < 6.6 — no color scheme API

    def _next_tab(self):
        n = self._tab_widget.count()
        if n > 1:
            self._tab_widget.setCurrentIndex(
                (self._tab_widget.currentIndex() + 1) % n
            )

    def _prev_tab(self):
        n = self._tab_widget.count()
        if n > 1:
            self._tab_widget.setCurrentIndex(
                (self._tab_widget.currentIndex() - 1) % n
            )

    # ── Tab management ────────────────────────────────────────────────────────
    def _ensure_plus_tab(self):
        """Keep a '+' pseudo-tab always at the very end of the tab bar.

        Removes any existing '+' tab(s), then appends a fresh one at the end.
        Call this after every structural change (new tab, close tab, rebuild headers,
        session restore).  The "+" tab is painted by CalNavTabBar._paint_group_overlays;
        clicking it emits new_tab_requested without ever becoming the current tab.
        """
        # Remove all existing "+" pseudo-tabs (there should normally be at most one)
        to_remove = [i for i in range(self._tab_bar.count())
                     if CalNavTabBar.is_plus_data(self._tab_bar.tabData(i))]
        for i in reversed(to_remove):
            w = self._tab_widget.widget(i)
            self._tab_widget.removeTab(i)
            if w:
                w.deleteLater()
        # Append a new "+" pseudo-tab at the end
        placeholder = QWidget()
        idx = self._tab_widget.addTab(placeholder, "")
        self._tab_bar.setTabData(idx, CalNavTabBar._PLUS_DATA)
        # Make sure it has no close button
        self._tab_bar.setTabButton(idx, QTabBar.ButtonPosition.RightSide, None)
        self._tab_bar.setTabButton(idx, QTabBar.ButtonPosition.LeftSide, None)

    def _new_tab(self, url: str = "", group_id: Optional[str] = None,
                 activate: bool = True) -> QWebEngineView:
        """Create a new tab with its own page, optionally in a group."""
        view = QWebEngineView()
        page = QWebEnginePage(self._web_profile, view)
        page.setWebChannel(self._channel)
        view.setPage(page)

        # Connect signals
        view.urlChanged.connect(self._on_url_changed)
        view.loadProgress.connect(self._on_load_progress)
        view.loadStarted.connect(self._on_load_started)
        view.loadFinished.connect(self._on_load_finished)
        view.titleChanged.connect(self._on_title_changed)

        idx = self._tab_widget.addTab(view, "Nuova scheda")
        self._tab_bar.setTabData(idx, group_id)

        # Ensure group header "linguetta" is present (may shift indices)
        if group_id:
            self._ensure_group_header(group_id)

        # Re-find tab index after possible header / "+" insertion
        idx = self._tab_widget.indexOf(view)

        # Visible × close button
        btn_close = QPushButton("×")
        btn_close.setFixedSize(16, 16)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setToolTip("Chiudi scheda")
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_DIM};
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 0;
            }}
            QPushButton:hover {{
                background: rgba(255,107,107,0.30);
                color: #FF6B6B;
            }}
        """)
        btn_close.clicked.connect(lambda: self._close_tab_by_view(view))
        self._tab_bar.setTabButton(idx, QTabBar.ButtonPosition.RightSide, btn_close)

        # Keep "+" pseudo-tab at the end (new tab was appended, possibly after "+")
        self._ensure_plus_tab()

        # Re-find index after _ensure_plus_tab may have shifted things
        idx = self._tab_widget.indexOf(view)

        if activate:
            self._tab_widget.setCurrentIndex(idx)

        if url:
            self._load_in_view(view, url)

        return view

    def _close_tab_by_view(self, view: QWebEngineView):
        """Close the tab that contains *view* (used by per-tab close buttons)."""
        idx = self._tab_widget.indexOf(view)
        if idx >= 0:
            self._close_tab(idx)

    def _ensure_group_header(self, group_id: str):
        """Insert a group-header 'linguetta' tab immediately before the first real
        tab of *group_id*, if no header is already present."""
        g = self._get_group(group_id)
        if not g:
            return
        header_data = CalNavTabBar.header_data(group_id)
        # Check if header already exists
        for i in range(self._tab_bar.count()):
            if self._tab_bar.tabData(i) == header_data:
                return
        # Find first real tab with this group_id
        first_real = -1
        for i in range(self._tab_bar.count()):
            if self._tab_bar.tabData(i) == group_id:
                first_real = i
                break
        if first_real < 0:
            return  # no real tabs to head yet
        is_collapsed = group_id in self._collapsed_groups
        label = f"▶ {g.name}" if is_collapsed else f"▼ {g.name}"
        placeholder = QWidget()
        idx = self._tab_widget.insertTab(first_real, placeholder, label)
        self._tab_bar.setTabData(idx, header_data)

    def _maybe_remove_group_header(self, group_id: str):
        """Remove the group-header tab if no real tabs remain in the group."""
        has_real = any(
            self._tab_bar.tabData(i) == group_id
            for i in range(self._tab_bar.count())
        )
        if has_real:
            return
        header_data = CalNavTabBar.header_data(group_id)
        to_remove = [i for i in range(self._tab_bar.count())
                     if self._tab_bar.tabData(i) == header_data]
        for i in reversed(to_remove):
            w = self._tab_widget.widget(i)
            self._tab_widget.removeTab(i)
            if w:
                w.deleteLater()

    def _close_tab(self, index: int):
        """Close a tab. Group-header and '+' tabs are ignored; always keeps ≥1 real tab."""
        if index < 0 or index >= self._tab_widget.count():
            return
        raw = self._tab_bar.tabData(index)
        # Never close a group-header linguetta tab or the "+" pseudo-tab
        if CalNavTabBar.is_header_data(raw) or CalNavTabBar.is_plus_data(raw):
            return
        group_id = raw if raw else None
        # Count real (non-header, non-plus) web views
        real_count = sum(
            1 for i in range(self._tab_widget.count())
            if isinstance(self._tab_widget.widget(i), QWebEngineView)
        )
        if real_count <= 1:
            self.load(self._settings["homepage"])
            return
        view = self._tab_widget.widget(index)
        self._tab_widget.removeTab(index)
        if isinstance(view, QWebEngineView):
            try:
                view.urlChanged.disconnect(self._on_url_changed)
                view.loadProgress.disconnect(self._on_load_progress)
                view.loadStarted.disconnect(self._on_load_started)
                view.loadFinished.disconnect(self._on_load_finished)
                view.titleChanged.disconnect(self._on_title_changed)
            except Exception:
                pass
            view.setPage(QWebEnginePage())   # detach shared profile page
            self._media_states.pop(view, None)   # clean up media state
        if view:
            view.deleteLater()
        # Remove group header if no more real tabs belong to that group
        if group_id:
            self._maybe_remove_group_header(group_id)

    def _clear_all_tabs(self):
        """Remove all tabs without creating a replacement (used on profile switch)."""
        while self._tab_widget.count() > 0:
            view = self._tab_widget.widget(0)
            self._tab_widget.removeTab(0)
            if isinstance(view, QWebEngineView):
                try:
                    view.urlChanged.disconnect(self._on_url_changed)
                    view.loadProgress.disconnect(self._on_load_progress)
                    view.loadStarted.disconnect(self._on_load_started)
                    view.loadFinished.disconnect(self._on_load_finished)
                    view.titleChanged.disconnect(self._on_title_changed)
                except Exception:
                    pass
                view.setPage(QWebEnginePage())
            if view:
                view.deleteLater()

    def _on_tab_changed(self, index: int):
        """Update toolbar state to reflect newly-selected tab."""
        if index < 0:
            return

        raw_data = self._tab_bar.tabData(index)

        # Header or "+" pseudo-tab got selected (Qt auto-selected it after
        # a collapse or a tab removal — header clicks are intercepted in
        # mousePressEvent and never reach here normally).
        # Silently redirect focus to the nearest visible real tab.
        if CalNavTabBar.is_header_data(raw_data) or CalNavTabBar.is_plus_data(raw_data):
            for i in range(self._tab_widget.count()):
                d = self._tab_bar.tabData(i)
                if (self._tab_bar.isTabVisible(i)
                        and not CalNavTabBar.is_header_data(d)
                        and not CalNavTabBar.is_plus_data(d)):
                    self._tab_widget.setCurrentIndex(i)
                    # _on_tab_changed will be called again with the real tab index
                    return
            return   # no real tab visible yet (e.g. during startup)

        view = self._tab_widget.widget(index)
        if not isinstance(view, QWebEngineView):
            return
        url = view.url().toString()
        if url and url != "about:blank":
            self.address_bar.setText(url)
        else:
            self.address_bar.clear()
        h = view.history()
        self.btn_back.setEnabled(h.canGoBack())
        self.btn_forward.setEnabled(h.canGoForward())
        self._update_star_button(url)
        title = view.title()
        prof = self.profile_manager.current
        suffix = f"  —  CalNav [{prof.display_name}]"
        self.setWindowTitle(f"{title}{suffix}" if title else f"CalNav [{prof.display_name}]")

        # ── Media bar: show cached state for this tab, then ask it to re-report
        cached = self._media_states.get(view, {})
        self._media_bar.update_state(cached)
        # Request an immediate fresh report from the newly-active tab's JS
        # (the MEDIA_JS visibilitychange handler fires too, but this ensures
        #  the bar updates even on first switch when the JS is already loaded)
        QTimer.singleShot(200, lambda: view.page().runJavaScript(
            "if(window.__cn_report) window.__cn_report();"
        ))

    # ── Group management ──────────────────────────────────────────────────────
    def _get_group_color(self, group_id: str) -> Optional[str]:
        for g in self._groups:
            if g.id == group_id:
                return g.color
        return None

    def _get_group(self, group_id: str) -> Optional[TabGroup]:
        return next((g for g in self._groups if g.id == group_id), None)

    def _show_tab_context_menu(self, pos):
        """Right-click context menu on the tab bar."""
        index = self._tab_bar.tabAt(pos)
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {NAVY_MID}; color: {TEXT_BRIGHT};
                border: 1px solid #253852; border-radius: 8px; padding: 4px;
            }}
            QMenu::item {{ padding: 6px 20px 6px 12px; border-radius: 5px; }}
            QMenu::item:selected {{ background: rgba(0,212,255,0.15); color: {TEAL}; }}
            QMenu::separator {{ height: 1px; background: #253852; margin: 4px 8px; }}
        """)

        if index >= 0 and CalNavTabBar.is_plus_data(self._tab_bar.tabData(index)):
            # Right-clicked on the "+" pseudo-tab — treat same as empty area
            index = -1

        if index >= 0:
            raw_data = self._tab_bar.tabData(index)
            is_header = CalNavTabBar.is_header_data(raw_data)

            if is_header:
                # Right-clicked on a group-header linguetta
                gid = CalNavTabBar.real_gid(raw_data)
                g = self._get_group(gid)
                is_col = gid in self._collapsed_groups
                lbl = f"{'▶  Espandi' if is_col else '▼  Comprimi'} gruppo «{g.name if g else '?'}»"
                act_exp = menu.addAction(lbl)
                act_exp.triggered.connect(lambda: self._toggle_group_collapse(gid))
                if g:
                    menu.addSeparator()
                    act_edit = menu.addAction("✏  Modifica gruppo…")
                    act_edit.triggered.connect(lambda: self._edit_group(gid))
                    act_del = menu.addAction("✕  Elimina gruppo")
                    act_del.triggered.connect(lambda: self._delete_group(gid))
            else:
                current_gid = raw_data  # str | None
                current_group = self._get_group(current_gid) if current_gid else None

                # Collapse/expand for grouped tab
                if current_gid:
                    is_col = current_gid in self._collapsed_groups
                    lbl = f"{'▶  Espandi' if is_col else '▼  Comprimi'} gruppo «{current_group.name if current_group else '?'}»"
                    act_col = menu.addAction(lbl)
                    act_col.triggered.connect(lambda: self._toggle_group_collapse(current_gid))
                    menu.addSeparator()

                # Group assignment submenu
                grp_menu = menu.addMenu("📂  Assegna gruppo")
                grp_menu.setStyleSheet(menu.styleSheet())

                act_no_grp = grp_menu.addAction("Nessun gruppo")
                act_no_grp.setCheckable(True)
                act_no_grp.setChecked(current_gid is None)
                act_no_grp.triggered.connect(lambda: self._assign_tab_group(index, None))

                if self._groups:
                    grp_menu.addSeparator()
                    for g in self._groups:
                        act = grp_menu.addAction(f"● {g.name}")
                        act.setCheckable(True)
                        act.setChecked(g.id == current_gid)
                        act.triggered.connect(lambda _, gid=g.id: self._assign_tab_group(index, gid))

                grp_menu.addSeparator()
                act_new_grp = grp_menu.addAction("＋  Nuovo gruppo…")
                act_new_grp.triggered.connect(lambda: self._create_group_and_assign(index))

                if current_gid:
                    act_edit_grp = menu.addAction(f"✏  Modifica gruppo «{current_group.name if current_group else '?'}»")
                    act_edit_grp.triggered.connect(lambda: self._edit_group(current_gid))

                menu.addSeparator()
                act_dup = menu.addAction("⧉  Duplica scheda")
                act_dup.triggered.connect(lambda: self._duplicate_tab(index))

                act_new = menu.addAction("＋  Nuova scheda")
                act_new.triggered.connect(lambda: self._new_tab(self._settings["homepage"]))

                menu.addSeparator()
                act_close = menu.addAction("✕  Chiudi scheda  Ctrl+W")
                act_close.triggered.connect(lambda: self._close_tab(index))
        else:
            # Clicked on empty area of tab bar
            act_new = menu.addAction("＋  Nuova scheda  Ctrl+T")
            act_new.triggered.connect(lambda: self._new_tab(self._settings["homepage"]))

        # Groups management
        if self._groups:
            menu.addSeparator()
            act_manage = menu.addAction("⚙  Gestisci gruppi…")
            act_manage.triggered.connect(self._manage_groups)

        menu.exec(self._tab_bar.mapToGlobal(pos))

    def _assign_tab_group(self, index: int, group_id: Optional[str]):
        old_raw = self._tab_bar.tabData(index)
        old_gid = old_raw if (old_raw and not CalNavTabBar.is_header_data(old_raw)) else None
        self._tab_bar.setTabData(index, group_id)
        if group_id:
            self._ensure_group_header(group_id)
        if old_gid and old_gid != group_id:
            self._maybe_remove_group_header(old_gid)
        self._tab_bar.update()

    def _create_group_and_assign(self, tab_index: int):
        dlg = GroupDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, color = dlg.get_values()
            if name:
                g = TabGroup.new(name, color)
                self._groups.append(g)
                self._assign_tab_group(tab_index, g.id)

    def _edit_group(self, group_id: str):
        g = self._get_group(group_id)
        if not g:
            return
        dlg = GroupDialog(group=g, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, color = dlg.get_values()
            if name:
                g.name = name
                g.color = color
                self._tab_bar.update()

    def _manage_groups(self):
        """Simple groups management: list + delete."""
        if not self._groups:
            return
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {NAVY_MID}; color: {TEXT_BRIGHT};
                border: 1px solid #253852; border-radius: 8px; padding: 4px;
            }}
            QMenu::item {{ padding: 6px 20px 6px 12px; border-radius: 5px; }}
            QMenu::item:selected {{ background: rgba(0,212,255,0.15); color: {TEAL}; }}
        """)
        for g in list(self._groups):
            act = menu.addAction(f"✕  Elimina «{g.name}»")
            act.triggered.connect(lambda _, gid=g.id: self._delete_group(gid))
        menu.exec(self.cursor().pos())

    def _delete_group(self, group_id: str):
        # Reveal hidden tabs first (expand without calling toggle to avoid side-effects)
        if group_id in self._collapsed_groups:
            self._collapsed_groups.discard(group_id)
            for i in range(self._tab_bar.count()):
                if self._tab_bar.tabData(i) == group_id:
                    self._tab_bar.setTabVisible(i, True)
        # Remove the group-header linguetta tab
        header_data = CalNavTabBar.header_data(group_id)
        to_remove = [i for i in range(self._tab_bar.count())
                     if self._tab_bar.tabData(i) == header_data]
        for i in reversed(to_remove):
            w = self._tab_widget.widget(i)
            self._tab_widget.removeTab(i)
            if w:
                w.deleteLater()
        self._groups = [g for g in self._groups if g.id != group_id]
        self._collapsed_groups.discard(group_id)
        # Remove group assignment from all tabs that used it
        for i in range(self._tab_bar.count()):
            if self._tab_bar.tabData(i) == group_id:
                self._tab_bar.setTabData(i, None)
        self._tab_bar.update()

    def _toggle_group_collapse(self, group_id: str):
        """Collapse or expand a group via its header 'linguetta' tab."""
        g = self._get_group(group_id)
        if not g:
            return

        header_data = CalNavTabBar.header_data(group_id)

        if group_id in self._collapsed_groups:
            # ── EXPAND ──────────────────────────────────────────────────────
            self._collapsed_groups.discard(group_id)
            first_real = -1
            for i in range(self._tab_bar.count()):
                d = self._tab_bar.tabData(i)
                if d == group_id:
                    self._tab_bar.setTabVisible(i, True)
                    if first_real < 0:
                        first_real = i
                elif d == header_data:
                    self._tab_widget.setTabText(i, f"▼ {g.name}")
            # Jump to the first tab of the now-expanded group
            if first_real >= 0:
                self._tab_widget.setCurrentIndex(first_real)
                self._on_tab_changed(first_real)
        else:
            # ── COLLAPSE ────────────────────────────────────────────────────
            cur = self._tab_widget.currentIndex()
            cur_data = self._tab_bar.tabData(cur) if cur >= 0 else None
            on_this_group = (
                cur_data == group_id
                or (cur >= 0 and not self._tab_bar.isTabVisible(cur))
                or CalNavTabBar.is_header_data(cur_data)
                or CalNavTabBar.is_plus_data(cur_data)
            )

            if on_this_group:
                # Must switch BEFORE hiding tabs, otherwise Qt auto-selects the
                # header (empty QWidget) and causes an ugly blank-page flash.
                # Find the nearest visible real tab that is NOT in this group.
                alternative = -1
                for i in range(self._tab_widget.count()):
                    d = self._tab_bar.tabData(i)
                    if (i != cur
                            and self._tab_bar.isTabVisible(i)
                            and not CalNavTabBar.is_header_data(d)
                            and not CalNavTabBar.is_plus_data(d)
                            and d != group_id):
                        alternative = i
                        break
                if alternative < 0:
                    # Every visible real tab belongs to this group — abort collapse
                    # rather than showing a blank screen.
                    self._tab_bar.update()
                    return
                # Switch to the alternative tab first, then hide the group
                self._tab_widget.setCurrentIndex(alternative)
                self._on_tab_changed(alternative)

            self._collapsed_groups.add(group_id)
            for i in range(self._tab_bar.count()):
                d = self._tab_bar.tabData(i)
                if d == group_id:
                    self._tab_bar.setTabVisible(i, False)
                elif d == header_data:
                    self._tab_widget.setTabText(i, f"▶ {g.name}")

        self._tab_bar.update()

    def _apply_collapsed_groups(self):
        """Called after session restore to re-collapse groups that were collapsed."""
        for group_id in list(self._collapsed_groups):
            self._collapsed_groups.discard(group_id)   # will be re-added by toggle
            self._toggle_group_collapse(group_id)

    def _rebuild_headers(self):
        """Remove all group-header linguette and re-insert at correct positions.
        Called after a tab is reordered by drag-and-drop to keep headers aligned."""
        # Remember the currently active view so we can restore it
        current_view = self._tab_widget.currentWidget()

        # Remove all existing header tabs AND any "+" pseudo-tab
        # (both will be re-created below in the right order)
        to_remove = [i for i in range(self._tab_bar.count())
                     if (CalNavTabBar.is_header_data(self._tab_bar.tabData(i))
                         or CalNavTabBar.is_plus_data(self._tab_bar.tabData(i)))]
        for i in reversed(to_remove):
            w = self._tab_widget.widget(i)
            self._tab_widget.removeTab(i)
            if w:
                w.deleteLater()

        # Re-insert a header before each group's first real tab (first-seen order)
        seen: set = set()
        for i in range(self._tab_bar.count()):
            d = self._tab_bar.tabData(i)
            if d and not CalNavTabBar.is_header_data(d) and not CalNavTabBar.is_plus_data(d) and d not in seen:
                seen.add(d)
                if self._get_group(d):
                    self._ensure_group_header(d)

        # Re-apply collapsed state on the freshly inserted headers
        for gid in self._collapsed_groups:
            g = self._get_group(gid)
            if not g:
                continue
            hdr = CalNavTabBar.header_data(gid)
            for i in range(self._tab_bar.count()):
                d = self._tab_bar.tabData(i)
                if d == gid:
                    self._tab_bar.setTabVisible(i, False)
                elif d == hdr:
                    self._tab_widget.setTabText(i, f"▶ {g.name}")

        # Restore active view
        if isinstance(current_view, QWebEngineView):
            idx = self._tab_widget.indexOf(current_view)
            if idx >= 0 and self._tab_bar.isTabVisible(idx):
                self._tab_widget.setCurrentIndex(idx)

        # Always keep "+" pseudo-tab at the end
        self._ensure_plus_tab()
        self._tab_bar.update()

    def _duplicate_tab(self, index: int):
        view = self._tab_widget.widget(index)
        if isinstance(view, QWebEngineView):
            url = view.url().toString()
            raw = self._tab_bar.tabData(index)
            # Resolve placeholder data to the real group id (or None)
            gid = CalNavTabBar.real_gid(raw) if raw else None
            self._new_tab(url, group_id=gid)

    # ── Session persistence ───────────────────────────────────────────────────
    def _save_session(self):
        tabs = []
        for i in range(self._tab_widget.count()):
            raw = self._tab_bar.tabData(i)
            # Skip group-header linguetta tabs and "+" pseudo-tab (virtual)
            if CalNavTabBar.is_header_data(raw) or CalNavTabBar.is_plus_data(raw):
                continue
            view = self._tab_widget.widget(i)
            if not isinstance(view, QWebEngineView):
                continue
            url = view.url().toString()
            if not url or url == "about:blank":
                url = self._settings["homepage"]
            title = self._tab_widget.tabText(i)
            tabs.append(SavedTab(url=url, title=title, group_id=raw))
        if not tabs:
            return
        # Stamp collapsed state onto groups before saving
        for g in self._groups:
            g.collapsed = (g.id in self._collapsed_groups)
        # Determine active index among real (non-header, non-plus) tabs
        active_real = 0
        real_counter = 0
        for i in range(self._tab_widget.count()):
            raw = self._tab_bar.tabData(i)
            if CalNavTabBar.is_header_data(raw) or CalNavTabBar.is_plus_data(raw):
                continue
            if not isinstance(self._tab_widget.widget(i), QWebEngineView):
                continue
            if i == self._tab_widget.currentIndex():
                active_real = real_counter
                break
            real_counter += 1
        sm = SessionManager(self.profile_manager.current.session_file)
        sm.save(self._groups, tabs, active_real)

    def _restore_session(self):
        sm = SessionManager(self.profile_manager.current.session_file)
        active, groups, tabs = sm.load()
        self._groups = groups
        self._collapsed_groups = {g.id for g in groups if g.collapsed}
        if tabs:
            active_view = None
            for i, t in enumerate(tabs):
                view = self._new_tab(t.url, group_id=t.group_id, activate=False)
                if i == active:
                    active_view = view
            # Re-collapse groups — this inserts placeholder tabs, shifting indices
            self._apply_collapsed_groups()
            # Ensure "+" pseudo-tab is at the end after all structural changes
            self._ensure_plus_tab()
            # Locate the active view by object identity (immune to index shifts)
            if active_view:
                idx = self._tab_widget.indexOf(active_view)
                if idx >= 0 and self._tab_bar.isTabVisible(idx):
                    self._tab_widget.setCurrentIndex(idx)
                    self._on_tab_changed(idx)
                else:
                    # Active tab was in a collapsed group — show first visible real tab
                    for i in range(self._tab_widget.count()):
                        d = self._tab_bar.tabData(i)
                        if (self._tab_bar.isTabVisible(i)
                                and isinstance(self._tab_widget.widget(i), QWebEngineView)
                                and not CalNavTabBar.is_plus_data(d)):
                            self._tab_widget.setCurrentIndex(i)
                            self._on_tab_changed(i)
                            break
        else:
            self._new_tab(self._settings["homepage"])

    def closeEvent(self, event):
        self._save_session()
        event.accept()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        self.toolbar_widget = self._build_toolbar()
        vbox.addWidget(self.toolbar_widget)
        vbox.addWidget(self._build_progress_bar())

        self._update_bar = UpdateBar()
        # "Scarica" button opens the GitHub releases page in the active tab
        self._update_bar.download_clicked.connect(
            lambda: self.load(GITHUB_RELEASES_URL)
        )
        vbox.addWidget(self._update_bar)

        self._save_bar = SavePasswordBar()
        self._save_bar.save_requested.connect(self._on_save_bar_saved)
        vbox.addWidget(self._save_bar)

        self._autofill_bar = AutofillBar()
        self._autofill_bar.fill_requested.connect(self._on_autofill_fill)
        vbox.addWidget(self._autofill_bar)

        vbox.addWidget(self._build_tab_widget(), stretch=1)

        # ── Persistent media control bar ─────────────────────────────────────
        self._media_bar = CalNavMediaBar()
        self._media_bar.play_pause_requested.connect(self._media_play_pause)
        self._media_bar.seek_requested.connect(self._media_seek)
        self._media_bar.seek_rel_requested.connect(self._media_seek_rel)
        self._media_bar.volume_requested.connect(self._media_volume)
        self._media_bar.pip_requested.connect(self._media_pip)
        vbox.addWidget(self._media_bar)

        self._build_status_bar()
        self.setStyleSheet(f"QMainWindow {{ background: {NAVY_DEEP}; }}")

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(64)
        self._toolbar = bar
        self._refresh_toolbar_style()

        h = QHBoxLayout(bar)
        h.setContentsMargins(14, 0, 14, 0)
        h.setSpacing(6)

        brand_icon = QLabel()
        ico_path = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "logo_browser.ico"
        if ico_path.exists():
            # Pick the largest ICO frame then downscale smoothly to avoid graininess
            brand_icon.setPixmap(
                QIcon(str(ico_path)).pixmap(64, 64).scaled(
                    32, 32,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        brand_icon.setStyleSheet("padding-right: 2px;")
        h.addWidget(brand_icon)

        brand = QLabel("CalNav")
        brand.setFont(QFont("Segoe UI", 13, QFont.Weight.Black))
        brand.setStyleSheet(
            f"color:{TEAL}; font-size:17px; font-weight:800; letter-spacing:3px; padding-right:6px;"
        )
        h.addWidget(brand)

        div = QWidget()
        div.setFixedSize(1, 28)
        div.setStyleSheet("background:#1C3050;")
        h.addWidget(div)

        self.btn_back    = NavButton("\u2190", "Indietro  Alt+\u2190")
        self.btn_forward = NavButton("\u2192", "Avanti  Alt+\u2192")
        self.btn_reload  = NavButton("\u21bb", "Ricarica  F5")
        self.btn_home    = NavButton("\u2302", "Home  Ctrl+H")
        self.btn_back.setEnabled(False)
        self.btn_forward.setEnabled(False)

        self.btn_reload.clicked.connect(self._toggle_reload)
        self.btn_home.clicked.connect(lambda: self.load(self._settings["homepage"]))
        for b in (self.btn_back, self.btn_forward, self.btn_reload, self.btn_home):
            h.addWidget(b)

        self.address_bar = AddressBar()
        self.address_bar.returnPressed.connect(self._navigate_from_bar)
        h.addWidget(self.address_bar, stretch=1)

        btn_go = QPushButton("Vai")
        btn_go.setFixedSize(62, 38)
        btn_go.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_go.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        btn_go.setStyleSheet(f"""
            QPushButton {{
                background:{TEAL}; color:{NAVY_DEEP};
                border:none; border-radius:19px; letter-spacing:1px;
            }}
            QPushButton:hover  {{ background:#33DDFF; }}
            QPushButton:pressed{{ background:{TEAL_DIM}; }}
        """)
        btn_go.clicked.connect(self._navigate_from_bar)
        h.addWidget(btn_go)

        self.btn_ie = QPushButton("\u212f IE")
        self.btn_ie.setFixedSize(58, 38)
        self.btn_ie.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ie.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_ie.setToolTip("Modalita compatibilita IE11  Ctrl+I")
        self.btn_ie.clicked.connect(self._toggle_ie_mode)
        self._refresh_ie_button_style()
        h.addWidget(self.btn_ie)

        div2 = QWidget()
        div2.setFixedSize(1, 28)
        div2.setStyleSheet("background:#1C3050;")
        h.addWidget(div2)

        # Star button (bookmarks)
        self.btn_star = NavButton("\u2606", "Aggiungi ai preferiti  Ctrl+D")
        self.btn_star.setFont(QFont("Segoe UI", 18))
        self.btn_star.clicked.connect(self._toggle_bookmark)
        h.addWidget(self.btn_star)

        # Bookmarks button
        self.btn_bmarks = NavButton("\U0001f4d6", "Preferiti  Ctrl+Shift+B")
        self.btn_bmarks.setFont(QFont("Segoe UI", 15))
        self.btn_bmarks.clicked.connect(self._open_bookmarks)
        h.addWidget(self.btn_bmarks)

        # Key button (password vault)
        self.btn_keys = NavButton("\U0001f511", "Password salvate  Ctrl+Shift+K")
        self.btn_keys.setFont(QFont("Segoe UI", 14))
        self.btn_keys.clicked.connect(self._open_password_vault)
        h.addWidget(self.btn_keys)

        # Theme toggle button
        _is_dark = _current_theme == "dark"
        self.btn_theme = NavButton("\u2600" if _is_dark else "\U0001f319",
                                   "Passa a tema chiaro" if _is_dark else "Passa a tema scuro")
        self.btn_theme.setFont(QFont("Segoe UI", 13))
        self.btn_theme.clicked.connect(self._toggle_theme)
        h.addWidget(self.btn_theme)

        # Gear button (settings)
        self.btn_settings = NavButton("\u2699", "Impostazioni  Ctrl+,")
        self.btn_settings.setFont(QFont("Segoe UI", 16))
        self.btn_settings.clicked.connect(self._open_settings)
        h.addWidget(self.btn_settings)

        # Profile avatar button
        self.btn_profile = ProfileAvatarButton()
        self.btn_profile.clicked.connect(self._open_profile_dialog)
        h.addWidget(self.btn_profile)

        return bar

    def _refresh_toolbar_style(self):
        accent = AMBER if self._ie_mode else TEAL
        self._toolbar.setStyleSheet(f"""
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {NAVY_MID}, stop:1 {NAVY_DEEP}
            );
            border-bottom: 2px solid {accent};
        """)

    def _refresh_ie_button_style(self):
        if self._ie_mode:
            self.btn_ie.setStyleSheet(f"""
                QPushButton {{
                    background:{AMBER}; color:{NAVY_DEEP};
                    border:none; border-radius:8px; letter-spacing:1px;
                }}
                QPushButton:hover  {{ background:#FFB84D; }}
                QPushButton:pressed{{ background:{AMBER_DIM}; }}
            """)
        else:
            self.btn_ie.setStyleSheet(f"""
                QPushButton {{
                    background:transparent; color:#556A88;
                    border:1px solid #253852; border-radius:8px; letter-spacing:1px;
                }}
                QPushButton:hover  {{ background:rgba(245,166,35,0.12); color:{AMBER}; border-color:{AMBER_DIM}; }}
                QPushButton:pressed{{ background:rgba(245,166,35,0.22); }}
            """)

    def _build_progress_bar(self) -> QProgressBar:
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{ background:{NAVY_DEEP}; border:none; }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #005FCC, stop:1 {TEAL});
            }}
        """)
        self.progress_bar.hide()
        return self.progress_bar

    def _build_tab_widget(self) -> QTabWidget:
        self._tab_bar = CalNavTabBar()
        self._tab_bar.set_color_resolver(self._get_group_color)
        self._tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tab_bar.customContextMenuRequested.connect(self._show_tab_context_menu)
        # Linguetta clicks toggle collapse (no black flash — super() not called in bar)
        self._tab_bar.group_header_clicked.connect(self._toggle_group_collapse)
        # "+" pseudo-tab emits this signal when clicked (see _ensure_plus_tab)
        self._tab_bar.new_tab_requested.connect(
            lambda: self._new_tab(self._settings["homepage"])
        )
        # Rebuild header positions after drag-and-drop reorder.
        # tabs_reordered fires in mouseReleaseEvent (not tabMoved), so Qt's
        # internal drag state is fully committed before we call removeTab/insertTab.
        self._tab_bar.tabs_reordered.connect(self._rebuild_headers)

        self._tab_widget = QTabWidget()
        self._tab_widget.setTabBar(self._tab_bar)
        self._tab_widget.setTabsClosable(False)   # close via × button or Ctrl+W
        self._tab_widget.setMovable(True)
        self._tab_widget.currentChanged.connect(self._on_tab_changed)

        self._tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: {NAVY_DEEP};
            }}
            QTabBar {{
                background: {NAVY_DEEP};
            }}
            QTabBar::tab {{
                background: {NAVY_MID};
                color: {TEXT_DIM};
                border: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 7px 24px 11px 14px;
                margin-right: 2px;
                min-width: 110px;
                max-width: 220px;
                font-size: 12px;
            }}
            QTabBar::tab:selected {{
                background: {NAVY_LIGHT};
                color: {TEXT_BRIGHT};
                font-weight: bold;
            }}
            QTabBar::tab:hover:!selected {{
                background: #182840;
                color: {TEXT_BRIGHT};
            }}
        """)
        # Allow the "+" pseudo-tab to be narrower than the normal min-width.
        # tabSizeHint() returns 36 px for it; without this override the stylesheet
        # min-width: 110px would prevent that small size from being honoured.
        self._tab_bar.setStyleSheet("QTabBar::tab { min-width: 0px; max-width: 220px; }")

        # Wire back/forward via lambdas (lazy evaluation of self.webview)
        self.btn_back.clicked.connect(lambda: self.webview.back()    if self.webview else None)
        self.btn_forward.clicked.connect(lambda: self.webview.forward() if self.webview else None)

        return self._tab_widget

    def _build_status_bar(self):
        sb = QStatusBar()
        sb.setStyleSheet(f"""
            QStatusBar {{
                background:{NAVY_DEEP}; color:{TEXT_DIM};
                font-size:11px; border-top:1px solid #111D2E; padding:0 8px;
            }}
        """)
        self.setStatusBar(sb)

        self._ie_badge = QLabel("  \u212f Compatibilita IE11  ")
        self._ie_badge.setStyleSheet(f"""
            color:{NAVY_DEEP}; background:{AMBER};
            border-radius:4px; font-size:10px; font-weight:bold;
            padding:1px 6px; margin:2px 0;
        """)
        self._ie_badge.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._ie_badge.hide()
        sb.addPermanentWidget(self._ie_badge)

        self._profile_badge = QLabel()
        self._profile_badge.setStyleSheet(f"""
            color:{NAVY_DEEP}; background:{PROFILE_COLORS[0]};
            border-radius:4px; font-size:10px; font-weight:bold;
            padding:1px 6px; margin:2px 4px;
        """)
        self._profile_badge.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        sb.addPermanentWidget(self._profile_badge)

    # ── Modalita IE ───────────────────────────────────────────────────────────
    def _toggle_ie_mode(self):
        self._ie_mode = not self._ie_mode
        self._apply_profile_settings()
        self._refresh_toolbar_style()
        self._refresh_ie_button_style()

        if self._ie_mode:
            self.address_bar._set_ie_mode()
            self._ie_badge.show()
            self.statusBar().showMessage("Modalita IE11 attivata — ricaricamento…", 3000)
        else:
            self.address_bar._set_normal()
            self._ie_badge.hide()
            self.statusBar().showMessage("Modalita moderna ripristinata — ricaricamento…", 3000)

        if self.webview:
            self.webview.reload()

    # ── Navigazione ───────────────────────────────────────────────────────────
    def _load_in_view(self, view: QWebEngineView, url: str):
        """Navigate a specific view to url (smart URL / search fallback)."""
        if not url.startswith(("http://", "https://", "file://")):
            if "." in url and " " not in url:
                url = "https://" + url
            else:
                url = "https://www.google.com/search?q=" + url.replace(" ", "+")
        view.setUrl(QUrl(url))

    def load(self, url: str):
        if self.webview:
            self._load_in_view(self.webview, url)

    def _navigate_from_bar(self):
        t = self.address_bar.text().strip()
        if t:
            self.load(t)

    def _toggle_reload(self):
        if self.webview:
            self.webview.reload()

    # ── WebView signals ───────────────────────────────────────────────────────
    def _on_url_changed(self, url: QUrl):
        view = self.sender()
        is_current = (view is self.webview)

        if is_current:
            u = url.toString()
            if u != "about:blank":
                self.address_bar.setText(u)
            h = view.history()
            self.btn_back.setEnabled(h.canGoBack())
            self.btn_forward.setEnabled(h.canGoForward())
            self._update_star_button(u)

            # Update profile badge
            prof = self.profile_manager.current
            self._profile_badge.setText(f"  {prof.initial} {prof.display_name}  ")
            self._profile_badge.setStyleSheet(f"""
                color:{NAVY_DEEP}; background:{prof.color};
                border-radius:4px; font-size:10px; font-weight:bold;
                padding:1px 6px; margin:2px 4px;
            """)

    def _on_load_progress(self, pct: int):
        if self.sender() is self.webview:
            self.progress_bar.setValue(pct)

    def _on_load_started(self):
        view = self.sender()
        if view is not self.webview:
            return
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.btn_reload.setText("\u2715")
        self.btn_reload.setToolTip("Interrompi  Esc")
        self.btn_reload.clicked.disconnect()
        self.btn_reload.clicked.connect(lambda: self.webview.stop() if self.webview else None)
        self.statusBar().showMessage("Caricamento…")

    def _on_load_finished(self, ok: bool):
        view = self.sender()
        # Always update tab close-button area
        idx = self._tab_widget.indexOf(view)
        if idx >= 0:
            pass   # title will be updated via titleChanged
        if view is not self.webview:
            return
        self.progress_bar.setValue(100)
        self.progress_bar.hide()
        self.btn_reload.setText("\u21bb")
        self.btn_reload.setToolTip("Ricarica  F5")
        self.btn_reload.clicked.disconnect()
        self.btn_reload.clicked.connect(self._toggle_reload)
        self.statusBar().showMessage("Pronto" if ok else "Errore nel caricamento", 5000)
        # \u2500\u2500 Autofill: offer credentials if we have any for this host \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        if ok and self.password_manager.available:
            url = view.url().toString()
            creds = self.password_manager.get(url)
            if creds:
                self._autofill_bar.offer(creds)
            else:
                self._autofill_bar.hide()

    def _on_title_changed(self, title: str):
        view = self.sender()
        # Update tab label for every tab
        idx = self._tab_widget.indexOf(view)
        if idx >= 0:
            self._tab_widget.setTabText(idx, (title[:28] + "…") if len(title) > 28 else title or "Nuova scheda")
            self._tab_widget.setTabToolTip(idx, title)
        # Update window title only for current tab
        if view is self.webview:
            prof = self.profile_manager.current
            suffix = f"  —  CalNav [{prof.display_name}]"
            self.setWindowTitle(f"{title}{suffix}" if title else f"CalNav [{prof.display_name}]")


# ── Entry point ───────────────────────────────────────────────────────────────
def _app_icon() -> QIcon:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    for name in ("logo_browser.ico",):
        ico = base / name
        if ico.exists():
            return QIcon(str(ico))
    return QIcon()


def main():
    # ── Chromium flags (must be set BEFORE QApplication is created) ──────────
    _existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")

    # The UA we want every page to see in navigator.userAgent.
    # QWebEngineProfile.setHttpUserAgent() updates the HTTP header but in some
    # Qt versions it does NOT update navigator.userAgent in JavaScript.
    # Streaming sites (Twitch, Netflix…) read navigator.userAgent via JS, so
    # they would still see the QtWebEngine UA and refuse to play.
    # --user-agent set at engine startup guarantees BOTH the HTTP header AND
    # navigator.userAgent report the same Chrome-compatible string.
    _chrome_ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    _flags = (
        # Engine-level UA override — ensures navigator.userAgent matches in JS
        f'--user-agent="{_chrome_ua}" '
        # Allow media to autoplay without a user-gesture requirement
        "--autoplay-policy=no-user-gesture-required "
        # Force software H.264/AAC decode via bundled FFmpeg.
        # On Windows N (no Media Feature Pack) or when GPU H.264 decode is
        # blocked, Chromium silently fails the hardware path and reports
        # "codec not supported".  This flag bypasses that path entirely.
        "--disable-accelerated-video-decode "
        # Allow requestPictureInPicture() called from runJavaScript() to be
        # treated as a trusted user gesture.  Without this flag the Web API
        # rejects PiP requests that didn't originate from a real click/keypress.
        "--disable-features=UserActivationV2"
    )
    if "--autoplay-policy=no-user-gesture-required" not in _existing:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
            f"{_existing} {_flags}".strip()
        )

    app = QApplication(sys.argv)
    app.setApplicationName("CalNav")
    app.setApplicationDisplayName("CalNav Browser")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(_app_icon())
    app.setStyle("Fusion")

    win = CalNavWindow()
    app.setStyleSheet(_global_qss())
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
