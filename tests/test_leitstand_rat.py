import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from entwicklung import cli, pfade, speicher
from entwicklung.leitstand.server import baue_app
from tests.test_graph_s1 import _abh, umgebung  # noqa: F401  (Fixture)
from tests.test_graph_s2 import _codex, _pruefer
from tests.test_graph_s3 import RICHTIG, Implementierer
from tests.test_graph_s4 import KLAR, Planer, s4  # noqa: F401  (s4 Fixture)
from tests.test_leitstand_server import BASIS, PORT, TOKEN

RAT_FREIGEBEN = {"entscheidung": "freigeben", "text": "", "begruendung": "Nur kleine Punkte.", "sicherheit": "hoch",
                 "punkte": [{"aussage": "x", "warum": "y", "einschaetzung": "klein"}]}


class Fable:
    """Fake-Fable: liefert einen festen Rat; optional wartet er auf ein Signal (zum Testen von „veraltet“)."""

    def __init__(self, rat=RAT_FREIGEBEN, warten=None):
        self.rat, self.warten, self.aufrufe, self.angekommen = rat, warten, [], threading.Event()

    def __call__(self, name, prompt, cwd, schema, modell="sonnet", timeout=600, effort=None, runner=None):
        self.aufrufe.append(modell)
        self.angekommen.set()
        if self.warten:
            self.warten.wait(60)
        return {"name": name, "ok": True, "daten": self.rat, "fehler": None, "dauer_s": 0.1}


class Astra:
    """Fake-Astra (Codex-Signatur): fester Rat, optional Fehler oder Warten auf ein Signal."""

    def __init__(self, rat=None, fehler=None, warten=None):
        self.rat, self.fehler, self.warten = rat or RAT_AENDERN, fehler, warten
        self.aufrufe, self.prompts, self.angekommen = [], [], threading.Event()

    def __call__(self, name, prompt, cwd, schema, timeout=900, effort=None, runner=None):
        self.aufrufe.append(name)
        self.prompts.append(prompt)
        self.angekommen.set()
        if self.warten:
            self.warten.wait(60)
        if self.fehler:
            raise RuntimeError(self.fehler)
        return {"name": name, "ok": True, "daten": self.rat, "fehler": None, "dauer_s": 0.1}


RAT_AENDERN = {"entscheidung": "aendern", "text": "Idempotenz-Satz streichen.",
               "begruendung": "Die Spec widerspricht sich. Mehr dazu unten.", "sicherheit": "hoch", "punkte": []}


def _aufbau(s4, fable, astra=None):
    repo, aufgaben = s4
    planer = Planer(klaeren=[KLAR])
    abh = _abh(aufgaben, implementierer=Implementierer(RICHTIG), pruefer=_pruefer(), codex=_codex(),
               planer=planer, planer_codex=planer.codex, berater=fable, berater_astra=astra or Astra())
    app = baue_app(abh, speicher.oeffne_checkpointer(), TOKEN, PORT, repos_dir=repo.parent)
    client = TestClient(app, base_url=BASIS, headers={"X-Leitstand-Token": TOKEN})
    r = client.post("/api/laeufe", json={"repo": "mini", "aufgabe": "M2"})
    tid = r.json()["thread_id"]
    app.state.ausfuehrer.warte(tid, 120)
    return client, app, tid, abh


def _rat_fertig(client, app, tid):
    app.state.ausfuehrer.warte_rat(tid, 120)
    return client.get(f"/api/laeufe/{tid}/rat").json()


