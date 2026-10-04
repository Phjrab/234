'use strict';
// Optional operator check. Dependencies: playwright and @axe-core/playwright.
// Credentials and cookies stay private; reports contain only validation outcomes.
const fs = require('node:fs');
const crypto = require('node:crypto');
const https = require('node:https');
const net = require('node:net');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const args = process.argv.slice(2);
function option(name) { const i = args.indexOf(name); return i < 0 ? null : args[i + 1]; }
const credentialFile = option('--credentials');
const reportFile = option('--report');
const certificateFile = option('--certificate');
const expiry = args.includes('--session-expiry');
if (!credentialFile || !reportFile) {
  console.error('Usage: node tools/verify_browser.js --credentials PRIVATE_JSON --report PRIVATE_JSON [--certificate PUBLIC_PEM] [--session-expiry]');
  process.exit(2);
}
const credentials = JSON.parse(fs.readFileSync(credentialFile, 'utf8'));
const url = new URL(credentials.url);
if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname))) throw Error('Use HTTPS or a loopback HTTP listener');
const launchArgs = [];
let certificate;
if (certificateFile) {
  certificate = fs.readFileSync(certificateFile);
  const cert = new crypto.X509Certificate(certificate);
  const host = url.hostname.replace(/^\[|\]$/g, '');
  const matches = net.isIP(host) ? cert.checkIP(host) : cert.checkHost(host);
  if (!matches || Date.now() < Date.parse(cert.validFrom) || Date.now() >= Date.parse(cert.validTo)) throw Error('Reference certificate does not match the host or validity period');
  const pin = crypto.createHash('sha256').update(cert.publicKey.export({ type: 'spki', format: 'der' })).digest('base64');
  launchArgs.push('--ignore-certificate-errors-spki-list=' + pin);
}
const report = { status: 'RUNNING', mode: expiry ? 'real_elapsed_session' : 'accessibility', started_at_utc: new Date().toISOString(), global_tls_errors_ignored: false,
  browser_certificate_policy: certificate ? 'Exact reference certificate SPKI pin in isolated Chromium' : 'Default Chromium trust', checks: [] };
