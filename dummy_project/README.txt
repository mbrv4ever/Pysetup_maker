Dummy test-project voor PySetup_Maker
======================================

Bestanden:
  main.py       - Hoofd Qt-app (klikteller + extras-check)
  icon.ico      - Paars icoontje met witte 'D'
  data.txt      - Test-extra (moet meegeinstalleerd worden)
  config.json   - Test-extra (idem)

Wat dit test:
  1. PySetup_Maker herkent main.py als hoofd-script
  2. PySetup_Maker pikt icon.ico op
  3. data.txt en config.json worden als extras voorgesteld
  4. Na build + installeren toont de app:
       - "data.txt gevonden: Dit is een test-bestand."
       - "config.json gevonden, version=1.0.0"
     Als die boodschappen "NIET gevonden" zeggen werkt de
     extras-flow nog niet goed.

Test stappen:
  1. Start PySetup_Maker
  2. Klik "Map kiezen..." en wijs naar deze map
  3. Verifieer dat alle 4 de velden auto-ingevuld zijn
  4. Klik "Maken"
  5. De output installer komt in: <deze map>/installer/
  6. Dubbel-klik die installer.exe
  7. Loop de wizard door
  8. Start de geinstalleerde Dummy_App.exe
  9. Beide statusregels moeten "gevonden" zeggen
 10. Check Apps en functies in Windows: Dummy_App moet er staan
 11. Verwijder via Apps en functies -> moet schoon weg zijn
