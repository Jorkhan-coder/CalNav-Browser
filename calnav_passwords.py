#!/usr/bin/env python3
"""CalNav — Password manager with per-profile Fernet encryption."""

import json
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

try:
    import winreg as _winreg

    def _machine_id() -> str:
        try:
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
            return "calnav-fallback-machine-id"
except ImportError:
    def _machine_id() -> str:
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

    def _load(self):
        if not self._file.exists() or not _CRYPTO_OK or not self._fernet:
            self._entries = []
            return
        try:
            raw = self._fernet.decrypt(self._file.read_bytes())
            self._entries = json.loads(raw.decode())
        except Exception:
            self._entries = []

    def _save(self):
        if not _CRYPTO_OK or not self._fernet:
            return
        raw = json.dumps(self._entries, ensure_ascii=False).encode()
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_bytes(self._fernet.encrypt(raw))

    def save(self, url: str, username: str, password: str):
        host = _host(url)
        for e in self._entries:
            if e["host"] == host and e["username"] == username:
                e["password"] = password
                e["url"] = url
                self._save()
                return
        self._entries.append({"host": host, "url": url, "username": username, "password": password})
        self._save()

    def get(self, url: str) -> List[Dict]:
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

    def count(self) -> int:
        return len(self._entries)

    @property
    def available(self) -> bool:
        return _CRYPTO_OK
