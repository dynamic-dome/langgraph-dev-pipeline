"""Austragen eines [[port]]-Blocks aus der Portliste ports.toml."""
from __future__ import annotations

import os
import re
import tempfile
import tomllib
from pathlib import Path

from portwart.liste import Eintrag, lade

_VERKLEINERN = "Liste kann nicht durch Entfernen eines [[port]]-Blocks verkleinert werden"
_KOPF = re.compile(rb"[ \t]*\[\[[ \t]*port[ \t]*\]\][ \t]*(#.*)?")
_LEERRAUM = b" \t"
# Schlüsselteil: bare, basic oder literal
_TEIL = rb"""(?:[A-Za-z0-9_-]+|"(?:[^"\\\n]|\\.)*"|'[^'\n]*')"""
# Schlüsselpfad: unquotiertes port, dahinter mindestens ein weiterer Teil
_PFAD = rb"[ \t]*port(?:[ \t]*\.[ \t]*" + _TEIL + rb")+[ \t]*"
_UNTER = re.compile(
    rb"[ \t]*(?:\[\[" + _PFAD + rb"\]\]|\[" + _PFAD + rb"\])[ \t]*(?:#.*)?"
)


class AustragFehler(ValueError):
    """Der Eintrag wurde abgelehnt oder konnte nicht entfernt werden."""


def _zeilen(roh: bytes) -> list[bytes]:
    return re.findall(rb"[^\n]*\n|[^\n]+", roh)


def _inhalt(zeile: bytes) -> bytes:
    if zeile.endswith(b"\r\n"):
        return zeile[:-2]
    if zeile.endswith(b"\n"):
        return zeile[:-1]
    return zeile


def _ende_mehrzeilig(text: bytes, i: int, delim: bytes) -> int | None:
    """Position hinter dem schließenden delim ab i, sonst None."""
    q = delim[:1]
    while i < len(text):
        c = text[i:i + 1]
        if c == b"\\" and delim == b'"""':
            i += 2
            continue
        if c == q and text[i:i + 3] == delim:
            n = 3
            while text[i + n:i + n + 1] == q:
                n += 1
            return i + n
        i += 1
    return None


def _scanne(text: bytes, delim, tiefe: int):
    """Zustand (delim, tiefe) nach der Zeile text bestimmen."""
    i = 0
    if delim is not None:
        ende = _ende_mehrzeilig(text, 0, delim)
        if ende is None:
            return delim, tiefe
        delim, i = None, ende
    while i < len(text):
        c = text[i:i + 1]
        if c == b"#":
            break
        if c in (b'"', b"'"):
            if text[i:i + 3] == c * 3:
                ende = _ende_mehrzeilig(text, i + 3, c * 3)
                if ende is None:
                    return c * 3, tiefe
                i = ende
                continue
            i += 1
            while i < len(text):
                d = text[i:i + 1]
                if d == b"\\" and c == b'"':
                    i += 2
                    continue
                i += 1
                if d == c:
                    break
            continue
        if c == b"[":
            tiefe += 1
        elif c == b"]":
            tiefe = max(0, tiefe - 1)
        i += 1
    return None, tiefe


def _klassifiziere(zeilen: list[bytes]) -> list[str]:
    """Art je Zeile: kopf, tabelle, leer, kommentar, string oder wert."""
    arten = []
    delim, tiefe = None, 0
    for zeile in zeilen:
        text = _inhalt(zeile)
        kern = text.lstrip(_LEERRAUM)
        if delim is not None:
            art = "string"
        elif not kern:
            art = "leer"
        elif kern.startswith(b"#"):
            art = "kommentar"
        elif tiefe == 0 and kern.startswith(b"["):
            art = "kopf" if _KOPF.fullmatch(text) else "tabelle"
        else:
            art = "wert"
        if art in ("string", "wert"):
            delim, tiefe = _scanne(text, delim, tiefe)
        arten.append(art)
    return arten


def _entferne(tmp) -> None:
    if tmp is None:
        return
    try:
        os.remove(tmp)
    except OSError:
        pass


