from pathlib import Path

import pytest

from entwicklung import berater
from entwicklung.strukturiert import passt

FRAGE_SPEC = {"art": "spec_freigabe", "spec_text": "# A5\n## Vertrag\ndrift [WURZEL]", "tests": ["test_a"],
              "tests_text": {"test_akzeptanz_a5.py": "def test_a():\n    assert 1\n"},
              "probe": {"erwartet": 35, "bestanden": 4}, "annahmen": ["pfad optional"],
              "pruefpunkte": [{"pruefer": "codex", "schwere": "major", "aussage": "Test liste/liste kaputt"}],
              "spec_runde": 0}
WERTE = {"aufgabe_id": "A5", "wunsch": "Pfad je Eintrag", "klaerung": [{"fragen": ["Feldname?"], "antwort": "pfad"}]}


def _rat(entscheidung, text="", **kw):
    return {"entscheidung": entscheidung, "text": text, "begruendung": "weil", "sicherheit": "hoch", "punkte": [],
            **kw}


def test_prompt_enthaelt_material_und_wissen():
    p = berater.berater_prompt("spec_freigabe", FRAGE_SPEC, WERTE)
    for teil in ("drift [WURZEL]", "def test_a", "Test liste/liste kaputt", "Pfad je Eintrag", "Feldname?",
                 "tests/_akzeptanz", "keine Prüfpunkte", "tests_nachbessern", "freigeben", "35"):
        assert teil in p, teil
    q = berater.berater_prompt("plan_freigabe", {"art": "plan_freigabe", "plan_text": "# Plan X", "dateien": ["a.py"],
                                                  "pruefpunkte": []}, WERTE)
    assert "# Plan X" in q and "a.py" in q and "tests_nachbessern" not in q.split("Erlaubte Entscheidungen")[1]


def test_prompt_kuerzt_lange_texte():
    lang = {**FRAGE_SPEC, "spec_text": "x" * 100_000}
    assert len(berater.berater_prompt("spec_freigabe", lang, WERTE)) < 60_000


@pytest.mark.parametrize("punkt,rat,erwartet", [
    ("fragen", _rat("antwort", "nur .py"), {"antwort": "nur .py"}),
    ("fragen", _rat("abbrechen"), {"entscheidung": "abbrechen"}),
    ("spec_freigabe", _rat("freigeben"), {"entscheidung": "freigeben"}),
    ("spec_freigabe", _rat("tests_nachbessern", "Test X reparieren"),
     {"entscheidung": "tests_nachbessern", "hinweis": "Test X reparieren"}),
    ("plan_freigabe", _rat("aendern", "kleiner"), {"entscheidung": "aendern", "hinweis": "kleiner"}),
    ("eskalation", _rat("annehmen"), {"entscheidung": "annehmen"}),
])
def test_rat_pruefen_gueltig_je_haltepunkt(punkt, rat, erwartet):
    assert berater.rat_pruefen(punkt, rat) == (erwartet, None)


@pytest.mark.parametrize("punkt,rat", [
    ("spec_freigabe", _rat("weiter")), ("spec_freigabe", _rat("aendern", "")), ("fragen", _rat("antwort", " ")),
    ("plan_freigabe", _rat("tests_nachbessern", "x")), ("eskalation", _rat("freigeben")),
])
def test_rat_pruefen_ungueltig(punkt, rat):
    antwort, grund = berater.rat_pruefen(punkt, rat)
    assert antwort is None and punkt in grund


class FakeFable:
    def __init__(self, rat, schreibt=False):
        self.rat, self.schreibt, self.aufrufe = rat, schreibt, []

    def __call__(self, name, prompt, cwd, schema, modell="sonnet", timeout=600, effort=None, runner=None):
        self.aufrufe.append({"name": name, "modell": modell, "timeout": timeout, "cwd": cwd, "prompt": prompt})
        if self.schreibt:
            (Path(cwd) / "notiz.txt").write_text("x", encoding="utf-8")
        return {"name": name, "ok": True, "daten": self.rat, "fehler": None, "dauer_s": 0.1}


