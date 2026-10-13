// priority: 0
// Rezepte, die wegen Fehlern in Mods gar nicht laden (logs/kubejs/server.log: „Error parsing recipe“), hier nachgebaut.
ServerEvents.recipes(event => {
  // Forbidden Arcanus 2.2.6: Truhenboote nutzen fabric_value/forge_value als Zutat – Forge liest das nicht, das Rezept fehlte
  event.shapeless('forbidden_arcanus:edelwood_chest_boat', ['forbidden_arcanus:edelwood_boat', '#forge:chests/wooden']).id('kubejs:forbidden_arcanus/edelwood_chest_boat')
  event.shapeless('forbidden_arcanus:aurum_chest_boat', ['forbidden_arcanus:aurum_boat', '#forge:chests/wooden']).id('kubejs:forbidden_arcanus/aurum_chest_boat')
})
