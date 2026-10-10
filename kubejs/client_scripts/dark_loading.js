// Ladebildschirm: dunkler statt roter Mojang-Hintergrund. Den sieht man ganz am Ende des Ladens ein paar Sekunden,
// während der Titelbildschirm aufgebaut wird (danach übernimmt FancyMenu). Entspricht der Videoeinstellung „Monochromes Logo“.
try {
  let vdMc = Java.loadClass('net.minecraft.client.Minecraft').getInstance()
  if (vdMc && vdMc.options) {
    vdMc.options.darkMojangStudiosBackground().set(true)
    console.info('[VD] dunkler Ladehintergrund aktiv')
  } else {
    console.warn('[VD] Optionen beim Laden noch nicht da – Ladehintergrund unverändert')
  }
} catch (e) {
  console.warn('[VD] dunkler Ladehintergrund: ' + e)
}
