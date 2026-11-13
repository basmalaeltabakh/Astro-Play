"""Tiny JSON settings store (language, music, sound effects). Survives restarts; never crashes the game."""
import json
from dataclasses import dataclass, asdict
from pathlib import Path

from . import config


@dataclass
class Settings:
    lang: str = "en"
    music: bool = True
    sfx: bool = True
    music_volume: float = 0.5
    sfx_volume: float = 0.8

    @classmethod
    def load(cls, path=None) -> "Settings":
        path = Path(path or config.SETTINGS_PATH)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            s = cls()
            for k, v in raw.items():
                if hasattr(s, k) and type(getattr(s, k)) is type(v):
                    setattr(s, k, v)
            if s.lang not in ("en", "ar"):
                s.lang = "en"
            s.music_volume = max(0.0, min(1.0, s.music_volume))
            s.sfx_volume = max(0.0, min(1.0, s.sfx_volume))
            return s
        except Exception:
            return cls()

    def save(self, path=None):
        path = Path(path or config.SETTINGS_PATH)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        except Exception:  # pragma: no cover - read-only folder etc.
            pass
