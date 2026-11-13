"""Stufe 7, Task 3: Abschluss-Freigabe in CLI, Leitstand und Bericht."""
import json
import shutil
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from entwicklung import cli, pfade, speicher
from entwicklung.leitstand.server import baue_app
from tests.test_cli_s4 import _abh4, _fort, _lauf, _wartepunkt
from tests.test_graph_s1 import umgebung  # noqa: F401  (Fixture)
from tests.test_graph_s3 import RICHTIG, Implementierer
from tests.test_graph_s4 import Planer, s4  # noqa: F401  (s4 ist eine Fixture)
from tests.test_graph_s7 import GESAMT_MAJOR, MIT_RMTREE
from tests.test_leitstand_rat import Astra, Fable
from tests.test_leitstand_server import BASIS, PORT, TOKEN


def _kopf(repo):
    return subprocess.run([shutil.which("git"), "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True,
                          check=True).stdout.strip()


def _bis_abschluss_cli(s4, capsys, planer=None, impl=None):
    repo, aufgaben = s4
    abh = _abh4(aufgaben, planer, impl)
    assert _lauf(repo, abh) == 3
    assert _fort(abh, "--entscheidung", "freigeben") == 3
    assert _fort(abh, "--entscheidung", "freigeben") == 3
    assert _wartepunkt(abh) == "abschluss_freigabe"
    return abh, repo, aufgaben, capsys.readouterr().out


def test_cli_bis_zum_merge(s4, capsys):
    abh, repo, aufgaben, aus = _bis_abschluss_cli(s4, capsys)
    assert "Abschluss-Freigabe" in aus and "Tür: zweiseitig · Radius: Repo" in aus  # mathe.py + tests/
    assert "Tests: 4 bestanden · 0 übersprungen" in aus and "Gesamtreview (Codex): PASS" in aus
    assert "--entscheidung mergen" in aus and "--entscheidung nicht_mergen" in aus
    vorher = _kopf(repo)
    assert _fort(abh, "--entscheidung", "mergen") == 0
    aus = capsys.readouterr().out
    assert "🟢 gruen" in aus and "Gemergt:" in aus and _kopf(repo) != vorher
    assert (aufgaben / "mini" / "M2" / "test_akzeptanz_m2.py").is_file()


def test_cli_mergen_trotz_einwand_braucht_begruendung(s4, capsys):
    abh, repo, _, aus = _bis_abschluss_cli(s4, capsys, Planer(gesamtreview=[GESAMT_MAJOR]))
    assert "Gesamtreview (Codex) meldet major: Vertrag für negative Zahlen fehlt" in aus
    assert _fort(abh, "--entscheidung", "mergen") == 3
    assert "begruendung" in capsys.readouterr().out
    assert _fort(abh, "--entscheidung", "mergen", "--begruendung", "Folgeaufgabe") == 0


def test_cli_nicht_mergen(s4, capsys):
    abh, repo, aufgaben, _ = _bis_abschluss_cli(s4, capsys)
    vorher = _kopf(repo)
    assert _fort(abh, "--entscheidung", "nicht_mergen") == 0
    assert "Nicht gemergt" in capsys.readouterr().out and _kopf(repo) == vorher


def test_cli_einseitig_zeigt_faelle(s4, capsys):
    _, _, _, aus = _bis_abschluss_cli(s4, capsys, impl=Implementierer(MIT_RMTREE))
    assert "Tür: einseitig" in aus and "Löschen von Daten oder Dateien" in aus


def test_bericht_abschnitt_abschluss(s4, capsys):
    abh, repo, _, _ = _bis_abschluss_cli(s4, capsys)
    _fort(abh, "--entscheidung", "mergen")
    md = next(pfade.berichte_dir().glob("*.md")).read_text(encoding="utf-8")
    teil = md.split("## Abschluss")[1]
    assert "Tür: zweiseitig · Radius: Repo" in teil and "Entscheidung: mergen" in teil
    assert "Gemergt:" in teil and "Gesamtreview (Codex): PASS" in teil and "Aufgeräumt: ja" in teil
    daten = json.loads(next(pfade.berichte_dir().glob("*.json")).read_text(encoding="utf-8"))
    for feld in ("gesamtreview", "abschluss", "zielzweig", "tuer"):
        assert daten[feld] is not None, feld


def test_bericht_merge_abgelehnt_symbol():
    from entwicklung.bericht import SYMBOL
    assert "merge_abgelehnt" in SYMBOL


def test_kein_rat_am_abschluss_cli(s4, capsys):
    repo, aufgaben = s4
    fable = Fable()
    planer = Planer()
    abh = _abh4(aufgaben, planer)
    abh.berater = fable
    _lauf(repo, abh)
    _fort(abh, "--entscheidung", "freigeben")
    _fort(abh, "--entscheidung", "freigeben")
    capsys.readouterr()
    assert cli.main(["rat"], abh=abh) == 1
    assert "Abschluss" in capsys.readouterr().out and fable.aufrufe == []


def _leitstand(s4, planer=None):
    repo, aufgaben = s4
    planer = planer or Planer()
    abh = _abh4(aufgaben, planer)
    abh.berater, abh.berater_astra = Fable(), Astra()
    app = baue_app(abh, speicher.oeffne_checkpointer(), TOKEN, PORT, repos_dir=repo.parent)
    client = TestClient(app, base_url=BASIS, headers={"X-Leitstand-Token": TOKEN})
    tid = client.post("/api/laeufe", json={"repo": "mini", "aufgabe": "M2"}).json()["thread_id"]
    app.state.ausfuehrer.warte(tid, 120)
    for _ in range(2):  # Spec und Plan freigeben
        lauf = client.get(f"/api/laeufe/{tid}").json()
        r = client.post(f"/api/laeufe/{tid}/antwort", json={"entscheidung": "freigeben", "haltepunkt": lauf["wartepunkt"],
                                                            "checkpoint_id": lauf["checkpoint_id"]})
        assert r.status_code == 202, r.json()
        app.state.ausfuehrer.warte(tid, 120)
    lauf = client.get(f"/api/laeufe/{tid}").json()
    assert lauf["wartepunkt"] == "abschluss_freigabe"
    return client, app, tid, lauf, repo


def test_leitstand_kein_rat_am_abschluss(s4):
    client, _, tid, _, _ = _leitstand(s4)
    r = client.post(f"/api/laeufe/{tid}/rat", params={"wer": "beide"})
    assert r.status_code == 409 and "Abschluss" in r.json()["fehler"]


def test_leitstand_mergen_mit_einwand_ohne_begruendung_400(s4):
    client, app, tid, lauf, repo = _leitstand(s4, Planer(gesamtreview=[GESAMT_MAJOR]))
    assert lauf["frage"]["einwaende"] and lauf["einwaende"]
    basis = {"entscheidung": "mergen", "haltepunkt": "abschluss_freigabe", "checkpoint_id": lauf["checkpoint_id"]}
    vorher = _kopf(repo)
    r = client.post(f"/api/laeufe/{tid}/antwort", json=basis)
    assert r.status_code == 400 and _kopf(repo) == vorher
    r = client.post(f"/api/laeufe/{tid}/antwort", json={**basis, "begruendung": "Folgeaufgabe"})
    assert r.status_code == 202
    app.state.ausfuehrer.warte(tid, 120)
    assert _kopf(repo) != vorher


def test_leitstand_knotentexte_und_phase():
    from entwicklung.graph_s4 import baue_graph_s4
    from entwicklung.leitstand.daten import graph_daten
    knoten = {k["id"]: k for k in graph_daten(baue_graph_s4())["knoten"]}
    for name in ("budget_abschluss", "gesamtreview", "abschluss_freigabe", "abschluss"):
        assert knoten[name]["text"], name
        assert knoten[name]["phase"] == "abschluss", name
    assert knoten["abschluss_freigabe"]["haltepunkt"] and knoten["budget_abschluss"]["haltepunkt"]


def test_app_js_kennt_abschluss():
    js = (Path(pfade.projekt_dir()) / "entwicklung" / "leitstand" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'lauf.wartepunkt === "abschluss_freigabe"' in js and '"mergen"' in js and "tuer_zeile" in js
