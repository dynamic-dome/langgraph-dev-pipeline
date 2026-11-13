"""Planungsphase (ab Stufe 4): Schemas, Prompts und die Prüfung der Akzeptanztests, die ein Agent schreibt.

Die Planungsagenten lesen nur und liefern JSON (`strukturiert.py`). Dateien legt nur `lege_ab` an, und zwar unter
`berichte/<lauf_id>/`, außerhalb des Worktrees: Der Implementierer sieht weder Spec-Datei noch Tests.
`pruefe_akzeptanz` ist die erste Sicherung gegen schlechte Tests, deterministisch per `ast`. Die zweite ist die
Probe gegen main (Graph), die dritte sind die Spec-Prüfer, die letzte Dominics Freigabe.
"""
import ast
import re
import shutil
import sys
from pathlib import Path

from entwicklung.pfade import pruefe_schreibziel


def _objekt(**felder) -> dict:
    """Strenges Schema (Codex verlangt mit --output-schema: alle Felder Pflicht, keine zusätzlichen)."""
    return {"type": "object", "additionalProperties": False, "required": list(felder), "properties": felder}


_TEXT = {"type": "string"}


def _liste(items: dict) -> dict:
    return {"type": "array", "items": items}


KLAER_SCHEMA = _objekt(klar={"type": "boolean"}, verstaendnis=_TEXT, fragen=_liste(_TEXT))
_KOMPLEXITAET = {"type": "string", "enum": ["einfach", "mittel", "schwer"]}
SPEC_SCHEMA = _objekt(spec=_TEXT, schnittstellen=_liste(_objekt(modul=_TEXT, namen=_liste(_TEXT))),
                      annahmen=_liste(_TEXT), komplexitaet=_KOMPLEXITAET, komplexitaet_grund=_TEXT)
AKZEPTANZ_SCHEMA = _objekt(dateien=_liste(_objekt(name=_TEXT, inhalt=_TEXT)))
SPEC_PRUEF_SCHEMA = _objekt(verdict={"type": "string", "enum": ["PASS", "FAIL"]},
                            punkte=_liste(_objekt(schwere={"type": "string", "enum": ["major", "minor"]},
                                                  aussage=_TEXT)))
# ab 6b-2: Die Spec-Prüfer schätzen die Komplexität mit (Codex zählt: Gegenschätzung der anderen Familie)
SPEC_PRUEF_K_SCHEMA = _objekt(**SPEC_PRUEF_SCHEMA["properties"], komplexitaet=_KOMPLEXITAET,
                              komplexitaet_grund=_TEXT)
KOMPLEXITAET_TEXT = ("`komplexitaet`: `einfach` (eine Datei, klarer Vertrag), `mittel` (mehrere Dateien oder ein neuer "
                     "Befehl) oder `schwer` (der Dateivertrag ändert sich, Nebenläufigkeit oder Risiko von "
                     "Datenverlust). `komplexitaet_grund`: ein Satz. Danach richtet sich, welches Modell umsetzt und "
                     "prüft; im Zweifel die höhere Stufe.")
PLAN_SCHEMA = _objekt(plan=_TEXT, dateien=_liste(_TEXT))  # dateien: was der Plan anlegen/ändern will

ERLAUBT_OBEN = set(sys.stdlib_module_names) | {"pytest"}
DYNAMISCH_NAMEN = {"__import__", "exec", "eval", "compile", "importlib"}  # Umwege an der Importprüfung vorbei
ERLAUBTE_DUNDER = {"__file__", "__name__"}


def dateiname(aufgabe_id: str) -> str:
    return f"test_akzeptanz_{aufgabe_id.lower()}.py"


def _klaerung_text(klaerung: list[dict]) -> str:
    if not klaerung:
        return "(noch keine Rückfragen)"
    zeilen = []
    for i, k in enumerate(klaerung, 1):
        zeilen += [f"Runde {i}, Fragen:", *[f"- {f}" for f in k["fragen"]], f"Antwort von Dominic: {k['antwort']}"]
    return "\n".join(zeilen)


def _schnittstellen_text(schnittstellen: list[dict]) -> str:
    return "\n".join(f"- {s['modul']}: {', '.join(s['namen'])}" for s in schnittstellen) or "- (keine)"


