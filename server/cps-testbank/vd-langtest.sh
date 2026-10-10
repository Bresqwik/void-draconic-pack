#!/bin/sh
# Langzeittest C2ME (8 Threads, alle 12 Kerne): Oberwelt r1500, dann Nether r1000 und Twilight Forest r750 im selben Server
B=/usr/local/sbin/vd-bench
$B lang_ow --label "Langzeit: Oberwelt r1.500" --radius 1500 --cpus 0-11 --xmx 12G --keep
$B lang_nether --label "Langzeit: Nether r1.000" --dim minecraft:the_nether --radius 1000 --center "2500 2500" --cpus 0-11 --xmx 12G --attach --keep
$B lang_tf --label "Langzeit: Twilight Forest r750" --dim twilightforest:twilight_forest --radius 750 --center "0 0" --cpus 0-11 --xmx 12G --attach --keep
echo FERTIG > /opt/vd-cps-test/results/_langtest.done
