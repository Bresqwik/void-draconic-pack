// priority: 10
// Reparaturen an Block-Tags fremder Mods.
// The Abyss II 1.0.5 trägt den nicht existierenden Block theabyss:infused_magma in minecraft:mineable/pickaxe ein.
// Minecraft verwirft dann den ganzen Spitzhacken-Tag und alle Tags, die darauf aufbauen (Paxel, AIOT, Bohrer,
// Hammer, Mattock, Grabklauen): Stein und Erze lassen sich mit keiner Spitzhacke mehr richtig abbauen.
ServerEvents.tags('block', event => {
  event.remove('minecraft:mineable/pickaxe', 'theabyss:infused_magma')
})
