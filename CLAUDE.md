# Maç Önü Bahis Analizi — çalışma talimatı

Kullanıcı Türkçe konuşur; tüm yanıtlar Türkçe olmalı.

## Kalıcı bahis kataloğu

- `bahis-katalogu/katalog.json`: kullanıcının bahis sitesinde (Lord Palace) görünen **tüm bahis seçenekleri** (338 seçenek, 22 kategori). `{EV}` = ev sahibi (Takım 1), `{DEP}` = deplasman (Takım 2).
- `bahis-katalogu/kaynak-lordpalace.txt`: kullanıcının gönderdiği orijinal metin (Hollanda – Yunanistan örneği).
- Kullanıcı kataloğu bir kez gönderdi; tekrar istemeyin. Yeni seçenek gönderirse kataloğa ekleyin.

## Kullanıcı bir maç adı verdiğinde

1. **Maçı araştır (web araması):** tarih, organizasyon, son 5–10 maç formu, iç saha / deplasman gol ortalamaları, xG/xGA varsa, sakat ve cezalılar, muhtemel 11'ler, aralarındaki son maçlar, korner ve kart ortalamaları, hakem (kart eğilimi), maçın önemi / motivasyon. Kaynakları not et.
2. **Model kur:** iki takım için beklenen gol (λ) → Poisson skor matrisi. Yarı dağılımı için genel oran ≈ %45 ilk yarı / %55 ikinci yarı (takım verisi varsa onu kullan). Korner ve kartları takım ve hakem ortalamalarından ayrı modelle.
3. **Kataloğun tamamını değerlendir:** her kategori için en makul seçeneği ve olasılığını çıkar (`yontem` alanı hangi veriye dayanacağını söyler: gol, gol-yari, gol-zaman, korner, kart, penalti, ozel, oyuncu).
   - `ozel` (rövaşata, VAR sayısı vb.) ve çoğu `oyuncu` pazarı yüksek belirsizlik taşır; yalnızca güçlü veri varsa öner.
4. **Sunum:** en mantıklı 1 seçenek (gerekçeli), 2–3 alternatif, kategori kategori özet tablo, kaçınılması gerekenler. Kullanıcı oran verdiyse adil oranla karşılaştır (değer = olasılık × oran − 1).
5. Kesin sonuç garantisi verilmez; olasılık olarak sun.
6. Analizi `analizler/YYYY-AA-GG-ev-dep.md` olarak kaydet ve analiz sayfasını güncelle.

## Tam katalog motoru (338 seçeneğin hepsi)

1. `motor/maclar/<slug>.json` yaz: takım adları, `beklenen_gol`, `korner`, `sari_kart`, isteğe bağlı `oyuncular` (gol_payi, asist_payi, kart_ihtimali, penaltici), `korner_guven`/`kart_guven`. Örnekler klasörde.
2. `python3 motor/motor.py motor/maclar/<slug>.json` → `analizler/<slug>-tam.json` ve `-tam.md` (120.000 Monte Carlo simülasyonu; 338 pazarın tamamı).
3. Sayfa verisi: `veri/maclar.json` dizinine maçı ekle (ana öneri, gerekçe, riskler, kaynaklar) ve `veri/<slug>.json` ince sürümünü üret (bkz. git geçmişi: `-tam.json` → `{ev,dep,beklenen_gol,simulasyon,pazarlar:[{k,y,p,g,n,s}]}`).
4. Sayfa: `sayfa/mac-onu.html`, yayın adresi https://claude.ai/artifact/UYrg8ESS8tYYVNpMHhi1CE (`veri/*.json` dosyalarıyla birlikte yayımlanır).
- Oyuncu istatistik pazarları (şut, pas, faul vb.) oyuncu başına 90 dk verisi girilmeden değerlendirilmez.
- Ağ erişimi sınırsız (17.11'den beri). SofaScore ve FBref otomatik erişimi kendileri engelliyor (403).

## Araştırma kuralı: "bulamadım" yok
Kullanıcı açıkça istedi: her eksik bilgi için tüm kaynaklar sırayla taranır, tek kaynakta durulmaz.
1. FotMob API: `api/data/matches?date=YYYYMMDD`, `api/data/matchDetails?matchId=`. infoBox.Referee.stats → hakemin maç başı sarı/kırmızı/penaltı/faul ortalaması; teamForm → son 5 maçın her biri için matchDetails (korner, kart, xG); lineup; h2h; oddspoll Facts.
2. Transfermarkt: hakem profili (`/profil/schiedsrichter/<id>`, arama `schnellsuche?query=`), kadro, sakatlıklar.
3. Flashscore, footballwebpages.co.uk (alt ligler), worldfootball.net, soccerway, lig resmi siteleri.
4. WebSearch (standard, gerekirse extended) farklı dillerde (TR, EN, maçın ülkesinin dili).
5. Lord Palace sayfası (lp4.js ile kaydırarak): oranlar + sitenin gösterdiği puan durumu ve form.
Veri gerçekten hiçbir kaynakta yoksa hangi kaynakların denendiği yazılır.

## Çok kaynaklı analiz (kullanıcı isteği: tek siteye / tek ölçüye bağlı kalma)
Her öneri en az 3 bağımsız kaynakla çapraz kontrol edilir ve cevapta kaynak kaynak gösterilir:
- **İstatistik:** FotMob + en az bir başkası (Flashscore, Soccerway, Understat, Statarea, Maçkolik, Sporx, ESPN, BBC; alt ligde Football Web Pages).
- **Oran (en değerli kontrol):** Lord Palace oranı diğer bahisçilerle karşılaştırılır: Oddsportal (çok bahisçi ortalaması, `search/<takım>/` → maç sayfası), Pinnacle (keskin piyasa), Nesine/İddaa. Lord Palace oranı piyasa ortalamasından belirgin yüksekse gerçek değer adayıdır.
- **Önizleme/tahmin siteleri:** Sports Mole, Squawka, tips.gg vb. (görüş olarak, veri değil).
- Erişim: curl 403 veren siteler `motor/araclar/render.js <url> <çıktı>` (Playwright) ile denenir. Lord Palace: `motor/araclar/lp4.js <klasör> <url>`.
- Oddsportal lig sayfası (`/football/<bölge>/<lig>/`) maç satırında piyasa ortalaması 1X2'yi gösterir; `motor/araclar/oddsportal.js` maç detay sekmelerini dener. Lord Palace 1X2 marjı ~%10, piyasa ~%4-5 (bkz. `analizler/lord-palace-marj.md`).
- Erişilebilirlik (18.11): Oddsportal, Betexplorer, Pinnacle, Nesine, İddaa, Flashscore, Soccerway, Understat, Statarea, Livescore, Maçkolik, Sporx 200; Forebet, Footystats, WhoScored, Soccerstats, Oddschecker, Betfair curl'e 403.
