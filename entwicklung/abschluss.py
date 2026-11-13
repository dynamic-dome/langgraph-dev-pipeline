"""Stufe 7: Werkzeuge für den Abschluss (Gesamtreview, Tür-Bewertung, Einwände, Übernahme der Akzeptanztests).

Hier laufen keine Agenten. Der Graph (`graph_s4`) ruft Codex mit `gesamt_prompt` und `GESAMT_SCHEMA` und entscheidet
mit `einwaende`, ob `mergen` eine Begründung braucht.

Warum Codex das letzte Wort vor dem Merge hat: Spec, Plan und Code stammen aus der Claude-Familie. Das Urteil über
das Ganze soll die andere Modellfamilie fällen (wie die Sperre aus Stufe 6b-1). Kein Modell gibt sich selbst frei.

Die Tür (Merge-Danger-Zeile): „zweiseitig“ heißt, der Schritt lässt sich zurückholen; „einseitig“, er wirkt über
das Repo hinaus oder zerstört etwas (Migration, Löschen, Veröffentlichen, Produktions-DB, Rechte und Secrets).
`tuer_selbst` ist ein grobes Mindesturteil aus dem Diff, Codex prüft es gegen, und das strengere Urteil gilt.
"""
import re
import shutil
from pathlib import Path

from entwicklung.bericht import tests_zeile

GESAMT_GRENZE = 200_000  # Zeichen; der Verifier 6c lief mit 390 000
ABSCHLUSS_ENTSCHEIDUNGEN = ("mergen", "nicht_mergen")
PLATTFORM_MARKE = "plattform:"  # Skip-Grund, der als dokumentiert gilt (Festlegung 2026-11-13, Entscheidung 8)
RADIEN = ("Datei", "Modul", "Repo", "System")


def _objekt(**felder) -> dict:
    """Strenges Schema (Codex verlangt mit --output-schema: alle Felder Pflicht, keine zusätzlichen)."""
    return {"type": "object", "additionalProperties": False, "required": list(felder), "properties": felder}


_TEXT = {"type": "string"}

GESAMT_SCHEMA = _objekt(
    verdict={"type": "string", "enum": ["PASS", "FAIL"]},
    zusammenfassung=_TEXT,
    spec_erfuellt={"type": "boolean"},
    restpunkte={"type": "array", "items": _objekt(schwere={"type": "string", "enum": ["major", "minor"]},
                                                  aussage=_TEXT)},
    tuer=_objekt(urteil={"type": "string", "enum": ["einseitig", "zweiseitig"]},
                 radius={"type": "string", "enum": list(RADIEN)},
                 begruendung=_TEXT,
                 faelle={"type": "array", "items": _TEXT},
                 selbstbewertung_stimmt={"type": "boolean"}),
)

# Feste Liste einseitiger Fälle: (Name, Muster auf hinzugefügten Zeilen, Muster auf Pfaden aus --name-status,
# Status-Buchstaben, die allein schon zählen). Absichtlich grob: lieber ein Fehlalarm, den Codex entkräftet,
# als ein übersehener Fall.
EINSEITIG_FAELLE = (
    ("Schema-Migration", re.compile(r"\b(ALTER|DROP|CREATE)\s+TABLE\b", re.I),
     re.compile(r"(^|/)migrations/|\.sql$", re.I), ""),
    ("Löschen von Daten oder Dateien",
     re.compile(r"\b(rmtree|unlink|os\.remove|os\.rmdir|removedirs)\b|\bDELETE\s+FROM\b|\bTRUNCATE\b", re.I),
     None, "D"),
    ("Veröffentlichen", re.compile(r"\bgit\W+push\b|\bdeploy\b|\bpublish\b|\btwine\b|\bgh\s+release\b", re.I),
     re.compile(r"^\.github/workflows/"), ""),
    ("Produktions-DB schreiben", re.compile(r"\bsqlite3\.connect\b|\bINSERT\s+INTO\b|\bUPDATE\s+\w+\s+SET\b", re.I),
     re.compile(r"\.(db|sqlite3?)$", re.I), ""),
    ("Rechte, Konten, Secrets",
     re.compile(r"\b(chmod|chown|icacls|setx)\b|(api[_-]?key|secret|token|passw(or)?d)\w*\s*[:=]\s*['\"][^'\"]{8,}",
                re.I),
     re.compile(r"(^|/)\.env(\.|$)|\.(pem|key)$", re.I), ""),
)
SYSTEM_FAELLE = {"Schema-Migration", "Veröffentlichen", "Produktions-DB schreiben", "Rechte, Konten, Secrets"}


