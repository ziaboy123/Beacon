"""NBT parsing for playerdata (.dat) and level.dat.

Verified 2026-09-13 against the real live TheUltimateRealm world (1.21.11):
item stacks use the 1.20.5+ schema (lowercase `count`, `components`
compound with `minecraft:enchantments`/`minecraft:custom_name`/etc.), and
level.dat stores spawn as a nested `spawn.pos` int array and game rules as
lowercase, namespaced `game_rules` with typed values — not the legacy flat
`SpawnX`/`GameRules` shape. Both old and new shapes are handled.

Slot-number handling is defensive on purpose (bucketed by known ranges with
an "other" catch-all for anything unrecognized) so an ambiguous or
version-specific slot number surfaces the item somewhere instead of being
silently dropped.
"""

import json

import nbtlib
from nbtlib.tag import Byte

DIFFICULTY_NAMES = {0: "peaceful", 1: "easy", 2: "normal", 3: "hard"}
GAMEMODE_NAMES = {0: "survival", 1: "creative", 2: "adventure", 3: "spectator"}


def _short_name(item_id: str) -> str:
    name = item_id.split(":", 1)[-1]
    return name.replace("_", " ").title()


def _extract_text(raw: str) -> str:
    """Custom names are stored as a JSON text-component string
    (e.g. '{"text":"Realm Guardian"}'). Best-effort plain-text extraction;
    falls back to the raw string for formats this doesn't recognize.
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
    if isinstance(parsed, str):
        return parsed
    if isinstance(parsed, dict) and "text" in parsed:
        return parsed["text"]
    return raw


def _format_gamerule_value(v) -> str:
    """Byte-typed gamerules are boolean flags in vanilla convention;
    everything else (Int, String, ...) prints as its plain value.
    """
    if isinstance(v, Byte):
        return "true" if int(v) else "false"
    if isinstance(v, (int, float)):
        return str(v.real if isinstance(v, float) else int(v))
    return str(v)


def _get(compound, *keys, default=None):
    for key in keys:
        if compound is not None and key in compound:
            return compound[key]
    return default


def _decode_item_stack(item) -> dict:
    """Decode an item stack's id/count/components — shared by top-level
    inventory entries and by items nested inside a shulker box's
    `minecraft:container` component (same shape, just nested one level
    deeper under an "item" key rather than being the entry itself).
    """
    item_id = str(_get(item, "id", default="unknown"))
    count = int(_get(item, "count", "Count", default=1))
    components = _get(item, "components", default=None)

    result: dict = {"id": item_id, "name": _short_name(item_id), "count": count}

    if components is not None:
        try:
            enchants = components.get("minecraft:enchantments")
            if enchants is not None:
                levels = enchants.get("levels") if hasattr(enchants, "get") and "levels" in enchants else enchants
                if hasattr(levels, "items"):
                    result["enchantments"] = {str(k): int(v) for k, v in levels.items()}
        except Exception:
            pass
        try:
            custom_name = components.get("minecraft:custom_name")
            if custom_name is not None:
                result["custom_name"] = _extract_text(str(custom_name))
        except Exception:
            pass
        try:
            damage = components.get("minecraft:damage")
            if damage is not None:
                result["damage"] = int(damage)
        except Exception:
            pass
        try:
            potion = components.get("minecraft:potion_contents")
            if potion is not None:
                potion_id = potion.get("potion")
                if potion_id:
                    result["potion"] = _short_name(str(potion_id))
        except Exception:
            pass
        try:
            trim = components.get("minecraft:trim")
            if trim is not None:
                pattern = trim.get("pattern")
                material = trim.get("material")
                result["trim"] = {
                    "pattern": _short_name(str(pattern)) if pattern else None,
                    "material": _short_name(str(material)) if material else None,
                    # Raw id (e.g. "gold", not "Gold") — needed to build the
                    # composited icon URL; the material's color PALETTE is
                    # what actually renders, pattern only affects the 3D
                    # worn model, not the flat 2D icon overlay.
                    "material_id": str(material).split(":", 1)[-1] if material else None,
                }
        except Exception:
            pass
        try:
            container = components.get("minecraft:container")
            if container:
                contents = [
                    _decode_item_stack(entry["item"]) for entry in container if "item" in entry
                ]
                if contents:
                    result["contents"] = contents
        except Exception:
            pass

    return result


def _decode_item(entry) -> dict:
    slot = int(_get(entry, "Slot", "slot", default=-1))
    result = _decode_item_stack(entry)
    result["slot"] = slot
    return result


def _bucket_inventory(items: list[dict]) -> dict:
    """Fixed-size slot arrays (None for empty) so the frontend can render a
    real inventory grid — including genuinely empty slots in their correct
    position — rather than densely packing only the occupied ones.

    Armor/offhand are NOT handled here — confirmed against a real live
    equip (see `equipment` compound below) that they aren't stored via
    special slot numbers (100-103/-106) within Inventory in current
    versions. That's a legacy/older-version convention; this server's
    Inventory list only ever holds hotbar (0-8) + main (9-35).
    """
    hotbar: list = [None] * 9
    main: list = [None] * 27
    other: list = []

    for entry in items:
        slot = entry["slot"]
        if 0 <= slot <= 8:
            hotbar[slot] = entry
        elif 9 <= slot <= 35:
            main[slot - 9] = entry
        else:
            other.append(entry)

    return {"hotbar": hotbar, "main": main, "other": other}


_EQUIPMENT_KEYS = {"head": "helmet", "chest": "chestplate", "legs": "leggings", "feet": "boots"}


def _decode_equipment(equipment) -> tuple[dict, dict | None]:
    """Reads the `equipment` compound (head/chest/legs/feet/offhand) —
    the actual current-version storage for worn armor and held offhand
    item, confirmed live against a real equipped player. Absent entirely
    when nothing is equipped.
    """
    armor = {"helmet": None, "chestplate": None, "leggings": None, "boots": None}
    offhand = None
    if equipment is None:
        return armor, offhand
    for raw_key, armor_key in _EQUIPMENT_KEYS.items():
        item = _get(equipment, raw_key, default=None)
        if item is not None:
            armor[armor_key] = _decode_item_stack(item)
    offhand_item = _get(equipment, "offhand", default=None)
    if offhand_item is not None:
        offhand = _decode_item_stack(offhand_item)
    return armor, offhand


def _bucket_ender_chest(items: list[dict]) -> list:
    slots: list = [None] * 27
    for entry in items:
        slot = entry["slot"]
        if 0 <= slot <= 26:
            slots[slot] = entry
    return slots


def parse_playerdata(path: str) -> dict:
    root = nbtlib.load(path)

    inventory_raw = _get(root, "Inventory", default=[])
    ender_raw = _get(root, "EnderItems", default=[])
    pos = _get(root, "Pos", default=None)

    inventory = _bucket_inventory([_decode_item(e) for e in inventory_raw])
    armor, offhand = _decode_equipment(_get(root, "equipment", default=None))
    inventory["armor"] = armor
    inventory["offhand"] = offhand

    return {
        "health": float(_get(root, "Health", default=20.0)),
        "food_level": int(_get(root, "foodLevel", default=20)),
        "xp_level": int(_get(root, "XpLevel", default=0)),
        "xp_total": int(_get(root, "XpTotal", default=0)),
        "dimension": str(_get(root, "Dimension", default="minecraft:overworld")),
        "gamemode": GAMEMODE_NAMES.get(int(_get(root, "playerGameType", default=0)), "survival"),
        "position": [round(float(p), 1) for p in pos] if pos else None,
        "inventory": inventory,
        "ender_chest": _bucket_ender_chest([_decode_item(e) for e in ender_raw]),
    }


def parse_level_dat(path: str) -> dict:
    root = nbtlib.load(path)
    data = _get(root, "Data")
    if data is None:
        return {"error": "level.dat has no Data compound"}

    world_gen = _get(data, "WorldGenSettings", default=None)
    seed = _get(world_gen, "seed", default=None) if world_gen is not None else None
    if seed is None:
        seed = _get(data, "RandomSeed", default=None)

    # Two on-disk shapes observed: legacy flat SpawnX/Y/Z ints, and a newer
    # nested "spawn" compound with a "pos" int array (confirmed against a
    # real 1.21.11 level.dat — the legacy keys weren't present at all here).
    spawn_compound = _get(data, "spawn", default=None)
    if spawn_compound is not None and "pos" in spawn_compound:
        pos = spawn_compound["pos"]
        spawn = {"x": int(pos[0]), "y": int(pos[1]), "z": int(pos[2])}
    else:
        spawn = {
            "x": int(_get(data, "SpawnX", default=0)),
            "y": int(_get(data, "SpawnY", default=0)),
            "z": int(_get(data, "SpawnZ", default=0)),
        }

    # Same story for game rules: newer worlds store "game_rules" (lowercase,
    # namespaced keys like "minecraft:fall_damage", typed values) instead of
    # the legacy "GameRules" (plain names, all-string values).
    game_rules_raw = _get(data, "game_rules", "GameRules", default={}) or {}
    game_rules = {_short_name(str(k)): _format_gamerule_value(v) for k, v in game_rules_raw.items()}

    return {
        "level_name": str(_get(data, "LevelName", default="")),
        # String: a 64-bit seed exceeds JS's exact-integer range (2^53) and would
        # be silently rounded by JSON.parse in the browser.
        "seed": str(int(seed)) if seed is not None else None,
        "difficulty": DIFFICULTY_NAMES.get(int(_get(data, "Difficulty", default=2)), "normal"),
        "difficulty_locked": bool(_get(data, "DifficultyLocked", default=0)),
        "day_time": int(_get(data, "DayTime", default=0)),
        "raining": bool(_get(data, "raining", default=0)),
        "thundering": bool(_get(data, "thundering", default=0)),
        "spawn": spawn,
        "game_rules": game_rules,
    }
