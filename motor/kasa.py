"""Kasa hesabı: python3 motor/kasa.py  → analizler/kasa.md üretir ve özet yazar."""
import json, os
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
k = json.load(open(os.path.join(R, "analizler", "kasa.json"), encoding="utf-8"))
nakit = k["baslangic"]; bekleyen = []
satir = ["# Kasa", "", f"Başlangıç: {k['baslangic']:,.2f} ₺", "", "| # | Açıklama | Yatırılan | Oran | Dönüş | Durum | Nakit (sonra) |", "|---|---|---|---|---|---|---|"]
for h in k["hareketler"]:
    nakit -= h["yatirilan"]
    if h["durum"] == "kazandı": nakit += h["donus"]
    elif h["durum"] == "iade": nakit += h["yatirilan"]
    elif h["durum"] == "bekliyor": bekleyen.append(h)
    o = f"{h['oran']:.2f}" if h.get("oran") else "—"
    satir.append(f"| {h['no']} | {h['aciklama']} | {h['yatirilan']:,.2f} ₺ | {o} | {h['donus']:,.2f} ₺ | {h['durum']} | {nakit:,.2f} ₺ |")
bek = sum(h["yatirilan"] for h in bekleyen); pot = sum(h["donus"] for h in bekleyen)
satir += ["", f"**Kullanılabilir nakit:** {nakit:,.2f} ₺", f"**Bekleyen kuponlarda:** {bek:,.2f} ₺ (hepsi tutarsa {pot:,.2f} ₺ döner)",
          f"**Toplam (bekleyenler yatırılan kadar sayılırsa):** {nakit + bek:,.2f} ₺ · net {nakit + bek - k['baslangic']:+,.2f} ₺"]
open(os.path.join(R, "analizler", "kasa.md"), "w", encoding="utf-8").write("\n".join(satir).replace(",", "X").replace(".", ",").replace("X", ".") + "\n")
print(f"nakit {nakit:.2f} | bekleyen {bek:.2f} | potansiyel {pot:.2f} | toplam {nakit+bek:.2f} | net {nakit+bek-k['baslangic']:+.2f}")
