from fastapi import APIRouter

from .. import rcon
from ..config import settings
from ..mc_paths import get_systemd_active_since, read_server_properties
from ..mc_status import parse_player_list, parse_tps, strip_colors

router = APIRouter()


@router.get("/api/status")
async def get_status():
    props = read_server_properties()
    result = {
        "motd": strip_colors(props.get("motd", "")).replace("\\n", "\n"),
        "online": False,
        "players_online": 0,
        "players_max": int(props.get("max-players", 20)) if props.get("max-players", "20").isdigit() else 20,
        "player_names": [],
        "tps": None,
        "uptime_since": get_systemd_active_since(settings.systemd_unit),
        "error": None,
    }

    try:
        list_resp = await rcon.run(settings.rcon_host, settings.rcon_port, settings.rcon_password, "list")
        result["online"] = True
        parsed = parse_player_list(list_resp)
        result["players_online"] = parsed["online"]
        result["players_max"] = parsed["max"] or result["players_max"]
        result["player_names"] = parsed["names"]
    except Exception as exc:
        result["error"] = str(exc)
        return result

    try:
        tps_resp = await rcon.run(settings.rcon_host, settings.rcon_port, settings.rcon_password, "tps")
        result["tps"] = parse_tps(tps_resp)
    except Exception:
        pass

    return result
