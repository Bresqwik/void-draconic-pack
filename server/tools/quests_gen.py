"""Erzeugt das FTB-Quests-Buch (Format 2101.1.x: Struktur in chapters/, Texte in lang/<sprache>/) für Void & Draconic.
Prüft alle Mod-Item-, Entity- und Dimensions-IDs gegen mc_ids.json (aus den Server-Jars gezogen).
Aufruf: python quests_gen.py <ziel: pack/config/ftbquests/quests>"""
import hashlib, json, os, shutil, sys

OUT = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
IDS = json.load(open(os.path.join(HERE, "mc_ids.json"), encoding="utf-8"))
ITEMS, ENTS = set(IDS["items"]), set(IDS["entities"])
DIMS = set(IDS["dims"]) | {"minecraft:the_nether", "minecraft:the_end", "minecraft:overworld"}
VANILLA_ENTS = {"minecraft:ender_dragon", "minecraft:wither", "minecraft:warden", "minecraft:elder_guardian"}
errors = []


def hid(*parts):
    """Feste 16-stellige Hex-ID aus einem Schlüssel (bleibt bei jedem Lauf gleich)."""
    h = hashlib.sha1("|".join(parts).encode()).hexdigest()[:16].upper()
    return h if h != "0000000000000001" else "1000000000000001"


def check_item(i):
    if not i.startswith("minecraft:") and i not in ITEMS:
        errors.append("Item fehlt: " + i)


# ---------------- Aufgaben und Belohnungen (Kurzschreibweise) ----------------
def item(i, n=1):
    check_item(i)
    return {"type": "item", "item": i, "count": n}


def kill(e, n=1):
    if e not in ENTS and e not in VANILLA_ENTS:
        errors.append("Entity fehlt: " + e)
    return {"type": "kill", "entity": e, "value": n}


def dim(d):
    if d not in DIMS:
        errors.append("Dimension fehlt: " + d)
    return {"type": "dimension", "dimension": d}


def check():
    return {"type": "checkmark"}


def xp(n):
    return {"type": "xp", "xp": n}


def give(i, n=1):
    check_item(i)
    return {"type": "item", "item": i, "count": n}


def Q(key, x, y, title, tasks, desc, rewards=(), deps=(), sub="", icon=None, shape=None, size=None):
    return dict(key=key, x=x, y=y, title=title, tasks=tasks, desc=desc, rewards=list(rewards), deps=list(deps), sub=sub, icon=icon, shape=shape, size=size)