def klaer_prompt(wunsch: str, klaerung: list[dict], runde: int, max_runden: int) -> str:
    return f"""Du klärst einen Entwicklungswunsch, bevor jemand eine Spec schreibt. Du liest das Repo im aktuellen
Ordner (nur lesen). Rückfragerunde {runde} von {max_runden}.

## Wunsch von Dominic
{wunsch}

## Bisherige Rückfragen und Antworten
{_klaerung_text(klaerung)}

## Auftrag
- Ist alles so klar, dass sich ein prüfbarer Vertrag (Module, Funktionen, CLI, Ausgabe, Exit-Codes, Fehler)
  schreiben lässt? Dann `klar: true` und keine Fragen.
- Sonst höchstens 5 kurze, konkrete Fragen, deren Antwort den Vertrag ändert. Keine Fragen, die das Repo
  beantwortet, und keine schon beantworteten. Biete bei jeder Frage eine sinnvolle Voreinstellung an; bei
  Grenzfällen ist sie: mit klarer Meldung ablehnen.
- `verstaendnis`: dein Verständnis des Wunsches in 2–4 Sätzen.
"""


def spec_prompt(wunsch: str, klaerung: list[dict], aenderung: str | None, vorige_spec: str | None,
                pruefpunkte: list[dict]) -> str:
    teile = [f"""Du schreibst die Spec für einen Entwicklungswunsch. Du liest das Repo im aktuellen Ordner (nur lesen),
damit die Spec zum vorhandenen Code passt.

## Wunsch von Dominic
{wunsch}

## Rückfragen und Antworten
{_klaerung_text(klaerung)}
"""]
    if vorige_spec:
        teile.append(f"## Vorige Fassung der Spec\n{vorige_spec}\n")
    if aenderung:
        teile.append(f"## Änderungswunsch von Dominic (Vorrang)\n{aenderung}\n")
    if pruefpunkte:
        teile.append("## Punkte der Spec-Prüfer zur vorigen Fassung\n"
                     + "\n".join(f"- [{p.get('pruefer', '?')}, {p['schwere']}] {p['aussage']}" for p in pruefpunkte)
                     + "\n")
    teile.append("""## Auftrag
`spec`: Markdown mit genau diesen Abschnitten:
- `# <Aufgabe>: <Titel>`
- `## Ziel` (2–4 Sätze)
- `## Vertrag`: Module und Funktionen mit Signatur, Ausnahmen, CLI-Befehl mit Optionen, Ausgabeformat zeilengenau,
  Exit-Codes, Fehlerfälle. So genau, dass jemand ohne Rückfrage Tests dafür schreiben kann.
- `## Rahmen` (nur Standardbibliothek, eigene Tests, Bestehendes bleibt unverändert)
- `## Annahmen` (was du selbst entschieden hast, weil es offen blieb)
`schnittstellen`: jedes Modul mit vollem Namen (z. B. `portwart.drift`) und den Namen, die Tests importieren dürfen,
auch vorhandene, die die Tests brauchen. `annahmen`: dieselben Annahmen als Liste.
Grenzfälle, die nur mit einer Sonderregel lösbar wären, lehnst du mit klarer Meldung ab und nennst das in `annahmen`.
""" + KOMPLEXITAET_TEXT + "\n")
    if vorige_spec:  # Zuschnitt-Bremse (6c): In A8 erzeugte jede lokale Korrektur neue Befunde
        teile.append("Gesamtsicht: Lies die ganze vorige Fassung gegen Wunsch und Antworten. Löse jeden Punkt "
                     "bevorzugt durch Streichen, Vereinfachen oder Ablehnen, keine neue Sonderregel. Die Spec wird nur "
                     "länger, wenn ein Punkt es verlangt.\n")
    return "\n".join(teile)


