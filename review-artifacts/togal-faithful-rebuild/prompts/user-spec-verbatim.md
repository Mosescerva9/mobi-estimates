Use browser inspection, screenshots, computed styles where legally and technically available, and direct visual measurement.

The specification does not need every value to be mathematically identical, but it must be close enough to produce the same visual proportions.

FONT REQUIREMENT

Identify the font family or the closest legally usable equivalent to Togal.AI’s current font.

Do not choose a font simply because it is “modern.”

Compare:

- Lowercase shapes
- Width of characters
- Weight
- Roundedness
- Headline density
- Paragraph appearance
- Numerals
- Button text

Use the exact font only when it is publicly licensed and legally available for Mobi’s use.

Otherwise, choose the closest open-source or properly licensed equivalent.

Implement the complete font-weight system correctly.

Do not use a default browser font.

Do not use Inter automatically unless visual comparison confirms that it is the closest match.

GLOBAL DESIGN TOKENS

Build a centralized design-token system based on the Togal visual measurements.

Include variables or theme tokens for:

- Page background
- Surface colors
- Mobi primary color
- Mobi secondary color
- Dark hero overlay
- Text colors
- Muted text
- Border colors
- Button radius
- Card radius
- Image radius
- Container width
- Mobile page padding
- Tablet page padding
- Desktop page padding
- Section spacing
- Heading sizes
- Body sizes
- Line heights
- Shadows
- Transition timing

Do not scatter arbitrary styling values throughout the codebase.

BUTTONS MUST MATCH

The buttons on the failed redesign do not have permission to remain unless they closely match Togal’s proportions.

Recreate the Togal button system for Mobi:

- Same approximate height
- Same approximate width behavior
- Same corner radius
- Same font weight
- Same internal padding
- Same text alignment
- Same hover movement or color behavior
- Same mobile full-width behavior
- Same navigation button proportions

Use Mobi’s brand color instead of Togal green.

The primary CTA text must be:

“Book a Free Estimate”

It must be the visually dominant button throughout the website.

Do not use pill-shaped buttons unless Togal currently uses that exact shape in the corresponding location.

Do not invent gradients, glow effects, glass effects, thick shadows, or oversized rounded corners.

HEADER AND NAVIGATION

Recreate the current Togal header structure closely.

Desktop should match its:

- Overall height
- White background
- Logo placement
- Navigation positioning
- Menu spacing
- CTA size
- Login placement
- Alignment
- Horizontal padding
- Sticky or non-sticky behavior

Mobile should match its:

- Header height
- Logo scale
- CTA scale
- Hamburger size
- Hamburger spacing
- Side padding
- Menu opening behavior
- Menu typography
- Menu item spacing

Replace Togal branding with the existing Mobi logo.

Do not redesign the Mobi logo.

Do not place the logo inside an unnecessary card or container.

HERO SECTION

The hero must closely reproduce the composition shown on Togal.AI.

Use:

- A large background image or video area
- A dark Mobi-colored overlay
- White hero text
- Small uppercase eyebrow
- Large multi-line headline
- Supporting paragraph
- Large primary CTA
- Secondary link below the CTA
- Similar content width
- Similar left alignment
- Similar vertical placement
- Similar relationship between text and background
- Similar transition into the next section

Use this exact headline:

“Estimating Department in Your Pocket”

Use this eyebrow:

“AI-POWERED CONSTRUCTION ESTIMATING”

Use this supporting copy:

“Mobi gives contractors a complete estimating department without the overhead of hiring one. Upload your plans, collaborate directly as the estimate is built, request changes, and receive a detailed human-reviewed estimate shaped around your scope, pricing, and preferences.”

You may improve punctuation and responsive line wrapping, but do not replace the positioning with generic software language.

Primary button:

“Get A Free Estimate Trial”

Secondary link:

“See How Mobi Works →”
The secondary link must scroll to the explainer video.

HERO BACKGROUND

Use an existing Mobi-owned construction, estimating, plan-review, or platform visual.

When no suitable hero asset exists, create a temporary Mobi-branded visual composition using assets we own.

