#!/usr/bin/env python3
"""CalNav — Tab session & group persistence."""

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class TabGroup:
    id: str
    name: str
    color: str
    collapsed: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name,
            "color": self.color, "collapsed": self.collapsed,
        }

    @staticmethod
    def from_dict(d: dict) -> "TabGroup":
        return TabGroup(
            id=d["id"], name=d["name"], color=d["color"],
            collapsed=d.get("collapsed", False),
        )

    @staticmethod
    def new(name: str, color: str) -> "TabGroup":
        return TabGroup(id=str(uuid.uuid4()), name=name, color=color)


@dataclass
class SavedTab:
    url: str
    title: str
    group_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {"url": self.url, "title": self.title, "group_id": self.group_id}

    @staticmethod
    def from_dict(d: dict) -> "SavedTab":
        return SavedTab(
            url=d.get("url", ""),
            title=d.get("title", ""),
            group_id=d.get("group_id"),
        )


class SessionManager:
    def __init__(self, session_file: Path):
        self._file = session_file

    def save(self, groups: List[TabGroup], tabs: List[SavedTab], active_idx: int):
        if not tabs:
            return
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps(
                {
                    "active": active_idx,
                    "groups": [g.to_dict() for g in groups],
                    "tabs":   [t.to_dict() for t in tabs],
                },
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    def load(self):
        """Returns (active_idx, groups, tabs). Empty lists if no session."""
        if not self._file.exists():
            return 0, [], []
        try:
            data  = json.loads(self._file.read_text(encoding="utf-8"))
            groups = [TabGroup.from_dict(g) for g in data.get("groups", [])]
            tabs   = [SavedTab.from_dict(t)  for t in data.get("tabs",   [])]
            active = int(data.get("active", 0))
            return active, groups, tabs
        except Exception:
            return 0, [], []
