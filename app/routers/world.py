import os

from fastapi import APIRouter

from ..config import settings
from ..mc_paths import get_disk_usage, get_world_dir
from ..nbt_utils import parse_level_dat

router = APIRouter()


@router.get("/api/world")
async def get_world():
    world_dir = get_world_dir()
    level_dat_path = os.path.join(world_dir, "level.dat")

    info: dict = {}
    if os.path.exists(level_dat_path):
        try:
            info = parse_level_dat(level_dat_path)
        except Exception as exc:
            info = {"error": f"Failed to parse level.dat: {exc}"}
    else:
        info = {"error": "level.dat not found"}

    info["disk_usage"] = get_disk_usage(
        [
            world_dir,
            f"{world_dir}_nether",
            f"{world_dir}_the_end",
            os.path.join(settings.mc_server_dir, "backups"),
        ]
    )
    return info
