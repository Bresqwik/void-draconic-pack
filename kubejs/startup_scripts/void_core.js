// priority: 0
// Questbuch 2.0: Der Void-Kern (Endziel) und seine 7 Komponenten. Texturen: assets/kubejs/textures/item/<id>.png
// Namen kommen aus assets/kubejs/lang/de_de.json und en_us.json.
StartupEvents.registry('item', event => {
  event.create('void_core').maxStackSize(1).rarity('epic').glow(true).fireResistant(true)
  const parts = ['core_technik', 'core_magie', 'core_dimension', 'core_lager', 'core_boss', 'core_draconic', 'core_ressourcen']
  parts.forEach(id => event.create(id).maxStackSize(16).rarity('rare').fireResistant(true))
})