Do not use Togal’s background image.

Do not use an obviously AI-generated construction worker image.

Do not use generic stock imagery that makes Mobi look cheap.

Apply the overlay with similar darkness and readability to Togal’s hero.

The hero image should remain visible but subordinate to the text.

VIDEO SECTION

Directly after the hero, recreate the same type of large, rounded video presentation used by Togal.

The explainer video will be recorded this weekend.

Until it is ready:

- Build the final video component now.
- Use a high-quality temporary Mobi thumbnail.
- Preserve a 16:9 ratio.
- Match Togal’s approximate radius.
- Match its width and surrounding spacing.
- Add a centered play control.
- Ensure the component is easy to update through one video URL and one thumbnail URL.
- Document the exact file or CMS field to replace.

Do not insert a generic embedded YouTube video merely to fill space.

PAGE STRUCTURE

Mirror the current Togal.AI homepage section rhythm and hierarchy from top to bottom, translated to Mobi’s business.

Use this Mobi content mapping:

1. Togal-style navigation
2. Togal-style hero
3. Mobi explainer video
4. Real credibility or customer-logo strip
5. Mobi value-proposition section
6. Benefit or capability grid
7. Collaboration and contractor-feedback section
8. Multi-trade estimating section
9. Estimate deliverables or product-interface section
10. Real customer testimonials
11. Final conversion section
12. Togal-style multi-column footer

Do not add unnecessary sections merely to make the page longer.

Do not use fake customer logos or testimonials.

When Mobi does not yet have enough real logos or testimonials, create a clean structurally correct component and hide it until real content is available, rather than filling it with fake proof.

CONTENT MAPPING RULE

Match each Togal component with the closest truthful Mobi equivalent.

Examples:

- Togal takeoff benefit grid becomes Mobi estimating-service benefits.
- Togal collaboration capability becomes contractor live review and revision.
- Togal automation capability becomes AI-assisted estimating with human review.
- Togal trade pages become Mobi multi-trade support.
- Togal product imagery becomes Mobi portal, estimate, takeoff, or workflow imagery.
- Togal demo CTA becomes “Book a Free Estimate.”

Mobi is not only takeoff software.

Do not accidentally position Mobi as a Togal clone at the product level.

Mobi’s core positioning is:

A contractor-facing estimating department that combines automation, contractor collaboration, and human-reviewed deliverables.

RESPONSIVE MATCHING

Do not design desktop first and allow CSS to collapse randomly.

At each target viewport, compare Mobi directly against Togal.

For mobile, match:

- Header proportions
- Hero height
- Hero text location
- Headline size
- Headline wrapping
- Paragraph width
- Button width
- Button height
- Spacing before the video
- Video radius
- Section padding
- Card stacking
- Footer stacking

For tablet, match:

- Container width
- Grid transition
- Header behavior
- Text and image balance
- Section spacing
- Image scale

For desktop, match:

- Maximum content width
- Hero scale
- Navigation spacing
- Grid column widths
- Section vertical rhythm
- Content alignment
- Footer columns

Use explicit responsive rules rather than hoping automatic wrapping produces the right result.

VISUAL QA LOOP

This is the most important requirement.

After each major component is implemented:

1. Run the local or preview website.
2. Capture a screenshot.
3. Capture or open the corresponding Togal screenshot.
4. Compare them side by side.
5. Identify visible discrepancies.
6. Correct the code.
7. Repeat.

At minimum, perform comparison loops for:

- Header
- Mobile hero
- Desktop hero
- Video area
- First content section
- Benefit grid
- Testimonial area
- Final CTA
- Footer
- Full mobile page
- Full desktop page

Do not mark the work complete while major differences remain in:

- Font
- Scale
- Spacing
- Alignment
- Button shape
- Button dimensions
- Card shape
- Section height
- Image sizing
- Mobile wrapping
- Background placement

PIXEL-DIFFERENCE REVIEW

Where practical, create overlay comparisons between the Mobi screenshot and the reference screenshot.

Because content and brand colors differ, do not expect literal pixel equality.

Use the overlay to evaluate:

