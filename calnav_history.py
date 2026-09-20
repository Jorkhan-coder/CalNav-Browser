#!/usr/bin/env python3
"""CalNav — Cronologia di navigazione, organizzata "a capitoli" per data.

Ogni pagina visitata è una `Visit`. Le visite vengono raggruppate a due
livelli per la UI: capitolo (giorno) -> sito "master" (dominio) -> singole
pagine visitate su quel dominio quel giorno, in ordine cronologico.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse

# Oltre questa soglia le visite più vecchie vengono scartate: la cronologia
# resta utile (ricerca, capitoli, suggerimenti) senza crescere senza limite.
MAX_ENTRIES = 15000


def domain_of(url: str) -> str:
    """Dominio 'master' di un url — senza www., minuscolo."""
    try:
        host = (urlparse(url).netloc or url).lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return url


@dataclass
class Visit:
    id: str
    url: str
    title: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {"id": self.id, "url": self.url, "title": self.title, "timestamp": self.timestamp}

    @staticmethod
    def from_dict(d: dict) -> "Visit":
        return Visit(
            id=d.get("id", str(uuid.uuid4())),
            url=d["url"],
            title=d.get("title", d["url"]),
            timestamp=d.get("timestamp", datetime.now().isoformat()),
        )

    @property
    def dt(self) -> datetime:
        try:
            return datetime.fromisoformat(self.timestamp)
        except Exception:
            return datetime.now()

    @property
    def domain(self) -> str:
        return domain_of(self.url)


class HistoryManager:
    def __init__(self, history_file: Path):
        self._file = history_file
        self._visits: List[Visit] = []
        self._load()

    def _load(self):
        if not self._file.exists():
            self._visits = []
            return
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            self._visits = [Visit.from_dict(v) for v in data.get("visits", [])]
        except Exception:
            self._visits = []

    def _save(self):
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps({"visits": [v.to_dict() for v in self._visits]},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── Recording ────────────────────────────────────────────────────────────
    def add_visit(self, url: str, title: str) -> Visit:
        v = Visit(id=str(uuid.uuid4()), url=url, title=(title or "").strip() or url)
        self._visits.append(v)
        if len(self._visits) > MAX_ENTRIES:
            self._visits = self._visits[-MAX_ENTRIES:]
        self._save()
        return v

    def update_last_title(self, url: str, title: str):
        """Aggiorna il titolo dell'ultima visita registrata per questo url —
        usato per le pagine SPA che cambiano <title> senza una nuova
        navigazione, così da non creare una riga duplicata per ogni update."""
        title = (title or "").strip()
        if not title:
            return
        for v in reversed(self._visits):
            if v.url == url:
                if v.title != title:
                    v.title = title
                    self._save()
                return

    # ── Reading ──────────────────────────────────────────────────────────────
    def get_all(self) -> List[Visit]:
        return sorted(self._visits, key=lambda v: v.timestamp, reverse=True)

    def count(self) -> int:
        return len(self._visits)

    def suggestions(self, prefix: str, limit: int = 8) -> List[Visit]:
        """Un risultato per url (l'ultima visita), più recenti prima —
        per il suggerimento nella barra degli indirizzi."""
        q = prefix.strip().lower()
        if not q:
            return []
        seen = set()
        out: List[Visit] = []
        for v in self.get_all():
            if v.url in seen:
                continue
            if q in v.url.lower() or q in v.title.lower():
                seen.add(v.url)
                out.append(v)
                if len(out) >= limit:
                    break
        return out

    def grouped_by_day(self, query: str = "") -> List[dict]:
        """Restituisce i "capitoli": una lista, dal più recente,
        di {date_key, date, total, sites: [{domain, count, last_visit, visits}]}.
        `visits` dentro ogni sito è ordinata cronologicamente (orario asc)."""
        visits = self.get_all()
        q = query.strip().lower()
        if q:
            visits = [v for v in visits if q in v.title.lower() or q in v.url.lower()]

        days: Dict[str, List[Visit]] = {}
        day_order: List[str] = []
        for v in visits:
            key = v.dt.strftime("%Y-%m-%d")
            if key not in days:
                days[key] = []
                day_order.append(key)
            days[key].append(v)

        chapters = []
        for key in day_order:
            day_visits = days[key]
            sites: Dict[str, List[Visit]] = {}
            site_order: List[str] = []
            for v in day_visits:
                d = v.domain
                if d not in sites:
                    sites[d] = []
                    site_order.append(d)
                sites[d].append(v)

            site_groups = []
            for d in site_order:
                svisits = sites[d]  # già in ordine decrescente (ereditato dal giorno)
                site_groups.append({
                    "domain": d,
                    "count": len(svisits),
                    "last_visit": svisits[0],
                    "visits": sorted(svisits, key=lambda v: v.timestamp),  # orario asc
                })
            site_groups.sort(key=lambda g: g["last_visit"].timestamp, reverse=True)

            chapters.append({
                "date_key": key,
                "date": datetime.strptime(key, "%Y-%m-%d").date(),
                "total": len(day_visits),
                "sites": site_groups,
            })
        return chapters

    def on_this_day(self) -> List[Visit]:
        """'Accadde oggi': pagine visitate nello stesso giorno/mese di oggi,
        in anni o mesi passati (esclude le visite odierne)."""
        today = date.today()
        out = []
        for v in self.get_all():
            d = v.dt.date()
            if d == today:
                continue
            if d.month == today.month and d.day == today.day:
                out.append(v)
        return out

    # ── Deletion ─────────────────────────────────────────────────────────────
    def delete_visit(self, visit_id: str):
        self._visits = [v for v in self._visits if v.id != visit_id]
        self._save()

    def delete_site_on_day(self, domain: str, date_key: str):
        self._visits = [
            v for v in self._visits
            if not (v.domain == domain and v.dt.strftime("%Y-%m-%d") == date_key)
        ]
        self._save()

    def delete_day(self, date_key: str):
        self._visits = [v for v in self._visits if v.dt.strftime("%Y-%m-%d") != date_key]
        self._save()

    def delete_since(self, cutoff) -> None:
        """Cancella le visite più recenti di `cutoff` (un datetime).
        Passare `None` per cancellare tutto (equivalente a `clear_all`)."""
        if cutoff is None:
            self.clear_all()
            return
        self._visits = [v for v in self._visits if v.dt < cutoff]
        self._save()

    def clear_all(self):
        self._visits = []
        self._save()
