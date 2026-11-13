import pytest

from entwicklung import steuerung

GUELTIG = [
    ("fragen", None, "nur .py", None, {"antwort": "nur .py"}),
    ("fragen", "abbrechen", None, None, {"entscheidung": "abbrechen"}),
    ("spec_freigabe", "freigeben", None, None, {"entscheidung": "freigeben"}),
    ("spec_freigabe", "abbrechen", None, None, {"entscheidung": "abbrechen"}),
    ("spec_freigabe", "aendern", None, " genauer ", {"entscheidung": "aendern", "hinweis": "genauer"}),
    ("spec_freigabe", "tests_nachbessern", None, "x", {"entscheidung": "tests_nachbessern", "hinweis": "x"}),
    ("plan_freigabe", "freigeben", None, None, {"entscheidung": "freigeben"}),
    ("plan_freigabe", "aendern", None, "kleiner", {"entscheidung": "aendern", "hinweis": "kleiner"}),
    ("eskalation", "weiter", None, None, {"entscheidung": "weiter"}),
    ("eskalation", "annehmen", None, None, {"entscheidung": "annehmen"}),
]
UNGUELTIG = [
    ("fragen", None, "", None), ("fragen", None, "  ", None), ("fragen", "freigeben", None, None),
    ("fragen", None, "x", "y"), ("fragen", None, None, None),
    ("spec_freigabe", "aendern", None, None), ("spec_freigabe", "aendern", None, " "),
    ("spec_freigabe", "freigeben", "x", None), ("spec_freigabe", "freigeben", None, "x"),
    ("spec_freigabe", "weiter", None, None),
    ("plan_freigabe", "tests_nachbessern", None, "x"), ("plan_freigabe", None, "x", None),
    ("eskalation", "freigeben", None, None), ("eskalation", "weiter", None, "x"), ("eskalation", None, "x", None),
    ("unbekannt", "freigeben", None, None),
]


@pytest.mark.parametrize("punkt,entscheidung,antwort,hinweis,erwartet", GUELTIG)
def test_antwort_fuer_gueltig(punkt, entscheidung, antwort, hinweis, erwartet):
    assert steuerung.antwort_fuer(punkt, entscheidung, antwort, hinweis) == erwartet


@pytest.mark.parametrize("punkt,entscheidung,antwort,hinweis", UNGUELTIG)
def test_antwort_fuer_ungueltig(punkt, entscheidung, antwort, hinweis):
    assert steuerung.antwort_fuer(punkt, entscheidung, antwort, hinweis) is None


def test_erlaubt_kurz_fuer_jeden_haltepunkt():
    from entwicklung.speicher import WARTEPUNKTE
    assert set(steuerung.ERLAUBT_KURZ) == set(WARTEPUNKTE)
    assert steuerung.ERLAUBT_KURZ["spec_freigabe"] == ["freigeben", "aendern", "tests_nachbessern", "abbrechen"]
    assert steuerung.ERLAUBT_KURZ["fragen"] == ["antwort", "abbrechen"]


def test_antwort_fuer_begruendung():
    assert steuerung.antwort_fuer("spec_freigabe", "freigeben", None, None, " geprüft ") == {
        "entscheidung": "freigeben", "begruendung": "geprüft"}
    assert steuerung.antwort_fuer("spec_freigabe", "freigeben", None, None, "  ") == {"entscheidung": "freigeben"}
    assert steuerung.antwort_fuer("eskalation", "annehmen", None, None, "ok") == {
        "entscheidung": "annehmen", "begruendung": "ok"}


@pytest.mark.parametrize("antwort,einwaende,sperrt", [
    ({"entscheidung": "freigeben"}, ["E"], True),
    ({"entscheidung": "freigeben", "begruendung": "  "}, ["E"], True),
    ({"entscheidung": "freigeben", "begruendung": "geprüft"}, ["E"], False),
    ({"entscheidung": "annehmen"}, ["E"], True),
    ({"entscheidung": "freigeben"}, [], False),
    ({"entscheidung": "aendern", "hinweis": "x"}, ["E"], False),
    ({"entscheidung": "abbrechen"}, ["E"], False),
    ({"antwort": "Text"}, ["E"], False),
])
def test_einwand_fehlt(antwort, einwaende, sperrt):
    grund = steuerung.einwand_fehlt("spec_freigabe", antwort, einwaende)
    assert (grund is not None) == sperrt
    if sperrt:
        assert "E" in grund and "begruendung" in grund.lower()



def test_antwort_fuer_komplexitaet():
    assert steuerung.antwort_fuer("plan_freigabe", "freigeben", None, None, None, "schwer") == {
        "entscheidung": "freigeben", "komplexitaet": "schwer"}
    assert steuerung.antwort_fuer("plan_freigabe", "freigeben", None, None, None, None) == {"entscheidung": "freigeben"}
    assert steuerung.antwort_fuer("spec_freigabe", "freigeben", None, None, None, "schwer") is None
    assert steuerung.antwort_fuer("plan_freigabe", "aendern", None, "x", None, "schwer") is None
    assert steuerung.antwort_fuer("plan_freigabe", "freigeben", None, None, None, "extrem") is None



def test_antwort_fuer_budget():
    for punkt in ("budget_spec", "budget_plan", "budget_umsetzung"):
        assert steuerung.antwort_fuer(punkt, "mehr", None, None) == {"entscheidung": "mehr"}
        assert steuerung.antwort_fuer(punkt, "abbrechen", None, None) == {"entscheidung": "abbrechen"}
        assert steuerung.antwort_fuer(punkt, "freigeben", None, None) is None
        assert steuerung.ERLAUBT_KURZ[punkt] == ["mehr", "abbrechen"]


def test_abschluss_freigabe_antworten():
    """Stufe 7: mergen/nicht_mergen ohne Text; mergen ist eine Durchlass-Entscheidung (Begründung bei Einwand)."""
    from entwicklung.steuerung import DURCHLASS, ERLAUBT_KURZ, antwort_fuer, einwand_fehlt
    assert ERLAUBT_KURZ["abschluss_freigabe"] == ["mergen", "nicht_mergen"]
    assert antwort_fuer("abschluss_freigabe", "mergen", None, None) == {"entscheidung": "mergen"}
    assert antwort_fuer("abschluss_freigabe", "nicht_mergen", None, None) == {"entscheidung": "nicht_mergen"}
    assert antwort_fuer("abschluss_freigabe", "mergen", None, "Hinweis") is None
    assert antwort_fuer("abschluss_freigabe", "freigeben", None, None) is None
    assert "mergen" in DURCHLASS
    assert einwand_fehlt("abschluss_freigabe", {"entscheidung": "mergen"}, ["Tür einseitig: x"])
    assert einwand_fehlt("abschluss_freigabe", {"entscheidung": "nicht_mergen"}, ["Tür einseitig: x"]) is None
    assert antwort_fuer("abschluss_freigabe", "mergen", None, None, begruendung="geprüft") == {
        "entscheidung": "mergen", "begruendung": "geprüft"}
