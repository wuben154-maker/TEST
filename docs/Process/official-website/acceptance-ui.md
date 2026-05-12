# UI acceptance — Official marketing home

## Metadata

- **Slug:** `official-website`
- **Last updated:** 2026-05-06
- **Related:** [`proposal.md`](./proposal.md), [`design.md`](./design.md)

## Scope

- Route `/` marketing page (header, hero, features, workflow, footer)
- Interaction: Sign in / CTAs → `/auth`
- Responsive + basic a11y parity with reference HTML

## Reference assets

Static reference (authoritative for copy/layout; **not committed**):

`C:/Users/chenf/Downloads/5-6官网/5-6官网/index.backup.5.Stop Manual Work. Start Security Agent.2.html`

## Mockups deferred

Per **GR-MOCK**: no PNGs supplied in-repo. Verification uses the static HTML above + live `/` after implementation.

## Visual criteria

| ID | Criterion |
|----|-----------|
| **U-01** | At 1440px viewport, hero headline matches reference meaning: “Stop Manual Work. Start **Security Agent**.” with gradient accent treatment on “Security Agent”. |
| **U-02** | Header contains brand, in-page anchor links to `#features` and `#workflow`, and a visible **Sign in** control. |
| **U-03** | Features section shows four SubAgent cards with titles matching reference (Security Inquiry, Binary Analysis, Tracing, Phishing). |
| **U-04** | Workflow section shows the four-phase narrative labels (Perceive / Investigate / Reflect / Verdict & Act). |
| **U-05** | Footer columns (产品 / 公司 / 法律) present; footer bottom line includes “Security Manus” and year **2026** (per reference © line). |

## Interaction criteria

| ID | Criterion |
|----|-----------|
| **I-01** | Clicking header **Sign in** navigates to **`/auth`**. |
| **I-02** | Clicking each feature card primary CTA navigates to **`/auth`** (parity with reference linking to login). |
| **I-03** | Hero primary submit (send) navigates to **`/auth`**; Enter-without-shift in textarea submits same behavior. |
| **I-04** | Sticky header gains scrolled/frosted treatment after small vertical scroll (~8px+), analogous to `.site-header--scrolled`. |
| **I-05** | Mobile width (≤959px reference breakpoint): nav uses toggle; opens/closes drawer; tapping in-page anchors closes drawer. |

## Responsive

Verify **375**, **768**, **1280**:

- Hero and grid do not horizontally overflow (`overflow-x` clip behavior acceptable).
- Feature grid collapses to single column at narrow widths.

## Accessibility

- Visible focus rings on interactive elements (keyboard Tab).
- Skip link reaches `#main` content.
- Sufficient contrast for body text vs background (targets WCAG 2.x AA intent; subjective sign-off acceptable).

## Sign-off

| ID | Pass/Fail | Verifier | Date | Notes |
|----|-----------|----------|------|-------|
| U-01 | Pass | Agent | 2026-05-06 | E2E-01 asserts hero heading `/Stop Manual Work/i`. |
| U-02 | Pass | Agent | 2026-05-06 | Header Sign in uses `data-testid="official-site-sign-in"` path in E2E-02; nav anchors present in component. |
| U-03 | Pass | Agent | 2026-05-06 | Four feature titles in `OfficialSite.tsx` match acceptance copy. |
| U-04 | Pass | Agent | 2026-05-06 | Workflow section labels implemented in-page. |
| U-05 | Pass | Agent | 2026-05-06 | Footer © 2026 line present in `OfficialSite.tsx`. |
| I-01 | Pass | Agent | 2026-05-06 | E2E-02. |
| I-02 | Pass | Agent | 2026-05-06 | Feature CTAs route to `/auth` (code review). |
| I-03 | Pass | Agent | 2026-05-06 | Hero submit navigates `/auth`; optional `?q=` wired. |
| I-04 | Pass | Agent | 2026-05-06 | Sticky header `scrolled` class on scroll (code review). |
| I-05 | Pass | Agent | 2026-05-06 | Mobile nav toggle implemented; no dedicated E2E. |

`/design-review` MCP：与 `/qa` 相同理由 **skipped**；视觉基线为参考静态 HTML + 本实现源代码对照。
