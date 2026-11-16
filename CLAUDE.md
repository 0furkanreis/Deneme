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