def test_rat_bis_fertig_und_uebernehmen(s4):
    fable = Fable()
    client, app, tid, _ = _aufbau(s4, fable)
    assert client.post(f"/api/laeufe/{tid}/rat").status_code == 202
    rat = _rat_fertig(client, app, tid)["fable"]
    assert rat["zustand"] == "fertig" and rat["haltepunkt"] == "spec_freigabe" and not rat["veraltet"]
    assert rat["antwort"] == {"entscheidung": "freigeben"} and rat["rat"]["sicherheit"] == "hoch"
    assert fable.aufrufe == ["fable"]
    r = client.post(f"/api/laeufe/{tid}/antwort", json={**rat["antwort"], "haltepunkt": rat["haltepunkt"],
                                                        "checkpoint_id": rat["checkpoint_id"]})
    assert r.status_code == 202
    app.state.ausfuehrer.warte(tid, 120)
    assert client.get(f"/api/laeufe/{tid}").json()["wartepunkt"] == "plan_freigabe"
    assert client.get(f"/api/laeufe/{tid}/rat").json()["fable"]["veraltet"] is True


def test_rat_veraltet_nach_eigener_antwort(s4):
    los = threading.Event()
    fable = Fable(warten=los)
    client, app, tid, _ = _aufbau(s4, fable)
    client.post(f"/api/laeufe/{tid}/rat")
    assert fable.angekommen.wait(60)
    lauf = client.get(f"/api/laeufe/{tid}").json()
    client.post(f"/api/laeufe/{tid}/antwort", json={"entscheidung": "freigeben", "haltepunkt": lauf["wartepunkt"],
                                                    "checkpoint_id": lauf["checkpoint_id"]})
    app.state.ausfuehrer.warte(tid, 120)
    los.set()
    rat = _rat_fertig(client, app, tid)["fable"]
    assert rat["veraltet"] is True
    r = client.post(f"/api/laeufe/{tid}/antwort", json={**rat["antwort"], "haltepunkt": rat["haltepunkt"],
                                                        "checkpoint_id": rat["checkpoint_id"]})
    assert r.status_code == 409


def test_doppelter_rat_409(s4):
    los = threading.Event()
    fable = Fable(warten=los)
    client, app, tid, _ = _aufbau(s4, fable)
    assert client.post(f"/api/laeufe/{tid}/rat").status_code == 202
    assert fable.angekommen.wait(60)
    assert client.get(f"/api/laeufe/{tid}/rat").json()["fable"]["zustand"] == "laeuft"
    assert client.post(f"/api/laeufe/{tid}/rat").status_code == 409
    los.set()
    _rat_fertig(client, app, tid)


def test_rat_ohne_haltepunkt_409(s4):
    client, app, tid, _ = _aufbau(s4, Fable())
    lauf = client.get(f"/api/laeufe/{tid}").json()
    client.post(f"/api/laeufe/{tid}/antwort", json={"entscheidung": "abbrechen", "haltepunkt": lauf["wartepunkt"],
                                                    "checkpoint_id": lauf["checkpoint_id"]})
    app.state.ausfuehrer.warte(tid, 120)
    assert client.post(f"/api/laeufe/{tid}/rat").status_code == 409
    assert client.get(f"/api/laeufe/{tid}/rat").status_code == 204


def test_rat_ohne_token_403(s4):
    client, app, tid, _ = _aufbau(s4, Fable())
    ohne = TestClient(app, base_url=BASIS)
    assert ohne.post(f"/api/laeufe/{tid}/rat").status_code == 403
    assert ohne.get(f"/api/laeufe/{tid}/rat").status_code == 403


def test_rat_nicht_verwertbar(s4):
    client, app, tid, _ = _aufbau(s4, Fable(rat={**RAT_FREIGEBEN, "entscheidung": "weiter"}))
    client.post(f"/api/laeufe/{tid}/rat")
    rat = _rat_fertig(client, app, tid)["fable"]
    assert rat["zustand"] == "fertig" and rat["antwort"] is None and "nicht erlaubt" in rat["grund"]


