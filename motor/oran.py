"""Lord Palace sayfasından okunan oranları motorun olasılıklarıyla karşılaştırır.

Kullanım: python3 motor/oran.py <slug> <site_satirlari.txt>
Çıktı:    analizler/<slug>-oranlar.json ve ekrana değer tablosu (değer = olasılık × oran − 1)
"""
import json, sys, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUM = re.compile(r"^[+-]?\d+(\.\d+)?$")


class Site:
    def __init__(self, path):
        self.L = [l for l in open(path, encoding="utf-8").read().split("\n") if l and not l.startswith("Canlı bahis")]

    def idx(self, title):
        try:
            return self.L.index(title)
        except ValueError:
            return None

    def multi(self, title, n):
        """title, n etiket, n oran → {etiket: oran}"""
        i = self.idx(title)
        if i is None:
            return {}
        labs, vals = self.L[i + 1:i + 1 + n], self.L[i + 1 + n:i + 1 + 2 * n]
        if not all(NUM.match(v) for v in vals):
            return {}
        return {a: float(b) for a, b in zip(labs, vals)}

    def ou(self, title):
        """title, Üst, Alt, (çizgi, üst, alt)* → {(çizgi,'Üst'):oran,...}"""
        i = self.idx(title)
        if i is None or self.L[i + 1:i + 3] != ["Üst", "Alt"]:
            return {}
        out, j = {}, i + 3
        while j + 2 < len(self.L) and all(NUM.match(x) for x in self.L[j:j + 3]):
            ln = float(self.L[j])
            out[(ln, "Üst")], out[(ln, "Alt")] = float(self.L[j + 1]), float(self.L[j + 2])
            j += 3
        return out

    def yn(self, title):
        d = self.multi(title, 2)
        return d


def fl(x):
    t = f"{x:.2f}".rstrip("0").rstrip(".")
    return t.replace(".", ",")