def _name_status(name_status: str) -> list[tuple[str, str]]:
    """(Status, Pfad) je Zeile; bei Umbenennung (R100<TAB>alt<TAB>neu) der neue Pfad."""
    eintraege = []
    for zeile in name_status.splitlines():
        teile = zeile.split("\t")
        if len(teile) >= 2 and teile[0]:
            eintraege.append((teile[0][0], teile[-1]))
    return eintraege


def _hinzugefuegt(diff: str) -> list[str]:
    return [z[1:] for z in diff.splitlines() if z.startswith("+") and not z.startswith("+++")]


def _radius(pfade: list[str], faelle: list[str]) -> str:
    if any(f.split(":")[0] in SYSTEM_FAELLE for f in faelle):
        return "System"
    if len(pfade) <= 1:
        return "Datei"
    ordner = {p.rsplit("/", 1)[0] if "/" in p else "" for p in pfade}
    return "Modul" if len(ordner) == 1 else "Repo"


def tuer_selbst(diff: str, name_status: str) -> dict:
    """Deterministisches Mindesturteil aus dem Diff basis..HEAD (nicht das Urteil des Implementierers)."""
    zeilen = _hinzugefuegt(diff)
    eintraege = _name_status(name_status)
    faelle = []
    for name, zeilen_muster, pfad_muster, status in EINSEITIG_FAELLE:
        treffer = next((z.strip() for z in zeilen if zeilen_muster.search(z)), None)
        if treffer is None:
            treffer = next((p for s, p in eintraege if (status and s in status)
                            or (pfad_muster is not None and pfad_muster.search(p))), None)
        if treffer is not None:
            faelle.append(f"{name}: {treffer[:80]}")
    return {"urteil": "einseitig" if faelle else "zweiseitig", "radius": _radius([p for _, p in eintraege], faelle),
            "faelle": faelle}


def tuer_endgueltig(selbst: dict, gesamt: dict | None) -> dict:
    """Das strengere Urteil gewinnt (einseitig vor zweiseitig, größerer Radius vor kleinerem), die Fälle beider
    zählen. Fehlt Codex, gilt die Selbstbewertung; `einwaende` meldet dann ohnehin „Gesamtreview fehlt“."""
    codex = (gesamt or {}).get("tuer")
    urteile = [selbst] + ([codex] if codex else [])
    urteil = "einseitig" if any(u.get("urteil") == "einseitig" for u in urteile) else "zweiseitig"
    radius = max((u.get("radius") for u in urteile if u.get("radius") in RADIEN), key=RADIEN.index,
                 default="Datei")
    faelle = list(dict.fromkeys(f for u in urteile for f in u.get("faelle") or []))
    uneinig = bool(codex) and codex.get("urteil") != selbst.get("urteil")
    return {"urteil": urteil, "radius": radius, "faelle": faelle, "selbst": selbst, "codex": codex,
            "uneinig": uneinig}


def skips_undokumentiert(testergebnis: dict | None) -> int:
    """Übersprungene Tests ohne Grund `plattform: …`. Ohne gesammelte Gründe (ältere Läufe) zählt jeder Skip."""
    if not testergebnis:
        return 0
    gesamt = testergebnis.get("uebersprungen") or 0
    gruende = testergebnis.get("skip_gruende") or []
    dokumentiert = sum(1 for g in gruende if str(g).strip().lower().startswith(PLATTFORM_MARKE))
    return max(gesamt - dokumentiert, 0)


def einwaende(gesamt: dict | None, tuer: dict | None = None, testergebnis: dict | None = None) -> list[str]:
    """Was `mergen` begründungspflichtig macht: major des Gesamtreviews oder sein Fehlen, eine einseitige Tür,
    übersprungene Tests ohne Plattform-Begründung. `gesamt` ist das Agentenergebnis {ok, daten, fehler}."""
    saetze = []
    if gesamt is None:
        saetze.append("Gesamtreview fehlt: nicht gelaufen")
    elif not gesamt.get("ok") or not gesamt.get("daten"):
        saetze.append(f"Gesamtreview fehlt: {gesamt.get('fehler') or 'kein verwertbares Ergebnis'}")
    else:
        saetze += [f"Gesamtreview (Codex) meldet major: {p['aussage']}" for p in gesamt["daten"].get("restpunkte") or []
                   if p.get("schwere") == "major"]
    if tuer and tuer.get("urteil") == "einseitig":
        saetze.append(f"Tür einseitig: {', '.join(tuer.get('faelle') or []) or 'ohne Fallangabe'}")
    n = skips_undokumentiert(testergebnis)
    if n:
        saetze.append(f"Tests übersprungen: {n} ohne Plattform-Begründung (unerwartete Skips sind eine Lücke, "
                      f"kein Bestehen)")
    return saetze