- Element positions
- Relative widths
- Relative heights
- Whitespace
- Alignment
- Section boundaries
- Component proportions

Save the comparison screenshots as review artifacts.

PROHIBITED DESIGN BEHAVIOR

Do not:

- Freestyle the design
- “Improve” Togal’s layout
- Add trendy visual effects
- Add excessive gradients
- Add glassmorphism
- Use random pill-shaped cards
- Use oversized rounded containers
- Add floating decorative blobs
- Use excessive animations
- Add AI-generated construction scenes
- Replace sections with generic SaaS templates
- Use an unrelated Tailwind landing-page template
- Preserve styling solely because it already exists
- Declare completion after one implementation pass
- use Togal’s source code or proprietary assets
- copy Togal customer logos or testimonials
- make unsupported speed or accuracy claims

FUNCTIONAL PROTECTION

Before replacing the visual layer, audit and preserve:

- Routes
- Pricing links
- Login
- Registration
- Stripe
- Estimate intake flow
- Contact forms
- Customer portal
- Analytics
- SEO metadata
- Sitemap
- Robots configuration
- Blog
- Redirects
- Existing API integrations

Create a safe branch before implementation.

Do not deploy directly to production.

IMPLEMENTATION QUALITY

The final implementation must:


- Use reusable components
- Use centralized design tokens
- Use semantic HTML
- Be accessible
- Have visible focus states
- Have usable keyboard navigation
- Have appropriate contrast
- Use optimized imagery
- Avoid cumulative layout shift
- Avoid horizontal overflow
- Avoid console errors
- Avoid dead links
- Avoid placeholder buttons
- Avoid duplicated CSS
- Avoid unnecessary dependencies
- Preserve strong page performance

FABLE 5 ACCEPTANCE GATES

Fable 5 must not approve the work until all gates pass.

Gate 1: Structural match
- Section order and general component structure closely match Togal.

Gate 2: Typography match
- The font, weights, sizes, line heights, and wrapping closely match the reference.

Gate 3: Component match
- Buttons, cards, videos, navigation, imagery, and footer use similar proportions and shapes.

Gate 4: Mobile match
- The 390px mobile version closely matches Togal’s layout density and hierarchy.

Gate 5: Tablet match
- The iPad layouts look intentional and not like enlarged mobile pages.

Gate 6: Desktop match
- The desktop page matches Togal’s container widths, whitespace, and visual rhythm.

Gate 7: Brand conversion
- Togal’s brand has been completely replaced by Mobi’s colors, logo, wording, assets, and CTAs.

Gate 8: Functional verification
- Existing critical website functionality still works.

Gate 9: Screenshot review
- Side-by-side screenshots show a strong visual match.

Gate 10: Preview readiness
- No major visual defects, dead controls, placeholder copy, console errors, or broken layouts remain.

EXECUTION ORDER

1. Create a safe branch.
2. Audit the failed redesign.
3. Audit the existing functional routes and integrations.
4. Capture Togal reference screenshots.
5. Produce the visual measurement specification.
6. Identify the closest legal font.
7. Build the design tokens.
8. Rebuild the header.
9. Rebuild the hero.
10. Build the video component.
11. Rebuild the remaining homepage sections in Togal’s order and rhythm.
12. Rebuild the footer.
13. Run mobile comparison passes.
14. Run tablet comparison passes.
15. Run desktop comparison passes.
16. Run functional QA.
17. Have Fable 5 perform final visual review.
18. Fix every material issue it identifies.
19. Deploy a preview.
20. Return the review package.

FINAL RESPONSE FORMAT

Do not send me a large running commentary.

Do not repeatedly ask me to approve routine implementation decisions.

Return only when a materially improved preview is ready.

Provide:

- Preview URL
- Branch name
- Pull request URL
- Exact font selected
- Mobile screenshot
- iPad screenshot
- Desktop screenshot
- Side-by-side reference comparison
- Overlay comparison where available
- List of existing functionality tested
- Confirmation that the main CTA says “Book a Free Estimate”
- Confirmation of where that CTA leads
- Exact location for replacing the video this weekend
- Any Mobi assets still needed
- Any sections hidden because real proof or content is not yet available