def test_rat_wird_abgelegt_und_im_bericht(s4):
    client, app, tid, _ = _aufbau(s4, Fable())
    client.post(f"/api/laeufe/{tid}/rat")
    rat = _rat_fertig(client, app, tid)["fable"]
    datei = Path(rat["datei"])
    assert datei.is_relative_to(pfade.berichte_dir()) and datei.name == "rat-spec_freigabe-fable-1.json"
    assert json.loads(datei.read_text(encoding="utf-8"))["rat"]["entscheidung"] == "freigeben"
    lauf = client.get(f"/api/laeufe/{tid}").json()
    client.post(f"/api/laeufe/{tid}/antwort", json={"entscheidung": "abbrechen", "haltepunkt": lauf["wartepunkt"],
                                                    "checkpoint_id": lauf["checkpoint_id"]})
    app.state.ausfuehrer.warte(tid, 120)
    bericht = Path(client.get(f"/api/laeufe/{tid}").json()["bericht_pfad"]).read_text(encoding="utf-8")
    assert "## Berater (Fable, Astra)" in bericht and "spec_freigabe · fable: freigeben (hoch)" in bericht


def test_cli_rat(s4, capsys):
    repo, aufgaben = s4
    fable = Fable(rat={**RAT_FREIGEBEN, "entscheidung": "aendern", "text": "Bitte genauer."})
    planer = Planer(klaeren=[KLAR])
    abh = _abh(aufgaben, implementierer=Implementierer(RICHTIG), pruefer=_pruefer(), codex=_codex(),
               planer=planer, planer_codex=planer.codex, berater=fable)
    assert cli.main(["lauf", "--repo", str(repo), "--aufgabe", "M2"], abh=abh) == 3
    capsys.readouterr()
    assert cli.main(["rat"], abh=abh) == 0
    aus = capsys.readouterr().out
    assert "Fable empfiehlt: aendern" in aus and "Nur kleine Punkte." in aus and "[klein] x" in aus
    assert "fortsetzen --entscheidung aendern --hinweis 'Bitte genauer.'" in aus
    assert fable.aufrufe == ["fable"]



def test_rat_bindet_sich_nicht_an_spaeteren_stand(s4):
    """Codex F-003: Hat sich der Stand zwischen Anfordern und Thread-Start geändert, fragt der Thread Fable nicht
    für den neuen Haltepunkt, sondern meldet den Rat als nicht mehr passend."""
    from entwicklung.leitstand.ausfuehrer import rat_fuer_lauf
    fable = Fable()
    client, app, tid, abh = _aufbau(s4, fable)
    graph = app.state.ausfuehrer.graph_fuer(4)
    erg = rat_fuer_lauf(abh, graph, tid, erwartet=("spec_freigabe", "gibt-es-nicht"))
    assert fable.aufrufe == [] and "geändert" in erg["fehler"] and erg["antwort"] is None


def test_nachkontrolle_sieht_akzeptanzordner(s4):
    """Codex F-005: Ein Schreibzugriff unter tests/_akzeptanz/ ist auch bei lesenden Agenten eine Verletzung."""
    from entwicklung.graph_s4 import planung_sauber
    client, app, tid, abh = _aufbau(s4, Fable())
    werte = app.state.ausfuehrer.graph_fuer(4).get_state({"configurable": {"thread_id": tid}}).values
    ziel = Path(werte["worktree"]) / "tests" / "_akzeptanz" / "notiz.py"
    ziel.parent.mkdir(parents=True)
    ziel.write_text("x = 1\n", encoding="utf-8")
    assert any("_akzeptanz" in v for v in planung_sauber(abh, werte))


