// Full-page, multi-viewport screenshot + measurement capture over CDP.
//
// LEGAL/ETHICAL NOTE: read-only. Navigates, hides fixed overlays locally in the
// DOM for a clean screenshot, and reads computed styles. It never submits forms,
// accepts cookies, downloads assets, or copies source. Use only on sites you are
// permitted to view.
//
// Usage:
//   node scripts/visual-review/capture.mjs \
//     --url https://www.togal.ai/ --out review-artifacts/.../reference \
//     --label togal [--measure measurements/togal.json]
//
import { writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { launchChrome, CDP, sleep } from "./cdp.mjs";

const VIEWPORTS = [
  { name: "390x844",   w: 390,  h: 844,  mobile: true,  dsf: 3 },
  { name: "430x932",   w: 430,  h: 932,  mobile: true,  dsf: 3 },
  { name: "768x1024",  w: 768,  h: 1024, mobile: true,  dsf: 2 },
  { name: "834x1194",  w: 834,  h: 1194, mobile: true,  dsf: 2 },
  { name: "1024x1366", w: 1024, h: 1366, mobile: true,  dsf: 2 },
  { name: "1440x1000", w: 1440, h: 1000, mobile: false, dsf: 1 },
  { name: "1920x1080", w: 1920, h: 1080, mobile: false, dsf: 1 },
];

// Locally hide common fixed cookie/marketing overlays so they don't obscure the
// screenshot. This only mutates the DOM in our throwaway browser; nothing is
// submitted or accepted.
const HIDE_OVERLAYS = `(() => {
  const kill = [];
  const sel = ['[id*="cookie" i]','[class*="cookie" i]','[id*="consent" i]','[class*="consent" i]',
    '[class*="gdpr" i]','[id*="onetrust" i]','[class*="onetrust" i]','#hs-eu-cookie-confirmation',
    '[aria-label*="cookie" i]','[class*="banner" i][class*="cookie" i]','[class*="drift" i]',
    '[id*="intercom" i]','[class*="intercom" i]','[class*="chat-widget" i]'];
  for (const s of sel) document.querySelectorAll(s).forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.position === 'fixed' || cs.position === 'sticky' || /cookie|consent|gdpr|onetrust/i.test(el.className+el.id)) {
      el.style.setProperty('display','none','important'); kill.push(s);
    }
  });
  return kill.length;
})()`;

function measureExpr() {
  // Runs in the page; returns computed geometry/typography for representative
  // elements by structural heuristics (works without knowing the site's classes).
  return `(() => {
    const px = (v) => v;
    const g = (el) => { if(!el) return null; const c = getComputedStyle(el); const r = el.getBoundingClientRect();
      return { tag: el.tagName.toLowerCase(), text: (el.textContent||'').trim().slice(0,60),
        rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
        fontFamily:c.fontFamily, fontSize:c.fontSize, fontWeight:c.fontWeight, lineHeight:c.lineHeight,
        letterSpacing:c.letterSpacing, textTransform:c.textTransform, color:c.color,
        background:c.backgroundColor, padding:c.padding, margin:c.margin, borderRadius:c.borderRadius,
        boxShadow:c.boxShadow, position:c.position, display:c.display, gap:c.gap,
        maxWidth:c.maxWidth, width:c.width, height:c.height, transition:c.transition }; };
    const out = { url: location.href, viewport: {w: innerWidth, h: innerHeight, dpr: devicePixelRatio},
      docHeight: document.documentElement.scrollHeight, rootFont: getComputedStyle(document.documentElement).fontFamily };
    const header = document.querySelector('header') || document.querySelector('[class*="header" i]') || document.querySelector('nav')?.closest('div');
    out.header = g(header);
    const logo = header && (header.querySelector('img') || header.querySelector('svg'));
    out.logo = logo ? g(logo) : null;
    const navLinks = header ? [...header.querySelectorAll('a')].slice(0,10).map(a => ({t:(a.textContent||'').trim().slice(0,24), x:Math.round(a.getBoundingClientRect().x), w:Math.round(a.getBoundingClientRect().width)})) : [];
    out.navLinks = navLinks;
    out.h1 = g(document.querySelector('h1'));
    out.h2 = g(document.querySelector('h2'));
    // first paragraph after h1
    const h1 = document.querySelector('h1');
    let para = null; if (h1) { let n = h1; for (let i=0;i<8 && n;i++){ n = n.nextElementSibling || (n.parentElement && n.parentElement.nextElementSibling); const p = n && (n.matches && n.matches('p') ? n : n && n.querySelector && n.querySelector('p')); if (p){para=p;break;} } }
    out.paragraph = g(para || document.querySelector('p'));
    // buttons / CTAs
    const btns = [...document.querySelectorAll('a,button')].filter(el => {
      const r = el.getBoundingClientRect(); const c = getComputedStyle(el);
      return r.height>=28 && r.height<=90 && r.width>=70 && (c.backgroundColor && c.backgroundColor!=='rgba(0, 0, 0, 0)') && (el.textContent||'').trim().length>2;
    }).slice(0,6).map(g);
    out.buttons = btns;
    // hero = section/div containing h1
    out.hero = h1 ? g(h1.closest('section') || h1.closest('div')) : null;
    // main content max-width probe: widest common container
    const containers = [...document.querySelectorAll('div,section,main')].map(el=>{const r=el.getBoundingClientRect();return {w:Math.round(r.width), mw:getComputedStyle(el).maxWidth};}).filter(o=>/px/.test(o.mw));
    out.containerMaxWidths = [...new Set(containers.map(o=>o.mw))].slice(0,12);
    // footer
    out.footer = g(document.querySelector('footer') || document.querySelector('[class*="footer" i]'));
    // video-ish element (iframe / video / large 16:9 block)
    const vid = document.querySelector('video, iframe[src*="youtu" i], iframe[src*="vimeo" i], [class*="video" i]');
    out.video = g(vid);
    // section vertical rhythm: y positions of top-level sections
    out.sectionTops = [...document.querySelectorAll('section')].slice(0,14).map(s=>Math.round(s.getBoundingClientRect().top + scrollY));
    return out;
  })()`;
}

async function main() {
  const args = Object.fromEntries(
    process.argv.slice(2).reduce((acc, a, i, arr) => {
      if (a.startsWith("--")) acc.push([a.slice(2), arr[i + 1]]);
      return acc;
    }, [])
  );
  const url = args.url;
  const outDir = args.out;
  const label = args.label || "site";
  const measurePath = args.measure;
  if (!url || !outDir) throw new Error("need --url and --out");
  mkdirSync(outDir, { recursive: true });

  const chrome = await launchChrome();
  const cdp = await CDP.connect(chrome.webSocketDebuggerUrl);
  const results = [];
  const measurements = {};
  try {
    const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
    const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
    await cdp.send("Page.enable", {}, sessionId);
    await cdp.send("Runtime.enable", {}, sessionId);

    for (const vp of VIEWPORTS) {
      await cdp.send("Emulation.setDeviceMetricsOverride", {
        width: vp.w, height: vp.h, deviceScaleFactor: vp.dsf, mobile: vp.mobile,
      }, sessionId);
      const loaded = cdp.once("Page.loadEventFired", sessionId, 40000).catch(() => null);
      await cdp.send("Page.navigate", { url }, sessionId);
      await loaded;
      await sleep(2200); // settle fonts, lazy content, animations
      // scroll through the page to trigger lazy images, then back to top
      await cdp.send("Runtime.evaluate", { expression: "(async()=>{const h=document.body.scrollHeight;for(let y=0;y<h;y+=600){scrollTo(0,y);await new Promise(r=>setTimeout(r,60));}scrollTo(0,0);})()", awaitPromise: true }, sessionId);
      await sleep(500);
      const hid = await cdp.send("Runtime.evaluate", { expression: HIDE_OVERLAYS, returnByValue: true }, sessionId);
      await sleep(300);

      const metrics = await cdp.send("Page.getLayoutMetrics", {}, sessionId);
      const cw = Math.ceil(metrics.cssContentSize.width);
      const ch = Math.min(Math.ceil(metrics.cssContentSize.height), 22000);
      const shot = await cdp.send("Page.captureScreenshot", {
        format: "png",
        captureBeyondViewport: true,
        clip: { x: 0, y: 0, width: cw, height: ch, scale: 1 },
      }, sessionId);
      const file = join(outDir, `${label}-${vp.name}.png`);
      writeFileSync(file, Buffer.from(shot.data, "base64"));
      results.push({ vp: vp.name, file, w: cw, h: ch, overlaysHidden: hid.result.value });
      console.log(`  ${label} ${vp.name} -> ${file} (${cw}x${ch}, overlays hidden: ${hid.result.value})`);

      if (measurePath && ["390x844", "768x1024", "1440x1000"].includes(vp.name)) {
        const m = await cdp.send("Runtime.evaluate", { expression: measureExpr(), returnByValue: true }, sessionId);
        measurements[vp.name] = m.result.value;
      }
    }
    if (measurePath) {
      mkdirSync(join(measurePath, ".."), { recursive: true });
      writeFileSync(measurePath, JSON.stringify(measurements, null, 2));
      console.log(`  measurements -> ${measurePath}`);
    }
  } finally {
    cdp.close();
    await chrome.close();
  }
  console.log(`DONE ${label}: ${results.length} screenshots`);
}

main().catch((e) => { console.error("CAPTURE FAILED:", e); process.exit(1); });