def akzeptanz_prompt(spec: str, schnittstellen: list[dict], aufgabe_id: str, gruende: list[str],
                     vorige: dict[str, str] | None = None, hinweis: str | None = None) -> str:
    teile = [f"""Du schreibst unabhängige Akzeptanztests für die folgende Spec. Den Code gibt es noch nicht; ein anderer
Agent setzt ihn später um und sieht deine Tests nie. Du liest das Repo im aktuellen Ordner (nur lesen).

## Spec
{spec}

## Erlaubte Schnittstellen (nur diese Namen importieren)
{_schnittstellen_text(schnittstellen)}

## Regeln (werden maschinell geprüft)
- Genau eine Datei `{dateiname(aufgabe_id)}`.
- Auf Modulebene nur Standardbibliothek und `pytest`. Den Zielcode importierst du **in den Testfunktionen**, und nur
  als `from <modul> import <name>` mit Namen aus der Liste oben.
- Die Datei liegt beim Testlauf zwei Ebenen unter dem Repo: `REPO = Path(__file__).resolve().parents[2]`.
- Die CLI rufst du mit `subprocess.run([sys.executable, "-m", "<paket>", ...], cwd=tmp_path,
  env=dict(os.environ, PYTHONPATH=str(REPO), PYTHONIOENCODING="utf-8"), capture_output=True, text=True,
  encoding="utf-8", timeout=60)` auf.
- Nur Dateien unter `tmp_path`, kein Netz, kein echtes netstat, nichts außerhalb von `tmp_path` schreiben.
- Kein `pytest.skip` und kein `skipif`: Ein übersprungener Test prüft nichts. Was auf diesem Rechner (Windows, ohne
  Rechte für Symlinks) nicht geht, simulierst du mit `monkeypatch`.
- 10 bis 30 Tests. Jeder prüft ein Verhalten aus der Spec (auch Fehlerfälle und Exit-Codes) mit genauen Werten.
  Keine Tests, die schon ohne den neuen Code bestehen, außer einem, der prüft, dass Bestehendes unverändert bleibt.
"""]
    if vorige:
        teile.append("## Deine vorige Fassung (verbessern, nicht von vorn)\n"
                     + "\n\n".join(f"### {n}\n```python\n{i}\n```" for n, i in vorige.items()) + "\n")
    if hinweis:
        teile.append(f"## Hinweis von Dominic zu den Tests (Vorrang)\n{hinweis}\n")
    if gruende:
        teile.append("## Dein voriger Versuch wurde abgelehnt\n" + "\n".join(f"- {g}" for g in gruende) + "\n")
    teile.append("Liefere `dateien` mit `name` und vollständigem `inhalt`.\n")
    return "\n".join(teile)


def plan_prompt(spec: str, schnittstellen: list[dict], aenderung: str | None, voriger_plan: str | None,
                pruefpunkte: list[dict]) -> str:
    teile = [f"""Du schreibst den Umsetzungsplan für eine freigegebene Spec. Ein anderer Agent setzt ihn danach um.
Du liest das Repo im aktuellen Ordner (nur lesen).

## Spec
{spec}

## Schnittstellen der Spec
{_schnittstellen_text(schnittstellen)}
"""]
    if voriger_plan:
        teile.append(f"## Voriger Plan\n{voriger_plan}\n")
    if aenderung:
        teile.append(f"## Änderungswunsch von Dominic (Vorrang)\n{aenderung}\n")
    if pruefpunkte:
        teile.append("## Punkte zur vorigen Fassung\n"
                     + "\n".join(f"- [{p.get('pruefer', '?')}, {p['schwere']}] {p['aussage']}" for p in pruefpunkte)
                     + "\n")
    teile.append("""## Auftrag
`plan`: Markdown, je Schritt eine Überschrift mit den Dateien. In jedem Schritt zuerst der Test (TDD), dann die
Umsetzung. Jede Schnittstelle der Spec kommt im Plan vor. Nichts außerhalb des Rahmens der Spec; `ports.toml` und
Akzeptanztests werden nicht angefasst.
`dateien`: alle Pfade, die der Plan anlegt oder ändert, relativ zum Repo, mit `/`.
""")
    return "\n".join(teile)


