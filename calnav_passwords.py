#!/usr/bin/env python3
"""CalNav — Password manager with per-profile Fernet encryption."""

import json
import secrets
import string
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

DEFAULT_CATEGORY = "Generale"


def _machine_id() -> str:
    """Return a stable per-machine identifier used as KDF input.

    Windows  → HKLM\\SOFTWARE\\Microsoft\\Cryptography → MachineGuid
    Linux    → /etc/machine-id  (systemd)  or  /var/lib/dbus/machine-id
    macOS    → ioreg IOPlatformUUID
    Fallback → static string (passwords are still encrypted, just not
               machine-tied — acceptable for a single-user desktop app)
    """
    import sys as _sys

    # ── Windows ──────────────────────────────────────────────────────────────
    if _sys.platform == "win32":
        try:
            import winreg as _winreg
            key = _winreg.OpenKey(
                _winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                _winreg.KEY_READ | _winreg.KEY_WOW64_64KEY,
            )
            val, _ = _winreg.QueryValueEx(key, "MachineGuid")
            _winreg.CloseKey(key)
            return val
        except Exception:
            pass

    # ── Linux / BSD (systemd machine-id) ─────────────────────────────────────
    for _mid_path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            mid = open(_mid_path).read().strip()
            if mid:
                return mid
        except OSError:
            pass

    # ── macOS (IOPlatformUUID) ────────────────────────────────────────────────
    if _sys.platform == "darwin":
        try:
            import subprocess as _sp
            out = _sp.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                stderr=_sp.DEVNULL,
                text=True,
            )
            import re as _re
            m = _re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', out)
            if m:
                return m.group(1)
        except Exception:
            pass

    return "calnav-fallback-machine-id"


try:
    import base64
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.fernet import Fernet
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False


def _derive_key(profile_name: str) -> bytes:
    salt = (profile_name + ":calnav:v1").encode()
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=120_000)
    material = (_machine_id() + ":" + profile_name).encode()
    return base64.urlsafe_b64encode(kdf.derive(material))


def _host(url: str) -> str:
    try:
        p = urlparse(url)
        h = p.netloc or p.path
        return h.removeprefix("www.").lower().split(":")[0]
    except Exception:
        return url.lower()


class PasswordManager:
    def __init__(self, passwords_file: Path, profile_name: str):
        self._file = passwords_file
        self._profile = profile_name
        self._fernet = None
        self._entries: List[Dict] = []
        if _CRYPTO_OK:
            self._fernet = Fernet(_derive_key(profile_name))
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self):
        if not self._file.exists() or not _CRYPTO_OK or not self._fernet:
            self._entries = []
            return
        try:
            raw = self._fernet.decrypt(self._file.read_bytes())
            self._entries = json.loads(raw.decode())
            # Back-fill category for entries saved before this feature
            for e in self._entries:
                e.setdefault("category", DEFAULT_CATEGORY)
        except Exception:
            self._entries = []

    def _save(self):
        if not _CRYPTO_OK or not self._fernet:
            return
        raw = json.dumps(self._entries, ensure_ascii=False).encode()
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_bytes(self._fernet.encrypt(raw))

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def save(self, url: str, username: str, password: str,
             category: str = DEFAULT_CATEGORY):
        """Save or update a credential.  Category is only set on first save."""
        host = _host(url)
        for e in self._entries:
            if e["host"] == host and e["username"] == username:
                e["password"] = password
                e["url"] = url
                self._save()
                return
        self._entries.append({
            "host": host,
            "url": url,
            "username": username,
            "password": password,
            "category": category,
        })
        self._save()

    def update_entry(self, host: str, username: str, *,
                     new_username: Optional[str] = None,
                     new_password: Optional[str] = None,
                     new_category: Optional[str] = None) -> bool:
        """Update fields of an existing entry.  Returns True if found."""
        for e in self._entries:
            if e["host"] == host and e["username"] == username:
                if new_username is not None:
                    e["username"] = new_username
                if new_password is not None:
                    e["password"] = new_password
                if new_category is not None:
                    e["category"] = new_category or DEFAULT_CATEGORY
                self._save()
                return True
        return False

    def get(self, url: str) -> List[Dict]:
        """Return all entries matching the given URL's host."""
        return [e for e in self._entries if e["host"] == _host(url)]

    def all_entries(self) -> List[Dict]:
        return list(self._entries)

    def delete(self, host: str, username: str) -> bool:
        before = len(self._entries)
        self._entries = [
            e for e in self._entries
            if not (e["host"] == host and e["username"] == username)
        ]
        if len(self._entries) < before:
            self._save()
            return True
        return False

    # ── Categories ────────────────────────────────────────────────────────────

    def categories(self) -> List[str]:
        """Sorted list of unique category names present in the vault."""
        return sorted({e.get("category", DEFAULT_CATEGORY) for e in self._entries})

    def rename_category(self, old_name: str, new_name: str):
        new_name = new_name.strip() or DEFAULT_CATEGORY
        for e in self._entries:
            if e.get("category", DEFAULT_CATEGORY) == old_name:
                e["category"] = new_name
        self._save()

    def delete_category(self, name: str):
        """Remove a category — all its entries move to DEFAULT_CATEGORY."""
        for e in self._entries:
            if e.get("category", DEFAULT_CATEGORY) == name:
                e["category"] = DEFAULT_CATEGORY
        self._save()

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, query: str = "", category: Optional[str] = None) -> List[Dict]:
        """Filter entries by text query and/or category.

        - category=None or "Tutte" → all categories
        - query="" → no text filter
        """
        q = query.strip().lower()
        results = []
        for e in self._entries:
            # Category filter
            if category and category != "Tutte":
                if e.get("category", DEFAULT_CATEGORY) != category:
                    continue
            # Text filter
            if q:
                haystack = (
                    e.get("host", "")
                    + " " + e.get("username", "")
                    + " " + e.get("category", "")
                ).lower()
                if q not in haystack:
                    continue
            results.append(e)
        return results

    # ── Password generator ────────────────────────────────────────────────────

    @staticmethod
    def generate_password(length: int = 16, *,
                          uppercase: bool = True,
                          digits: bool = True,
                          symbols: bool = True) -> str:
        """Generate a cryptographically random password."""
        pool = string.ascii_lowercase
        required: List[str] = [secrets.choice(string.ascii_lowercase)]

        if uppercase:
            pool += string.ascii_uppercase
            required.append(secrets.choice(string.ascii_uppercase))
        if digits:
            pool += string.digits
            required.append(secrets.choice(string.digits))
        if symbols:
            sym = "!@#$%^&*()_+-=[]{}|;:,.<>?"
            pool += sym
            required.append(secrets.choice(sym))

        # Fill remaining length with random chars from full pool
        while len(required) < length:
            required.append(secrets.choice(pool))

        # Shuffle with a cryptographic RNG
        lst = required[:length]
        for i in range(len(lst) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            lst[i], lst[j] = lst[j], lst[i]
        return "".join(lst)

    # ── Misc ──────────────────────────────────────────────────────────────────

    def count(self) -> int:
        return len(self._entries)

    @property
    def available(self) -> bool:
        return _CRYPTO_OK