class Abh:
    def __init__(self, fake):
        self.berater = fake


def test_hole_rat_nutzt_fable_und_liest_nur(tmp_path):
    fake = FakeFable(_rat("freigeben"))
    erg = berater.hole_rat(Abh(fake), "spec_freigabe", FRAGE_SPEC, WERTE, tmp_path, sauber=lambda: [])
    assert erg["ok"] and erg["antwort"] == {"entscheidung": "freigeben"} and erg["grund"] is None
    assert fake.aufrufe[0]["modell"] == "fable" and fake.aufrufe[0]["timeout"] == 900 and fake.aufrufe[0]["cwd"] == tmp_path
    schreiber = FakeFable(_rat("freigeben"), schreibt=True)
    erg = berater.hole_rat(Abh(schreiber), "spec_freigabe", FRAGE_SPEC, WERTE, tmp_path,
                           sauber=lambda: [p.name for p in tmp_path.iterdir()])
    assert erg["ok"] is False and "Grenzverletzung" in erg["fehler"] and erg["antwort"] is None


def test_hole_rat_nicht_verwertbar_und_fehler(tmp_path):
    erg = berater.hole_rat(Abh(FakeFable(_rat("weiter"))), "spec_freigabe", FRAGE_SPEC, WERTE, tmp_path, lambda: [])
    assert erg["ok"] is True and erg["antwort"] is None and "spec_freigabe" in erg["grund"]

    def kaputt(*a, **k):
        raise RuntimeError("Fable weg")
    erg = berater.hole_rat(Abh(kaputt), "spec_freigabe", FRAGE_SPEC, WERTE, tmp_path, lambda: [])
    assert erg["ok"] is False and "Fable weg" in erg["fehler"]


def test_rat_schema_streng():
    def streng(s):
        if s.get("type") == "object":
            assert s["additionalProperties"] is False and set(s["required"]) == set(s["properties"])
            for t in s["properties"].values():
                streng(t)
        if s.get("type") == "array":
            streng(s["items"])
    streng(berater.RAT_SCHEMA)
    assert passt(_rat("freigeben"), berater.RAT_SCHEMA)


def test_testsperre_gilt(tmp_path):
    from entwicklung import agenten
    from entwicklung.graph import Abhaengigkeiten
    with pytest.raises(agenten.EchterAgentImTest):
        berater.hole_rat(Abhaengigkeiten(), "spec_freigabe", FRAGE_SPEC, WERTE, tmp_path, lambda: [])



def test_plan_und_eskalation_sehen_spec_tests_plan():
    """Codex F-008: An der Plan-Freigabe braucht Fable Spec und Tests, an der Eskalation Spec und Plan."""
    werte = {**WERTE, "spec": "# Spec A5 Vertrag", "plan": "# Plan A5 Schritte",
             "akz_dateien": [{"name": "test_akzeptanz_a5.py", "inhalt": "def test_vertrag(): ..."}]}
    p = berater.berater_prompt("plan_freigabe", {"art": "plan_freigabe", "plan_text": "# Plan A5 Schritte",
                                                  "dateien": [], "pruefpunkte": []}, werte)
    assert "# Spec A5 Vertrag" in p and "def test_vertrag" in p and "# Plan A5 Schritte" in p
    e = berater.berater_prompt("eskalation", {"frage": "Wie weiter?", "tests": "1/2", "ausloesend": []}, werte)
    assert "# Spec A5 Vertrag" in e and "# Plan A5 Schritte" in e


# ---------------------------------------------------------------------------------------------- Astra (6b-1)
def _worktree(tmp_path):
    wt = tmp_path / "wt"
    (wt / "portwart").mkdir(parents=True)
    (wt / "portwart" / "drift.py").write_text("def drift():\n    return 'DRIFT-INHALT'\n", encoding="utf-8")
    (tmp_path / "draussen.py").write_text("GEHEIM", encoding="utf-8")
    return wt


