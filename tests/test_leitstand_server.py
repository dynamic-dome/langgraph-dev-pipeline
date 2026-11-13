import pytest
from fastapi.testclient import TestClient

from entwicklung import speicher
from entwicklung.leitstand.server import baue_app
from tests.test_graph_s1 import _abh, umgebung  # noqa: F401  (Fixture)
from tests.test_graph_s2 import _codex, _pruefer
from tests.test_graph_s3 import RICHTIG, Implementierer
from tests.test_graph_s4 import FRAGEN, KLAR, Planer, s4  # noqa: F401  (s4 Fixture)

PORT = 8793
TOKEN = "geheim-123"
BASIS = f"http://127.0.0.1:{PORT}"


@pytest.fixture
def leitstand(s4):
    repo, aufgaben = s4
    planer = Planer(klaeren=[KLAR])
    abh = _abh(aufgaben, implementierer=Implementierer(RICHTIG), pruefer=_pruefer(), codex=_codex(),
               planer=planer, planer_codex=planer.codex)
    app = baue_app(abh, speicher.oeffne_checkpointer(), TOKEN, PORT, repos_dir=repo.parent)
    client = TestClient(app, base_url=BASIS, headers={"X-Leitstand-Token": TOKEN})
    return client, app, repo


def _antworte(client, tid, **body):
    """Wie der Browser: mit dem angezeigten Haltepunkt und Stand."""
    lauf = client.get(f"/api/laeufe/{tid}").json()
    return client.post(f"/api/laeufe/{tid}/antwort",
                       json={"haltepunkt": lauf["wartepunkt"], "checkpoint_id": lauf["checkpoint_id"], **body})


def _starte(client, app, **body):
    r = client.post("/api/laeufe", json={"repo": "mini", "aufgabe": "M2", **body})
    assert r.status_code == 201, r.text
    tid = r.json()["thread_id"]
    app.state.ausfuehrer.warte(tid, 120)
    return tid


def test_ohne_token_403(leitstand):
    client, app, repo = leitstand
    ohne = TestClient(app, base_url=BASIS)
    assert ohne.get("/api/laeufe").status_code == 403
    assert ohne.get("/api/laeufe", headers={"X-Leitstand-Token": "falsch"}).status_code == 403
    # Die Seite selbst enthält keine Daten: Neuladen (F5, ohne Token in der Adresse) muss gehen.
    # Alle Daten und Aktionen laufen über /api und brauchen das Token im Header.
    assert ohne.get("/").status_code == 200
    assert ohne.get("/static/app.js").status_code == 200
    assert ohne.post("/api/laeufe", json={"repo": "mini", "aufgabe": "M2"}).status_code == 403


def test_seite_und_dateien_ohne_cache(leitstand):
    """Nach einem Update darf der Browser kein altes app.js nehmen (6b-1: neue Rat-Form, altes Skript zeigte keinen
    Rat). no-cache heißt: immer beim Server nachfragen; dank ETag kommt meist nur 304."""
    client, app, repo = leitstand
    for pfad in ("/", "/static/app.js", "/static/stil.css"):
        assert client.get(pfad).headers.get("cache-control") == "no-cache", pfad


def test_falscher_host_oder_origin_403(leitstand):
    client, app, repo = leitstand
    fremd = TestClient(app, base_url=f"http://localhost:{PORT}", headers={"X-Leitstand-Token": TOKEN})
    assert fremd.get("/api/laeufe").status_code == 403
    r = client.post("/api/laeufe", json={"repo": "mini", "aufgabe": "M2"}, headers={"Origin": "http://boese.example"})
    assert r.status_code == 403
    assert client.get("/api/laeufe", headers={"Origin": BASIS}).status_code == 200


def test_start_und_antwort_ueber_api(leitstand):
    client, app, repo = leitstand
    tid = _starte(client, app)
    lauf = client.get(f"/api/laeufe/{tid}").json()
    assert lauf["wartepunkt"] == "spec_freigabe" and lauf["frage"]["art"] == "spec_freigabe"
    assert lauf["zustand"] == {"laeuft": False, "fehler": None}
    assert client.get("/api/laeufe").json()[0]["thread_id"] == tid
    r = _antworte(client, tid, entscheidung="freigeben")
    assert r.status_code == 202, r.text
    app.state.ausfuehrer.warte(tid, 120)
    assert client.get(f"/api/laeufe/{tid}").json()["wartepunkt"] == "plan_freigabe"
    graph = client.get("/api/graph?stufe=4").json()
    assert {k["id"] for k in graph["knoten"]} >= {"klaeren", "plan_freigabe", "implementieren"}


def test_unpassende_antwort_400(leitstand):
    client, app, repo = leitstand
    tid = _starte(client, app)
    r = _antworte(client, tid, entscheidung="aendern")
    assert r.status_code == 400 and "tests_nachbessern" in r.json()["erlaubt"]
    r = _antworte(client, tid, antwort="hallo")
    assert r.status_code == 400
    assert client.get(f"/api/laeufe/{tid}").json()["wartepunkt"] == "spec_freigabe"


def test_lauf_wartet_nicht_409(leitstand):
    client, app, repo = leitstand
    tid = _starte(client, app)
    _antworte(client, tid, entscheidung="abbrechen")
    app.state.ausfuehrer.warte(tid, 120)
    r = client.post(f"/api/laeufe/{tid}/antwort", json={"haltepunkt": "spec_freigabe", "checkpoint_id": "x",
                                                        "entscheidung": "freigeben"})
    assert r.status_code == 409
    assert client.get("/api/laeufe/lauf-gibt-es-nicht").status_code == 404


