"""FotMob'dan maç özeti: hakem istatistikleri, kadrolar, h2h, son 5 maç (gol, korner, sarı, xG) ve ortalamalar.
Kullanım: python3 -I fotmob_mac.py <matchId> <çalışma_klasörü>"""
import json, subprocess, sys, os, statistics as S
mid, wd = sys.argv[1], sys.argv[2]
os.makedirs(wd, exist_ok=True)
get = lambda i, f: subprocess.run(["curl", "-s", "-m", "15", "-A", "Mozilla/5.0", f"https://www.fotmob.com/api/data/matchDetails?matchId={i}", "-o", f])
d0 = os.path.join(wd, f"m_{mid}.json"); get(mid, d0)
d = json.load(open(d0)); c = d["content"]; mf = c.get("matchFacts") or {}
D = lambda x: x if isinstance(x, dict) else {}
ib = D(mf.get("infoBox")); r = D(ib.get("Referee"))
print("TAKIMLAR", [t["name"] for t in d["header"]["teams"]], "| STAT", D(ib.get("Stadium")).get("name"), "| TUR", D(ib.get("Tournament")).get("roundName"))
print("HAKEM", r.get("text"), r.get("country"), [(s.get("type"), s.get("value"), s.get("average")) for s in r.get("stats", [])])
h = D(c.get("h2h")); print("H2H", h.get("summary"), [(m["home"]["name"], m["status"].get("scoreStr"), m["away"]["name"], m["time"]["utcTime"][:10]) for m in h.get("matches", [])[:5]])
lu = D(c.get("lineup"))
for s in ("homeTeam", "awayTeam"):
    t = D(lu.get(s)); print("KADRO", s, t.get("formation"), [p.get("name") for p in t.get("starters", [])], "| eksik:", [p.get("name") for p in (t.get("unavailable") or [])])
for f in (D(D(mf.get("poll")).get("oddspoll")).get("Facts") or []): print("BİLGİ", f.get("defaultText"))
for i, team in enumerate(mf.get("teamForm") or []):
    rows = []
    for x in team:
        fid = x["linkToMatch"].split("#")[-1]; tt = x["tooltipText"]; fp = os.path.join(wd, f"f_{fid}.json"); get(fid, fp)
        st = {}
        try:
            dd = json.load(open(fp)); mine = 0 if x["home"]["isOurTeam"] else 1
            for g in (D(D(dd["content"].get("stats")).get("Periods")).get("All") or {}).get("stats", []):
                for s in g.get("stats", []):
                    if s.get("title") in ("Corners", "Yellow cards", "Expected goals (xG)", "Shots on target") and s.get("stats") and s["stats"][0] is not None:
                        st[s["title"]] = (float(s["stats"][mine]), float(s["stats"][1 - mine]))
        except Exception:
            pass
        gf = int(tt["homeScore"] if x["home"]["isOurTeam"] else tt["awayScore"]); ga = int(tt["awayScore"] if x["home"]["isOurTeam"] else tt["homeScore"])
        rows.append((gf, ga, st)); print("FORM", i, tt["homeTeam"], tt["homeScore"], "-", tt["awayScore"], tt["awayTeam"], tt["utcTime"][:10], st)
    def m(k, j):
        v = [r[2][k][j] for r in rows if k in r[2]]; return (round(S.mean(v), 2), len(v)) if v else None
    if rows:
        print(f"ORT {i}: gol {S.mean(r[0] for r in rows):.2f}-{S.mean(r[1] for r in rows):.2f} | korner {m('Corners',0)}-{m('Corners',1)} | sarı {m('Yellow cards',0)}-{m('Yellow cards',1)} | xG {m('Expected goals (xG)',0)}-{m('Expected goals (xG)',1)}")
