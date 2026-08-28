"""User settings and named profiles for Facer Studio."""

import json
import os
from pathlib import Path
from typing import Dict, Optional

from .backend import LightingState
from .i18n import DEFAULT_LANGUAGE, normalize_language


BUILTIN_PROFILES = {
    "Фиолетовый пульс": LightingState(mode=1, red=145, green=55, blue=255, brightness=78, speed=4),
    "Cyber Pink": LightingState(mode=4, red=255, green=35, blue=145, brightness=82, speed=5, direction=2),
    "Ледяная волна": LightingState(mode=3, red=65, green=180, blue=255, brightness=72, speed=5, direction=2),
    "Изумрудный импульс": LightingState(mode=5, red=20, green=235, blue=150, brightness=75, speed=4),
}


def default_config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / "facer-studio" / "settings.json"


def _uses_retired_disco_effect(value) -> bool:
    return isinstance(value, dict) and value.get("software_effect") == "disco"


class ProfileStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else default_config_path()
        self.last_state = LightingState()
        self.live_apply = False
        self.language = DEFAULT_LANGUAGE
        self.user_profiles: Dict[str, LightingState] = {}
        self.load()

    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        if not isinstance(data, dict):
            return
        profiles = data.get("profiles", {})
        migrate_retired_settings = (
            "keep_awake_ac" in data
            or _uses_retired_disco_effect(data.get("last_state"))
            or (
                isinstance(profiles, dict)
                and any(_uses_retired_disco_effect(state) for state in profiles.values())
            )
        )
        try:
            self.last_state = LightingState.from_dict(data.get("last_state", {}))
        except (TypeError, ValueError):
            self.last_state = LightingState()
        self.live_apply = bool(data.get("live_apply", False))
        self.language = normalize_language(data.get("language", DEFAULT_LANGUAGE))
        if isinstance(profiles, dict):
            for name, state in profiles.items():
                try:
                    self.user_profiles[str(name)] = LightingState.from_dict(state)
                except (TypeError, ValueError):
                    continue
        if migrate_retired_settings:
            self.save()

    def save(self) -> None:
        self.language = normalize_language(self.language)
        data = {
            "last_state": self.last_state.to_dict(),
            "live_apply": self.live_apply,
            "language": self.language,
            "profiles": {name: state.to_dict() for name, state in self.user_profiles.items()},
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            # Lighting control must keep working even when the config directory is read-only.
            pass

    def all_profiles(self) -> Dict[str, LightingState]:
        profiles = dict(BUILTIN_PROFILES)
        profiles.update(self.user_profiles)
        return profiles

    def state_for(self, name: str) -> Optional[LightingState]:
        return self.all_profiles().get(name)

    def put(self, name: str, state: LightingState) -> None:
        self.user_profiles[name.strip()] = state.normalized()
        self.save()

    def remove(self, name: str) -> bool:
        if name not in self.user_profiles:
            return False
        del self.user_profiles[name]
        self.save()
        return True
