#!/usr/bin/env node
/* Execute the real web button handlers with a tiny DOM; no network. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.join(__dirname, '..');
const official = JSON.parse(fs.readFileSync(path.join(root, 'android-build/base-apk.json'))).url;
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    listeners: {}, children: [], classList: {add(){},remove(){}},
    setAttribute(){}, addEventListener(event, callback){this.listeners[event] = callback;},
    appendChild(child){this.children.push(child);}, removeChild(){this.children.shift();}
  });
  return elements.get(id);
}
(async () => {
  const opened = [], shared = [], copied = [];
  const sandbox = {
    document: {getElementById: element, querySelector: element, querySelectorAll: () => [],
      addEventListener(){}, createElement: () => element(Symbol())},
    navigator: {share: async data => shared.push(data), clipboard: {writeText: async text => copied.push(text)}},
    setTimeout(){}, Promise,
    open: (...args) => opened.push(args), matchMedia: () => ({matches:true})
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  for (const name of ['config.js', 'services.js', 'app.js'])
    vm.runInContext(fs.readFileSync(path.join(root, 'smartedtv/js', name), 'utf8'), sandbox);
  assert.equal(sandbox.SMARTEDTV_CONFIG.apkDownloadUrl, official);
  assert.equal(sandbox.SMARTEDTV_CONFIG.apkShareUrl, official);
  for (const device of ['mobile','tvbox','projetor']) {
    // Link destinations do not depend on the visual device selector.
    sandbox.device = device;
    elements.get('baixar-apk').listeners.click();
    elements.get('atualizar').listeners.click();
    elements.get('share').listeners.click();
  }
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(opened.length, 6);
  assert.ok(opened.every(args => args[0] === official));
  assert.equal(shared.length, 3);
  assert.ok(shared.every(data => data.url === official));
  sandbox.navigator.share = undefined;
  elements.get('share').listeners.click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(copied[0], official);
  console.log('OK: web download/update/share handlers, three device flows and clipboard fallback');
})().catch(error => {console.error(error); process.exitCode = 1;});
