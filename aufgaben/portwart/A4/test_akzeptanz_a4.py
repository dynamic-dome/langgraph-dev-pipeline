"""Akzeptanztests A4 (Port-Drift), erzeugt vom Test-Schreiber der Pipeline im Lauf 20261020-120157, von
Dominic freigegeben (Spec-Freigabe 20.10.). Unverändert übernommen bis auf eine Ausnahme:
test_durchsuche_symlink_auf_ordner_nicht_verfolgt gestrichen. Er braucht einen echten Ordner-Symlink, der auf diesem Rechner
nicht erlaubt ist (WinError 1314), und sprang deshalb aus. Ein übersprungener Test in der Regression würde jede
spätere Aufgabe rot machen (Funktionsprüfung).
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def cli(tmp_path, *args):
    return subprocess.run(
        [sys.executable, "-m", "portwart", *args],
        cwd=tmp_path,
        env=dict(os.environ, PYTHONPATH=str(REPO), PYTHONIOENCODING="utf-8"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )


def schreibe(pfad, inhalt):
    pfad.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(inhalt, str):
        inhalt = inhalt.encode("utf-8")
    pfad.write_bytes(inhalt)


def liste_toml(tmp_path, eintraege):
    text = ""
    for port, projekt in eintraege:
        text += f'[[port]]\nport = {port}\nprojekt = "{projekt}"\n\n'
    p = tmp_path / "ports.toml"
    p.write_text(text, encoding="utf-8")
    return p


def ports(text):
    from portwart.drift import finde_ports
    return finde_ports(text)


# ---------- finde_ports ----------

def test_schluesselmuster_treffer():
    text = (
        "PORT=8766\n"
        "export PORT=8767\n"
        "port = 8768\n"
        "port: 8769\n"
        '"port": 8770\n'
        "web_port = 1\n"
        "DB_PORT='5432'\n"
        "port\t=\t65535\n"
    )
    assert ports(text) == [
        (1, 8766), (2, 8767), (3, 8768), (4, 8769), (5, 8770),
        (6, 1), (7, 5432), (8, 65535),
    ]


def test_schluessel_nichttreffer():
    text = "report = 5\ntransport: 80\nmyport=81\nport_x = 82\n12:30\n{\"a\":8080}\n"
    assert ports(text) == []


def test_option_port():
    assert ports("run --port 8766\nrun --port=8767\nrun --port \t8768\n") == [
        (1, 8766), (2, 8767), (3, 8768)
    ]


def test_hostmuster_localhost_und_ip():
    text = (
        "curl localhost:3000\n"
        "x 127.0.0.1:5000 y\n"
        "bind 0.0.0.0:8000\n"
        "xlocalhost:3001\n"
        "a.localhost:3002\n"
    )
    assert ports(text) == [(1, 3000), (2, 5000), (3, 8000)]


def test_url_host_muster():
    text = (
        "u = https://example.com:8443/path\n"
        "v = postgres://db-server:5432\n"
        "w = http://localhost:8080/\n"
        "x = http://example.com/no/port\n"
    )
    assert ports(text) == [(1, 8443), (2, 5432), (3, 8080)]


def test_ungueltige_zahlen_ignoriert():
    text = (
        "port = 0\n"
        "port = 65536\n"
        "port = 08766\n"
        "port = 8766abc\n"
        "port = 8766_x\n"
        "port = 8766.5\n"
        "port = 99999\n"
        "port = 8766\n"
    )
    assert ports(text) == [(8, 8766)]


def test_zeilen_sortierung_duplikate_und_zeilenenden():
    text = "port=80 --port 81 port=80\r\nlocalhost:90\rhttp://localhost:90\nport: 5"
    assert ports(text) == [(1, 80), (1, 81), (2, 90), (3, 90), (4, 5)]


# ---------- durchsuche ----------

def test_durchsuche_projekte_pfade_sortierung(tmp_path):
    from portwart.drift import durchsuche, Fund
    schreibe(tmp_path / "wiki" / "src" / "app.py", "x = 1\n\nport = 9000\n")
    schreibe(tmp_path / "wiki" / "a.txt", "PORT=7000\nport=6000\n")
    (tmp_path / "leer").mkdir()
    schreibe(tmp_path / "lose.txt", "port=1234\n")
    erg = durchsuche(tmp_path)
    assert set(erg) == {"wiki", "leer"}
    assert erg["leer"] == []
    assert erg["wiki"] == [
        Fund(7000, "wiki/a.txt", 1),
        Fund(6000, "wiki/a.txt", 2),
        Fund(9000, "wiki/src/app.py", 3),
    ] or erg["wiki"] == sorted(erg["wiki"], key=lambda f: (f.datei, f.zeile, f.port))
    assert [(f.datei, f.zeile, f.port) for f in erg["wiki"]] == [
        ("wiki/a.txt", 1, 7000),
        ("wiki/a.txt", 2, 6000),
        ("wiki/src/app.py", 3, 9000),
    ]
    # str-Pfad funktioniert ebenfalls
    assert durchsuche(str(tmp_path)) == erg


def test_durchsuche_ausschlussordner(tmp_path):
    from portwart.drift import durchsuche
    namen = [".git", "node_modules", ".venv", "__pycache__", "dist", "build",
             "arbeit", ".pytest_cache"]
    for n in namen:
        schreibe(tmp_path / "proj" / n / "x.txt", "port=1111\n")
        schreibe(tmp_path / "proj" / "sub" / n / "x.txt", "port=2222\n")
        schreibe(tmp_path / n / "x.txt", "port=3333\n")
    schreibe(tmp_path / "proj" / "ok.txt", "port=4444\n")
    erg = durchsuche(tmp_path)
    assert set(erg) == {"proj"}
    assert [(f.datei, f.port) for f in erg["proj"]] == [("proj/ok.txt", 4444)]


def test_durchsuche_ueberspringt_binaer_gross_nicht_utf8(tmp_path):
    from portwart.drift import durchsuche
    p = tmp_path / "p"
    schreibe(p / "bin.dat", b"port=1001\n\x00\x01")
    schreibe(p / "latin.txt", "port=1002\n\xe4".encode("latin-1"))
    kopf = b"port=1003\n"
    schreibe(p / "genau.txt", kopf + b" " * (1048576 - len(kopf)))
    schreibe(p / "zu_gross.txt", kopf + b" " * (1048577 - len(kopf)))
    schreibe(p / "bom.txt", b"\xef\xbb\xbfport=1004\n")
    schreibe(p / "ok.md", "port=1005 ä\n")
    erg = durchsuche(tmp_path)
    gefunden = {(f.datei, f.port) for f in erg["p"]}
    assert gefunden == {("p/genau.txt", 1003), ("p/bom.txt", 1004), ("p/ok.md", 1005)}


def test_durchsuche_fehler(tmp_path):
    from portwart.drift import durchsuche, DriftFehler
    fehlt = tmp_path / "nix"
    with pytest.raises(DriftFehler) as e:
        durchsuche(fehlt)
    assert str(e.value) == f"Wurzelordner nicht gefunden: {fehlt}"
    datei = tmp_path / "datei.txt"
    datei.write_text("x")
    with pytest.raises(DriftFehler) as e:
        durchsuche(datei)
    assert str(e.value) == f"Wurzel ist kein Ordner: {datei}"
    assert issubclass(DriftFehler, ValueError)


# ---------- drift / zeilen ----------

def test_drift_unbekannt_sortiert():
    from portwart.drift import drift, Fund, Unbekannt
    from portwart.liste import Eintrag
    eintraege = [Eintrag(8000, "a")]
    funde = {
        "b": [Fund(9100, "b/z.py", 2), Fund(9000, "b/z.py", 5)],
        "a": [Fund(8000, "a/x.py", 1), Fund(9000, "a/x.py", 3)],
        "frei": [Fund(9000, "frei/f.py", 1)],
    }
    erg = drift(eintraege, funde)
    assert erg.unbekannt == [
        Unbekannt(9000, "a", "a/x.py", 3),
        Unbekannt(9000, "b", "b/z.py", 5),
        Unbekannt(9000, "frei", "frei/f.py", 1),
        Unbekannt(9100, "b", "b/z.py", 2),
    ]
    assert erg.abweichend == []


def test_drift_abweichend_mit_mehreren_ports():
    from portwart.drift import drift, Fund, Abweichung
    from portwart.liste import Eintrag
    eintraege = [Eintrag(8770, "job-radar")]
    funde = {"job-radar": [
        Fund(8002, "job-radar/config.py", 9),
        Fund(8001, "job-radar/config.py", 7),
        Fund(8001, "job-radar/zz.py", 1),
    ]}
    # Eingabe bereits wie von durchsuche sortiert
    funde["job-radar"].sort(key=lambda f: (f.datei, f.zeile, f.port))
    erg = drift(eintraege, funde)
    assert erg.abweichend == [
        Abweichung("job-radar", [8770], [8001, 8002], "job-radar/config.py", 7)
    ]


def test_drift_kein_befund_faelle():
    from portwart.drift import drift, Fund
    from portwart.liste import Eintrag
    eintraege = [
        Eintrag(8000, "a"), Eintrag(8001, "a"),   # mehrere Eintraege, einer genuegt
        Eintrag(8100, "b"),                       # zusaetzlicher Listenport im Code
        Eintrag(8200, "ohne-ordner"),             # kein Ordner
        Eintrag(8300, "c"),                       # keine Funde
    ]
    funde = {
        "a": [Fund(8001, "a/x", 1)],
        "b": [Fund(8100, "b/x", 2), Fund(8100, "b/y", 1)],
        "c": [],
    }
    erg = drift(eintraege, funde)
    assert erg.unbekannt == []
    assert erg.abweichend == []


def test_drift_port_eines_anderen_projekts_fuehrt_zur_abweichung():
    from portwart.drift import drift, Fund, Abweichung
    from portwart.liste import Eintrag
    eintraege = [Eintrag(8000, "a"), Eintrag(8001, "b"), Eintrag(8002, "a")]
    funde = {"a": [Fund(8001, "a/x.py", 4)], "b": [Fund(8001, "b/y.py", 1)]}
    erg = drift(eintraege, funde)
    assert erg.unbekannt == []
    assert erg.abweichend == [Abweichung("a", [8000, 8002], [8001], "a/x.py", 4)]


def test_drift_projektname_gross_kleinschreibung():
    from portwart.drift import drift, Fund
    from portwart.liste import Eintrag
    erg = drift([Eintrag(8000, "Wiki")], {"wiki": [Fund(8000, "wiki/x", 1)]})
    assert erg.unbekannt == [] and erg.abweichend == []
    erg = drift([Eintrag(8000, "Wiki"), Eintrag(8500, "x")], {"wiki": [Fund(8500, "wiki/x", 1)]})
    assert erg.abweichend == []


def test_zeilen_format_und_reihenfolge():
    from portwart.drift import zeilen, DriftErgebnis, Unbekannt, Abweichung
    erg = DriftErgebnis(
        unbekannt=[Unbekannt(9000, "wiki", "wiki/src/app.py", 12)],
        abweichend=[
            Abweichung("job-radar", [8770], [8001, 8002], "job-radar/config.py", 7),
            Abweichung("x", [1, 2], [3], "x/a", 1),
        ],
    )
    assert zeilen(erg) == [
        "unbekannt 9000 wiki wiki/src/app.py:12",
        "abweichend job-radar LISTE=8770 CODE=8001,8002 job-radar/config.py:7",
        "abweichend x LISTE=1,2 CODE=3 x/a:1",
    ]
    assert zeilen(DriftErgebnis([], [])) == []


# ---------- CLI ----------

def test_cli_kein_drift_exit0(tmp_path):
    wurzel = tmp_path / "w"
    schreibe(wurzel / "wiki" / "app.py", "port = 8000\n")
    liste_toml(tmp_path, [(8000, "wiki")])
    r = cli(tmp_path, "drift", "w")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "kein Drift"


def test_cli_leere_liste_ohne_ports_exit0(tmp_path):
    (tmp_path / "w" / "p").mkdir(parents=True)
    (tmp_path / "ports.toml").write_text("", encoding="utf-8")
    r = cli(tmp_path, "drift", "w")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "kein Drift"


def test_cli_befunde_exit1_und_zeilen(tmp_path):
    wurzel = tmp_path / "w"
    schreibe(wurzel / "sig" / "run.bat", "@echo off\nrem x\nset PORT=8766\n")
    schreibe(wurzel / "wiki" / "app.py", "a\nport = 8000\nport = 9000\n")
    liste_toml(tmp_path, [(8767, "sig"), (8000, "wiki")])
    r = cli(tmp_path, "drift", "w")
    assert r.returncode == 1, r.stderr
    assert r.stdout.splitlines() == [
        "unbekannt 8766 sig sig/run.bat:3",
        "unbekannt 9000 wiki wiki/app.py:3",
        "abweichend sig LISTE=8767 CODE=8766 sig/run.bat:3",
    ]


def test_cli_eigene_datei_option(tmp_path):
    schreibe(tmp_path / "w" / "p" / "a.py", "port = 7777\n")
    (tmp_path / "andere.toml").write_text(
        '[[port]]\nport = 7777\nprojekt = "p"\n', encoding="utf-8")
    r = cli(tmp_path, "drift", "w", "--datei", "andere.toml")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "kein Drift"


def test_cli_fehler_exit2(tmp_path):
    (tmp_path / "w").mkdir()
    # Liste fehlt
    r = cli(tmp_path, "drift", "w")
    assert r.returncode == 2
    assert r.stdout == ""
    assert r.stderr.startswith("Fehler: ")
    # Liste ungültig
    (tmp_path / "ports.toml").write_text("[[port\n", encoding="utf-8")
    r = cli(tmp_path, "drift", "w")
    assert r.returncode == 2 and r.stdout == "" and r.stderr.startswith("Fehler: ")
    # Wurzel fehlt
    (tmp_path / "ports.toml").write_text("", encoding="utf-8")
    r = cli(tmp_path, "drift", "nix")
    assert r.returncode == 2 and r.stdout == ""
    assert r.stderr.startswith("Fehler: Wurzelordner nicht gefunden: nix")
    # Wurzel ist Datei
    (tmp_path / "datei").write_text("x")
    r = cli(tmp_path, "drift", "datei")
    assert r.returncode == 2 and r.stdout == ""
    assert r.stderr.startswith("Fehler: Wurzel ist kein Ordner: datei")


def test_cli_wurzel_pflichtargument(tmp_path):
    r = cli(tmp_path, "drift")
    assert r.returncode == 2
    assert r.stdout == ""
    assert r.stderr != ""


def test_cli_veraendert_nichts(tmp_path):
    wurzel = tmp_path / "w"
    schreibe(wurzel / "a" / "x.py", "port = 9000\n")
    schreibe(wurzel / "a" / "bin", b"\x00\xff port=1")
    schreibe(wurzel / "b" / "y.txt", "PORT=8001\n")
    liste_toml(tmp_path, [(8002, "b")])

    def schnappschuss():
        return {str(p.relative_to(tmp_path)): p.read_bytes()
                for p in tmp_path.rglob("*") if p.is_file()}

    vorher = schnappschuss()
    r = cli(tmp_path, "drift", "w")
    assert r.returncode == 1, r.stderr
    assert schnappschuss() == vorher


def test_bestehende_befehle_weiter_vorhanden(tmp_path):
    r = cli(tmp_path, "--help")
    assert r.returncode == 0
    for name in ("pruefen", "abgleich", "frei", "drift"):
        assert name in r.stdout
