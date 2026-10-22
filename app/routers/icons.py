"""Serves real Minecraft item/block icons, fetched once from a public
mirror of Mojang's game assets (misode/mcmeta, pinned to the 1.21.11 tag
this server runs) and cached to disk on first request. Item-form texture
is tried first, falling back to the block texture for block-items (stone,
shulker boxes, etc.) which have no separate item sprite.
"""

import io
import os
import re
import time

import httpx
from fastapi import APIRouter, Response
from fastapi.responses import FileResponse
from PIL import Image

router = APIRouter()

_ASSET_TAG = "1.21.11-assets"
_BASE_URL = f"https://raw.githubusercontent.com/misode/mcmeta/{_ASSET_TAG}/assets/minecraft/textures"
_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static", "items")
_VALID_NAME = re.compile(r"^[a-z0-9_]+$")

_TRANSPARENT_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a"
    "49444154789c6360000002000100ffff03000006000557bfabd40000000049454e44ae426082"
)

# Items with no flat 2D texture in the raw asset files at all — real vanilla
# renders these as a baked 3D model specifically for their inventory icon
# (chests, shields, banners, heads all fall in this category). Mapped to
# the Minecraft Wiki's pre-rendered icon for each, resolved via its API
# rather than hardcoding a guessed image URL (wiki media paths are
# hash-bucketed and not derivable from the filename alone).
_WIKI_ICON_OVERRIDES = {
    "shield": "Shield_JE2_BE1.png",
    "chest": "Chest.png",
    "ender_chest": "Ender_Chest.png",
    "trapped_chest": "Trapped_Chest.png",
}

# Items whose flat texture is missing or misleading, so the wiki's rendered
# inventory icon ("Invicon_<Title_Case>.png") is used first: beds, banners,
# heads/skulls, chests, decorated pots (no flat texture at all) and shulker
# boxes (the block texture is just a flat coloured square).
_WIKI_FIRST = re.compile(r"(^|_)(shulker_box|bed|banner|head|skull|chest|decorated_pot)$")


def _wiki_filename(item_name: str) -> str | None:
    if item_name in _WIKI_ICON_OVERRIDES:
        return _WIKI_ICON_OVERRIDES[item_name]
    if _WIKI_FIRST.search(item_name):
        return "Invicon_" + "_".join(w.capitalize() for w in item_name.split("_")) + ".png"
    return None


# A failed lookup is remembered in memory only, for an hour. It used to be
# written to disk as a 1x1 placeholder, which cached every miss forever (even
# after the lookup was fixed). Placeholders already on disk are treated as
# misses and retried (see _cached_icon).
_MISS_TTL = 3600.0
_misses: dict[str, float] = {}


def _cached_icon(cache_path: str) -> str | None:
    if not os.path.exists(cache_path):
        return None
    if os.path.getsize(cache_path) == len(_TRANSPARENT_PNG):
        with open(cache_path, "rb") as f:
            if f.read() == _TRANSPARENT_PNG:
                os.remove(cache_path)
                return None
    return cache_path


# Which trim overlay a piece of armor uses — same one file per armor
# category regardless of pattern (confirmed: mcmeta only ships
# helmet_trim.png/chestplate_trim.png/leggings_trim.png/boots_trim.png,
# nothing per-pattern). Pattern only changes the 3D worn-model geometry,
# not this flat 2D icon overlay, so trim compositing only needs material.
_ARMOR_TRIM_TYPES = ("helmet", "chestplate", "leggings", "boots")


def _armor_trim_type(item_name: str) -> str | None:
    return next((t for t in _ARMOR_TRIM_TYPES if item_name.endswith(t)), None)


async def _fetch_wiki_icon(client: httpx.AsyncClient, filename: str) -> bytes | None:
    api_url = "https://minecraft.wiki/api.php"
    params = {
        "action": "query",
        "titles": f"File:{filename}",
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json",
    }
    try:
        resp = await client.get(api_url, params=params)
        pages = resp.json()["query"]["pages"]
        page = next(iter(pages.values()))
        image_url = page["imageinfo"][0]["url"]
        img_resp = await client.get(image_url)
        if img_resp.status_code == 200:
            return img_resp.content
    except Exception:
        pass
    return None


async def _fetch_base_icon_bytes(client: httpx.AsyncClient, item_name: str) -> tuple[bytes | None, bool]:
    """Returns (png bytes, degraded). `degraded` means a wiki-first item had
    to fall back to its raw texture (wiki unreachable), so the caller should
    not cache it and let the next request retry the wiki."""
    wiki_filename = _wiki_filename(item_name)
    if wiki_filename:
        content = await _fetch_wiki_icon(client, wiki_filename)
        if content:
            return content, False
    for category in ("item", "block"):
        try:
            resp = await client.get(f"{_BASE_URL}/{category}/{item_name}.png")
        except Exception:
            continue
        if resp.status_code == 200:
            return resp.content, wiki_filename is not None
    return None, False


