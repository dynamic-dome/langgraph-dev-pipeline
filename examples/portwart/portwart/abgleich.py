"""Abgleich der Portliste mit den lauschenden Ports."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Abgleich:
    belegt: list[int]
    frei: list[int]
    unbekannt: list[int]


def abgleich(eintraege, lauschend, bereich=(1024, 49151)) -> Abgleich:
    eingetragen = {e.port for e in eintraege}
    lauschend = set(lauschend)
    unten, oben = bereich
    return Abgleich(
        belegt=sorted(eingetragen & lauschend),
        frei=sorted(eingetragen - lauschend),
        unbekannt=sorted(p for p in lauschend - eingetragen if unten <= p <= oben),
    )
