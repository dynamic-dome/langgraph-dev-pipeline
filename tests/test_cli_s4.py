import json
from pathlib import Path

from entwicklung import cli, pfade, speicher
from tests.test_graph_s1 import _abh, umgebung  # noqa: F401  (Fixture)
from tests.test_graph_s2 import _codex, _pruefer
from tests.test_graph_s3 import FALSCH, RICHTIG, Implementierer
from tests.test_graph_s4 import FRAGEN, KLAR, Planer, s4  # noqa: F401  (s4 ist eine Fixture)


def _abh4(aufgaben, planer=None, impl=None):
    planer = planer or Planer()
    return _abh(aufgaben, implementierer=impl or Implementierer(RICHTIG), pruefer=_pruefer(), codex=_codex(),
                planer=planer, planer_codex=planer.codex)


def _lauf(repo, abh, aufgabe="M2", *extra):
    return cli.main(["lauf", "--repo", str(repo), "--aufgabe", aufgabe, *extra], abh=abh)


def _fort(abh, *args):
    return cli.main(["fortsetzen", *args], abh=abh)


def _wartepunkt(abh):
    cp = speicher.oeffne_checkpointer()
    graph_fuer = cli._graph_fuer(cp, abh)
    tid = speicher.wartende_laeufe(cp, graph_fuer)[0]
    return speicher.wartepunkt(graph_fuer(speicher.stufe_des_laufs(cp, tid)), tid)


def test_lauf_s4_haelt_an_fragen_exit_3(s4, capsys):
    repo, aufgaben = s4
    abh = _abh4(aufgaben, Planer(klaeren=[FRAGEN, KLAR]))
    assert _lauf(repo, abh) == 3
    aus = capsys.readouterr().out
    assert "1. Auch negative Zahlen?" in aus and 'fortsetzen --antwort "' in aus
    assert _wartepunkt(abh) == "fragen"


def test_fortsetzen_antwort_dann_freigabe(s4, capsys):
    repo, aufgaben = s4
    abh = _abh4(aufgaben, Planer(klaeren=[FRAGEN, KLAR]))
    _lauf(repo, abh)
    capsys.readouterr()
    assert _fort(abh, "--antwort", "ja, auch negative") == 3
    aus = capsys.readouterr().out
    assert "spec.md" in aus and "1 von 1 rot gegen main" in aus and "test_plus_gross" in aus
    assert "--entscheidung freigeben" in aus and '--entscheidung aendern --hinweis "' in aus
    assert '--entscheidung tests_nachbessern --hinweis "' in aus
    assert _fort(abh, "--entscheidung", "freigeben") == 3  # ab 4b: Plan-Freigabe
    assert _fort(abh, "--entscheidung", "freigeben") == 3  # ab Stufe 7: Halt an der Abschluss-Freigabe
    assert _fort(abh, "--entscheidung", "mergen") == 0
    assert "🟢 gruen" in capsys.readouterr().out


def test_fortsetzen_falsche_angabe_fuer_wartepunkt(s4, capsys):
    repo, aufgaben = s4
    abh = _abh4(aufgaben, Planer(klaeren=[FRAGEN, KLAR]))
    _lauf(repo, abh)
    for falsch in (["--entscheidung", "freigeben"], ["--antwort", ""], ["--antwort", "x", "--hinweis", "y"]):
        capsys.readouterr()
        assert _fort(abh, *falsch) == 3  # Codex F8: der Lauf wartet weiter
        assert "--antwort" in capsys.readouterr().out and _wartepunkt(abh) == "fragen"
    _fort(abh, "--antwort", "ja")
    for falsch in (["--antwort", "x"], ["--entscheidung", "aendern"], ["--entscheidung", "weiter"]):
        capsys.readouterr()
        assert _fort(abh, *falsch) == 3
        assert "--entscheidung freigeben" in capsys.readouterr().out and _wartepunkt(abh) == "spec_freigabe"


def test_fortsetzen_ohne_angabe(s4, capsys):
    repo, aufgaben = s4
    abh = _abh4(aufgaben, Planer(klaeren=[FRAGEN, KLAR]))
    _lauf(repo, abh)
    capsys.readouterr()
    assert _fort(abh) == 3 and "--antwort" in capsys.readouterr().out


