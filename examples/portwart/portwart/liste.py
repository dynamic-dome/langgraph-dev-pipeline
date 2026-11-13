"""Lesen der Portliste ports.toml und Suche nach doppelten Ports."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


class ListenFehler(ValueError):
    """Die Portliste fehlt oder ist ungültig."""


@dataclass(frozen=True)
class Eintrag:
    port: int
    projekt: str
    zweck: str = ""
    pfad: str | None = None


def _lies_toml(pfad) -> dict:
    pfad = Path(pfad)
    try:
        with open(pfad, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise ListenFehler(f"Datei nicht gefunden: {pfad}") from None
    except tomllib.TOMLDecodeError as e:
        raise ListenFehler(f"kein gültiges TOML in {pfad}: {e}") from None
    except OSError as e:
        raise ListenFehler(f"Datei nicht lesbar: {pfad}: {e}") from None


def lade_ausschluss(pfad) -> list[str]:
    roh = _lies_toml(pfad).get("ausschluss", [])
    if not isinstance(roh, list) or not all(
        isinstance(x, str) and x.strip() for x in roh
    ):
        raise ListenFehler("'ausschluss' muss eine Liste von nicht leeren Texten sein")
    return roh


def lade(pfad) -> list[Eintrag]:
    daten = _lies_toml(pfad)

    roh = daten.get("port", [])
    if not isinstance(roh, list) or not all(isinstance(r, dict) for r in roh):
        raise ListenFehler("'port' muss eine Liste von Tabellen ([[port]]) sein")

    ergebnis = []
    for nr, r in enumerate(roh, 1):
        if "port" not in r:
            raise ListenFehler(f"Eintrag {nr}: Pflichtfeld 'port' fehlt")
        if "projekt" not in r:
            raise ListenFehler(f"Eintrag {nr}: Pflichtfeld 'projekt' fehlt")
        port, projekt, zweck = r["port"], r["projekt"], r.get("zweck", "")
        pfad = r.get("pfad")
        if isinstance(port, bool) or not isinstance(port, int):
            raise ListenFehler(f"Eintrag {nr}: 'port' muss eine ganze Zahl sein")
        if not 1 <= port <= 65535:
            raise ListenFehler(f"Eintrag {nr}: 'port' {port} liegt außerhalb von 1-65535")
        if not isinstance(projekt, str) or not projekt.strip():
            raise ListenFehler(f"Eintrag {nr}: 'projekt' muss ein nicht leerer Text sein")
        if not isinstance(zweck, str):
            raise ListenFehler(f"Eintrag {nr}: 'zweck' muss ein Text sein")
        if "pfad" in r and (not isinstance(pfad, str) or not pfad.strip()):
            raise ListenFehler(f"Eintrag {nr}: 'pfad' muss ein nicht leerer Text sein")
        ergebnis.append(Eintrag(port, projekt, zweck, pfad))
    return ergebnis


def doppelte(eintraege) -> dict[int, list[str]]:
    je_port: dict[int, set[str]] = {}
    for e in eintraege:
        je_port.setdefault(e.port, set()).add(e.projekt)
    return {p: sorted(pr) for p, pr in sorted(je_port.items()) if len(pr) >= 2}