async def _fetch_trim_layers(client: httpx.AsyncClient, armor_type: str, material: str):
    trim_url = f"{_BASE_URL}/trims/items/{armor_type}_trim.png"
    palette_url = f"{_BASE_URL}/trims/color_palettes/{material}.png"
    trim_resp = await client.get(trim_url)
    palette_resp = await client.get(palette_url)
    if trim_resp.status_code != 200 or palette_resp.status_code != 200:
        return None, None
    return trim_resp.content, palette_resp.content


def _composite_trim(base_bytes: bytes, trim_bytes: bytes, palette_bytes: bytes) -> bytes:
    """Real Minecraft trim rendering: the overlay is a 16x16 GRAYSCALE
    image (confirmed by inspecting the actual asset) where each nonzero
    pixel is an index (value // 32, giving 0-7) into the material's 8x1
    color-swatch palette strip (also confirmed directly against real
    files) — zero pixels stay fully transparent. This reproduces that
    exact algorithm rather than a simple tint/multiply approximation.
    """
    base = Image.open(io.BytesIO(base_bytes)).convert("RGBA")
    trim = Image.open(io.BytesIO(trim_bytes)).convert("L")
    palette = Image.open(io.BytesIO(palette_bytes)).convert("RGB")

    overlay = Image.new("RGBA", trim.size, (0, 0, 0, 0))
    trim_px = trim.load()
    overlay_px = overlay.load()
    palette_px = palette.load()
    palette_width = palette.size[0]

    for y in range(trim.size[1]):
        for x in range(trim.size[0]):
            level = trim_px[x, y]
            if level > 0:
                index = min(level // 32, palette_width - 1)
                r, g, b = palette_px[index, 0]
                overlay_px[x, y] = (r, g, b, 255)

    if overlay.size != base.size:
        overlay = overlay.resize(base.size, Image.NEAREST)

    composited = Image.alpha_composite(base, overlay)
    buf = io.BytesIO()
    composited.save(buf, format="PNG")
    return buf.getvalue()


@router.get("/api/icon/{item_name}.png")
async def get_icon(item_name: str):
    if not _VALID_NAME.match(item_name):
        return Response(content=_TRANSPARENT_PNG, media_type="image/png")

    os.makedirs(_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(_CACHE_DIR, f"{item_name}.png")
    if _cached_icon(cache_path):
        return FileResponse(cache_path, media_type="image/png")

    if time.monotonic() - _misses.get(item_name, -_MISS_TTL) < _MISS_TTL:
        return Response(content=_TRANSPARENT_PNG, media_type="image/png")

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        content, degraded = await _fetch_base_icon_bytes(client, item_name)

    if content:
        if not degraded:
            with open(cache_path, "wb") as f:
                f.write(content)
        return Response(content=content, media_type="image/png")

    _misses[item_name] = time.monotonic()
    return Response(content=_TRANSPARENT_PNG, media_type="image/png")


@router.get("/api/icon/{item_name}/trim/{material}.png")
async def get_trimmed_icon(item_name: str, material: str):
    if not _VALID_NAME.match(item_name) or not _VALID_NAME.match(material):
        return Response(content=_TRANSPARENT_PNG, media_type="image/png")

    armor_type = _armor_trim_type(item_name)
    if armor_type is None:
        return await get_icon(item_name)

    os.makedirs(_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(_CACHE_DIR, f"{item_name}_trim_{material}.png")
    if os.path.exists(cache_path):
        return FileResponse(cache_path, media_type="image/png")

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        base_bytes, _ = await _fetch_base_icon_bytes(client, item_name)
        if base_bytes is None:
            return Response(content=_TRANSPARENT_PNG, media_type="image/png")

        trim_bytes, palette_bytes = await _fetch_trim_layers(client, armor_type, material)

    if not trim_bytes or not palette_bytes:
        # No such material/overlay found — fall back to the plain icon
        # rather than a broken image.
        with open(cache_path, "wb") as f:
            f.write(base_bytes)
        return Response(content=base_bytes, media_type="image/png")

    try:
        composited = _composite_trim(base_bytes, trim_bytes, palette_bytes)
    except Exception:
        composited = base_bytes

    with open(cache_path, "wb") as f:
        f.write(composited)
    return Response(content=composited, media_type="image/png")
