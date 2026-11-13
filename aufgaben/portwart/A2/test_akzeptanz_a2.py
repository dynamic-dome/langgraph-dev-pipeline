"""Unabhängige Akzeptanztests für A2. Der Implementierer sieht sie nicht.

Imports des Zielcodes stehen in den Testfunktionen (Regel der Pipeline: Anzahl ohne Zielcode zählbar).
"""
import dataclasses
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# Ausschnitt eines echten Mitschnitts (deutsches Windows, cp850: b"\x99" ist "Ö" in ABHÖREN)
NETSTAT_DE = (
    b"\r\nAktive Verbindungen\r\n\r\n"
    b"  Proto  Lokale Adresse         Remoteadresse          Status\r\n"
    b"  TCP    0.0.0.0:135            0.0.0.0:0              ABH\x99REN\r\n"
    b"  TCP    0.0.0.0:8766           0.0.0.0:0              ABH\x99REN\r\n"
    b"  TCP    127.0.0.1:8770         0.0.0.0:0              ABH\x99REN\r\n"
    b"  TCP    127.0.0.1:9000         0.0.0.0:0              ABH\x99REN\r\n"
    b"  TCP    0.0.0.0:49664          0.0.0.0:0              ABH\x99REN\r\n"
    b"  TCP    127.0.0.1:50123        127.0.0.1:8766         HERGESTELLT\r\n"
    b"  TCP    [::]:445               [::]:0                 ABH\x99REN\r\n"
    b"  TCP    [::1]:7171             [::]:0                 ABH\x99REN\r\n"
    b"  UDP    0.0.0.0:5353           *:*                    \r\n"
)

NETSTAT_EN = """
Active Connections

  Proto  Local Address          Foreign Address        State
  TCP    0.0.0.0:8080           0.0.0.0:0              LISTENING
  TCP    192.168.1.5:51000      140.82.112.4:443       ESTABLISHED
  tcpv6  [::]:8443              [::]:0                 LISTENING
  UDP    [::]:5353              *:*
"""

PORTS = """
[[port]]
port = 8766
projekt = "wiki-inselwelt"

[[port]]
port = 8770
projekt = "tool-tracker"

[[port]]
port = 8770
projekt = "job-radar"

[[port]]
port = 8792
projekt = "langgraph-lab"
"""


