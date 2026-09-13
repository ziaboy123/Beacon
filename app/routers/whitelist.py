import json
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import mojang, rcon
from ..config import settings

router = APIRouter()


def _path(name: str) -> str:
    return os.path.join(settings.mc_server_dir, name)


def _load(name: str) -> list:
    try:
        with open(_path(name), "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def _save(name: str, data: list) -> None:
    with open(_path(name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


async def _reload_whitelist() -> None:
    try:
        await rcon.run(settings.rcon_host, settings.rcon_port, settings.rcon_password, "whitelist reload")
    except Exception:
        pass  # file is already updated; a failed reload just means it applies on next restart


@router.get("/api/whitelist")
async def get_whitelist():
    whitelist = _load("whitelist.json")
    ops_by_uuid = {o["uuid"]: o for o in _load("ops.json")}
    for entry in whitelist:
        op = ops_by_uuid.get(entry.get("uuid"))
        entry["is_op"] = op is not None
        entry["op_level"] = op["level"] if op else None
    return whitelist


class AddWhitelistRequest(BaseModel):
    username: str


@router.post("/api/whitelist")
async def add_whitelist(req: AddWhitelistRequest):
    try:
        profile = await mojang.lookup_uuid(req.username)
    except mojang.MojangLookupError as exc:
        raise HTTPException(404, str(exc))

    whitelist = _load("whitelist.json")
    if any(e.get("uuid") == profile["id"] for e in whitelist):
        raise HTTPException(409, f"{profile['name']} is already whitelisted")

    whitelist.append({"uuid": profile["id"], "name": profile["name"]})
    _save("whitelist.json", whitelist)
    await _reload_whitelist()
    return {"uuid": profile["id"], "name": profile["name"]}


@router.delete("/api/whitelist/{name}")
async def remove_whitelist(name: str):
    whitelist = _load("whitelist.json")
    filtered = [e for e in whitelist if e.get("name", "").lower() != name.lower()]
    if len(filtered) == len(whitelist):
        raise HTTPException(404, f"{name} not found on whitelist")

    _save("whitelist.json", filtered)
    await _reload_whitelist()
    return {"removed": name}
