-- =============================================================================
-- LOCAL DEVELOPMENT SEED — FICTIONAL / PLACEHOLDER DATA ONLY
-- Do NOT run in production. Contains no real customers. Prices/text are
-- PLACEHOLDERS pending OWNER_DECISIONS.md confirmation.
-- =============================================================================

-- Plans — the three APPROVED monthly subscription plans. Public prices mirror
-- src/lib/pricing.ts (the source of truth). Set stripe_price_id per environment.
-- Pay Per Project is a one-time option, not a plan row (see pay_per_project_orders).
insert into public.plans (code, name, description, price_cents, sort_order)
values
  ('starter',               'Starter',               'Add estimating capacity without hiring another full-time estimator.', 99500,  1),
  ('growth',                'Growth',                'More monthly estimating capacity so you can submit more bids.',       199500, 2),
  ('estimating_department', 'Estimating Department', 'Your outsourced estimating department for steady monthly bid volume.', 299500, 3)
on conflict (code) do nothing;

-- Training modules (video_url left blank — owner to supply; summaries are real policy)
insert into public.training_modules (code, title, summary, sort_order) values
  ('turnaround',   'How turnaround works',                       'Turnaround begins only after a project is accepted as complete.', 1),
  ('scope',        'What Mobi Estimates does and does not do',    'Estimates are professional opinions, not guarantees.', 2),
  ('questions',    'How estimator questions are handled',         'Questions are answered in the portal; no phone call required.', 3),
  ('review',       'How clients should review completed estimates','Clients must review the estimate before using or submitting it.', 4),
  ('revisions',    'How revisions and addenda work',              'Addenda may affect the completion date.', 5),
  ('capacity',     'How subscription capacity works',             'Plans reserve capacity; they are not unlimited-use.', 6)
on conflict (code) do nothing;

-- A starting service agreement version (DRAFT — attorney review required)
insert into public.service_agreements (version, title, body, is_current)
values ('v1-draft', 'Estimating Service Agreement (DRAFT)',
        'DRAFT — not attorney-approved. See OWNER_DECISIONS.md. Final language to be supplied by the owner/counsel before launch.',
        true)
on conflict (version) do nothing;

-- A few approved FAQ entries (mirrors the public site; safe for the assistant)
insert into public.faq_entries (category, question, answer, sort_order) values
  ('Turnaround','When does turnaround start?','Turnaround begins only after a project is accepted as complete. Missing documents or late addenda may affect the completion date.',1),
  ('Estimate process','Are estimates guaranteed?','No. Estimates are professional opinions based on the documents and information available at the time. Clients must review the estimate before using or submitting it.',2),
  ('Plans and billing','What does monthly capacity mean?','Monthly plans reserve estimating capacity (standard bids per month). They are not unlimited-use plans; classifications are confirmed during onboarding.',3),
  ('Plans and billing','Do you offer a free trial?','No. Mobi Estimates does not offer a free trial. New monthly subscribers receive 50% off their first month, and regular monthly pricing begins with the second month.',10),
  ('Plans and billing','Is the 50% discount recurring?','No. The 50% discount applies only to the first month of a new monthly subscription. Regular pricing begins with the second month.',11),
  ('Plans and billing','Can I purchase only one estimate?','Yes. The Pay Per Project option is a one-time payment of $199 for one estimate. It does not create a monthly subscription.',12),
  ('Plans and billing','Where does the Join Now button take me?','The Join Now button takes you to the pricing page, where you can compare the available options and choose the plan that fits your business.',13)
on conflict do nothing;
