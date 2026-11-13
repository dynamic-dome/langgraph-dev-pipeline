"""Kommandozeile: python -m portwart pruefen|abgleich|frei|drift [WURZEL] [--datei PFAD] [--ausschliessen NAME ...]
eintragen NAME PORT [--datei PFAD] [--zweck TEXT] [--pfad PFAD]
austragen NAME [--datei PFAD]"""
from __future__ import annotations

import argparse
import os
import re
import sys

from portwart.abgleich import abgleich
from portwart.austragen import AustragFehler, trage_aus
from portwart.eintragen import EintragFehler, anzeige_text, trage_ein
from portwart.drift import DriftFehler, drift, durchsuche_liste, zeilen
from portwart.frei import BereichsFehler, freie_ports, parse_bereich
from portwart.lauschen import LauschFehler, lauschende_ports, lies_netstat
from portwart.liste import ListenFehler, doppelte, lade, lade_ausschluss


class _ArgFehler(Exception):
    pass


def _lies_text(args) -> str:
    """netstat-Ausgabe aus --netstat-datei lesen oder netstat starten."""
    if not args.netstat_datei:
        return lies_netstat()
    try:
        with open(args.netstat_datei, "rb") as f:
            return f.read().decode(errors="replace")
    except OSError as e:
        raise LauschFehler(
            f"netstat-Datei nicht lesbar: {args.netstat_datei}: {e}"
        ) from None


def _abgleich(args) -> int:
    try:
        eintraege = lade(args.datei)
        text = _lies_text(args)
    except (ListenFehler, LauschFehler) as e:
        print(f"Fehler: {e}", file=sys.stderr)
        return 2
    bereich = (1, 65535) if args.alle else (1024, 49151)
    ergebnis = abgleich(eintraege, lauschende_ports(text), bereich)
    projekte: dict[int, set[str]] = {}
    for e in eintraege:
        projekte.setdefault(e.port, set()).add(e.projekt)
    zeilen = []
    for status, ports in (("belegt", ergebnis.belegt), ("frei", ergebnis.frei)):
        for p in ports:
            zeilen.append(f"{status} {p} {', '.join(sorted(projekte[p]))}")
    for p in ergebnis.unbekannt:
        zeilen.append(f"unbekannt {p}")
    if zeilen:
        print("\n".join(zeilen))
    return 1 if ergebnis.unbekannt else 0


def _frei(args) -> int:
    try:
        von, bis = parse_bereich(args.bereich)
        try:
            anzahl = int(args.anzahl)
        except ValueError:
            raise BereichsFehler(
                f"--anzahl muss eine ganze Zahl sein: {args.anzahl!r}"
            ) from None
        if anzahl < 1:
            raise BereichsFehler("--anzahl muss mindestens 1 sein")
        eintraege = lade(args.datei)
        text = _lies_text(args)
        frei =freie_ports(eintraege, lauschende_ports(text), von, bis)
    except (BereichsFehler, ListenFehler, LauschFehler) as e:
        print(f"Fehler: {e}", file=sys.stderr)
        return 2
    if not frei:
        print(f"kein freier Port in {von}-{bis}")
        return 1
    print("\n".join(str(p) for p in frei[:anzahl]))
    return 0


def _drift(args) -> int:
    try:
        eintraege = lade(args.datei)
        ausschluss = lade_ausschluss(args.datei)
        basis = os.path.dirname(os.path.abspath(args.datei))
        alle = ausschluss + list(args.ausschliessen or [])
        d = durchsuche_liste(eintraege, basis, args.wurzel, alle)
    except (ListenFehler, DriftFehler) as e:
        print(f"Fehler: {e}", file=sys.stderr)
        return 2
    except UnicodeDecodeError as e:
        print(f"Fehler: Liste ist kein gültiges TOML: {args.datei}: {e}",
              file=sys.stderr)
        return 2
    aus = zeilen(drift(eintraege, d.funde, d.fehlend))
    if not aus:
        print("kein Drift")
        return 0
    print("\n".join(aus))
    return 1


