"""Generates a synthetic mc_server_dir for local testing without the real
Minecraft box. NOT for deployment — dev/testing only.

Usage: .venv/bin/python3 scripts/dev_fixtures.py [target_dir]
"""

import json
import os
import sys

import nbtlib
from nbtlib.tag import Byte, Compound, Double, Float, Int, IntArray, List, Long, String

TEST_UUID = "11111111-2222-3333-4444-555555555555"
TEST_NAME = "ziaboy123"

# (uuid, name, dimension, gamemode, op?)
PLAYERS = [
    (TEST_UUID, TEST_NAME, "minecraft:overworld", 0, True),
    ("22222222-2222-3333-4444-555555555555", "xX_DragonSlay_Xx", "minecraft:the_nether", 1, False),
    ("33333333-2222-3333-4444-555555555555", "CaptainDemise", "minecraft:the_end", 0, True),
]


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def make_item(slot, item_id, count, components=None):
    entry = {"Slot": Byte(slot), "id": String(item_id), "count": Int(count)}
    if components:
        entry["components"] = Compound(components)
    return Compound(entry)


def make_stack(item_id, count=1, components=None):
    entry = {"id": String(item_id), "count": Int(count)}
    if components:
        entry["components"] = Compound(components)
    return Compound(entry)


def enchants(**levels):
    return {"minecraft:enchantments": Compound({f"minecraft:{k}": Int(v) for k, v in levels.items()})}


def trimmed(material, pattern="rib", **enchant_levels):
    comps = {"minecraft:trim": Compound({"material": String(f"minecraft:{material}"), "pattern": String(f"minecraft:{pattern}")})}
    if enchant_levels:
        comps.update(enchants(**enchant_levels))
    return comps


def shulker(color, contents, name=None):
    comps = {
        "minecraft:container": List[Compound](
            [Compound({"slot": Int(i), "item": make_stack(item_id, count)}) for i, (item_id, count) in enumerate(contents)]
        )
    }
    if name:
        comps["minecraft:custom_name"] = String(json.dumps({"text": name}))
    return make_stack(f"minecraft:{color}_shulker_box", 1, comps)


def build_inventory(index):
    items = [
        make_item(0, "minecraft:diamond_sword", 1, {
            **enchants(sharpness=5, unbreaking=3),
            "minecraft:damage": Int(120),
            "minecraft:custom_name": String('{"text":"Realm Guardian"}'),
        }),
        make_item(1, "minecraft:bow", 1, enchants(power=4, infinity=1)),
        make_item(2, "minecraft:red_bed", 1),
        make_item(3, "minecraft:white_banner", 1),
        make_item(4, "minecraft:player_head", 1),
        make_item(9, "minecraft:cobblestone", 64),
        make_item(10, "minecraft:torch", 32),
        make_item(11, "minecraft:shield", 1),
        make_item(12, "minecraft:ender_chest", 64),
        make_item(13, "minecraft:splash_potion", 3, {"minecraft:potion_contents": Compound({"potion": String("minecraft:strong_strength")})}),
    ]
    if index == 0:
        items.append(Compound({"Slot": Byte(14), **shulker("orange", [("minecraft:splash_potion", 1)] * 27, "STRENGTH")}))
    return List[Compound](items)


def build_equipment(index):
    if index == 2:
        return None
    return Compound({
        "head": make_stack("minecraft:netherite_helmet", 1, trimmed("redstone", **{"protection": 4, "respiration": 3})),
        "chest": make_stack("minecraft:netherite_chestplate", 1, trimmed("redstone", protection=4)),
        "legs": make_stack("minecraft:netherite_leggings", 1, trimmed("gold", protection=4)),
        "feet": make_stack("minecraft:netherite_boots", 1, trimmed("gold", "silence", protection=4, feather_falling=4)),
        "offhand": make_stack("minecraft:totem_of_undying", 1),
    })


def main(target_dir):
    os.makedirs(target_dir, exist_ok=True)

    with open(os.path.join(target_dir, "server.properties"), "w", encoding="utf-8") as f:
        f.write("level-name=world\n")
        f.write("max-players=20\n")
        f.write("motd=§c§lThe Ultimate Realm\\n§7A private realm\n")

    write_json(
        os.path.join(target_dir, "whitelist.json"),
        [{"uuid": u, "name": n} for u, n, *_ in PLAYERS],
    )
    write_json(
        os.path.join(target_dir, "ops.json"),
        [{"uuid": u, "name": n, "level": 4, "bypassesPlayerLimit": False} for u, n, _d, _g, op in PLAYERS if op],
    )
    write_json(
        os.path.join(target_dir, "usercache.json"),
        [{"name": n, "uuid": u, "expiresOn": "2099-01-01T00:00:00+0000"} for u, n, *_ in PLAYERS],
    )

    # Seed is beyond 2^53 on purpose: JS can't hold it exactly (regression check).
    level_data = Compound(
        {
            "Data": Compound(
                {
                    "LevelName": String("TheUltimateRealm"),
                    "WorldGenSettings": Compound({"seed": Long(-4226899070022691377)}),
                    "Difficulty": Byte(3),
                    "DifficultyLocked": Byte(1),
                    "DayTime": Long(13500),
                    "raining": Byte(0),
                    "thundering": Byte(0),
                    "spawn": Compound({"pos": IntArray([-1848, 180, 1189])}),
                    "game_rules": Compound(
                        {
                            "minecraft:keep_inventory": Byte(1),
                            "minecraft:mob_griefing": Byte(0),
                            "minecraft:random_tick_speed": Int(15),
                        }
                    ),
                }
            )
        }
    )
    os.makedirs(os.path.join(target_dir, "world"), exist_ok=True)
    nbtlib.File(level_data, gzipped=True).save(os.path.join(target_dir, "world", "level.dat"))

    os.makedirs(os.path.join(target_dir, "world", "playerdata"), exist_ok=True)
    for index, (uuid, _name, dimension, gamemode, _op) in enumerate(PLAYERS):
        stats = {
            "stats": {
                "minecraft:custom": {
                    "minecraft:play_time": 720000 + index * 100000,
                    "minecraft:deaths": 7 + index,
                    "minecraft:jump": 5230,
                    "minecraft:walk_one_cm": 812345,
                    "minecraft:damage_dealt": 15234,
                    "minecraft:damage_taken": 4210,
                    "minecraft:mob_kills": 340,
                    "minecraft:player_kills": 2,
                },
                "minecraft:mined": {"minecraft:stone": 5230, "minecraft:oak_log": 812, "minecraft:diamond_ore": 44},
                "minecraft:killed": {"minecraft:zombie": 120, "minecraft:skeleton": 90, "minecraft:enderman": 12},
            },
            "DataVersion": 3953,
        }
        write_json(os.path.join(target_dir, "world", "stats", f"{uuid}.json"), stats)

        data = {
            "Health": Float(20.0 - index * 8.5),
            "foodLevel": Int(18),
            "XpLevel": Int(30),
            "XpTotal": Int(1200),
            "Dimension": String(dimension),
            "playerGameType": Int(gamemode),
            "Pos": List[Double]([Double(120.5 + index), Double(70.0), Double(-340.2)]),
            "Inventory": build_inventory(index),
            "EnderItems": List[Compound]([make_item(0, "minecraft:ender_pearl", 16)]),
        }
        equipment = build_equipment(index)
        if equipment is not None:
            data["equipment"] = equipment
        nbtlib.File(Compound(data), gzipped=True).save(
            os.path.join(target_dir, "world", "playerdata", f"{uuid}.dat")
        )

    print(f"Fixtures written to {target_dir}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/beacon_dev_data")
