"""Stufe 6c: Einordnung der Spec-Punkte bei der Nachprüfung (reine Funktionen, keine Agenten)."""
from entwicklung.konvergenz import (DIFF_GRENZE, NACHPRUEF_SCHEMA, diff_text, einordnen, nachpruef_text, nummeriert,
                                    verlauf_eintrag)

A = {"pruefer": "claude", "ok": True}
ALT = [{"nr": 1, "pruefer": "codex", "schwere": "major", "aussage": "Reload fehlt"},
       {"nr": 2, "pruefer": "claude", "schwere": "minor", "aussage": "Meldung unklar"}]


def _neu(*punkte, alte=()):
    return {**A, "punkte": list(punkte), "alte_punkte": list(alte)}


def test_erste_pruefung_alle_major_loesen_aus():
    e = einordnen([{**A, "punkte": [{"schwere": "major", "aussage": "x"}, {"schwere": "minor", "aussage": "y"}]}], None)
    assert [p["aussage"] for p in e["ausloesend"]] == ["x"] and [p["aussage"] for p in e["liste"]] == ["y"]
    assert e["ausloesend"][0]["herkunft"] == "erstpruefung" and e["ausloesend"][0]["pruefer"] == "claude"
    assert e["alte"] == []


def test_sonstiges_major_geht_in_die_liste():
    e = einordnen([_neu({"schwere": "major", "aussage": "alt übersehen", "herkunft": "sonstiges"})], [])
    assert e["ausloesend"] == [] and e["liste"][0]["herkunft"] == "sonstiges"


def test_aenderung_und_widerspruch_loesen_aus():
    e = einordnen([_neu({"schwere": "major", "aussage": "neu kaputt", "herkunft": "aenderung"},
                        {"schwere": "major", "aussage": "gegen Antwort 2", "herkunft": "widerspruch"},
                        {"schwere": "minor", "aussage": "Tippfehler", "herkunft": "aenderung"})], [])
    assert [p["aussage"] for p in e["ausloesend"]] == ["neu kaputt", "gegen Antwort 2"]
    assert [p["aussage"] for p in e["liste"]] == ["Tippfehler"]


def test_major_ohne_herkunft_loest_aus():
    e = einordnen([_neu({"schwere": "major", "aussage": "ohne"},
                        {"schwere": "major", "aussage": "falsch", "herkunft": "quatsch"})], [])
    assert [p["aussage"] for p in e["ausloesend"]] == ["ohne", "falsch"]
    assert {p["herkunft"] for p in e["ausloesend"]} == {"unbekannt"}


def test_alter_major_teilweise_loest_aus():
    e = einordnen([_neu(alte=[{"nr": 1, "status": "teilweise", "grund": "nur Pfad A"},
                              {"nr": 2, "status": "offen", "grund": ""}])], ALT)
    assert [p["nr"] for p in e["ausloesend"]] == [1]  # nr 2 ist minor → Liste
    assert [p["nr"] for p in e["liste"]] == [2]
    assert e["ausloesend"][0]["status"] == "teilweise" and e["ausloesend"][0]["aussage"] == "Reload fehlt"


def test_schlechtester_status_gilt():
    claude = _neu(alte=[{"nr": 1, "status": "geloest", "grund": ""}])
    codex = {"pruefer": "codex", "ok": True, "punkte": [], "alte_punkte": [{"nr": 1, "status": "offen", "grund": ""}]}
    alt = einordnen([claude, codex], ALT[:1])["alte"][0]
    assert alt["status"] == "offen" and alt["bewertet"] == {"claude": "geloest", "codex": "offen"}


def test_alter_punkt_ohne_bewertung_ist_offen():
    e = einordnen([_neu()], ALT[:1])
    assert e["alte"][0]["status"] == "offen" and e["alte"][0]["bewertet"] == {"claude": "offen"}
    assert [p["nr"] for p in e["ausloesend"]] == [1]


def test_unbekannte_nr_wird_ignoriert():
    e = einordnen([_neu(alte=[{"nr": 99, "status": "offen", "grund": ""}, {"nr": 1, "status": "geloest", "grund": ""},
                              {"nr": "x", "status": "offen", "grund": ""}])], ALT[:1])
    assert [p["nr"] for p in e["alte"]] == [1] and e["alte"][0]["status"] == "geloest"


def test_ungueltiger_status_ist_offen():
    e = einordnen([_neu(alte=[{"nr": 1, "status": "erledigt", "grund": ""}])], ALT[:1])
    assert e["alte"][0]["status"] == "offen"


def test_nicht_verwertbarer_pruefer_zaehlt_nicht():
    claude = _neu(alte=[{"nr": 1, "status": "geloest", "grund": ""}])
    codex = {"pruefer": "codex", "ok": False, "punkte": [], "alte_punkte": []}
    alt = einordnen([claude, codex], ALT[:1])["alte"][0]
    assert alt["status"] == "geloest" and alt["bewertet"] == {"claude": "geloest"}