def _eintragen(args) -> int:
    def fehler(grund) -> int:
        print(f"Fehler: {anzeige_text(str(grund))}", file=sys.stderr)
        return 2

    try:
        lade(args.datei)
        try:
            port = int(args.port)
        except ValueError:
            return fehler(f"Port muss eine ganze Zahl sein: {args.port!r}")
        trage_ein(args.datei, args.name, port, args.zweck, args.pfad)
    except (ListenFehler, EintragFehler) as e:
        return fehler(e)
    except UnicodeDecodeError as e:
        return fehler(f"Liste ist kein gültiges TOML: {args.datei}: {e}")
    print(f"eingetragen {anzeige_text(args.name)} {port}")
    return 0


def _austragen(args) -> int:
    def fehler(grund) -> int:
        print(f"Fehler: {anzeige_text(str(grund))}", file=sys.stderr)
        return 2

    try:
        lade(args.datei)
        e = trage_aus(args.datei, args.name)
    except (ListenFehler, AustragFehler) as err:
        return fehler(err)
    except UnicodeDecodeError as err:
        return fehler(f"Liste ist kein gültiges TOML: {args.datei}: {err}")
    print(f"ausgetragen {anzeige_text(args.name)} {e.port}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="portwart")
    sub = parser.add_subparsers(dest="befehl", required=True)
    p = sub.add_parser("pruefen", help="doppelte Ports melden")
    p.add_argument("--datei", default="ports.toml")
    a = sub.add_parser("abgleich", help="lauschende Ports mit der Liste vergleichen")
    a.add_argument("--datei", default="ports.toml")
    a.add_argument("--netstat-datei")
    a.add_argument("--alle", action="store_true")
    f = sub.add_parser("frei", help="freie Ports in einem Bereich vorschlagen")
    f.add_argument("bereich")
    f.add_argument("--anzahl", default="1")
    f.add_argument("--datei", default="ports.toml")
    f.add_argument("--netstat-datei")
    d = sub.add_parser("drift", help="Port-Angaben im Code mit der Liste vergleichen")
    d.add_argument("wurzel", nargs="?")
    d.add_argument("--datei", default="ports.toml")
    d.add_argument("--ausschliessen", metavar="NAME", action="append", default=[])
    e = sub.add_parser("eintragen", help="neuen Port in die Liste eintragen")
    e.add_argument("name")
    e.add_argument("port")
    e.add_argument("--datei", default="ports.toml")
    e.add_argument("--zweck")
    e.add_argument("--pfad")
    au = sub.add_parser("austragen", help="Port aus der Liste austragen")
    au.add_argument("name")
    au.add_argument("--datei", default="ports.toml")
    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    if argv and argv[0] == "frei":
        def _fehler(message):
            zeile = " ".join(message.split())
            print(f"Fehler: {zeile}", file=sys.stderr)
            raise _ArgFehler

        f.error = parser.error = _fehler
        # Bereiche mit führendem Minus (z. B. "-1-5") nicht als Option lesen
        i = 1
        while i < len(argv):
            tok = argv[i]
            if tok == "--":
                break
            if tok in ("--anzahl", "--datei", "--netstat-datei"):
                i += 2
                continue
            if re.match(r"-\d", tok) and not re.fullmatch(r"-\d+", tok):
                argv = argv[:i] + argv[i + 1:] + ["--", tok]
                break
            i += 1
    try:
        args = parser.parse_args(argv)
    except _ArgFehler:
        return 2

    if args.befehl == "eintragen":
        return _eintragen(args)

    if args.befehl == "austragen":
        return _austragen(args)

    if args.befehl == "frei":
        return _frei(args)

    if args.befehl == "drift":
        return _drift(args)

    if args.befehl == "abgleich":
        return _abgleich(args)

    try:
        dopp = doppelte(lade(args.datei))
    except ListenFehler as e:
        print(f"Fehler: {e}", file=sys.stderr)
        return 2
    if not dopp:
        print("keine doppelten Ports")
        return 0
    for port, projekte in dopp.items():
        print(f"Port {port} doppelt: {', '.join(projekte)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
