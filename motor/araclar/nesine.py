"""Nesine bülteninden maç oranlarını okur (herkese açık bülten verisi, sitenin kendi kullandığı).
Kullanım:  python3 -I nesine.py <takım_adı_parçası> [<takım2_parçası>]
Doğrulanmış pazar kimlikleri (MTID) — 20.11.2026:
  1  Maç Sonucu (1, X, 2)                3  Çifte Şans (1-X, 1-2, X-2)
  38 Karşılıklı Gol (Var, Yok)           7  İlk Yarı Sonucu (1, X, 2)
  9  İkinci Yarı Sonucu (1, X, 2)        5  İlk Yarı / Maç Sonucu
  11/12/13 Alt/Üst 1,5 / 2,5 / 3,5 — seçenek sırası (Alt, Üst): 516/516 maçta matematiksel olarak doğrulandı
  43 Toplam Gol aralığı                   268 Handikaplı Maç Sonucu (SOV = handikap)
Diğer kimlikler (korner, kart, takım alt/üst, yarı alt/üst …) doğrulanmadan KULLANILMAZ; ham hâlleriyle listelenir.
Ek istatistik kaynağı: https://istatistik.nesine.com/<C>/ozet (puan tablosu, son maçlar, kadrolar, korner & kart, hakem).
"""
import json, sys, subprocess, os, tempfile
AD = {1: ("Maç Sonucu", ["1", "X", "2"]), 3: ("Çifte Şans", ["1-X", "1-2", "X-2"]), 38: ("Karşılıklı Gol", ["Var", "Yok"]),
      7: ("İlk Yarı Sonucu", ["1", "X", "2"]), 9: ("İkinci Yarı Sonucu", ["1", "X", "2"]),
      11: ("Alt/Üst", ["Alt", "Üst"]), 12: ("Alt/Üst", ["Alt", "Üst"]), 13: ("Alt/Üst", ["Alt", "Üst"]),
      5: ("İY/MS", ["1/1", "1/X", "1/2", "X/1", "X/X", "X/2", "2/1", "2/X", "2/2"]), 268: ("Handikaplı MS", ["1", "X", "2"])}

def bulten():
    f = os.path.join(tempfile.gettempdir(), "nesine_bulten.json")
    subprocess.run(["curl", "-s", "-m", "40", "-A", "Mozilla/5.0", "-H", "Referer: https://www.nesine.com/",
                    "https://cdnbulten.nesine.com/api/bulten/getprebultenfull", "-o", f], check=True)
    return json.load(open(f))["sg"]["EA"]

def bul(ea, a, b=None):
    a = a.lower(); b = b.lower() if b else None
    return [e for e in ea if e.get("HN") and (a in (e["HN"] + " " + e["AN"]).lower()) and (not b or b in (e["HN"] + " " + e["AN"]).lower())]

def marj(oca):
    return sum(1 / x["O"] for x in oca if x["O"] > 1) - 1

if __name__ == "__main__":
    ea = bulten()
    for e in bul(ea, *sys.argv[1:3]):
        print(f"== {e['HN']} - {e['AN']} | {e['D']} {e['T']} TSİ | maç kodu {e['C']} | istatistik: https://istatistik.nesine.com/{e['C']}/ozet")
        for m in sorted(e.get("MA", []), key=lambda m: (m["MTID"] not in AD, m["MTID"], m.get("SOV", 0))):
            o = [x["O"] for x in m.get("OCA", [])]
            if m["MTID"] in AD:
                ad, et = AD[m["MTID"]]
                sov = f" {m['SOV']:+g}" if m["MTID"] == 268 else (f" {m['SOV']:g}" if m["MTID"] in (11, 12, 13) else "")
                print(f"   {ad}{sov}: " + " | ".join(f"{et[i] if i < len(et) else i+1} {x}" for i, x in enumerate(o)) + f"   (marj %{marj(m['OCA'])*100:.1f})")
            else:
                print(f"   [doğrulanmamış MTID {m['MTID']} SOV {m.get('SOV')}] {o}")
