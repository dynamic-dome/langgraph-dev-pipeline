from pathlib import Path

import pytest

from entwicklung import pfade


def test_projekt_dir():
    assert pfade.projekt_dir() == Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("funktion,env", [
    (pfade.data_dir, "ENTWICKLUNG_DATA_DIR"),
    (pfade.berichte_dir, "ENTWICKLUNG_BERICHTE_DIR"),
    (pfade.arbeit_dir, "ENTWICKLUNG_ARBEIT_DIR"),
])
def test_umleitung_per_umgebung(funktion, env, tmp_path, monkeypatch):
    ziel = tmp_path / "x"
    monkeypatch.setenv(env, str(ziel))
    assert funktion() == ziel
    assert ziel.is_dir()


@pytest.mark.parametrize("unter", ["daten/x", "wiki/lab2", "daten"])
def test_fremde_speicher_verboten(unter, tmp_path, monkeypatch):
    """Verbotene Wurzeln kommen aus lokal.toml oder ENTWICKLUNG_VERBOTENE_WURZELN; sie gelten auch im Temp-Ordner."""
    monkeypatch.setenv("ENTWICKLUNG_VERBOTENE_WURZELN", f"{tmp_path / 'daten'};{tmp_path / 'wiki'}")
    monkeypatch.setenv("ENTWICKLUNG_ARBEIT_DIR", str(tmp_path / unter))
    with pytest.raises(pfade.GefaehrlicherPfad):
        pfade.arbeit_dir()


def test_nur_projekt_oder_temp(monkeypatch):
    monkeypatch.setenv("ENTWICKLUNG_DATA_DIR", str(pfade.projekt_dir().parent / "fremdes-projekt" / "lab2"))
    with pytest.raises(pfade.GefaehrlicherPfad):
        pfade.data_dir()


def test_punktpunkt_wird_aufgeloest(monkeypatch):
    monkeypatch.setenv("ENTWICKLUNG_BERICHTE_DIR", str(pfade.projekt_dir() / ".." / "systemkarte"))
    with pytest.raises(pfade.GefaehrlicherPfad):
        pfade.berichte_dir()


def test_checkpoint_db_liegt_in_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ENTWICKLUNG_DATA_DIR", str(tmp_path / "d"))
    assert pfade.checkpoint_db_pfad() == tmp_path / "d" / "checkpoints.db"


def test_standard_im_projekt(tmp_path, monkeypatch):
    # projekt_dir umbiegen: Der Test darf den echten Ordner arbeit/ nicht anlegen (Codex S1, Befund 5).
    monkeypatch.setattr(pfade, "projekt_dir", lambda: tmp_path / "projekt")
    monkeypatch.delenv("ENTWICKLUNG_ARBEIT_DIR")
    assert pfade.arbeit_dir() == tmp_path / "projekt" / "arbeit"


@pytest.mark.parametrize("unterordner", ["portwart", "docs", "aufgaben", "", "arbeitx"])
def test_im_projekt_nur_data_berichte_arbeit(unterordner, monkeypatch):
    monkeypatch.setenv("ENTWICKLUNG_BERICHTE_DIR", str(pfade.projekt_dir() / unterordner))
    with pytest.raises(pfade.GefaehrlicherPfad):
        pfade.berichte_dir()


def test_unterordner_von_arbeit_erlaubt():
    ziel = pfade.projekt_dir() / "arbeit" / "portwart-x"
    assert pfade.pruefe_schreibziel(ziel) == ziel.resolve()


def test_pruefe_schreibziel(tmp_path):
    assert pfade.pruefe_schreibziel(tmp_path / "a.md") == (tmp_path / "a.md").resolve()
    with pytest.raises(pfade.GefaehrlicherPfad):
        pfade.pruefe_schreibziel(pfade.projekt_dir().parent / "portliste.md")
