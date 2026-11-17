"""Maç önü tam katalog değerlendirme motoru.

Kullanım:  python3 motor/motor.py motor/maclar/<mac>.json
Çıktı:     analizler/<mac>-tam.json ve analizler/<mac>-tam.md

Monte Carlo simülasyonu: her maç 99 zaman diliminde (1. yarı 45 dk + 2 dk uzatma,
2. yarı 45 dk + 5 dk uzatma) gol, korner, sarı/kırmızı kart, penaltı olayları
olarak simüle edilir. Katalogdaki her seçenek bu simülasyonlar üzerinden hesaplanır.
"""
import json, sys, os, re
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------- zaman dilimleri
HALF = np.array([1] * 47 + [2] * 50)
MIN = np.array(list(range(45)) + [44, 44] + list(range(45, 90)) + [89] * 5)  # dakika (0 tabanlı; uzatmalar 45. ve 90. dakikaya sayılır)
STOP2 = np.arange(97) >= 92  # 2. yarı uzatma dilimleri
NS = len(HALF)


def w_shape(first_share, ramp=0.25):
    """Yarı içinde hafif artan yoğunluk, 1. yarı payı first_share."""
    w = np.zeros(NS)
    for h, share in ((1, first_share), (2, 1 - first_share)):
        idx = np.where(HALF == h)[0]
        x = np.linspace(0, 1, len(idx))
        v = 1 + ramp * x
        w[idx] = share * v / v.sum()
    return w


def win(lo, hi):
    """[lo, hi) dakika aralığı; 1. yarı uzatması 45, 2. yarı uzatması 90 sayılır."""
    return (MIN >= lo) & (MIN < hi)


# ---------------------------------------------------------------- simülasyon
class Sim:
    def __init__(self, cfg, n=120_000, seed=7):
        rng = np.random.default_rng(seed)
        self.n = n
        self.cfg = cfg
        T = {}
        for side in ("ev", "dep"):
            t = cfg[side]
            pen_rate = t.get("penalti_kazanma", 0.07 + 0.04 * t["beklenen_gol"])
            lam = t["beklenen_gol"]
            og = 0.035 * lam
            open_lam = max(0.02, lam - pen_rate * 0.77 - og)
            wg = w_shape(t.get("ilk_yari_gol_payi", cfg.get("ilk_yari_gol_payi", 0.44)))
            T[side] = dict(
                g_open=rng.poisson(open_lam * wg, size=(n, NS)).astype(np.int8),
                og=rng.poisson(og * wg, size=(n, NS)).astype(np.int8),
                pen=rng.poisson(pen_rate * wg, size=(n, NS)).astype(np.int8),
                c=rng.poisson(t.get("korner", 4.8) * w_shape(0.47, 0.15), size=(n, NS)).astype(np.int8),
                y=rng.poisson(t.get("sari_kart", 1.9) * w_shape(0.36, 0.6), size=(n, NS)).astype(np.int8),
                rd=rng.poisson(t.get("direkt_kirmizi", 0.035) * w_shape(0.4, 0.6), size=(n, NS)).astype(np.int8),
                r2=rng.poisson(t.get("ikinci_sari", 0.03) * w_shape(0.25, 1.0), size=(n, NS)).astype(np.int8),
            )
            pen = T[side]["pen"]
            scored = rng.binomial(pen, 0.77).astype(np.int8)
            T[side]["pen_goal"] = scored
            T[side]["pen_miss"] = (pen - scored).astype(np.int8)
        # goller (kendi kalesine goller lehine yazılan takıma)
        for side in ("ev", "dep"):
            t = T[side]
            t["g"] = t["g_open"] + t["pen_goal"] + t["og"]
            t["r"] = t["rd"] + t["r2"]
            t["yy"] = t["y"] + t["r2"]  # ikinci sarı da sarı karttır
        self.T = T
        self.rng = rng
        self._goal_details()
        self._players()
        self.var = rng.poisson(cfg.get("var_ort", 0.22), n) + rng.binomial(
            self.tot("pen") + self.tot("r"), 0.45)

    # --- yardımcılar
    def cnt(self, side, kind, mask=None):
        a = self.T[side][kind]
        return a.sum(1) if mask is None else a[:, mask].sum(1)

    def tot(self, kind, mask=None):
        return self.cnt("ev", kind, mask) + self.cnt("dep", kind, mask)

    def first_event(self, kind, mask=None):
        """0: yok, 1: ev, 2: dep (aynı dilimde ise yazı-tura)."""
        e, d = self.T["ev"][kind], self.T["dep"][kind]
        if mask is not None:
            e, d = e[:, mask], d[:, mask]
        fe = np.where(e.any(1), e.argmax(1), 999)
        fd = np.where(d.any(1), d.argmax(1), 999)
        coin = self.rng.random(self.n) < 0.5
        out = np.where(fe < fd, 1, np.where(fd < fe, 2, np.where(fe == 999, 0, np.where(coin, 1, 2))))
        return out, np.minimum(fe, fd)

    def last_event(self, kind, mask=None):
        e, d = self.T["ev"][kind], self.T["dep"][kind]
        if mask is not None:
            e, d = e[:, mask], d[:, mask]
        k = e.shape[1]
        le = np.where(e.any(1), k - 1 - e[:, ::-1].argmax(1), -1)
        ld = np.where(d.any(1), k - 1 - d[:, ::-1].argmax(1), -1)
        coin = self.rng.random(self.n) < 0.5
        return np.where(le > ld, 1, np.where(ld > le, 2, np.where(le == -1, 0, np.where(coin, 1, 2))))

    def path(self):
        ce = np.cumsum(self.T["ev"]["g"], 1)
        cd = np.cumsum(self.T["dep"]["g"], 1)
        return ce, cd

    # --- gol türleri (simülasyon başına sayılar)
    def _goal_details(self):
        rng, n = self.rng, self.n
        d = {}
        for side in ("ev", "dep"):
            go = self.cnt(side, "g_open")
            head = rng.binomial(go, 0.17)
            rest = go - head
            fk = rng.binomial(rest, 0.04)
            rest2 = rest - fk
            outside = rng.binomial(rest2, 0.11) + fk
            bicycle = rng.binomial(rest2, 0.003)
            sixyard = rng.binomial(go - outside, 0.2)
            d[side] = dict(open=go, head=head, fk=fk, outside=outside, bicycle=bicycle, six=sixyard,
                           assisted=rng.binomial(go, 0.72))
        d["gk_assist"] = rng.binomial(d["ev"]["assisted"] + d["dep"]["assisted"], 0.006)
        self.D = d
        # ilk golün şekli
        side, slot = self.first_event("g")
        kinds = np.full(n, "Gol yok", dtype=object)
        for s_i, s in ((1, "ev"), (2, "dep")):
            m = side == s_i
            idx = np.where(m)[0]
            sl = slot[idx]
            og = self.T[s]["og"][idx, sl] > 0
            pen = self.T[s]["pen_goal"][idx, sl] > 0
            u = rng.random(len(idx))
            k = np.where(og, "Kendi kalesine", np.where(pen, "Penaltı",
                         np.where(u < 0.17, "Kafa", np.where(u < 0.17 + 0.033, "Serbest vuruş", "Şut"))))
            kinds[idx] = k
        self.first_goal_kind = kinds

    # --- oyuncular
    def _players(self):
        rng, n = self.rng, self.n
        self.P = {}
        for side in ("ev", "dep"):
            plist = self.cfg[side].get("oyuncular", [])
            go = self.cnt(side, "g_open")
            pg = self.cnt(side, "pen_goal")
            pm = self.cnt(side, "pen_miss")
            shares = [p.get("gol_payi", 0) for p in plist]
            other = max(0.0, 1 - sum(shares))
            # kalan payı 6 sıradan oyuncuya böl (hat-trick hesabı için)
            probs = shares + [other / 6] * 6
            # vektörel multinomial
            res = np.zeros((n, len(probs)), dtype=np.int16)
            left = go.astype(np.int64)
            rem = 1.0
            for k, p in enumerate(probs[:-1]):
                q = 0 if rem <= 0 else min(1, p / rem)
                x = rng.binomial(left, q)
                res[:, k] = x
                left = left - x
                rem -= p
            res[:, -1] = left
            # penaltıcı
            taker = next((i for i, p in enumerate(plist) if p.get("penaltici")), None)
            if taker is not None:
                res[:, taker] += pg
            else:
                res[:, len(plist)] += pg  # sıradan oyuncu
            # asistler
            ast_sh = [p.get("asist_payi", 0) for p in plist]
            assisted = self.D[side]["assisted"]
            ares = np.zeros((n, len(plist)), dtype=np.int16)
            left = assisted.astype(np.int64)
            rem = 1.0
            for k, p in enumerate(ast_sh):
                q = 0 if rem <= 0 else min(1, p / rem)
                x = rng.binomial(left, q)
                ares[:, k] = x
                left = left - x
                rem -= p
            # yarı dağılımı: oyuncunun gollerini takımın yarı payına göre böl
            h1_share = self.cnt(side, "g", HALF == 1) / np.maximum(1, self.cnt(side, "g"))
            for i, p in enumerate(plist):
                g = res[:, i].astype(np.int64)
                g1 = rng.binomial(g, np.clip(h1_share, 0, 1))
                cards = rng.random(n) < p.get("kart_ihtimali", 0.12)
                self.P[p["ad"]] = dict(side=side, g=g, g1=g1, g2=g - g1, a=ares[:, i],
                                       pen_miss=(rng.binomial(pm, 1.0) if p.get("penaltici") else np.zeros(n, int)),
                                       head=rng.binomial(g, 0.17), outside=rng.binomial(g, 0.12),
                                       fk=rng.binomial(g, 0.03), right=rng.binomial(g, p.get("sag_ayak", 0.55)),
                                       six=rng.binomial(g, 0.2), pen=(np.minimum(g, pg) if p.get("penaltici") else np.zeros(n, int)),
                                       card=cards, red=rng.random(n) < p.get("kart_ihtimali", 0.12) * 0.05,
                                       first10=rng.binomial(g, 0.1), info=p)
            self.P[side + "_hattrick"] = (res >= 3).any(1)
            self.P[side + "_res"] = res


