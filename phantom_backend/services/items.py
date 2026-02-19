from __future__ import annotations

import contextlib
import csv
import os
import threading
import unicodedata
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from phantom_backend.config_manager import ConfigManager
from phantom_backend.core.errors import PhantomError
from phantom_backend.services.repo_paths import repo_root_for

_ZIP_HANDLES = {}
_GLOBAL_ZIP_LOCK = threading.Lock()


def normalize_text(text: str) -> str:
    """
    Normalize text for search using standard Unicode normalization.
    This handles:
    - Converting Arabic Presentation Forms (e.g. ﺳﻴﻒ) to standard Arabic (سيف).
    - Removing diacritics.
    - Case folding.
    """
    if not text:
        return ""

    # 1. NFKC Compatibility Decomposition matches Presentation Forms to Standard characters
    text = unicodedata.normalize("NFKC", text)

    # 2. Casefold for case-insensitive matching (stronger than lower())
    text = text.casefold()

    # 3. Remove non-spacing marks (diacritics)
    text = "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )

    return text


@dataclass(frozen=True)
class ItemRow:
    id: int
    name: str
    normalized_name: str
    icon_id: str | None = None
    max_upgrade: int = 0
    raw: dict[str, Any] | None = None


class ItemAssetService:
    def __init__(self, *, game_key: str):
        self._game = game_key

    def _repo_root(self) -> Path:
        return repo_root_for(self._game)

    def items_dir(self) -> Path:
        # Explicit override (useful for Proton/AppImage where the Python process
        # runs under Wine and external assets live next to the .AppImage file).
        #
        # Example value:
        #   Z:\home\user\Downloads\PhantomToolkit\items
        override = os.environ.get("PHANTOM_ITEMS_DIR", "").strip()
        if override:
            p = Path(override)
            if p.exists():
                return p

        # 1. If frozen (PyInstaller), check next to the executable first
        import sys

        if getattr(sys, "frozen", False):
            # PyInstaller: `sys.executable` is the bundled binary path.
            # AppImage: `sys.executable` points INSIDE the mounted image, but the
            # external files live next to the `.AppImage` file on disk.

            # 1a. Check next to the running executable (Windows/Linux onefile)
            exe_dir = Path(sys.executable).resolve().parent
            frozen_items = exe_dir / "items" / self._game
            if frozen_items.exists():
                return frozen_items

            # 1b. AppImage runtime sets $APPIMAGE to the path of the AppImage file.
            # If present, prefer looking next to that file for external assets.
            appimage_path = os.environ.get("APPIMAGE")
            if appimage_path:
                appimage_dir = Path(appimage_path).resolve().parent
                appimage_items = appimage_dir / "items" / self._game
                if appimage_items.exists():
                    return appimage_items

        # 2. Check local project items/{game} (Development mode)
        local_root = Path(__file__).resolve().parents[2]  # 2Pz_Phantom_Toolki
        local_items = local_root / "items" / self._game
        if local_items.exists():
            return local_items

        # Fallback to external repo structure
        # DS3 repo uses items/Images.zip; ER repo has zips too.
        return self._repo_root() / "items"

    def images_zip(self) -> Path:
        # Check specific zip names or glob
        p = self.items_dir() / "Images.zip"
        if p.exists():
            return p
        p2 = self.items_dir() / "images.zip"
        if p2.exists():
            return p2

        # fallback: pick first zip that looks like images
        for z in self.items_dir().glob("*.zip"):
            if "image" in z.name.lower():
                return z
        # Should we raise? If folder is empty, maybe just return a dummy path or raise.
        # raising is fine as it indicates missing assets.
        raise PhantomError(f"Images zip not found in {self.items_dir()}")

    def list_csv_files(self) -> list[str]:
        return sorted([p.name for p in self.items_dir().glob("*.csv")])

    def _load_csv(
        self, csv_name: str, language: str | None = None
    ) -> dict[int, ItemRow]:
        if language is None:
            language = ConfigManager().language
        return _load_csv(self.items_dir() / csv_name, language, self._game)

    def get_item(
        self, *, csv_name: str, item_id: int, language: str | None = None
    ) -> ItemRow:
        table = self._load_csv(csv_name, language)
        if item_id not in table:
            raise PhantomError(f"Item {item_id} not found in {csv_name}")
        return table[item_id]

    def _normalize_weapon_id(self, item_id: int) -> int:
        """
        Normalize weapon ID to base ID to handle upgrades/infusions.
        Elden Ring: upgrades are +0..+25 (last 2 digits). Infusions are often blocks of 100/1000?
        Actually safe bet for ER is typically removing last 2 digits for upgrade level of basic weapons.
        DS3: upgrades +0..+10. Infusions are blocks of 100?

        Let's try a heuristic:
        1. Try exact match (already done in find_item_any_csv).
        2. ER: id - (id % 100) cover +0 to +99 ? +25 is max meaningful.
        3. DS3: id - (id % 100) creates base ID?

        If we assume standard weapons are X00, and +1 is X01...
        """
        # This is a heuristic.
        # Most "base" weapons in CSVs end in 00.
        # So flooring to 100 is a good generic attempt.
        # But some IDs might not end in 00?
        # Let's try flooring to 100.
        return item_id - (item_id % 100)

    def find_item_any_csv(
        self, item_id: int, language: str | None = None, hints: list[str] | None = None
    ) -> ItemRow | None:
        """Find an item by ID across all known CSVs, prioritizing hints."""
        candidates = self.list_csv_files()
        if language is None:
            language = ConfigManager().language

        if hints:
            # Reorder: hints first
            others = [c for c in candidates if c not in hints]
            candidates = hints + others  # Search hints first?
            # Actually, if we provide hints, we probably ONLY want those for correctness?
            # But what if ID is wrong?
            # If "Ash of War in Armor slot", we specifically want to FAIL instead of returning Ash of War.
            # So if hints provided, we should probably restrict to them?
            # But let's support fallback if strictly needed.
            # Given the bug, Strict is better.
            candidates = hints

        # 1. Exact match
        for csv_file in candidates:
            # Handle potential case mismatch in hints if manual strings passed
            # But list_csv_files depends on file system. simpler to just use passed string if it exists?
            # Let's rely on _load_csv handling simple strings.
            table = self._load_csv(csv_file, language)
            if item_id in table:
                return table[item_id]

        # 2. Normalized match (for Upgraded weapons)
        norm_id = self._normalize_weapon_id(item_id)
        if norm_id != item_id:
            for csv_file in candidates:
                table = self._load_csv(csv_file, language)
                if norm_id in table:
                    return table[norm_id]

        return None

    def _get_shared_zip(self) -> zipfile.ZipFile:
        """
        Get a cached handle to the zip file.
        WARNING: zipfile.ZipFile is NOT thread-safe for concurrent reads if using the same handle?
        Actually, in read mode it mostly is if we use `read(name)`.
        However, to be safe and avoid multi-threading issues in FastAPI (which uses threadpool for sync defs),
        we should probably treat this carefully.
        But practically, re-opening for every icon is the bottleneck.
        Let's keep it simple: open once per service instance?
        Service instance is created per request in `api/routes/items.py` (svc = ItemAssetService).
        So caching on `self` is useless if `svc` is recreated.
        We need a class-level or module-level cache.
        """
        zpath = self.images_zip()
        return _get_global_zip_handle(str(zpath))

    def _zip_namelist(self) -> dict[str, str]:
        """Map stem -> full path inside zip for fast lookup."""
        return _get_zip_namelist(str(self.images_zip()))

    def search_items(
        self,
        *,
        csv_name: str | None = None,
        q: str,
        language: str | None = None,
        limit: int = 50,
    ) -> list[ItemRow]:
        """Search items. If csv_name is None, search all."""
        # Normalize the query using the same helper
        qn = normalize_text(q)
        if not qn and not csv_name:
            return []

        if language is None:
            language = ConfigManager().language

        sources = [csv_name] if csv_name else self.list_csv_files()
        hits: list[ItemRow] = []

        for fname in sources:
            table = self._load_csv(fname, language)
            for item in table.values():
                # Compare normalized query against normalized name
                if not qn or qn in item.normalized_name or qn in str(item.id):
                    hits.append(item)
                if len(hits) >= limit:
                    return hits  # Global limit
        return hits

    def read_icon_bytes(self, icon_id: str) -> bytes:
        mapping = self._zip_namelist()

        target = mapping.get(icon_id)
        if not target:
            # Try fuzzy match: keys ending with _{icon_id}
            # This covers MENU_Knowledge_10000 when icon_id is 10000
            suffix = f"_{icon_id}"
            for k, v in mapping.items():
                if k.endswith(suffix):
                    target = v
                    break

        if target:
            zf = self._get_shared_zip()
            # ZipFile.read is thread-safe enough for concurrent reads of different files in Python 3?
            # To be absolutely safe we can lock.
            with _GLOBAL_ZIP_LOCK:
                return zf.read(target)

        raise PhantomError(f"Icon '{icon_id}' not found")

    def read_icon_data(self, icon_id: str) -> tuple[bytes, str]:
        """Read icon data and return (bytes, format_extension)."""
        data = self.read_icon_bytes(icon_id)

        # WebP magic: RIFF....WEBP
        if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return data, "webp"

        # PNG magic
        if data.startswith(b"\x89PNG"):
            return data, "png"

        # Empty/Small
        if len(data) < 4:
            return data, "bin"

        # DDS magic: DDS
        if data.startswith(b"DDS "):
            try:
                import io

                from PIL import Image

                with io.BytesIO(data) as bio, Image.open(bio) as img:
                    out = io.BytesIO()
                    # Convert DDS to WebP on the fly if not optimized yet
                    img.save(out, format="WEBP", quality=85)
                    return out.getvalue(), "webp"
            except Exception:
                # Fallback: return raw DDS
                return data, "dds"

        # Unknown
        return data, "bin"