def test_fortsetzen_stufe_3_lauf_weiter_moeglich(s4, capsys):
    repo, aufgaben = s4
    abh = _abh4(aufgaben, impl=Implementierer(FALSCH))
    assert _lauf(repo, abh, "M1", "--stufe", "3") == 3
    assert _wartepunkt(abh) == "eskalation"
    assert _fort(abh, "--entscheidung", "annehmen") == 1
    assert "🟡 angenommen" in capsys.readouterr().out


def test_bericht_s4_abschnitte(s4):
    repo, aufgaben = s4
    abh = _abh4(aufgaben, Planer(klaeren=[FRAGEN, KLAR]))
    _lauf(repo, abh)
    _fort(abh, "--antwort", "ja, auch negative")
    _fort(abh, "--entscheidung", "aendern", "--hinweis", "bitte genauer")
    assert _fort(abh, "--entscheidung", "freigeben") == 3
    assert _fort(abh, "--entscheidung", "freigeben") == 3  # ab Stufe 7: Halt an der Abschluss-Freigabe
    assert _fort(abh, "--entscheidung", "mergen") == 0
    bericht = next(p for p in pfade.berichte_dir().glob("*.md"))
    text = bericht.read_text(encoding="utf-8")
    for abschnitt in ("## Klärung", "ja, auch negative", "## Spec", "Spec-Runden: 2", "nur ganze Zahlen",
                      "## Akzeptanztests aus der Spec", "1 von 1 rot gegen main", "## Spec-Prüfung",
                      "Freigabe: freigeben", "## Plan", "plan.md", "Plan-Freigabe: freigeben"):
        assert abschnitt in text, abschnitt
    daten = json.loads(bericht.with_suffix(".json").read_text(encoding="utf-8"))
    assert daten["spec_runde"] == 1 and daten["akz_probe"]["erwartet"] == 1 and daten["freigabe"] == "freigeben"
    assert daten["plan_freigabe"] == "freigeben" and daten["plan"].startswith("# Plan M2")


def test_akzeptanz_fehler_symbol(s4, capsys):
    repo, aufgaben = s4
    kaputt = {"dateien": [{"name": "falsch.py", "inhalt": "x"}]}
    abh = _abh4(aufgaben, Planer(akzeptanz_schreiben=[kaputt]))
    assert _lauf(repo, abh) == 1
    aus = capsys.readouterr().out
    assert "⚠ akzeptanz_fehler" in aus and "Dateiname" in aus


def test_live_zeigt_planung(s4, capsys):
    """Echter Lauf 20261020-120157: --live stürzte an pruefen_spec_* ab (Zweig für pruefen_* griff zuerst)."""
    repo, aufgaben = s4
    abh = _abh4(aufgaben, Planer(klaeren=[FRAGEN, KLAR]))
    assert _lauf(repo, abh, "M2", "--live") == 3
    assert _fort(abh, "--antwort", "ja", "--live") == 3
    aus = capsys.readouterr().out
    for teil in ("✓ klaeren", "1 Fragen", "✓ fragen", "Antwort erhalten", "✓ spec_schreiben", "1 Module",
                 "✓ akzeptanz_schreiben", "1 von 1 rot gegen main", "✓ pruefen_spec_claude", "PASS · 0 Punkte",
                 "✓ pruefen_spec_codex", "✓ spec_pruefung_sammeln", "⏸ wartet auf dich"):
        assert teil in aus, teil
    assert _fort(abh, "--entscheidung", "freigeben", "--live") == 3
    aus = capsys.readouterr().out
    for teil in ("Freigabe: freigeben", "✓ plan_schreiben", "Plan · 2 Dateien · 0 Gründe", "✓ plan_pruefen",
                 "codex: PASS · 0 Punkte", "⏸ wartet auf dich", "Plan:", "plan.md"):
        assert teil in aus, teil
    assert _fort(abh, "--entscheidung", "freigeben", "--live") == 3  # ab Stufe 7: Halt an der Abschluss-Freigabe
    assert _fort(abh, "--entscheidung", "mergen", "--live") == 0
    aus = capsys.readouterr().out
    assert "Plan-Freigabe: freigeben" in aus and "Spec und Plan sind jetzt die Aufgabe" in aus
    assert "✓ pruefen_codex" in aus



