"""Der Implementierer: `claude -p` im Worktree, gehärtet und eingeschränkt.

Flag-Satz aus dem Spike vom 19.10. (docs/spike-2026-10-19-restricted.md), gemessen an Claude Code 2.1.303:
- --restricted: Dateiwerkzeuge nur im Arbeitsordner (cwd = Worktree), Befehls-Werkzeuge nur, wenn --tools sie nennt.
- --permission-prompts none: Was eine Rückfrage bräuchte, wird ohne Rückfrage verweigert (git, Netz, alles
  außerhalb der Allowlist). --allowedTools erlaubt nur den Testbefehl.
- --settings disableAllHooks, --strict-mcp-config: weder Hooks noch MCP-Server des Aufrufers.
- --output-format json: Ergebnis, Turns und permission_denials (was der Agent versucht hat) maschinenlesbar.
Dazu die Härtungen aus langgraph-lab/oekopuls/llm.py: shutil.which, Prompt per stdin in UTF-8, API-Keys aus der
Umgebung, BOM entfernen, Ausgabe vor dem Exit-Code auswerten.

Bekannte Lücke: Code, den der Agent über pytest ausführt, kann überall schreiben. Die Nachkontrolle
(worktree.grenzverletzungen) sieht davon nur, was in den geschützten Repos landet.
"""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

STANDARD_MODELL = "sonnet"
MAX_TURNS = 60
WERKZEUGE = "Read,Edit,Write,Glob,Grep,Bash"


class EchterAgentImTest(BaseException):
    """Ein Test wollte das echte claude als Implementierer starten.

    BaseException statt Exception: Der Graph fängt Agentenfehler ab und würde den Schutz sonst still in einen
    Befund verwandeln. So bricht der Test laut ab.
    """


_TESTSPERRE = False  # tests/conftest.py setzt das auf True


def implementierer_prompt(aufgabe_text: str, testbefehl_text: str) -> str:
    return f"""Du bist der Implementierer in einer Entwicklungs-Pipeline. Setze die folgende Aufgabe im aktuellen
Arbeitsordner um (ein git-Worktree des Zielrepos).

Regeln:
- Ändere nur Dateien in diesem Arbeitsordner. Schreibe nichts außerhalb, auch nicht über Testcode.
- kein git: Die Pipeline sichert dein Ergebnis selbst. Netz und andere Befehle sind gesperrt.
- Schreibe eigene Tests unter tests/ und führe sie aus mit genau diesem Befehl: {testbefehl_text}
- Halte dich genau an Namen, Signaturen, Ausgaben und Exit-Codes aus der Aufgabe. Unabhängige Tests prüfen das.
- Arbeite, bis deine Tests grün sind. Antworte am Ende mit einer kurzen Zusammenfassung auf Deutsch:
  welche Dateien, was sie tun, Testergebnis.

Aufgabe:
{aufgabe_text}
"""


def fix_prompt(aufgabe_text: str, runde: int, befunde: list[dict], testauszug: str | None,
               testbefehl_text: str) -> str:
    """Auftrag für eine Fix-Runde: was die Prüfer gefunden haben, im bestehenden Worktree beheben.

    Der Testauszug ist das, was ein Entwickler im CI sähe; die Akzeptanztest-Dateien selbst bleiben unsichtbar.
    """
    zeilen = [f"- [{', '.join(b['pruefer'])}] {b['path']}:{b['line']} — {b['claim']}" for b in befunde]
    auszug = f"\nTestausgabe der letzten Runde:\n```\n{testauszug}\n```\n" if testauszug else ""
    return f"""Du bist der Implementierer in einer Entwicklungs-Pipeline, Fix-Runde {runde}. Deine bisherige Arbeit liegt
schon im aktuellen Arbeitsordner (git-Worktree). Mach dort weiter, nicht von vorn.

Diese Befunde musst du beheben (sie lösen die Fix-Runde aus):
{chr(10).join(zeilen)}
{auszug}
Regeln:
- Ändere nur Dateien in diesem Arbeitsordner. Schreibe nichts außerhalb, auch nicht über Testcode.
- kein git: Die Pipeline sichert dein Ergebnis selbst. Netz und andere Befehle sind gesperrt.
- Ergänze oder korrigiere deine Tests unter tests/ und führe sie aus mit genau diesem Befehl: {testbefehl_text}
- Halte dich weiter genau an den Vertrag der Aufgabe. Unabhängige Tests prüfen ihn.
- Antworte am Ende mit einer kurzen Zusammenfassung auf Deutsch: was du je Befund geändert hast, Testergebnis.

Aufgabe:
{aufgabe_text}
"""


