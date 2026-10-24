import json, sys, pathlib
out = pathlib.Path(sys.argv[1])
OW = "execute in minecraft:overworld run "
GRAVE = "gravestone:gravestone"
RS = {"slot": "back", "idx": 0, "item": "sophisticatedbackpacks:iron_backpack", "name": "VD Rucksack"}
JP = {"slot": "body", "idx": 0, "item": "ironjetpacks:jetpack", "nbt": "{Id:\"ironjetpacks:diamond\",Energy:123456}", "name": "VD Jetpack voll"}
RA = {"slot": "ring", "idx": 0, "item": "botania:aura_ring", "name": "VD Ring A"}
RB = {"slot": "ring", "idx": 1, "item": "botania:magnet_ring", "name": "VD Ring B"}
def chk(c, label=None):
    d = {"slot": c["slot"], "idx": c["idx"], "name": c["name"]}
    if label: d["label"] = label
    return {"curio_check": d}
def empty(slot, idx): return {"curio_check": {"slot": slot, "idx": idx, "name": ""}}
def reset():
    return {"cmd": ["clear @p", "kill @e[type=minecraft:item]", OW + "tp @p 3000 121 3000 0 0"], "curio_clear": True, "wait": 10}
def run(label, fixed):
    E = (lambda c, l: chk(c, l)) if fixed else None
    s = [
        {"note": "Vorbereitung: Überleben-Modus, keepInventory aus, Testfläche 3000 120 3000",
         "cmd": ["gamerule keepInventory false", "gamerule doMobSpawning false", "time set 6000",
                 OW + "forceload add 2992 2992 3008 3008", OW + "tp @p 3000 121 3000 0 0"], "wait": 120},
        {"cmd": [OW + "fill 2994 120 2994 3006 120 3006 minecraft:bedrock", OW + "fill 2994 121 2994 3006 127 3006 minecraft:air",
                 "gamemode survival @p"]},
        reset(),
        # A: normaler Tod
        {"note": "A: Rucksack, voller Jetpack, 2 Ringe anlegen + Steine im Inventar, sterben, Grab abbauen"},
        {"curio_set": RS}, {"curio_set": JP}, {"curio_set": RA}, {"curio_set": RB},
        {"cmd": ["give @p minecraft:stone 20"], "wait": 5},
        {"kill": True, "wait": 5},
        {"until_alive": 400}, {"wait": 20},
        empty("back", 0),
        {"break_grave": GRAVE, "wait": 10},
        chk(RS, "A: Rucksack wieder in back#0" if fixed else "A: Rucksack in back#0 (ohne Fix erwartet ❌)"),
        chk(JP, "A: voller Jetpack wieder in body#0" if fixed else "A: Jetpack in body#0 (ohne Fix erwartet ❌)"),
        chk(RA, "A: Ring A wieder in ring#0" if fixed else "A: Ring A in ring#0 (ohne Fix erwartet ❌)"),
        chk(RB, "A: Ring B wieder in ring#1" if fixed else "A: Ring B in ring#1 (ohne Fix erwartet ❌)"),
        {"count": "minecraft:stone", "expect": 20, "name": "A: Steine zurück im Inventar"},
        reset(),
        # B: Slot nach dem Respawn schon belegt
        {"note": "B: voller Jetpack + Rucksack, sterben, dann leeren Jetpack anlegen, Grab abbauen"},
        {"curio_set": RS}, {"curio_set": JP},
        {"kill": True, "wait": 5}, {"until_alive": 400}, {"wait": 20},
        {"curio_set": {"slot": "body", "idx": 0, "item": "ironjetpacks:jetpack", "nbt": "{Id:\"ironjetpacks:iron\",Energy:0}", "name": "Neuer Jetpack leer"}},
        {"break_grave": GRAVE, "wait": 10},
        {"curio_check": {"slot": "body", "idx": 0, "name": "Neuer Jetpack leer", "label": "B: belegter Slot bleibt unangetastet"}},
        {"count": "ironjetpacks:jetpack", "named": "VD Jetpack voll", "expect": 1, "name": "B: voller Jetpack liegt im Inventar"},
        chk(RS, "B: Rucksack wieder in back#0" if fixed else "B: Rucksack in back#0 (ohne Fix erwartet ❌)"),
        reset(),
        # C: volles Inventar
        {"note": "C: Inventar voll Holz + Rucksack, sterben, Inventar mit Bruchstein füllen, Grab abbauen"},
        {"curio_set": RS}, {"fill_inv": "minecraft:oak_log"},
        {"kill": True, "wait": 5}, {"until_alive": 400}, {"wait": 20},
        {"fill_inv": "minecraft:cobblestone"},
        {"break_grave": GRAVE, "wait": 10},
        chk(RS, "C: Rucksack trotz vollem Inventar in back#0" if fixed else "C: Rucksack in back#0 (ohne Fix erwartet ❌)"),
        {"ground_kept": True, "min": 1, "name": "C: Überlauf liegt beim Spieler ohne Ablaufzeit" if fixed else "C: Überlauf ohne Ablaufzeit (ohne Fix erwartet ❌)"},
        # D: Xpetrified Orb – Schleichen + Rechtsklick = ganzer Stapel (KubeJS xpetrified_orb.js)
        {"note": "D: Xpetrified Orb schleichend (10 Stück) und normal (10 Stück)", "cmd": ["clear @p", "xp set @p 0 levels", "xp set @p 0 points"], "wait": 5},
        {"use_item": {"item": "forbidden_arcanus:xpetrified_orb", "count": 10, "sneak": True}, "wait": 5},
        {"xp_check": {"min": 910, "max": 910, "name": "D: schleichend 10 Orbs = 910 XP"}},
        {"count": "forbidden_arcanus:xpetrified_orb", "expect": 0, "name": "D: Stapel aufgebraucht"},
        {"cmd": ["clear @p"], "use_item": {"item": "forbidden_arcanus:xpetrified_orb", "count": 10, "sneak": False}, "wait": 5},
        {"xp_check": {"min": 91, "max": 91, "name": "D: ohne Schleichen 1 Orb = 91 XP (wie bisher)"}},
        {"count": "forbidden_arcanus:xpetrified_orb", "expect": 9, "name": "D: ohne Schleichen bleiben 9 übrig"},
        {"note": "Aufräumen", "cmd": ["clear @p", "kill @e[type=minecraft:item]", "gamemode creative @p", "gamerule doMobSpawning true",
                                       OW + "forceload remove 2992 2992 3008 3008"], "curio_clear": True, "wait": 20},
    ]
    (out / f"szenario-{label}.json").write_text(json.dumps({"label": label, "steps": s}, ensure_ascii=False, indent=1), encoding="utf-8")
run("grab-curios-ohne-fix", False)
run("grab-curios-mit-fix", True)