def _bis_plan_freigabe(repo, abh):
    _lauf(repo, abh)
    assert _fort(abh, "--entscheidung", "freigeben") == 3
    assert _wartepunkt(abh) == "plan_freigabe"


def test_fortsetzen_bis_plan_freigabe_und_umsetzung(s4, capsys):
    repo, aufgaben = s4
    abh = _abh4(aufgaben)
    _lauf(repo, abh)
    capsys.readouterr()
    assert _fort(abh, "--entscheidung", "freigeben") == 3
    aus = capsys.readouterr().out
    assert "Freigabe des Plans" in aus and "plan.md" in aus and "mathe.py, tests/test_mathe.py" in aus
    assert '--entscheidung aendern --hinweis "' in aus and "tests_nachbessern" not in aus.split("Weiter mit")[1]
    assert _fort(abh, "--entscheidung", "freigeben") == 3  # ab Stufe 7: Halt an der Abschluss-Freigabe
    assert _fort(abh, "--entscheidung", "mergen") == 0


def test_tests_nachbessern_ueber_cli(s4, capsys):
    repo, aufgaben = s4
    abh = _abh4(aufgaben)
    _lauf(repo, abh)
    assert _fort(abh, "--entscheidung", "tests_nachbessern") == 3
    assert "--hinweis" in capsys.readouterr().out and _wartepunkt(abh) == "spec_freigabe"
    assert _fort(abh, "--entscheidung", "tests_nachbessern", "--hinweis", "negative Zahlen") == 3
    assert _wartepunkt(abh) == "spec_freigabe"
    assert "negative Zahlen" in abh.planer.prompts["akzeptanz_schreiben"][1]


def test_falsche_angabe_an_plan_freigabe(s4, capsys):
    repo, aufgaben = s4
    abh = _abh4(aufgaben)
    _bis_plan_freigabe(repo, abh)
    for falsch in (["--entscheidung", "tests_nachbessern", "--hinweis", "x"], ["--entscheidung", "aendern"],
                   ["--antwort", "x"], ["--entscheidung", "weiter"]):
        capsys.readouterr()
        assert _fort(abh, *falsch) == 3
        assert "plan_freigabe" in capsys.readouterr().out and _wartepunkt(abh) == "plan_freigabe"
    assert _fort(abh, "--entscheidung", "aendern", "--hinweis", "kleinere Schritte") == 3
    assert "kleinere Schritte" in abh.planer.prompts["plan_schreiben"][1]



def test_cli_fortsetzen_braucht_begruendung(s4, capsys):
    from tests.test_graph_s4 import CODEX_MAJOR, EINWAND
    repo, aufgaben = s4
    abh = _abh4(aufgaben, Planer(spec_codex=[CODEX_MAJOR]))
    assert _lauf(repo, abh) == 3
    assert EINWAND in capsys.readouterr().out
    assert _fort(abh, "--entscheidung", "freigeben") == 3
    aus = capsys.readouterr().out
    assert EINWAND in aus and "--begruendung" in aus and _wartepunkt(abh) == "spec_freigabe"
    assert _fort(abh, "--entscheidung", "freigeben", "--begruendung", "Satz gestrichen") == 3
    assert _wartepunkt(abh) == "plan_freigabe"
    assert _fort(abh, "--entscheidung", "freigeben") == 3  # ab Stufe 7: Halt an der Abschluss-Freigabe
    assert _fort(abh, "--entscheidung", "mergen") == 0
    bericht = next(p for p in pfade.berichte_dir().glob("*.md")).read_text(encoding="utf-8")
    teil = bericht.split("## Freigaben trotz Einwand")[1]
    assert "spec_freigabe" in teil and EINWAND in teil and "Satz gestrichen" in teil


def test_bericht_ohne_einwand_kein_abschnitt():
    from entwicklung.bericht import _einwand_abschnitt
    assert _einwand_abschnitt({}) == [] and _einwand_abschnitt({"einwand_freigaben": None}) == []



