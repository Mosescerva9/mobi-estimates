import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Construction Estimating Business Starter Kit | Mobi Estimates",
  description: "The unlocked Mobi Estimates starter kit for building a construction estimating service.",
  robots: { index: false, follow: false },
};

const plans = [
  ["Starter", "$995 / month", "Entry recurring option for lower estimating volume."],
  ["Growth", "$1,995 / month", "Higher recurring capacity for contractors bidding more consistently."],
  ["Estimating Department", "$2,995 / month", "Highest recurring tier for companies that need substantial outsourced capacity."],
  ["Pay Per Project", "$599 / project", "For contractors that do not need a monthly relationship yet."],
] as const;

const outreach = [
  ["Cold email", "Subject: Quick question about your estimating workload", "Hi [First Name], I came across [Company] and wanted to reach out. We help contractors handle overflow estimating so they can get more bids out without spending nights and weekends behind the computer. If estimating is a bottleneck for you right now, I’d be happy to handle one upcoming estimate free so you can judge the work before paying us anything. If you have a project coming up, send it over and I can tell you whether it’s a fit. - [Your Name]"],
  ["Short LinkedIn / DM", "Message", "Hey [First Name] - quick question. Are you still handling most of the estimating in-house? We help contractors with overflow estimating, and I’m offering the first project free so you can see the quality before committing to anything. Happy to take a look at an upcoming bid if it would help."],
  ["Phone opener", "20-second opener", "Hey [Name], this is [Your Name]. I’ll keep it quick. We help contractors with overflow estimating when bids start piling up. I’m not calling to lock you into anything - we’re offering the first estimate free so you can actually see the work. Are you bidding anything right now that you could use help getting out?"],
  ["Follow-up", "After no reply", "Hey [First Name] - just bumping this in case estimating gets backed up this week. The first project is still on us. If you send the plans and bid date, I can let you know quickly whether we can help."],
] as const;

const qa = [
  "Correct project and latest plan set are being used.",
  "All relevant addenda and revisions are included.",
  "Scope matches what the client requested.",
  "Major quantities have been sanity-checked.",
  "Obvious scope gaps have been investigated.",
  "Allowances, alternates, and exclusions are clearly labeled.",
  "Unit pricing sources and assumptions are appropriate for the project.",
  "Labor, location, tax, freight, waste, and equipment assumptions are considered where relevant.",
  "Markups are applied correctly and not duplicated.",
  "Estimate totals calculate correctly.",
  "Client-facing document is readable and professional.",
  "Reviewer has approved delivery.",
] as const;

const intake = [
  "Company / client name",
  "Primary contact name, email, and phone",
  "Project name and address/location",
  "Bid due date and time",
  "Plans / drawings received",
  "Specifications received if applicable",
  "Addenda received and current revision confirmed",
  "Scope/trades to estimate clearly defined",
  "Bid form or required client format received",
  "Labor assumptions / wage requirements identified",
  "Material or supplier preferences identified",
  "Sales tax / location-specific assumptions identified",
  "Alternates identified",
  "Exclusions / owner-supplied items identified",
  "Delivery format confirmed",
  "Questions / RFIs logged before estimating begins",
] as const;

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-slate-200 py-10 sm:py-14">
      <h2 className="text-2xl font-bold tracking-tight text-navy sm:text-3xl">{title}</h2>
      <div className="mt-5 space-y-5 leading-7 text-slate-700">{children}</div>
    </section>
  );
}

