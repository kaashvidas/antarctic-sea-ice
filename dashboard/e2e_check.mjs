// One-off real browser check against the CURRENT backend (isochrone routing,
// weather-enhanced ConvLSTM). Not part of the app -- deleted after use.
import { chromium } from 'playwright';

const FRONTEND = 'http://localhost:5173';

const browser = await chromium.launch();
const page = await browser.newPage();
const consoleErrors = [];
page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push(msg.text());
});
page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`));

console.log('Loading planner...');
await page.goto(FRONTEND, { waitUntil: 'networkidle', timeout: 20000 });
await page.screenshot({ path: 'e2e_1_planner.png' });

await page.fill('input[placeholder="-65.500"]', '-58.88');
await page.fill('input[placeholder="-57.000"]', '-51.12');
await page.fill('input[placeholder="-56.500"]', '-54.88');
await page.fill('input[placeholder="-37.000"]', '-35.12');

const iceClassSelect = page.locator('select');
await iceClassSelect.selectOption('ice_strengthened');

console.log('Submitting journey (real isochrone route, expect ~20-35s)...');
const t0 = Date.now();
await page.click('button[type="submit"]');
await page.screenshot({ path: 'e2e_2_submitting.png' });

// Wait for either the report view or an error panel, real timeout generous
// enough for the real ~20-35s isochrone computation.
await Promise.race([
  page.waitForSelector('.report', { timeout: 60000 }),
  page.waitForSelector('.alert-panel', { timeout: 60000 }),
]);
const elapsed = (Date.now() - t0) / 1000;
console.log(`Response after ${elapsed.toFixed(1)}s`);

const hasReport = await page.locator('.report').count();
const hasError = await page.locator('.alert-panel').count();
console.log('report visible:', hasReport > 0, '| error visible:', hasError > 0);

if (hasError > 0) {
  console.log('ERROR TEXT:', await page.locator('.alert-panel').innerText());
}

await page.screenshot({ path: 'e2e_3_result.png', fullPage: true });

if (hasReport > 0) {
  const summaryText = await page.locator('.summary-header').innerText().catch(() => '(no summary-header found)');
  console.log('SUMMARY HEADER TEXT:\n', summaryText);
  const disclosureText = await page.locator('.disclosure-banner').innerText().catch(() => '(no disclosure-banner found)');
  console.log('DISCLOSURE TEXT:\n', disclosureText);
}

console.log('CONSOLE ERRORS:', consoleErrors.length ? consoleErrors : 'none');

await browser.close();