# ---------------------------------------------------------------- pazar tanımları
def fmt_line(x):
    t = f"{x:.2f}".rstrip("0").rstrip(".")
    return t.replace(".", ",")


class Ev:
    def __init__(self, sim, cfg):
        self.s = sim
        self.cfg = cfg
        s = sim
        self.H, self.A = s.cnt("ev", "g"), s.cnt("dep", "g")
        h1 = HALF == 1
        self.H1, self.A1 = s.cnt("ev", "g", h1), s.cnt("dep", "g", h1)
        self.H2, self.A2 = self.H - self.H1, self.A - self.A1
        self.E, self.D = cfg["ev"]["ad"], cfg["dep"]["ad"]

    # temel olasılık
    def p(self, mask):
        return float(np.mean(mask))

    def res3(self, h, a, lab=None):
        e, d = (lab or (self.E, self.D))
        return [(f"1 ({e})", self.p(h > a)), ("X", self.p(h == a)), (f"2 ({d})", self.p(h < a))]

    def ou(self, x, lines, name="Toplam"):
        out = []
        for L in lines:
            out.append((f"{name} {fmt_line(L)} Üst", self.p(x > L)))
            out.append((f"{name} {fmt_line(L)} Alt", self.p(x < L)))
        return out

    def asian_ou(self, x, lines, name="Toplam"):
        out = []
        for L in lines:
            for over in (True, False):
                o = asian_fair(x, L, over)
                if o:
                    out.append((f"{name} Asya {fmt_line(L)} {'Üst' if over else 'Alt'}", o))
        return out

    def asian_hcp(self, diff, lines):
        out = []
        for L in lines:
            for side, sgn, nm in ((1, 1, self.E), (2, -1, self.D)):
                o = asian_fair(sgn * diff, -L, True)
                if o:
                    out.append((f"{nm} Asya {('+' if L > 0 else '')}{fmt_line(L)}", o))
        return out

    def hcp2(self, diff, lines):
        out = []
        for L in lines:
            out.append((f"{self.E} {('+' if L > 0 else '')}{fmt_line(L)}", self.p(diff + L > 0)))
            out.append((f"{self.D} {('+' if -L > 0 else '')}{fmt_line(-L)}", self.p(diff + L < 0)))
        return out

    def hcp3(self, diff, lines):
        out = []
        for L in lines:
            t = f"({('+' if L > 0 else '')}{L})"
            out += [(f"{self.E} {t}", self.p(diff + L > 0)), (f"X {t}", self.p(diff + L == 0)),
                    (f"{self.D} {t}", self.p(diff + L < 0))]
        return out

    def exact(self, x, top, label="gol"):
        out = [(f"{k} {label}", self.p(x == k)) for k in range(top)]
        out.append((f"{top}+ {label}", self.p(x >= top)))
        return out

    def ranges(self, x, rngs, label="gol"):
        out = []
        for lo, hi in rngs:
            nm = f"{lo}-{hi}" if hi is not None and hi != lo else (f"{lo}" if hi == lo else f"{lo}+")
            m = (x >= lo) & (x <= (hi if hi is not None else 99))
            out.append((f"{nm} {label}", self.p(m)))
        return out

    def yn(self, mask, label=""):
        return [(f"{label}Evet".strip(), self.p(mask)), (f"{label}Hayır".strip(), self.p(~mask))]


def asian_fair(x, L, over):
    """Asya çizgisi için adil orana karşılık gelen eşdeğer olasılık (1/adil oran)."""
    def outcome(line):
        d = (x - line) if over else (line - x)
        return d
    frac = round((L % 1) * 4) / 4 if L >= 0 else round(((-L) % 1) * 4) / 4
    if frac in (0.25, 0.75):
        lines = (L - 0.25, L + 0.25)
    else:
        lines = (L,)
    W = HW = HL = Ls = 0.0
    for ln in lines:
        d = outcome(ln)
        wgt = 1 / len(lines)
        W += wgt * np.mean(d > 0)
        Ls += wgt * np.mean(d < 0)
    # W ve Ls ağırlıklı; itiraz/iade kısmı otomatik olarak dışarıda
    if W <= 0:
        return None
    fair = 1 + Ls / W
    return 1 / fair


