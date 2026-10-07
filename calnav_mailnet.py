#!/usr/bin/env python3
"""CalNav — MailGuard: impostazioni per profilo e controlli di rete *opzionali*.

- Store: opzioni (rdap / feeds / auto), mittenti fidati e cache RDAP, in
  <profilo>/mailguard.json.
- RDAP: età di registrazione di un dominio. Invia SOLO il nome del dominio a
  rdap.org (che reindirizza al registro competente).
- Feed di phishing noti (OpenPhish, Phishing.Database): l'elenco viene
  SCARICATO e il confronto avviene in locale, quindi nessun link della tua
  posta lascia il computer.

Tutto è fail-silent: se la rete non c'è, l'analisi locale prosegue.
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote, urlparse
import urllib.request

UA = "CalNav-MailGuard/1.0 (+https://github.com/Jorkhan-coder/CalNav-Browser)"
RDAP_TTL = 7 * 86400          # età di un dominio: cambia lentamente
RDAP_FAIL_TTL = 3600          # non riprovare subito un lookup fallito

FEEDS = (
    # (nome, url, ttl secondi, tipo, file, max byte)
    ("OpenPhish",
     "https://raw.githubusercontent.com/openphish/public_feed/refs/heads/main/feed.txt",
     6 * 3600, "urls", "openphish.txt", 2_000_000),
    ("Phishing.Database",
     "https://raw.githubusercontent.com/Phishing-Database/Phishing.Database/master/phishing-domains-ACTIVE.txt",
     24 * 3600, "hosts", "phishingdb.txt", 30_000_000),
)


# ── Impostazioni per profilo ─────────────────────────────────────────────────
class MailGuardStore:
    DEFAULTS = {"rdap": False, "feeds": False, "auto": False, "trusted": [], "rdap_cache": {}}

    def __init__(self, path):
        self.path = Path(path)
        self._d = json.loads(json.dumps(self.DEFAULTS))
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self._d.update({k: v for k, v in loaded.items() if k in self.DEFAULTS})
        except Exception:
            pass

    @property
    def feed_dir(self) -> Path:
        return self.path.parent / "mailguard_feeds"

    def get(self, key):
        return self._d.get(key)

    def set(self, key, value):
        self._d[key] = value
        self.save()

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._d, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)
        except Exception:
            pass

    # mittenti fidati (indirizzo esatto, minuscolo)
    def is_trusted(self, email: str) -> bool:
        return (email or "").strip().lower() in self._d["trusted"]

    def trust(self, email: str):
        e = (email or "").strip().lower()
        if e and e not in self._d["trusted"]:
            self._d["trusted"].append(e)
            self.save()

    def untrust(self, email: str):
        e = (email or "").strip().lower()
        if e in self._d["trusted"]:
            self._d["trusted"].remove(e)
            self.save()


# ── HTTP ─────────────────────────────────────────────────────────────────────
def _http_get(url: str, timeout: float = 6, max_bytes: int = 2_000_000) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("risposta troppo grande")
    return data


# ── RDAP: età del dominio ────────────────────────────────────────────────────
def _parse_dt(s: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def domain_age_days(domain: str, store: Optional[MailGuardStore] = None) -> Optional[int]:
    """Giorni dalla registrazione del dominio, None se sconosciuto."""
    domain = (domain or "").lower().strip(".")
    cache = store.get("rdap_cache") if store else {}
    now = time.time()
    hit = cache.get(domain) if cache is not None else None
    if hit:
        ttl = RDAP_TTL if hit.get("age") is not None else RDAP_FAIL_TTL
        if now - hit.get("t", 0) < ttl:
            return hit.get("age")
    age = None
    try:
        j = json.loads(_http_get("https://rdap.org/domain/" + quote(domain), timeout=6))
        for ev in j.get("events", []):
            if ev.get("eventAction") == "registration":
                dt = _parse_dt(ev.get("eventDate", ""))
                if dt:
                    age = max(0, (datetime.now(timezone.utc) - dt).days)
                break
    except Exception:
        age = None
    if cache is not None and store is not None:
        cache[domain] = {"t": now, "age": age}
    return age


# ── Feed di phishing noti ────────────────────────────────────────────────────
def refresh_feeds(feed_dir: Path, timeout: float = 15):
    feed_dir.mkdir(parents=True, exist_ok=True)
    for name, url, ttl, _kind, fname, max_bytes in FEEDS:
        path = feed_dir / fname
        try:
            if path.exists() and time.time() - path.stat().st_mtime < ttl:
                continue
            data = _http_get(url, timeout=timeout, max_bytes=max_bytes)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, path)
        except Exception:
            continue


def _norm_url(u: str) -> str:
    u = (u or "").strip().lower()
    for pre in ("https://", "http://"):
        if u.startswith(pre):
            u = u[len(pre):]
    if u.startswith("www."):
        u = u[4:]
    return u.rstrip("/")


def feed_hits(feed_dir: Path, urls: Iterable[str]) -> List[Tuple[str, str]]:
    """[(url, nome feed)] per i link presenti nei feed scaricati."""
    norm = {}
    hosts = {}
    for u in urls:
        n = _norm_url(u)
        if not n:
            continue
        norm[n] = u
        try:
            h = (urlparse(u).hostname or "").lower()
        except Exception:
            h = ""
        if h.startswith("www."):
            h = h[4:]
        if h:
            hosts[h] = u
    hits: List[Tuple[str, str]] = []
    if not norm:
        return hits
    for name, _url, _ttl, kind, fname, _mb in FEEDS:
        path = feed_dir / fname
        if not path.exists():
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    n = _norm_url(line)
                    if not n or n.startswith("#"):
                        continue
                    if kind == "urls":
                        if n in norm:
                            hits.append((norm[n], name))
                        elif "/" not in n and n in hosts:      # voce del feed = intero host
                            hits.append((hosts[n], name))
                    elif n in hosts:
                        hits.append((hosts[n], name))
        except Exception:
            continue
    seen, out = set(), []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


# ── Orchestrazione (da chiamare in un thread) ────────────────────────────────
def enrich(store: MailGuardStore, domains: List[str], urls: List[str],
           use_rdap: bool, use_feeds: bool, budget: float = 9.0) -> dict:
    """Esegue i controlli di rete abilitati. Ritorna {'ages': {dom: giorni|None}, 'listed': [(url, feed)]}."""
    out = {"ages": {}, "listed": [], "rdap": use_rdap, "feeds": use_feeds}
    t0 = time.time()
    if use_feeds:
        refresh_feeds(store.feed_dir, timeout=max(3, budget - 2))
        out["listed"] = feed_hits(store.feed_dir, urls)
    if use_rdap and domains:
        left = max(1.0, budget - (time.time() - t0))
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(domain_age_days, d, store): d for d in domains[:8]}
            done, _pending = wait(futs, timeout=left)
            for f, d in futs.items():
                if f in done:
                    try:
                        out["ages"][d] = f.result()
                    except Exception:
                        out["ages"][d] = None
        store.save()
    return out
