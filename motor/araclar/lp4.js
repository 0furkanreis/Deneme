const { chromium, devices } = require('playwright');
const fs = require('fs');
(async () => {
  const dir = process.argv[2], url = process.argv[3];
  const b = await chromium.launch();
  const ctx = await b.newContext({ ...devices['iPhone 13'], locale: 'tr-TR' });
  const p = await ctx.newPage();
  await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await p.waitForTimeout(9000);
  try { await p.getByText('TÜMÜ', { exact: true }).first().click({ timeout: 3000 }); } catch (e) {}
  await p.waitForTimeout(2000);
  const snaps = [];
  let last = -1;
  for (let i = 0; i < 160; i++) {
    snaps.push(await p.evaluate(() => document.body.innerText));
    await p.mouse.wheel(0, 500); await p.waitForTimeout(180);
    const y = await p.evaluate(() => { const el = document.scrollingElement; let m = el.scrollTop; document.querySelectorAll('*').forEach(e => { if (e.scrollHeight > e.clientHeight + 50 && e.scrollTop > m) m = e.scrollTop; }); return m; });
    if (y === last && i > 20) break; last = y;
  }
  fs.writeFileSync(dir + '/snaps.json', JSON.stringify(snaps));
  console.log('adım', snaps.length, 'durum', (await p.evaluate(() => document.body.innerText)).slice(0, 0));
  await b.close();
})();