def build(ev):
    s, E, D = ev.s, ev.E, ev.D
    cfg = ev.cfg
    H, A, H1, A1, H2, A2 = ev.H, ev.A, ev.H1, ev.A1, ev.H2, ev.A2
    TG, TG1, TG2 = H + A, H1 + A1, H2 + A2
    p, yn = ev.p, ev.yn
    ce, cd = s.path()
    lead_e = (ce > cd).any(1)
    lead_d = (cd > ce).any(1)
    trail_e, trail_d = lead_d, lead_e
    fg, _ = s.first_event("g")
    lg = s.last_event("g")
    ast_e, ast_d = s.D["ev"]["assisted"], s.D["dep"]["assisted"]
    res = lambda h, a: np.where(h > a, 1, np.where(h == a, 0, 2))
    R, R1, R2 = res(H, A), res(H1, A1), res(H2, A2)
    RL = {1: "1", 0: "X", 2: "2"}
    out = {}

    def add(key, sel, note=None, conf=None):
        out[key] = dict(secimler=sel, not_=note, guven=conf)

    # ------ MAÇ SONUCU / TEMEL
    add("Maç Sonucu", ev.res3(H, A))
    add("Çifte Şans", [("1X", p(H >= A)), ("12", p(H != A)), ("X2", p(H <= A))])
    sdiv = lambda a, b: a / b if b > 0 else float("nan")
    dn = p(H != A)
    add("Beraberlikte İade", [(E, sdiv(p(H > A), dn)), (D, sdiv(p(H < A), dn))], "Beraberlikte iade; olasılık iade hariç")
    nd = p(H <= A)
    add("{EV} : Bahis Yok", [("X", sdiv(p(H == A), nd)), (D, sdiv(p(H < A), nd))], f"{E} kazanırsa iade")
    nd2 = p(H >= A)
    add("{DEP} : Bahis Yok", [(E, sdiv(p(H > A), nd2)), ("X", sdiv(p(H == A), nd2))], f"{D} kazanırsa iade")
    add("{EV} : Geriden Gelerek Kazanır", yn(trail_e & (H > A)))
    add("{DEP} : Geriden Kazanır", yn(trail_d & (A > H)))
    for key, x, y in (("{EV} : Kazanma Marjı", H, A), ("{DEP} : Kazanma Marjı", A, H)):
        m = x - y
        add(key, [("1 fark", p(m == 1)), ("2 fark", p(m == 2)), ("3 fark", p(m == 3)), ("4+ fark", p(m >= 4)),
                  ("Kazanamaz", p(m <= 0))])

    # ------ TOPLAM GOL
    L = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5]
    TL = [0.5, 1.5, 2.5, 3.5]
    AL = [1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.25]
    add("Toplam Goller", ev.ou(TG, L))
    add("{EV} : Toplam Gol", ev.ou(H, TL, E))
    add("{DEP} : Toplam Gol", ev.ou(A, TL, D))
    add("Toplam Goller Asya", ev.asian_ou(TG, AL), "Asya çizgisi: değer = 1/adil oran")
    add("{EV} : Toplam Gol Asya", ev.asian_ou(H, [0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25], E))
    add("{DEP} : Toplam Gol Asya", ev.asian_ou(A, [0.25, 0.5, 0.75, 1.0, 1.25, 1.5], D))
    t3 = []
    for k in (1, 2, 3, 4):
        t3 += [(f"{k} Alt", p(TG < k)), (f"Tam {k}", p(TG == k)), (f"{k} Üst", p(TG > k))]
    add("Toplam Gol (3-İhtimalli)", t3)
    add("Toplam Gol Tek/Çift", [("Tek", p(TG % 2 == 1)), ("Çift", p(TG % 2 == 0))])
    add("Toplam Gol (Kesin)", ev.exact(TG, 6))
    add("{EV} : Toplam Gol (Kesin)", ev.exact(H, 4))
    add("{DEP} : Toplam Gol (Kesin)", ev.exact(A, 4))
    add("Toplam Gol (Aralık)", ev.ranges(TG, [(0, 1), (2, 3), (4, 5), (6, None)]))
    add("{EV} : Toplam Gol (Aralık)", ev.ranges(H, [(0, 0), (1, 2), (3, None)]))
    add("{DEP} : Toplam Gol (Aralık)", ev.ranges(A, [(0, 0), (1, 2), (3, None)]))
    ext = [(0, 0), (1, 2), (1, 3), (2, 3), (2, 4), (3, 4), (3, 5), (4, 6), (5, None)]
    add("Toplam Gol (Genişletilmiş Gol Aralığı)", ev.ranges(TG, ext), "Sitedeki aralıklar farklı olabilir")
    add("{EV} : Toplam Gol (Genişletilmiş Aralıklar)", ev.ranges(H, [(0, 1), (1, 2), (2, 3), (3, None)]))
    add("{DEP} : Toplam Gol (Genişletilmiş Aralıklar)", ev.ranges(A, [(0, 1), (1, 2), (2, 3), (3, None)]))
    add("Kesin Gol Sayısı", ev.exact(TG, 7))
    for k in (1, 2, 3, 4):
        add(f"Maçta {k} Gol Olur", yn(TG == k))
    add("En Az Bir Takım Üst Gol Atar", [(f"En az bir takım {fmt_line(l)} Üst", p((H > l) | (A > l))) for l in (0.5, 1.5, 2.5)])
    add("{EV} : Asist Yapar. Toplam", ev.ou(ast_e, [0.5, 1.5, 2.5], f"{E} asist"))
    add("{DEP} : Asist Yapar. Toplam", ev.ou(ast_d, [0.5, 1.5], f"{D} asist"))

    # ------ KARŞILIKLI GOL
    btts = (H > 0) & (A > 0)
    add("Her İki Takımda Gol Atar", yn(btts))
    add("Her İki Takım da 2 veya Daha Fazla Gol Atar", yn((H >= 2) & (A >= 2)))
    add("{EV} : Gol Atar", yn(H > 0))
    add("{DEP} : Gol Atar", yn(A > 0))
    add("Karşılıklı Gol ve Toplam Goller 2.5", [("KG Var & Üst", p(btts & (TG > 2))), ("KG Var & Alt", p(btts & (TG < 3))),
                                               ("KG Yok & Üst", p(~btts & (TG > 2))), ("KG Yok & Alt", p(~btts & (TG < 3)))])
    add("Her İki Yarıda da Karşılıklı Gol", yn((H1 > 0) & (A1 > 0) & (H2 > 0) & (A2 > 0)))

    # ------ HANDİKAP
    diff = H - A
    add("Gol Handikapı", ev.hcp2(diff, [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5]))
    add("Goller Asya Handikapı", ev.asian_hcp(diff, [-2.0, -1.75, -1.5, -1.25, -1.0, -0.75, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5]))
    add("Gol Handikapı (3-İhtimalli)", ev.hcp3(diff, [-3, -2, -1, 1, 2, 3]))

    # ------ KOMBİNE
    def combo_res(extra, labels):
        o = []
        for r in (1, 0, 2):
            for m, lab in zip(extra, labels):
                o.append((f"{RL[r]} & {lab}", p((R == r) & m)))
        return o
    add("{EV} Gol Atar ve Maç Sonucu", combo_res([H > 0, H == 0], [f"{E} gol atar", f"{E} gol atamaz"]))
    add("{DEP} Gol Atar ve Maç Sonucu", combo_res([A > 0, A == 0], [f"{D} gol atar", f"{D} gol atamaz"]))
    add("Maç Sonucu ve Karşılıklı Gol", combo_res([btts, ~btts], ["KG Var", "KG Yok"]))
    dc = {"1X": H >= A, "12": H != A, "X2": H <= A}
    add("Çifte Şans ve Karşılıklı Gol", [(f"{k} & {l}", p(v & m)) for k, v in dc.items() for m, l in ((btts, "KG Var"), (~btts, "KG Yok"))])
    for l in (1.5, 2.5, 3.5, 4.5):
        add(f"Maç Sonucu ve Toplam Gol {l}", combo_res([TG > l, TG < l], [f"{fmt_line(l)} Üst", f"{fmt_line(l)} Alt"]))
    add("Sonuç ve {EV} : Toplam Gol", combo_res([H > 1.5, H < 1.5], [f"{E} 1,5 Üst", f"{E} 1,5 Alt"]))
    add("Sonuç ve {DEP} : Toplam Gol", combo_res([A > 0.5, A < 0.5], [f"{D} 0,5 Üst", f"{D} 0,5 Alt"]))
    add("Sonuç veya Toplam Gol", [(f"{RL[r]} veya {fmt_line(2.5)} {ou}", p((R == r) | m)) for r in (1, 0, 2) for m, ou in ((TG > 2.5, "Üst"), (TG < 2.5, "Alt"))])
    add("Maç Sonucu ve Toplam Gol (Kesin)", [(f"{RL[r]} & {k} gol", p((R == r) & (TG == k))) for r in (1, 0, 2) for k in range(6)])
    add("Sonuç ve Toplam Gol (Genişletilmiş Aralık)", [(f"{RL[r]} & {lo}-{hi} gol", p((R == r) & (TG >= lo) & (TG <= hi))) for r in (1, 0, 2) for lo, hi in ((1, 2), (1, 3), (2, 3), (2, 4), (3, 4), (3, 5))])
    add("Çifte Şans ve Toplam Gol (Genişletilmiş Aralık)", [(f"{k} & {lo}-{hi} gol", p(v & (TG >= lo) & (TG <= hi))) for k, v in dc.items() for lo, hi in ((1, 2), (1, 3), (2, 3), (2, 4))])
    scores = sorted({(i, j) for i in range(5) for j in range(5)}, key=lambda t: -p((H == t[0]) & (A == t[1])))[:6]
    add("Sonuç veya Doğru Skor", [(f"{RL[r]} veya {i}-{j}", p((R == r) | ((H == i) & (A == j)))) for r in (1, 0, 2) for i, j in scores if res(np.array(i), np.array(j)) != r])
    add("Her İki Yarı Toplam Gol Kombinasyonu", [(f"İY {a} 1,5 & 2Y {b} 1,5", p(m1 & m2)) for a, m1 in (("Alt", TG1 < 2), ("Üst", TG1 > 1)) for b, m2 in (("Alt", TG2 < 2), ("Üst", TG2 > 1))])
    add("Farklı Kombineler", [("1 & 2Y gol olur", p((R == 1) & (TG2 > 0))), ("2 & 2Y gol olur", p((R == 2) & (TG2 > 0))),
                              (f"{E} her iki yarıda gol & 1", p((H1 > 0) & (H2 > 0) & (R == 1))),
                              (f"{D} her iki yarıda gol & 2", p((A1 > 0) & (A2 > 0) & (R == 2)))],
        "Sitedeki kombinasyon içerikleri farklı olabilir")
    add("Çifte Şans Kombo", [(f"{k} & {fmt_line(l)} {ou}", p(v & m)) for k, v in dc.items() for l in (1.5, 2.5, 3.5) for m, ou in ((TG > l, "Üst"), (TG < l, "Alt"))])
    add("İlk Yarı/Maç Sonucu ve Toplam Gol", [(f"{RL[a]}/{RL[b]} & 2,5 {ou}", p((R1 == a) & (R == b) & m)) for a in (1, 0, 2) for b in (1, 0, 2) for m, ou in ((TG > 2.5, "Üst"), (TG < 2.5, "Alt"))])

    # ------ GOL SÜRESİ
    add("Her İki Yarıda Gol Olur", yn((TG1 > 0) & (TG2 > 0)))
    add("İlk Golü Atacak Takım", [(E, p(fg == 1)), ("Gol yok", p(fg == 0)), (D, p(fg == 2))])
    add("Son Golü Atacak Takım", [(E, p(lg == 1)), ("Gol yok", p(lg == 0)), (D, p(lg == 2))])
    fk = s.first_goal_kind
    add("İlk Golün Atılma Şekli", [(k, p(fk == k)) for k in ("Şut", "Kafa", "Penaltı", "Serbest vuruş", "Kendi kalesine", "Gol yok")])
    _, fslot = s.first_event("g")
    fmin = np.where(fslot < 999, MIN[np.minimum(fslot, NS - 1)], -1)
    def bins(fm, edges):
        o = []
        for lo, hi in edges:
            o.append((f"{lo + 1}-{hi}" + (" (+uz.)" if hi in (45, 90) else "") + " dk", p((fm >= lo) & (fm < hi))))
        o.append(("Gol yok", p(fm < 0)))
        return o
    add("1. Gol Zamanı", [("1-27 dk", p((fmin >= 0) & (fmin < 27))), ("28-90 dk", p(fmin >= 27)), ("Gol yok", p(fmin < 0))], "Sınır 27. dk varsayıldı")
    tens = [(i, i + 10) for i in range(0, 80, 10)] + [(80, 90)]
    for key, side in (("{EV} : 1. Gol Zamanı (10 dk. Ara)", "ev"), ("{DEP} : 1. Gol Zamanı (10 dk. Ara)", "dep")):
        g = s.T[side]["g"]
        fs = np.where(g.any(1), g.argmax(1), -1)
        fm = np.where(fs >= 0, MIN[np.maximum(fs, 0)], -1)
        add(key, bins(fm, tens))
    add("1. Gol Zamanı (15 dk.)", bins(fmin, [(0, 15), (15, 30), (30, 45), (45, 60), (60, 75), (75, 90)]))
    add("İlk Golü Atacak Takım ve Maç Sonucu", [(f"İlk gol {E} & {RL[r]}", p((fg == 1) & (R == r))) for r in (1, 0, 2)] + [(f"İlk gol {D} & {RL[r]}", p((fg == 2) & (R == r))) for r in (1, 0, 2)] + [("Gol yok", p(fg == 0))])
    add("İlk Golü Atacak Takım ve 1. Yarı Sonucu", [(f"İlk gol {E} & İY {RL[r]}", p((fg == 1) & (R1 == r))) for r in (1, 0, 2)] + [(f"İlk gol {D} & İY {RL[r]}", p((fg == 2) & (R1 == r))) for r in (1, 0, 2)] + [("Gol yok", p(fg == 0))])
    add("İlk Golü Atacak Takım ve 2. Yarı Sonucu", [(f"İlk gol {E} & 2Y {RL[r]}", p((fg == 1) & (R2 == r))) for r in (1, 0, 2)] + [(f"İlk gol {D} & 2Y {RL[r]}", p((fg == 2) & (R2 == r))) for r in (1, 0, 2)] + [("Gol yok", p(fg == 0))])

    # ------ DOĞRU SKOR
    def cs(h, a, top=5):
        o = [(f"{i}-{j}", p((h == i) & (a == j))) for i in range(top) for j in range(top)]
        o.append(("Diğer", p((h >= top) | (a >= top))))
        return sorted(o, key=lambda t: -t[1])
    add("Doğru Skor", cs(H, A))
    reached = []
    for i in range(4):
        for j in range(4):
            if i == 0 and j == 0:
                continue
            m = ((ce == i) & (cd == j)).any(1) | ((i == 0) & (j == 0))
            reached.append((f"{i}-{j} herhangi bir anda", p(m)))
    add("Herhangi Bir Zamanda Doğru Skor", sorted(reached, key=lambda t: -t[1]))
    groups = {f"{E} 1-0/2-0/2-1": [(1, 0), (2, 0), (2, 1)], f"{E} 3-0/3-1/4-0": [(3, 0), (3, 1), (4, 0)],
              "0-0/1-1": [(0, 0), (1, 1)], f"{D} 0-1/0-2/1-2": [(0, 1), (0, 2), (1, 2)], f"{D} 0-3/1-3/0-4": [(0, 3), (1, 3), (0, 4)],
              "2-2/3-3": [(2, 2), (3, 3)]}
    add("Skor Kombinasyonları", [(k, p(np.any([(H == i) & (A == j) for i, j in v], 0))) for k, v in groups.items()], "Sitedeki gruplar farklı olabilir")
    htft = []
    for a in range(3):
        for b in range(3):
            for c in range(a, 5):
                for d in range(b, 5):
                    htft.append((f"İY {a}-{b} / MS {c}-{d}", p((H1 == a) & (A1 == b) & (H == c) & (A == d))))
    add("1.Yarı/Maç Skoru", sorted(htft, key=lambda t: -t[1])[:12])
    add("Maç Skoru Beraberlik (0-0 hariç)", yn((H == A) & (H > 0)))

    # ------ KAZANMA ŞEKLİ
    for key, x, y in (("{EV} Kesin Gol Farkıyla Kazanır", H, A), ("{DEP} : Kesin Gol Farkıyla Kazanır", A, H)):
        add(key, [(f"{k} farkla", p(x - y == k)) for k in (1, 2, 3)] + [("4+ farkla", p(x - y >= 4))])
    for key, x, y in (("{EV} Kazanır ve Kesin Gol Atar", H, A), ("{DEP} Kazanır ve Kesin Gol Atar", A, H)):
        add(key, [(f"Kazanır & {k} gol", p((x > y) & (x == k))) for k in (1, 2, 3)] + [("Kazanır & 4+ gol", p((x > y) & (x >= 4)))])
    add("{EV} Gol Yemeden Kazanır", yn((H > 0) & (A == 0)))
    add("{DEP} Gol Yemeden Kazanır", yn((A > 0) & (H == 0)))
    add("{EV} İki veya Üç Gol Farkla Kazanır", yn((H - A >= 2) & (H - A <= 3)))
    add("{DEP} İki veya Üç Gol Farkla Kazanır", yn((A - H >= 2) & (A - H <= 3)))
    add("{EV} Bir Gol Farkla Kazanır veya Berabere Kalır", yn((H - A == 1) | (H == A)))
    add("{DEP} Bir Gol Farkla Kazanır veya Berabere Kalır", yn((A - H == 1) | (H == A)))
    add("{EV} En Az Bir Yarıyı Kazanır", yn((H1 > A1) | (H2 > A2)))
    add("{DEP} En Az Bir Yarıyı Kazanır", yn((A1 > H1) | (A2 > H2)))
    add("{EV} İlk Yarıyı Kazanır ve Maçı Kazanamaz", yn((H1 > A1) & (H <= A)))
    add("{DEP} İlk Yarıyı Kazanır ve Maçı Kazanamaz", yn((A1 > H1) & (A <= H)))

    # ------ YARILAR
    h1m = HALF == 1
    for hn, hh, aa, tg, mask, pre in (("1", H1, A1, TG1, h1m, "1. Yarı"), ("2", H2, A2, TG2, ~h1m, "2. Yarı")):
        rr = res(hh, aa)
        d = hh - aa
        fgx, _ = s.first_event("g", mask)
        lgx = s.last_event("g", mask)
        tl = [0.5, 1.5, 2.5]
        items = {
            f"{pre} Sonucu" if hn == "1" else "2. Yarı Sonucu": ev.res3(hh, aa),
            f"{pre} Çifte Şans": [("1X", p(hh >= aa)), ("12", p(hh != aa)), ("X2", p(hh <= aa))],
            f"{pre} Toplam Gol": ev.ou(tg, tl),
            f"{pre} Karşılıklı Gol": yn((hh > 0) & (aa > 0)),
            f"{pre} Gol Handikapı": ev.hcp2(d, [-1.5, -0.5, 0.5, 1.5]),
            f"{pre} Gol Handikapı 3 İhtimalli": ev.hcp3(d, [-2, -1, 1, 2]),
            f"{pre} : Sonuç ve Her İki Takımda Gol Atar": [(f"{RL[r]} & KG {k}", p((rr == r) & (m))) for r in (1, 0, 2) for m, k in (((hh > 0) & (aa > 0), "Var"), (~((hh > 0) & (aa > 0)), "Yok"))],
            f"{pre} Toplam Gol Aralığı": ev.ranges(tg, [(0, 0), (1, 1), (2, 3), (4, None)]),
            f"{pre} {{EV}} Toplam Gol (Aralık)": ev.ranges(hh, [(0, 0), (1, 1), (2, None)]),
            f"{pre} {{DEP}} Toplam Gol (Aralık)": ev.ranges(aa, [(0, 0), (1, 1), (2, None)]),
            f"{pre} Toplam Gol (Genişletilmiş Aralıklar)": ev.ranges(tg, [(0, 1), (1, 2), (2, 3), (3, None)]),
            f"{pre} Takım 1 : Toplam Gol (Genişletilmiş Aralıklar)": ev.ranges(hh, [(0, 0), (0, 1), (1, 2), (2, None)]),
            f"{pre} Toplam Gol (Kesin)": ev.exact(tg, 4),
            f"{pre} {{EV}} Toplam Gol (Kesin)": ev.exact(hh, 3),
            f"{pre} {{DEP}} Toplam Gol (Kesin)": ev.exact(aa, 3),
            f"{pre} {{EV}} Kazanır Kesin Gol Farkla": [(f"{k} farkla", p(d == k)) for k in (1, 2)] + [("3+ farkla", p(d >= 3))],
            f"{pre} {{DEP}} Kazanır Kesin Gol Farkla": [(f"{k} farkla", p(-d == k)) for k in (1, 2)] + [("3+ farkla", p(-d >= 3))],
            f"{pre} {{EV}} Sıfıra Karşı Kazanır": yn((hh > 0) & (aa == 0)),
            f"{pre} {{DEP}} Sıfıra Karşı Kazanır": yn((aa > 0) & (hh == 0)),
            f"{pre} İlk Golü Atacak Takım": [(E, p(fgx == 1)), ("Gol yok", p(fgx == 0)), (D, p(fgx == 2))],
            f"{pre} Son Golü Atacak Takım": [(E, p(lgx == 1)), ("Gol yok", p(lgx == 0)), (D, p(lgx == 2))],
            f"{pre} Doğru Skor": cs(hh, aa, 4),
        }
        if hn == "1":
            items.update({
                "1. Yarı 1. Takım Toplam Gol": ev.ou(hh, [0.5, 1.5], E),
                "1. Yarı 2. Takım Toplam Gol": ev.ou(aa, [0.5, 1.5], D),
                "1. Yarı {EV} Toplam Gol Asya": ev.asian_ou(hh, [0.5, 0.75, 1.0], E),
                "1. Yarı {DEP} Toplam Gol Asya": ev.asian_ou(aa, [0.25, 0.5], D),
                "1. Yarı Goller Asya Handikapı": ev.asian_hcp(d, [-1.0, -0.75, -0.5, -0.25, 0.0, 0.25, 0.5]),
                "1. Yarı Toplam Gol Asya": ev.asian_ou(tg, [0.75, 1.0, 1.25]),
                "1. Yarı : Toplam Gol (3-İhtimalli)": [("1 Alt", p(tg < 1)), ("Tam 1", p(tg == 1)), ("1 Üst", p(tg > 1))],
                "1. Yarı Takım 2 : Toplam Gol (Genişletilmiş Aralıklar)": ev.ranges(aa, [(0, 0), (0, 1), (1, 2), (2, None)]),
            })
        else:
            items.update({
                "2. Yarı {EV} Toplam Gol": ev.ou(hh, [0.5, 1.5], E),
                "2. Yarı {DEP} Toplam Gol": ev.ou(aa, [0.5, 1.5], D),
                "2. Yarı Takım 2 : Toplam Gol Sayısı (Genişletilmiş Aralıklar)": ev.ranges(aa, [(0, 0), (0, 1), (1, 2), (2, None)]),
            })
        for k, v in items.items():
            add(k, v)

    # ------ YARI KARŞILAŞTIRMA
    add("1. Yarı/2. Yarı Karşılıklı Gol", [(f"İY {a} / 2Y {b}", p(m1 & m2)) for a, m1 in (("Var", (H1 > 0) & (A1 > 0)), ("Yok", ~((H1 > 0) & (A1 > 0)))) for b, m2 in (("Var", (H2 > 0) & (A2 > 0)), ("Yok", ~((H2 > 0) & (A2 > 0))))])
    add("1. Yarı veya Maç Sonucu", [(f"İY {RL[r]} veya MS {RL[r]}", p((R1 == r) | (R == r))) for r in (1, 0, 2)])
    add("İlk Yarı/Maç Sonucu", [(f"{RL[a]}/{RL[b]}", p((R1 == a) & (R == b))) for a in (1, 0, 2) for b in (1, 0, 2)])
    add("1. Yarı/2. Yarı Sonucu", [(f"{RL[a]}/{RL[b]}", p((R1 == a) & (R2 == b))) for a in (1, 0, 2) for b in (1, 0, 2)])
    add("En Çok Gol Atılan Yarı", [("1. Yarı", p(TG1 > TG2)), ("Eşit", p(TG1 == TG2)), ("2. Yarı", p(TG2 > TG1))])
    add("En Çok Gol Atılan Yarı : Çifte Şans", [("1. Yarı veya Eşit", p(TG1 >= TG2)), ("2. Yarı veya Eşit", p(TG2 >= TG1)), ("1. veya 2. Yarı", p(TG1 != TG2))])
    for key, x1, x2 in (("{EV} : En Çok Gol Attığı Yarı", H1, H2), ("{DEP} : En Çok Gol Attığı Yarı", A1, A2)):
        add(key, [("1. Yarı", p(x1 > x2)), ("Eşit", p(x1 == x2)), ("2. Yarı", p(x2 > x1))])
    add("{EV} : Her İki Yarıda Gol Atar", yn((H1 > 0) & (H2 > 0)))
    add("{DEP} Her İki Yarıda Gol Atar", yn((A1 > 0) & (A2 > 0)))
    add("{EV} : İlk Yarıda Gol Atar", yn(H1 > 0))
    add("{DEP} İlk Yarıda Gol Atar", yn(A1 > 0))
    add("{EV} : İkinci Yarıda Gol Atar", yn(H2 > 0))
    add("{DEP} İkinci Yarıda Gol Atar", yn(A2 > 0))
    add("İlk Yarıda Gol", yn(TG1 > 0))
    add("İkinci Yarıda Gol", yn(TG2 > 0))
    add("Her İki Yarıda da 1.5 Üst Gol", yn((TG1 > 1) & (TG2 > 1)))
    add("Her İki Yarı Goller 1.5 Alt", yn((TG1 < 2) & (TG2 < 2)))
    for key, x1, x2 in (("{EV} : Gol Atar 1.Yarı/2.Yarı", H1, H2), ("{DEP} Gol Atar İlk Yarı/İkinci Yarı", A1, A2)):
        add(key, [(f"{a}/{b}", p(m1 & m2)) for a, m1 in (("Evet", x1 > 0), ("Hayır", x1 == 0)) for b, m2 in (("Evet", x2 > 0), ("Hayır", x2 == 0))])
    add("Yarıları Farklı Takımlar Kazanır", yn(((R1 == 1) & (R2 == 2)) | ((R1 == 2) & (R2 == 1))))
    add("Yarılardan En Az Birinde Beraberlik", yn((R1 == 0) | (R2 == 0)))
    dd = TG2 - TG1
    add("1.Yarı Toplam Gol'e karşı 2. Yarı Toplam Gol Handikapı", [(f"2. Yarı {('+' if l > 0 else '')}{fmt_line(l)}", p(dd + l > 0)) for l in (-1.5, -0.5, 0.5)] + [(f"1. Yarı {('+' if -l > 0 else '')}{fmt_line(-l)}", p(dd + l < 0)) for l in (-1.5, -0.5, 0.5)])

    # ------ DAKİKA ARALIKLARI
    w10 = win(0, 10)
    add("İlk 10 Dakika (00:00 - 09:59) Gol", yn(s.tot("g", w10) > 0))
    add("İlk 10 Dakika (00:00 - 09:59) Köşe Vuruşu", yn(s.tot("c", w10) > 0))
    add("{EV} : İlk 10 Dakika (00:00 - 09:59) Kornerler", ev.ou(s.cnt("ev", "c", w10), [0.5, 1.5], E))
    add("{DEP} : İlk 10 Dakika (00:00 - 09:59) Kornerler", ev.ou(s.cnt("dep", "c", w10), [0.5], D))
    add("İlk 10 Dakika (00:00 - 09:59) Sarı Kartlar", yn(s.tot("yy", w10) > 0))
    for lo_hi, lab in (((0, 15), "1-15"), ((0, 30), "1-30"), ((0, 60), "1-60"), ((0, 75), "1-75")):
        m = win(*lo_hi)
        h, a = s.cnt("ev", "g", m), s.cnt("dep", "g", m)
        add(f"{lab} Dk. Galibi", ev.res3(h, a))
        add(f"{lab} Dk. Gol Handikapı", ev.hcp2(h - a, [-1.5, -0.5, 0.5]) if lab in ("1-60", "1-75") else ev.hcp3(h - a, [-1, 1]))
        add(f"{lab} Dk. Toplam Goller", ev.ou(h + a, [0.5, 1.5, 2.5] if lab in ("1-60", "1-75") else [0.5, 1.5]))
        add(f"{lab} Dk. {{EV}} Toplam Goller", ev.ou(h, [0.5, 1.5], E))
        add(f"{lab} Dk. {{DEP}} Toplam Goller", ev.ou(a, [0.5], D))
        if lab in ("1-15",):
            add("1-15 Dk. İki Takım Gol Atar", yn((h > 0) & (a > 0)))
        if lab in ("1-60", "1-75"):
            add(f"{lab} Dk. Karşılıklı Gol", yn((h > 0) & (a > 0)))

    # ------ GOL TÜRÜ / ÖZEL
    Dt = s.D
    add("Maçta Kafa Golü Olur", yn(Dt["ev"]["head"] + Dt["dep"]["head"] > 0), conf="orta")
    add("Frikikten Gol Olur", yn(Dt["ev"]["fk"] + Dt["dep"]["fk"] > 0), conf="düşük")
    add("Rövaşata ile Gol Atılır", yn(Dt["ev"]["bicycle"] + Dt["dep"]["bicycle"] > 0), conf="düşük")
    add("Ceza Sahası Dışından Gol", yn(Dt["ev"]["outside"] + Dt["dep"]["outside"] > 0), conf="orta")
    add("Maçta Kendi Kalesine Gol Atılır", yn(s.tot("og") > 0), conf="düşük")
    add("Herhangi Bir Oyuncu Hat-trick Yapar", yn(s.P["ev_hattrick"] | s.P["dep_hattrick"]), conf="düşük")
    add("Herhangi Bir Kaleci Asist Yapar", yn(Dt["gk_assist"] > 0), conf="düşük")
    add("VAR'lar: Toplam (Yalnızca Sahada İnceleme veya Video İnceleme İşareti (TV))", ev.ou(s.var, [0.5, 1.5]), conf="düşük")

    # ------ KORNER
    cf = cfg.get("korner_guven", "düşük")
    CE, CD = s.cnt("ev", "c"), s.cnt("dep", "c")
    CT = CE + CD
    add("Kornerler : Sonuç", ev.res3(CE, CD), conf=cf)
    add("Kornerler : Toplam", ev.ou(CT, [7.5, 8.5, 9.5, 10.5, 11.5]), conf=cf)
    add("Toplam Korner : {EV}", ev.ou(CE, [3.5, 4.5, 5.5, 6.5, 7.5], E), conf=cf)
    add("Toplam Korner : {DEP}", ev.ou(CD, [1.5, 2.5, 3.5, 4.5], D), conf=cf)
    add("Kornerler : Handikap", ev.hcp2(CE - CD, [-4.5, -3.5, -2.5, -1.5, -0.5, 0.5, 1.5, 2.5]), conf=cf)
    add("Kornerler : Toplam (3-İhtimalli)", [(f"{k} Alt", p(CT < k)) for k in (9, 10)] + [(f"Tam {k}", p(CT == k)) for k in (9, 10)] + [(f"{k} Üst", p(CT > k)) for k in (9, 10)], conf=cf)
    add("Kornerler : Toplam (Aralık)", ev.ranges(CT, [(0, 8), (9, 11), (12, None)], "korner"), conf=cf)
    add("Kornerler : Tek/Çift", [("Tek", p(CT % 2 == 1)), ("Çift", p(CT % 2 == 0))], conf=cf)
    ce_c, cd_c = np.cumsum(s.T["ev"]["c"], 1), np.cumsum(s.T["dep"]["c"], 1)
    race = []
    for k in (3, 5, 7, 9):
        te = np.where((ce_c >= k).any(1), (ce_c >= k).argmax(1), 999)
        td = np.where((cd_c >= k).any(1), (cd_c >= k).argmax(1), 999)
        race += [(f"İlk {k} korner {E}", p(te < td)), (f"İlk {k} korner {D}", p(td < te)), (f"{k} kornere kimse ulaşamaz", p((te == 999) & (td == 999)))]
    add("Korner Yarışı", race, conf=cf)
    CE1, CD1 = s.cnt("ev", "c", h1m), s.cnt("dep", "c", h1m)
    add("Kornerler : 1. Yarı Sonucu", ev.res3(CE1, CD1), conf=cf)
    add("Kornerler : 1. Yarı Handikap", ev.hcp2(CE1 - CD1, [-2.5, -1.5, -0.5, 0.5]), conf=cf)
    add("Kornerler : 1. Yarı Toplam", ev.ou(CE1 + CD1, [3.5, 4.5, 5.5]), conf=cf)
    add("Kornerler : 1. Yarı {EV} Toplam", ev.ou(CE1, [1.5, 2.5, 3.5], E), conf=cf)
    add("Kornerler : 1. Yarı {DEP} Toplam", ev.ou(CD1, [0.5, 1.5], D), conf=cf)
    add("Toplam Korner : 2. Yarı", ev.ou(CT - CE1 - CD1, [4.5, 5.5, 6.5]), conf=cf)
    fc, _ = s.first_event("c")
    add("Kornerler : İlk Korner", [(E, p(fc == 1)), (D, p(fc == 2)), ("Korner yok", p(fc == 0))], conf=cf)
    lc = s.last_event("c")
    add("Kornerler : Son Korner", [(E, p(lc == 1)), (D, p(lc == 2)), ("Korner yok", p(lc == 0))], conf=cf)
    C1, C2 = CE1 + CD1, CT - CE1 - CD1
    add("En Fazla Korner Olan Yarı", [("1. Yarı", p(C1 > C2)), ("Eşit", p(C1 == C2)), ("2. Yarı", p(C2 > C1))], conf=cf)

    # ------ KART
    kf = cfg.get("kart_guven", "düşük")
    YE, YD = s.cnt("ev", "yy"), s.cnt("dep", "yy")
    RE, RD = s.cnt("ev", "r"), s.cnt("dep", "r")
    PE, PD = 10 * YE + 25 * RE, 10 * YD + 25 * RD
    PT = PE + PD
    YE1, YD1 = s.cnt("ev", "yy", h1m), s.cnt("dep", "yy", h1m)
    RE1, RD1 = s.cnt("ev", "r", h1m), s.cnt("dep", "r", h1m)
    PE1, PD1 = 10 * YE1 + 25 * RE1, 10 * YD1 + 25 * RD1
    note_pts = "Sarı = 10, kırmızı = 25 puan varsayıldı"
    add("Kartlar : Puan : Sonuç", ev.res3(PE, PD), note_pts, kf)
    add("Kartlar : Puan Handikapı", ev.hcp2(PE - PD, [-15.5, -5.5, 5.5, 15.5]), note_pts, kf)
    add("Kartlar : Toplam Puan", ev.ou(PT, [25.5, 35.5, 45.5, 55.5]), note_pts, kf)
    add("Kartlar : {EV} : Toplam Kart Puanı", ev.ou(PE, [5.5, 15.5, 25.5], E), note_pts, kf)
    add("Kartlar : {DEP} : Toplam Kart Puanı", ev.ou(PD, [5.5, 15.5, 25.5, 35.5], D), note_pts, kf)
    add("Kartlar : Toplam (Aralıklar)", ev.ranges(PT, [(0, 20), (21, 40), (41, 60), (61, None)], "puan"), note_pts, kf)
    add("Kartlar : 1. Yarı : Toplam Kart Puanı", ev.ou(PE1 + PD1, [5.5, 15.5, 25.5]), note_pts, kf)
    add("Kartlar : 1. Yarı : {EV} : Toplam Kart Puanı", ev.ou(PE1, [5.5, 15.5], E), note_pts, kf)
    add("Kartlar : 1. Yarı : {DEP} : Toplam Kart Puanı", ev.ou(PD1, [5.5, 15.5], D), note_pts, kf)
    add("Kartlar : 2. Yarı : {EV} : Toplam Kart Puanı", ev.ou(PE - PE1, [5.5, 15.5], E), note_pts, kf)
    add("Kartlar : 2. Yarı : {DEP} : Toplam Kart Puanı", ev.ou(PD - PD1, [5.5, 15.5, 25.5], D), note_pts, kf)
    RT = RE + RD
    add("Direkt Kırmızı Kart", yn(s.tot("rd") > 0), conf=kf)
    YT1 = YE1 + YD1 + RE1 + RD1
    YT2 = YE + YD + RE + RD - YT1
    add("Her İki Yarıda Kart Olur", yn((YT1 > 0) & (YT2 > 0)), conf=kf)
    add("Her İki Takım da Kırmızı Kart Alır", yn((RE > 0) & (RD > 0)), conf=kf)
    add("Her İki Takım da Kart Alır", yn((YE + RE > 0) & (YD + RD > 0)), conf=kf)
    add("Her İki Takım da 2 veya Daha Fazla Kart Görür", yn((YE + RE >= 2) & (YD + RD >= 2)), conf=kf)
    add("Her İki Takım da Her İki Yarıda Kart Alır", yn((YE1 + RE1 > 0) & (YD1 + RD1 > 0) & (YE + RE - YE1 - RE1 > 0) & (YD + RD - YD1 - RD1 > 0)), conf=kf)
    s.T["ev"]["k"] = s.T["ev"]["yy"] + s.T["ev"]["rd"]
    s.T["dep"]["k"] = s.T["dep"]["yy"] + s.T["dep"]["rd"]
    fkk, _ = s.first_event("k")
    lkk = s.last_event("k")
    add("İlk Kartı Görecek Takım", [(E, p(fkk == 1)), (D, p(fkk == 2)), ("Kart yok", p(fkk == 0))], conf=kf)
    add("Son Kartı Görecek Takım", [(E, p(lkk == 1)), (D, p(lkk == 2)), ("Kart yok", p(lkk == 0))], conf=kf)
    PEN = s.tot("pen")
    add("Maçta Penaltı, Kırmızı Kart ve Kendi Kalesine Gol Olur", yn((PEN > 0) & (RT > 0) & (s.tot("og") > 0)), conf="düşük")
    st = STOP2
    add("İkinci Yarı Uzatma Dakikalarında Kart Gösterilir (90+ dak)", yn(s.tot("k", st) > 0), conf=kf)
    add("İkinci Yarının Uzatma Dakikalarında Kırmızı Kart veya Gol Olur (90+ dakika)", yn((s.tot("r", st) + s.tot("g", st)) > 0), conf=kf)
    add("Toplam Kırmızı Kartlar", ev.ou(RT, [0.5, 1.5]), conf=kf)
    add("{EV} : Kırmızı Kart", yn(RE > 0), conf=kf)
    add("{DEP} : Kırmızı Kart", yn(RD > 0), conf=kf)
    add("1. Yarı : Kırmızı Kart", yn(RE1 + RD1 > 0), conf=kf)
    add("2. Yarı : Kırmızı Kart", yn(RT - RE1 - RD1 > 0), conf=kf)
    # sarı kart
    add("Sarı Kartlar : Sonuç", ev.res3(YE, YD), conf=kf)
    add("Sarı Kartlar : Çifte Şans", [("1X", p(YE >= YD)), ("12", p(YE != YD)), ("X2", p(YE <= YD))], conf=kf)
    add("Sarı Kartlar : Handikap", ev.hcp2(YE - YD, [-1.5, -0.5, 0.5, 1.5]), conf=kf)
    YT = YE + YD
    add("Sarı Kartlar : Toplam", ev.ou(YT, [2.5, 3.5, 4.5, 5.5]), conf=kf)
    add("Sarı Kartlar : {EV} : Toplam", ev.ou(YE, [0.5, 1.5, 2.5], E), conf=kf)
    add("Sarı Kartlar : {DEP} : Toplam", ev.ou(YD, [0.5, 1.5, 2.5, 3.5], D), conf=kf)
    add("Sarı Kartlar : 1. Yarı Sonucu", ev.res3(YE1, YD1), conf=kf)
    add("Sarı Kartlar : 1. Yarı Handikap", ev.hcp2(YE1 - YD1, [-0.5, 0.5]), conf=kf)
    add("Sarı Kartlar : 1. Yarı : Toplam", ev.ou(YE1 + YD1, [0.5, 1.5, 2.5]), conf=kf)
    add("Sarı Kartlar : 1. Yarı {EV} Toplam", ev.ou(YE1, [0.5, 1.5], E), conf=kf)
    add("Sarı Kartlar : 1. Yarı {DEP} Toplam", ev.ou(YD1, [0.5, 1.5], D), conf=kf)
    add("Sarı Kartlar : 2. Yarı Sonuç", ev.res3(YE - YE1, YD - YD1), conf=kf)
    add("Sarı Kartlar : 2. Yarı Handikap", ev.hcp2((YE - YE1) - (YD - YD1), [-0.5, 0.5]), conf=kf)
    add("Sarı Kartlar : 2. Yarı : Toplam", ev.ou(YT - YE1 - YD1, [1.5, 2.5, 3.5]), conf=kf)
    add("Sarı Kartlar : 2. Yarı : {EV} Toplam", ev.ou(YE - YE1, [0.5, 1.5], E), conf=kf)
    fy, _ = s.first_event("yy")
    ly = s.last_event("yy")
    add("Sarı Kartlar : İlk Sarı Kartı Görür", [(E, p(fy == 1)), (D, p(fy == 2)), ("Sarı kart yok", p(fy == 0))], conf=kf)
    add("Sarı Kartlar : Son Sarı Kartı Görür", [(E, p(ly == 1)), (D, p(ly == 2)), ("Sarı kart yok", p(ly == 0))], conf=kf)

    # ------ PENALTI
    pf = "düşük"
    PEe, PEd = s.cnt("ev", "pen"), s.cnt("dep", "pen")
    add("Maçta Penaltı Olur", yn(PEN > 0), conf=pf)
    add("{EV} : Penaltı Kazanır", yn(PEe > 0), conf=pf)
    add("{DEP} : Penaltı Kazanır", yn(PEd > 0), conf=pf)
    add("İki Takım da Penaltı Kazanır", yn((PEe > 0) & (PEd > 0)), conf=pf)
    add("Maçta İki Penaltı Olur", yn(PEN >= 2), conf=pf)
    add("1. Yarı : Penaltı", yn(s.tot("pen", h1m) > 0), conf=pf)
    add("Penaltıdan Gol Atar", yn(s.tot("pen_goal") > 0), conf=pf)
    add("Penaltı Kaçırır", yn(s.tot("pen_miss") > 0), conf=pf)
    add("Penaltı ve Kırmızı Kart", yn((PEN > 0) & (RT > 0)), conf=pf)
    add("Maçta Penaltı veya Kırmızı Kart Olur", yn((PEN > 0) | (RT > 0)), conf=pf)

    # ------ OYUNCULAR
    players = {k: v for k, v in s.P.items() if isinstance(v, dict)}
    of = "düşük"
    def pl(fn, label_fmt="{}"):
        o = [(label_fmt.format(nm), p(fn(d))) for nm, d in players.items()]
        return sorted(o, key=lambda t: -t[1])
    if players:
        add("Herhangi Bir Zamanda Gol Atar", pl(lambda d: d["g"] > 0), conf=of)
        # ilk/son golcü
        firsts = {}
        for nm, d in players.items():
            team_first = fg == (1 if d["side"] == "ev" else 2)
            share = d["info"].get("gol_payi", 0)
            firsts[nm] = (team_first, share)
        add("İlk Golcü", sorted([(nm, p(tf) * sh * 0.97) for nm, (tf, sh) in firsts.items()], key=lambda t: -t[1]) + [("Gol yok", p(TG == 0))], "Takımın ilk golü × oyuncu payı", of)
        add("İlk Golcü Çifte Şans", sorted([(f"{nm} ilk golü veya ikinci golü", min(1, p(tf) * sh * 1.8)) for nm, (tf, sh) in firsts.items()], key=lambda t: -t[1]), "Yaklaşık", of)
        add("Son Golcü", sorted([(nm, p(lg == (1 if players[nm]["side"] == "ev" else 2)) * sh * 0.97) for nm, (tf, sh) in firsts.items()], key=lambda t: -t[1]), "Yaklaşık", of)
        for key, sd, kind in (("{EV} : İlk Golü Atar", "ev", "first"), ("{DEP} : İlk Golü Atar", "dep", "first"), ("{EV} : Son Golcü", "ev", "last"), ("{DEP} : Son Golü Atar", "dep", "last")):
            g = s.cnt(sd, "g")
            add(key, sorted([(nm, p(g > 0) * d["info"].get("gol_payi", 0)) for nm, d in players.items() if d["side"] == sd], key=lambda t: -t[1]), "Takımın ilk/son golünü atan oyuncu (yaklaşık)", of)
        add("Oyuncu En Az 2 Gol Atar", pl(lambda d: d["g"] >= 2), conf=of)
        add("Oyuncu En Az 3 Gol Atar", pl(lambda d: d["g"] >= 3), conf=of)
        add("Oyuncu 4 veya Daha Çok Gol Atar", pl(lambda d: d["g"] >= 4), conf=of)
        names = list(players)
        pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]]
        add("Herhangi Bir Zaman Gol Atar Çifte Şans", sorted([(f"{a} veya {b}", p((players[a]["g"] > 0) | (players[b]["g"] > 0))) for a, b in pairs], key=lambda t: -t[1])[:8], conf=of)
        add("Her İki Oyuncu da Herhangi Bir Zamanda Gol Atar", sorted([(f"{a} ve {b}", p((players[a]["g"] > 0) & (players[b]["g"] > 0))) for a, b in pairs], key=lambda t: -t[1])[:8], conf=of)
        for l in (1.5, 2.5, 3.5):
            add(f"2 Oyuncu Toplamda Üst {l} Gol Atar", sorted([(f"{a} + {b}", p(players[a]["g"] + players[b]["g"] > l)) for a, b in pairs], key=lambda t: -t[1])[:6], conf=of)
        add("Oyuncu 1. Yarıda Gol Atar", pl(lambda d: d["g1"] > 0), conf=of)
        add("Oyuncu 2. Yarıda Gol Atar", pl(lambda d: d["g2"] > 0), conf=of)
        add("Oyuncu Her İki Yarıda da Gol Atar", pl(lambda d: (d["g1"] > 0) & (d["g2"] > 0)), conf=of)
        add("İlk 10 Dakikada Gol Atar", pl(lambda d: d["first10"] > 0), conf=of)
        add("Oyuncu Penaltıdan Gol Atar", pl(lambda d: d["pen"] > 0), conf=of)
        add("Oyuncu Ceza Sahası Dışından Gol Atar", pl(lambda d: d["outside"] > 0), conf=of)
        add("Oyuncu Kale Sahası İçinden Gol Atar", pl(lambda d: d["six"] > 0), conf=of)
        add("Oyuncu Kafa Golü Atar", pl(lambda d: d["head"] > 0), conf=of)
        add("Oyuncu Serbest Vuruştan Gol Atar", pl(lambda d: d["fk"] > 0), conf=of)
        add("Oyuncu Sağ Ayağıyla Gol Atar", pl(lambda d: d["right"] > 0), conf=of)
        def teamres(d, kind):
            mine = R == (1 if d["side"] == "ev" else 2)
            opp = R == (2 if d["side"] == "ev" else 1)
            return {"win": mine, "opp": opp, "draw": R == 0}[kind]
        add("Oyuncu Gol Atar ve Takımı Kazanır", pl(lambda d: (d["g"] > 0) & teamres(d, "win")), conf=of)
        add("Oyuncu Gol Atar ve Rakip Takım Kazanır", pl(lambda d: (d["g"] > 0) & teamres(d, "opp")), conf=of)
        add("Oyuncu Gol Atar ve Maç Berabere Biter", pl(lambda d: (d["g"] > 0) & teamres(d, "draw")), conf=of)
        add("Oyuncu Asist Yapar", pl(lambda d: d["a"] > 0), conf=of)
        add("Oyuncu Gol Atar veya Asist Yapar", pl(lambda d: (d["g"] > 0) | (d["a"] > 0)), conf=of)
        add("Oyuncu Gol Atar veya Asist Yapar (Çifte Şans)", sorted([(f"{a} veya {b} gol/asist", p((players[a]["g"] + players[a]["a"] + players[b]["g"] + players[b]["a"]) > 0)) for a, b in pairs], key=lambda t: -t[1])[:6], conf=of)
        add("Oyuncu Gol Atar ve Asist Yapar", pl(lambda d: (d["g"] > 0) & (d["a"] > 0)), conf=of)
        add("Gol Asisti Yapar Çifte Şans", sorted([(f"{a} veya {b} asist", p((players[a]["a"] + players[b]["a"]) > 0)) for a, b in pairs], key=lambda t: -t[1])[:6], conf=of)
        add("Oyuncu Penaltı Kaçırır", pl(lambda d: d["pen_miss"] > 0), conf=of)
        add("Penaltı Kazandıran Oyuncu", [], "Oyuncu bazlı penaltı verisi yok", of)
        add("Oyuncu Kart Görür", pl(lambda d: d["card"]), "Oyuncunun kart ihtimali girdiden", of)
        add("Oyuncu Kart Görür Çifte Şans", sorted([(f"{a} veya {b}", p(players[a]["card"] | players[b]["card"])) for a, b in pairs], key=lambda t: -t[1])[:6], conf=of)
        add("Oyuncu Sarı Kart Görür", pl(lambda d: d["card"]), conf=of)
        add("Kart Görecek İlk Oyuncu", [], "Oyuncu sıralaması için yeterli veri yok", of)
        add("Son Kartı Görecek Oyuncu", [], "Oyuncu sıralaması için yeterli veri yok", of)
        add("Oyundan Uzaklaştırılır", pl(lambda d: d["red"]), conf=of)
    # oyuncu istatistikleri
    stats_keys = ["Oyuncu Kaleyi Bulan Şutlar", "Oyuncu Şutları", "Oyuncu Pasları", "Oyuncu Pas Denemeleri",
                  "Oyuncunun Yaptığı Fauller", "Oyuncuya Faul Yapılır", "Oyuncu Topa Müdahaleler", "Oyuncu Ofsayta Düşer",
                  "Kaleci Kurtarışları", "En Çok Pas Veren Oyuncu", "En Çok Faul Yapan Oyuncu",
                  "Oyuncu 1. Yarıda Kaleyi Bulan Şutlar", "Oyuncu 2. Yarıda Kaleyi Bulan Şutlar",
                  "Oyuncu Her İki Yarıda Kaleyi Bulan Şutlar", "Oyuncu Ceza Sahası Dışından Çektiği Şutlar",
                  "Oyuncu Ceza Sahası Dışından Kaleyi Bulan Şutlar", "Oyuncu Kafayla Kaleyi Bulan Şutlar",
                  "Oyuncu Sağ Ayakla Kaleyi Bulan Şutlar"]
    # kaleci kurtarışları: rakibin isabetli şutları - gol
    rng = s.rng
    for side, opp, nm in (("ev", "dep", E), ("dep", "ev", D)):
        lam_opp = cfg[opp]["beklenen_gol"]
        sot_nongoal = rng.poisson(lam_opp * cfg.get("kurtaris_carpani", 2.3), s.n)
        out.setdefault("_kurtaris", {})[nm] = sot_nongoal
    kk = out.pop("_kurtaris")
    add("Kaleci Kurtarışları", [(f"{nm} kalecisi {fmt_line(l)} {ou}", p((v > l) if ou == "Üst" else (v < l))) for nm, v in kk.items() for l in (1.5, 2.5, 3.5, 4.5) for ou in ("Üst", "Alt")],
        "Rakibin beklenen golünden türetildi", "düşük")
    for k in stats_keys:
        if k not in out:
            ps = [pp for pp in cfg["ev"].get("oyuncular", []) + cfg["dep"].get("oyuncular", []) if "istatistik" in pp]
            sel = []
            for pp in ps:
                st_ = pp["istatistik"]
                key_map = {"Oyuncu Kaleyi Bulan Şutlar": "isabetli_sut", "Oyuncu Şutları": "sut"}
                if k in key_map and key_map[k] in st_:
                    v = rng.poisson(st_[key_map[k]], s.n)
                    for l in (0.5, 1.5, 2.5):
                        sel.append((f"{pp['ad']} {fmt_line(l)} Üst", p(v > l)))
            add(k, sorted(sel, key=lambda t: -t[1]), None if sel else "Oyuncu istatistiği (90 dk başına) bulunamadı; değerlendirilmedi", "düşük")
    return out