def test_ohne_verwertbare_pruefung_bleibt_alter_punkt_offen():
    e = einordnen([{"pruefer": "codex", "ok": False, "punkte": [], "alte_punkte": []}], ALT[:1])
    assert e["alte"][0]["status"] == "offen" and [p["nr"] for p in e["ausloesend"]] == [1]


def test_alle_geloest_nichts_loest_aus():
    e = einordnen([_neu(alte=[{"nr": 1, "status": "geloest", "grund": ""}, {"nr": 2, "status": "geloest", "grund": ""}])],
                  ALT)
    assert e["ausloesend"] == [] and [p["nr"] for p in e["liste"]] == [1, 2]


def test_nummeriert():
    assert [p["nr"] for p in nummeriert([{"aussage": "a"}, {"aussage": "b", "nr": 7}])] == [1, 2]


def test_diff_unveraendert():
    assert diff_text("a\n", "a\n", "spec") == "spec: unverändert"


def test_diff_zeigt_aenderung():
    d = diff_text("a\nb\n", "a\nc\n", "spec")
    assert "--- spec (vorher)" in d and "+++ spec (jetzt)" in d and "-b" in d and "+c" in d


def test_diff_wird_gekuerzt():
    d = diff_text("", "x" * 100 + "\n" * 40000, "spec")
    assert len(d) <= DIFF_GRENZE + 80 and "Diff gekürzt" in d


def test_nachpruef_text_nennt_alte_punkte_und_diffs():
    t = nachpruef_text({"spec": "a\n", "tests": {"t.py": "x = 1\n"}, "punkte": ALT}, "b\n", {"t.py": "x = 2\n"})
    assert "## Nachprüfung" in t and "1. [codex, major] Reload fehlt" in t and "2. [claude, minor] Meldung unklar" in t
    assert "-a" in t and "+b" in t and "+x = 2" in t


def test_nachpruef_text_neue_und_entfallene_testdatei():
    t = nachpruef_text({"spec": "a\n", "tests": {"alt.py": "y = 1\n"}, "punkte": []}, "a\n", {"neu.py": "z = 1\n"})
    assert "spec: unverändert" in t and "+z = 1" in t and "-y = 1" in t


def test_nachpruef_schema_streng():
    item = NACHPRUEF_SCHEMA["properties"]["punkte"]["items"]
    assert item["required"] == ["schwere", "aussage", "herkunft"] and item["additionalProperties"] is False
    assert item["properties"]["herkunft"]["enum"] == ["aenderung", "widerspruch", "sonstiges"]
    alt = NACHPRUEF_SCHEMA["properties"]["alte_punkte"]["items"]
    assert alt["required"] == ["nr", "status", "grund"] and alt["properties"]["nr"] == {"type": "integer"}
    assert set(NACHPRUEF_SCHEMA["required"]) >= {"verdict", "punkte", "alte_punkte", "komplexitaet",
                                                 "komplexitaet_grund"}


def test_verlauf_eintrag():
    e = einordnen([_neu({"schwere": "major", "aussage": "x", "herkunft": "aenderung"},
                        {"schwere": "minor", "aussage": "y", "herkunft": "sonstiges"})], [])
    assert verlauf_eintrag(1, False, "abcd", ["a1", "a2"], ["t1", "t2", "t3"], e) == {
        "fassung": 2, "nachgebessert": False, "zeichen": 4, "annahmen": 2, "tests": 3, "ausloesend": 1, "liste": 1}


def test_punkt_zeile_neu_und_alt():
    from entwicklung.konvergenz import punkt_zeile
    assert punkt_zeile({"pruefer": "claude", "schwere": "major", "aussage": "x", "herkunft": "aenderung"}) == \
        "[claude, major, aenderung] x"
    assert punkt_zeile({"nr": 1, "pruefer": "codex", "schwere": "major", "aussage": "y", "status": "offen",
                        "bewertet": {}}) == "[codex, major, alt offen] y"


def test_verlauf_zeile():
    from entwicklung.konvergenz import verlauf_zeile
    v = {"fassung": 2, "nachgebessert": False, "zeichen": 1200, "annahmen": 3, "tests": 12, "ausloesend": 1, "liste": 4}
    assert verlauf_zeile(v) == "Fassung 2: 1200 Zeichen, 3 Annahmen, 12 Tests, 1 auslösend, 4 auf der Liste"
    assert verlauf_zeile({**v, "nachgebessert": True}).endswith("(Tests nachgebessert)")


def test_nur_sperre_loest_nicht_aus():
    alt = [{"nr": 1, "pruefer": "codex", "schwere": "major", "aussage": "Alt übersehen", "nur_sperre": True}]
    e = einordnen([_neu()], alt)
    assert e["ausloesend"] == [] and e["liste"][0]["nur_sperre"] is True and e["liste"][0]["status"] == "offen"
