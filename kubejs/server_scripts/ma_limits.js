// priority: 0
// Mystical Agriculture begrenzen (Beschluss 12.10.2026, Liste: design/MA-ITEMLISTE.md):
// - Samen, die nicht in VD_MA_KEEP stehen, kann man nicht mehr herstellen (Infusion entfernt). Vorhandene Samen,
//   Felder und Essenz bleiben nutzbar – nur neue Samen gibt es nicht mehr.
// - Mystical-Samen wachsen nicht mehr in Botany Pots (alle Topf-Rezepte der Pflanzen entfernt).
// Weitere Bremsen: secondarySeedDrops = false (config/mysticalagriculture-common.toml), 3× langsameres Wachstum,
// Ackerboden nur in der Stufe des Samens und Mob-Samen 1× pro Team (vd-fixes).
const VD_MA_KEEP = [
  // Elemente + Grundlage
  'air', 'earth', 'fire', 'water', 'inferium',
  // Natur & Blöcke
  'stone', 'dirt', 'wood', 'ice', 'deepslate', 'nature', 'dye', 'nether', 'coral', 'honey', 'prismarine', 'end',
  // Vanilla-Ressourcen (begrenzt)
  'coal', 'amethyst', 'copper', 'iron', 'redstone', 'glowstone', 'nether_quartz', 'obsidian', 'gold', 'lapis_lazuli', 'diamond',
  // Mob-Samen bis Stufe 4 (begrenzt: 1× pro Team)
  'chicken', 'cow', 'pig', 'sheep', 'fish', 'squid', 'slime', 'turtle',
  'zombie', 'skeleton', 'creeper', 'spider', 'rabbit', 'blaze', 'ghast', 'enderman'
]

ServerEvents.recipes(event => {
  // alle Samen-Infusionen außer den erlaubten (die entfernten Samen blendet kubejs/assets/emi/index/stacks aus)
  event.remove({ id: new RegExp('^mysticalagriculture:seed/infusion/(?!(?:' + VD_MA_KEEP.join('|') + ')$).+$') })
  // Botany Pots: Pflanzen-Rezepte für Mystical-Samen (Böden bleiben, sie bringen ohne Pflanze nichts)
  event.remove({ id: /^botanypots:mysticalagriculture\/crop\// })
  event.remove({ id: /^botanypots:mysticalagradditions\/crop\// })
})
