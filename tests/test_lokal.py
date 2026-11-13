"""Maschinenspezifisches aus lokal.toml oder Umgebungsvariablen (öffentliche Fassung ohne feste Pfade)."""
import json
from pathlib import Path

import pytest

from entwicklung import befunde, lokal, pfade, pruefer
from tests.test_befunde import _befund, _pruefer, repo  # noqa: F401  (repo ist eine Fixture)


@pytest.fixture
def ohne_lokal(tmp_path, monkeypatch):
    """Projekt ohne lokal.toml und ohne Umgebungsvariablen."""
    monkeypatch.setattr(pfade, "projekt_dir", lambda: tmp_path / "projekt")
    (tmp_path / "projekt").mkdir()
    for name in ("ENTWICKLUNG_FUSION_HARNESS", "ENTWICKLUNG_VERBOTENE_WURZELN"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path / "projekt"


def test_ohne_alles_keine_festen_pfade(ohne_lokal):
    assert lokal.einstellungen() == {"fusion_harness": None, "verbotene_wurzeln": []}


def test_lokal_toml_wird_gelesen(ohne_lokal, tmp_path):
    (ohne_lokal / "lokal.toml").write_text(
        f'fusion_harness = "{(tmp_path / "fh.py").as_posix()}"\nverbotene_wurzeln = ["{(tmp_path / "x").as_posix()}"]\n',
        encoding="utf-8")
    e = lokal.einstellungen()
    assert e["fusion_harness"] == tmp_path / "fh.py" and e["verbotene_wurzeln"] == [tmp_path / "x"]


def test_umgebung_schlaegt_datei(ohne_lokal, tmp_path, monkeypatch):
    (ohne_lokal / "lokal.toml").write_text('fusion_harness = "C:/gibt/es/nicht.py"\n', encoding="utf-8")
    monkeypatch.setenv("ENTWICKLUNG_FUSION_HARNESS", "")  # leer = ausdrücklich aus
    monkeypatch.setenv("ENTWICKLUNG_VERBOTENE_WURZELN", f"{tmp_path / 'a'};{tmp_path / 'b'}")
    e = lokal.einstellungen()
    assert e["fusion_harness"] is None and e["verbotene_wurzeln"] == [tmp_path / "a", tmp_path / "b"]


def test_kaputte_lokal_toml_ist_klarer_fehler(ohne_lokal):
    (ohne_lokal / "lokal.toml").write_text("kaputt =", encoding="utf-8")
    with pytest.raises(ValueError, match="lokal.toml"):
        lokal.einstellungen()


def test_verbotene_wurzeln_aus_einstellungen(ohne_lokal, tmp_path, monkeypatch):
    verboten = tmp_path / "fremder-speicher"
    monkeypatch.setenv("ENTWICKLUNG_VERBOTENE_WURZELN", str(verboten))
    monkeypatch.setenv("ENTWICKLUNG_ARBEIT_DIR", str(verboten / "lab2"))
    with pytest.raises(pfade.GefaehrlicherPfad, match="fremder-speicher"):
        pfade.arbeit_dir()


# ------------------------------------------------------------------------------------------ eingebauter Filter


@pytest.fixture
def eingebaut(monkeypatch):
    monkeypatch.setenv("ENTWICKLUNG_FUSION_HARNESS", "")


def test_eingebauter_filter_toepfe(repo, eingebaut):
    wt, rev = repo
    erg = befunde.sammle([_pruefer("security", _befund(id="F1", claim="echt"),
                                   _befund(id="F2", claim="erfunden", quote="os.system(eingabe)"),
                                   _befund(id="F3", claim="klein", severity="minor"),
                                   _befund(id="F4", claim="woanders", path="b.py", quote="X = 1"))], wt, rev, ["a.py"])
    topf = {b["claim"]: b["topf"] for b in erg["befunde"]}
    assert topf == {"echt": "candidates", "erfunden": "quote_missing", "klein": "side", "woanders": "out_of_scope"}
    assert erg["fix_noetig"] is True and erg["befund_filter"] == "eingebaut (fusion-harness nicht eingerichtet)"


def test_eingebauter_filter_einrueckung_egal(repo, eingebaut):
    wt, rev = repo
    erg = befunde.sammle([_pruefer("codex", _befund(quote="    return open('/daten/' +   name).read()"))],
                         wt, rev, ["a.py"])
    assert erg["befunde"][0]["topf"] == "candidates"


def test_eingebauter_filter_liest_den_commit_nicht_die_platte(repo, eingebaut):
    """Das Zitat muss im geprüften Commit stehen, nicht in einer später geänderten Datei."""
    wt, rev = repo
    (wt / "a.py").write_text("ganz anders\n", encoding="utf-8")
    erg = befunde.sammle([_pruefer("codex", _befund())], wt, rev, ["a.py"])
    assert erg["befunde"][0]["topf"] == "candidates"
    erg = befunde.sammle([_pruefer("codex", _befund(quote="ganz anders"))], wt, rev, ["a.py"])
    assert erg["befunde"][0]["topf"] == "quote_missing"


def test_eingebauter_filter_kaputter_bericht(repo, eingebaut):
    wt, rev = repo
    with pytest.raises(ValueError):
        befunde.filtere({"irgendwas": 1}, wt, rev, ["a.py"])


def test_fehlender_fusion_harness_faellt_zurueck(repo, monkeypatch, tmp_path):
    monkeypatch.setenv("ENTWICKLUNG_FUSION_HARNESS", str(tmp_path / "gibt-es-nicht.py"))
    wt, rev = repo
    erg = befunde.sammle([_pruefer("codex", _befund())], wt, rev, ["a.py"])
    assert erg["befunde"][0]["topf"] == "candidates"
    assert erg["befund_filter"].startswith("eingebaut") and "nicht gefunden" in erg["befund_filter"]


def test_review_schema_im_paket():
    schema = json.loads(pruefer.SCHEMA_PFAD.read_text(encoding="utf-8"))
    assert pruefer.SCHEMA_PFAD.is_relative_to(pfade.projekt_dir() / "entwicklung")
    assert set(schema["required"]) == {"verdict", "findings", "not_checkable"}


def test_review_schema_gleich_fusion_harness():
    """Drift-Wache: Ist fusion-harness eingerichtet, muss die Kopie im Paket gleich seinem Schema sein."""
    fh = lokal.einstellungen()["fusion_harness"]
    if not fh or not Path(fh).is_file():
        pytest.skip("fusion-harness nicht eingerichtet")
    original = Path(fh).parent / "prompts" / "REVIEW_SCHEMA.json"
    assert json.loads(pruefer.SCHEMA_PFAD.read_text(encoding="utf-8")) == json.loads(original.read_text(encoding="utf-8"))