def plan_pruef_prompt(spec: str, plan: str, dateien: list[str]) -> str:
    return f"""Du prüfst einen Umsetzungsplan gegen die freigegebene Spec, bevor Dominic ihn freigibt. Du liest das Repo
im aktuellen Ordner (nur lesen, nichts ausführen).

## Spec
{spec}

## Plan
{plan}

## Dateien laut Plan
{chr(10).join(f"- {d}" for d in dateien) or "- (keine)"}

## Auftrag
Deckt der Plan jeden Teil des Vertrags ab? Hält er den Rahmen ein (nichts Bestehendes ändern, was die Spec nicht
erlaubt)? Würde ein Implementierer, der dem Plan folgt, die Spec erfüllen? `punkte` nur mit echten Problemen,
`major` wenn der Plan in die falsche Richtung führt. `verdict` FAIL bei mindestens einem major.
"""


def pruefe_plan(plan: str, dateien: list[str], schnittstellen: list[dict]) -> list[str]:
    """Deterministische Plan-Prüfung; die Gründe blockieren nicht, sie gehen in die Freigabe."""
    if not plan.strip():
        return ["Plan ist leer"]
    gruende = []
    for s in schnittstellen:
        kurz = s["modul"].rsplit(".", 1)[-1]
        if not (re.search(rf"\b{re.escape(kurz)}\b", plan) or s["modul"].replace(".", "/") + ".py" in plan):
            gruende.append(f"Modul {s['modul']} kommt im Plan nicht vor")
        gruende += [f"Schnittstelle {s['modul']}.{n} kommt im Plan nicht vor" for n in s["namen"]
                    if not re.search(rf"\b{re.escape(n)}\b", plan)]
    for d in dateien:
        teile = d.replace("\\", "/").split("/")
        if re.match(r"^[A-Za-z]:", d) or d.startswith(("/", "\\")):
            gruende.append(f"Datei {d}: absoluter Pfad")
        elif ".." in teile:
            gruende.append(f"Datei {d}: verlässt das Repo")
        elif teile[:2] == ["tests", "_akzeptanz"]:
            gruende.append(f"Datei {d}: Akzeptanztests sind tabu")
        elif teile[-1] == "ports.toml":
            gruende.append(f"Datei {d}: ports.toml wird nicht verändert")
    return gruende


def lege_plan_ab(ordner: Path, plan: str) -> Path:
    ordner = pruefe_schreibziel(ordner)
    ordner.mkdir(parents=True, exist_ok=True)
    pfad = ordner / "plan.md"
    pfad.write_text(plan, encoding="utf-8")
    return pfad


def spec_pruef_prompt(wunsch: str, klaerung: list[dict], spec: str, tests: dict[str, str]) -> str:
    dateien = "\n\n".join(f"### {name}\n```python\n{inhalt}\n```" for name, inhalt in tests.items())
    return f"""Du prüfst eine Spec und die daraus geschriebenen Akzeptanztests, bevor Dominic sie freigibt. Du liest
das Repo im aktuellen Ordner (nur lesen, nichts ausführen).

## Wunsch von Dominic
{wunsch}

## Rückfragen und Antworten
{_klaerung_text(klaerung)}

## Spec
{spec}

## Akzeptanztests
{dateien}

## Auftrag
Prüfe: Deckt die Spec den Wunsch und die Antworten ab? Ist sie eindeutig und widerspruchsfrei, passt sie zum
vorhandenen Code? Prüfen die Tests genau die Spec (nicht mehr, nicht weniger, richtige Werte), und würden sie eine
falsche Umsetzung finden? `punkte` nur mit echten Problemen, `major` wenn es die Umsetzung in die falsche Richtung
lenkt. `verdict` FAIL bei mindestens einem major.
Schätze außerdem, wie schwer die Umsetzung ist. {KOMPLEXITAET_TEXT}
"""


def _top(name: str | None) -> str:
    return (name or "").split(".")[0]


