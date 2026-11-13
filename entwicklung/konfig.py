"""Zielkonfiguration: wie die Pipeline ein Zielrepo testet (entwicklung.toml im Zielrepo).

Gelesen wird immer aus dem Hauptrepo, nie aus dem Worktree: Der Implementierer könnte die Datei im Worktree
ändern und sich so einen bequemeren Testbefehl geben.
"""
import tomllib
from pathlib import Path


def lade_zielkonfig(repo: Path) -> dict:
    pfad = repo / "entwicklung.toml"
    try:
        daten = tomllib.loads(pfad.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"{pfad}: entwicklung.toml fehlt (python und testbefehl eintragen)") from None
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"{pfad}: entwicklung.toml ist kein gültiges TOML ({e})") from None
    python, befehl = daten.get("python"), daten.get("testbefehl")
    if not isinstance(python, str) or not python:
        raise ValueError(f"{pfad}: entwicklung.toml braucht python als Text")
    if not isinstance(befehl, list) or not befehl or not all(isinstance(t, str) for t in befehl):
        raise ValueError(f"{pfad}: entwicklung.toml braucht testbefehl als Liste von Texten")
    return {"python": python, "testbefehl": befehl}
