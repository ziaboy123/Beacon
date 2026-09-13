from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import rcon
from ..config import settings

router = APIRouter()


class CommandRequest(BaseModel):
    command: str


@router.post("/api/command")
async def run_command(req: CommandRequest):
    cmd = req.command.strip().lstrip("/")
    if not cmd:
        raise HTTPException(400, "Empty command")

    # broadcast-rcon-to-ops is off server-side (see plan) specifically so
    # RCON commands are silent by default; announce attribution ourselves,
    # matching the convention Arc already uses for its own RCON commands.
    escaped = cmd.replace("\\", "\\\\").replace('"', '\\"')
    announce = f'tellraw @a {{"text":"[Beacon] running: /{escaped}","color":"gold"}}'

    try:
        await rcon.run(settings.rcon_host, settings.rcon_port, settings.rcon_password, announce)
        response = await rcon.run(settings.rcon_host, settings.rcon_port, settings.rcon_password, cmd)
        return {"response": response}
    except Exception as exc:
        raise HTTPException(502, f"RCON error: {exc}")
