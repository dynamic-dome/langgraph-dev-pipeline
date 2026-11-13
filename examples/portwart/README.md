# portwart

Eine zentrale Liste der lokalen Ports (`ports.toml`) und ein Prüfer dafür.
Übungsrepo für die Entwicklungs-Pipeline in `langgraph-lab-2`: Die Funktionen (Aufgaben A1 bis A9 unter
`aufgaben/portwart/`) hat die Pipeline selbst gebaut. Anlass waren Port-Kollisionen zwischen lokalen Diensten.
Dieser Ordner ist ein Abzug des Standes nach A9; die Demo (`python -m entwicklung demo`) macht daraus ein frisches
Git-Repo in einem Temp-Ordner.

```
python -m portwart pruefen        doppelte Ports in ports.toml melden
python -m portwart drift [WURZEL] [--datei PFAD]
                                  Port-Angaben im Code mit ports.toml vergleichen
                                  (nur lesend; --datei Standard: ports.toml)
python -m portwart eintragen NAME PORT [--datei PFAD] [--zweck TEXT] [--pfad PFAD]
                                  neuen [[port]]-Block anhängen (atomar, Rest bleibt byteweise gleich)
python -m portwart austragen NAME [--datei PFAD]
                                  genau einen [[port]]-Eintrag samt Untertabellen entfernen
                                  (atomar, Rest bleibt byteweise gleich)
```

`austragen`: Ausgabe `ausgetragen NAME PORT`, Exit 0 bei Erfolg, Exit 2 bei allen Fehlern
(Name unbekannt oder mehrfach, ungültige Liste, Schreibfehler). Kommentarzeilen bleiben stehen.
Nicht zeilenweise bearbeitbare Formen (z. B. `[["port"]]`, `port = [...]` als Inline-Array)
werden abgelehnt.
Entfernt wird der ganze Eintrag samt seiner Untertabellen `[port.…]` (`[port.meta]`,
`[[port.sub]]`, auch tiefer wie `[port.a.b]`), die zusammenhängend hinter ihm stehen;
fremde Tabellen wie `[andere]` bleiben stehen. Kann portwart nicht sicher erkennen, was zum
Eintrag gehört (z. B. eine Untertabelle erst hinter einer fremden Tabelle oder `["port".meta]`),
wird mit derselben Meldung abgelehnt und die Datei bleibt unberührt.

`drift`: Einträge mit `pfad` werden dort durchsucht, Einträge ohne `pfad` über den
Ordnernamen unter WURZEL (optional). Ausgabe je Befund eine Zeile:
`unbekannt PORT PROJEKT DATEI:ZEILE`, `abweichend PROJEKT LISTE=… CODE=… DATEI:ZEILE`,
`pfad-fehlt PROJEKT PFAD`; sonst `kein Drift`.
Exit 0 kein Befund, 1 mindestens ein Befund (auch nur `pfad-fehlt`), 2 Fehler
(ungültige Liste, Wurzel fehlt/kein Ordner/nicht lesbar, Projekt mit verschiedenen Pfaden).

Optionales Feld `pfad` in `ports.toml` (nicht leerer Text; `~` und relative Pfade
gelten ab dem Ordner der Liste):

```toml
[[port]]
port = 8766
projekt = "wiki"
pfad = "../wiki"
```

Nur `drift` wertet `pfad` aus; `pruefen`, `abgleich` und `frei` ignorieren es.
Alle Einträge eines Projekts brauchen denselben Pfad, sonst Exit 2.
