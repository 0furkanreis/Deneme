// Oddsportal'dan bir maçın bahisçi oranlarını okur (normal tarayıcı gibi gezerek).
// Kullanım: node oddsportal.js <lig_sayfası_url> <ev_takımı_metni> <çıktı_klasörü>
// Maç satırına tıklar, sonra 1X2, Alt/Üst, KG ve Asya handikap sekmelerini açıp görünen metni kaydeder.
const { chromium } = require('playwright'); const fs = require('fs');
(async () => {
  const [leagueUrl, team, outDir] = process.argv.slice(2);
  const b = await chromium.launch();
  const p = await b.newPage({ userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36', locale: 'en-GB', viewport: { width: 1400, height: 2200 } });
  await p.goto(leagueUrl, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await p.waitForTimeout(6000);
  for (const t of ['I Accept', 'Accept', 'Accept All']) { try { await p.getByRole('button', { name: t }).first().click({ timeout: 800 }); } catch (e) {} }
  const row = p.locator('a', { hasText: new RegExp(team, 'i') }).filter({ hasNotText: 'h2h' });
  const n = await row.count(); let clicked = false;
  for (let i = 0; i < n && !clicked; i++) {
    const href = await row.nth(i).getAttribute('href');
    if (href && !href.includes('/h2h/') && href.split('/').filter(Boolean).length >= 4) { await p.goto(new URL(href, leagueUrl).href, { waitUntil: 'domcontentloaded' }); clicked = true; }
  }
  if (!clicked) { await row.first().click().catch(() => {}); }
  await p.waitForTimeout(6000);
  const base = p.url().split('#')[0];
  console.log('MAÇ', base);
  const tabs = { '1x2': '#1X2;2', 'alt_ust': '#over-under;2', 'kg': '#bts;2', 'asya': '#ah;2', 'cifte_sans': '#double;2' };
  for (const [k, h] of Object.entries(tabs)) {
    try { await p.goto(base + h, { waitUntil: 'domcontentloaded' }); await p.waitForTimeout(5000); } catch (e) {}
    // Alt/Üst ve Asya sayfalarında çizgiler kapalı satırlar halinde; hepsini aç
    if (k === 'alt_ust' || k === 'asya') {
      const rows = p.locator('div:has-text("Over/Under +"), div:has-text("Asian Handicap")').locator('xpath=self::*[contains(@class,"cursor-pointer")]');
      const cnt = Math.min(await rows.count(), 12);
      for (let i = 0; i < cnt; i++) { try { await rows.nth(i).click({ timeout: 1500 }); await p.waitForTimeout(700); } catch (e) {} }
    }
    fs.writeFileSync(`${outDir}/op_${k}.txt`, await p.evaluate(() => document.body.innerText));
    console.log(k, 'kaydedildi');
  }
  await b.close();
})();
