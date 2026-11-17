"""Beklenen golleri site oranlarından türetir (takım 0,5 gol Üst/Alt pazarlarından, marj çıkarılarak).

Kullanım: python3 motor/kalibre.py motor/maclar/<slug>.json oranlar/<slug>.txt
Maç ayar dosyasındaki ev/dep beklenen_gol değerlerini piyasa değerleriyle günceller
(eski değerler 'model_beklenen_gol' alanına yazılır).
"""
import json, sys, math, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oran import Site


def lam_from_ou05(over, under):
    p_over = (1 / over) / (1 / over + 1 / under)
    return -math.log(1 - p_over)


def main(cfg_path, site_path):
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    S = Site(site_path)
    for side in ("ev", "dep"):
        nm = cfg[side]["ad"]
        tbl = S.ou(f"{nm} : Toplam Gol")
        if (0.5, "Üst") not in tbl:
            print(f"{nm}: 0,5 çizgisi bulunamadı, model değeri korunuyor")
            continue
        lam = lam_from_ou05(tbl[(0.5, "Üst")], tbl[(0.5, "Alt")])
        cfg[side].setdefault("model_beklenen_gol", cfg[side]["beklenen_gol"])
        cfg[side]["beklenen_gol"] = round(lam, 3)
        print(f"{nm}: piyasa λ {lam:.2f} (model {cfg[side]['model_beklenen_gol']})")
    cfg["kalibrasyon"] = "Beklenen goller site oranlarından (takım 0,5 gol pazarı)"
    json.dump(cfg, open(cfg_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
