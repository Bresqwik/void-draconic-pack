// priority: 0
// Rezept-Konflikte mit gleichem Muster: Minecraft nimmt dann nur eines, Polymorph bietet nicht überall eine Auswahl.
// 2×2 Obsidian: Cataclysm (4 Obsidian-Ziegel) verdrängte Environmental Tech (8 Obsidian Plates, Grundteil für
// Modifier und Interconnects). Die Ziegel gibt es weiter über die Steinsäge (1 Obsidian → 1 Ziegel, gleiches Verhältnis).
// Absent by Design hat für die Obsidian-Falltür dasselbe 2×2-Muster (im RS-Grid kam die Falltür statt der Plates);
// die Falltür gibt es jetzt über die Steinsäge (1 Obsidian → 1 Falltür).
// Extra Disks und Extra Storage (beides RS-Addons) haben für 7 Speicherteile identische Rezepte. Es bleibt das Rezept von
// Extra Disks; die Teile von Extra Storage gibt es per 1:1-Umwandlung im Crafting-Grid (in beide Richtungen, Quests nutzen beide).
// Ender IO Wood Gear (Grundteil für Maschinen) hatte dasselbe Muster wie Supplementaries Timber Frame (4 Stöcke im Kreuz) und
// Timber Cross Brace (4 Stöcke in den Ecken). Die Supplementaries-Rezepte bekommen ein Brett in die Mitte. Decorative Blocks
// Lattice (4 Vanilla-Stöcke im Kreuz) ebenso: Lattice jetzt mit 5 Stöcken als Plus (Muster war noch frei).
// Industrial Foregoing Iron/Gold Gear (4 Barren im Kreis, Maschinenteil) und Aether Iron/Golden Ring hatten dasselbe Muster –
// im RS-Grid/Autocrafting kam immer der Ring. Die Ringe bekommen ein Nugget in die Mitte, die Zahnräder bleiben wie gewohnt.
const VD_RS_PARTS = [
  ['256k_storage_part', 'storagepart_256k'], ['1024k_storage_part', 'storagepart_1024k'],
  ['4096k_storage_part', 'storagepart_4096k'], ['16384k_storage_part', 'storagepart_16384k'],
  ['16384k_fluid_storage_part', 'storagepart_16384k_fluid'], ['65536k_fluid_storage_part', 'storagepart_65536k_fluid'],
  ['262144k_fluid_storage_part', 'storagepart_262144k_fluid']
]
ServerEvents.recipes(event => {
  event.remove({ id: 'cataclysm:obsidian_bricks' })
  event.remove({ id: 'absentbydesign:trapdoor_obsidian' })
  event.stonecutting('absentbydesign:trapdoor_obsidian', 'minecraft:obsidian').id('kubejs:trapdoor_obsidian_stonecutting')

  VD_RS_PARTS.forEach(p => {
    event.remove({ id: 'extrastorage:part/' + p[1] })
    event.shapeless('extrastorage:' + p[1], ['extradisks:' + p[0]]).id('kubejs:rs_parts/to_extrastorage_' + p[1])
    event.shapeless('extradisks:' + p[0], ['extrastorage:' + p[1]]).id('kubejs:rs_parts/to_extradisks_' + p[0])
  })

  event.remove({ id: 'supplementaries:timber_frame' })
  event.remove({ id: 'supplementaries:timber_cross_brace' })
  event.shaped('supplementaries:timber_frame', [' S ', 'SPS', ' S '], { S: '#forge:rods/wooden', P: '#minecraft:planks' }).id('kubejs:supplementaries/timber_frame')
  event.shaped('supplementaries:timber_cross_brace', ['S S', ' P ', 'S S'], { S: '#forge:rods/wooden', P: '#minecraft:planks' }).id('kubejs:supplementaries/timber_cross_brace')
  event.remove({ id: 'decorative_blocks:lattice' })
  event.shaped('decorative_blocks:lattice', [' S ', 'SSS', ' S '], { S: 'minecraft:stick' }).id('kubejs:decorative_blocks/lattice')

  event.remove({ id: 'aether:iron_ring' })
  event.remove({ id: 'aether:golden_ring' })
  event.shaped('aether:iron_ring', [' I ', 'INI', ' I '], { I: 'minecraft:iron_ingot', N: 'minecraft:iron_nugget' }).id('kubejs:aether/iron_ring')
  event.shaped('aether:golden_ring', [' G ', 'GNG', ' G '], { G: 'minecraft:gold_ingot', N: 'minecraft:gold_nugget' }).id('kubejs:aether/golden_ring')
})
