"""Maç sonrası değerlendirme: önerilen her seçimi gerçek maç verisiyle karşılaştırır.

Kullanım: python3 motor/degerlendir.py motor/maclar/<slug>.json motor/sonuclar/<slug>.json

Sonuç dosyası: goller (dakika, takım, penaltı/kendi kalesine, oyuncu), kartlar (dakika, takım, tür),
korner sayıları (dakika bilinmiyorsa yalnızca toplam). Zamanı/türü bilinmeyen olaylar rastgele
yerleştirilerek motor 40 kez çalıştırılır; sonucu her seferinde aynı çıkan pazarlar kesin
olarak değerlendirilir, değişenler "belirsiz" sayılır.
"""
import json, sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import motor as M

K = 40


def slot(minute, extra=0):
    if minute <= 45 and extra == 0:
        return minute - 1
    if minute == 45:
        return 45 + min(extra - 1, 1)
    if minute <= 90 and extra == 0:
        return 47 + (minute - 46)
    return 92 + min(extra - 1, 4)


def fake_sim(cfg, res, rng):
    s = M.Sim.__new__(M.Sim)
    s.n, s.cfg, s.rng = 1, cfg, rng
    z = lambda: np.zeros((1, M.NS), dtype=np.int8)
    T = {sd: {k: z() for k in ("g_open", "og", "pen", "pen_goal", "pen_miss", "c", "y", "rd", "r2")} for sd in ("ev", "dep")}
    for g in res["goller"]:
        sd, sl = g["takim"], slot(g["dk"], g.get("uz", 0))
        k = "pen_goal" if g.get("penalti") else "og" if g.get("kendi_kalesine") else "g_open"
        T[sd][k][0, sl] += 1
        if g.get("penalti"):
            T[sd]["pen"][0, sl] += 1
    for p in res.get("kacan_penaltilar", []):
        T[p["takim"]]["pen"][0, slot(p["dk"])] += 1
        T[p["takim"]]["pen_miss"][0, slot(p["dk"])] += 1
    for c in res["kartlar"]:
        key = {"sari": "y", "kirmizi": "rd", "ikinci_sari": "r2"}[c["tur"]]
        T[c["takim"]][key][0, slot(c["dk"], c.get("uz", 0))] += 1
    for sd in ("ev", "dep"):
        n_c = res["kornerler"][sd]
        w = M.w_shape(0.47, 0.15)
        for sl in rng.choice(M.NS, size=n_c, p=w / w.sum()):
            T[sd]["c"][0, sl] += 1
        t = T[sd]
        t["g"] = t["g_open"] + t["pen_goal"] + t["og"]
        t["r"] = t["rd"] + t["r2"]
        t["yy"] = t["y"] + t["r2"]
    s.T = T
    # gol ayrıntıları bilinmiyorsa rastgele
    s._goal_details()
    if "ilk_gol_turu" in res:
        s.first_goal_kind = np.array([res["ilk_gol_turu"]], dtype=object)
    # oyuncular: gerçek golcüler
    s.P = {}
    for sd in ("ev", "dep"):
        for p in cfg[sd].get("oyuncular", []):
            nm = p["ad"]
            mine = [g for g in res["goller"] if g.get("oyuncu") == nm]
            g = np.array([len(mine)])
            g1 = np.array([sum(1 for x in mine if x["dk"] <= 45)])
            pen = np.array([sum(1 for x in mine if x.get("penalti"))])
            a = np.array([rng.integers(0, 2) if res.get("asistler_bilinmiyor", True) else 0])
            s.P[nm] = dict(side=sd, g=g, g1=g1, g2=g - g1, a=a, pen_miss=np.array([0]),
                           head=rng.binomial(g, 0.5), outside=rng.binomial(g, 0.5), fk=rng.binomial(g, 0.2),
                           right=rng.binomial(g, 0.5), six=rng.binomial(g, 0.5), pen=pen,
                           card=np.array([any(c.get("oyuncu") == nm for c in res["kartlar"])]),
                           red=np.array([any(c.get("oyuncu") == nm and c["tur"] != "sari" for c in res["kartlar"])]),
                           first10=np.array([sum(1 for x in mine if x["dk"] <= 10)]), info=p)
        s.P[sd + "_hattrick"] = np.array([max([sum(1 for g in res["goller"] if g.get("oyuncu") == o) for o in {g.get("oyuncu") for g in res["goller"] if g["takim"] == sd}] or [0]) >= 3])
    s.var = np.array([res.get("var", rng.integers(0, 2))])
    return s


def main(cfg_path, res_path):
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    res = json.load(open(res_path, encoding="utf-8"))
    slug = os.path.splitext(os.path.basename(cfg_path))[0]
    pred = json.load(open(os.path.join(M.ROOT, "analizler", f"{slug}-tam.json"), encoding="utf-8"))
    runs = []
    for k in range(K):
        rng = np.random.default_rng(1000 + k)
        sim = fake_sim(cfg, res, rng)
        out = M.build(M.Ev(sim, cfg))
        runs.append({key.replace("{EV}", cfg["ev"]["ad"]).replace("{DEP}", cfg["dep"]["ad"]): {l: p for l, p in v["secimler"]} for key, v in out.items()})
    rows = []
    for r in pred["pazarlar"]:
        if not r["oneri"]:
            rows.append(dict(r, sonuc="değerlendirilmedi"))
            continue
        raw = [run.get(r["pazar"], {}).get(r["oneri"]) for run in runs]
        vals = {("iade" if v != v else v) for v in raw}
        if vals == {"iade"}:
            sonuc = "iade"
        elif len(vals) == 1 and None not in vals:
            v = vals.pop()
            sonuc = "tuttu" if v >= 0.999 else "tutmadı" if v <= 0.001 else f"kısmi ({v:.2f})"
        else:
            sonuc = "belirsiz"
        rows.append(dict(r, sonuc=sonuc))
    json.dump(dict(mac=slug, skor=res["skor"], pazarlar=rows), open(os.path.join(M.ROOT, "analizler", f"{slug}-sonuc.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    graded = [r for r in rows if r["sonuc"] in ("tuttu", "tutmadı")]
    won = [r for r in graded if r["sonuc"] == "tuttu"]
    exp = sum(r["olasilik"] for r in graded)
    print(f"{slug}: {res['skor']} | değerlendirilen {len(graded)} / {len(rows)} | tuttu {len(won)} | beklenen {exp:.1f}")
    bands = [(0, .4), (.4, .55), (.55, .7), (.7, .84), (.84, 1.01)]
    for lo, hi in bands:
        b = [r for r in graded if lo <= r["olasilik"] < hi]
        if b:
            print(f"   %{lo*100:.0f}-{min(hi,1)*100:.0f}: {len(b):3d} öneri, tuttu {sum(r['sonuc']=='tuttu' for r in b):3d} (%{100*sum(r['sonuc']=='tuttu' for r in b)/len(b):.0f}), model ort. %{100*sum(r['olasilik'] for r in b)/len(b):.0f}")
    return rows


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