def test_quelldateien_bettet_ein_und_bleibt_im_worktree(tmp_path):
    wt = _worktree(tmp_path)
    werte = {"plan_dateien": ["../draussen.py", str(tmp_path / "draussen.py"), "fehlt.py", "portwart"],
             "schnittstellen": [{"modul": "portwart.drift", "namen": ["drift"]},
                                {"modul": "portwart/drift.py", "namen": ["drift"]}]}
    q = berater.quelldateien(werte, {}, "plan_freigabe", wt)
    assert list(q) == ["portwart/drift.py"] and "DRIFT-INHALT" in q["portwart/drift.py"]


def test_quelldateien_reihenfolge_und_eskalation(tmp_path):
    wt = _worktree(tmp_path)
    (wt / "a.py").write_text("A", encoding="utf-8")
    (wt / "b.py").write_text("B", encoding="utf-8")
    werte = {"plan_dateien": ["b.py"], "geaenderte_dateien": ["a.py"],
             "schnittstellen": [{"modul": "portwart.drift", "namen": []}]}
    assert list(berater.quelldateien(werte, {"dateien": ["a.py"]}, "plan_freigabe", wt)) == ["a.py", "portwart/drift.py"]
    assert list(berater.quelldateien(werte, {}, "eskalation", wt)) == ["b.py", "a.py", "portwart/drift.py"]
    assert list(berater.quelldateien(werte, {}, "spec_freigabe", wt)) == ["portwart/drift.py"]


def test_quelldateien_kuerzt(tmp_path, monkeypatch):
    wt = _worktree(tmp_path)
    (wt / "gross.py").write_text("x" * 500, encoding="utf-8")
    monkeypatch.setattr(berater, "MAX_QUELLEN", 100)
    q = berater.quelldateien({"plan_dateien": ["gross.py", "portwart/drift.py"]}, {}, "eskalation", wt)
    assert sum(len(v) for v in q.values()) < 200 and "gekürzt" in q["gross.py"]


def test_astra_prompt_ohne_lesen_mit_quellen():
    p = berater.berater_prompt("spec_freigabe", FRAGE_SPEC, WERTE, quellen={"portwart/drift.py": "DRIFT-INHALT"})
    assert "DRIFT-INHALT" in p and "## Quelldateien (Worktree)" in p and "keine Dateien lesen" in p
    assert "im aktuellen Ordner lesen" not in p
    assert "im aktuellen Ordner lesen" in berater.berater_prompt("spec_freigabe", FRAGE_SPEC, WERTE)


def test_astra_prompt_ohne_passende_quellen():
    """An der Spec-Freigabe gibt es neue Module oft noch nicht: Astra soll das lesen, nicht einen leeren Verweis."""
    p = berater.berater_prompt("spec_freigabe", FRAGE_SPEC, WERTE, quellen={})
    assert "## Quelldateien (Worktree)" in p and "keine passenden Dateien" in p


def test_wissen_spec_widerspruch_und_codex_major():
    assert "Ein Widerspruch in der Spec ist nie harmlos" in berater.WISSEN
    assert "nur mit Gegenbeleg aus dem Code herab" in berater.WISSEN


class FakeAstra:
    def __init__(self, rat):
        self.rat, self.aufrufe = rat, []

    def __call__(self, name, prompt, cwd, schema, timeout=900, effort=None, runner=None):
        self.aufrufe.append({"name": name, "timeout": timeout, "prompt": prompt, "cwd": cwd})
        return {"name": name, "ok": True, "daten": self.rat, "fehler": None, "dauer_s": 0.1}


class AbhBeide:
    def __init__(self, fable=None, astra=None):
        self.berater, self.berater_astra = fable, astra


