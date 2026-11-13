"""Agenten, die nur lesen und ihr Ergebnis als JSON nach einem Schema liefern (ab Stufe 4: Planungsagenten).

Klärer, Spec-Schreiber, Test-Schreiber und Spec-Prüfer schreiben keine Dateien. Was sie erzeugen, kommt als JSON
zurück, und erst Pipeline-Code legt es ab. So bleibt ein schreibender Agent die Ausnahme (nur der Implementierer).
Flags und Fehlerbehandlung wie bei den Prüfern (`pruefer.py`), nur mit beliebigem Schema.
"""
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from entwicklung.pruefer import MAX_TURNS, STANDARD_MODELL, _runner, _umgebung

TYPEN = {"boolean": bool, "string": str, "array": list, "object": dict, "integer": int}


def passt(daten, schema: dict) -> bool:
    """Flache Prüfung: Objekt, alle Pflichtfelder da, oberste Ebene mit dem richtigen Typ."""
    if not isinstance(daten, dict) or not all(k in daten for k in schema.get("required", [])):
        return False
    for name, regel in schema.get("properties", {}).items():
        typ = TYPEN.get(regel.get("type"))
        if name in daten and typ and (not isinstance(daten[name], typ)
                                      or (typ is int and isinstance(daten[name], bool))):
            return False
    return True


def _ergebnis(name: str, start: float, daten=None, fehler=None) -> dict:
    return {"name": name, "ok": fehler is None, "daten": daten if fehler is None else None, "fehler": fehler,
            "dauer_s": round(time.monotonic() - start, 1)}


def claude_strukturiert(name: str, prompt: str, cwd: Path, schema: dict, modell: str = STANDARD_MODELL,
                        timeout: int = 600, effort: str | None = None, runner=None) -> dict:
    runner = _runner(runner)
    cmd = [shutil.which("claude") or "claude", "-p", "--model", modell,
           "--restricted", "--strict-mcp-config",
           "--permission-prompts", "none",
           "--settings", '{"disableAllHooks": true}',
           "--tools", "Read,Glob,Grep",
           "--json-schema", json.dumps(schema, ensure_ascii=False),
           "--output-format", "json",
           "--max-turns", str(MAX_TURNS)]
    if effort:
        cmd += ["--effort", effort]
    start = time.monotonic()
    try:
        lauf = runner(cmd, input=prompt, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                      errors="replace", timeout=timeout, env=_umgebung())
    except subprocess.TimeoutExpired:
        return _ergebnis(name, start, fehler=f"Timeout nach {timeout} s")
    except OSError as e:
        return _ergebnis(name, start, fehler=f"claude nicht startbar: {e}")
    roh = (lauf.stdout or "").lstrip("﻿").strip()
    if not roh:
        return _ergebnis(name, start, fehler=f"keine Ausgabe (rc={lauf.returncode})")
    try:
        antwort = json.loads(roh)
    except json.JSONDecodeError:
        return _ergebnis(name, start, fehler=f"keine gültige JSON-Ausgabe: {roh[:200]}")
    if antwort.get("is_error"):
        return _ergebnis(name, start, fehler=f"Agent meldet Fehler ({antwort.get('subtype', '?')})")
    if lauf.returncode != 0:
        return _ergebnis(name, start, fehler=f"claude endete mit rc={lauf.returncode}")
    daten = antwort.get("structured_output")
    if not passt(daten, schema):
        return _ergebnis(name, start, fehler="Ergebnis entspricht nicht dem Schema")
    return _ergebnis(name, start, daten=daten)


def codex_strukturiert(name: str, prompt: str, cwd: Path, schema: dict, timeout: int = 900, effort: str = "high",
                       runner=None) -> dict:
    runner = _runner(runner)
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="lab2-codex-") as tmp:
        schema_datei, ausgabe = Path(tmp) / "schema.json", Path(tmp) / "ergebnis.json"
        schema_datei.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
        cmd = [shutil.which("codex") or "codex", "exec", "-s", "read-only",
               "-c", "approval_policy=never", "-c", f'model_reasoning_effort="{effort}"',
               "--skip-git-repo-check", "--output-schema", str(schema_datei), "-o", str(ausgabe), "-"]
        try:
            lauf = runner(cmd, input=prompt, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, env=_umgebung())
        except subprocess.TimeoutExpired:
            return _ergebnis(name, start, fehler=f"Timeout nach {timeout} s")
        except OSError as e:
            return _ergebnis(name, start, fehler=f"codex nicht startbar: {e}")
        if not ausgabe.exists():
            return _ergebnis(name, start, fehler=f"keine Ergebnisdatei (rc={lauf.returncode})")
        try:
            daten = json.loads(ausgabe.read_text(encoding="utf-8").lstrip("﻿"))
        except json.JSONDecodeError:
            return _ergebnis(name, start, fehler="Ergebnisdatei ist kein gültiges JSON")
    if lauf.returncode != 0:
        return _ergebnis(name, start, fehler=f"codex endete mit rc={lauf.returncode}")
    if not passt(daten, schema):
        return _ergebnis(name, start, fehler="Ergebnis entspricht nicht dem Schema")
    return _ergebnis(name, start, daten=daten)
