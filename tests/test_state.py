from entwicklung.state import LEEREN, sammeln_oder_leeren


def test_reducer_sammelt_und_leert():
    a = sammeln_oder_leeren([], [{"pruefer": "funktion"}])
    b = sammeln_oder_leeren(a, [{"pruefer": "codex"}])
    assert [p["pruefer"] for p in b] == ["funktion", "codex"]
    assert sammeln_oder_leeren(b, LEEREN) == []
    assert sammeln_oder_leeren(None, [{"pruefer": "x"}]) == [{"pruefer": "x"}]


def test_state_kennt_planungsfelder():
    import operator
    import typing
    from entwicklung.state import EntwicklungState
    felder = typing.get_type_hints(EntwicklungState, include_extras=True)
    for name in ("wunsch", "klaer_runde", "offene_fragen", "verstaendnis", "spec", "schnittstellen", "annahmen",
                 "spec_runde", "spec_aenderung", "akz_versuch", "akz_gruende", "akz_dateien", "akz_ordner",
                 "akz_probe", "halt_hinweis"):
        assert name in felder, name
    assert felder["klaerung"].__metadata__ == (operator.add,)
    assert felder["spec_pruefungen"].__metadata__ == (sammeln_oder_leeren,)