def test_cli_rat_befehl_gebunden_und_shell_sicher(s4, capsys):
    """Codex F-001/F-002: Der angebotene Befehl nennt Haltepunkt und Stand und setzt Fables Text sicher in
    einfache Anführungszeichen (PowerShell: $() und " wirken dort nicht)."""
    repo, aufgaben = s4
    boese = "Bitte $(Set-Content x.txt y) und \"Zitat\" und 'einfach'."
    fable = Fable(rat={**RAT_FREIGEBEN, "entscheidung": "aendern", "text": boese})
    planer = Planer(klaeren=[KLAR])
    abh = _abh(aufgaben, implementierer=Implementierer(RICHTIG), pruefer=_pruefer(), codex=_codex(),
               planer=planer, planer_codex=planer.codex, berater=fable)
    cli.main(["lauf", "--repo", str(repo), "--aufgabe", "M2"], abh=abh)
    capsys.readouterr()
    assert cli.main(["rat"], abh=abh) == 0
    aus = capsys.readouterr().out
    assert "--hinweis 'Bitte $(Set-Content x.txt y) und \"Zitat\" und ''einfach''.'" in aus
    assert "--haltepunkt spec_freigabe --stand " in aus


def test_fortsetzen_mit_falschem_haltepunkt_oder_stand(s4, capsys):
    """Codex F-001: Ein alter Befehl darf nicht den nächsten Haltepunkt treffen."""
    repo, aufgaben = s4
    planer = Planer(klaeren=[KLAR])
    abh = _abh(aufgaben, implementierer=Implementierer(RICHTIG), pruefer=_pruefer(), codex=_codex(),
               planer=planer, planer_codex=planer.codex, berater=Fable())
    cli.main(["lauf", "--repo", str(repo), "--aufgabe", "M2"], abh=abh)
    capsys.readouterr()
    assert cli.main(["fortsetzen", "--entscheidung", "freigeben", "--haltepunkt", "plan_freigabe"], abh=abh) == 3
    assert "geändert" in capsys.readouterr().out
    assert cli.main(["fortsetzen", "--entscheidung", "freigeben", "--stand", "falsch"], abh=abh) == 3
    assert cli.main(["fortsetzen", "--entscheidung", "freigeben", "--haltepunkt", "spec_freigabe"], abh=abh) == 3
    assert "Freigabe des Plans" in capsys.readouterr().out



# ---------------------------------------------------------------------------------------------- 6b-1: Astra, Einwände
def test_beide_fragen_parallel_und_vergleich(s4):
    astra = Astra()
    client, app, tid, _ = _aufbau(s4, Fable(), astra)
    r = client.post(f"/api/laeufe/{tid}/rat?wer=beide")
    assert r.status_code == 202 and sorted(r.json()["gestartet"]) == ["astra", "fable"]
    raete = _rat_fertig(client, app, tid)
    assert raete["fable"]["rat"]["entscheidung"] == "freigeben" and raete["astra"]["wer"] == "astra"
    assert raete["vergleich"]["einig"] is False and raete["vergleich"]["vorbelegt"] == "astra"
    assert astra.aufrufe == ["berater_astra"] and "## Quelldateien (Worktree)" in astra.prompts[0]
    namen = sorted(p.name for p in Path(raete["astra"]["datei"]).parent.glob("rat-*.json"))
    assert namen == ["rat-spec_freigabe-astra-1.json", "rat-spec_freigabe-fable-1.json"]
    assert "Fable empfiehlt freigeben, Astra aendern" in client.get(f"/api/laeufe/{tid}").json()["einwaende"]


def test_unbekannter_berater_400(s4):
    client, app, tid, _ = _aufbau(s4, Fable())
    assert client.post(f"/api/laeufe/{tid}/rat?wer=gpt").status_code == 400


def test_ein_berater_scheitert(s4):
    client, app, tid, _ = _aufbau(s4, Fable(), Astra(fehler="Codex Timeout"))
    client.post(f"/api/laeufe/{tid}/rat?wer=beide")
    raete = _rat_fertig(client, app, tid)
    assert raete["fable"]["ok"] and "Codex Timeout" in raete["astra"]["fehler"] and raete["vergleich"] is None
    assert client.get(f"/api/laeufe/{tid}").json()["einwaende"] == []