# ---------------- Inhalt ----------------
CHAPTERS = [
    ("willkommen", "Willkommen in der Leere", "voidminersremastered:rubetine", [
        Q("start", 0, 0, "&dWillkommen bei Void & Draconic!", [check()], [
            "Schön, dass du da bist! Dieses Questbuch führt dich vom ersten Holz bis zum &5Draconic-Reaktor&r und zum &dUltimate Void Miner&r.",
            "",
            "Jedes Kapitel gehört zu einem Bereich des Packs. Du kannst sie in beliebiger Reihenfolge spielen, innerhalb eines Kapitels bauen die Quests aufeinander auf.",
            "",
            "Belohnungen holst du dir mit einem Klick auf die Quest ab."], [xp(50), give("minecraft:bread", 16)], sub="Hier fängt alles an", shape="hexagon", size=2.0),
        Q("werkbank", 3, -2, "Erste Schritte", [item("minecraft:crafting_table"), item("minecraft:stone_pickaxe")], [
            "Klassisch: Holz, Werkbank, Steinwerkzeug.",
            "Tipp: Mit &eJEI&r (Taste &eR&r auf einem Item) siehst du jedes Rezept, mit &eU&r wofür ein Item benutzt wird."], [xp(30)], deps=["start"]),
        Q("eisen", 6, -2, "Eisenzeit", [item("minecraft:iron_ingot", 16)], [
            "Eisen brauchst du für fast alles. Später verdoppelt bis verfünffacht &bMekanism&r deine Erze, heb dir also Roherz auf, wenn du magst."], [xp(50), give("minecraft:torch", 32)], deps=["werkbank"]),
        Q("ultimine", 3, 2, "Ganze Adern abbauen", [check()], [
            "Mit &eFTB Ultimine&r baust du verbundene Erze auf einmal ab: &eTilde-Taste&r (links neben der 1) gedrückt halten und einen Block abbauen.",
            "",
            "Mit gehaltener Taste und Mausrad wechselst du die Form, z. B. 3×3-Tunnel. Bis zu 64 Blöcke, kostet etwas Hunger."], [xp(30)], deps=["start"]),
        Q("chunks", 0, 3, "Basis sichern", [check()], [
            "Öffne die Karte mit &eM&r und ziehe mit der Maus über die Chunks deiner Basis, um sie zu &aclaimen&r.",
            "",
            "Mit Rechtsklick auf einen geclaimten Chunk kannst du ihn dauerhaft laden (&eForceload&r). So laufen Farmen und Maschinen weiter, auch wenn du offline bist."], [xp(30)], deps=["start"]),
        Q("rucksack", 6, 2, "Mehr Platz", [item("sophisticatedbackpacks:backpack")], [
            "Ein &eSophisticated Backpack&r ist Gold wert. Später lässt er sich mit Upgrades zu einem fahrenden Lager ausbauen."], [xp(50), give("minecraft:leather", 8)], deps=["eisen"]),
        Q("waystone", 9, 0, "Schnell reisen", [item("waystones:waystone")], [
            "&eWaystones&r verbinden deine wichtigsten Orte. Stell einen an deiner Basis auf, dann kommst du jederzeit zurück."], [xp(50), give("waystones:warp_stone")], deps=["eisen"]),
        Q("diamant", 9, -3, "Glitzernd", [item("minecraft:diamond", 5)], [
            "Diamanten brauchst du für Mekanism-Schaltkreise, den ersten Void-Miner-Kristall und vieles mehr."], [xp(100)], deps=["eisen"]),
        Q("jetpack", 12, -2, "Ab in die Luft", [item("ironjetpacks:jetpack")], [
            "&eIron Jetpacks&r bringen dich früh in die Luft. Sie laufen mit FE-Strom. Ein Jetpack aus Eisen reicht für den Anfang, später geht es bis Smaragd und darüber."], [xp(150)], deps=["diamant"]),
        Q("nether", 12, 1, "Ein heißer Ausflug", [dim("minecraft:the_nether")], [
            "Bau ein Netherportal und schau dich um. Für Draconic Evolution und einige Mekanism-Rezepte brauchst du später Nether-Materialien."], [xp(150), give("minecraft:golden_carrot", 8)], deps=["diamant"]),
    ]),
    ("mekanism", "Mekanism: Die Grundlagen", "mekanism:metallurgic_infuser", [
        Q("osmium", 0, 0, "Osmium", [item("mekanism:ingot_osmium", 8)], [
            "&bOsmium&r ist das Grundmetall von Mekanism. Du findest das Erz in mittlerer Tiefe, gleich verarbeitet wie Eisen."], [xp(50)], shape="hexagon", size=1.5),
        Q("infuser", 3, 0, "Der Metallurgische Infuser", [item("mekanism:metallurgic_infuser")], [
            "Der Infuser verbindet Metalle mit Zusätzen: aus Eisen und Kohle wird &7Stahl&r, aus Redstone werden &cLegierungen&r.",
            "Fast jede Mekanism-Maschine braucht ihn."], [xp(100)], deps=["osmium"]),
        Q("stahl", 6, -2, "Stahl", [item("mekanism:ingot_steel", 16)], ["Stahl steckt in jedem Maschinengehäuse."], [xp(50)], deps=["infuser"]),
        Q("schaltkreis", 6, 2, "Schaltkreise", [item("mekanism:basic_control_circuit", 4)], ["Grundschaltkreise aus Osmium und Redstone. Aus ihnen werden später die besseren Stufen."], [xp(50)], deps=["infuser"]),
        Q("energie", 9, 2, "Strom!", [item("mekanismgenerators:heat_generator")], [
            "Maschinen brauchen Strom. Der &cWärmegenerator&r läuft mit Brennstoff oder Lava, &eSolargeneratoren&r sind kostenlos, aber schwach.",
            "Wer es einfacher mag: &ePowah!&r liefert früh viel Strom."], [xp(80)], deps=["schaltkreis"]),
        Q("kabel", 12, 2, "Kabel und Speicher", [item("mekanism:basic_universal_cable", 16), item("mekanism:basic_energy_cube")], [
            "Universalkabel verteilen Strom, der Energiewürfel puffert ihn. Mit dem &eKonfigurator&r stellst du ein, welche Seite rein- und welche rausgibt."], [xp(80)], deps=["energie"]),
        Q("enrichment", 9, -2, "Doppelte Erze", [item("mekanism:enrichment_chamber")], [
            "Die &aAnreicherungskammer&r macht aus 1 Erz 2 Staub: die &e2-fache&r Ausbeute.",
            "Im Kapitel &bErzverarbeitung&r geht es bis zur &e5-fachen&r."], [xp(100), give("mekanism:upgrade_speed")], deps=["stahl", "energie"]),
        Q("konfigurator", 12, -2, "Der Konfigurator", [item("mekanism:configurator")], [
            "Mit Shift-Rechtsklick wechselst du den Modus, mit Rechtsklick auf eine Maschinenseite stellst du Ein- und Ausgänge ein. Unverzichtbar für Automatisierung."], [xp(50)], deps=["enrichment"]),
        Q("fabrik", 15, 0, "Fabriken", [item("mekanism:basic_smelting_factory")], [
            "Fabriken verarbeiten mehrere Items gleichzeitig. Mit Stufen-Upgrades werden sie bis zu 9 Plätze breit."], [xp(150)], deps=["konfigurator", "kabel"]),
    ]),
    ("erzverarbeitung", "Mekanism: Erzverarbeitung bis 5×", "mekanism:chemical_dissolution_chamber", [
        Q("x2", 0, 0, "2×: Anreichern", [item("mekanism:dirty_dust_iron", 8)], ["Schon erledigt, wenn du die Anreicherungskammer hast. Ab jetzt geht es aufwärts."], [xp(50)], shape="hexagon", size=1.5),
        Q("x3", 3, 0, "3×: Reinigen", [item("mekanism:purification_chamber"), item("mekanism:clump_iron", 8)], [
            "Die &aReinigungskammer&r nutzt Sauerstoff, um aus 1 Erz 3 Klumpen zu machen.",
            "Sauerstoff bekommst du aus dem &eelektrolytischen Separator&r (Wasser → Wasserstoff + Sauerstoff)."], [xp(100)], deps=["x2"]),
        Q("separator", 3, -3, "Wasser spalten", [item("mekanism:electrolytic_separator")], ["Liefert Sauerstoff und Wasserstoff, beides brauchst du noch oft."], [xp(80)], deps=["x2"]),
        Q("x4", 6, 0, "4×: Chemische Injektion", [item("mekanism:chemical_injection_chamber"), item("mekanism:shard_iron", 8)], [
            "Mit &eChlorwasserstoff&r wird aus 1 Erz 4 Scherben. Chlor kommt aus Salz, das du mit einer &eThermischen Verdampfungsanlage&r aus Wasser gewinnst."], [xp(150)], deps=["x3", "separator"]),
        Q("verdampfung", 6, -3, "Salz aus Wasser", [item("mekanism:thermal_evaporation_controller")], ["Die thermische Verdampfung ist ein Multiblock. Je höher, desto schneller. Sie macht aus Wasser Sole und Salz."], [xp(100)], deps=["separator"]),
        Q("x5", 9, 0, "5×: Auflösen und Kristallisieren", [item("mekanism:chemical_dissolution_chamber"), item("mekanism:chemical_washer"), item("mekanism:chemical_crystallizer")], [
            "Die Königsklasse: Erz wird mit Schwefelsäure aufgelöst, gewaschen und zu Kristallen geformt. &e1 Erz = 5 Barren&r.",
            "Bau die Kette Schritt für Schritt und verbinde alles mit Rohren. Ein Void Miner füttert sie später rund um die Uhr."], [xp(400), give("mekanism:upgrade_speed", 4)], deps=["x4", "verdampfung"], size=1.5),
        Q("digitalminer", 12, -2, "Der Digitale Miner", [item("mekanism:digital_miner")], ["Baut Erze in einem großen Radius automatisch ab, ohne Löcher in die Landschaft zu reißen. Mit Filtern holst du nur, was du willst."], [xp(300)], deps=["x5"]),
        Q("disassembler", 12, 2, "Atomarer Zerleger", [item("mekanism:atomic_disassembler")], ["Werkzeug für alles: Spitzhacke, Axt, Schaufel und Schwert in einem, mit Strom betrieben."], [xp(200)], deps=["x5"]),
        Q("teleporter", 15, 0, "Teleporter", [item("mekanism:teleporter")], ["Ein Multiblock-Teleporter, der dich (und Mitspieler) zwischen festen Punkten hin- und herschickt."], [xp(250)], deps=["digitalminer"]),
        Q("sps", 15, 3, "Antimaterie", [item("mekanism:sps_casing", 4), item("mekanism:pellet_antimatter")], [
            "Der &dSuperkritische Phasenwandler&r macht aus Polonium Antimaterie. Brauchst du für die besten Mekanism-Items wie die MekaSuit."], [xp(800)], deps=["disassembler"], shape="gear", size=1.5),
        Q("mekasuit", 18, 3, "&dMekaSuit", [item("mekanism:mekasuit_helmet"), item("mekanism:mekasuit_bodyarmor"), item("mekanism:mekasuit_pants"), item("mekanism:mekasuit_boots")], [
            "Die beste Rüstung von Mekanism: Fliegen, Nachtsicht, Schutz vor fast allem. Lässt sich mit Modulen ausbauen."], [xp(1500)], deps=["sps"], shape="hexagon", size=2.0),
    ]),
    ("industrial_foregoing", "Industrial Foregoing", "industrialforegoing:machine_frame_simple", [
        Q("latex", 0, 0, "Latex zapfen", [item("industrialforegoing:fluid_extractor"), item("industrialforegoing:latex_bucket")], [
            "Stell den &eFluid Extractor&r vor einen Baumstamm, er zapft langsam Latex. Mehrere Extraktoren an einem großen Baum gehen schneller."], [xp(80)], shape="hexagon", size=1.5),
        Q("plastik", 3, 0, "Plastik", [item("industrialforegoing:latex_processing_unit"), item("industrialforegoing:plastic", 16)], [
            "Die &eLatex Processing Unit&r macht aus Latex und Wasser getrockneten Gummi, im Ofen wird daraus &ePlastik&r: das Grundmaterial für alle Maschinen."], [xp(100)], deps=["latex"]),
        Q("rahmen", 6, 0, "Maschinenrahmen", [item("industrialforegoing:machine_frame_simple")], ["Der einfache Maschinenrahmen ist das Herz der ersten Maschinen. Später folgen fortgeschritten und supreme."], [xp(100)], deps=["plastik"]),
        Q("pflanzen", 9, -2, "Pflanzenfarm", [item("industrialforegoing:plant_sower"), item("industrialforegoing:plant_gatherer")], ["Säen und ernten, vollautomatisch. Die Fläche lässt sich mit Range-Addons vergrößern."], [xp(150)], deps=["rahmen"]),
        Q("mobs", 9, 2, "Mob-Farm", [item("industrialforegoing:mob_crusher")], ["Der &cMob Crusher&r tötet Mobs in seinem Bereich und sammelt Beute und Erfahrung als Flüssigkeit."], [xp(150)], deps=["rahmen"]),
        Q("pinkslime", 12, 2, "Pinker Schleim", [item("industrialforegoing:pink_slime_ingot", 4)], ["Aus Mob-Resten wird Pink Slime, daraus fortgeschrittene Teile. Eklig, aber nützlich."], [xp(200)], deps=["mobs"]),
        Q("blackhole", 12, -2, "Tierfarm", [item("industrialforegoing:animal_feeder"), item("industrialforegoing:animal_rancher")], ["Der &eAnimal Feeder&r füttert und vermehrt Tiere, der &eAnimal Rancher&r melkt und schert sie. Nie wieder von Hand Wolle sammeln."], [xp(150)], deps=["pflanzen"]),
        Q("laser", 15, 0, "Der Laserbohrer", [item("industrialforegoing:laser_drill")], [
            "Der &cLaser Drill&r holt mit Linsen gezielt Erze aus dem Boden. Eine schöne Ergänzung zum Void Miner."], [xp(400)], deps=["pinkslime", "blackhole"], size=1.5),
        Q("infinity", 18, 0, "&dUnendlicher Bohrer", [item("industrialforegoing:infinity_drill")], ["Ein Bohrer, der mit Strom und Biofuel wächst, bis er ganze Gebiete auf einmal abbaut."], [xp(800)], deps=["laser"], shape="hexagon", size=1.5),
    ]),
    ("refined_storage", "Refined Storage 2", "refinedstorage:controller", [
        Q("quarz", 0, 0, "Quarzangereichertes Eisen", [item("refinedstorage:quartz_enriched_iron", 16), item("refinedstorage:silicon", 8)], [
            "Die Grundzutaten von Refined Storage: Eisen mit Netherquarz und &eSilizium&r aus geschmolzenem Quarz."], [xp(80)], shape="hexagon", size=1.5),
        Q("prozessor", 3, 0, "Prozessoren", [item("refinedstorage:basic_processor", 4), item("refinedstorage:improved_processor", 2)], ["Prozessoren stecken in fast allen Bauteilen."], [xp(80)], deps=["quarz"]),
        Q("controller", 6, 0, "Der Controller", [item("refinedstorage:controller")], [
            "Herz des Netzes. Er braucht Strom (FE), alles andere wird per &eKabel&r angeschlossen. Anders als bei AE2 gibt es &akeine Kanäle&r."], [xp(150)], deps=["prozessor"], size=1.5),
        Q("speicher", 9, -2, "Erster Speicher", [item("refinedstorage:disk_drive"), item("refinedstorage:1k_storage_disk")], ["Das Laufwerk nimmt bis zu 8 Disks auf. Eine 1k-Disk fasst 1.000 Items beliebiger Sorten."], [xp(100)], deps=["controller"]),
        Q("grid", 9, 2, "Zugriff", [item("refinedstorage:crafting_grid")], ["Das Crafting Grid zeigt alles im Netz und hat eine Werkbank eingebaut. Mit &eJEI&r überträgst du Rezepte direkt hinein."], [xp(100)], deps=["controller"]),
        Q("bus", 12, 2, "Rein und raus", [item("refinedstorage:importer"), item("refinedstorage:exporter")], ["Importer ziehen Items aus Maschinen ins Netz, Exporter schieben sie hinein. So fütterst du z. B. die Mekanism-Erzverarbeitung."], [xp(100)], deps=["grid"]),
        Q("autocrafting", 15, 0, "Autocrafting", [item("refinedstorage:pattern_grid"), item("refinedstorage:autocrafter"), item("refinedstorage:pattern", 4)], [
            "Im Pattern Grid legst du Muster an, der &eAutocrafter&r stellt sie dann auf Bestellung her. Auch Maschinenrezepte (Verarbeitungsmuster) gehen."], [xp(300)], deps=["bus", "speicher"], size=1.5),
        Q("mehrplatz", 12, -2, "Mehr Platz", [item("extrastorage:disk_256k")], ["&eExtraStorage&r bringt riesige Disks und schnellere Autocrafter."], [xp(200)], deps=["speicher"]),
        Q("schneller", 18, -2, "Schnellere Busse", [item("cabletiers:elite_importer"), item("cabletiers:elite_exporter")], ["&eCable Tiers&r macht Importer und Exporter schneller und gibt ihnen mehr Filterplätze."], [xp(200)], deps=["autocrafting"]),
        Q("wireless", 18, 2, "Kabellos", [item("refinedstorage:wireless_transmitter"), item("universalgrid:wireless_universal_grid")], [
            "Mit dem Wireless Transmitter erreichst du dein Lager von überall. Das &eUniversal Grid&r schaltet zwischen Grid, Crafting Grid und Autocrafting-Monitor um."], [xp(300)], deps=["autocrafting"], shape="hexagon", size=1.5),
    ]),
    ("void_miner", "Der Void Miner", "voidminersremastered:ultimate_miner", [
        Q("rubetine", 0, 0, "&cRubetine", [item("voidminersremastered:rubetine_miner")], [
            "Der Void Miner bohrt in die Leere und holt Erze heraus. Stufe 1 entsteht aus &cRubetine&r (Redstone, Lohenstaub, Diamant).",
            "Er ist ein Multiblock: Kristallblöcke, Rahmen und Glas nach dem Bauplan, den JEI zeigt. Der Structure Builder hilft beim Bauen."], [xp(300)], shape="hexagon", size=2.0),
        Q("modifier", 0, 3, "Modifikatoren", [item("voidminersremastered:rubetine_speed_modifier")], [
            "Speed-, Energie- und Item-Modifikatoren verbessern deinen Miner. Ein Item-Modifikator lenkt ihn auf bestimmte Erze."], [xp(150)], deps=["rubetine"]),
        Q("solar", 3, 3, "Solar-Arrays", [item("voidminersremastered:solar_rubetine_panel")], ["Die Void Miner haben eigene Solar-Arrays in den gleichen 9 Stufen. Kostenloser Strom für die Leere."], [xp(150)], deps=["rubetine"]),
        Q("aurantium", 3, 0, "&6Aurantium", [item("voidminersremastered:aurantium_miner")], ["Stufe 2 baut Stufe 1 ab und bringt mehr Erzsorten."], [xp(400)], deps=["rubetine"]),
        Q("citrinetine", 6, 0, "&eCitrinetine", [item("voidminersremastered:citrinetine_miner")], ["Ab hier gibt es &5Draconium&r aus der Leere."], [xp(500)], deps=["aurantium"]),
        Q("verdium", 9, 0, "&aVerdium", [item("voidminersremastered:verdium_miner")], ["Mehr Ertrag, höherer Strombedarf."], [xp(600)], deps=["citrinetine"]),
        Q("azurine", 12, 0, "&9Azurine", [item("voidminersremastered:azurine_miner")], ["Die Mitte der Leiter. Zeit, die Solar-Arrays auszubauen."], [xp(700)], deps=["verdium"]),
        Q("caerium", 15, 0, "&bCaerium", [item("voidminersremastered:caerium_miner")], ["Seltene Erze werden häufiger."], [xp(800)], deps=["azurine"]),
        Q("amethystine", 18, 0, "&5Amethystine", [item("voidminersremastered:amethystine_miner")], ["Fast oben. Dein RS-Netz sollte jetzt groß sein."], [xp(900)], deps=["caerium"]),
        Q("rosarium", 21, 0, "&dRosarium", [item("voidminersremastered:rosarium_miner")], ["Die Vorstufe zum Ultimate-Kristall."], [xp(1000)], deps=["amethystine"]),
        Q("ultimate", 24, 0, "&f&lUltimate Void Miner", [item("voidminersremastered:ultimate_miner")], [
            "8 Rosarium-Blöcke und ein Netherstern. Der stärkste Miner, bis zu 700 FE/t Bedarf, und eine Erzflut ohne Ende."], [xp(2500), give("minecraft:nether_star")], deps=["rosarium"], shape="gear", size=2.0),
    ]),
    ("draconic", "Draconic Evolution", "draconicevolution:awakened_core", [
        Q("draconium", 0, 0, "Draconium", [item("draconicevolution:draconium_ingot", 16)], [
            "&5Draconium&r findest du tief unten, im Nether und im End (dort am meisten). Ab Citrinetine liefert es auch der Void Miner."], [xp(150)], shape="hexagon", size=1.5),
        Q("kern", 3, 0, "Draconium-Kern", [item("draconicevolution:draconium_core", 4)], ["Der Grundbaustein für alles Weitere."], [xp(150)], deps=["draconium"]),
        Q("fusion", 6, 0, "Fusion Crafting", [item("draconicevolution:crafting_core"), item("draconicevolution:basic_crafting_injector", 4)], [
            "Der Fusions-Kern in der Mitte, Injektoren drumherum (mit Blick auf den Kern). Jeder Injektor hält eine Zutat, der Kern das Hauptitem. Strom rein und los."], [xp(300)], deps=["kern"], size=1.5),
        Q("wyvern", 9, -2, "Wyvern-Kern", [item("draconicevolution:wyvern_core")], ["Der erste große Fusionsschritt. Mit Wyvern-Injektoren wird Fusion schneller."], [xp(400)], deps=["fusion"]),
        Q("energiekern", 9, 2, "Der Energiekern", [item("draconicevolution:energy_core"), item("draconicevolution:energy_core_stabilizer", 4), item("draconicevolution:energy_pylon")], [
            "Ein Multiblock-Akku, der in höheren Stufen Billionen FE speichert. Die Pylonen verbinden ihn mit deinem Netz."], [xp(400)], deps=["fusion"]),
        Q("drache", 12, -2, "Den Drachen besiegen", [kill("minecraft:ender_dragon")], ["Für die nächsten Stufen brauchst du ein &5Drachenherz&r. Ab in das End!"], [xp(500), give("minecraft:golden_apple", 2)], deps=["wyvern"]),
        Q("erwacht", 15, -2, "Erwachtes Draconium", [item("draconicevolution:awakened_draconium_ingot", 4), item("draconicevolution:awakened_core")], ["Mit dem Drachenherz erweckst du Draconium. Daraus wird die Draconic-Stufe."], [xp(800)], deps=["drache"]),
        Q("ruestung", 18, -2, "Draconic-Rüstung", [item("draconicevolution:draconic_chestpiece")], ["Fliegen, Schilde, Module. Mit dem Modul-System baust du sie nach deinen Wünschen aus."], [xp(1000)], deps=["erwacht"]),
        Q("chaos", 18, 2, "Der Chaos-Wächter", [kill("draconicevolution:draconic_guardian")], [
            "Auf der Chaos-Insel weit draußen im End wartet der &4Chaos-Wächter&r. Nur mit sehr guter Ausrüstung angehen! Er lässt &4Chaos-Splitter&r fallen."], [xp(2000)], deps=["ruestung", "energiekern"], shape="gear", size=1.5),
        Q("chaotisch", 21, 0, "Chaotischer Kern", [item("draconicevolution:chaos_shard"), item("draconicevolution:chaotic_core")], ["Die höchste Stufe. Chaotische Werkzeuge und Rüstung sind das Ende der Fahnenstange."], [xp(2000)], deps=["chaos"]),
        Q("reaktor", 24, 0, "&c&lDer Draconic-Reaktor", [item("draconicevolution:reactor_core"), item("draconicevolution:reactor_stabilizer", 4), item("draconicevolution:reactor_injector")], [
            "Unvorstellbar viel Strom, aber Vorsicht: ein schlecht eingestellter Reaktor explodiert und reißt einen riesigen Krater. Erst in einer Testwelt üben!"], [xp(3000)], deps=["chaotisch"], shape="gear", size=2.0),
    ]),
    ("abenteuer", "Abenteuer und Bosse", "minecraft:nether_star", [
        Q("twilight", 0, 0, "Der Zauberwald", [dim("twilightforest:twilight_forest")], [
            "Ein Teich aus 2×2 Wasser, Blumen drumherum, einen Diamanten hineinwerfen: schon öffnet sich das Portal in den &2Twilight Forest&r."], [xp(200), give("twilightforest:magic_map")], shape="hexagon", size=1.5),
        Q("naga", 3, -2, "Die Naga", [kill("twilightforest:naga")], ["Der erste Boss im Twilight Forest, in einem Hof mit Steinmauern."], [xp(300)], deps=["twilight"]),
        Q("lich", 6, -2, "Der Lich", [kill("twilightforest:lich")], ["Ganz oben im Turm des Lich. Achte auf seine Schilde und Kopien."], [xp(400)], deps=["naga"]),
        Q("hydra", 9, -2, "Die Hydra", [kill("twilightforest:hydra")], ["Im Feuersumpf. Mehrere Köpfe, viel Feuer. Feuerresistenz hilft enorm."], [xp(600)], deps=["lich"]),
        Q("ghast", 12, -2, "Der Ur-Ghast", [kill("twilightforest:ur_ghast")], ["Tief im Dunkelturm. Ein riesiger Ghast, der in Tränen ausbricht."], [xp(700)], deps=["hydra"]),
        Q("aether", 3, 2, "Der Himmel", [dim("aether:the_aether")], ["Ein Rahmen aus Glowstone und ein Wassereimer öffnen das Portal in den &eAether&r."], [xp(200)], deps=["twilight"]),
        Q("slider", 6, 2, "Der Slider", [kill("aether:slider")], ["Der erste Aether-Boss, ein rutschender Steinblock im Bronze-Dungeon."], [xp(300)], deps=["aether"]),
        Q("valkyrie", 9, 2, "Die Walkürenkönigin", [kill("aether:valkyrie_queen")], ["Im Silber-Dungeon. Sammle erst die Medaillen der Walküren."], [xp(500)], deps=["slider"]),
        Q("sonnengeist", 12, 2, "Der Sonnengeist", [kill("aether:sun_spirit")], ["Im Gold-Dungeon. Nur mit seinen eigenen Eiskristallen verwundbar."], [xp(700)], deps=["valkyrie"]),
        Q("wither", 15, 0, "Der Wither", [kill("minecraft:wither")], ["Drei Wither-Skelettschädel auf Seelensand. Der Netherstern brauchst du für den Ultimate Void Miner!"], [xp(800), give("minecraft:golden_apple", 2)], deps=["ghast", "sonnengeist"], size=1.5),
        Q("ignis", 18, -2, "Ignis", [kill("cataclysm:ignis")], ["Ein Boss aus &cL_Ender's Cataclysm&r, in der Feuer-Arena im Nether."], [xp(1000)], deps=["wither"]),
        Q("monstrosity", 18, 2, "Die Netherite-Monstrosität", [kill("cataclysm:netherite_monstrosity")], ["Ein riesiger Golem aus Netherite und Lava. Sehr viel Leben, sehr viel Schaden."], [xp(1000)], deps=["wither"]),
        Q("ender_guardian", 21, 0, "Der Ender-Wächter", [kill("cataclysm:ender_guardian")], ["Im Ruinierten Zitadellen-Turm im End. Bring Ender-Perlen und viel Geduld mit."], [xp(1500)], deps=["ignis", "monstrosity"], shape="gear", size=1.5),
        Q("otherside", 15, 4, "Die Otherside", [dim("deeperdarker:otherside")], ["Hinter der Ancient City wartet mit &8Deeper and Darker&r eine eigene, düstere Dimension."], [xp(500)], deps=["wither"]),
    ]),
]