def test_hole_rat_astra(tmp_path):
    wt = _worktree(tmp_path)
    astra = FakeAstra(_rat("aendern", "Satz streichen"))
    werte = {**WERTE, "schnittstellen": [{"modul": "portwart.drift", "namen": []}]}
    erg = berater.hole_rat(AbhBeide(astra=astra), "spec_freigabe", FRAGE_SPEC, werte, wt, lambda: [], wer="astra")
    assert erg["ok"] and erg["wer"] == "astra" and erg["antwort"] == {"entscheidung": "aendern", "hinweis": "Satz streichen"}
    assert astra.aufrufe[0]["timeout"] == 900 and astra.aufrufe[0]["name"] == "berater_astra"
    assert "DRIFT-INHALT" in astra.aufrufe[0]["prompt"]
    erg = berater.hole_rat(AbhBeide(astra=astra), "spec_freigabe", FRAGE_SPEC, werte, wt, lambda: ["x geändert"],
                           wer="astra")
    assert erg["ok"] is False and "Grenzverletzung" in erg["fehler"]
    erg = berater.hole_rat(Abh(FakeFable(_rat("freigeben"))), "spec_freigabe", FRAGE_SPEC, WERTE, tmp_path, lambda: [])
    assert erg["wer"] == "fable"


def _eintrag(wer, entscheidung, ok=True, cp="c1", punkt="spec_freigabe"):
    rat = _rat(entscheidung, "Text" if entscheidung in ("aendern", "tests_nachbessern") else "",
               begruendung="Der Satz widerspricht sich. Mehr Details.")
    antwort, _ = berater.rat_pruefen(punkt, rat)
    return {"wer": wer, "haltepunkt": punkt, "checkpoint_id": cp, "ok": ok, "rat": rat if ok else None,
            "antwort": antwort if ok else None, "fehler": None if ok else "Timeout"}


def test_vergleiche_einig_uneinig_vorsichtiger():
    v = berater.vergleiche("spec_freigabe", _eintrag("fable", "freigeben"), _eintrag("astra", "aendern"))
    assert v["einig"] is False and v["vorbelegt"] == "astra" and v["einwaende"]
    v = berater.vergleiche("spec_freigabe", _eintrag("fable", "aendern"), _eintrag("astra", "freigeben"))
    assert v["einig"] is False and v["vorbelegt"] == "fable"
    v = berater.vergleiche("spec_freigabe", _eintrag("fable", "freigeben"), _eintrag("astra", "freigeben"))
    assert v == {"einig": True, "vorbelegt": "astra", "einwaende": []}
    assert berater.vergleiche("spec_freigabe", _eintrag("fable", "freigeben"),
                              _eintrag("astra", "aendern", cp="c2")) is None
    assert berater.vergleiche("spec_freigabe", _eintrag("fable", "freigeben"), _eintrag("astra", "x", ok=False)) is None
    assert berater.vergleiche("spec_freigabe", None, _eintrag("astra", "aendern")) is None
    v = berater.vergleiche("eskalation", _eintrag("fable", "annehmen", punkt="eskalation"),
                           _eintrag("astra", "weiter", punkt="eskalation"))
    assert v["vorbelegt"] == "astra"


def test_einwaende_aus_raeten():
    e = berater.einwaende_aus_raeten("spec_freigabe", {"astra": _eintrag("astra", "aendern")})
    assert e == ["Astra (GPT) rät zu aendern: Der Satz widerspricht sich."]
    e = berater.einwaende_aus_raeten("spec_freigabe", {"fable": _eintrag("fable", "freigeben"),
                                                        "astra": _eintrag("astra", "aendern")})
    assert e[0] == "Fable empfiehlt freigeben, Astra aendern" and len(e) == 2
    assert berater.einwaende_aus_raeten("spec_freigabe", {"astra": _eintrag("astra", "x", ok=False)}) == []
    assert berater.einwaende_aus_raeten("spec_freigabe", {"fable": _eintrag("fable", "aendern"),
                                                          "astra": _eintrag("astra", "freigeben")}) == [
        "Fable empfiehlt aendern, Astra freigeben"]


def test_testsperre_astra(tmp_path):
    from entwicklung import agenten
    from entwicklung.graph import Abhaengigkeiten
    with pytest.raises(agenten.EchterAgentImTest):
        berater.hole_rat(Abhaengigkeiten(), "spec_freigabe", FRAGE_SPEC, WERTE, tmp_path, lambda: [], wer="astra")



