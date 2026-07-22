import { EXPLAINER_VIDEO } from "@/lib/explainer-video";

export function ExplainerVideo() {
  return (
    <section id="explainer-video" aria-labelledby="explainer-heading" className="scroll-mt-24 bg-slate-50 py-16 sm:py-20 lg:py-24">
      <div className="mx-auto max-w-6xl px-5 sm:px-7 lg:px-10">
        <div className="mx-auto max-w-3xl text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand">See the workflow</p>
          <h2 id="explainer-heading" className="mt-3 text-balance text-3xl font-bold tracking-tight text-navy sm:text-4xl lg:text-5xl">{EXPLAINER_VIDEO.title}</h2>
          <p className="mx-auto mt-5 max-w-2xl text-base leading-7 text-slate-600 sm:text-lg">{EXPLAINER_VIDEO.description}</p>
        </div>

        <div className="mx-auto mt-10 max-w-5xl overflow-hidden rounded-[1.75rem] border border-slate-200 bg-navy-deep shadow-2xl shadow-navy/20">
          <div className="aspect-video">
            {EXPLAINER_VIDEO.src ? (
              <video className="h-full w-full bg-black object-cover" controls preload="metadata" poster={EXPLAINER_VIDEO.poster || undefined} aria-label={EXPLAINER_VIDEO.title}>
                <source src={EXPLAINER_VIDEO.src} type="video/mp4" />
                Your browser does not support embedded video.
              </video>
            ) : (
              <div role="img" aria-label={EXPLAINER_VIDEO.placeholderLabel} className="relative flex h-full items-center justify-center overflow-hidden bg-[radial-gradient(circle_at_75%_20%,rgba(94,134,196,.5),transparent_35%),linear-gradient(135deg,#0c1830,#1e3157)] px-5 text-center">
                <div aria-hidden="true" className="absolute inset-0 opacity-20 [background-image:linear-gradient(rgba(255,255,255,.15)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.15)_1px,transparent_1px)] [background-size:42px_42px]" />
                <div className="relative flex max-w-xl flex-col items-center gap-3 sm:gap-5">
                  <span className="rounded-full border border-white/20 bg-white/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-blue-100 sm:text-xs">Temporary development preview</span>
                  <span aria-hidden="true" className="flex h-14 w-14 items-center justify-center rounded-full border border-white/40 bg-white/10 shadow-xl backdrop-blur sm:h-20 sm:w-20"><span className="ml-1 text-2xl text-white sm:text-4xl">▶</span></span>
                  <div><p className="text-base font-semibold text-white sm:text-xl">Final Mobi explainer video coming soon</p><p className="mx-auto mt-2 max-w-md text-xs leading-5 text-blue-100 sm:text-sm">No stock footage or sample video is being shown. This branded frame will be replaced when the completed video is supplied.</p></div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
