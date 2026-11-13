"""Test-Isolation: Kein Test darf den echten Speicher des Projekts anfassen.

Jeder Test bekommt eigene Ordner für Daten, Berichte und Worktrees (tmp_path). Danach wird geprüft,
dass die echte checkpoints.db (samt -wal/-shm), der Berichtsordner und der Arbeitsordner unverändert sind.
"""
from pathlib import Path

import pytest

PROJEKT = Path(__file__).resolve().parents[1]
ECHTE_DB = PROJEKT / "data" / "checkpoints.db"
ECHTE_BERICHTE = PROJEKT / "berichte"
ECHTE_ARBEIT = PROJEKT / "arbeit"


def _stand(pfad: Path):
    return pfad.stat().st_mtime_ns if pfad.exists() else None


def _stand_db(db: Path):
    """mtime von DB, -wal und -shm: SQLite im WAL-Modus schreibt oft nur in die -wal-Datei."""
    return tuple(_stand(db.with_name(db.name + endung)) for endung in ("", "-wal", "-shm"))


def _ordnerstand(ordner: Path):
    """None, wenn der Ordner fehlt: So fällt auch ein neu angelegter leerer Ordner auf."""
    return {p.name: p.stat().st_mtime_ns for p in ordner.iterdir()} if ordner.exists() else None


@pytest.fixture(autouse=True)
def isolierte_ordner(tmp_path, monkeypatch):
    monkeypatch.setenv("ENTWICKLUNG_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ENTWICKLUNG_BERICHTE_DIR", str(tmp_path / "berichte"))
    monkeypatch.setenv("ENTWICKLUNG_ARBEIT_DIR", str(tmp_path / "arbeit"))
    from entwicklung import agenten, pfade

    # Kein Test darf das echte claude als Implementierer starten (Kosten, Schreibzugriffe, Nicht-Determinismus).
    monkeypatch.setattr(agenten, "_TESTSPERRE", True)

    # Hard-Guard: bricht ab, falls die Umleitung nicht greift.
    if pfade.checkpoint_db_pfad().resolve() == ECHTE_DB.resolve():
        raise RuntimeError("Test würde die echte checkpoints.db benutzen")
    if pfade.berichte_dir().resolve() == ECHTE_BERICHTE.resolve():
        raise RuntimeError("Test würde in den echten Berichtsordner schreiben")
    if pfade.arbeit_dir().resolve() == ECHTE_ARBEIT.resolve():
        raise RuntimeError("Test würde Worktrees im echten Arbeitsordner anlegen")
    vorher = (_stand_db(ECHTE_DB), _ordnerstand(ECHTE_BERICHTE), _ordnerstand(ECHTE_ARBEIT))
    yield
    nachher = (_stand_db(ECHTE_DB), _ordnerstand(ECHTE_BERICHTE), _ordnerstand(ECHTE_ARBEIT))
    assert nachher[0] == vorher[0], "Test hat die echte checkpoints.db angefasst"
    assert nachher[1] == vorher[1], "Test hat in den echten Berichtsordner geschrieben"
    assert nachher[2] == vorher[2], "Test hat im echten Arbeitsordner geschrieben"
