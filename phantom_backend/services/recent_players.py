import json
import os
import platform
from datetime import datetime
from pathlib import Path
from typing import Any

from phantom_backend.api.models import PlayerDetails


class RecentPlayersService:
    _instances: dict[str, "RecentPlayersService"] = {}

    def __new__(cls, game_key: str):
        if game_key not in cls._instances:
            instance = super().__new__(cls)
            instance._game_key = game_key
            instance._load_recent_players()
            cls._instances[game_key] = instance
        return cls._instances[game_key]

    def _get_storage_path(self) -> Path:
        if platform.system() == "Windows":
            base_dir = Path(os.environ.get("LOCALAPPDATA", "."))
        else:
            base_dir = Path.home() / ".config"

        config_dir = base_dir / "PhantomToolkit"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / f"recent_players_{self._game_key}.json"

    def _load_recent_players(self):
        self._path = self._get_storage_path()
        self._players: list[dict[str, Any]] = []

        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._players = data
            except Exception:
                self._players = []

    def _save_recent_players(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._players, f, indent=2)
        except Exception:
            pass

    def add_players(self, players: list[PlayerDetails]):
        if not players:
            return

        added_or_updated = False

        # We assume players is from list_players and contains all current valid non-local players.
        for p in players:
            if p.player_num == 0 or not p.is_valid:
                continue

            # Check if player already exists in the recent list (match by steamId if available, else name)
            # Identifying by SteamID is best, but fallback to name is necessary.
            steam_id = p.stats.get("steamId") if p.stats else None

            # Convert PlayerDetails to dict
            p_dict = p.model_dump()
            found = False
            for i, rp in enumerate(self._players):
                rp_steam_id = rp.get("stats", {}).get("steamId")

                # If steam ID matches, or name matches (when steam ID is absent)
                if steam_id and rp_steam_id == steam_id:
                    # Update all details EXCEPT last_seen, so we keep the first time we saw them
                    # OR we could update it to show the LAST time they were seen in the session.
                    # Since the user requested it not keep updating, we'll keep the existing time.
                    old_last_seen = rp.get("last_seen")
                    self._players[i] = p_dict
                    self._players[i]["last_seen"] = old_last_seen
                    found = True
                    break
                elif not steam_id and not rp_steam_id and rp.get("name") == p.name:
                    old_last_seen = rp.get("last_seen")
                    self._players[i] = p_dict
                    self._players[i]["last_seen"] = old_last_seen
                    found = True
                    break

            if not found:
                p_dict["last_seen"] = datetime.now().isoformat()
                self._players.append(p_dict)

            added_or_updated = True

        if added_or_updated:
            # Sort by last_seen descending
            self._players.sort(key=lambda x: x.get("last_seen", ""), reverse=True)

            # Keep only the last 50 players
            if len(self._players) > 50:
                self._players = self._players[:50]

            self._save_recent_players()

    def get_recent_players(self) -> list[PlayerDetails]:
        return [PlayerDetails(**p) for p in self._players]
