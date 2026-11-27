#!/usr/bin/env node
/* Unit tests for smartedtv/js/vast.js (parser + helpers).
   Run:  npm i --no-save @xmldom/xmldom   (once, for the DOMParser shim)
         node tools/test-vast.js
   The player (DOM/video) is covered manually via demo-vast.html. */
"use strict";
const fs = require("fs");
const path = require("path");

let DOMParser;
try {
  ({ DOMParser } = require("@xmldom/xmldom"));
} catch (e) {
  console.error("missing @xmldom/xmldom — run: npm i --no-save @xmldom/xmldom");
  process.exit(2);
}

global.window = global;
global.DOMParser = DOMParser;
global.SMARTEDTV_CONFIG = { vastTagUrl: "https://vast.yomeno.xyz/vast?spot_id=1508180" };
global.Image = function () {}; // beacon target (no-op in tests)

const src = fs.readFileSync(path.join(__dirname, "..", "smartedtv", "js", "vast.js"), "utf8");
eval(src); // attaches window.SmartedtvVast
const V = window.SmartedtvVast;

let pass = 0, fail = 0;
function check(name, cond) {
  if (cond) { pass++; console.log("ok   " + name); }
  else { fail++; console.log("FAIL " + name); }
}
function readFixture(name) {
  return fs.readFileSync(path.join(__dirname, "..", "smartedtv", "testdata", name), "utf8");
}

/* --- parseTimeOffset / parseClock --- */
check("offset HH:MM:SS", V.parseTimeOffset("00:00:05").seconds === 5);
check("offset percent", V.parseTimeOffset("25%").value === 25);
check("offset garbage -> null", V.parseTimeOffset("abc") === null);
check("clock MM:SS", V.parseClock("01:30") === 90);
check("clock HH:MM:SS.mmm", Math.abs(V.parseClock("00:00:30.000") - 30) < 1e-9);

/* --- with-ad fixture --- */
const withAd = V.parseVast(readFixture("vast-with-ad.xml"));
check("with-ad: not nofill", withAd.noFill === false);
check("with-ad: 1 ad", withAd.ads.length === 1);
const ad = withAd.ads[0];
check("with-ad: duration 30s", ad.duration === 30);
check("with-ad: skipoffset 5s", ad.skipOffset && ad.skipOffset.seconds === 5);
check("with-ad: 2 media files", ad.mediaFiles.length === 2);
check("with-ad: best media = 1280w mp4", ad.mediaFile && ad.mediaFile.width === 1280);
check("with-ad: clickThrough", ad.clickThrough.indexOf("example.com/landing") !== -1);
check("with-ad: impression", ad.impressions.length === 1);
for (const ev of ["start", "firstQuartile", "midpoint", "thirdQuartile", "complete", "error"]) {
  check("with-ad: tracking " + ev, Array.isArray(ad.tracking[ev]) && ad.tracking[ev].length === 1);
}

/* --- no-fill fixtures: must NOT throw, must resolve nofill --- */
const nofill = V.parseVast(readFixture("vast-nofill.xml"));
check("nofill minimal: nofill=true", nofill.noFill === true && nofill.ads.length === 0);
check("nofill minimal: reason no-ad", nofill.reason === "no-ad");

const empty = V.parseVast(readFixture("vast-empty.xml"));
check("empty: nofill=true", empty.noFill === true && empty.reason === "empty");

const err = V.parseVast(readFixture("vast-error.xml"));
check("vast-error: nofill=true", err.noFill === true && err.reason === "vast-error");
check("vast-error: code 303", err.errorCode === "303");

const malformed = V.parseVast("<VAST><Ad><oops");
check("malformed: nofill, no throw", malformed.noFill === true && malformed.reason === "malformed");

const blank = V.parseVast("   \n  ");
check("whitespace: nofill", blank.noFill === true && blank.reason === "empty");

/* --- chooseMediaFile --- */
check("choose: null on empty", V.chooseMediaFile([]) === null);
check("choose: prefers mp4", V.chooseMediaFile([
  { url: "a.webm", type: "video/webm", width: 1920 },
  { url: "b.mp4", type: "video/mp4", width: 640 }
]).url === "b.mp4");

console.log("\n" + pass + " passed, " + fail + " failed");
process.exit(fail ? 1 : 0);
