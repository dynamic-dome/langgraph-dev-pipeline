"""Die Prüfer: Security und Clean Code (`claude -p`, nur lesend), Codex (`codex exec -s read-only`) und Funktion.

Flag-Sätze aus dem Spike vom 19.10. (docs/spike-2026-10-19-pruefer.md):
- claude: --restricted mit nur Read/Glob/Grep, --json-schema; das Ergebnis steht in `structured_output`.
- codex: -s read-only, approval never, effort high, --output-schema, Ergebnis per -o in eine Temp-Datei. Codex kann
  hier keine Prozesse starten, deshalb stehen Diff und geänderte Dateien vollständig im Prompt.
Alle Berichte folgen review_schema.json (gleich dem REVIEW_SCHEMA.json von fusion-harness; liegt im Paket, damit
die Pipeline auch ohne fusion-harness läuft). Was nicht dem Schema genügt, ist „nicht verwertbar“,
nie ein stilles PASS.

Funktion ist bewusst kein LLM: funktion_bericht() macht aus dem gezählten Testergebnis Befunde.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from entwicklung import agenten

SCHEMA_PFAD = Path(__file__).resolve().parent / "review_schema.json"
STANDARD_MODELL = "sonnet"
MAX_ZEICHEN = 60_000  # Diff + Dateien im Prompt
MAX_TURNS = 30

ROLLEN = {
    "security": "Prüfe auf Sicherheitsprobleme: Ausführung oder Auswertung fremder Eingaben, Pfade außerhalb des "
                "Erwarteten, Schreibzugriffe, Subprozesse und ihre Argumente, Umgang mit Fehlern und Encodings, "
                "Geheimnisse im Code. Melde nur, was mit einer konkreten Eingabe zu einem Schaden führt.",
    "clean_code": "Prüfe auf Wartbarkeit und Korrektheit: Verstöße gegen den Vertrag der Aufgabe, doppelte Logik, "
                  "unklare Namen, zu lange Funktionen, fehlende Fehlerbehandlung, Lücken in den Tests. Reine "
                  "Stilfragen nur mit kind \"style\".",
    "codex": "Prüfe als unabhängiger Verifier: Erfüllt der Code den Vertrag der Aufgabe genau (Namen, Signaturen, "
             "Ausgaben, Exit-Codes)? Gibt es Logikfehler, Randfälle, Windows-Fallen oder Testlücken?",
}


def pruefer_prompt(rolle: str, aufgabe_text: str, diff: str, dateien: dict[str, str]) -> str:
    fokus = ROLLEN[rolle]
    rest = MAX_ZEICHEN - len(diff)
    teile = []
    for pfad, inhalt in sorted(dateien.items()):
        if rest <= 0:
            teile.append(f"### {pfad}\n[gekürzt: Datei weggelassen, Grenze von {MAX_ZEICHEN} Zeichen erreicht]")
            continue
        if len(inhalt) > rest:
            inhalt = inhalt[:rest] + f"\n[gekürzt: Rest der Datei weggelassen, Grenze {MAX_ZEICHEN} Zeichen]"
        rest -= len(inhalt)
        teile.append(f"### {pfad}\n```\n{inhalt}\n```")
    return f"""Du bist Prüfer ({rolle}) in einer Entwicklungs-Pipeline. Du liest nur, du änderst nichts.
{fokus}

Antworte ausschließlich im vorgegebenen JSON-Schema:
- `path` relativ zum Repo, `line` die Zeile in der Datei.
- `quote` wörtlich aus der genannten Datei (eine Zeile oder ein kurzer Ausschnitt), sonst wird der Befund verworfen.
- `status` "read-only", `check` sagt, wie du es geprüft hast.
- `verdict` "FAIL", sobald es einen Befund mit Schwere blocker oder major gibt, sonst "PASS".
- Was du nicht prüfen kannst, gehört in `not_checkable`.

## Aufgabe
{aufgabe_text}

## Diff
```diff
{diff}
```

