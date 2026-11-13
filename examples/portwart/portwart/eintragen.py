"""Eintragen eines neuen [[port]]-Blocks in die Portliste ports.toml."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from portwart.liste import Eintrag, lade

_KURZ = {"\n": "\\n", "\r": "\\r", "\t": "\\t", "\b": "\\b", "\f": "\\f"}


class EintragFehler(ValueError):
    """Der Eintrag wurde abgelehnt oder konnte nicht geschrieben werden."""


def _steuer(c: str) -> bool:
    return ord(c) < 0x20 or ord(c) == 0x7F


def toml_text(wert: str) -> str:
    teile = ['"']
    for c in wert:
        if c == "\\":
            teile.append("\\\\")
        elif c == '"':
            teile.append('\\"')
        elif c in _KURZ:
            teile.append(_KURZ[c])
        elif _steuer(c):
            teile.append(f"\\u{ord(c):04x}")
        else:
            teile.append(c)
    teile.append('"')
    return "".join(teile)


def anzeige_text(text: str) -> str:
    teile = []
    for c in text:
        if c in _KURZ:
            teile.append(_KURZ[c])
        elif _steuer(c):
            teile.append(f"\\u{ord(c):04x}")
        else:
            teile.append(c)
    return "".join(teile)


def baue_block(name: str, port: int, zweck: str | None = None,
               pfad: str | None = None) -> str:
    zeilen = ["", "[[port]]", f"port = {port}", f"projekt = {toml_text(name)}"]
    if zweck is not None:
        zeilen.append(f"zweck = {toml_text(zweck)}")
    if pfad is not None:
        zeilen.append(f"pfad = {toml_text(pfad)}")
    return "\n".join(zeilen) + "\n"


def _pruefe(alt, name, port, zweck, pfad) -> None:
    if not name.strip():
        raise EintragFehler("Name darf nicht leer sein")
    if isinstance(port, bool) or not isinstance(port, int):
        raise EintragFehler("Port muss eine ganze Zahl sein")
    if not 1 <= port <= 65535:
        raise EintragFehler(f"Port {port} liegt außerhalb von 1-65535")
    if zweck is not None and not isinstance(zweck, str):
        raise EintragFehler("Zweck muss ein Text sein")
    if pfad is not None and (not isinstance(pfad, str) or not pfad.strip()):
        raise EintragFehler("Pfad muss ein nicht leerer Text sein")
    if any(e.projekt == name for e in alt):
        raise EintragFehler(f"Name '{name}' gibt es schon")
    treffer = list(dict.fromkeys(e.projekt for e in alt if e.port == port))
    if treffer:
        raise EintragFehler(
            f"Port {port} ist schon vergeben: {', '.join(treffer)}"
        )


def _entferne(tmp) -> None:
    if tmp is None:
        return
    try:
        os.remove(tmp)
    except OSError:
        pass


def trage_ein(datei, name: str, port: int, zweck: str | None = None,
              pfad: str | None = None) -> Eintrag:
    alt = lade(datei)
    _pruefe(alt, name, port, zweck, pfad)
    neu = Eintrag(port, name, zweck or "", pfad)
    ordner = os.path.dirname(os.path.abspath(datei))
    tmp = None
    try:
        try:
            roh = Path(datei).read_bytes()
            if roh and not roh.endswith(b"\n"):
                roh += b"\n"
            roh += baue_block(name, port, zweck, pfad).encode("utf-8")
            fd, tmp = tempfile.mkstemp(dir=ordner)
            try:
                f = os.fdopen(fd, "wb")
            except BaseException:
                os.close(fd)
                raise
            with f:
                f.write(roh)
            try:
                ok = lade(tmp) == alt + [neu]
            except Exception:
                ok = False
            if not ok:
                raise EintragFehler(
                    "Liste kann nicht durch einen [[port]]-Block erweitert werden"
                )
            os.replace(tmp, datei)
            tmp = None
        except OSError as e:
            raise EintragFehler(f"Datei nicht schreibbar: {datei}: {e}") from None
    finally:
        _entferne(tmp)
    return neu
