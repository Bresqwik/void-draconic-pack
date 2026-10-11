// priority: 0
// Rezept-Konflikte mit gleichem Muster: Minecraft nimmt dann nur eines, Polymorph bietet nicht überall eine Auswahl.
// 2×2 Obsidian: Cataclysm (4 Obsidian-Ziegel) verdrängte Environmental Tech (8 Obsidian Plates, Grundteil für
// Modifier und Interconnects). Die Ziegel gibt es weiter über die Steinsäge (1 Obsidian → 1 Ziegel, gleiches Verhältnis).
ServerEvents.recipes(event => {
  event.remove({ id: 'cataclysm:obsidian_bricks' })
})
