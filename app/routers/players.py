import asyncio
import json
import os
import time

from fastapi import APIRouter, HTTPException

from .. import rcon
from ..config import settings
from ..mc_paths import get_world_dir
from ..mc_status import parse_player_list
from ..nbt_utils import parse_playerdata

router = APIRouter()

_STAT_LABELS = {
    "minecraft:play_time": ("Playtime (hours)", lambda ticks: round(ticks / 20 / 3600, 1)),
    "minecraft:deaths": ("Deaths", int),
    "minecraft:jump": ("Jumps", int),
    "minecraft:walk_one_cm": ("Distance Walked (m)", lambda cm: round(cm / 100, 1)),
    "minecraft:damage_dealt": ("Damage Dealt", int),
    "minecraft:damage_taken": ("Damage Taken", int),
    "minecraft:mob_kills": ("Mob Kills", int),
    "minecraft:player_kills": ("Player Kills", int),
}


def _usercache() -> list:
    path = os.path.join(settings.mc_server_dir, "usercache.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


async def _online_names() -> set[str]:
    try:
        resp = await rcon.run(settings.rcon_host, settings.rcon_port, settings.rcon_password, "list")
        return set(parse_player_list(resp)["names"])
    except Exception:
        return set()


# `save-all flush` writes every online player, so one flush serves all
# requests. With the player popup open, /stats and /inventory each ran their
# own flush every 4 s (two world saves per refresh); now concurrent and
# back-to-back requests share one.
_flush_lock = asyncio.Lock()
_last_flush = 0.0
_FLUSH_MIN_INTERVAL = 3.0


async def _flush_if_online(uuid: str) -> None:
    """Playerdata/stats files are only written on Minecraft's own periodic
    autosave (every few minutes) or on logout — stale by up to that whole
    interval for a player who's currently online. `save-all flush` forces
    an immediate, synchronous write so a live player's file is fresh before
    we read it (Paper/Bukkit-specific; `flush` makes it block until done
    instead of just queuing the save).
    """
    global _last_flush
    entry = next((e for e in _usercache() if e.get("uuid") == uuid), None)
    if entry is None:
        return
    async with _flush_lock:
        if time.monotonic() - _last_flush < _FLUSH_MIN_INTERVAL:
            return
        online = await _online_names()
        if entry.get("name") not in online:
            return
        try:
            await rcon.run(settings.rcon_host, settings.rcon_port, settings.rcon_password, "save-all flush")
        except Exception:
            pass
        _last_flush = time.monotonic()


@router.get("/api/players")
async def list_players():
    online = await _online_names()
    players = []
    for entry in _usercache():
        players.append(
            {
                "uuid": entry.get("uuid"),
                "name": entry.get("name"),
                "online": entry.get("name") in online,
            }
        )
    return players


@router.get("/api/players/{uuid}/stats")
async def get_player_stats(uuid: str):
    await _flush_if_online(uuid)
    path = os.path.join(get_world_dir(), "stats", f"{uuid}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        raise HTTPException(404, "No stats recorded for this player")
    except json.JSONDecodeError as exc:
        raise HTTPException(500, f"Malformed stats file: {exc}")

    stats = raw.get("stats", {})
    custom = stats.get("minecraft:custom", {})

    summary = {}
    for key, (label, fmt) in _STAT_LABELS.items():
        if key in custom:
            summary[label] = fmt(custom[key])

    mined = stats.get("minecraft:mined", {})
    killed = stats.get("minecraft:killed", {})

    return {
        "summary": summary,
        "top_mined": sorted(
            ({"item": k, "count": v} for k, v in mined.items()), key=lambda e: -e["count"]
        )[:10],
        "top_killed": sorted(
            ({"entity": k, "count": v} for k, v in killed.items()), key=lambda e: -e["count"]
        )[:10],
    }


@router.get("/api/players/{uuid}/inventory")
async def get_player_inventory(uuid: str):
    await _flush_if_online(uuid)
    path = os.path.join(get_world_dir(), "playerdata", f"{uuid}.dat")
    if not os.path.exists(path):
        raise HTTPException(404, "No playerdata found for this player")
    try:
        return parse_playerdata(path)
    except Exception as exc:
        raise HTTPException(500, f"Failed to parse playerdata: {exc}")
