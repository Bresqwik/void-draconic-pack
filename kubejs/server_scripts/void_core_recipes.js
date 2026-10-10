// priority: 0
// Rezepte für den Void-Kern: Jede Komponente bündelt das Endgame einer Säule, der Kern vereint alle sieben
// um ein Drachenei. Zutaten sind bewusst teuer – das ist das Ziel des ganzen Packs.
ServerEvents.recipes(event => {
  const shaped = (out, rows, keys) => event.shaped(out, rows, keys).id(`kubejs:${out.replace('kubejs:', '')}`)

  shaped('kubejs:core_technik', ['APA', 'CMC', 'APA'], {
    A: 'mekanism:alloy_atomic', P: 'create:precision_mechanism', C: 'mekanism:ultimate_control_circuit', M: 'mekanism:ultimate_induction_cell'
  })
  shaped('kubejs:core_magie', ['TGT', 'ESE', 'TLT'], {
    T: 'botania:terrasteel_ingot', G: 'botania:gaia_ingot', E: 'irons_spellbooks:arcane_essence',
    S: 'ars_nouveau:source_gem_block', L: 'irons_spellbooks:legendary_ink'
  })
  shaped('kubejs:core_dimension', ['LAH', 'VXF', 'UBK'], {
    L: 'twilightforest:lich_trophy', A: 'aether:enchanted_gravitite', H: 'twilightforest:hydra_trophy',
    V: 'blue_skies:horizonite_ingot', X: 'deeperdarker:heart_of_the_deep', F: 'theabyss:fusion_ingot',
    U: 'twilightforest:ur_ghast_trophy', B: 'the_bumblezone:essence_of_the_bees', K: 'twilightforest:knightmetal_ingot'
  })
  shaped('kubejs:core_lager', ['PNP', 'SCS', 'PNP'], {
    P: 'refinedstorage:advanced_processor', N: 'extrastorage:neural_processor', S: 'extrastorage:storagepart_1024k',
    C: 'refinedstorage:64k_storage_part'
  })
  shaped('kubejs:core_boss', ['IWI', 'CSC', 'IDI'], {
    I: 'cataclysm:ignitium_ingot', W: 'witherstormmod:withered_nether_star', C: 'cataclysm:cursium_ingot',
    S: 'minecraft:nether_star', D: 'deeperdarker:soul_crystal'
  })
  shaped('kubejs:core_draconic', ['FAF', 'ACA', 'FAF'], {
    F: 'draconicevolution:large_chaos_frag', A: 'draconicevolution:awakened_draconium_block', C: 'draconicevolution:chaotic_core'
  })
  shaped('kubejs:core_ressourcen', ['SIS', 'IBI', 'SIS'], {
    S: 'mysticalagriculture:supremium_block', I: 'mysticalagradditions:insanium_essence', B: 'mysticalagradditions:insanium_block'
  })
  shaped('kubejs:void_core', ['TMD', 'LEB', 'RCN'], {
    T: 'kubejs:core_technik', M: 'kubejs:core_magie', D: 'kubejs:core_dimension', L: 'kubejs:core_lager',
    E: 'minecraft:dragon_egg', B: 'kubejs:core_boss', R: 'kubejs:core_ressourcen', C: 'kubejs:core_draconic', N: 'minecraft:nether_star'
  })
})
