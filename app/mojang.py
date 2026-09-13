"""Username -> UUID lookup, same Mojang API approach already used when the
whitelist/ops were first set up for this server (see project memory).
"""

import httpx

_LOOKUP_URL = "https://api.mojang.com/users/profiles/minecraft/{username}"


class MojangLookupError(Exception):
    pass


async def lookup_uuid(username: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(_LOOKUP_URL.format(username=username))

    if resp.status_code == 404:
        raise MojangLookupError(f"No Minecraft account found for username '{username}'")
    if resp.status_code != 200:
        raise MojangLookupError(f"Mojang API error ({resp.status_code}) looking up '{username}'")

    data = resp.json()
    raw_id = data["id"]
    dashed = f"{raw_id[0:8]}-{raw_id[8:12]}-{raw_id[12:16]}-{raw_id[16:20]}-{raw_id[20:32]}"
    return {"name": data["name"], "id": dashed}