# ---------------- SNBT schreiben ----------------
def s(v):
    return json.dumps(v, ensure_ascii=False)


def task_snbt(t, tid, ind):
    p = "\t" * ind
    lines = []
    if t["type"] == "item":
        if t["count"] > 1:
            lines.append(f"count: {t['count']}L")
        lines += [f"id: {s(tid)}", f"item: {{ count: 1, id: {s(t['item'])} }}", 'type: "item"']
    elif t["type"] == "kill":
        lines += [f"entity: {s(t['entity'])}", f"id: {s(tid)}", 'type: "kill"', f"value: {t['value']}L"]
    elif t["type"] == "dimension":
        lines += [f"dimension: {s(t['dimension'])}", f"id: {s(tid)}", 'type: "dimension"']
    else:
        lines += [f"id: {s(tid)}", 'type: "checkmark"']
    return p + "{\n" + "".join(p + "\t" + l + "\n" for l in lines) + p + "}"


def reward_snbt(r, rid, ind):
    p = "\t" * ind
    if r["type"] == "xp":
        lines = [f"id: {s(rid)}", 'type: "xp"', f"xp: {r['xp']}"]
    else:
        lines = ([f"count: {r['count']}"] if r["count"] > 1 else []) + [f"id: {s(rid)}", f"item: {{ count: 1, id: {s(r['item'])} }}", 'type: "item"']
    return p + "{\n" + "".join(p + "\t" + l + "\n" for l in lines) + p + "}"