def test_server_antwort_einwand_ohne_begruendung_400(s4):
    client, app, tid, _ = _aufbau(s4, Fable(), Astra())
    client.post(f"/api/laeufe/{tid}/rat?wer=astra")
    _rat_fertig(client, app, tid)
    lauf = client.get(f"/api/laeufe/{tid}").json()
    assert lauf["einwaende"] and "Astra (GPT) rät zu aendern" in lauf["einwaende"][0]
    basis = {"entscheidung": "freigeben", "haltepunkt": lauf["wartepunkt"], "checkpoint_id": lauf["checkpoint_id"]}
    r = client.post(f"/api/laeufe/{tid}/antwort", json={**basis, "einwaende": [], "begruendung": "  "})
    assert r.status_code == 400 and r.json()["einwaende"] == lauf["einwaende"]
    r = client.post(f"/api/laeufe/{tid}/antwort", json={**basis, "begruendung": "Satz ist so gemeint",
                                                        "einwaende": ["gefälscht"]})
    assert r.status_code == 202
    app.state.ausfuehrer.warte(tid, 120)
    werte = app.state.ausfuehrer.graph_fuer(4).get_state({"configurable": {"thread_id": tid}}).values
    assert werte["einwand_freigaben"] == [{"haltepunkt": "spec_freigabe", "entscheidung": "freigeben",
                                           "einwaende": lauf["einwaende"], "begruendung": "Satz ist so gemeint"}]


def test_alter_rat_erzeugt_keinen_einwand(s4):
    client, app, tid, _ = _aufbau(s4, Fable(), Astra())
    client.post(f"/api/laeufe/{tid}/rat?wer=astra")
    _rat_fertig(client, app, tid)
    lauf = client.get(f"/api/laeufe/{tid}").json()
    r = client.post(f"/api/laeufe/{tid}/antwort", json={"entscheidung": "aendern", "hinweis": "Satz streichen",
                                                        "haltepunkt": lauf["wartepunkt"],
                                                        "checkpoint_id": lauf["checkpoint_id"]})
    assert r.status_code == 202
    app.state.ausfuehrer.warte(tid, 120)
    neu = client.get(f"/api/laeufe/{tid}").json()
    assert neu["wartepunkt"] == "spec_freigabe" and neu["checkpoint_id"] != lauf["checkpoint_id"]
    assert neu["einwaende"] == []
    r = client.post(f"/api/laeufe/{tid}/antwort", json={"entscheidung": "freigeben", "haltepunkt": "spec_freigabe",
                                                        "checkpoint_id": neu["checkpoint_id"]})
    assert r.status_code == 202


def test_rat_doppelklick_je_berater(s4):
    los = threading.Event()
    astra = Astra(warten=los)
    client, app, tid, _ = _aufbau(s4, Fable(), astra)
    assert client.post(f"/api/laeufe/{tid}/rat?wer=astra").status_code == 202
    assert astra.angekommen.wait(60)
    r = client.post(f"/api/laeufe/{tid}/rat?wer=beide")
    assert r.status_code == 202 and r.json() == {"thread_id": tid, "gestartet": ["fable"], "belegt": ["astra"]}
    assert client.post(f"/api/laeufe/{tid}/rat?wer=astra").status_code == 409
    los.set()
    _rat_fertig(client, app, tid)


def test_alte_ratdatei_ohne_wer_gilt_als_fable(tmp_path):
    from entwicklung.berater import raete_fuer_stand
    (tmp_path / "rat-spec_freigabe-1.json").write_text(json.dumps(
        {"haltepunkt": "spec_freigabe", "checkpoint_id": "c1", "ok": True}), encoding="utf-8")
    (tmp_path / "rat-spec_freigabe-astra-1.json").write_text(json.dumps(
        {"wer": "astra", "haltepunkt": "spec_freigabe", "checkpoint_id": "alt", "ok": True}), encoding="utf-8")
    (tmp_path / "rat-kaputt.json").write_text("{", encoding="utf-8")
    assert list(raete_fuer_stand(tmp_path, "spec_freigabe", "c1")) == ["fable"]
    assert raete_fuer_stand(tmp_path / "fehlt", "spec_freigabe", "c1") == {}