# ---------------------------------------------------------------------------------------------- 6b-2
def test_hole_rat_gleiche_stufe(tmp_path):
    gesehen = {}

    def fable(name, prompt, cwd, schema, modell="sonnet", timeout=600, effort=None, runner=None):
        gesehen["fable"] = effort
        return {"name": name, "ok": True, "daten": _rat("freigeben"), "fehler": None, "dauer_s": 0.1}

    def astra(name, prompt, cwd, schema, timeout=900, effort="high", runner=None):
        gesehen["astra"] = effort
        return {"name": name, "ok": True, "daten": _rat("freigeben"), "fehler": None, "dauer_s": 0.1}
    for wer in ("fable", "astra"):
        berater.hole_rat(AbhBeide(fable, astra), "spec_freigabe", FRAGE_SPEC, WERTE, tmp_path, lambda: [], wer=wer)
    assert gesehen == {"fable": berater.BERATER_EFFORT, "astra": berater.BERATER_EFFORT} and berater.BERATER_EFFORT == "high"


def _git_wt(tmp_path):
    import subprocess
    wt = tmp_path / "wt"
    for d in ("portwart", "tests/_akzeptanz"):
        (wt / d).mkdir(parents=True)
    (wt / "portwart" / "liste.py").write_text("LISTE = 1\n", encoding="utf-8")
    (wt / "tests" / "test_liste.py").write_text("def test_x(): ...\n", encoding="utf-8")
    (wt / "tests" / "_akzeptanz" / "test_geheim.py").write_text("GEHEIM = 1\n", encoding="utf-8")
    (wt / "README.md").write_text("x\n", encoding="utf-8")
    for befehl in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", *befehl], cwd=wt, check=True, capture_output=True)
    return wt


def test_quelldateien_repo_code_an_rueckfragen(tmp_path):
    """Auch ohne Schnittstellen (Rückfragen) sieht Astra den Code des Ziel-Repos, nie die Akzeptanztests."""
    q = berater.quelldateien({}, {}, "fragen", _git_wt(tmp_path))
    assert list(q) == ["portwart/liste.py", "tests/test_liste.py"]


def test_quelldateien_grenze_mit_vermerk(tmp_path, monkeypatch):
    """Codex 6b-1 F-005: Der Kürzungsvermerk zählt in MAX_QUELLEN mit."""
    wt = _worktree(tmp_path)
    (wt / "gross.py").write_text("x" * 500, encoding="utf-8")
    monkeypatch.setattr(berater, "MAX_QUELLEN", 100)
    q = berater.quelldateien({"plan_dateien": ["gross.py", "portwart/drift.py"]}, {}, "eskalation", wt)
    assert sum(len(v) for v in q.values()) <= 100 and "gekürzt" in q["gross.py"]


def test_prompt_mit_einordnung_ab_fassung_2():
    """6c: Die Berater sehen die beiden Gruppen und die Regel, wann „ändern“ angebracht ist."""
    einordnung = {"ausloesend": [{"pruefer": "codex", "schwere": "major", "aussage": "Neu kaputt",
                                  "herkunft": "aenderung"}],
                  "liste": [{"pruefer": "claude", "schwere": "major", "aussage": "Stand schon so",
                             "herkunft": "sonstiges"}], "alte": []}
    frage = {**FRAGE_SPEC, "spec_runde": 1, "nachpruefung": True, "einordnung": einordnung}
    p = berater.berater_prompt("spec_freigabe", frage, WERTE)
    aus, liste = p.split("## Lösen eine neue Runde aus")[1].split("## Liste für Dominic")
    assert "[codex, major, aenderung] Neu kaputt" in aus and "Stand schon so" in liste
    assert "Ab Fassung 2 empfiehlst du `aendern` nur" in p
    assert "## Punkte der Prüfer" not in p  # nicht doppelt
    assert "Ab Fassung 2" not in berater.berater_prompt("spec_freigabe", FRAGE_SPEC, WERTE)
