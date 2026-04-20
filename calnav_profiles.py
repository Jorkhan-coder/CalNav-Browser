#!/usr/bin/env python3
"""CalNav — Profile management."""

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

PROFILE_COLORS = [
    "#00D4FF", "#FF6B6B", "#51CF66", "#FFD43B",
    "#CC5DE8", "#FF922B", "#20C997", "#74C0FC",
    "#F06595", "#A9E34B",
]

DATA_DIR = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "CalNav"
PROFILES_DIR = DATA_DIR / "profiles"
INDEX_FILE = DATA_DIR / "profiles.json"
DEFAULT_PROFILE = "default"


@dataclass
class Profile:
    name: str
    display_name: str
    color: str
    created: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def path(self) -> Path:
        return PROFILES_DIR / self.name

    @property
    def passwords_file(self) -> Path:
        return self.path / "passwords.enc"

    @property
    def initial(self) -> str:
        return (self.display_name or self.name)[0].upper()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "color": self.color,
            "created": self.created,
        }

    @staticmethod
    def from_dict(d: dict) -> "Profile":
        return Profile(
            name=d["name"],
            display_name=d.get("display_name", d["name"]),
            color=d.get("color", PROFILE_COLORS[0]),
            created=d.get("created", datetime.now().isoformat()),
        )


class ProfileManager:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        self._profiles: List[Profile] = []
        self._current_name: str = DEFAULT_PROFILE
        self._load()

    def _load(self):
        if INDEX_FILE.exists():
            try:
                data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
                self._profiles = [Profile.from_dict(p) for p in data.get("profiles", [])]
                self._current_name = data.get("current", DEFAULT_PROFILE)
            except Exception:
                self._profiles = []
        if not self._profiles:
            self._create_default()
        if not any(p.name == self._current_name for p in self._profiles):
            self._current_name = self._profiles[0].name

    def _save(self):
        INDEX_FILE.write_text(
            json.dumps(
                {"current": self._current_name,
                 "profiles": [p.to_dict() for p in self._profiles]},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    def _create_default(self):
        p = Profile(name=DEFAULT_PROFILE, display_name="Principale", color=PROFILE_COLORS[0])
        p.path.mkdir(parents=True, exist_ok=True)
        self._profiles = [p]
        self._current_name = DEFAULT_PROFILE
        self._save()

    @property
    def profiles(self) -> List[Profile]:
        return list(self._profiles)

    @property
    def current(self) -> Profile:
        for p in self._profiles:
            if p.name == self._current_name:
                return p
        return self._profiles[0]

    def set_current(self, name: str):
        if any(p.name == name for p in self._profiles):
            self._current_name = name
            self._save()

    def get(self, name: str) -> Optional[Profile]:
        return next((p for p in self._profiles if p.name == name), None)

    def create(self, display_name: str, color: str) -> Profile:
        slug = re.sub(r"[^a-z0-9_]", "", display_name.lower().replace(" ", "_")) or "profilo"
        base, i = slug, 2
        while any(p.name == slug for p in self._profiles):
            slug = f"{base}_{i}"
            i += 1
        p = Profile(name=slug, display_name=display_name, color=color)
        p.path.mkdir(parents=True, exist_ok=True)
        self._profiles.append(p)
        self._save()
        return p

    def delete(self, name: str) -> bool:
        if len(self._profiles) <= 1:
            return False
        for i, p in enumerate(self._profiles):
            if p.name == name:
                if p.path.exists():
                    shutil.rmtree(p.path, ignore_errors=True)
                self._profiles.pop(i)
                if self._current_name == name:
                    self._current_name = self._profiles[0].name
                self._save()
                return True
        return False

    def rename(self, name: str, new_display: str) -> bool:
        p = self.get(name)
        if p:
            p.display_name = new_display
            self._save()
            return True
        return False

    def update_color(self, name: str, color: str) -> bool:
        p = self.get(name)
        if p:
            p.color = color
            self._save()
            return True
        return False