def _ist_untertabelle(text: bytes) -> bool:
    """Tabellenzeile [port.…] oder [[port.…]] mit unquotiertem Erstteil port."""
    return _UNTER.fullmatch(text) is not None


def _mit_leerzeile(weg: set[int], arten: list[str], k: int) -> None:
    weg.add(k)
    if k > 0 and arten[k - 1] == "leer":
        weg.add(k - 1)


def _ohne_block(zeilen: list[bytes], arten: list[str], i: int) -> bytes:
    koepfe = [k for k, art in enumerate(arten) if art == "kopf"]
    start = koepfe[i]
    weg: set[int] = set()
    _mit_leerzeile(weg, arten, start)
    k = start + 1
    while k < len(zeilen) and arten[k] != "kopf":
        if arten[k] == "tabelle":
            if not _ist_untertabelle(_inhalt(zeilen[k])):
                break
            _mit_leerzeile(weg, arten, k)
        elif arten[k] in ("wert", "string"):
            weg.add(k)
        k += 1
    return b"".join(z for k, z in enumerate(zeilen) if k not in weg)


def _gleich(a, b) -> bool:
    """Strenger Vergleich geparster TOML-Daten (Typen, NaN, -0.0).

    Iterativ über einen Stapel, damit beliebig tiefe Schlüsselpfade
    keine Rekursionsgrenze erreichen.
    """
    stapel = [(a, b)]
    while stapel:
        x, y = stapel.pop()
        if type(x) is not type(y):
            return False
        if isinstance(x, dict):
            if x.keys() != y.keys():
                return False
            stapel.extend((x[k], y[k]) for k in x)
        elif isinstance(x, list):
            if len(x) != len(y):
                return False
            stapel.extend(zip(x, y))
        elif isinstance(x, float):
            if repr(x) != repr(y):
                return False
        elif x != y:
            return False
    return True


def _daten_gleich(roh_alt: bytes, tmp, i: int) -> bool:
    """Daten der Tempdatei = alte Daten ohne den i-ten [[port]]-Eintrag."""
    alt = tomllib.loads(roh_alt.decode("utf-8"))
    neu = tomllib.loads(Path(tmp).read_bytes().decode("utf-8"))
    soll = alt.pop("port")
    if not isinstance(soll, list):
        return False
    soll = soll[:i] + soll[i + 1:]
    return _gleich(neu.pop("port", []), soll) and _gleich(neu, alt)


def trage_aus(datei, name: str) -> Eintrag:
    alt = lade(datei)
    treffer = [k for k, e in enumerate(alt) if e.projekt == name]
    if not treffer:
        raise AustragFehler(f"Name '{name}' nicht gefunden")
    if len(treffer) > 1:
        ports = dict.fromkeys(str(alt[k].port) for k in treffer)
        raise AustragFehler(
            f"Name '{name}' ist mehrfach eingetragen: Ports {', '.join(ports)}"
        )
    i = treffer[0]
    ordner = os.path.dirname(os.path.abspath(datei))
    tmp = None
    try:
        try:
            roh = Path(datei).read_bytes()
            zeilen = _zeilen(roh)
            arten = _klassifiziere(zeilen)
            if arten.count("kopf") != len(alt):
                raise AustragFehler(_VERKLEINERN)
            neu = _ohne_block(zeilen, arten, i)
            fd, tmp = tempfile.mkstemp(dir=ordner)
            try:
                f = os.fdopen(fd, "wb")
            except BaseException:
                os.close(fd)
                raise
            with f:
                f.write(neu)
            try:
                ok = (lade(tmp) == alt[:i] + alt[i + 1:]
                      and _daten_gleich(roh, tmp, i))
            except Exception:
                ok = False
            if not ok:
                raise AustragFehler(_VERKLEINERN)
            os.replace(tmp, datei)
            tmp = None
        except OSError as e:
            raise AustragFehler(f"Datei nicht schreibbar: {datei}: {e}") from None
    finally:
        _entferne(tmp)
    return alt[i]
