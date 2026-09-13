# FleetBuilt Partners — Marketing Website

A fast, fully-static marketing site for **FleetBuilt Partners**, CDL academy launch
support. Built with HTML + design tokens, plain CSS, and dependency-free JavaScript.
No framework is required to run it.

> Design direction: **Trust & Authority** — royal navy + emerald, Poppins
> (open source under the SIL Open Font License), elegant scroll/entrance animations that respect
> `prefers-reduced-motion`.

## Preview

It's a static site — open `index.html` directly, or serve the folder:

```bash
cd marketing-site
python3 -m http.server 8080
# visit http://localhost:8080
```

## Structure

```
marketing-site/
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

Home · About · Services · Feasibility Blueprint · Founding implementation ·
How It Works · Pricing · What You Get · FAQ · Contact ·
Privacy Policy · Terms of Service · Launch-Support Disclaimer

## Notes

- **Forms** are front-end only (validation + simulated submit + success state). Wire the
  `<form data-demo-form>` elements to a real backend / email service before launch.
- **Client Login** is a UI placeholder; connect it to a real portal/auth when ready.
- Content intentionally avoids unverifiable claims (years in business, $ estimated, win
  rates, accuracy %). Replace the credibility section with real figures once available.
- Contact details live in `config.py`: `EMAIL` (`moses@fleetbuiltpartners.com`) is the
  public address. `PHONE`/`PHONE_HREF` are blank until a verified number exists.
