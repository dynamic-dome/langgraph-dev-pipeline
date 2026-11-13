"""Unabhängige Akzeptanztests für A3. Der Implementierer sieht sie nicht.

Imports des Zielcodes stehen in den Testfunktionen (Regel der Pipeline: Anzahl ohne Zielcode zählbar).
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

PORTS = """
[[port]]
port = 8702
projekt = "a"

[[port]]
port = 8702
projekt = "b"

[[port]]
port = 8766
projekt = "wiki-inselwelt"
"""

NETSTAT = (b"  Proto  Lokale Adresse  Remoteadresse  Status\r\n"
           b"  TCP    0.0.0.0:8700    0.0.0.0:0      ABH\x99REN\r\n"
           b"  TCP    127.0.0.1:8701  0.0.0.0:0      ABH\x99REN\r\n"
           b"  TCP    127.0.0.1:50000 127.0.0.1:8703 HERGESTELLT\r\n")


def _cli(*args, cwd, **umgebung):
    env = dict(os.environ, PYTHONPATH=str(REPO), PYTHONIOENCODING="utf-8", **umgebung)
    return subprocess.run([sys.executable, "-m", "portwart", *args], cwd=cwd, env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=60)


def _dateien(tmp_path, ports=PORTS, netstat=NETSTAT):
    (tmp_path / "ports.toml").write_text(ports, encoding="utf-8")
    (tmp_path / "netstat.txt").write_bytes(netstat)
    return str(tmp_path / "netstat.txt")


def test_freie_ports():
    from portwart.frei import freie_ports
    from portwart.liste import Eintrag
    eintraege = [Eintrag(8702, "a", ""), Eintrag(8702, "b", "")]
    assert freie_ports(eintraege, {8700, 8701}, 8700, 8705) == [8703, 8704, 8705]


def test_freie_ports_grenzen_einschliesslich():
    from portwart.frei import freie_ports
    assert freie_ports([], set(), 1, 1) == [1]
    assert freie_ports([], {65535}, 65535, 65535) == []
    assert freie_ports([], {8700}, 8699, 8701) == [8699, 8701]


@pytest.mark.parametrize("von,bis", [(8701, 8700), (0, 10), (8700, 65536)])
def test_freie_ports_ungueltig(von, bis):
    from portwart.frei import BereichsFehler, freie_ports
    assert issubclass(BereichsFehler, ValueError)
    with pytest.raises(BereichsFehler):
        freie_ports([], set(), von, bis)


def test_parse_bereich():
    from portwart.frei import parse_bereich
    assert parse_bereich("8700-8799") == (8700, 8799)
    assert parse_bereich("  1-65535 ") == (1, 65535)
    assert parse_bereich("8700-8700") == (8700, 8700)


@pytest.mark.parametrize("text", ["8700", "a-b", "8799-8700", "0-10", "8700-70000", "", "-5-10", "8700-"])
def test_parse_bereich_ungueltig(text):
    from portwart.frei import BereichsFehler, parse_bereich
    with pytest.raises(BereichsFehler):
        parse_bereich(text)


def test_cli_erster_freier(tmp_path):
    netstat = _dateien(tmp_path)
    r = _cli("frei", "8700-8799", "--netstat-datei", netstat, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines() == ["8703"]


def test_cli_anzahl(tmp_path):
    netstat = _dateien(tmp_path)
    r = _cli("frei", "8700-8799", "--anzahl", "3", "--netstat-datei", netstat, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines() == ["8703", "8704", "8705"]


def test_cli_weniger_als_anzahl(tmp_path):
    netstat = _dateien(tmp_path)
    r = _cli("frei", "8700-8704", "--anzahl", "5", "--netstat-datei", netstat, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines() == ["8703", "8704"]


def test_cli_kein_freier_port(tmp_path):
    netstat = _dateien(tmp_path)
    r = _cli("frei", "8700-8702", "--netstat-datei", netstat, cwd=tmp_path)
    assert r.returncode == 1, r.stderr
    assert r.stdout.strip() == "kein freier Port in 8700-8702"


def test_cli_andere_liste(tmp_path):
    netstat = _dateien(tmp_path)
    (tmp_path / "andere.toml").write_text('[[port]]\nport = 8703\nprojekt = "x"\n', encoding="utf-8")
    r = _cli("frei", "8700-8799", "--datei", str(tmp_path / "andere.toml"), "--netstat-datei", netstat,
             cwd=tmp_path)
    assert r.stdout.strip().splitlines() == ["8702"]


@pytest.mark.parametrize("args", [["8799-8700"], ["abc"], ["-5-10"], ["8700-8799", "--anzahl", "0"],
                                  ["8700-8799", "--anzahl", "-2"]])
def test_cli_ungueltige_eingabe(tmp_path, args):
    netstat = _dateien(tmp_path)
    r = _cli("frei", *args, "--netstat-datei", netstat, cwd=tmp_path)
    assert r.returncode == 2
    assert r.stderr.strip().startswith("Fehler: ")
    assert r.stdout.strip() == ""


def test_cli_kaputte_liste(tmp_path):
    netstat = _dateien(tmp_path, ports='[[port]]\nport = 0\nprojekt = "a"\n')
    r = _cli("frei", "8700-8799", "--netstat-datei", netstat, cwd=tmp_path)
    assert r.returncode == 2 and r.stderr.strip().startswith("Fehler: ") and r.stdout.strip() == ""


def test_cli_fehlende_netstat_datei(tmp_path):
    _dateien(tmp_path)
    r = _cli("frei", "8700-8799", "--netstat-datei", str(tmp_path / "fehlt.txt"), cwd=tmp_path)
    assert r.returncode == 2 and r.stderr.strip().startswith("Fehler: ")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-Vertrag (netstat aus SystemRoot, A2)")
def test_cli_ohne_netstat_datei_nutzt_lies_netstat(tmp_path):
    """Ohne --netstat-datei läuft lies_netstat(). Unter einem SystemRoot ohne netstat.exe gibt es LauschFehler,
    also Exit-Code 2, statt still mit leerer Portmenge Ports vorzuschlagen."""
    _dateien(tmp_path)
    r = _cli("frei", "8700-8799", cwd=tmp_path, SystemRoot=str(tmp_path))
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert r.stderr.strip().startswith("Fehler: ") and r.stdout.strip() == ""


def test_bisherige_befehle_unveraendert(tmp_path):
    netstat = _dateien(tmp_path)
    r = _cli("pruefen", cwd=tmp_path)
    assert (r.returncode, r.stdout.strip()) == (1, "Port 8702 doppelt: a, b")
    r = _cli("abgleich", "--netstat-datei", netstat, cwd=tmp_path)
    assert r.stdout.strip().splitlines() == ["frei 8702 a, b", "frei 8766 wiki-inselwelt",
                                            "unbekannt 8700", "unbekannt 8701"]