This task is not complete because the code builds.

It is complete only when the Mobi homepage looks and behaves extremely close to Togal.AI’s current website while remaining unmistakably Mobi Estimates.
The website redesign you just completed is not acceptable.

It does not visually match the Togal.AI reference closely enough, and the result looks significantly worse than the reference. Do not try to improve the current design through small edits. Start a controlled visual rebuild of the Mobi Estimates marketing homepage.

PRIMARY DIRECTIVE

Rebuild the Mobi Estimates homepage as a highly faithful, measurement-driven recreation of the current Togal.AI homepage design system.

Reference website:

https://www.togal.ai/

Use Togal.AI as the visual specification for:

- Overall page structure
- Section order
- Navigation proportions
- Hero height
- Hero image
- Container widths
- Typography hierarchy
- Font style
- Font weights
- Font sizing
- Line heights
- Headline wrapping
- Button dimensions
- Button corner radius
- Card dimensions
- Card corner radius
- Image placement
- Video placement
- Section spacing
- Internal padding
- Background transitions
- Alignment
- Grid behavior
- Mobile stacking
- Tablet layout
- Desktop layout
- Footer structure
- Hover behavior
- Animation restraint
- Responsive behavior

This is not a request for a website that is merely “inspired by” Togal.AI.

The goal is for someone viewing Mobi and Togal side by side to immediately see that the two sites use nearly the same layout, proportions, typography system, spacing system, component shapes, and responsive behavior.

The differences must be:

- Mobi Estimates branding
- Mobi logo
- Mobi colors
- Mobi wording
- Mobi product screenshots
- Mobi video
- Mobi customer information
- Mobi calls to action
- Mobi functionality
- Mobi pricing
Do not copy Togal’s source code, proprietary imagery, videos, logos, testimonials, customer logos, or unsupported marketing claims.

AGENT AND EXECUTION REQUIREMENT

Use the Fable 5 workflow to manage this rebuild.

Use Claude Code as the primary implementation agent.

Fable 5 must:

1. Define the visual target.
2. Inspect the existing implementation.
3. Identify why the previous redesign failed.
4. Break the rebuild into measurable stages.
5. Direct Claude Code through each implementation stage.
6. Review screenshots after every major stage.
7. Compare the screenshots against Togal.AI.
8. Reject visually inaccurate work.
9. Repeat implementation and review until the visual match is strong.
10. Prevent the task from being declared finished merely because the page compiles.

Claude Code must perform the actual code inspection, component implementation, styling, testing, responsive fixes, screenshot generation, and preview deployment.

Use the high reasoning model for Fable 5 planning and visual review.

DO NOT PRESERVE THE FAILED DESIGN

Do not treat the current redesign as a foundation that must be protected.

First inspect it and determine which parts should be:

- Removed
- Rebuilt
- Simplified
- Replaced
- Retained only for functionality

Preserve working backend functionality, routes, forms, integrations, authentication, analytics, and SEO behavior.

Do not preserve bad visual decisions merely because they were recently implemented.

VISUAL REVERSE-ENGINEERING PHASE

Before writing code, inspect the complete current Togal.AI homepage on:

- Mobile
- Tablet
- Desktop

Capture full-page screenshots at approximately:

- 390 × 844
- 430 × 932
- 768 × 1024
- 834 × 1194
- 1024 × 1366
- 1440 × 1000
- 1920 × 1080

Create a visual specification documenting estimated values for:

- Header height
- Logo dimensions
- Desktop navigation gap
- Hero minimum height
- Hero content width
- Hero left and right padding
- Hero top and bottom padding
- Eyebrow font size
- Hero heading font size
- Hero heading line height
- Hero heading weight
- Paragraph font size
- Paragraph line height
- Primary button height
- Primary button width
- Button padding
- Button radius
- Section vertical spacing
- Content maximum width
- Grid gaps
- Card padding
- Card radius
- Image radius
- Footer spacing
- Responsive breakpoint behavior

Do not guess broadly.

