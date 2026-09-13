"""Parsing helpers for RCON text responses, shared by status.py and players.py."""

import re

_COLOR_CODE = re.compile(r"§.")
_PLAYER_LIST = re.compile(r"There are (\d+) of a max(?: of)? (\d+) players online:?\s*(.*)")
_TPS_VALUES = re.compile(r"([\d.]+),\s*([\d.]+),\s*([\d.]+)")


def strip_colors(text: str) -> str:
    return _COLOR_CODE.sub("", text)


def parse_player_list(list_response: str) -> dict:
    cleaned = strip_colors(list_response).strip()
    match = _PLAYER_LIST.match(cleaned)
    if not match:
        return {"online": 0, "max": 0, "names": []}
    online, max_players, names_blob = match.group(1), match.group(2), match.group(3)
    names = [n.strip() for n in names_blob.split(",") if n.strip()]
    return {"online": int(online), "max": int(max_players), "names": names}


def parse_tps(tps_response: str) -> list[float] | None:
    match = _TPS_VALUES.search(strip_colors(tps_response))
    if not match:
        return None
    return [float(match.group(i)) for i in (1, 2, 3)]
