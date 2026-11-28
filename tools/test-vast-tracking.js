#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {DOMParser}=require('@xmldom/xmldom');
const source=fs.readFileSync(require('node:path').join(__dirname,'../smartedtv/js/vast.js'),'utf8');
const ua='Mozilla/5.0 (Linux; Android 14; Actual-Test-Device) AppleWebKit/537.36';
const pixel=(id)=>`https://pixels.invalid/${id}?cb=[CACHEBUSTING]&amp;alias=%5BCACHEBUSTER%5D&amp;random=[RANDOM]&amp;ts=[TIMESTAMP]&amp;ua=[DEVICEUA]`;
const wrapper=(next,id)=>`<VAST><Ad><Wrapper><Impression>${pixel(id)}</Impression><Impression>${pixel('duplicate')}</Impression><Error>https://pixels.invalid/error?e=[ERRORCODE]</Error><VASTAdTagURI>${next}</VASTAdTagURI><Creatives><Creative><Linear><TrackingEvents><Tracking event="start">https://pixels.invalid/start-${id}</Tracking></TrackingEvents></Linear></Creative></Creatives></Wrapper></Ad></VAST>`;
const inline=`<VAST><Ad><InLine><Impression>${pixel('inline-one')}</Impression><Impression>${pixel('inline-two')}</Impression><Creatives><Creative><Linear><Duration>00:00:21</Duration><MediaFiles><MediaFile type="video/mp4">https://media.invalid/ad.mp4</MediaFile></MediaFiles></Linear></Creative></Creatives></InLine></Ad></VAST>`;
(async()=>{
 const sent=[],requests=[],timers=new Map();let timerId=0;
 class Element{
  constructor(){this.children=[];this.listeners={};this.currentTime=0;this.duration=21;}
  addEventListener(n,cb){(this.listeners[n]||=[]).push(cb);}
  emit(n){for(const cb of this.listeners[n]||[])cb();}
  appendChild(child){this.children.push(child);child.parentNode=this;}
  removeChild(child){this.children.splice(this.children.indexOf(child),1);child.parentNode=null;}
  setAttribute(){} removeAttribute(){} load(){} focus(){} pause(){} play(){return Promise.resolve();}
 }
 const pages={'https://tag.invalid/one':wrapper('https://tag.invalid/two','outer'),'https://tag.invalid/two':wrapper('https://tag.invalid/inline','inner'),'https://tag.invalid/inline':inline};
 const context={DOMParser,Date,Math,Promise,AbortController,navigator:{userAgent:ua},
  document:{body:new Element(),createElement:()=>new Element()},
  Image:class{set src(value){sent.push(value);if(this.onload)this.onload();}},
  setTimeout(cb){timers.set(++timerId,cb);return timerId;},clearTimeout(id){timers.delete(id);},
  fetch:async(url,opts)=>{requests.push([url,opts]);return{ok:true,text:async()=>pages[url]||'<VAST/>'};}};
 context.window=context;vm.runInNewContext(source,context);const V=context.SmartedtvVast;
 const expanded=V.expandMacros('https://p.invalid/?a=[CACHEBUSTING]&b=%5Bcachebuster%5D&c=%%RANDOM%%&e=%5BERRORCODE%5D&u=[DEVICEUA]',{errorCode:405});
 const params=new URL(expanded).searchParams;
 assert.match(params.get('a'),/^\d{8}$/);assert.equal(params.get('a'),params.get('b'));assert.equal(params.get('a'),params.get('c'));assert.equal(params.get('e'),'405');assert.equal(params.get('u'),ua);
 const parsed=await V.fetchResolvedVast('https://tag.invalid/one',8000);
 assert.equal(parsed.ads[0].impressions.length,6);assert.equal(sent.length,0);
 assert.equal(parsed.ads[0].tracking.start.length,2);
 const player=new V.VastPlayer({tagUrl:'https://tag.invalid/one'});const done=player.play();
 for(let i=0;i<40;i++)await Promise.resolve();
 assert.ok(player._video);player._video.emit('playing');player._video.emit('playing');
 const impressions=sent.filter(url=>url.includes('cb='));assert.equal(impressions.length,6);
 assert.equal(impressions.filter(url=>url.includes('/duplicate?')).length,2);
 for(const url of impressions){assert.ok(!url.includes('['));assert.equal(new URL(url).searchParams.get('ua'),ua);}
 assert.ok(requests.every(([,opts])=>!Object.keys(opts.headers).some(key=>key.toLowerCase()==='user-agent')));
 player._video.emit('ended');await done;
 sent.length=0;pages['https://tag.invalid/inline']='<VAST/>';
 const nofill=await V.fetchResolvedVast('https://tag.invalid/one',8000);
 assert.equal(nofill.noFill,true);assert.equal(sent.filter(url=>url.includes('cb=')).length,0);
 assert.equal(sent.filter(url=>url.includes('/error?e=303')).length,2);
 sent.length=0;pages['https://tag.invalid/two']=wrapper('https://tag.invalid/one','cycle');
 const cycle=await V.fetchResolvedVast('https://tag.invalid/one',8000);
 assert.equal(cycle.noFill,true);assert.equal(sent.filter(url=>url.includes('/error?e=302')).length,2);
 console.log('OK: JS nested Wrapper impressions, duplicate XML nodes, macros, actual-browser UA, no-fill and cycle');
})().catch(error=>{console.error(error);process.exitCode=1;});
