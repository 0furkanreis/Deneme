"""Beklenen golleri site oranlarından türetir (takım 0,5 gol Üst/Alt pazarlarından, marj çıkarılarak).

Kullanım: python3 motor/kalibre.py motor/maclar/<slug>.json oranlar/<slug>.txt
Maç ayar dosyasındaki ev/dep beklenen_gol değerlerini piyasa değerleriyle günceller
(eski değerler 'model_beklenen_gol' alanına yazılır).
"""
import json, sys, math, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oran import Site


def lam_from_line(line, over, under):
    """x,5 çizgisindeki marjsız Üst olasılığından Poisson λ (ikiye bölme ile)."""
    p_over = (1 / over) / (1 / over + 1 / under)
    k = int(line)  # Üst = X >= k+1
    def p_ge(lam):
        return 1 - sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k + 1))
    lo, hi = 0.01, 8.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if p_ge(mid) < p_over else (lo, mid)
    return (lo + hi) / 2


def main(cfg_path, site_path):
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    S = Site(site_path)
    for side in ("ev", "dep"):
        nm = cfg[side]["ad"]
        tbl = S.ou(f"{nm} : Toplam Gol")
        lines = sorted({ln for ln, _ in tbl if ln % 1 == 0.5})
        if not lines:
            print(f"{nm}: takım gol çizgisi bulunamadı, model değeri korunuyor")
            continue
        lams = [lam_from_line(ln, tbl[(ln, "Üst")], tbl[(ln, "Alt")]) for ln in lines]
        lam = sum(lams) / len(lams)
        cfg[side].setdefault("model_beklenen_gol", cfg[side]["beklenen_gol"])
        cfg[side]["beklenen_gol"] = round(lam, 3)
        print(f"{nm}: piyasa λ {lam:.2f} (model {cfg[side]['model_beklenen_gol']})")
    cfg["kalibrasyon"] = "Beklenen goller site oranlarından (takım gol çizgilerinin ortalaması)"
    json.dump(cfg, open(cfg_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