def _abh_rat(s4, fable, astra):
    repo, aufgaben = s4
    planer = Planer(klaeren=[KLAR])
    abh = _abh(aufgaben, implementierer=Implementierer(RICHTIG), pruefer=_pruefer(), codex=_codex(),
               planer=planer, planer_codex=planer.codex, berater=fable, berater_astra=astra)
    assert cli.main(["lauf", "--repo", str(repo), "--aufgabe", "M2"], abh=abh) == 3
    return abh


def test_cli_rat_beide(s4, capsys):
    abh = _abh_rat(s4, Fable(), Astra())
    capsys.readouterr()
    assert cli.main(["rat", "--wer", "beide"], abh=abh) == 0
    aus = capsys.readouterr().out
    assert "Fable empfiehlt: freigeben" in aus and "Astra empfiehlt: aendern" in aus and "uneinig" in aus
    assert "--entscheidung aendern --hinweis 'Idempotenz-Satz streichen.'" in aus


def test_cli_fortsetzen_einwand_aus_rat(s4, capsys):
    abh = _abh_rat(s4, Fable(), Astra())
    assert cli.main(["rat", "--wer", "astra"], abh=abh) == 0
    capsys.readouterr()
    assert cli.main(["fortsetzen", "--entscheidung", "freigeben"], abh=abh) == 3
    aus = capsys.readouterr().out
    assert "Astra (GPT) rät zu aendern" in aus and "begruendung" in aus
    assert cli.main(["fortsetzen", "--entscheidung", "freigeben", "--begruendung", "geprüft"], abh=abh) == 3
    assert "Freigabe des Plans" in capsys.readouterr().out


def test_kein_rat_am_kostenrahmen(s4):
    """6b-2: Am Kostenrahmen entscheidet nur Dominic; ein Rat würde selbst Aufrufe kosten und kennt „mehr“ nicht."""
    repo, aufgaben = s4
    fable = Fable()
    planer = Planer(klaeren=[KLAR])
    abh = _abh(aufgaben, implementierer=Implementierer(RICHTIG), pruefer=_pruefer(), codex=_codex(),
               planer=planer, planer_codex=planer.codex, berater=fable, berater_astra=Astra())
    app = baue_app(abh, speicher.oeffne_checkpointer(), TOKEN, PORT, repos_dir=repo.parent)
    client = TestClient(app, base_url=BASIS, headers={"X-Leitstand-Token": TOKEN})
    tid = client.post("/api/laeufe", json={"repo": "mini", "aufgabe": "M2", "budget": 1}).json()["thread_id"]
    app.state.ausfuehrer.warte(tid, 120)
    assert client.get(f"/api/laeufe/{tid}").json()["wartepunkt"] == "budget_spec"
    r = client.post(f"/api/laeufe/{tid}/rat", params={"wer": "beide"})
    assert r.status_code == 409 and "Kostenrahmen" in r.json()["fehler"]
    assert fable.aufrufe == []


def test_cli_kein_rat_am_kostenrahmen(s4, capsys):
    repo, aufgaben = s4
    fable = Fable()
    planer = Planer(klaeren=[KLAR])
    abh = _abh(aufgaben, implementierer=Implementierer(RICHTIG), pruefer=_pruefer(), codex=_codex(),
               planer=planer, planer_codex=planer.codex, berater=fable)
    assert cli.main(["lauf", "--repo", str(repo), "--aufgabe", "M2", "--budget", "1"], abh=abh) == 3
    capsys.readouterr()
    assert cli.main(["rat"], abh=abh) == 1
    assert "Kostenrahmen" in capsys.readouterr().out and fable.aufrufe == []