# ---------------------------------------------------------------- seçim ve rapor
GUVEN_KAT = {"gol": 1.0, "gol-yari": 0.95, "gol-zaman": 0.85, "korner": 0.75, "kart": 0.7, "penalti": 0.6, "ozel": 0.5, "oyuncu": 0.55}


def pick(sel):
    """Önerilen seçim: adil oranı ≥ 1,20 (olasılık ≤ %83) olanlar içinde en olası."""
    if not sel:
        return None, None
    best_any = max(sel, key=lambda t: t[1])
    cand = [t for t in sel if t[1] <= 0.835]
    rec = max(cand, key=lambda t: t[1]) if cand else best_any
    if rec[1] < 0.40 and best_any[1] > 0.835:
        rec = best_any  # olası tüm seçimler zayıfsa güçlü olanı göster
    return rec, best_any


def main(path):
    cfg = json.load(open(path, encoding="utf-8"))
    cat = json.load(open(os.path.join(ROOT, "bahis-katalogu", "katalog.json"), encoding="utf-8"))
    sim = Sim(cfg)
    ev = Ev(sim, cfg)
    res = build(ev)
    E, D = cfg["ev"]["ad"], cfg["dep"]["ad"]
    rows, missing = [], []
    for c in cat["kategoriler"]:
        for item in c["secenekler"]:
            key = item
            if key not in res:
                missing.append(key)
                continue
            r = res[key]
            rec, best = pick(r["secimler"])
            conf = r["guven"] or ("yüksek" if c["yontem"] in ("gol", "gol-yari") else "orta")
            rows.append(dict(kategori=c["kategori"], yontem=c["yontem"], pazar=key.replace("{EV}", E).replace("{DEP}", D),
                             oneri=rec[0] if rec else None, olasilik=round(rec[1], 4) if rec else None,
                             adil_oran=round(1 / rec[1], 2) if rec and rec[1] > 0 else None,
                             en_olasi=best[0] if best else None, en_olasi_p=round(best[1], 4) if best else None,
                             guven=conf, not_=r["not_"],
                             secimler=[(a, round(b, 4)) for a, b in r["secimler"]]))
    slug = os.path.splitext(os.path.basename(path))[0]
    outj = os.path.join(ROOT, "analizler", f"{slug}-tam.json")
    meta = {k: v for k, v in cfg.items() if k not in ("ev", "dep")}
    json.dump(dict(mac=meta, ev=E, dep=D, beklenen_gol=[cfg["ev"]["beklenen_gol"], cfg["dep"]["beklenen_gol"]],
                   simulasyon=sim.n, pazarlar=rows, eksik=missing), open(outj, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # markdown
    md = [f"# {E} – {D} · Tam katalog değerlendirmesi", "",
          f"{meta.get('organizasyon', '')} · {meta.get('tarih', '')} · {sim.n:,} simülasyon".replace(",", "."), "",
          f"Beklenen gol: {E} {cfg['ev']['beklenen_gol']} – {D} {cfg['dep']['beklenen_gol']}", "",
          "Öneri = adil oranı en az 1,20 olan seçimler içinde en olası olan. Güven: veri kalitesi.", ""]
    cur = None
    for r in rows:
        if r["kategori"] != cur:
            cur = r["kategori"]
            md += ["", f"## {cur}", "", "| Pazar | Öneri | Olasılık | Adil oran | Güven |", "|---|---|---|---|---|"]
        if r["oneri"] is None:
            md.append(f"| {r['pazar']} | — | — | — | {r['not_'] or 'veri yok'} |")
        else:
            ao = f"{r['adil_oran']:.2f}".replace(".", ",") if r["adil_oran"] else "—"
            pc = f"%{r['olasilik'] * 100:.1f}".replace(".", ",")
            md.append(f"| {r['pazar']} | {r['oneri']} | {pc} | {ao} | {r['guven']}{' · ' + r['not_'] if r['not_'] else ''} |")
    if missing:
        md += ["", "## Eşleşmeyen pazarlar", ""] + [f"- {m}" for m in missing]
    open(os.path.join(ROOT, "analizler", f"{slug}-tam.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print(f"{len(rows)} pazar değerlendirildi, {len(missing)} eşleşmedi")
    for m in missing:
        print("  EKSİK:", m)


if __name__ == "__main__":
    main(sys.argv[1])
