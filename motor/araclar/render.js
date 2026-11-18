// Kullanım: node render.js <url> <çıktı.txt> [bekleme_ms] — sayfayı normal tarayıcı gibi açar, görünen metni ve bağlantıları kaydeder
const { chromium } = require('playwright'); const fs = require('fs');
(async () => {
  const [url, out, wait] = process.argv.slice(2);
  const b = await chromium.launch(); const p = await b.newPage({ userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36', locale: 'en-GB' });
  try { await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 }); } catch (e) { console.log('goto', e.message.split('\n')[0]); }
  await p.waitForTimeout(+(wait || 7000));
  for (const t of ['Accept', 'I Accept', 'Agree', 'Kabul', 'Accept All', 'Allow all']) { try { await p.getByRole('button', { name: t }).first().click({ timeout: 800 }); } catch (e) {} }
  const txt = await p.evaluate(() => document.body.innerText);
  const links = await p.evaluate(() => [...document.querySelectorAll('a')].map(a => a.innerText.trim().replace(/\s+/g, ' ') + ' => ' + a.href).filter(x => x.length < 300));
  fs.writeFileSync(out, txt + '\n\n#LINKS\n' + links.join('\n'));
  console.log('ok', p.url(), txt.length);
  await b.close();
})();
