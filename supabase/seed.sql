-- =============================================================================
-- LOCAL DEVELOPMENT SEED — FICTIONAL / PLACEHOLDER DATA ONLY
-- Do NOT run in production. Contains no real customers. Prices/text are
-- PLACEHOLDERS pending OWNER_DECISIONS.md confirmation.
-- =============================================================================

-- Plans (placeholder pricing — confirm in OWNER_DECISIONS.md, then set stripe_price_id)
insert into public.plans (code, name, description, price_cents, active_capacity, max_active_projects, turnaround_note, revision_note, sort_order)
values
  ('starter',    'Starter Estimating Support',      'PLACEHOLDER — confirm', 99500,  3, 1, 'PLACEHOLDER', 'PLACEHOLDER', 1),
  ('growth',     'Growth Bid Support',              'PLACEHOLDER — confirm', 199500, 7, 2, 'PLACEHOLDER', 'PLACEHOLDER', 2),
  ('department', 'Outsourced Estimating Department','PLACEHOLDER — confirm', 299500, 12, 3, 'PLACEHOLDER', 'PLACEHOLDER', 3)
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
  ('Plans and billing','What does monthly capacity mean?','Monthly plans reserve estimating capacity (standard bids per month). They are not unlimited-use plans; classifications are confirmed during onboarding.',3)
on conflict do nothing;
