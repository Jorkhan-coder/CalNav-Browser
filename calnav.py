#!/usr/bin/env python3
"""CalNav Browser — Modern spirit, classic roots."""

__version__ = "1.0.0"

import json
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLineEdit, QPushButton, QStatusBar, QProgressBar, QLabel,
    QDialog, QDialogButtonBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QScrollArea, QMessageBox,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile, QWebEngineSettings, QWebEngineScript, QWebEnginePage,
)
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import (
    QUrl, Qt, QObject, pyqtSlot, pyqtSignal, QFile, QIODevice,
    PYQT_VERSION_STR, QT_VERSION_STR, QTimer,
)
from PyQt6.QtGui import QFont, QIcon, QKeySequence, QShortcut
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest

from calnav_profiles import ProfileManager, PROFILE_COLORS, DATA_DIR
from calnav_passwords import PasswordManager

HOME_URL = "https://www.google.com"
GITHUB_API_URL = (
    "https://api.github.com/repos/Jorkhan-coder/CalNav-Browser/releases/latest"
)
GITHUB_RELEASES_URL = (
    "https://github.com/Jorkhan-coder/CalNav-Browser/releases/latest"
)
_SETTINGS_FILE = DATA_DIR / "settings.json"
_SETTINGS_DEFAULTS = {"homepage": HOME_URL}


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

CALNAV_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "CalNav/1.0 Chrome/120.0.0.0 Safari/537.36"
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

