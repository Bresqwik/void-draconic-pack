// priority: 0
// Rezept-Konflikte mit gleichem Muster: Minecraft nimmt dann nur eines, Polymorph bietet nicht überall eine Auswahl.
// 2×2 Obsidian: Cataclysm (4 Obsidian-Ziegel) verdrängte Environmental Tech (8 Obsidian Plates, Grundteil für
// Modifier und Interconnects). Die Ziegel gibt es weiter über die Steinsäge (1 Obsidian → 1 Ziegel, gleiches Verhältnis).
// Absent by Design hat für die Obsidian-Falltür dasselbe 2×2-Muster (im RS-Grid kam die Falltür statt der Plates);
// die Falltür gibt es jetzt über die Steinsäge (1 Obsidian → 1 Falltür).
ServerEvents.recipes(event => {
  event.remove({ id: 'cataclysm:obsidian_bricks' })
  event.remove({ id: 'absentbydesign:trapdoor_obsidian' })
  event.stonecutting('absentbydesign:trapdoor_obsidian', 'minecraft:obsidian').id('kubejs:trapdoor_obsidian_stonecutting')
})