function save() { fs.writeFileSync(reportFile, JSON.stringify(report, null, 2) + '\n', { mode: 0o600 }); }
function statusWithOriginalCookie(cookie) {
  return new Promise((resolve, reject) => {
    const req = https.get(new URL('/api/status', url), { ca: certificate, rejectUnauthorized: true, headers: { Cookie: cookie } }, res => {
      res.resume(); res.on('end', () => resolve(res.statusCode));
    });
    req.on('error', reject); req.setTimeout(10000, () => req.destroy(Error('HTTPS request timed out')));
  });
}
(async () => {
  const browser = await chromium.launch({ headless: true, args: launchArgs });
  try {
    const context = await browser.newContext({ ignoreHTTPSErrors: false, viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.goto(url.href, { waitUntil: 'networkidle' });
    async function audit(view) {
      const AxeBuilder = require('@axe-core/playwright').default;
      const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
      report.axe_version = result.testEngine.version;
      // Exclude node HTML, selectors, dataset contents and experiment names.
      report.checks.push({ view, violations: result.violations.map(v => ({ id: v.id, impact: v.impact, count: v.nodes.length })) });
      save();
    }
    if (!expiry) await audit('login');
    await page.locator('#login-form input[name=username]').fill(credentials.username);
    await page.locator('#login-form input[name=password]').fill(credentials.password);
    await page.locator('#login-form button[type=submit]').click();
    await page.locator('#login-dialog').waitFor({ state: 'hidden' });
    if (expiry) {
      if (url.protocol !== 'https:') throw Error('Elapsed-session verification requires HTTPS');
      const start = performance.now();
      report.started_at_utc = new Date().toISOString(); report.clock_injected = false; report.session_seconds = 3600;
      const cookie = (await context.cookies(url.href)).find(c => c.name === 'ft_session');
      assert(cookie, 'Expected session cookie');
      const originalCookie = cookie.name + '=' + cookie.value;
      save(); console.log('Actual one-hour session check started');
      for (const target of [300,600,900,1200,1500,1800,2100,2400,2700,3000,3300,3590,3605]) {
        await new Promise(resolve => setTimeout(resolve, Math.max(0, target * 1000 - (performance.now() - start))));
        const elapsed = (performance.now() - start) / 1000;
        const status = await statusWithOriginalCookie(originalCookie);
        const expected = elapsed >= 3600 ? 401 : 200;
        report.checks.push({ elapsed_seconds: Math.round(elapsed * 100) / 100, http_status: status }); save();
        assert.equal(status, expected); console.log('Elapsed ' + Math.floor(elapsed) + 's: HTTP ' + status);
      }
      await page.locator('#login-dialog').waitFor({ state: 'visible', timeout: 15000 });
      report.login_dialog_after_expiry = true;
      await page.locator('#login-form input[name=password]').fill(credentials.password);
      await page.locator('#login-form button[type=submit]').click();
      await page.locator('#login-dialog').waitFor({ state: 'hidden' });
      assert.equal(await page.evaluate(async () => (await fetch('/api/status')).status), 200);
      report.reauthentication = 'PASS';
    } else {
      await page.locator('[data-nav=settings]').click();
      await page.locator('#language-select').selectOption('ko');
      for (const view of ['overview','runs','datasets','recipes','compare','environment','settings']) {
        await page.locator(`[data-nav=${view}]`).click(); await page.waitForTimeout(700); await audit(view);
        assert.equal(await page.locator(`[data-nav=${view}]`).getAttribute('aria-current'), 'page');
        if (view === 'runs') {
          await page.locator('[data-filter=LLM]').press('Enter');
          assert.equal(await page.locator('[data-filter=LLM]').getAttribute('aria-pressed'), 'true');
          await page.locator('[data-filter=all]').press('Space');
          assert.equal(await page.locator('[data-filter=all]').getAttribute('aria-pressed'), 'true');
          const row = page.locator('tr[data-run]').first();
          if (await row.count()) {
            await row.focus(); const id = await row.getAttribute('data-run'); await page.keyboard.press('Enter');
            await page.waitForTimeout(2500);
            assert.equal(await page.evaluate(() => document.activeElement.dataset.run), id);
          }
          await page.locator('[data-tab=logs]').focus();
          for (const [key, tab] of [['ArrowRight','checkpoints'],['End','configuration'],['Home','logs'],['ArrowLeft','configuration']]) {
            await page.keyboard.press(key);
            assert.equal(await page.evaluate(() => document.activeElement.dataset.tab), tab);
            assert.equal(await page.locator(`[data-tab=${tab}]`).getAttribute('aria-selected'), 'true');
          }
          report.keyboard = { status: 'PASS', scope: 'Navigation and filter state, Enter/Space, row focus across polling, tab arrows/Home/End' };
        }
        if (view === 'runs') for (const tab of ['logs','checkpoints','evaluation','configuration']) {
          await page.locator(`[data-tab=${tab}]`).click(); await audit('runs-' + tab);
        }
      }
      await page.setViewportSize({ width: 390, height: 844 });
      for (const view of ['runs','datasets','recipes','settings']) {
        await page.locator('#mobile-view').selectOption(view); await page.waitForTimeout(700); await audit('mobile-' + view);
      }
      assert(report.checks.every(c => c.violations.length === 0), 'Accessibility violations found; inspect the private report');
    }
    assert.deepEqual(errors, [], 'Browser JavaScript errors found');
    await page.evaluate(async () => {
      const auth = await (await fetch('/api/auth/status')).json();
      const res = await fetch('/api/auth/logout', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': auth.csrf_token }, body: '{}' });
      if (!res.ok) throw Error('Could not close the verification session');
    });
    report.status = 'PASS'; report.completed_at_utc = new Date().toISOString(); save(); console.log('PASS ' + report.mode);
  } catch (error) {
    report.status = 'FAIL'; report.error = error.message; save(); console.error(error.message); process.exitCode = 1;
  } finally { await browser.close(); }
})();
