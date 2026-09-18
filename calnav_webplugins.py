"""
calnav_webplugins.py — Avvia in background il servizio locale "WebPlugins"
richiesto dalle pagine web di telecamere IP / NVR (es. Hikvision e OEM
compatibili) per decodificare e renderizzare il video.

Il meccanismo non ha nulla a che vedere con ActiveX: la pagina della
telecamera si collega via socket locale a WebPluginService.exe (porte
34000-34009) e questo disegna il video in una finestra overlay. Per questo
funziona identico sia nel motore IE reale che, in teoria, in un motore
Chromium — ma qui lo avviamo solo quando si apre il motore IE, come richiesto.

I binari (vendor/webplugins/App/) sono bundlati con CalNav: l'utente finale
non deve installare separatamente il "Web Plugins Setup" originale.
"""
from __future__ import annotations

import atexit
import socket
import subprocess
import sys
from pathlib import Path

_SERVICE_EXE = "WebPluginService.exe"
_PORT_RANGE = range(34000, 34010)

_process: "subprocess.Popen | None" = None


def _vendor_dir() -> "Path | None":
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", "")) / "webplugins" / "App"
    else:
        base = Path(__file__).resolve().parent / "vendor" / "webplugins" / "App"
    return base if (base / _SERVICE_EXE).exists() else None


def _already_listening() -> bool:
    for port in _PORT_RANGE:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.15)
            try:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    return True
            except OSError:
                continue
    return False


def ensure_running() -> bool:
    """Assicura che WebPluginService.exe sia attivo. Ritorna True se lo è
    (già in esecuzione o avviato ora), False se non disponibile."""
    global _process

    if sys.platform != "win32":
        return False
    if _process is not None and _process.poll() is None:
        return True
    if _already_listening():
        return True

    vendor = _vendor_dir()
    if vendor is None:
        return False

    try:
        _process = subprocess.Popen(
            [str(vendor / _SERVICE_EXE)],
            cwd=str(vendor),
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        atexit.register(stop)
        return True
    except Exception:
        _process = None
        return False


def stop() -> None:
    global _process
    if _process is not None and _process.poll() is None:
        try:
            _process.terminate()
        except Exception:
            pass
    _process = None
