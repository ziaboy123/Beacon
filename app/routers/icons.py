"""Serves real Minecraft item/block icons, fetched once from a public
mirror of Mojang's game assets (misode/mcmeta, pinned to the 1.21.11 tag
this server runs) and cached to disk on first request. Item-form texture
is tried first, falling back to the block texture for block-items (stone,
shulker boxes, etc.) which have no separate item sprite.
"""

import io
import os
import re

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


async def _fetch_base_icon_bytes(client: httpx.AsyncClient, item_name: str) -> bytes | None:
    for category in ("item", "block"):
        try:
            resp = await client.get(f"{_BASE_URL}/{category}/{item_name}.png")
        except Exception:
            continue
        if resp.status_code == 200:
            return resp.content
    wiki_filename = _WIKI_ICON_OVERRIDES.get(item_name)
    if wiki_filename:
        return await _fetch_wiki_icon(client, wiki_filename)
    return None


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
    if os.path.exists(cache_path):
        return FileResponse(cache_path, media_type="image/png")

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        content = await _fetch_base_icon_bytes(client, item_name)

    if content:
        with open(cache_path, "wb") as f:
            f.write(content)
        return Response(content=content, media_type="image/png")

    # Cache the miss too (as the placeholder) so we don't re-hit GitHub for
    # every render of an item with no plain 2D texture (e.g. player heads).
    with open(cache_path, "wb") as f:
        f.write(_TRANSPARENT_PNG)
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
        base_bytes = await _fetch_base_icon_bytes(client, item_name)
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