def compare(slug, site_path):
    pred = json.load(open(os.path.join(ROOT, "analizler", f"{slug}-tam.json"), encoding="utf-8"))
    E, D = pred["ev"], pred["dep"]
    P = {r["pazar"]: dict(r["secimler"]) for r in pred["pazarlar"]}
    S = Site(site_path)
    rows = []

    def add(name, mk, lab, odd):
        p = P.get(mk, {}).get(lab)
        if p is None or odd is None or p != p:
            return
        rows.append(dict(secim=name, pazar=mk, etiket=lab, olasilik=p, oran=odd, deger=p * odd - 1))

    # 3'lü sonuç pazarları
    for site_t, mk in (("Maç Sonucu", "Maç Sonucu"), ("1.Yarı Sonucu", "1. Yarı Sonucu"), ("2. Yarı Sonucu", "2. Yarı Sonucu"),
                       ("Kornerler : Sonuç", "Kornerler : Sonuç"), ("Sarı Kartlar: Sonuç", "Sarı Kartlar : Sonuç")):
        d = S.multi(site_t, 3)
        if d:
            v = list(d.values())
            pre = "" if mk == "Maç Sonucu" else mk.split(" Sonuc")[0].split(" :")[0] + " "
            add(f"{pre}1", mk, f"1 ({E})", v[0]); add(f"{pre}X", mk, "X", v[1]); add(f"{pre}2", mk, f"2 ({D})", v[2])
    d = S.multi("Çifte Şans", 3)
    for k, v in d.items():
        add(f"Çifte Şans {k}", "Çifte Şans", k, v)
    d = S.multi("Beraberlikte İade", 2)
    for k, v in d.items():
        add(f"Beraberlikte İade {k}", "Beraberlikte İade", k, v)
    # alt/üst pazarları
    for site_t, mk, lab_fmt in (("Toplam Goller", "Toplam Goller", "Toplam {l} {s}"),
                                (f"{E} : Toplam Gol", f"{E} : Toplam Gol", E + " {l} {s}"),
                                (f"{D} : Toplam Gol", f"{D} : Toplam Gol", D + " {l} {s}"),
                                ("1. Yarı Toplam Gol", "1. Yarı Toplam Gol", "Toplam {l} {s}"),
                                ("2.Yarı Toplam Gol", "2. Yarı Toplam Gol", "Toplam {l} {s}"),
                                ("Kornerler : Toplam", "Kornerler : Toplam", "Toplam {l} {s}"),
                                (f"Toplam Korner : {E}", f"Toplam Korner : {E}", E + " {l} {s}"),
                                (f"Toplam Korner : {D}", f"Toplam Korner : {D}", D + " {l} {s}"),
                                ("Sarı Kartlar: Toplam", "Sarı Kartlar : Toplam", "Toplam {l} {s}"),
                                (f"Sarı Kartlar: {E} : Toplam", f"Sarı Kartlar : {E} : Toplam", E + " {l} {s}"),
                                (f"Sarı Kartlar: {D} : Toplam", f"Sarı Kartlar : {D} : Toplam", D + " {l} {s}")):
        for (ln, sd), v in S.ou(site_t).items():
            if ln % 1 == 0.5:
                add(f"{mk} {fl(ln)} {sd}", mk, lab_fmt.format(l=fl(ln), s=sd), v)
    # evet/hayır pazarları (site başlığı → motor pazarı)
    yn = {"Her iki takımda gol atar": "Her İki Takımda Gol Atar", "Her iki yarıda gol olur": "Her İki Yarıda Gol Olur",
          f"{E} : Gol Atar": f"{E} : Gol Atar", f"{D} Gol Atar": f"{D} : Gol Atar",
          f"{E} Gol Yemeden Kazanır": f"{E} Gol Yemeden Kazanır", f"{D} Gol Yemeden Kazanır": f"{D} Gol Yemeden Kazanır",
          "İlk Yarıda Gol": "İlk Yarıda Gol", "İkinci Yarıda Gol": "İkinci Yarıda Gol",
          f"{E} : İlk Yarıda Gol Atar": f"{E} : İlk Yarıda Gol Atar", f"{D} İlk Yarıda Gol Atar": f"{D} İlk Yarıda Gol Atar",
          f"{E} : İkinci Yarıda Gol Atar": f"{E} : İkinci Yarıda Gol Atar", f"{D} İkinci Yarıda Gol Atar": f"{D} İkinci Yarıda Gol Atar",
          "1. Yarı Karşılıklı Gol": "1. Yarı Karşılıklı Gol", "2. Yarı Karşılıklı Gol": "2. Yarı Karşılıklı Gol",
          f"{E} En Az Bir Yarıyı Kazanır": f"{E} En Az Bir Yarıyı Kazanır"}
    for st, mk in yn.items():
        for k, v in S.yn(st).items():
            add(f"{mk} {k}", mk, k, v)
    d = S.multi("İlk Golü Atacak Takım", 3)
    if d:
        v = list(d.values())
        add(f"İlk gol {E}", "İlk Golü Atacak Takım", E, v[0]); add(f"İlk gol {D}", "İlk Golü Atacak Takım", D, v[1])
    d = S.multi("En Çok Gol Atılan Yarı", 3)
    if d:
        v = list(d.values())
        for lab, o in zip(("1. Yarı", "Eşit", "2. Yarı"), v):
            add(f"En gollü yarı {lab}", "En Çok Gol Atılan Yarı", lab, o)
    d = S.multi("Toplam Gol Tek / Çift", 2)
    for k, v in d.items():
        add(f"Toplam gol {k}", "Toplam Gol Tek/Çift", k, v)
    # oyuncu golleri
    i = S.idx("Herhangi Bir Zamanda Gol Atar")
    if i is not None:
        j = i + 1
        while j + 1 < len(S.L) and NUM.match(S.L[j + 1]):
            add(f"{S.L[j]} gol atar", "Herhangi Bir Zamanda Gol Atar", S.L[j], float(S.L[j + 1]))
            j += 2
    rows.sort(key=lambda r: -r["deger"])
    json.dump(rows, open(os.path.join(ROOT, "analizler", f"{slug}-oranlar.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(rows)} seçim karşılaştırıldı")
    print(f"{'Seçim':44s} {'model':>7s} {'oran':>5s} {'adil':>5s} {'değer':>7s}")
    for r in rows:
        print(f"{r['secim'][:44]:44s} %{r['olasilik'] * 100:5.1f} {r['oran']:5.2f} {1 / r['olasilik']:5.2f} {r['deger'] * 100:+6.1f}%")
    return rows


if __name__ == "__main__":
    compare(sys.argv[1], sys.argv[2])