def build(out):
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "chapters"))
    data = """{
\tdefault_autoclaim_rewards: "disabled"
\tdefault_consume_items: false
\tdefault_quest_disable_jei: false
\tdefault_quest_shape: "circle"
\tdefault_reward_team: false
\tdetection_delay: 20
\tdisable_gui: false
\tdrop_loot_crates: false
\temergency_items_cooldown: 300
\tgrid_scale: 0.5d
\ticon: {
\t\tid: "voidminersremastered:ultimate_miner"
\t}
\tlock_message: ""
\tloot_crate_no_drop: {
\t\tboss: 0
\t\tmonster: 600
\t\tpassive: 4000
\t}
\tpause_game: false
\tprogression_mode: "flexible"
\tshow_lock_icons: true
\tversion: 13
}
"""
    open(os.path.join(out, "data.snbt"), "w", encoding="utf-8", newline="\n").write(data)
    open(os.path.join(out, "chapter_groups.snbt"), "w", encoding="utf-8", newline="\n").write("{\n\tchapter_groups: [ ]\n}\n")
    lang = {"file": {"file.0000000000000001.title": "&5Void &d& &cDraconic"}, "chapter": {}, "chapters": {}}
    n_quests = 0
    for order, (fname, title, icon, quests) in enumerate(CHAPTERS):
        check_item(icon)
        cid = hid("chapter", fname)
        keys = {q["key"]: hid("quest", fname, q["key"]) for q in quests}
        out_q = []
        clang = {}
        for q in quests:
            qid = keys[q["key"]]
            for d in q["deps"]:
                if d not in keys:
                    errors.append(f"{fname}/{q['key']}: Abhängigkeit {d} unbekannt")
            L = ["{"]
            if q["deps"]:
                L.append("\tdependencies: [" + ", ".join(s(keys[d]) for d in q["deps"] if d in keys) + "]")
            if q["icon"]:
                L.append(f"\ticon: {{ id: {s(q['icon'])} }}")
            L.append(f"\tid: {s(qid)}")
            if q["rewards"]:
                L.append("\trewards: [\n" + "\n".join(reward_snbt(r, hid("reward", fname, q["key"], str(i)), 2) for i, r in enumerate(q["rewards"])) + "\n\t]")
            if q["shape"]:
                L.append(f"\tshape: {s(q['shape'])}")
            if q["size"]:
                L.append(f"\tsize: {q['size']}d")
            L.append("\ttasks: [\n" + "\n".join(task_snbt(t, hid("task", fname, q["key"], str(i)), 2) for i, t in enumerate(q["tasks"])) + "\n\t]")
            L.append(f"\tx: {float(q['x'])}d")
            L.append(f"\ty: {float(q['y'])}d")
            L.append("}")
            out_q.append("\n".join("\t\t" + l for l in L))
            clang[f"quest.{qid}.title"] = q["title"]
            if q["sub"]:
                clang[f"quest.{qid}.quest_subtitle"] = q["sub"]
            clang[f"quest.{qid}.quest_desc"] = q["desc"]
            n_quests += 1
        ch = (f"{{\n\tdefault_hide_dependency_lines: false\n\tdefault_quest_shape: \"\"\n\tfilename: {s(fname)}\n\tgroup: \"\"\n"
              f"\ticon: {{\n\t\tid: {s(icon)}\n\t}}\n\tid: {s(cid)}\n\torder_index: {order}\n\tquest_links: [ ]\n\tquests: [\n"
              + "\n".join(out_q) + "\n\t]\n}\n")
        open(os.path.join(out, "chapters", fname + ".snbt"), "w", encoding="utf-8", newline="\n").write(ch)
        lang["chapter"][f"chapter.{cid}.title"] = title
        lang["chapters"][fname] = clang

    def lang_snbt(d):
        out_l = []
        for k in sorted(d):
            v = d[k]
            if isinstance(v, list):
                out_l.append(f"\t{k}: [\n" + "\n".join("\t\t" + s(x) for x in v) + "\n\t]")
            else:
                out_l.append(f"\t{k}: {s(v)}")
        return "{\n" + "\n".join(out_l) + "\n}\n"

    for code in ("en_us", "de_de"):
        base = os.path.join(out, "lang", code)
        os.makedirs(os.path.join(base, "chapters"))
        open(os.path.join(base, "file.snbt"), "w", encoding="utf-8", newline="\n").write(lang_snbt(lang["file"]))
        open(os.path.join(base, "chapter.snbt"), "w", encoding="utf-8", newline="\n").write(lang_snbt(lang["chapter"]))
        for fname, d in lang["chapters"].items():
            open(os.path.join(base, "chapters", fname + ".snbt"), "w", encoding="utf-8", newline="\n").write(lang_snbt(d))
    return n_quests


n = build(OUT)
if errors:
    print("FEHLER:\n  " + "\n  ".join(errors))
    sys.exit(1)
print(f"ok: {len(CHAPTERS)} Kapitel, {n} Quests")
