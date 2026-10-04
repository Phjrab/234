'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/i18n.js', 'utf8');

function createEnvironment(saved, unavailable = false) {
  const writes = [];
  const events = [];
  const listeners = {};
  const context = vm.createContext({
    document: {documentElement: {lang: 'en'}, dispatchEvent: event => events.push(event)},
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
    addEventListener: (type, callback) => { listeners[type] = callback; },
    localStorage: {
      getItem() { if (unavailable) throw new Error('Storage disabled'); return saved; },
      setItem(key, value) { if (unavailable) throw new Error('Storage disabled'); writes.push([key, value]); }
    }
  });
  vm.runInContext(source, context);
  return {context, writes, events, listeners, run: code => vm.runInContext(code, context)};
}

const saved = createEnvironment('ko');
assert.equal(saved.run('I18n.language'), 'ko');
assert.equal(saved.run("t('Access settings')"), '설정');
assert.equal(saved.run("t('Unknown server message')"), 'Unknown server message');
assert.match(saved.run("t('12 GB VRAM is an explicit planning assumption. This heuristic does not measure hardware, tokenize data or guarantee that any model/configuration fits.')"), /VRAM 12 GB/);
assert.equal(saved.run("t('Exact normalized duplicate of line 3; retained unless you edit the source.')"), '3번 줄과 정규화된 내용이 같습니다. 원본을 수정하지 않으면 중복이 유지됩니다.');
assert.equal(saved.run("t('{count} demo failures recorded. Review the injected scenario and next steps.', {count: 2})"), '데모 실패 2건이 기록됐습니다. 설정된 오류 시나리오와 다음 단계를 확인하세요.');
assert.equal(saved.run("I18n.setLanguage('ja')"), false);
assert.equal(saved.run('I18n.language'), 'ko');
saved.run("I18n.setLanguage('en')");
assert.equal(saved.run("t('Access settings')"), 'Access settings');
assert.deepEqual(saved.writes, [['forge.language', 'en']]);
assert.equal(saved.events[0].type, 'forge:languagechange');
assert.equal(saved.run('document.documentElement.lang'), 'en');
saved.listeners.storage({key: 'forge.language', newValue: 'ko'});
assert.equal(saved.run('I18n.language'), 'ko');
assert.equal(saved.writes.length, 1, 'Cross-tab updates must not write back');
saved.listeners.storage({key: 'unrelated', newValue: 'en'});
assert.equal(saved.run('I18n.language'), 'ko');
const invalid = createEnvironment('unsupported');
assert.equal(invalid.run('I18n.language'), 'en');
const disabled = createEnvironment(null, true);
assert.equal(disabled.run('I18n.language'), 'en');
assert.doesNotThrow(() => disabled.run("I18n.setLanguage('ko')"));
assert.equal(disabled.run("t('Display language')"), '표시 언어');
console.log('PASS: saved preference, both languages, unknown-message fallback, placeholder formatting, unsupported language, cross-tab updates, disabled storage.');
