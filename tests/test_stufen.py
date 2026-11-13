from entwicklung import stufen


def test_stufe_fuer_tabelle():
    assert [stufen.stufe_fuer("implementierer", k) for k in stufen.KOMPLEXITAETEN] == [
        ("sonnet", "medium"), ("sonnet", "high"), ("opus", "high")]
    assert [stufen.stufe_fuer("pruefer", k) for k in stufen.KOMPLEXITAETEN] == [
        ("opus", "high"), ("opus", "high"), ("opus", "xhigh")]
    assert {stufen.stufe_fuer("codex", k) for k in stufen.KOMPLEXITAETEN} == {(None, "high")}
    assert stufen.PLANUNG_STUFEN == {"planer": ("sonnet", "high"), "spec_pruefer": ("opus", "high"),
                                     "codex": (None, "high")}


def test_hoechste():
    assert stufen.hoechste("einfach", "schwer") == "schwer"
    assert stufen.hoechste("mittel", None) == "mittel"
    assert stufen.hoechste(None, None) == "mittel"
    assert stufen.hoechste("einfach") == "einfach"
    assert stufen.hoechste("quatsch", "einfach") == "einfach"


def test_stufe_im_lauf_startmodell_und_timeouts():
    s = {"komplexitaet": "schwer", "modell": "haiku", "pruefer_modell": "auto"}
    assert stufen.stufe_im_lauf(s, "implementierer") == {"modell": "haiku", "effort": "high", "timeout": 600}
    assert stufen.stufe_im_lauf(s, "pruefer") == {"modell": "opus", "effort": "xhigh", "timeout": 1200}
    assert stufen.stufe_im_lauf({"komplexitaet": "schwer"}, "implementierer") == {
        "modell": "opus", "effort": "high", "timeout": 900}
    assert stufen.stufe_im_lauf({}, "implementierer") == {"modell": "sonnet", "effort": "high", "timeout": 600}
    assert stufen.stufe_im_lauf({"pruefer_modell": "sonnet"}, "pruefer")["modell"] == "sonnet"
