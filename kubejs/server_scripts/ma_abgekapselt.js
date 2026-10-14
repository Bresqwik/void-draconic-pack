// priority: 0
// Mystical Agriculture „abgekapselt“ (Stefan, 14.10.2026 – live erst, nachdem byLapus2 alle Mystical-Quests geschafft hat):
// MA dient nur noch sich selbst. Essenz ergibt keine Ressourcen mehr – weder Vanilla (Eisen, Diamant …) noch Sachen anderer
// Mods (Mekanism, Botania, Ender IO …). Was MA für sich braucht (Samen, Werkzeuge, Rüstung, Maschinen, Augments, eigene
// Essenz-Stufen, Soulium-Staub, Erfahrungs-Tropfen) bleibt. Andere Mods dürfen MA-Sachen weiter verarbeiten.
// Die Void-Kern-Komponente „Ressourcen“ kommt ohne MA aus (void_core_recipes.js).
ServerEvents.recipes(event => {
  // alle Essenz-Rezepte außer denen, die MA-eigene Items ergeben
  event.remove({ id: /^mysticalag(riculture|radditions):essence\/(?!mysticalagriculture\/soulium_dust$|minecraft\/experience_droplet$|dragon_egg_chunk$|nether_star_shard$).+$/ })
  // MA-Zwischenstufen, die zu fremden Items werden
  event.remove({ id: 'mysticalagradditions:nether_star' })          // Netherstern-Splitter → Netherstern
  event.remove({ id: 'mysticalagradditions:dragon_egg' })           // Drachenei-Brocken → Drachenei
  event.remove({ id: 'mysticalagradditions:wither_skeleton_skull' })
  event.remove({ id: 'mysticalagriculture:experience_bottle' })     // Erfahrungs-Tropfen → Erfahrungsfläschchen
})
