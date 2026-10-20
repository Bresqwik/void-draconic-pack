// priority: 10
// Reparaturen an Block-Tags fremder Mods.
// The Abyss II 1.0.5 trägt den nicht existierenden Block theabyss:infused_magma in minecraft:mineable/pickaxe ein.
// Minecraft verwirft dann den ganzen Spitzhacken-Tag und alle Tags, die darauf aufbauen (Paxel, AIOT, Bohrer,
// Hammer, Mattock, Grabklauen): Stein und Erze lassen sich mit keiner Spitzhacke mehr richtig abbauen.
ServerEvents.tags('block', event => {
  event.remove('minecraft:mineable/pickaxe', 'theabyss:infused_magma')
})

// Leere Item-Tags, gefunden mit dem Rezept-Test (20.10.2026):
// - Fruitful Fun 7.9.1 liefert c:tulips, das Weak-Candle-Rezept fragt aber forge:tulips ab → Rezept ging nicht.
// - Better End 20.0.11 füllt seine Legier-Tags erst zur Laufzeit (Worlds Together TagManager), das greift im Pack
//   nicht → die 4 Legier-Rezepte im End-Schmelzofen (Eisen, Gold, Kupfer, Thallasium) hatten keine Zutaten.
//   Inhalt wie im Code von Better End (EndTags / MetalMaterial): Erz, Tiefenschiefer-Erz, Roh-Erz.
ServerEvents.tags('item', event => {
  event.add('forge:tulips', '#c:tulips')
  event.add('betterend:alloying_iron', ['minecraft:iron_ore', 'minecraft:deepslate_iron_ore', 'minecraft:raw_iron'])
  event.add('betterend:alloying_gold', ['minecraft:gold_ore', 'minecraft:deepslate_gold_ore', 'minecraft:raw_gold'])
  event.add('betterend:alloying_copper', ['minecraft:copper_ore', 'minecraft:deepslate_copper_ore', 'minecraft:raw_copper'])
  event.add('betterend:thallasium_alloying', ['betterend:thallasium_ore', 'betterend:thallasium_raw'])
})