def test_cli_auto_und_fortsetzen_komplexitaet(s4, capsys):
    from tests.test_graph_s4 import ImplMitStufe
    repo, aufgaben = s4
    impl = ImplMitStufe(RICHTIG)
    abh = _abh4(aufgaben, impl=impl)
    _lauf(repo, abh)
    assert _fort(abh, "--entscheidung", "freigeben") == 3
    aus = capsys.readouterr().out
    assert "Komplexität: mittel" in aus and "--komplexitaet" in aus
    assert _fort(abh, "--entscheidung", "freigeben", "--komplexitaet", "schwer") == 3  # ab Stufe 7: Halt an der Abschluss-Freigabe
    assert _fort(abh, "--entscheidung", "mergen") == 0
    assert impl.stufen == [("opus", "high", 900)]
    bericht = next(p for p in pfade.berichte_dir().glob("*.md")).read_text(encoding="utf-8")
    teil = bericht.split("## Modellstufen")[1]
    assert "Komplexität: schwer" in teil and "an der Plan-Freigabe geändert" in teil and "implementierer: opus · high" in teil



def test_cli_budget(s4, capsys):
    repo, aufgaben = s4
    abh = _abh4(aufgaben)
    assert _lauf(repo, abh, "M2", "--budget", "7") == 3
    assert _fort(abh, "--entscheidung", "freigeben") == 3
    assert _fort(abh, "--entscheidung", "freigeben") == 3
    aus = capsys.readouterr().out
    assert "Kostenrahmen erreicht" in aus and "7 von 7" in aus and "--entscheidung mehr" in aus
    assert _fort(abh, "--entscheidung", "mehr") == 3  # ab Stufe 7: Halt an der Abschluss-Freigabe
    assert _fort(abh, "--entscheidung", "mergen") == 0
    bericht = next(p for p in pfade.berichte_dir().glob("*.md")).read_text(encoding="utf-8")
    assert "Agentenaufrufe: 12 von 27" in bericht  # ab Stufe 7 mit Gesamtreview and "Berater: 0× Fable, 0× Astra" in bericht



def test_bericht_json_felder_6b():
    """Codex 6b-1 F-004 und 6b-2: Einwände, Aufrufe, Rahmen und Komplexität stehen auch im JSON-Bericht."""
    from entwicklung.bericht import JSON_FELDER
    for feld in ("einwand_freigaben", "aufrufe", "budget", "komplexitaet", "komplexitaet_vorschlag",
                 "komplexitaet_claude", "komplexitaet_codex"):
        assert feld in JSON_FELDER, feld


def test_cli_zeigt_einordnung_und_verlauf(s4, capsys):
    """6c: ab der Nachprüfung zwei Gruppen statt einer Liste, dazu der Verlauf je Fassung; im Bericht ebenso."""
    from tests.test_graph_s4 import PRUEF_OK, PRUEF_PUNKT
    from tests.test_graph_s6c import NACH_MIX, NACH_OK
    repo, aufgaben = s4
    abh = _abh4(aufgaben, Planer(spec_pruefer=[PRUEF_PUNKT, NACH_MIX], spec_codex=[PRUEF_OK, NACH_OK]))
    assert _lauf(repo, abh) == 3
    erst = capsys.readouterr().out
    assert "[claude, major] Negative Zahlen fehlen" in erst and "Lösen eine neue Runde aus" not in erst
    assert _fort(abh, "--entscheidung", "aendern", "--hinweis", "auch negative") == 3
    aus = capsys.readouterr().out
    teil_aus, teil_liste = aus.split("Lösen eine neue Runde aus:")[1].split("Liste für dich (keine neue Runde nötig):")
    assert "[claude, major, aenderung] Neu kaputt" in teil_aus and "Stand schon so" not in teil_aus
    assert "[claude, major, sonstiges] Stand schon so" in teil_liste
    assert "[claude, major, alt geloest] Negative Zahlen fehlen" in teil_liste
    assert "Fassung 1:" in aus and "Fassung 2:" in aus and "1 auslösend" in aus
    assert _fort(abh, "--entscheidung", "abbrechen") == 1
    bericht = next(p for p in pfade.berichte_dir().glob("*.md")).read_text(encoding="utf-8")
    assert "## Spec-Verlauf" in bericht and "- Fassung 2:" in bericht