def pruefe_akzeptanz(dateien: list[dict], schnittstellen: list[dict], aufgabe_id: str) -> list[str]:
    """Gründe, warum die Tests nicht taugen; leer heißt in Ordnung."""
    if len(dateien) != 1:
        return [f"genau eine Datei erwartet, geliefert: {len(dateien)}"]
    name, inhalt = dateien[0]["name"], dateien[0]["inhalt"]
    gruende = []
    if name != dateiname(aufgabe_id):
        gruende.append(f"Dateiname {name!r}, erwartet {dateiname(aufgabe_id)!r}")
    try:
        baum = ast.parse(inhalt)
    except SyntaxError as e:
        return gruende + [f"Syntaxfehler Zeile {e.lineno}: {e.msg}"]
    erlaubt = {(s["modul"], n) for s in schnittstellen for n in s["namen"]}
    ziel_pakete = {_top(s["modul"]) for s in schnittstellen}
    in_funktion = {id(k) for f in ast.walk(baum) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
                   for k in ast.walk(f) if k is not f}
    for knoten in ast.walk(baum):
        if not isinstance(knoten, (ast.Import, ast.ImportFrom)):
            continue
        zeile = knoten.lineno
        if isinstance(knoten, ast.ImportFrom) and knoten.level:
            gruende.append(f"Zeile {zeile}: relativer Import")
            continue
        module = [a.name for a in knoten.names] if isinstance(knoten, ast.Import) else [knoten.module]
        if id(knoten) not in in_funktion:
            gruende += [f"Zeile {zeile}: Import von {m} auf Modulebene (nur Standardbibliothek und pytest)"
                        for m in module if _top(m) not in ERLAUBT_OBEN]
            continue
        for m in module:
            if _top(m) in ziel_pakete:
                if isinstance(knoten, ast.Import) or m not in {mod for mod, _ in erlaubt}:
                    gruende.append(f"Zeile {zeile}: Import {m} ist keine Schnittstelle der Spec "
                                   f"(nur `from <modul> import <name>`)")
                else:
                    gruende += [f"Zeile {zeile}: {m}.{a.name} ist keine Schnittstelle der Spec"
                                for a in knoten.names if (m, a.name) not in erlaubt]
            elif _top(m) not in ERLAUBT_OBEN:
                gruende.append(f"Zeile {zeile}: Import von {m} (weder Standardbibliothek noch Schnittstelle)")
    gruende += _dynamische_zugriffe(baum)
    if not any(isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f.name.startswith("test_")
               for f in ast.walk(baum)):
        gruende.append("keine Testfunktion (test_…)")
    return gruende


def _dunder(name) -> bool:
    return isinstance(name, str) and name.startswith("__") and name.endswith("__") and name not in ERLAUBTE_DUNDER


def _dynamische_zugriffe(baum: ast.AST) -> list[str]:
    """importlib, __import__, exec/eval und Dunder-Zugriffe wie __globals__ würden die Importprüfung umgehen."""
    gruende = []
    for k in ast.walk(baum):
        zeile = getattr(k, "lineno", "?")
        if isinstance(k, ast.Name) and k.id in DYNAMISCH_NAMEN:
            gruende.append(f"Zeile {zeile}: dynamischer Zugriff über {k.id}")
        elif isinstance(k, (ast.Import, ast.ImportFrom)):
            module = [a.name for a in k.names] if isinstance(k, ast.Import) else [k.module or ""]
            gruende += [f"Zeile {zeile}: dynamischer Zugriff über {m}" for m in module if _top(m) == "importlib"]
        elif isinstance(k, ast.Attribute) and _dunder(k.attr):
            gruende.append(f"Zeile {zeile}: dynamischer Zugriff über .{k.attr}")
        elif (isinstance(k, ast.Call) and isinstance(k.func, ast.Name) and k.func.id in ("getattr", "setattr")
              and any(isinstance(a, ast.Constant) and _dunder(a.value) for a in k.args)):
            gruende.append(f"Zeile {zeile}: dynamischer Zugriff über {k.func.id}(…, Dunder)")
    return gruende


def lege_ab(ordner: Path, spec: str, dateien: list[dict], aufgabe_id: str) -> Path:
    """Schreibt spec.md und akzeptanz/<aufgabe_id>/<datei>; ein voriger Versuch wird ersetzt."""
    for d in dateien:
        if Path(d["name"]).name != d["name"] or "\\" in d["name"] or not d["name"].endswith(".py"):
            raise ValueError(f"ungültiger Dateiname {d['name']!r}")
    ordner = pruefe_schreibziel(ordner)
    akz = ordner / "akzeptanz" / aufgabe_id
    if akz.exists():
        shutil.rmtree(akz)
    akz.mkdir(parents=True)
    (ordner / "spec.md").write_text(spec, encoding="utf-8")
    for d in dateien:
        (akz / d["name"]).write_text(d["inhalt"], encoding="utf-8")
    return akz
