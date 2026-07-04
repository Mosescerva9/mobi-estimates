# Mobi Estimates — Marketing Website

A fast, fully-static marketing site for **Mobi Estimates**, a nationwide construction
estimating firm. Built with HTML + Tailwind-inspired design tokens, plain CSS, and
dependency-free JavaScript. No build step or framework is required to run it.

> Design direction: **Trust & Authority** — professional navy + blue, Plus Jakarta Sans
> (with Fraunces serif accents), elegant scroll/entrance animations that respect
> `prefers-reduced-motion`.

## Preview

It's a static site — open `index.html` directly, or serve the folder:

```bash
cd mobi-estimates
python3 -m http.server 8080
# visit http://localhost:8080
```

## Structure

```
mobi-estimates/
├── *.html                 # 18 generated pages (do not edit by hand)
├── assets/
│   ├── css/styles.css     # design tokens, components, animations
│   ├── js/site.js         # nav drawer, scroll reveal, FAQ, forms, dropzone
│   └── img/               # trimmed logo, icon, favicons
├── build.py               # shared templates: <head>, header/nav, footer, icons, components
└── generate.py            # page content + build entrypoint
```

## Editing

Pages are **generated**. Edit `build.py` (layout/chrome) or `generate.py` (page content),
then rebuild:

```bash
python3 generate.py
```

## Pages

Home · About · Services · Quantity Takeoffs · Construction Cost Estimating ·
General Contractor Estimating · Subcontractor Estimating · Monthly Estimating Support ·
Industries · How It Works · Upload a Project · Request a Quote · FAQ · Contact ·
Client Login · Privacy Policy · Terms of Service · Estimating Disclaimer

## Notes

- **Forms** are front-end only (validation + simulated submit + success state). Wire the
  `<form data-demo-form>` elements to a real backend / email service before launch.
- **Client Login** is a UI placeholder; connect it to a real portal/auth when ready.
- Content intentionally avoids unverifiable claims (years in business, $ estimated, win
  rates, accuracy %). Replace the credibility section with real figures once available.
- Contact details (`(800) 555-0142`, `estimates@mobiestimates.com`) are placeholders —
  update them in `build.py`.