@pytest.mark.parametrize("body", [{"repo": "../mini"}, {"repo": "gibtsnicht"}, {"aufgabe": "M9"},
                                  {"aufgabe": "../M2"}, {"stufe": 2}, {"modell": "fable"},
                                  {"pruefer_modell": "fable"}])
def test_start_nur_bekannte_werte(leitstand, body):
    client, app, repo = leitstand
    r = client.post("/api/laeufe", json={"repo": "mini", "aufgabe": "M2", **body})
    assert r.status_code == 400, body


def test_start_optionen(leitstand):
    client, app, repo = leitstand
    o = client.get("/api/start-optionen").json()
    assert o["repos"] == {"mini": ["M1", "M2"]} and "fable" not in o["modelle"] and o["stufen"] == [3, 4]


def test_standard_port_aus_ports_toml(tmp_path):
    from entwicklung.leitstand.server import standard_port
    liste = tmp_path / "ports.toml"
    liste.write_text('[[port]]\nport = 8766\nprojekt = "wiki"\n\n[[port]]\nport = 8794\nprojekt = "langgraph-lab-2"\n'
                     'zweck = "Leitstand (Stufe 5)"\n', encoding="utf-8")
    assert standard_port(liste) == 8794
    liste.write_text('[[port]]\nport = 8766\nprojekt = "wiki"\n', encoding="utf-8")
    assert standard_port(liste) is None
    assert standard_port(tmp_path / "fehlt.toml") is None


def test_cli_leitstand_port_belegt(capsys, monkeypatch):
    """Ohne echten Socket (Testsperre): bind meldet „belegt“."""
    import socket
    from entwicklung import cli

    class Belegt:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def bind(self, adresse):
            raise OSError(10048, "Adresse wird bereits verwendet")
    monkeypatch.setattr(socket, "socket", Belegt)
    assert cli.main(["leitstand", "--port", "8790", "--kein-browser"]) == 2
    assert "belegt" in capsys.readouterr().out



def test_veraltete_antwort_409(leitstand):
    """L2-002: Eine Freigabe aus einem veralteten Tab darf nicht den nächsten Haltepunkt treffen."""
    client, app, repo = leitstand
    tid = _starte(client, app)
    alt = client.get(f"/api/laeufe/{tid}").json()
    assert _antworte(client, tid, entscheidung="freigeben").status_code == 202
    app.state.ausfuehrer.warte(tid, 120)
    assert client.get(f"/api/laeufe/{tid}").json()["wartepunkt"] == "plan_freigabe"
    r = client.post(f"/api/laeufe/{tid}/antwort", json={"haltepunkt": alt["wartepunkt"],
                                                        "checkpoint_id": alt["checkpoint_id"],
                                                        "entscheidung": "freigeben"})
    assert r.status_code == 409 and "geändert" in r.json()["fehler"]
    r = client.post(f"/api/laeufe/{tid}/antwort", json={"haltepunkt": "plan_freigabe", "checkpoint_id": "falsch",
                                                        "entscheidung": "freigeben"})
    assert r.status_code == 409
    assert client.get(f"/api/laeufe/{tid}").json()["wartepunkt"] == "plan_freigabe"
    r = client.post(f"/api/laeufe/{tid}/antwort", json={"entscheidung": "freigeben"})
    assert r.status_code == 422  # ohne Haltepunkt und Stand nimmt der Server nichts an


def test_junction_ausserhalb_wird_nicht_angeboten(leitstand, tmp_path_factory):
    """L2-004: Ein Verweis (Junction/Symlink) unter dem Repo-Ordner auf ein Repo außerhalb zählt nicht."""
    import sys
    if sys.platform != "win32":
        pytest.skip("Junctions gibt es nur unter Windows")
    import _winapi
    client, app, repo = leitstand
    aussen = tmp_path_factory.mktemp("aussen") / "fremd"
    (aussen / ".git").mkdir(parents=True)
    (aussen / "entwicklung.toml").write_text('python = "x"\ntestbefehl = []\n', encoding="utf-8")
    _winapi.CreateJunction(str(aussen), str(repo.parent / "fremd"))
    (repo.parent / "aufgaben" / "fremd").mkdir()
    (repo.parent / "aufgaben" / "fremd" / "X1.md").write_text("# X1\n", encoding="utf-8")
    assert "fremd" not in client.get("/api/start-optionen").json()["repos"]
    assert client.post("/api/laeufe", json={"repo": "fremd", "aufgabe": "X1"}).status_code == 400


def test_info_kennzeichnet_demo(leitstand):
    """Die Demo mit Fake-Agenten muss in der Oberfläche als Demo erkennbar sein (Verwechslung am 20.10.)."""
    client, app, repo = leitstand
    assert client.get("/api/info").json() == {"demo": False, "port": PORT}
    demo = baue_app(None, speicher.oeffne_checkpointer(), TOKEN, PORT, repos_dir=repo.parent, demo=True)
    c = TestClient(demo, base_url=BASIS, headers={"X-Leitstand-Token": TOKEN})
    assert c.get("/api/info").json()["demo"] is True