# ── Palette ───────────────────────────────────────────────────────────────────
NAVY_DEEP   = "#07111F"
NAVY_MID    = "#0D1F3C"
NAVY_LIGHT  = "#1C2B45"
TEAL        = "#00D4FF"
TEAL_DIM    = "#008EAA"
AMBER       = "#F5A623"
AMBER_DIM   = "#B87400"
TEXT_BRIGHT = "#E8F4FD"
TEXT_DIM    = "#4A7AB5"
BTN_HOVER   = "rgba(0,212,255,0.14)"
BTN_PRESS   = "rgba(0,212,255,0.28)"


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

    def __init__(self, parent=None):
        super().__init__(parent)

    @pyqtSlot(str, str, str)
    def offer_save_password(self, url: str, username: str, password: str):
        self.save_password_requested.emit(url, username, password)


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
        self.setStyleSheet(
            f"background: {NAVY_MID}; border-bottom: 1px solid {TEAL_DIM};"
        )
        h = QHBoxLayout(self)
        h.setContentsMargins(18, 0, 18, 0)
        h.setSpacing(12)

        icon = QLabel("[*]")
        icon.setStyleSheet(f"color: {TEAL}; font-size: 14px; font-weight: bold;")
        h.addWidget(icon)

        self._msg = QLabel("Vuoi salvare la password per questo sito?")
        self._msg.setStyleSheet(f"color: {TEXT_BRIGHT}; font-size: 12px;")
        h.addWidget(self._msg, stretch=1)

        btn_save = QPushButton("Salva")
        btn_save.setFixedSize(80, 30)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        btn_save.setStyleSheet(f"""
            QPushButton {{ background: {TEAL}; color: {NAVY_DEEP}; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: #33DDFF; }}
        """)
        btn_save.clicked.connect(self._on_save)
        h.addWidget(btn_save)

        btn_dismiss = QPushButton("Non ora")
        btn_dismiss.setFixedSize(80, 30)
        btn_dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_dismiss.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT_DIM}; border: 1px solid #253852; border-radius: 6px; }}
            QPushButton:hover {{ border-color: {TEAL_DIM}; color: {TEXT_BRIGHT}; }}
        """)
        btn_dismiss.clicked.connect(self.hide)
        h.addWidget(btn_dismiss)

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


# ── Password vault dialog ─────────────────────────────────────────────────────
class PasswordVaultDialog(QDialog):
    def __init__(self, password_manager: PasswordManager, parent=None):
        super().__init__(parent)
        self.pm = password_manager
        self.setWindowTitle("Password Salvate — CalNav")
        self.resize(660, 460)
        self._build()

    def _build(self):
        self.setStyleSheet(f"background: {NAVY_MID}; color: {TEXT_BRIGHT};")
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(20, 20, 20, 16)
        vbox.setSpacing(12)

        hdr = QLabel("Password Salvate")
        hdr.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {TEAL}; margin-bottom: 4px;")
        vbox.addWidget(hdr)

        if not self.pm.available:
            warn = QLabel(
                "Il modulo 'cryptography' non e' installato.\n"
                "Esegui: pip install cryptography"
            )
            warn.setStyleSheet(f"color: #FF6B6B; padding: 20px; font-size: 13px;")
            vbox.addWidget(warn)
        else:
            self.table = QTableWidget()
            self.table.setColumnCount(4)
            self.table.setHorizontalHeaderLabels(["Sito", "Utente", "Password", "Azioni"])
            hh = self.table.horizontalHeader()
            hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            self.table.setStyleSheet(f"""
                QTableWidget {{
                    background: {NAVY_DEEP}; gridline-color: #1C3050;
                    color: {TEXT_BRIGHT}; border: 1px solid #1C3050; border-radius: 8px;
                }}
                QHeaderView::section {{
                    background: {NAVY_MID}; color: {TEAL};
                    border: none; padding: 6px; font-weight: bold;
                }}
                QTableWidget::item {{ padding: 4px 8px; }}
                QTableWidget::item:selected {{ background: rgba(0,212,255,0.15); }}
            """)
            self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.table.verticalHeader().setVisible(False)
            vbox.addWidget(self.table, stretch=1)
            self._fill_table()

        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_close = QPushButton("Chiudi")
        btn_close.setFixedHeight(36)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(f"""
            QPushButton {{ background: {TEAL}; color: {NAVY_DEEP}; border: none; border-radius: 8px; padding: 0 24px; font-weight: bold; }}
            QPushButton:hover {{ background: #33DDFF; }}
        """)
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        vbox.addLayout(bottom)

    def _fill_table(self):
        entries = self.pm.all_entries()
        self.table.setRowCount(len(entries))
        for r, e in enumerate(entries):
            self.table.setItem(r, 0, QTableWidgetItem(e.get("host", "")))
            self.table.setItem(r, 1, QTableWidgetItem(e.get("username", "")))
            self.table.setItem(r, 2, QTableWidgetItem("\u2022" * 8))
            self.table.setRowHeight(r, 44)

            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(4, 4, 4, 4)
            cell_layout.setSpacing(4)

            btn_show = QPushButton("Mostra")
            btn_show.setFixedHeight(28)
            btn_show.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_show.setStyleSheet(f"""
                QPushButton {{ background: rgba(0,212,255,0.15); color: {TEAL}; border: none; border-radius: 5px; padding: 0 8px; font-size: 11px; }}
                QPushButton:hover {{ background: rgba(0,212,255,0.3); }}
            """)
            btn_show.clicked.connect(lambda _, row=r, pw=e["password"]: self._toggle_pw(row, pw))
            cell_layout.addWidget(btn_show)

            btn_copy = QPushButton("Copia")
            btn_copy.setFixedHeight(28)
            btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_copy.setStyleSheet(f"""
                QPushButton {{ background: rgba(0,212,255,0.15); color: {TEAL}; border: none; border-radius: 5px; padding: 0 8px; font-size: 11px; }}
                QPushButton:hover {{ background: rgba(0,212,255,0.3); }}
            """)
            btn_copy.clicked.connect(lambda _, pw=e["password"]: QApplication.clipboard().setText(pw))
            cell_layout.addWidget(btn_copy)

            btn_del = QPushButton("X")
            btn_del.setFixedSize(28, 28)
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.setStyleSheet(f"""
                QPushButton {{ background: rgba(255,107,107,0.15); color: #FF6B6B; border: none; border-radius: 5px; font-size: 11px; }}
                QPushButton:hover {{ background: rgba(255,107,107,0.3); }}
            """)
            btn_del.clicked.connect(lambda _, h=e["host"], u=e["username"]: self._delete_entry(h, u))
            cell_layout.addWidget(btn_del)

            self.table.setCellWidget(r, 3, cell)

    def _toggle_pw(self, row: int, password: str):
        item = self.table.item(row, 2)
        if item.text() == "\u2022" * 8:
            item.setText(password)
        else:
            item.setText("\u2022" * 8)

    def _delete_entry(self, host: str, username: str):
        self.pm.delete(host, username)
        self._fill_table()


# ── Update notification bar ──────────────────────────────────────────────────
class UpdateBar(QWidget):
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

    def show_update(self, version: str):
        self._version = version
        self._msg.setText(
            f"Disponibile CalNav {version}  —  stai usando la {__version__}"
        )
        self.show()

    def _on_download(self):
        parent = self.parent()
        if parent and hasattr(parent, "load"):
            parent.load(GITHUB_RELEASES_URL)
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
        try:
            r = tuple(int(x) for x in remote.split("."))
            c = tuple(int(x) for x in current.split("."))
            return r > c
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


# ── Main window ───────────────────────────────────────────────────────────────
class CalNavWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._ie_mode = False
        self.setWindowTitle("CalNav")
        self.setMinimumSize(900, 600)
        self.resize(1280, 820)

        self._settings = _load_settings()
        self.profile_manager = ProfileManager()

        self._build_ui()

        prof = self.profile_manager.current
        self.password_manager = PasswordManager(prof.passwords_file, prof.name)

        self._bridge = CalNavBridge(self)
        self._bridge.save_password_requested.connect(self._on_save_request)
        self._channel = QWebChannel(self)
        self._channel.registerObject("calnav_bridge", self._bridge)

        self._web_profile = QWebEngineProfile(prof.name, self)
        self._web_page = QWebEnginePage(self._web_profile, self)
        self._web_page.setWebChannel(self._channel)
        self.webview.setPage(self._web_page)

        self._apply_profile_settings()
        self._setup_shortcuts()
        self._update_profile_button()
        self.load(self._settings["homepage"])

        # Controlla aggiornamenti 5 secondi dopo l'avvio
        self._updater = UpdateChecker(self)
        self._updater.update_available.connect(self._update_bar.show_update)
        QTimer.singleShot(5000, self._updater.check)

    # ── Profile / password helpers ────────────────────────────────────────────
    def _apply_profile_settings(self):
        p = self._web_profile
        p.setHttpUserAgent(IE_UA if self._ie_mode else CALNAV_UA)

        s = p.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
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
        for name in ("calnav_ie_shims", "calnav_qwebchannel", "calnav_forms"):
            for old in scripts.find(name):
                scripts.remove(old)

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
        self.profile_manager.set_current(name)
        prof = self.profile_manager.current

        self.password_manager = PasswordManager(prof.passwords_file, prof.name)
        self._save_bar.hide()

        old_profile = self._web_profile
        old_page = self._web_page

        self._web_profile = QWebEngineProfile(prof.name, self)
        self._web_page = QWebEnginePage(self._web_profile, self)
        self._web_page.setWebChannel(self._channel)
        self._apply_profile_settings()
        self.webview.setPage(self._web_page)

        old_page.deleteLater()
        old_profile.deleteLater()

        self._update_profile_button()
        self.statusBar().showMessage(f"Profilo: {prof.display_name}", 3000)
        self.webview.reload()

    def _open_profile_dialog(self):
        dlg = ProfileDialog(self.profile_manager, self)
        dlg.switched.connect(self._switch_profile)
        dlg.exec()

    def _open_password_vault(self):
        dlg = PasswordVaultDialog(self.password_manager, self)
        dlg.exec()

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

    # ── Shortcuts ─────────────────────────────────────────────────────────────
    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+L"),         self, self._focus_address_bar)
        QShortcut(QKeySequence("F5"),             self, self.webview.reload)
        QShortcut(QKeySequence("Escape"),         self, self.webview.stop)
        QShortcut(QKeySequence("Alt+Left"),       self, self.webview.back)
        QShortcut(QKeySequence("Alt+Right"),      self, self.webview.forward)
        QShortcut(QKeySequence("Ctrl+H"),         self, lambda: self.load(self._settings["homepage"]))
        QShortcut(QKeySequence("Ctrl+I"),         self, self._toggle_ie_mode)
        QShortcut(QKeySequence("F12"),            self, self._open_devtools)
        QShortcut(QKeySequence("Ctrl+Shift+P"),   self, self._open_profile_dialog)
        QShortcut(QKeySequence("Ctrl+Shift+K"),   self, self._open_password_vault)
        QShortcut(QKeySequence("Ctrl+,"),         self, self._open_settings)

    def _focus_address_bar(self):
        self.address_bar.setFocus()
        self.address_bar.selectAll()

    def _open_devtools(self):
        self.webview.page().triggerAction(
            self.webview.page().WebAction.InspectElement
        )

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
        vbox.addWidget(self._update_bar)

        self._save_bar = SavePasswordBar()
        self._save_bar.save_requested.connect(self._on_save_bar_saved)
        vbox.addWidget(self._save_bar)

        vbox.addWidget(self._build_webview(), stretch=1)
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

        brand = QLabel("\u2295 CalNav")
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

        # Key button (password vault)
        self.btn_keys = NavButton("\U0001f511", "Password salvate  Ctrl+Shift+K")
        self.btn_keys.setFont(QFont("Segoe UI", 14))
        self.btn_keys.clicked.connect(self._open_password_vault)
        h.addWidget(self.btn_keys)

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

    def _build_webview(self) -> QWebEngineView:
        self.webview = QWebEngineView()
        self.webview.urlChanged.connect(self._on_url_changed)
        self.webview.loadProgress.connect(self._on_load_progress)
        self.webview.loadStarted.connect(self._on_load_started)
        self.webview.loadFinished.connect(self._on_load_finished)
        self.webview.titleChanged.connect(self._on_title_changed)
        self.btn_back.clicked.connect(self.webview.back)
        self.btn_forward.clicked.connect(self.webview.forward)
        return self.webview

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

        self.webview.reload()

    # ── Navigazione ───────────────────────────────────────────────────────────
    def load(self, url: str):
        if not url.startswith(("http://", "https://", "file://")):
            if "." in url and " " not in url:
                url = "https://" + url
            else:
                url = "https://www.google.com/search?q=" + url.replace(" ", "+")
        self.webview.setUrl(QUrl(url))

    def _navigate_from_bar(self):
        t = self.address_bar.text().strip()
        if t:
            self.load(t)

    def _toggle_reload(self):
        self.webview.reload()

    # ── WebView signals ───────────────────────────────────────────────────────
    def _on_url_changed(self, url: QUrl):
        u = url.toString()
        if u != "about:blank":
            self.address_bar.setText(u)
        h = self.webview.history()
        self.btn_back.setEnabled(h.canGoBack())
        self.btn_forward.setEnabled(h.canGoForward())

        # Update profile badge
        prof = self.profile_manager.current
        self._profile_badge.setText(f"  {prof.initial} {prof.display_name}  ")
        self._profile_badge.setStyleSheet(f"""
            color:{NAVY_DEEP}; background:{prof.color};
            border-radius:4px; font-size:10px; font-weight:bold;
            padding:1px 6px; margin:2px 4px;
        """)

    def _on_load_progress(self, pct: int):
        self.progress_bar.setValue(pct)

    def _on_load_started(self):
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.btn_reload.setText("\u2715")
        self.btn_reload.setToolTip("Interrompi  Esc")
        self.btn_reload.clicked.disconnect()
        self.btn_reload.clicked.connect(self.webview.stop)
        self.statusBar().showMessage("Caricamento…")

    def _on_load_finished(self, ok: bool):
        self.progress_bar.setValue(100)
        self.progress_bar.hide()
        self.btn_reload.setText("\u21bb")
        self.btn_reload.setToolTip("Ricarica  F5")
        self.btn_reload.clicked.disconnect()
        self.btn_reload.clicked.connect(self._toggle_reload)
        self.statusBar().showMessage("Pronto" if ok else "Errore nel caricamento", 5000)

    def _on_title_changed(self, title: str):
        prof = self.profile_manager.current
        suffix = f"  —  CalNav [{prof.display_name}]"
        self.setWindowTitle(f"{title}{suffix}" if title else f"CalNav [{prof.display_name}]")


# ── Entry point ───────────────────────────────────────────────────────────────
def _app_icon() -> QIcon:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    for name in ("logo_browser.ico", "calnav_icon.ico"):
        ico = base / name
        if ico.exists():
            return QIcon(str(ico))
    return QIcon()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CalNav")
    app.setApplicationDisplayName("CalNav Browser")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(_app_icon())
    app.setStyle("Fusion")

    win = CalNavWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
