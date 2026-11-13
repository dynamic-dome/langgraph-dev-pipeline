import threading

import pytest

from entwicklung import speicher
from entwicklung.leitstand.ausfuehrer import Ausfuehrer, Belegt, WartetNicht
from tests.test_graph_s1 import _abh, umgebung  # noqa: F401  (Fixture)
from tests.test_graph_s2 import _codex, _pruefer
from tests.test_graph_s3 import RICHTIG, Implementierer
from tests.test_graph_s4 import FRAGEN, KLAR, Planer, s4  # noqa: F401  (s4 Fixture)


def _ausfuehrer(aufgaben, planer=None, **kw):
    planer = planer or Planer()
    abh = _abh(aufgaben, implementierer=Implementierer(RICHTIG), pruefer=_pruefer(), codex=_codex(),
               planer=planer, planer_codex=planer.codex, **kw)
    return Ausfuehrer(abh, speicher.oeffne_checkpointer())


def _punkt(a, tid):
    return speicher.wartepunkt(a.graph_fuer(speicher.stufe_des_laufs(a.cp, tid)), tid)


def test_starten_bis_fragen(s4):
    repo, aufgaben = s4
    a = _ausfuehrer(aufgaben, Planer(klaeren=[FRAGEN, KLAR]))
    tid = a.starte(str(repo), "M2")
    assert tid == "lauf-20261019-120000"
    a.warte(tid, 120)
    assert a.zustand(tid) == {"laeuft": False, "fehler": None}
    assert _punkt(a, tid) == "fragen" and speicher.stufe_des_laufs(a.cp, tid) == 4


def test_fortsetzen_bis_spec_freigabe(s4):
    repo, aufgaben = s4
    a = _ausfuehrer(aufgaben, Planer(klaeren=[FRAGEN, KLAR]))
    tid = a.starte(str(repo), "M2")
    a.warte(tid, 120)
    a.fortsetzen(tid, {"antwort": "ja"})
    a.warte(tid, 120)
    assert _punkt(a, tid) == "spec_freigabe"


def test_doppeltes_fortsetzen_belegt(s4):
    repo, aufgaben = s4
    los, angekommen = threading.Event(), threading.Event()

    def blockieren(wt):
        angekommen.set()
        los.wait(60)
    a = _ausfuehrer(aufgaben, Planer(klaeren=[FRAGEN, KLAR], extra={"spec_schreiben": blockieren}))
    tid = a.starte(str(repo), "M2")
    a.warte(tid, 120)
    a.fortsetzen(tid, {"antwort": "ja"})
    assert angekommen.wait(60)
    assert a.zustand(tid)["laeuft"] is True
    with pytest.raises(Belegt):
        a.fortsetzen(tid, {"antwort": "nochmal"})
    los.set()
    a.warte(tid, 120)
    assert _punkt(a, tid) == "spec_freigabe"


def test_fortsetzen_ohne_wartepunkt(s4):
    repo, aufgaben = s4
    a = _ausfuehrer(aufgaben, Planer(klaeren=[FRAGEN]))
    with pytest.raises(WartetNicht):
        a.fortsetzen("lauf-gibt-es-nicht", {"antwort": "x"})
    tid = a.starte(str(repo), "M2")
    a.warte(tid, 120)
    a.fortsetzen(tid, {"entscheidung": "abbrechen"})
    a.warte(tid, 120)
    with pytest.raises(WartetNicht):
        a.fortsetzen(tid, {"antwort": "x"})


def test_fehler_im_thread_wird_zustand(s4):
    repo, aufgaben = s4

    def kaputt(*args, **kwargs):
        raise RuntimeError("Testlauf kaputt")
    a = _ausfuehrer(aufgaben, tests=kaputt)
    tid = a.starte(str(repo), "M2")
    a.warte(tid, 120)
    z = a.zustand(tid)
    assert z["laeuft"] is False and "RuntimeError" in z["fehler"] and "Testlauf kaputt" in z["fehler"]
    zweiter = a.starte(str(repo), "M2")  # der Ausführer arbeitet weiter
    assert zweiter != tid
    a.warte(zweiter, 120)


def test_fortsetzen_nur_fuer_erwarteten_stand(s4):
    """Codex 6b-1 F-001: Eine verspätete Antwort auf die Spec-Freigabe darf nicht die Plan-Freigabe treffen. Der
    erwartete Stand wird unter derselben Sperre geprüft, unter der die Fortsetzung startet."""
    from entwicklung.leitstand.ausfuehrer import StandGeaendert, _stand
    repo, aufgaben = s4
    a = _ausfuehrer(aufgaben, Planer(klaeren=[KLAR]))
    tid = a.starte(str(repo), "M2")
    a.warte(tid, 120)
    _, punkt, stand = _stand(a.graph_fuer(4), tid)
    assert punkt == "spec_freigabe"
    a.fortsetzen(tid, {"entscheidung": "freigeben"}, erwartet=(punkt, stand))
    a.warte(tid, 120)
    assert _punkt(a, tid) == "plan_freigabe"
    with pytest.raises(StandGeaendert):
        a.fortsetzen(tid, {"entscheidung": "freigeben"}, erwartet=(punkt, stand))
    a.warte(tid, 5)
    assert _punkt(a, tid) == "plan_freigabe"
