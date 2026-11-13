"""Maschinenspezifische Einstellungen: nichts davon steht fest im Code.

Quelle 1: Umgebungsvariablen (haben Vorrang). Quelle 2: `lokal.toml` im Projektordner (git-ignoriert). Fehlt beides,
läuft die Pipeline ohne fusion-harness (eingebauter Filter) und ohne zusätzlich verbotene Ordner.

    fusion_harness = "C:/Werkzeuge/fusion-harness/fusion_harness.py"   # optional: Befund-Filter von außen
    verbotene_wurzeln = ["C:/Daten/anderes-projekt"]                    # optional: dort schreibt die Pipeline nie

ENTWICKLUNG_FUSION_HARNESS (leer = ausdrücklich aus), ENTWICKLUNG_VERBOTENE_WURZELN (getrennt mit os.pathsep).
Gelesen wird bei jedem Aufruf neu (lazy), damit Tests per monkeypatch umlenken können.
"""
import os
import tomllib
from pathlib import Path

from entwicklung import pfade

DATEI = "lokal.toml"


def _datei() -> dict:
    pfad = pfade.projekt_dir() / DATEI
    if not pfad.is_file():
        return {}
    try:
        return tomllib.loads(pfad.read_text(encoding="utf-8-sig"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"{pfad} ist kein gültiges TOML: {e}") from None


def einstellungen() -> dict:
    datei = _datei()
    fh = os.environ.get("ENTWICKLUNG_FUSION_HARNESS")
    if fh is None:
        fh = datei.get("fusion_harness")
    wurzeln = os.environ.get("ENTWICKLUNG_VERBOTENE_WURZELN")
    liste = [w for w in wurzeln.split(os.pathsep) if w.strip()] if wurzeln is not None \
        else list(datei.get("verbotene_wurzeln") or [])
    return {"fusion_harness": Path(fh) if isinstance(fh, str) and fh.strip() else None,
            "verbotene_wurzeln": [Path(w) for w in liste]}
