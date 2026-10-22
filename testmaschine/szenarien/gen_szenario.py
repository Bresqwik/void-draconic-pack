import json, sys, pathlib
out = pathlib.Path(sys.argv[1])
BAG = "majruszsdifficulty:wither_treasure_bag"
SW = "mysticalagriculture:supremium_sword"
OW = "execute in minecraft:overworld run "
W = "{NoAI:1b,PersistenceRequired:1b,Health:20f}"
def run(label, exp_machine):
    s = [
        {"note": "Vorbereitung: Kreativ, Testfläche bei 3000 120 3000 (Oberwelt)",
         "cmd": ["gamemode creative @p", "gamerule doMobSpawning false", "gamerule doDaylightCycle false", "time set 6000",
                 OW + "forceload add 2992 2992 3008 3008", OW + "tp @p 3000 121 2995 0 0"], "wait": 160},
        {"cmd": [OW + "fill 2994 120 2994 3006 120 3006 minecraft:bedrock", OW + "fill 2994 121 2994 3006 127 3006 minecraft:air",
                 "kill @e[type=minecraft:wither]", "kill @e[type=minecraft:item]", "clear @p " + BAG], "wait": 20},
        {"count": BAG, "expect": 0, "name": "Start: keine Bags im Inventar"},
        # A: echter Just-Dire-Things-Clicker
        {"note": "A: Just-Dire-Things-Clicker (aufgestellt von MarkMero) mit Supremium-Schwert gegen Wither",
         "cmd": [OW + "setblock 3003 121 3000 justdirethings:clickert1[facing=west]",
                 OW + "data merge block 3003 121 3000 {placedBy:{uuid},clickType:0,clickTarget:7,redstoneMode:0,machineHandler:{Size:1,Items:[{Slot:0,id:\"" + SW + "\",Count:1b}]}}",
                 OW + "summon minecraft:wither 3002.5 121 3000.5 " + W], "wait": 5},
        {"until_gone": "minecraft:wither", "max": 1200, "name": "A: Clicker tötet den Wither"},
        {"wait": 40},
        {"count": BAG, "expect": exp_machine, "name": f"A: Bag durch Clicker-Kill (erwartet {exp_machine})"},
        {"cmd": [OW + "setblock 3003 121 3000 minecraft:air", "clear @p " + BAG, "kill @e[type=minecraft:item]"], "wait": 10},
        # B: Fake-Spieler mit Spieler-UUID (wie jede Maschine)
        {"note": "B: Fake-Spieler mit MarkMeros UUID (wie Maschinen) gegen Wither",
         "cmd": [OW + "summon minecraft:wither 3000.5 121 3002.5 " + W], "wait": 5},
        {"attack": "minecraft:wither", "by": "fake", "item": SW, "every": 5, "max": 600},
        {"wait": 40},
        {"count": BAG, "expect": exp_machine, "name": f"B: Bag durch Fake-Spieler-Kill (erwartet {exp_machine})"},
        {"cmd": ["clear @p " + BAG, "kill @e[type=minecraft:item]"], "wait": 10},
        # C: echter Spieler
        {"note": "C: MarkMero schlägt den Wither selbst",
         "cmd": [OW + "summon minecraft:wither 3000.5 121 2998.5 " + W], "wait": 5},
        {"attack": "minecraft:wither", "by": "player", "item": SW, "every": 5, "max": 600},
        {"wait": 40},
        {"count": BAG, "expect": 1, "name": "C: Bag für echten Kampf (erwartet 1)"},
        {"note": "Aufräumen", "cmd": ["clear @p " + BAG, "kill @e[type=minecraft:item]", "kill @e[type=minecraft:wither]",
                                       OW + "forceload remove 2992 2992 3008 3008", "gamerule doMobSpawning true", "gamerule doDaylightCycle true"], "wait": 20},
    ]
    (out / f"szenario-{label}.json").write_text(json.dumps({"label": label, "steps": s}, ensure_ascii=False, indent=1), encoding="utf-8")
run("wither-bags-ohne-fix", 1)
run("wither-bags-mit-fix", 0)