def _get_global_zip_handle(path: str) -> zipfile.ZipFile:
    with _GLOBAL_ZIP_LOCK:
        try:
            mtime = os.stat(path).st_mtime
        except OSError:
            mtime = 0

        cached = _ZIP_HANDLES.get(path)
        if cached:
            handle, last_mtime = cached
            if last_mtime == mtime:
                return handle
            # File changed, close old and reload
            # File changed, close old and reload
            with contextlib.suppress(Exception):
                handle.close()

        # Open new
        zf = zipfile.ZipFile(path, "r")
        _ZIP_HANDLES[path] = (zf, mtime)
        return zf


_NAMELIST_CACHE = {}


def _get_zip_namelist(zip_path_str: str) -> dict[str, str]:
    """Map stem -> full path inside zip for fast lookup."""
    # Check cache first
    try:
        mtime = os.stat(zip_path_str).st_mtime
    except OSError:
        mtime = 0

    cached = _NAMELIST_CACHE.get(zip_path_str)
    if cached:
        mapping, last_mtime = cached
        if last_mtime == mtime:
            return mapping

    # Refresh
    zf = _get_global_zip_handle(zip_path_str)
    mapping = {}
    for name in zf.namelist():
        stem = Path(name).stem
        if stem not in mapping:
            mapping[stem] = name

    _NAMELIST_CACHE[zip_path_str] = (mapping, mtime)
    return mapping


@lru_cache(maxsize=256)
def _load_csv(path: Path, language: str, game: str) -> dict[int, ItemRow]:
    if not path.exists():
        return {}  # Return empty instead of raising if file missing (e.g. during dev)
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        out: dict[int, ItemRow] = {}
        for row in reader:
            rid = row.get("ID")
            if not rid or not str(rid).isdigit():
                continue
            item_id = int(rid)
            name = row.get(language) or row.get("en") or row.get("name") or f"{item_id}"
            icon_id = row.get("icon_id") or row.get("icon") or None

            # Determine max upgrade level
            upgrade_type = row.get("Upgrade")
            max_upgrade = 0
            if upgrade_type == "Smithing Stones":
                max_upgrade = 25
            elif (
                upgrade_type == "Somber Smithing Stones"
                or game == "ds3"
                and "Weapons" in path.name
            ):
                max_upgrade = 10

            out[item_id] = ItemRow(
                id=item_id,
                name=str(name),
                normalized_name=normalize_text(str(name)),
                icon_id=str(icon_id) if icon_id else None,
                max_upgrade=max_upgrade,
                raw=row,
            )
        return out
