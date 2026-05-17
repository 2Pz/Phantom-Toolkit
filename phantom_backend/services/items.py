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
    category: str | None = None
    is_only_one: bool = False
    max_num: int | None = None
    raw: dict[str, Any] | None = None


def _load_goods_csv(game_key: str) -> dict[int, ItemRow]:
    """Load EquipParamGoods.csv for a game, returning the full table."""
    try:
        svc = ItemAssetService(game_key=game_key)
        csv_path = svc.items_dir() / "EquipParamGoods.csv"
        if csv_path.exists():
            return _load_csv(csv_path, "en", game_key)
    except Exception:
        pass
    return {}


def load_is_only_one_map(game_key: str) -> dict[int, bool]:
    """Load isOnlyOne column from EquipParamGoods.csv for a game."""
    return {
        item_id: row.is_only_one for item_id, row in _load_goods_csv(game_key).items()
    }


def load_max_num_map(game_key: str) -> dict[int, int | None]:
    """Load maxNum column from EquipParamGoods.csv for a game.

    Returns a dict mapping item base ID -> max_num (or None if missing).
    """
    return {item_id: row.max_num for item_id, row in _load_goods_csv(game_key).items()}


def group_weapon_variants(items: list[dict]) -> list[dict]:
    """Group weapon items by base ID, returning base entries with variant lists.

    Infusible weapons have affinity variants at id = base + n*100.
    Groups by base_id = id - (id % 10000). Single-item groups are unique weapons.
    """
    groups: dict[int, list[dict]] = {}
    for item in items:
        base_id = item["id"] - (item["id"] % 10000)
        groups.setdefault(base_id, []).append(item)

    result: list[dict] = []
    for group in groups.values():
        if len(group) == 1:
            result.append({**group[0], "variants": None})
        else:
            base = next((i for i in group if i["id"] % 10000 == 0), group[0])
            variants = [
                {"id": i["id"], "name": i["name"]}
                for i in group
                if i["id"] != base["id"]
            ]
            result.append(
                {
                    **base,
                    "base_id": base["id"],
                    "base_name": base["name"],
                    "variants": variants,
                }
            )
    return result


SPIRIT_SUMMON_CATEGORIES = frozenset(
    {"Spirit Summon - Lesser", "Spirit Summon - Greater"}
)


def group_spirit_summons(items: list[dict]) -> list[dict]:
    """Group spirit summon goods by base ID (id - id % 1000), returning base entries with variant lists.

    Spirit summons have upgrade levels +0..+10 at id = base + level.
    Groups by base_id = id - (id % 1000). Non-spirit items pass through unmodified.
    """
    spirit_items = [i for i in items if i.get("category") in SPIRIT_SUMMON_CATEGORIES]
    other_items = [
        i for i in items if i.get("category") not in SPIRIT_SUMMON_CATEGORIES
    ]

    groups: dict[int, list[dict]] = {}
    for item in spirit_items:
        base_id = item["id"] - (item["id"] % 1000)
        groups.setdefault(base_id, []).append(item)

    result = list(other_items)
    for group in groups.values():
        if len(group) == 1:
            result.append({**group[0], "variants": None})
        else:
            base = next((i for i in group if i["id"] % 1000 == 0), group[0])
            variants = [
                {"id": i["id"], "name": i["name"]}
                for i in group
                if i["id"] != base["id"]
            ]
            result.append(
                {
                    **base,
                    "base_id": base["id"],
                    "base_name": base["name"],
                    "variants": variants,
                }
            )
    return result


# Maps internal game keys to physical directory names in the items/ folder.
_GAME_DIR_MAP: dict[str, list[str]] = {
    "eldenring": ["ER", "eldenring", "EldenRing"],
    "ds3": ["DS3", "ds3", "DARK_SOULS_3"],
}


def _resolve_items_dir(root: Path, game_key: str) -> Path | None:
    """Try each known directory name for a game key under root."""
    for name in _GAME_DIR_MAP.get(game_key, [game_key]):
        p = root / name
        if p.exists():
            return p
    return None


