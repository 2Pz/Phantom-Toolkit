import json
import os
import platform
from pathlib import Path
from typing import Any

CONFIG_FILE = "config.json"


class ConfigManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        # Determine platform-specific config directory
        if platform.system() == "Windows":
            base = Path(os.environ.get("LOCALAPPDATA", "."))
        else:
            base = Path.home() / ".config"

        self._config_dir = base / "PhantomToolkit"
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._config_path = self._config_dir / CONFIG_FILE

        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}
        else:
            self._data = {}

    def _save_config(self):
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        self._data[key] = value
        self._save_config()

    def keys(self):
        return self._data.keys()

    def __iter__(self):
        return iter(self._data.keys())

    @property
    def last_save_dir(self) -> str:
        return self.get("last_save_dir", "")

    @last_save_dir.setter
    def last_save_dir(self, value: str):
        self.set("last_save_dir", value)

    @property
    def language(self) -> str:
        return self.get("language", "en")

    @language.setter
    def language(self, value: str):
        self.set("language", value)

    @property
    def auto_calc_level(self) -> bool:
        return self.get("auto_calc_level", False)

    @auto_calc_level.setter
    def auto_calc_level(self, value: bool):
        self.set("auto_calc_level", value)
