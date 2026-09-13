"""Generates a synthetic mc_server_dir for local testing without the real
Minecraft box. NOT for deployment — dev/testing only.

Usage: .venv/bin/python3 scripts/dev_fixtures.py [target_dir]
"""

import json
import os
import sys

import nbtlib
from nbtlib.tag import Byte, Compound, Double, Float, Int, List, Long, Short, String

TEST_UUID = "11111111-2222-3333-4444-555555555555"
TEST_NAME = "ziaboy123"


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def make_item(slot, item_id, count, components=None):
    entry = {"Slot": Byte(slot), "id": String(item_id), "count": Int(count)}
    if components:
        entry["components"] = Compound(components)
    return Compound(entry)


def main(target_dir):
    os.makedirs(target_dir, exist_ok=True)

    # server.properties
    with open(os.path.join(target_dir, "server.properties"), "w", encoding="utf-8") as f:
        f.write("level-name=world\n")
        f.write("max-players=20\n")
        f.write("motd=§c§lThe Ultimate Realm\n")

    # whitelist / ops / usercache
    write_json(
        os.path.join(target_dir, "whitelist.json"),
        [{"uuid": TEST_UUID, "name": TEST_NAME}],
    )
    write_json(
        os.path.join(target_dir, "ops.json"),
        [{"uuid": TEST_UUID, "name": TEST_NAME, "level": 4, "bypassesPlayerLimit": False}],
    )
    write_json(
        os.path.join(target_dir, "usercache.json"),
        [{"name": TEST_NAME, "uuid": TEST_UUID, "expiresOn": "2099-01-01T00:00:00+0000"}],
    )

    # world/level.dat
    level_data = Compound(
        {
            "Data": Compound(
                {
                    "LevelName": String("TheUltimateRealm"),
                    "WorldGenSettings": Compound({"seed": Long(-4200123456789)}),
                    "Difficulty": Byte(2),
                    "DifficultyLocked": Byte(0),
                    "DayTime": Long(13500),
                    "raining": Byte(0),
                    "thundering": Byte(0),
                    "SpawnX": Int(120),
                    "SpawnY": Int(70),
                    "SpawnZ": Int(-340),
                    "GameRules": Compound(
                        {
                            "doDaylightCycle": String("true"),
                            "keepInventory": String("false"),
                            "mobGriefing": String("true"),
                        }
                    ),
                }
            )
        }
    )
    os.makedirs(os.path.join(target_dir, "world"), exist_ok=True)
    nbtlib.File(level_data, gzipped=True).save(os.path.join(target_dir, "world", "level.dat"))

    # world/stats/<uuid>.json (plain JSON, not NBT)
    stats = {
        "stats": {
            "minecraft:custom": {
                "minecraft:play_time": 720000,
                "minecraft:deaths": 7,
                "minecraft:jump": 5230,
                "minecraft:walk_one_cm": 812345,
                "minecraft:damage_dealt": 15234,
                "minecraft:damage_taken": 4210,
                "minecraft:mob_kills": 340,
                "minecraft:player_kills": 2,
            },
            "minecraft:mined": {
                "minecraft:stone": 5230,
                "minecraft:oak_log": 812,
                "minecraft:diamond_ore": 44,
                "minecraft:deepslate": 3021,
            },
            "minecraft:killed": {
                "minecraft:zombie": 120,
                "minecraft:skeleton": 90,
                "minecraft:creeper": 40,
                "minecraft:enderman": 12,
            },
        },
        "DataVersion": 3953,
    }
    write_json(os.path.join(target_dir, "world", "stats", f"{TEST_UUID}.json"), stats)

    # playerdata/<uuid>.dat — modern (1.20.5+) item-stack schema
    inventory = List[Compound](
        [
            make_item(0, "minecraft:diamond_sword", 1, {
                "minecraft:enchantments": Compound({"levels": Compound({"minecraft:sharpness": Int(5)})}),
                "minecraft:damage": Int(120),
            }),
            make_item(1, "minecraft:bow", 1),
            make_item(9, "minecraft:cobblestone", 64),
            make_item(10, "minecraft:torch", 32),
            make_item(100, "minecraft:diamond_boots", 1),
            make_item(101, "minecraft:diamond_leggings", 1),
            make_item(102, "minecraft:diamond_chestplate", 1),
            make_item(103, "minecraft:diamond_helmet", 1, {
                "minecraft:custom_name": String('{"text":"Realm Guardian"}'),
            }),
            make_item(-106, "minecraft:shield", 1),
        ]
    )
    ender_items = List[Compound]([make_item(0, "minecraft:ender_pearl", 16)])

    playerdata = Compound(
        {
            "Health": Float(20.0),
            "foodLevel": Int(18),
            "XpLevel": Int(30),
            "XpTotal": Int(1200),
            "Dimension": String("minecraft:overworld"),
            "Pos": List[Double]([Double(120.5), Double(70.0), Double(-340.2)]),
            "Inventory": inventory,
            "EnderItems": ender_items,
        }
    )
    os.makedirs(os.path.join(target_dir, "playerdata"), exist_ok=True)
    nbtlib.File(playerdata, gzipped=True).save(os.path.join(target_dir, "playerdata", f"{TEST_UUID}.dat"))

    print(f"Fixtures written to {target_dir}")
    print(f"Test player: {TEST_NAME} ({TEST_UUID})")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/beacon_dev_data")