export default function StarterKitGuide() {
  return (
    <main className="min-h-screen bg-white text-slate-900">
      <header className="bg-navy-deep text-white">
        <div className="mx-auto max-w-4xl px-5 py-10 sm:px-7 sm:py-14">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-200">Mobi Estimates • Free Starter Kit</p>
          <h1 className="mt-4 text-balance text-4xl font-extrabold tracking-tight sm:text-5xl">Construction Estimating Business Starter Kit</h1>
          <p className="mt-4 max-w-2xl text-lg leading-8 text-blue-50">The practical blueprint for going from zero to your first 10 estimating clients.</p>
          <p className="mt-5 text-sm text-blue-200">Offer design • pricing • contractor outreach scripts • free-estimate funnel • client intake • QA checklist • lead tracker • first-10-clients action plan</p>
        </div>
      </header>

      <div className="mx-auto max-w-4xl px-5 sm:px-7">
        <Section title="What this kit will help you build">
          <p>You do not need complicated software, a giant team, or knowledge of every trade before you validate an estimating service. Your first goal is simpler: find contractors with a real estimating bottleneck, give them a low-risk way to test your service, deliver excellent work, and convert the right customers into recurring relationships.</p>
          <div className="rounded-2xl bg-blue-50 p-5 font-semibold text-blue-950">Contractor with a bid bottleneck → Free first estimate → Quality delivery → Paid project or monthly plan → Repeatable fulfillment</div>
          <ol className="list-decimal space-y-2 pl-6">
            <li>Choose a clear offer and customer profile.</li><li>Set up a simple fulfillment system with qualified human review.</li><li>Build a list of contractors actively bidding work.</li><li>Offer a free first estimate to reduce the trust barrier.</li><li>Deliver the trial like it is already a paid account.</li><li>Follow up and offer the right paid option.</li><li>Document what worked, fix bottlenecks, and repeat.</li>
          </ol>
        </Section>

        <Section title="The business model in one page">
          <p>The product is not a spreadsheet. The product is estimating capacity. A contractor sends plans and project information; your company turns those inputs into a reviewed estimating deliverable so the contractor can spend less time behind a computer and more time running the business.</p>
          <div className="grid gap-4 sm:grid-cols-2">
            {[["Ideal customer","A contractor that bids consistently and has more estimating demand than available owner/staff time."],["Core pain","Estimating consumes time, slows bid volume, and competes with project management and sales."],["Entry offer","One qualified estimate free so the contractor can judge the work before committing."],["Paid offer","Pay-per-project or recurring monthly estimating capacity."],["Fulfillment","AI/automation for speed + a qualified estimator for review and judgment."],["Retention driver","Good work, reliable turnaround, communication, and becoming part of the contractor’s normal bid process."]].map(([k,v]) => <div key={k} className="rounded-2xl border border-slate-200 p-5"><h3 className="font-semibold text-navy">{k}</h3><p className="mt-2 text-sm leading-6 text-slate-600">{v}</p></div>)}
          </div>
          <div className="rounded-2xl bg-slate-50 p-5"><p className="text-sm font-semibold text-brand">Positioning statement</p><p className="mt-2 font-medium text-navy">“We help contractors get more bids out without spending nights and weekends estimating. Send us the plans, we handle the estimating workload, and a qualified estimator reviews the work before delivery.”</p></div>
        </Section>

        <Section title="Who to target first">
          <p>Prioritize general contractors and growing specialty contractors that actively bid work and feel estimating is stealing time from operations. A free estimate becomes expensive when it is offered to the wrong prospect.</p>
          <ul className="grid gap-3 sm:grid-cols-2">{["Bids weekly or several times per month","Owner/PM is still heavily involved in estimating","Trying to win more work or expand","Legitimate projects with usable plans/info","Responsive and can provide inputs","Can justify ongoing estimating spend"].map(x => <li key={x} className="rounded-xl bg-slate-50 p-4">✓ {x}</li>)}</ul>
          <p className="font-semibold text-navy">Rule of thumb: if you cannot explain why this company could become a repeat customer, do not spend heavily fulfilling a free trial for them.</p>
        </Section>

        <Section title="Build the offer">
          <p>The free first estimate exists to solve the trust problem. It should feel like the paid experience, not a rushed sample.</p>
          <div className="overflow-x-auto rounded-2xl border border-slate-200"><table className="w-full min-w-[640px] text-left text-sm"><thead className="bg-navy text-white"><tr><th className="p-4">Plan</th><th className="p-4">Price</th><th className="p-4">Purpose</th></tr></thead><tbody>{plans.map(([a,b,c]) => <tr key={a} className="border-t border-slate-200"><td className="p-4 font-semibold">{a}</td><td className="p-4">{b}</td><td className="p-4">{c}</td></tr>)}</tbody></table></div>
          <p className="rounded-2xl bg-amber-50 p-5 text-amber-950"><strong>Do not copy pricing blindly.</strong> Your capacity, project complexity, estimator cost, turnaround promise, revisions, and scope determine whether a price is profitable.</p>
        </Section>

        <Section title="Offer worksheet">
          {['Who do we serve?','What painful estimating bottleneck do we remove?','What exactly is included in the free first estimate?','What is explicitly NOT included?','What turnaround can we reliably promise?','What paid offer comes next?'].map(q => <div key={q}><p className="font-semibold text-navy">{q}</p><div className="mt-2 h-12 border-b border-dashed border-slate-300" /></div>)}
        </Section>

        <Section title="Your minimum viable fulfillment system">
          <ol className="list-decimal space-y-2 pl-6"><li><strong>Intake:</strong> receive plans, specifications, scope, due date, location, and client preferences.</li><li><strong>Qualification:</strong> confirm the project is estimable with the information provided.</li><li><strong>Project setup:</strong> organize files and assumptions.</li><li><strong>Takeoff / estimating:</strong> complete the requested work using your defined tools and process.</li><li><strong>Human review:</strong> a qualified estimator checks quantities, assumptions, scope gaps, and pricing logic.</li><li><strong>Corrections:</strong> resolve review issues before delivery.</li><li><strong>Delivery:</strong> send a professional estimate with exclusions and assumptions.</li><li><strong>Follow-up:</strong> ask for feedback and transition qualified trials into paid service.</li></ol>
          <p className="rounded-2xl bg-blue-50 p-5 font-semibold text-blue-950">Operating principle: AI is the speed layer. A qualified estimator owns the final judgment.</p>
        </Section>

        <Section title="Client intake checklist">
          <ul className="grid gap-2 sm:grid-cols-2">{intake.map(x => <li key={x} className="rounded-xl border border-slate-200 p-3 text-sm">☐ {x}</li>)}</ul>
        </Section>

        <Section title="Estimator QA checklist">
          <ul className="grid gap-2">{qa.map(x => <li key={x} className="rounded-xl border border-slate-200 p-3 text-sm">☐ {x}</li>)}</ul>
        </Section>

        <Section title="Contractor outreach scripts">
          <p>Keep outreach short. The goal is not to explain your entire business in the first message. The goal is to earn a reply or a chance to handle one real project.</p>
          <div className="space-y-4">{outreach.map(([type,label,copy]) => <article key={type} className="rounded-2xl border border-slate-200 p-5"><p className="text-xs font-semibold uppercase tracking-wide text-brand">{type}</p><h3 className="mt-1 font-semibold text-navy">{label}</h3><p className="mt-3 whitespace-pre-line text-sm leading-7 text-slate-600">{copy}</p></article>)}</div>
          <p>Do not blast these word-for-word to thousands of companies. Add one relevant detail, keep the tone human, and only contact legitimate prospects.</p>
        </Section>

        <Section title="Free trial → paid client conversion">
          <div className="rounded-2xl bg-slate-50 p-5"><p className="font-semibold text-navy">At delivery</p><p className="mt-2 text-sm">Hey [Name] - your estimate is ready. I’ve included the assumptions/exclusions so you can see exactly how we approached the project. Take a look and send over any questions or corrections you want us to review.</p></div>
          <div className="rounded-2xl bg-blue-50 p-5"><p className="font-semibold text-blue-950">After they have reviewed it</p><p className="mt-2 text-sm text-blue-950">Glad this was useful. If estimating keeps getting in the way of running jobs, we can keep handling these for you. We have a pay-per-project option for occasional work and monthly plans for contractors that bid consistently. Based on your volume, I’d probably point you toward [option]. Want me to send the breakdown?</p></div>
          <ul className="list-disc space-y-2 pl-6"><li>How many projects are you typically bidding each month?</li><li>Who currently handles estimating?</li><li>Where does the process usually get backed up?</li><li>What types and sizes of projects are most common?</li><li>How quickly do you normally need estimates returned?</li><li>Do you need occasional overflow help or ongoing capacity?</li></ul>
        </Section>

        <Section title="Simple lead tracker">
          <div className="overflow-x-auto rounded-2xl border border-slate-200"><table className="w-full min-w-[680px] text-left text-sm"><thead className="bg-navy text-white"><tr>{['Company','Contact','Fit','Last touch','Next action','Status'].map(x => <th key={x} className="p-3">{x}</th>)}</tr></thead><tbody><tr><td className="p-3">Example GC</td><td className="p-3">Jordan - Owner</td><td className="p-3">High</td><td className="p-3">8/9</td><td className="p-3">Call 8/11</td><td className="p-3">Trial offered</td></tr>{Array.from({length:6}).map((_,i) => <tr key={i} className="border-t border-slate-200"><td className="h-10" colSpan={6}></td></tr>)}</tbody></table></div>
          <p><strong>Recommended statuses:</strong> New lead • Contacted • Replied • Qualified • Trial offered • Trial in progress • Trial delivered • Paid client • Not now • Not a fit</p>
          <p className="font-semibold text-navy">Daily rule: never end the day with qualified leads sitting in the tracker and no next action.</p>
        </Section>

        <Section title="The first 10 clients action plan">
          <div className="space-y-3">{[["Days 1-3","Get sellable","Choose ICP, define the free trial and paid options, line up a qualified estimator/reviewer, and create intake + QA."],["Days 4-7","Build pipeline","Create an initial list of 100 qualified contractors with real contact information and a reason they fit."],["Week 2","Start conversations","Personalized email, calls, LinkedIn, and referrals. Track every touch and follow-up."],["Week 3","Deliver trials","Prioritize speed + accuracy. Ask for feedback immediately after delivery."],["Week 4","Convert + learn","Offer the right paid option. Record objections, conversion rate, project cost, and turnaround."],["Clients 1-10","Standardize","Document recurring tasks, templates, reviewer steps, and only then begin deeper automation."]].map(([phase,goal,what]) => <div key={phase} className="grid gap-2 rounded-2xl border border-slate-200 p-5 sm:grid-cols-[120px_150px_1fr]"><strong>{phase}</strong><span className="font-semibold text-brand">{goal}</span><span>{what}</span></div>)}</div>
        </Section>

        <Section title="Know your unit economics">
          <ul className="space-y-3"><li><strong>Trial → paid conversion rate:</strong> Paid clients from trials ÷ completed qualified trials.</li><li><strong>Customer acquisition cost:</strong> Sales + marketing + free-trial fulfillment cost ÷ new paying customers.</li><li><strong>Gross profit per client:</strong> Client revenue - direct fulfillment cost.</li><li><strong>Gross margin:</strong> Gross profit ÷ revenue.</li><li><strong>Simple lifetime revenue:</strong> Average monthly revenue per client × average client lifetime.</li><li><strong>Simple LTV:CAC check:</strong> Estimated customer value ÷ customer acquisition cost.</li></ul>
          <p className="rounded-2xl bg-amber-50 p-5 text-amber-950"><strong>Do not confuse revenue with take-home income.</strong> Subtract estimator/reviewer labor, software, sales and marketing, refunds/rework, payment fees, and other direct operating costs.</p>
        </Section>

        <Section title="The lean tool stack">
          <div className="grid gap-3 sm:grid-cols-2">{[["Business email","Professional domain email"],["Lead tracking","Spreadsheet or lightweight CRM"],["Client intake","Simple form + file upload"],["File storage","Organized cloud folders with access controls"],["Estimating / takeoff","Tools your qualified estimator can reliably use"],["AI assistance","Approved tools with human verification"],["Project tracking","Simple board/status system"],["Payments","Reliable invoicing/subscription processor"],["SOPs","Shared document or knowledge base"]].map(([need,solution]) => <div key={need} className="rounded-xl border border-slate-200 p-4"><p className="font-semibold text-navy">{need}</p><p className="mt-1 text-sm text-slate-600">{solution}</p></div>)}</div>
        </Section>

        <Section title="One-page project SOP">
          <ol className="list-decimal space-y-3 pl-6"><li><strong>Intake:</strong> required project information and files received.</li><li><strong>Qualification:</strong> scope is clear enough to estimate and deadline is feasible.</li><li><strong>Setup:</strong> files named, organized, and project created.</li><li><strong>Estimating:</strong> requested scope completed and assumptions documented.</li><li><strong>QA:</strong> quantities, scope, assumptions, and logic pass review.</li><li><strong>Corrections:</strong> QA comments resolved.</li><li><strong>Delivery:</strong> client receives final reviewed deliverable.</li><li><strong>Follow-up:</strong> feedback captured and next paid step offered where appropriate.</li></ol>
        </Section>

        <Section title="Your 7-day launch challenge">
          <div className="space-y-3">{[[1,"Write your one-sentence offer, free-trial scope, paid options, and ideal customer profile."],[2,"Identify or line up a qualified estimator/reviewer and walk through your QA checklist together."],[3,"Set up intake, file organization, lead tracker, and a professional delivery template."],[4,"Build your first 25-50 qualified contractor leads."],[5,"Begin personalized outreach and phone calls. Track every response."],[6,"Follow up, qualify interested contractors, and collect the first real project."],[7,"Review outreach, replies, qualified opportunities, objections, and next actions. Then repeat."]].map(([day,action]) => <div key={day} className="flex gap-4 rounded-2xl border border-slate-200 p-4"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-navy font-bold text-white">{day}</span><p>{action}</p></div>)}</div>
          <p className="font-semibold text-navy">The goal: get to the first real contractor conversation as fast as possible. Real feedback beats another week of planning.</p>
        </Section>

        <Section title="The three rules to remember">
          <div className="grid gap-4 sm:grid-cols-3">{[["1. Sell the outcome","Contractors care about getting bids out and getting time back - not your technology stack."],["2. Prove before you automate","A fast broken process is still broken. Get the service right, then add leverage."],["3. Quality protects the business","Estimating errors can have real financial consequences. Build human review and clear assumptions into the operating model."]].map(([a,b]) => <div key={a} className="rounded-2xl bg-slate-50 p-5"><h3 className="font-semibold text-navy">{a}</h3><p className="mt-2 text-sm leading-6 text-slate-600">{b}</p></div>)}</div>
        </Section>

        <section className="py-12 text-center sm:py-16">
          <h2 className="text-3xl font-bold tracking-tight text-navy">You have the blueprint. Now go get the first project.</h2>
          <p className="mx-auto mt-4 max-w-2xl leading-7 text-slate-600">Complete the offer worksheet, build your first 25 qualified contractor leads, contact them, get one real trial project, deliver it extremely well, and ask for the paid relationship.</p>
          <a href="/" className="mt-7 inline-flex min-h-12 items-center justify-center rounded-full bg-brand px-6 py-3 font-semibold text-white hover:bg-brand-dark">Follow Mobi Estimates</a>
        </section>
      </div>
    </main>
  );
}
