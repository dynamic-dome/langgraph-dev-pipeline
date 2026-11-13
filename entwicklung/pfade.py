"""Pfade des Projekts. Alle Funktionen lesen die Umgebung bei jedem Aufruf neu (lazy).

Bewusst keine Pfad-Konstante auf Modulebene: Tests setzen ENTWICKLUNG_*_DIR auf tmp_path, und das muss
überall sofort greifen. Schutzschichten wie im Ökosystem-Puls (langgraph-lab):
1. Ziele unter verbotenen Wurzeln (lokal.toml oder ENTWICKLUNG_VERBOTENE_WURZELN) werden abgelehnt.
2. Ziele müssen in data/, berichte/ oder arbeit/ des Projekts oder im Temp-Ordner (Tests) liegen.
3. checkpoint_db_pfad() liegt immer direkt in data_dir().
"""
import os
import tempfile
from pathlib import Path

SCHREIBORDNER = ("data", "berichte", "arbeit")  # nur hier darf die Pipeline im Projekt schreiben


class GefaehrlicherPfad(RuntimeError):
    """Ein Schreibziel liegt in einem fremden Speicher."""


def projekt_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _pruefe_ziel(pfad: Path) -> Path:
    aufgeloest = pfad.resolve()
    from entwicklung import lokal  # hier, nicht oben: lokal braucht projekt_dir aus diesem Modul
    for wurzel in (w.resolve() for w in lokal.einstellungen()["verbotene_wurzeln"]):
        if aufgeloest == wurzel or wurzel in aufgeloest.parents:
            raise GefaehrlicherPfad(f"{aufgeloest} liegt unter {wurzel}")
    erlaubt = (*(projekt_dir() / o for o in SCHREIBORDNER), Path(tempfile.gettempdir()).resolve())
    if not any(aufgeloest == w or w in aufgeloest.parents for w in erlaubt):
        raise GefaehrlicherPfad(f"{aufgeloest} liegt weder in {'/'.join(SCHREIBORDNER)} des Projekts noch im Temp-Ordner")
    return aufgeloest


def _ordner(env_name: str, standard: str) -> Path:
    roh = os.environ.get(env_name)
    ziel = _pruefe_ziel(Path(roh) if roh else projekt_dir() / standard)
    ziel.mkdir(parents=True, exist_ok=True)
    return ziel


def data_dir() -> Path:
    return _ordner("ENTWICKLUNG_DATA_DIR", "data")


def berichte_dir() -> Path:
    return _ordner("ENTWICKLUNG_BERICHTE_DIR", "berichte")


def arbeit_dir() -> Path:
    """Hier entstehen die Worktrees, in denen der Implementierer arbeiten darf."""
    return _ordner("ENTWICKLUNG_ARBEIT_DIR", "arbeit")


def checkpoint_db_pfad() -> Path:
    ordner = data_dir()
    pfad = ordner / "checkpoints.db"
    if pfad.parent != ordner:
        raise GefaehrlicherPfad(f"{pfad} liegt nicht direkt in {ordner}")
    return pfad


def pruefe_schreibziel(pfad: Path) -> Path:
    """Öffentliche Fassung des Ziel-Guards: nur Projekt oder Temp, nie fremde Speicher."""
    return _pruefe_ziel(pfad)
