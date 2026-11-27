#!/usr/bin/env node
/* Deterministic lifecycle tests: fake media/DOM/clock, no live ad requests.
   Browser codecs/autoplay and Kodi runtime still need device validation. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const { DOMParser } = require("@xmldom/xmldom");
const source = fs.readFileSync(path.join(__dirname, "../smartedtv/js/vast.js"), "utf8");
const fixture = fs.readFileSync(path.join(__dirname, "../smartedtv/testdata/vast-with-ad.xml"), "utf8");
let passed = 0;
const flush = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };
function env(xml = fixture) {
  let now = 0, id = 0;
  const timers = new Map(), beacons = [];
  class Element {
    constructor(tag) {
      this.tag = tag; this.children = []; this.listeners = {};
      this.currentTime = 0; this.duration = 30; this.paused = true;
      this.seeking = false; this.playCalls = 0;
    }
    addEventListener(name, cb) { (this.listeners[name] ||= new Set()).add(cb); }
    removeEventListener(name, cb) { this.listeners[name]?.delete(cb); }
    emit(name) { for (const cb of [...(this.listeners[name] || [])]) cb(); }
    appendChild(el) { this.children.push(el); el.parentNode = this; }
    removeChild(el) { this.children.splice(this.children.indexOf(el), 1); el.parentNode = null; }
    setAttribute() {} removeAttribute() {} load() {} focus() {}
    pause() { this.paused = true; }
    play() { this.playCalls++; this.paused = false; return Promise.resolve(); }
  }
  const context = {
    DOMParser, Promise, Date, Math, Error, AbortController, open() {},
    document: { body: new Element("body"), createElement: tag => new Element(tag) },
    Image: class { set src(url) { beacons.push(url); } },
    fetch: async () => ({ ok: true, text: async () => xml }),
    setTimeout(cb, ms) { timers.set(++id, { cb, at: now + ms }); return id; },
    clearTimeout(id) { timers.delete(id); }
  };
  context.window = context;
  vm.runInNewContext(source, context);
  const vod = new Element("video"); vod.currentTime = 42.123; vod.paused = false;
  return {
    context, vod, beacons, timers,
    player: () => new context.SmartedtvVast.VastPlayer({ tagUrl: "https://test.invalid/vast", resumeTarget: { video: vod } }),
    async tick(ms) {
      now += ms;
      for (const [id, timer] of [...timers]) if (timer.at <= now) { timers.delete(id); timer.cb(); }
      await flush();
    }
  };
}
async function test(name, fn) { await fn(); passed++; console.log("ok   " + name); }
(async () => {
  await test("inline Error URL is tracking, not no-fill", async () => {
    const e = env();
    const p = e.context.SmartedtvVast.parseVast(fixture.replace("<AdTitle>", "<Error>https://test.invalid/error?[ERRORCODE]</Error><AdTitle>"));
    assert.equal(p.noFill, false); assert.equal(p.ads[0].tracking.error.length, 2);
  });
  await test("no-fill pauses and resumes exact original position without overlay", async () => {
    const e = env("<VAST/>"); const p = e.player(); const done = p.play();
    assert.equal(e.vod.paused, true);
    const r = await done;
    assert.equal(r.outcome, "nofill"); assert.equal(r.resumeConfirmed, true);
    assert.equal(r.resumedAt, 42.123); assert.equal(e.vod.paused, false);
    assert.equal(e.context.document.body.children.length, 0); assert.equal(e.timers.size, 0);
  });
  await test("network rejection cleans up and resumes", async () => {
    const e = env(); e.context.fetch = () => Promise.reject(new Error("offline"));
    const r = await e.player().play(); assert.equal(r.outcome, "error"); assert.equal(e.vod.paused, false);
  });
  await test("timeout works without AbortController", async () => {
    const e = env(); e.context.AbortController = undefined;
    e.context.fetch = () => new Promise(() => {});
    const done = e.player().play(); await flush(); await e.tick(8001);
    const r = await done; assert.equal(r.reason, "vast-timeout"); assert.equal(r.resumeConfirmed, true);
  });
  await test("timeout includes response body", async () => {
    const e = env(); e.context.fetch = async () => ({ ok: true, text: () => new Promise(() => {}) });
    const done = e.player().play(); await flush(); await e.tick(8001);
    assert.equal((await done).reason, "vast-timeout");
  });
  await test("skip blocked before offset; after skip exact seek is confirmed", async () => {
    const e = env(); const p = e.player(); const done = p.play(); assert.equal(p.play(), done);
    await flush(); const ad = p._video, skip = p._skipBtn;
    skip.emit("click"); assert.equal(p._done, false); assert.equal(skip.disabled, true);
    ad.currentTime = 5; ad.emit("timeupdate"); assert.equal(skip.disabled, false);
    e.vod.currentTime = 9; e.vod.seeking = true;
    skip.emit("click"); assert.equal(e.vod.currentTime, 42.123); assert.equal(e.vod.paused, true);
    e.vod.seeking = false; e.vod.emit("seeked");
    const r = await done;
    assert.equal(r.outcome, "skipped"); assert.equal(r.resumeConfirmed, true);
    assert.equal(e.vod.paused, false); assert.equal(e.context.document.body.children.length, 0);
    assert.equal(e.timers.size, 0);
  });
  await test("completion emits each required playback beacon once", async () => {
    const e = env(); const p = e.player(); const done = p.play(); await flush(); const ad = p._video;
    ad.emit("play"); assert.equal(e.beacons.length, 0); // play request is not playback
    ad.emit("playing"); ad.emit("playing");
    for (const t of [7.5, 15, 22.5, 25]) { ad.currentTime = t; ad.emit("timeupdate"); }
    ad.emit("ended"); ad.emit("ended");
    assert.equal((await done).outcome, "completed");
    for (const event of ["impression", "start", "firstQuartile", "midpoint", "thirdQuartile", "complete"])
      assert.equal(e.beacons.filter(url => url.includes("/" + event + "?")).length, 1, event);
  });
  await test("real end does not fabricate unobserved quartiles", async () => {
    const e = env(); const p = e.player(); const done = p.play(); await flush();
    p._video.emit("playing"); p._video.currentTime = 1; p._video.emit("timeupdate");
    p._video.emit("ended");
    assert.equal((await done).outcome, "completed");
    assert(e.beacons.some(url => url.includes("/complete?")));
    assert(!e.beacons.some(url => /firstQuartile|midpoint|thirdQuartile/.test(url)));
  });
  await test("mid-ad stall resumes content and fires error, not complete", async () => {
    const e = env(); const p = e.player(); const done = p.play(); await flush();
    p._video.emit("playing"); p._video.currentTime = 1; p._video.emit("timeupdate");
    await e.tick(12001); assert.equal((await done).reason, "creative-stall");
    assert(e.beacons.some(url => url.includes("code=405")));
    assert(!e.beacons.some(url => url.includes("/complete?")));
  });
  await test("unconfirmed seek is not reported as exact; originally paused VOD stays paused", async () => {
    const e = env(); e.vod.paused = true;
    const p = e.player(); const done = p.play(); await flush();
    e.vod.seeking = true; p._video.emit("error"); await e.tick(1501);
    const r = await done; assert.equal(r.resumeConfirmed, false); assert.equal(e.vod.paused, true);
  });
  await test("AdMob feature flag prevents native calls", async () => {
    const e = env(); let calls = 0;
    e.context.SMARTEDTV_CONFIG = { admob: { enabled: false } };
    e.context.SmartedtvAdMobBridge = { showAppOpen() { calls++; } };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../smartedtv/js/admob.js"), "utf8"), e.context);
    assert.equal((await e.context.SmartedtvAdMob.showAppOpen()).connected, false); assert.equal(calls, 0);
  });
  console.log(`\n${passed} lifecycle tests passed`);
})().catch(err => { console.error(err); process.exitCode = 1; });
