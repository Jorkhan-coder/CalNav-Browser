#!/usr/bin/env python3
"""CalNav — Bookmark manager with categories and pin support."""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

UNCATEGORIZED = "Senza categoria"


@dataclass
class Bookmark:
    id: str
    url: str
    title: str
    category: str
    pinned: bool
    created: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "category": self.category,
            "pinned": self.pinned,
            "created": self.created,
        }

    @staticmethod
    def from_dict(d: dict) -> "Bookmark":
        return Bookmark(
            id=d.get("id", str(uuid.uuid4())),
            url=d["url"],
            title=d.get("title", d["url"]),
            category=d.get("category", UNCATEGORIZED),
            pinned=d.get("pinned", False),
            created=d.get("created", datetime.now().isoformat()),
        )


class BookmarkManager:
    def __init__(self, bookmarks_file: Path):
        self._file = bookmarks_file
        self._bookmarks: List[Bookmark] = []
        self._categories: List[str] = []
        self._load()

    def _load(self):
        if not self._file.exists():
            self._bookmarks = []
            self._categories = []
            return
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            self._bookmarks = [Bookmark.from_dict(b) for b in data.get("bookmarks", [])]
            self._categories = data.get("categories", [])
        except Exception:
            self._bookmarks = []
            self._categories = []

    def _save(self):
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps(
                {"categories": self._categories,
                 "bookmarks": [b.to_dict() for b in self._bookmarks]},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _sorted(bookmarks: List[Bookmark]) -> List[Bookmark]:
        pinned   = sorted([b for b in bookmarks if b.pinned],     key=lambda b: b.title.lower())
        unpinned = sorted([b for b in bookmarks if not b.pinned], key=lambda b: b.title.lower())
        return pinned + unpinned

    # ── Categories ────────────────────────────────────────────────────────────
    @property
    def categories(self) -> List[str]:
        return list(self._categories)

    def add_category(self, name: str) -> bool:
        name = name.strip()
        if name and name not in self._categories and name != UNCATEGORIZED:
            self._categories.append(name)
            self._save()
            return True
        return False

    def rename_category(self, old: str, new: str) -> bool:
        new = new.strip()
        if not new or new == old or new in self._categories:
            return False
        if old in self._categories:
            self._categories[self._categories.index(old)] = new
            for b in self._bookmarks:
                if b.category == old:
                    b.category = new
            self._save()
            return True
        return False

    def delete_category(self, name: str):
        if name in self._categories:
            self._categories.remove(name)
            for b in self._bookmarks:
                if b.category == name:
                    b.category = UNCATEGORIZED
            self._save()

    # ── Bookmarks ─────────────────────────────────────────────────────────────
    def add(self, url: str, title: str, category: str, pinned: bool = False) -> Bookmark:
        b = Bookmark(
            id=str(uuid.uuid4()),
            url=url,
            title=title.strip() or url,
            category=category if category else UNCATEGORIZED,
            pinned=pinned,
        )
        self._bookmarks.append(b)
        self._save()
        return b

    def remove(self, bookmark_id: str):
        self._bookmarks = [b for b in self._bookmarks if b.id != bookmark_id]
        self._save()

    def update(self, bookmark_id: str, **kwargs):
        for b in self._bookmarks:
            if b.id == bookmark_id:
                for k, v in kwargs.items():
                    setattr(b, k, v)
                self._save()
                return

    def get_all(self) -> List[Bookmark]:
        return self._sorted(self._bookmarks)

    def get_by_category(self, category: str) -> List[Bookmark]:
        return self._sorted([b for b in self._bookmarks if b.category == category])

    def get_pinned(self) -> List[Bookmark]:
        return sorted([b for b in self._bookmarks if b.pinned], key=lambda b: b.title.lower())

    def get_uncategorized(self) -> List[Bookmark]:
        return self._sorted([b for b in self._bookmarks if b.category == UNCATEGORIZED])

    def is_bookmarked(self, url: str) -> Optional[Bookmark]:
        return next((b for b in self._bookmarks if b.url == url), None)

    def count(self) -> int:
        return len(self._bookmarks)

    def count_pinned(self) -> int:
        return sum(1 for b in self._bookmarks if b.pinned)

    def count_by_category(self, category: str) -> int:
        return sum(1 for b in self._bookmarks if b.category == category)

    def count_uncategorized(self) -> int:
        return sum(1 for b in self._bookmarks if b.category == UNCATEGORIZED)
