// Maintainer baseline smoke, not an agent-facing or final browser grader.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const root = path.resolve(process.argv[2]);
  const executablePath = process.argv[3];
  if (!executablePath) throw new Error('Pass the Chromium executable path as the second argument');
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.json')));
  const fixture = JSON.parse(fs.readFileSync(path.join(root, 'fixture.json')));
  const base = `http://localhost:${manifest.port}`;
  const browser = await chromium.launch({ executablePath, headless: true,
    args: ['--disable-background-networking', '--no-first-run'] });
  const results = [];
  try {
    for (const actor of ['alice', 'bob']) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
      await context.route('**/*', route => {
        const url = new URL(route.request().url());
        return ['localhost', '127.0.0.1'].includes(url.hostname) ? route.continue() : route.abort();
      });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      try {
        await page.goto(`${base}/app/login`, { waitUntil: 'networkidle', timeout: 120000 });
        await page.locator('input[name=email_address]').fill(fixture.users[actor].email);
        await page.locator('input[name=password]').fill('PocketBench123!');
        await page.getByRole('button', { name: 'Login', exact: true }).click();
        await page.waitForURL('**/accounts/**');
        await page.getByText('My open requests', { exact: true }).first().waitFor();
        const expected = fixture.conversations.filter(c => c.account === 'A' && c.status === 'open'
          && (actor === 'alice' || c.inbox === 'general')).map(c => c.display_id);
        const filtered = page.waitForResponse(r => r.url().includes('/conversations/filter')
          && r.request().method() === 'POST', { timeout: 60000 });
        await page.getByText('My open requests', { exact: true }).first().click();
        const response = await filtered;
        assert.equal(response.status(), 200);
        const body = await response.json();
        assert.deepEqual(body.payload.map(row => row.id).sort((a,b) => a-b), expected.sort((a,b) => a-b));
        assert.equal(body.meta.all_count, expected.length);
        await page.getByText('general customer 0', { exact: true }).first().waitFor();
        if (actor === 'alice') {
          await page.getByText('restricted customer 0', { exact: true }).first().waitFor();
        } else {
          assert.equal(await page.getByText('restricted customer 0', { exact: true }).count(), 0);
        }
        await page.screenshot({ path: path.join(root, `browser-${actor}.png`), fullPage: true });
        assert.deepEqual(errors, [], 'Unexpected browser runtime error');
        results.push({ actor, status: 'pass', visible_conversations: expected.length });
      } catch (error) {
        // Do not report URLs, headers, localStorage or auth state in artifacts.
        results.push({ actor, status: 'error', detail: error.name, stage: 'baseline browser flow' });
      } finally {
        await context.close();
      }
    }
    const report = { kind: 'maintainer-browser-baseline', browser: browser.version(), checks: results };
    fs.writeFileSync(path.join(root, 'browser-baseline.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report, null, 2));
    if (results.some(result => result.status !== 'pass')) process.exitCode = 1;
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.name); process.exitCode = 1; });