def _cli(*args, cwd):
    env = dict(os.environ, PYTHONPATH=str(REPO), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-m", "portwart", *args], cwd=cwd, env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=60)


def _dateien(tmp_path, netstat=NETSTAT_DE, ports=PORTS):
    (tmp_path / "ports.toml").write_text(ports, encoding="utf-8")
    (tmp_path / "netstat.txt").write_bytes(netstat)
    return tmp_path / "netstat.txt"


def test_lauschende_ports_deutsch_cp850():
    from portwart.lauschen import lauschende_ports
    text = NETSTAT_DE.decode("utf-8", errors="replace")
    assert lauschende_ports(text) == {135, 8766, 8770, 9000, 49664, 445, 7171}


def test_lauschende_ports_englisch_und_tcpv6():
    from portwart.lauschen import lauschende_ports
    assert lauschende_ports(NETSTAT_EN) == {8080, 8443}


def test_verbindungen_udp_und_kopf_ignoriert():
    from portwart.lauschen import lauschende_ports
    assert lauschende_ports("  Proto  Lokale Adresse  Remoteadresse  Status\n"
                            "  TCP    127.0.0.1:50123  127.0.0.1:8766  HERGESTELLT\n"
                            "  UDP    0.0.0.0:5353  *:*\n\n") == set()


def test_stern_gegenadresse():
    from portwart.lauschen import lauschende_ports
    assert lauschende_ports("  TCP    *:8000    *:0    LISTEN\n") == {8000}


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-Vertrag")
def test_lies_netstat_nutzt_systemroot(monkeypatch, tmp_path):
    """Ohne netstat.exe unter SystemRoot gibt es LauschFehler, auch wenn netstat über PATH zu finden wäre."""
    from portwart import lauschen
    monkeypatch.setenv("SystemRoot", str(tmp_path))
    with pytest.raises(lauschen.LauschFehler):
        lauschen.lies_netstat()
    assert issubclass(lauschen.LauschFehler, RuntimeError)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-Vertrag")
def test_lies_netstat_ignoriert_netstat_im_arbeitsordner(monkeypatch, tmp_path):
    """Eine untergeschobene netstat.bat im aktuellen Ordner darf nie laufen (Windows-Standard ohne
    NoDefaultCurrentDirectoryInExePath, aktueller Ordner zuerst im PATH)."""
    from portwart import lauschen
    (tmp_path / "netstat.bat").write_bytes(b"@echo off\r\necho UNTERGESCHOBEN\r\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path) + ";" + __import__("os").environ.get("PATH", ""))
    text = lauschen.lies_netstat()
    assert "UNTERGESCHOBEN" not in text
    assert lauschen.lauschende_ports(text)  # das echte netstat lief und lieferte lauschende Ports


def test_abgleich_kategorien():
    from portwart.abgleich import Abgleich, abgleich
    from portwart.liste import Eintrag
    eintraege = [Eintrag(8766, "a", ""), Eintrag(8770, "b", ""), Eintrag(8770, "c", ""), Eintrag(8792, "d", "")]
    erg = abgleich(eintraege, {135, 8766, 8770, 9000, 49664, 49151, 1024})
    assert erg == Abgleich(belegt=[8766, 8770], frei=[8792], unbekannt=[1024, 9000, 49151])


def test_abgleich_bereich_nur_fuer_unbekannt():
    from portwart.abgleich import abgleich
    from portwart.liste import Eintrag
    erg = abgleich([Eintrag(80, "web", ""), Eintrag(50000, "hoch", "")], {80, 81, 50001}, bereich=(1024, 49151))
    assert (erg.belegt, erg.frei, erg.unbekannt) == ([80], [50000], [])
    erg = abgleich([], {80, 81, 50001}, bereich=(1, 65535))
    assert erg.unbekannt == [80, 81, 50001]


def test_abgleich_frozen():
    from portwart.abgleich import abgleich
    erg = abgleich([], set())
    with pytest.raises(dataclasses.FrozenInstanceError):
        erg.frei = [1]


def test_cli_abgleich(tmp_path):
    netstat = _dateien(tmp_path)
    r = _cli("abgleich", "--netstat-datei", str(netstat), cwd=tmp_path)
    assert r.returncode == 1, r.stderr
    assert r.stdout.strip().splitlines() == [
        "belegt 8766 wiki-inselwelt",
        "belegt 8770 job-radar, tool-tracker",
        "frei 8792 langgraph-lab",
        "unbekannt 7171",
        "unbekannt 9000",
    ]


def test_cli_alle(tmp_path):
    netstat = _dateien(tmp_path)
    r = _cli("abgleich", "--netstat-datei", str(netstat), "--alle", cwd=tmp_path)
    zeilen = r.stdout.strip().splitlines()
    assert "unbekannt 135" in zeilen and "unbekannt 445" in zeilen and "unbekannt 49664" in zeilen
    assert zeilen.index("unbekannt 135") < zeilen.index("unbekannt 445") < zeilen.index("unbekannt 49664")


def test_cli_nichts_unbekannt_exit_0(tmp_path):
    netstat = _dateien(tmp_path, netstat=b"  TCP    0.0.0.0:8766    0.0.0.0:0    LISTENING\r\n")
    r = _cli("abgleich", "--netstat-datei", str(netstat), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines() == [
        "belegt 8766 wiki-inselwelt", "frei 8770 job-radar, tool-tracker", "frei 8792 langgraph-lab"]


def test_cli_andere_datei(tmp_path):
    netstat = _dateien(tmp_path)
    andere = tmp_path / "sub"
    andere.mkdir()
    (andere / "liste.toml").write_text('[[port]]\nport = 9000\nprojekt = "neu"\n', encoding="utf-8")
    r = _cli("abgleich", "--datei", str(andere / "liste.toml"), "--netstat-datei", str(netstat), cwd=tmp_path)
    assert "belegt 9000 neu" in r.stdout.splitlines()


def test_cli_fehlende_netstat_datei(tmp_path):
    _dateien(tmp_path)
    r = _cli("abgleich", "--netstat-datei", str(tmp_path / "fehlt.txt"), cwd=tmp_path)
    assert r.returncode == 2
    assert r.stderr.strip().startswith("Fehler: ")
    assert r.stdout.strip() == ""


def test_cli_kaputte_liste(tmp_path):
    netstat = _dateien(tmp_path, ports='[[port]]\nport = 0\nprojekt = "a"\n')
    r = _cli("abgleich", "--netstat-datei", str(netstat), cwd=tmp_path)
    assert r.returncode == 2
    assert r.stderr.strip().startswith("Fehler: ")


def test_pruefen_aus_a1_unveraendert(tmp_path):
    _dateien(tmp_path)
    r = _cli("pruefen", cwd=tmp_path)
    assert r.returncode == 1
    assert r.stdout.strip() == "Port 8770 doppelt: job-radar, tool-tracker"