def _kuerze(text: str, grenze: int, was: str) -> str:
    if len(text) <= grenze:
        return text
    vermerk = f"\n… ({was} gekürzt, {len(text) - grenze} Zeichen fehlen)"
    return text[:max(grenze - len(vermerk), 0)] + vermerk


def gesamt_prompt(state: dict, diff: str, selbst: dict) -> str:
    """Prompt für das Gesamtreview. Codex liest unter Windows keine Dateien (Spike 19.10.), deshalb steht alles
    im Prompt: Spec, Plan, Diff, Befunde der letzten Runde, Testergebnis, Selbstbewertung der Tür."""
    befunde = state.get("befunde") or []
    befund_text = "\n".join(f"- [{b.get('severity', '?')}] {'+'.join(b.get('pruefer') or [])} "
                            f"{b.get('path', '?')}:{b.get('line', '?')}: {b.get('claim', '')}"
                            f"{' (auslösend)' if b.get('ausloesend') else ''}" for b in befunde) or "- (keine)"
    selbst_text = (f"{selbst['urteil']}, Radius {selbst['radius']}"
                   + (": " + "; ".join(selbst["faelle"]) if selbst.get("faelle") else ""))
    widerlegen = (" Diese Selbstbewertung („zweiseitig“, kleiner Radius) ist die am wenigsten belastbare: Versuche "
                  "ausdrücklich, sie zu widerlegen." if selbst["urteil"] == "zweiseitig" else "")
    kopf = f"""Du fällst das letzte Urteil vor einem lokalen Merge. Spec, Plan und Code hat die Claude-Familie
geschrieben; du gehörst zur anderen Modellfamilie und prüfst unabhängig. Alles, was du brauchst, steht hier im Prompt.

## Testergebnis
{tests_zeile(state.get("testergebnis"))}

## Befunde der letzten Prüfrunde
{befund_text}

## Tür (Selbstbewertung der Pipeline aus dem Diff)
{selbst_text}.{widerlegen}

## Auftrag
1. Erfüllt der Diff die Spec vollständig (`spec_erfuellt`)? Hält er den Plan und den Rahmen der Spec ein?
2. `restpunkte`: nur echte Probleme. `major`, wenn der Merge so nicht passieren sollte (Spec verfehlt, Fehler,
   Datenverlust, Sicherheitslücke). `verdict` FAIL bei mindestens einem major.
3. `tuer`: Ist der Merge-Inhalt umkehrbar (`zweiseitig`) oder wirkt er einseitig (Schema-Migration, Löschen von Daten
   oder Dateien, Veröffentlichen, Schreiben in eine Produktions-DB, Rechte/Konten/Secrets)? `radius`: Datei, Modul,
   Repo oder System. `faelle`: die einseitigen Fälle mit Fundstelle. `selbstbewertung_stimmt`: stimmt die
   Selbstbewertung oben? Ein Treffer in Tests, die nur Testdaten in einem Temp-Ordner anlegen, ist kein einseitiger
   Fall.
"""
    teile = [("Spec", state.get("spec") or ""), ("Plan", state.get("plan") or ""), ("Diff (basis..HEAD)", diff)]
    rest = GESAMT_GRENZE - len(kopf) - sum(len(f"\n## {t}\n\n") for t, _ in teile)
    # Spec und Plan höchstens je ein Viertel, der Diff bekommt den Rest
    spec = _kuerze(teile[0][1], rest // 4, "Spec")
    plan = _kuerze(teile[1][1], rest // 4, "Plan")
    diff_text = _kuerze(diff, rest - len(spec) - len(plan), "Diff")
    return kopf + f"\n## Spec\n{spec}\n\n## Plan\n{plan}\n\n## Diff (basis..HEAD)\n{diff_text}\n"


def uebernimm_tests(quelle: Path, ziel: Path) -> list[Path]:
    """Kopiert die erzeugten Akzeptanztests (*.py) nach aufgaben/<repo>/<id>/. Nie überschreiben: Existiert der
    Ordner schon (zweiter Lauf derselben Aufgabe), FileExistsError. Committet wird nicht (das macht der Mensch).
    Andere OSError (Rechte, Datenträger) gehen an den Aufrufer; eine Teilkopie bleibt dann stehen."""
    if ziel.exists():
        raise FileExistsError(f"{ziel} existiert schon, nichts übernommen")
    dateien = sorted(p for p in quelle.glob("*.py") if p.is_file())
    ziel.mkdir(parents=True)
    kopiert = []
    for datei in dateien:
        shutil.copy2(datei, ziel / datei.name)
        kopiert.append(ziel / datei.name)
    return kopiert
