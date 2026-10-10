// priority: 0
// Warnt alle Spieler 1 Minute vor dem automatischen Backup von Simple Backups (Timer aus simplebackups-common.toml).
// Simple Backups startet, sobald jetzt - timer > lastSaved ist (Millisekunden, kein Tick-Zähler).
// Das tägliche Backup um 04:00 (mc-backup-daily) warnt selbst per tellraw.
let VdBackupData = null, VdBackupConfig = null
try {
  VdBackupData = Java.loadClass('de.melanx.simplebackups.BackupData')
  VdBackupConfig = Java.loadClass('de.melanx.simplebackups.config.CommonConfig')
} catch (x) { console.warn('[Backup-Warnung] Simple Backups nicht gefunden: ' + x) }
let vdBackupWarnedFor = 0  // Fälligkeit (ms), für die schon gewarnt wurde

ServerEvents.tick(event => {
  let server = event.server
  if (!VdBackupData || server.tickCount % 20 != 0) return
  if (server.getPlayerList().getPlayers().isEmpty()) return
  try {
    if (!VdBackupConfig.isEnabled() || VdBackupConfig.useTickCounter()) return
    let data = VdBackupData.get(server)
    if (data.isPaused()) return
    let due = Number(data.getLastSaved()) + Number(VdBackupConfig.getTimer())
    let left = due - Date.now()
    if (left > 0 && left <= 60000 && vdBackupWarnedFor != due) {
      vdBackupWarnedFor = due
      let sec = Math.round(left / 1000)
      server.tell(Text.of('[Backup] ').gold().append(Text.yellow(`In ${sec >= 55 ? '1 Minute' : sec + ' Sekunden'} startet ein Backup. Es kann kurz ruckeln – am besten nichts Riskantes tun.`)))
      console.info(`[Backup-Warnung] Backup in ${sec} s angekündigt`)
    }
  } catch (x) { }
})