def _umgebung() -> dict:
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    return env


def _verweigerungen(daten: dict) -> list[str]:
    saetze = []
    for v in daten.get("permission_denials") or []:
        eingabe = v.get("tool_input") or {}
        ziel = eingabe.get("command") or eingabe.get("file_path") or json.dumps(eingabe, ensure_ascii=False)
        zeilen = ziel.strip().splitlines() or [""]
        kurz = zeilen[0][:120]
        if len(zeilen) > 1 or len(zeilen[0]) > 120:  # Heredocs und lange Befehle nur anreißen
            kurz += " …"
        saetze.append(f"{v.get('tool_name', '?')}: {kurz}")
    return saetze


def claude_implementierer(prompt: str, worktree: Path, python: str, modell: str = STANDARD_MODELL,
                          timeout: int = 600, effort: str | None = None, runner=None) -> dict:
    if runner is None:  # echtes claude
        if _TESTSPERRE:
            raise EchterAgentImTest("Tests dürfen das echte claude nicht starten – Fake über Abhaengigkeiten")
        runner = subprocess.run
    cmd = [shutil.which("claude") or "claude", "-p", "--model", modell,
           "--restricted", "--strict-mcp-config",
           "--permission-prompts", "none",
           "--permission-mode", "acceptEdits",
           "--settings", '{"disableAllHooks": true}',
           "--tools", WERKZEUGE,
           "--allowedTools", f"Bash({python} -m pytest:*)",
           "--output-format", "json",
           "--max-turns", str(MAX_TURNS)]
    if effort:  # Reasoning-Stufe aus der Tabelle (Stufe 6b-2)
        cmd += ["--effort", effort]
    ergebnis = {"ok": False, "zusammenfassung": "", "rc": None, "dauer_s": 0.0, "fehler": None,
                "turns": None, "verweigerungen": []}
    start = time.monotonic()
    try:
        lauf = runner(cmd, input=prompt, cwd=worktree, capture_output=True, text=True, encoding="utf-8",
                      errors="replace", timeout=timeout, env=_umgebung())
    except subprocess.TimeoutExpired:
        ergebnis.update(fehler=f"Timeout nach {timeout} s", dauer_s=round(time.monotonic() - start, 1))
        return ergebnis
    except OSError as e:
        ergebnis.update(fehler=f"claude nicht startbar: {e}", dauer_s=round(time.monotonic() - start, 1))
        return ergebnis
    ergebnis.update(rc=lauf.returncode, dauer_s=round(time.monotonic() - start, 1))
    roh = (lauf.stdout or "").lstrip("﻿").strip()
    if not roh:
        ergebnis["fehler"] = f"keine Ausgabe (rc={lauf.returncode}): {(lauf.stderr or '')[:200]}"
        return ergebnis
    try:
        daten = json.loads(roh)
    except json.JSONDecodeError:
        ergebnis["fehler"] = f"keine gültige JSON-Ausgabe: {roh[:200]}"
        return ergebnis
    ergebnis.update(zusammenfassung=(daten.get("result") or "").strip(), turns=daten.get("num_turns"),
                    verweigerungen=_verweigerungen(daten))
    if daten.get("is_error") or not ergebnis["zusammenfassung"]:
        ergebnis["fehler"] = f"Agent meldet Fehler ({daten.get('subtype', '?')})"
        return ergebnis
    if lauf.returncode != 0:  # auch mit brauchbar aussehendem JSON: Abbruch ist Abbruch
        ergebnis["fehler"] = f"claude endete mit rc={lauf.returncode}"
        return ergebnis
    ergebnis["ok"] = True
    return ergebnis
