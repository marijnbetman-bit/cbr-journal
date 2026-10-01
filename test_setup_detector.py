# -*- coding: utf-8 -*-
"""Tests voor setup_detector met de nagetekende candles van 22 sep 21:12-21:42."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import setup_detector as D

RUW = [
("21:12",4359.1,4359.3,4357.6,4357.7),("21:13",4358.8,4359.0,4357.5,4357.6),
("21:14",4358.1,4358.8,4357.9,4358.6),("21:15",4358.5,4358.7,4358.2,4358.4),
("21:16",4358.2,4358.9,4357.7,4357.8),("21:17",4357.8,4358.0,4356.7,4357.4),
("21:18",4357.4,4358.2,4357.2,4358.0),("21:19",4358.1,4358.5,4357.9,4358.2),
("21:20",4358.0,4358.3,4357.4,4357.5),("21:21",4357.5,4357.7,4356.4,4356.9),
("21:22",4356.9,4357.4,4356.7,4357.2),("21:23",4357.2,4357.9,4357.0,4357.8),
("21:24",4357.8,4359.2,4357.6,4359.0),("21:25",4359.0,4361.3,4358.8,4360.3),
("21:26",4360.3,4360.5,4358.5,4358.6),("21:27",4358.6,4358.8,4357.3,4357.4),
("21:28",4357.5,4358.5,4357.3,4358.3),("21:29",4358.3,4360.1,4358.1,4359.8),
("21:30",4359.8,4362.1,4359.6,4361.9),("21:31",4361.9,4364.9,4361.2,4364.7),
("21:32",4364.7,4366.6,4364.4,4366.4),("21:33",4366.4,4367.8,4365.3,4367.2),
("21:34",4367.5,4370.4,4367.3,4370.2),("21:35",4370.0,4370.5,4369.5,4369.9),
("21:36",4369.8,4370.2,4367.0,4367.1),("21:37",4367.1,4371.1,4366.8,4369.6),
("21:38",4369.6,4369.9,4368.4,4368.5),("21:39",4368.5,4369.8,4368.1,4369.6),
("21:40",4369.6,4371.0,4369.4,4370.6),("21:41",4370.6,4370.9,4368.2,4368.6),
("21:42",4368.6,4368.9,4368.2,4368.4),
]
def bars_van(ruw):
    return [(t, o, h, l, c) for (t, o, h, l, c) in ruw]

def main():
    global fouten
    fouten = []
    def check(naam, ok, info=""):
        print(("OK   " if ok else "FOUT ") + naam + (f"   [{info}]" if info else ""))
        if not ok: fouten.append(naam)

    B = bars_van(RUW)
    # 1. tot 21:42: impuls herkend, short gezocht, sweep gezien, nog geen BOS
    s = [x for x in D.scan(B) if x.impuls_richting == "up"]
    check("precies één setup na de impuls omhoog", len(s) == 1, [x.sleutel for x in s])
    s = s[0]
    imp = s.impuls
    check("impuls start 21:27/21:28", imp["van_tijd"] in ("21:27", "21:28"), imp["van_tijd"])
    check("top = 21:35 op 4370,5", s.top_tijd == "21:35" and abs(s.top - 4370.5) < 1e-9, (s.top_tijd, s.top))
    check("trade-richting short", s.trade == "short")
    check("kracht >= 4x ATR", imp["kracht"] >= 4, imp["kracht"])
    check("overlap <= 45%", imp["overlap"] <= 0.45, imp["overlap"])
    check("sweep 21:37 op 4371,1", s.sweep_tijd == "21:37" and abs(s.sweep - 4371.1) < 1e-9, (s.sweep_tijd, s.sweep))
    check("pullback-low 4367,0", abs(s.pullback - 4367.0) < 1e-9, s.pullback)
    check("status opgelet (wacht op BOS)", s.status == "opgelet", s.status)

    # 2. verder: BOS, pullback naar entry, TP
    VERDER = [("21:43",4368.4,4368.5,4366.2,4366.5),     # close < 4367,0 -> BOS
              ("21:44",4366.6,4369.2,4366.6,4368.9),     # raakt entry 4369,05
              ("21:45",4368.9,4369.0,4366.3,4366.4)]     # raakt TP 4366,50
    B2 = bars_van(RUW + VERDER)
    s = [x for x in D.scan(B2) if x.impuls_richting == "up"][0]
    check("entry = 50% sweep..pullback = 4369,05", s.entry == 4369.05, s.entry)
    check("SL = sweep + 5 points = 4371,60", s.sl == 4371.6, s.sl)
    check("TP op 1:1 = 4366,50", s.tp == 4366.5, s.tp)
    check("BOS om 21:43", s.bos_tijd == "21:43", s.bos_tijd)
    check("entry om 21:44", s.entry_tijd == "21:44", s.entry_tijd)
    check("uitkomst TP om 21:45", s.status == "tp" and s.uitkomst_tijd == "21:45", (s.status, s.uitkomst_tijd))
    check("events op volgorde", [e[0] for e in s.events] == ["opgelet", "rijp", "entry", "tp"], s.events)

    # 2b. live candle raakt de entry al voordat hij sluit
    B3 = bars_van(RUW + VERDER[:1])
    s = [x for x in D.scan(B3, live=("21:44", 4366.5, 4369.1, 4366.4, 4368.0)) if x.impuls_richting == "up"][0]
    check("entry via lopende candle", s.status == "entry" and s.entry_tijd == "21:44", (s.status, s.entry_tijd))
    s = [x for x in D.scan(B3) if x.impuls_richting == "up"][0]
    check("zonder live candle: rijp", s.status == "rijp", s.status)

    # 3. 50% van de impuls geraakt vóór entry -> vervallen
    DIEP = [("21:43",4368.4,4368.5,4363.0,4363.5)]       # BOS-candle zakt tot onder 4363,9
    s = [x for x in D.scan(bars_van(RUW + DIEP)) if x.impuls_richting == "up"][0]
    check("50% geraakt -> vervallen", s.status == "vervallen" and "50%" in s.reden, (s.status, s.reden))

    # 4. sweep > 30 points door de top -> geen sweep
    RUW4 = [r for r in RUW if r[0] <= "21:36"] + [("21:37",4367.1,4374.0,4366.8,4373.5)]
    s = [x for x in D.scan(bars_van(RUW4)) if x.impuls_richting == "up" and x.top_tijd == "21:35"][0]
    check("35 points door de top -> vervallen", s.status == "vervallen" and "nieuwe impuls" in s.reden, s.reden)

    # 5. geen sweep binnen 10 candles
    RUW5 = [r for r in RUW if r[0] <= "21:36"] + [(f"21:{m}", 4368.0, 4368.6, 4367.6, 4368.1) for m in range(37, 48)]
    s = [x for x in D.scan(bars_van(RUW5)) if x.impuls_richting == "up"][0]
    check("top verloopt na 10 min", s.status == "vervallen" and "10 min" in s.reden, s.reden)

    # 6. spiegelbeeld: impuls omlaag -> long
    def spiegel(r):
        t, o, h, l, c = r
        return (t, 9000 - o, 9000 - l, 9000 - h, 9000 - c)
    BM = [spiegel(r) for r in RUW + VERDER]
    s = [x for x in D.scan(BM) if x.impuls_richting == "down"][0]
    check("spiegel: long", s.trade == "long", s.trade)
    check("spiegel: entry 9000-4369,05", abs(s.entry - (9000 - 4369.05)) < 0.011, s.entry)
    check("spiegel: SL onder de sweep", abs(s.sl - (9000 - 4371.6)) < 0.011, s.sl)
    check("spiegel: TP geraakt", s.status == "tp", s.status)

    # 7. chop geeft niets
    CHOP = [(f"t{k:03d}", 100 + (k % 3) * .1, 100.4 + (k % 3) * .1, 99.7, 100.05) for k in range(80)]
    check("chop geeft geen setup", D.scan(CHOP) == [])
    k = D.beste_kandidaat(B[:24])
    check("waarom_niet geeft tekst", isinstance(D.waarom_niet(k), str), D.waarom_niet(k))

    # 8. 1H-break-regel (epoch-tijden). RUW (21:12-21:42) zit in één klok-uur;
    #    we plakken er een 'vorig uur' voor met een instelbare high, en checken of
    #    de impuls (top 4370,5) al dan niet die vorige-uur-high breekt.
    UUR = 3600
    def _epoch_ruw(basis):
        # RUW-candles binnen het uur dat begint op 'basis' (21:12 = +12 min, enz.)
        out = []
        for k, (t, o, h, l, c) in enumerate(RUW):
            mm = int(t.split(":")[1])
            out.append((basis + mm * 60, o, h, l, c))
        return out
    def _vorig_uur(basis, hoog, laag=4360.0):
        # 60 rustige 1-min candles in het uur ervoor; één candle zet de high/low
        cs = []
        for m in range(60):
            h = hoog if m == 30 else laag + 1.0
            l = laag if m == 30 else laag + 0.5
            cs.append((basis - UUR + m * 60, laag + 0.7, h, l, laag + 0.8))
        return cs
    B_START = 1_600_000_000 // UUR * UUR + UUR   # op een heel uur

    # breekt WEL: vorige-uur-high 4369 < impuls-top 4370,5
    bars_wel = _vorig_uur(B_START, hoog=4369.0) + _epoch_ruw(B_START)
    up_wel = [x for x in D.scan(bars_wel) if x.impuls_richting == "up"]
    check("1H-break: impuls breekt vorige high -> setup", len(up_wel) == 1, [x.sleutel for x in up_wel])

    # breekt NIET: vorige-uur-high 4380 > impuls-top 4370,5
    bars_niet = _vorig_uur(B_START, hoog=4380.0) + _epoch_ruw(B_START)
    up_niet = [x for x in D.scan(bars_niet) if x.impuls_richting == "up"]
    check("1H-break: impuls breekt vorige high NIET -> geen setup", len(up_niet) == 0, [x.sleutel for x in up_niet])

    # uitschakelbaar via config
    up_uit = [x for x in D.scan(bars_niet, {"eis_1h_break": False}) if x.impuls_richting == "up"]
    check("1H-break: uitgezet -> de impuls komt terug",
          any(x.sleutel == "up-1600003680-1600004100" for x in up_uit), [x.sleutel for x in up_uit])

    # predicaat rechtstreeks
    imp_up = D.Impuls("up", 0, 0, 100.0, 110.0, 10.0, 4, 0.1, 0.9, 1.0, 10.0)
    check("vorige_1h_extreme None bij string-tijd", D.vorige_1h_extreme([("21:00", 1, 2, 0, 1)], imp_up) is None)
    check("breekt_vorige_1h laat door zonder data", D.breekt_vorige_1h([("21:00", 1, 2, 0, 1)], imp_up, D.STANDAARD) is True)

    print("\n" + ("ALLES GOED" if not fouten else f"{len(fouten)} FOUT(EN): {fouten}"))
    return fouten


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