## Geänderte Dateien (vollständig)
{chr(10).join(teile) if teile else "(keine)"}
"""


def schema_ok(bericht) -> bool:
    """Pflichtfelder aus review_schema.json; mehr prüft der Befund-Filter ohnehin."""
    if not isinstance(bericht, dict) or bericht.get("verdict") not in ("PASS", "FAIL"):
        return False
    befunde, offen = bericht.get("findings"), bericht.get("not_checkable")
    if not isinstance(befunde, list) or not isinstance(offen, list):
        return False
    texte = ("id", "severity", "kind", "path", "claim", "quote", "check", "status")

    def befund_ok(b) -> bool:  # Typen mitprüfen: ein path als Liste brachte den Filter zum Absturz (Export SEC-005)
        return (isinstance(b, dict) and all(isinstance(b.get(k), str) for k in texte)
                and isinstance(b.get("line"), int) and not isinstance(b.get("line"), bool))
    return (all(befund_ok(b) for b in befunde)
            and all(isinstance(n, dict) and all(isinstance(n.get(k), str) for k in ("what", "why", "need"))
                    for n in offen))


def _umgebung() -> dict:
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    return env


def _ergebnis(name: str, start: float, bericht=None, fehler=None) -> dict:
    return {"pruefer": name, "ok": fehler is None, "bericht": bericht if fehler is None else None,
            "fehler": fehler, "dauer_s": round(time.monotonic() - start, 1)}


def _runner(runner):
    if runner is None:  # echtes Programm
        if agenten._TESTSPERRE:
            raise agenten.EchterAgentImTest("Tests dürfen keine echten Prüfer starten – Fake über Abhaengigkeiten")
        return subprocess.run
    return runner


def claude_pruefer(rolle: str, prompt: str, worktree: Path, modell: str = STANDARD_MODELL, timeout: int = 600,
                   effort: str | None = None, runner=None) -> dict:
    runner = _runner(runner)
    cmd = [shutil.which("claude") or "claude", "-p", "--model", modell,
           "--restricted", "--strict-mcp-config",
           "--permission-prompts", "none",
           "--settings", '{"disableAllHooks": true}',
           "--tools", "Read,Glob,Grep",
           "--json-schema", SCHEMA_PFAD.read_text(encoding="utf-8"),
           "--output-format", "json",
           "--max-turns", str(MAX_TURNS)]
    if effort:
        cmd += ["--effort", effort]
    start = time.monotonic()
    try:
        lauf = runner(cmd, input=prompt, cwd=worktree, capture_output=True, text=True, encoding="utf-8",
                      errors="replace", timeout=timeout, env=_umgebung())
    except subprocess.TimeoutExpired:
        return _ergebnis(rolle, start, fehler=f"Timeout nach {timeout} s")
    except OSError as e:
        return _ergebnis(rolle, start, fehler=f"claude nicht startbar: {e}")
    roh = (lauf.stdout or "").lstrip("\ufeff").strip()
    if not roh:
        return _ergebnis(rolle, start, fehler=f"keine Ausgabe (rc={lauf.returncode})")
    try:
        daten = json.loads(roh)
    except json.JSONDecodeError:
        return _ergebnis(rolle, start, fehler=f"keine gültige JSON-Ausgabe: {roh[:200]}")
    if daten.get("is_error"):
        return _ergebnis(rolle, start, fehler=f"Prüfer meldet Fehler ({daten.get('subtype', '?')})")
    if lauf.returncode != 0:
        return _ergebnis(rolle, start, fehler=f"claude endete mit rc={lauf.returncode}")
    bericht = daten.get("structured_output")
    if not schema_ok(bericht):
        return _ergebnis(rolle, start, fehler="Bericht entspricht nicht dem Schema")
    return _ergebnis(rolle, start, bericht=bericht)


def codex_pruefer(prompt: str, worktree: Path, timeout: int = 900, runner=None) -> dict:
    runner = _runner(runner)
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="lab2-codex-") as tmp:
        ausgabe = Path(tmp) / "bericht.json"
        cmd = [shutil.which("codex") or "codex", "exec", "-s", "read-only",
               "-c", "approval_policy=never", "-c", 'model_reasoning_effort="high"',
               "--skip-git-repo-check", "--output-schema", str(SCHEMA_PFAD), "-o", str(ausgabe), "-"]
        try:
            lauf = runner(cmd, input=prompt, cwd=worktree, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, env=_umgebung())
        except subprocess.TimeoutExpired:
            return _ergebnis("codex", start, fehler=f"Timeout nach {timeout} s")
        except OSError as e:
            return _ergebnis("codex", start, fehler=f"codex nicht startbar: {e}")
        if not ausgabe.exists():
            return _ergebnis("codex", start, fehler=f"keine Ergebnisdatei (rc={lauf.returncode})")
        try:
            bericht = json.loads(ausgabe.read_text(encoding="utf-8").lstrip("\ufeff"))
        except json.JSONDecodeError:
            return _ergebnis("codex", start, fehler="Ergebnisdatei ist kein gültiges JSON")
    if lauf.returncode != 0:
        return _ergebnis("codex", start, fehler=f"codex endete mit rc={lauf.returncode}")
    if not schema_ok(bericht):
        return _ergebnis("codex", start, fehler="Bericht entspricht nicht dem Schema")
    return _ergebnis("codex", start, bericht=bericht)


def _befund(nr: int, claim: str, kind: str = "bug") -> dict:
    return {"id": f"FUNK-{nr}", "severity": "blocker", "kind": kind, "path": "tests", "line": 0, "claim": claim,
            "quote": "", "check": "pytest im Worktree, gezählt aus dem JUnit-XML", "status": "executed"}


def funktion_bericht(testergebnis: dict) -> dict:
    """Deterministisch: Befunde aus dem gezählten Testergebnis, ohne LLM."""
    t = testergebnis
    a = t["akzeptanz"]
    claims = []
    if not (a["erwartet"] is not None and a["gesammelt"] == a["erwartet"] and a["bestanden"] == a["gesammelt"]):
        skip = a.get("uebersprungen") or 0  # sonst sähe ein übersprungener Test aus wie ein roter
        claims.append((f"Akzeptanztests {a['bestanden']}/{a['gesammelt']} bestanden, erwartet {a['erwartet']}"
                       + (f", davon {skip} übersprungen (auf diesem Rechner nicht ausführbar)" if skip else ""),
                       "bug"))
    if t["fehlgeschlagen"] or t["fehler"]:
        claims.append((f"{t['fehlgeschlagen']} Tests fehlgeschlagen, {t['fehler']} Fehler", "bug"))
    rc = t.get("rc") or {}
    if any(wert not in (0, None) for wert in rc.values()) or rc.get("eigene") is None:
        claims.append((f"pytest-Exit-Code eigene={rc.get('eigene')}, akzeptanz={rc.get('akzeptanz')}", "bug"))
    if t["gesammelt"] - a["gesammelt"] <= 0:
        claims.append(("keine eigenen Tests des Implementierers gelaufen", "test-gap"))
    if not t["gruen"] and not claims:
        claims.append(("Testlauf nicht grün", "bug"))
    if t["gruen"]:
        claims = []
    befunde = [_befund(i, claim, kind) for i, (claim, kind) in enumerate(claims, 1)]
    bericht = {"verdict": "FAIL" if befunde else "PASS", "findings": befunde, "not_checkable": []}
    return {"pruefer": "funktion", "ok": True, "bericht": bericht, "fehler": None, "dauer_s": 0.0}
