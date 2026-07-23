// Targeted live re-measurement of Togal's real header + hero breakpoint.
// Read-only. Fixes the Phase-1 gap where the automated probe hit a hidden
// OneTrust node. Measures the visible sticky header band, logo, nav gap at
// 1440, and bisects the 1-col/2-col hero switch across 900/960/992/1024.
import { writeFileSync, mkdirSync } from "node:fs";
import { launchChrome, CDP, sleep } from "./cdp.mjs";

const URL = process.env.TARGET_URL || "https://www.togal.ai/";
const OUT = "review-artifacts/togal-faithful-rebuild/measurements/togal-header-hero.json";

const HEADER_EXPR = `(() => {
  // Visible sticky/fixed bar pinned to the top that contains the logo + nav.
  const cands = [...document.querySelectorAll('header,[class*="header" i],[class*="navbar" i],nav')];
  let best = null;
  for (const el of cands) {
    const c = getComputedStyle(el); const r = el.getBoundingClientRect();
    if (c.display === 'none' || r.height === 0 || r.width < innerWidth * 0.8) continue;
    if (r.top > 4) continue;                       // pinned to very top
    if (!(c.position === 'fixed' || c.position === 'sticky' || c.position === 'absolute' || c.position === 'relative')) continue;
    if (r.height < 40 || r.height > 120) continue; // a header band, not the page
    if (!best || r.height < best.h) best = { h: Math.round(r.height), top: Math.round(r.top), bg: c.backgroundColor, position: c.position, cls: (el.className||'').toString().slice(0,80), tag: el.tagName };
  }
  const header = best;
  // logo image height
  const imgs = [...document.querySelectorAll('header img,[class*="header" i] img,[class*="nav" i] img')];
  const logo = imgs.map(i=>({h:Math.round(i.getBoundingClientRect().height), w:Math.round(i.getBoundingClientRect().width), alt:i.alt})).filter(o=>o.h>8 && o.h<80)[0] || null;
  // nav link gap: text links in the top band
  const links = [...document.querySelectorAll('a')].filter(a=>{const r=a.getBoundingClientRect();return r.top<70 && r.height>10 && r.height<50 && (a.textContent||'').trim().length>1 && (a.textContent||'').trim().length<20;}).map(a=>({t:(a.textContent||'').trim(), x:Math.round(a.getBoundingClientRect().x), w:Math.round(a.getBoundingClientRect().width)})).sort((a,b)=>a.x-b.x);
  let gaps=[]; for(let i=1;i<links.length;i++){const g=links[i].x-(links[i-1].x+links[i-1].w); if(g>0&&g<80)gaps.push(g);}
  return { header, logo, links, gaps, viewport: innerWidth };
})()`;

const HERO_EXPR = `(() => {
  const h1 = document.querySelector('h1'); if(!h1) return {cols:'?'};
  const hero = h1.closest('section') || h1.closest('div');
  const tr = h1.getBoundingClientRect();
  // largest media (video/iframe/img) within the hero region
  const media = [...(hero?hero.querySelectorAll('video,iframe,img,[class*="video" i]'):[])]
    .map(el=>({el,r:el.getBoundingClientRect()}))
    .filter(o=>o.r.width>160 && o.r.height>90)
    .sort((a,b)=>b.r.width*b.r.height-a.r.width*a.r.height)[0];
  if(!media) return {cols:1, reason:'no media'};
  const mr = media.r;
  const sideBySide = (mr.x > tr.x + tr.width*0.4) && (mr.top < tr.bottom + 40) && (mr.bottom > tr.top - 40);
  return { cols: sideBySide?2:1, textX:Math.round(tr.x), textRight:Math.round(tr.right), mediaX:Math.round(mr.x), mediaW:Math.round(mr.width), mediaTop:Math.round(mr.top), viewport: innerWidth };
})()`;

async function main(){
  const chrome = await launchChrome();
  const cdp = await CDP.connect(chrome.webSocketDebuggerUrl);
  const out = { url: URL, header1440: null, heroBreakpoint: {} };
  try {
    const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
    const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
    await cdp.send("Page.enable", {}, sessionId);
    await cdp.send("Runtime.enable", {}, sessionId);

    async function load(w,h){
      await cdp.send("Emulation.setDeviceMetricsOverride",{width:w,height:h,deviceScaleFactor:1,mobile:false},sessionId);
      const loaded = cdp.once("Page.loadEventFired", sessionId, 40000).catch(()=>null);
      await cdp.send("Page.navigate",{url:URL},sessionId); await loaded; await sleep(2200);
    }
    async function ev(expr){ const r = await cdp.send("Runtime.evaluate",{expression:expr,returnByValue:true},sessionId); return r.result.value; }

    await load(1440,1000);
    out.header1440 = await ev(HEADER_EXPR);

    for (const w of [900,960,992,1024,1100]) {
      await load(w, 1000);
      out.heroBreakpoint[w] = await ev(HERO_EXPR);
    }
  } finally { cdp.close(); await chrome.close(); }
  mkdirSync("review-artifacts/togal-faithful-rebuild/measurements",{recursive:true});
  writeFileSync(OUT, JSON.stringify(out,null,2));
  console.log(JSON.stringify(out,null,2));
}
main().catch(e=>{console.error("MEASURE FAILED:",e);process.exit(1);});
