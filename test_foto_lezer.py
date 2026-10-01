# -*- coding: utf-8 -*-
"""Sandboxtest voor foto_lezer.py -- toetst de logica, niet de modelnauwkeurigheid.

De modelnauwkeurigheid (kan Haiku de niveaus echt van jouw screenshots lezen)
kan alleen op de VPS met de echte sleutel en jouw eigen foto's getest worden;
dat is de acceptatietest van WP9. Deze test bewijst dat het parsen, de
plausibiliteitsband, de tweede-screenshot-trigger en het samenvoegen kloppen.
"""

import types
import foto_lezer as fl


class NepClient:
    """Doet alsof hij de Claude API is: geeft een vast JSON-antwoord terug."""
    def __init__(self, json_tekst):
        self._tekst = json_tekst
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, **_):
        blok = types.SimpleNamespace(text=self._tekst)
        return types.SimpleNamespace(content=[blok])


def test_getal_varianten():
    assert fl.naar_getal("4.330,23") == 4330.23
    assert fl.naar_getal("4,330.23") == 4330.23
    assert fl.naar_getal("4330.23") == 4330.23
    assert fl.naar_getal("4330") == 4330.0
    assert fl.naar_getal("4 330,23") == 4330.23
    assert fl.naar_getal("$4,313.55") == 4313.55
    # onplausibel of onleesbaar -> None (geen gok)
    assert fl.naar_getal("0.5") is None
    assert fl.naar_getal("99999") is None
    assert fl.naar_getal(None) is None
    assert fl.naar_getal("n/a") is None
    print("  getal-varianten OK")


def test_complete_uitlezing():
    client = NepClient('{"richting":"short","entry":4330.23,"sl":4319.36,'
                       '"tp":4341.09,"zeker":["richting","entry","sl","tp"],'
                       '"twijfel":[]}')
    u = fl.lees_niveaus(b"nep", client)
    assert u.fout == "", u.fout
    assert u.richting == "short"
    assert u.entry == 4330.23 and u.sl == 4319.36 and u.tp == 4341.09
    assert u.compleet
    assert not u.vraag_tweede
    assert u.ontbreekt == []
    print("  complete uitlezing OK")


def test_tp_ontbreekt_vraagt_tweede():
    client = NepClient('{"richting":"long","entry":4316.02,"sl":4313.55,'
                       '"tp":null,"zeker":["richting","entry","sl"],'
                       '"twijfel":["tp"]}')
    u = fl.lees_niveaus(b"nep", client)
    assert u.compleet is False
    assert u.ontbreekt == ["tp"]
    assert u.vraag_tweede is True
    print("  tp-ontbreekt vraagt tweede OK")


def test_model_gokte_onplausibel_wordt_none():
    # het model gaf per ongeluk een as-label als sl
    client = NepClient('{"richting":"short","entry":4330.23,"sl":25000,'
                       '"tp":4341.09,"zeker":["entry","sl","tp"]}')
    u = fl.lees_niveaus(b"nep", client)
    assert u.sl is None            # 25000 valt buiten de band -> weggegooid
    assert "sl" not in u.zeker     # en telt niet meer als 'zeker'
    assert u.vraag_tweede is True  # dus toch een tweede screenshot
    print("  onplausibele sl wordt None OK")


def test_geen_json():
    client = NepClient("Sorry, ik kan de niveaus niet zien op deze foto.")
    u = fl.lees_niveaus(b"nep", client)
    assert u.fout != ""
    assert u.entry is None
    print("  geen-json nette fout OK")


def test_combineer_tweede_wint():
    eerste = fl.Uitlezing(richting="long", entry=4316.02, sl=None, tp=None,
                          zeker=["richting", "entry"])
    tweede = fl.Uitlezing(entry=4316.10, sl=4313.55, tp=4321.00,
                          zeker=["entry", "sl", "tp"])
    samen = fl.combineer(eerste, tweede)
    assert samen.richting == "long"      # alleen in de eerste
    assert samen.entry == 4316.10        # tweede wint waar beide iets hebben
    assert samen.sl == 4313.55 and samen.tp == 4321.00
    assert samen.compleet and not samen.vraag_tweede
    print("  combineer tweede-wint OK")


if __name__ == "__main__":
    for naam, fn in sorted(globals().items()):
        if naam.startswith("test_") and callable(fn):
            fn()
    print("alle foto_lezer-tests geslaagd")
