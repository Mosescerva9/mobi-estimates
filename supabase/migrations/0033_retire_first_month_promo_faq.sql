-- =============================================================================
-- Mobi Estimates — Retire the 50%-off-first-month promotion from seeded FAQ and
-- replace it with the approved intro-offer wording.
--
-- The old promotion is fully retired. New copy states: one qualifying estimate
-- free per new company, no card, supported scope/complexity reviewed before
-- acceptance, regular pricing from month one after that, and no guaranteed win.
-- =============================================================================

-- Remove the retired-promotion FAQ rows (and the obsolete "Join Now" answer that
-- pointed at the old join-first funnel).
delete from public.faq_entries
 where question in (
   'Do you offer a free trial?',
   'Is the 50% discount recurring?',
   'Where does the Join Now button take me?',
   'Is there a free trial?',
   'Do new monthly subscribers get a first-month discount?',
   'Does the free estimate mean you will win my bid?'
 );

insert into public.faq_entries (category, question, answer, sort_order) values
  ('Plans and billing',
   'Is there a free trial?',
   'Not a trial, but new companies get one qualifying estimate free with no card required. Supported scope and project complexity are reviewed before acceptance. After that, regular monthly or pay-per-project pricing applies.',
   10),
  ('Plans and billing',
   'Do new monthly subscribers get a first-month discount?',
   'No. The regular monthly price applies from month one. There is no 50%-off-first-month promotion.',
   11),
  ('Plans and billing',
   'Does the free estimate mean you will win my bid?',
   'No. Mobi helps you track bid progress and follow-up steps. We do not promise a turnaround time or a guaranteed win, and final estimate delivery stays behind our human review and approval gates.',
   13);
