# -*- coding: utf-8 -*-
"""Tests voor structuur_detector (plan v3, fase 1) met kunstmatige candles waarvan elke prijs bekend is.
Short na een expansie omhoog, de gespiegelde long, sweep te ver, BOS op close, geen blik vooruit, meeschuivende order."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import structuur_detector as SD

T0 = 1790000000 - 1790000000 % 60


def maak(sweep_hoog=2012.6, h43=2010.5, h44=2011.3):
    """30 rustige candles rond 2000, expansie 2000 -> 2012 (8 candles), pullback, sweep 5 points boven de top,
    BOS met een wick (close erboven), been nog één candle lager, dan een candle zonder nieuwe low, dan vulling en TP."""
    rij = []
    for i in range(30):
        rij.append((2000.0, 2000.3, 1999.7, 2000.0 + (0.1 if i % 2 else -0.1)))
    o = 2000.0
    for _ in range(8):                                   # expansie: candles 30..37
        c = o + 1.5
        rij.append((o, c + 0.1, o - 0.05, c))
        o = c
    rij += [(2012.0, 2012.05, 2010.9, 2011.0),            # 38 pullback
            (2011.0, 2011.5, 2010.6, 2011.3),             # 39
            (2011.3, sweep_hoog, 2011.2, 2011.8),         # 40 sweep van de high van 37 (2012.1)
            (2011.8, 2011.9, 2010.2, 2010.6),             # 41 BOS: wick onder de structuur 2010.45, close erboven
            (2010.6, 2010.7, 2009.8, 2009.9),             # 42 been loopt nog: laagste 2009.8
            (2009.9, h43, 2009.85, 2010.4),               # 43 geen nieuwe low: been klaar
            (2010.4, h44, 2010.3, 2010.9),                # 44 order ligt er (entry 2011.2)
            (2010.9, 2011.0, 2009.6, 2009.7)]             # 45 TP 1:1 (2009.7) geraakt
    for _ in range(12):
        rij.append((2009.7, 2009.9, 2009.5, 2009.7))
    return [(T0 + 60 * i, o, h, l, c, 0.0) for i, (o, h, l, c) in enumerate(rij)]


def spiegel(bars, as_=4000.0):
    return [(t, as_ - o, as_ - l, as_ - h, as_ - c, sp) for (t, o, h, l, c, sp) in bars]


def main():
    fouten = []

    def check(naam, ok, info=""):
        print(("OK   " if ok else "FOUT ") + naam + (f"   [{info}]" if info else ""))
        if not ok:
            fouten.append(naam)

    B = maak()
    K = SD.kandidaten(B)
    shorts = [k for k in K if k["trade"] == "short"]
    check("precies één short, geen long", len(shorts) == 1 and len(K) == 1, [(k["trade"], k["sleutel"]) for k in K])
    k = shorts[0]
    check("sweep op candle 40 (2012.6), geveegde high 2012.1", k["i_sweep"] == 40 and k["sweep"] == 2012.6 and k["geveegd"] == 2012.1)
    check("structuur = laagste low tussen geveegde high en sweep (2010.45)", abs(k["structuur"] - 2010.45) < 1e-9, k["structuur"])
    check("BOS type 3: de wick van candle 41", k["i_bos"] == 41)
    check("BOS-been afgemaakt tot 2009.8, klaar op 43, order vanaf 44", k["bos_laag"] == 2009.8 and k["i_klaar"] == 43 and k["i_order"] == 44)
    check("entry = midden van sweep en been (2011.2)", abs(k["entry"] - 2011.2) < 1e-9, k["entry"])
    check("SL = sweep + 1 point (2012.7), TP 1:1 = 2009.7", abs(k["sl"] - 2012.7) < 1e-9 and abs(k["tp_11"] - 2009.7) < 1e-9)
    check("expansie begint op de laagste low (1999.7)", k["begin"] == 1999.7 and abs(k["tp_50"] - (1999.7 + 2012.6) / 2) < 1e-9)
    check("tijden zijn Python-ints", all(type(k[x]) is int for x in ("sweep_tijd", "bos_tijd", "order_tijd", "begin_tijd")))
    kk = k["kenmerken"]
    check("kenmerken: sweep 5 points, risico 15 points, BOS niet op close", round(kk["sweep_points"], 6) == 5.0 and round(kk["risico_points"], 6) == 15.0
          and kk["bos_close"] is False and kk["exp_atr"] > 4)
    u = SD.simuleer(B, k, "tp_11")
    check("simulatie: gevuld op 44, TP 1:1 op 45 (+1R)", u["status"] == "tp" and u["r"] == 1.0 and u["fill_tijd"] == B[44][0])

    L = SD.kandidaten(spiegel(B))
    check("gespiegeld: precies één long met gespiegelde prijzen",
          len(L) == 1 and L[0]["trade"] == "long" and abs(L[0]["entry"] - (4000 - 2011.2)) < 1e-9 and abs(L[0]["sl"] - (4000 - 2012.7)) < 1e-9)
    check("gespiegeld: zelfde uitkomst", SD.simuleer(spiegel(B), L[0], "tp_11")["status"] == "tp")

    check("sweep 45 points voorbij de high: geen sweep maar een nieuwe impuls", not SD.kandidaten(maak(sweep_hoog=2012.1 + 4.5)))
    C = SD.kandidaten(B, {"bos_op_close": True})
    check("BOS op close: pas candle 42 (close onder de structuur)", len(C) == 1 and C[0]["i_bos"] == 42)

    N = maak(h43=2011.25, h44=2010.9)                    # alleen de klaar-candle raakt de entry
    kn = SD.kandidaten(N)[0]
    check("geen blik vooruit: order pas vanaf 44, dus niet gevuld", SD.simuleer(N, kn, "tp_11")["status"] == "vervallen_tp")
    um = SD.simuleer(N, kn, "tp_11", doorlopend=True)
    check("meeschuivende order (zoals Marijn): gevuld in 43, TP", um["status"] == "tp" and um["fill_tijd"] == N[43][0])

    # 8 okt 2026: 'lopend' (live meeschuivende order): de setup al melden bij de BOS, terwijl het been nog loopt
    halverwege = B[:43]                                   # t/m candle 42: BOS op 41, been loopt nog (42 maakt een nieuwe low)
    check("standaard: geen setup zolang het been loopt (journal ongewijzigd)", not SD.kandidaten(halverwege))
    lp = SD.kandidaten(halverwege, {"lopend": True})
    check("lopend: setup al bij de BOS, order vanaf de candle erna (42), been tot nu toe",
          len(lp) == 1 and lp[0]["lopend"] and lp[0]["i_bos"] == 41 and lp[0]["i_order"] == 42 and lp[0]["i_klaar"] is None,
          [(x["lopend"], x["i_bos"], x["i_order"], x["bos_laag"]) for x in lp])
    check("lopend en klaar zijn dezelfde setup (zelfde sleutel)", lp and lp[0]["sleutel"] == k["sleutel"])
    check("met lopend aan blijft de klare setup gelijk", [x["sleutel"] for x in SD.kandidaten(B, {"lopend": True}) if not x["lopend"]] == [k["sleutel"]])

    print("\nALLES GOED" if not fouten else "\n%d FOUT(EN)" % len(fouten))
    return 1 if fouten else 0


if __name__ == "__main__":
    sys.exit(main())
