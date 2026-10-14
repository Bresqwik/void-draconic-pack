// priority: 0
// Rezepte, die wegen Fehlern in Mods gar nicht laden (logs/kubejs/server.log: „Error parsing recipe“), hier nachgebaut.
ServerEvents.recipes(event => {
  // Forbidden Arcanus 2.2.6: Truhenboote nutzen fabric_value/forge_value als Zutat – Forge liest das nicht, das Rezept fehlte
  event.shapeless('forbidden_arcanus:edelwood_chest_boat', ['forbidden_arcanus:edelwood_boat', '#forge:chests/wooden']).id('kubejs:forbidden_arcanus/edelwood_chest_boat')
  event.shapeless('forbidden_arcanus:aurum_chest_boat', ['forbidden_arcanus:aurum_boat', '#forge:chests/wooden']).id('kubejs:forbidden_arcanus/aurum_chest_boat')

  // Powah 5.0.11: Uraninit-Erzblöcke (kommen aus dem Void Ore Miner oder mit Behutsamkeit) hatten kein Schmelzrezept –
  // nur der Energizing Orb verarbeitet sie (5/3/10). Ofen, Hochofen und Energized Smelter: so viel wie normales Abbauen.
  let ores = [['', 2], ['_poor', 1], ['_dense', 4]]
  ores.forEach(o => {
    let input = [`powah:uraninite_ore${o[0]}`, `powah:deepslate_uraninite_ore${o[0]}`]
    let tag = o[0] ? o[0].substring(1) : 'normal'
    event.smelting(Item.of('powah:uraninite', o[1]), input).xp(0.7).id(`kubejs:powah/uraninite_ore_${tag}_smelting`)
    event.blasting(Item.of('powah:uraninite', o[1]), input).xp(0.7).id(`kubejs:powah/uraninite_ore_${tag}_blasting`)
  })
})