class ItemAssetService:
    def __init__(self, *, game_key: str):
        self._game = game_key

    def _repo_root(self) -> Path:
        return repo_root_for(self._game)

    def items_dir(self) -> Path:
        # Explicit override (useful for Proton/AppImage where the Python process
        # runs under Wine and external assets live next to the .AppImage file).
        override = os.environ.get("PHANTOM_ITEMS_DIR", "").strip()
        if override:
            p = Path(override)
            if p.exists():
                return p

        # 1. If frozen (PyInstaller), check next to the executable first
        import sys

        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            found = _resolve_items_dir(exe_dir / "items", self._game)
            if found:
                return found

            appimage_path = os.environ.get("APPIMAGE")
            if appimage_path:
                appimage_dir = Path(appimage_path).resolve().parent
                found = _resolve_items_dir(appimage_dir / "items", self._game)
                if found:
                    return found

        # 2. Check local project items/{game} (Development mode)
        local_root = Path(__file__).resolve().parents[2]
        found = _resolve_items_dir(local_root / "items", self._game)
        if found:
            return found

        # Fallback to external repo structure
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

    def get_distinct_categories(self, csv_name: str, column: str) -> tuple[str, ...]:
        """Return all distinct values from a column in a CSV file."""
        path = self.items_dir() / csv_name
        return _distinct_csv_values(path, column)

    def get_distinct_weapon_categories(self) -> list[str]:
        """Return all weapon categories from EquipParamWeapon.csv, excluding ammo types."""
        path = self.items_dir() / "EquipParamWeapon.csv"
        all_cats = _distinct_csv_values(path, "category")
        return [c for c in all_cats if c.lower() not in ("arrow", "bolt")]

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
        """Find an item by ID, optionally restricting to hinted CSV names."""
        if language is None:
            language = ConfigManager().language

        candidates = hints or self.list_csv_files()

        def _search(files: list[str]) -> ItemRow | None:
            for csv_file in files:
                table = self._load_csv(csv_file, language)
                if item_id in table:
                    return table[item_id]
            return None

        found = _search(candidates)
        if found:
            return found

        # Normalized match for upgraded weapons
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

    def enrich_weapon(self, item_id: int, language: str | None = None) -> dict | None:
        """Given any weapon variant ID, return the grouped entry with all variants/baseId/baseName."""
        table = self._load_csv("EquipParamWeapon.csv", language)
        base_id = item_id - (item_id % 10000)
        matching = [
            row for row in table.values() if row.id - (row.id % 10000) == base_id
        ]
        if not matching:
            return None
        items_dict = [row.__dict__ for row in matching]
        grouped = group_weapon_variants(items_dict)
        return grouped[0] if grouped else None

    def enrich_goods(self, item_id: int, language: str | None = None) -> dict | None:
        """Given any goods ID, return grouped entry with variants for spirit summons.

        For spirit summons, groups by id - (id % 1000). Non-spirit goods return as-is.
        """
        table = self._load_csv("EquipParamGoods.csv", language)
        base_id = item_id - (item_id % 1000)
        matching = [
            row for row in table.values() if row.id - (row.id % 1000) == base_id
        ]
        if not matching:
            return None
        items_dict = [row.__dict__ for row in matching]
        grouped = group_spirit_summons(items_dict)
        # If it's not a spirit summon, return as single item
        if grouped:
            return grouped[0]
        return items_dict[0]

    def search_items(
        self,
        *,
        csv_name: str | None = None,
        q: str,
        categories: list[str] | None = None,
        language: str | None = None,
        limit: int = 50,
    ) -> list[ItemRow]:
        """Search items.

        If csv_name is None, search all CSVs for the game.
        If categories is provided, only items matching those categories are returned.
        """
        qn = normalize_text(q)
        if language is None:
            language = ConfigManager().language

        sources = [csv_name] if csv_name else self.list_csv_files()
        hits: list[ItemRow] = []

        for fname in sources:
            table = self._load_csv(fname, language)
            for item in table.values():
                if categories and item.category not in categories:
                    continue
                if qn and qn not in item.normalized_name and qn not in str(item.id):
                    continue
                hits.append(item)
                if len(hits) >= limit:
                    return hits
        return hits

    def read_icon_bytes(self, icon_id: str) -> bytes:
        mapping = self._zip_namelist()

        target = mapping.get(icon_id)
        if not target:
            # Fuzzy match: keys ending with _{icon_id}
            # Covers MENU_Knowledge_10000 when icon_id is 10000
            suffix = f"_{icon_id}"
            for k, v in mapping.items():
                if k.endswith(suffix):
                    target = v
                    break

        if not target and icon_id.isdigit():
            # Some icon_ids need zero-padding (e.g. "3829" -> "_03829")
            padded = icon_id.zfill(5)
            suffix = f"_{padded}"
            for k, v in mapping.items():
                if k.endswith(suffix):
                    target = v
                    break

        if target:
            zf = self._get_shared_zip()
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


@lru_cache(maxsize=32)
def _distinct_csv_values(path: Path, column: str) -> tuple[str, ...]:
    """Read all distinct values from a column in a CSV file."""
    if not path.exists():
        return ()
    values: set[str] = set()
    with path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            val = row.get(column)
            if val:
                val = val.strip('" ')
                if val:
                    values.add(val)
    return tuple(sorted(values))


@lru_cache(maxsize=256)
def _load_csv(path: Path, language: str, game: str) -> dict[int, ItemRow]:
    if not path.exists():
        return {}  # Return empty instead of raising if file missing (e.g. during dev)
    with path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        out: dict[int, ItemRow] = {}
        for row in reader:
            rid = row.get("ID")
            if not rid or not str(rid).isdigit():
                continue
            item_id = int(rid)
            name = row.get(language) or row.get("en") or row.get("name") or f"{item_id}"
            icon_id = row.get("icon_id") or row.get("icon") or None

            # Read category (or goods_type for Goods CSV)
            category = row.get("category") or row.get("goods_type") or None
            if category:
                category = category.strip('" ')

            # Determine max upgrade level
            upgrade_type = row.get("Upgrade")
            max_upgrade = 0
            if upgrade_type == "Smithing Stones":
                max_upgrade = 25
            elif upgrade_type in ("Somber Smithing Stones", "Titanite"):
                max_upgrade = 10
            elif upgrade_type in ("Twinkling Titanite", "Titanite Scale"):
                max_upgrade = 5

            is_only_one = row.get("isOnlyOne", "0").replace('"', "").strip() == "1"
            raw_max = row.get("maxNum")
            max_num = (
                int(raw_max.replace('"', "").strip()) if raw_max is not None else None
            )

            out[item_id] = ItemRow(
                id=item_id,
                name=str(name),
                normalized_name=normalize_text(str(name)),
                icon_id=str(icon_id) if icon_id else None,
                max_upgrade=max_upgrade,
                category=category,
                is_only_one=is_only_one,
                max_num=max_num,
                raw=row,
            )
        return out
