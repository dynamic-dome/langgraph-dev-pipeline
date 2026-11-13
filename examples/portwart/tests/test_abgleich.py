from portwart.__main__ import main
from portwart.abgleich import Abgleich, abgleich
from portwart.lauschen import lauschende_ports
from portwart.liste import Eintrag

NS = """Aktive Verbindungen
  Proto  Lokale Adresse  Remoteadresse  Status
  TCP    0.0.0.0:8766   0.0.0.0:0   ABH�REN
  TCPv6  [::1]:9000     [::]:0      LISTENING
  TCP    1.2.3.4:5000   5.6.7.8:443 ESTABLISHED
  UDP    0.0.0.0:7000   *:0
"""


def test_lauschend():
    assert lauschende_ports(NS) == {8766, 9000}


def test_abgleich():
    e = [Eintrag(8766, "a"), Eintrag(8792, "b")]
    assert abgleich(e, {8766, 9000, 80}) == Abgleich([8766], [8792], [9000])
    assert abgleich(e, {80}, (1, 65535)).unbekannt == [80]


def test_befehl(tmp_path, capsys):
    t = tmp_path / "p.toml"
    t.write_text('[[port]]\nport=8766\nprojekt="x"\n[[port]]\nport=8766\nprojekt="a"\n'
                 '[[port]]\nport=8792\nprojekt="l"\n')
    n = tmp_path / "n.txt"
    n.write_bytes(NS.encode("utf-8"))
    assert main(["abgleich", "--datei", str(t), "--netstat-datei", str(n)]) == 1
    assert capsys.readouterr().out == "belegt 8766 a, x\nfrei 8792 l\nunbekannt 9000\n"
    assert main(["abgleich", "--datei", str(t), "--netstat-datei", str(tmp_path / "nix")]) == 2
    c = capsys.readouterr()
    assert c.out == "" and c.err.startswith("Fehler: ")
