## Frontend Design Standards (AI for Security)

### 1) Document overview
**Version:** v1.2 (builds on v1.1 by merging **product context, tone/motion, alternate type scale/stack, engineering mapping, and anti-slop rules**. **Guardrails in this document still prevail**: warm dark foundation, `--accent-primary` warm primary actions, **focus rings blue-only**, semantic `--sev-*` used in **small areas only**. **The full canonical text lives only in this root-level `DESIGN.md`**; the former path `docs/design/design-standards-v1-1.md` was removed—do not reference it.)

**Scope**
- This document defines frontend visual consistency and scenario-specific UX patterns for the AI-for-Security product. Audience: web frontend engineers, product/design/UX, data viz owners, and design-system maintainers.
- Covers primary layouts including **main monitoring**, **landing**, **settings/configuration**, and related flows.

**Canonical location (single source of truth)**
- **Canonical:** repository root **`DESIGN.md`** (this file—the only place the full standard is maintained).

**Three-layer model (executable without being brittle—for AI and handoffs)**
- **Guardrails (mandatory):** Few, hard rules—what must never be crossed (testable).
- **Default strategy (recommended):** High-probability-right defaults; exceptions allowed **with documented rationale**.
- **Pattern library (optional templates):** Composable page skeletons and component recipes—prefer reuse over reinventing each time.

**Key definitions (for review & acceptance—not vibes-based debates)**
- **“Screen / above-the-fold”:** defaults to the **browser viewport** (excluding scrolled-away content). If the **right pane scrolls independently**, “above-the-fold” uses **that pane’s viewport**.
- **“Warm-light primary action”:** button fill `--accent-primary` (warm `#e8e5de`) plus Lovable Dark **inset** shadow—the dominant cue for **next-step / highest-priority** action (e.g. Primary CTA, critical-response entry).
- **“Semantic wash fill”:** using `--sev-*` as **full container**, **full-row table**, **whole-panel**, or any pattern where **reds/oranges/greens/blues dominate page chrome**. **Badge tints do not count** (see §7.1).

**Extensibility (new scenario onboarding—v1.1 flow)**
- **Step 0 — Classify scenario:** pick one of **Monitoring / Analysis**, **Marketing / Onboarding**, **Settings / Forms**, **Reporting / Export**.
- **Step 1 — Reuse skeletons:** prefer composing existing **cards / lists / forms / tags**; compose before inventing net-new primitives.
- **Step 2 — Information priority:**
  - One sentence: the page’s **primary goal** (e.g. spot highest severity, finish critical configuration, start trial).
  - Declare how **first visual focus** is achieved (**at least one**): **single warm-light primary** / **largest type + highest contrast** / **fixed top-left primary region above the fold**.
- **Step 3 — Color budget (guardrails + exceptions):**
  - **Warm-light primary (`--accent-primary`):** count per **above-the-fold viewport**—default **≤ 2** warm-light primary buttons.
  - **Default:** spotlight **next step on main path**; demote everything else to Secondary / Link.
  - **Exception:** allow a **third** only when **two distinct user goals must execute immediately** above the fold—**document why**.
  - **Semantic (`--sev-*`):** **text / stroke / tiny icon dots / badge tint only**—never full-row fills, full-panel fills, or full-screen gradients.
  - **Focus:** rings **blue only** (`--focus-blue` / `--ring-focus`)—never red/orange as focus chrome.
- **Step 4 — Minimum deliverables:**
  - 3–5 **page principles** for the scenario (defaults + allowed exceptions)
  - Layout constraints (width / columns / scroll model / breakpoints)
  - List of **new components** if unavoidable
  - **At least one** page skeleton example
- **Step 5 — Ship checklist:**
  - Warm-light primary count ≤ **2** above the fold
  - Semantic colors only on **text / stroke / icon dots / badge tint**
  - Focus rings consistently **blue**
  - Evidence/logs **copyable**, **collapsible**, **no forced hard-wrap**

#### 1.1 Product context — SecManus Workspace (merged)

- **What:** AI workspace for security analysis & research—IOCs, email/Web/logs, Deep Agent reasoning timelines, exportable reports.
- **Who:** Analysts, threat researchers, blue-team/compliance roles—long sessions; readability & trust first.
- **Category:** SOC-style tooling, TI, enterprise security—peers often run dark, dense consoles (Splunk, Elastic, VT, Recorded Future—**reference patterns, not clones**).
- **Surface:** Web shell (**sidebar + central report/reasoning**); landing/settings secondary but share the **same visual language** (§3).

#### 1.2 Engineering mapping (implementation anchors—does not replace §4.1 tokens)

| Concern | Path |
|--------|------|
| CSS variables (theme semantics) | `src/index.css` |
| Tailwind font/color extensions | `tailwind.config.ts` |
| shadcn/Radix variants | `src/components/ui/*` |

**Convergence rule:** §**4.1** tokens are the **numeric baseline**. If running code diverges (cool-neutral shell, saturated brand primary buttons, `ring` tied to brand hue vs §**2.1–2.2**, §**Step 3 focus guardrails**), treat as **implementation drift**—new work should converge to §**4.1**; time-bound waivers must be logged in §**11** with expected fix date.

---

### 2) Visual theme & design intent (“how,” not just adjectives)

#### 2.1 Warm dark foundation (Lovable Dark)
- Warm charcoal shell (`#1a1916`) vs pure black / cold gray—subtle warmth for long sessions without feeling icy.
- Body copy warm-light (`#e8e5de`) vs pure white—easier contrast without harsh glare.
- Goal: comfortable long reads, scannable density, hierarchy you can **feel** without noise.

**Defaults**
- Page: `--bg-0`; sections: `--bg-1`; inputs/panels: `--bg-2`.
- Layering priority: **1px border `#2e2c28`** > **inset shadow** > warm overlays—**don’t rely on heavy drop shadows** for card depth.
- Neutral ramps derive from warm-light `#e8e5de` transparency for hue unity.

#### 2.2 Warm-light primary actions
- `#e8e5de` fills Primary CTAs—a natural anchor on dark chrome plus Lovable inset shadow.
- **Scarcity:** when it appears, users should instantly know **this is the thing**.

**Guardrail (repeat)**
- §1 Step 3: default ≤ **2** warm-light primaries above the fold.

#### 2.3 Restrained elevation
- Hover/active deltas should read clearly **without exaggeration**—especially in monitoring where misleading emphasis risks wrong severity reads.

**Defaults**
- Hover: step surface lift (`rgba(232,229,222,0.04)` → `rgba(232,229,222,0.06)`) or stronger border.
- Primary button hover/active: `opacity: 0.85` / `0.8`.
- Forbidden: harsh glow loops, stacked heavy shadows, red interaction chrome that reads like **higher severity**.

#### 2.4 Tone — Industrial / Utilitarian (works with warm chrome)

- **Angle:** industrial utility + light **editorial** clarity—trustworthy instrument, not marketing illustration.
- **Decoration:** minimal → intentional; motion only where status matters (running / alert / success)—readable, never misleading severity.
- **Metaphor:** “clean analysis cockpit”—dense yet scannable; **no** giant hero gradients, neon primaries, or three-column icon billboards (landing exceptions §3.2).
- **Differentiation:** deliberately **not** generic “purple + Inter + gradient primary” AI-demo tropes—pair with §**9.6** QA.

#### 2.5 Motion

**Defaults**
- **Role:** minimal-functional—states only (expand/collapse, fade, drawer slide)—no infinite attention grabs.
- **Easing:** enter `ease-out`; exit `ease-in`; translation `ease-in-out`.
- **Timing:** micro **50–100ms** (hover); short **150–220ms** (menus); medium **250–400ms** (sidebars/large surfaces).

**Guardrail**
- Under monitoring context: motion reads as **progress** or **UI feedback**, never full-field red pulses mistaken for **higher severity**.

---

### 3) Scenario guidance (defaults + exceptions)
Different densities & goals—**same visual mother tongue:** warm dark base, warm-light primaries, restrained elevation, consistent risk semantics.

#### 3.1 Main monitoring (five principles)
1. **Highest risk first:** above-the-fold must surface worst-case alert (level, blast radius, response entry).
   - **Default:** right pane top pinned **“top-risk card + response CTA + impact summary.”**
2. **Scannable layers:** glance order **conclusion → evidence → action.**
   - **Default card order:** Header (conclusion) → Summary (1–3 lines) → Evidence (collapsed) → Actions (primary/secondary).
   - **Exception:** scope/environment must precede action—move controls near header **but** keep footer primary zone.
3. **Separate risk vs interaction hues:** reds/ambers/greens/blues = risk/state (softened); interaction emphasis stays **warm-light**.
4. **Evidence collapsed by default:** logs/stacks/commands start folded.
   - **Default:** title + 1–3 preview lines; expanded = copy + horizontal scroll when needed.
5. **Traceability:** timestamps, provenance, copyable raw excerpts.

#### 3.2 Landing (three principles)
1. **Tool, not poster:** credible utility—warm dark restraint; proof via **input → output**, not spectacle.
2. **One warm-light hero CTA**
   - **Guardrail:** default **one** warm-light primary above fold.
   - **Exception:** dual mandatory primaries allowed—everything else demoted hard.
3. **Real cross-section:** left **sample input** → right **output cards** using shared card vocabulary.

#### 3.3 Settings / configuration (minimum viable spec)
Goals: **readable forms** + **recoverable errors**.

**Guardrail**
- Above-fold warm-light primaries default **one** (Save / Apply); demote the rest.

**Defaults**
- Labels tight to fields; inline errors with **focus ring + explanation + fix path**.
- Prefer borders over big saturated panels.

---

### 4) Color system (tokens are canonical + mapping)
> §4.1 is the single token source—don’t duplicate full palettes elsewhere.

#### 4.1 Full token set (`:root`)

```css
:root {
  /* ========== Color: Surfaces (Lovable Dark warm layers) ========== */
  --bg-0: #1a1916;          /* Page canvas: warm dark */
  --bg-1: #201e1b;          /* Cards/sections: slight lift */
  --bg-2: #282623;          /* Inputs/panels: another lift */
  --surface-1: rgba(232,229,222,0.04); /* Subtle lift layer */
  --surface-2: rgba(232,229,222,0.06); /* Hover/selected lift */

  /* ========== Color: Text ========== */
  --text-1: #e8e5de;        /* Primary body: warm light */
  --text-2: rgba(232,229,222,0.83); /* Secondary */
  --text-3: #9a9a98;        /* Meta: warm gray */
  --text-muted: rgba(232,229,222,0.35); /* Placeholder/support */

  /* ========== Color: Brand / Accent ========== */
  --accent-primary: #e8e5de; /* Warm-light primary CTA fill */
  --text-on-primary: #1a1916; /* Text on primary CTA */
  --accent-interactive: #e8e5de; /* Interactive accent + underline */
  --focus-blue: #3b82f6;    /* Focus ring hue */

  /* ========== Color: Borders & Dividers ========== */
  --border-1: #2e2c28;      /* Primary dividers */
  --border-2: #2e2c28;      /* Secondary dividers */
  --border-strong: rgba(232,229,222,0.35); /* Stronger interactive border */

  /* ========== Semantic: Alert levels (soft—for text/stroke/badge tint) ========== */
  --sev-critical: #c43e3e;
  --sev-high:     #d05858;
  --sev-medium:   #c4882c;
  --sev-low:      #3d8f5a;
  --sev-info:     #4a80b8;

  --sev-bg-alpha: 0.08; /* Badge tint default alpha (+0.04 on hover OK) */

  /* ========== Typography ========== */
  --font-ui: 'DM Sans', ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Arial, "Noto Sans", "PingFang SC", "Microsoft YaHei", sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;

  --fs-12: 12px;
  --fs-13: 13px;
  --fs-14: 14px;
  --fs-16: 16px;
  --fs-18: 18px;

  --lh-tight: 1.25;
  --lh-base: 1.50;
  --lh-relaxed: 1.65;

  /* ========== Spacing (8px rhythm) ========== */
  --sp-2: 2px;
  --sp-4: 4px;
  --sp-6: 6px;
  --sp-8: 8px;
  --sp-12: 12px;
  --sp-16: 16px;
  --sp-20: 20px;
  --sp-24: 24px;
  --sp-32: 32px;

  /* ========== Radius ========== */
  --r-6: 6px;
  --r-8: 8px;
  --r-12: 12px;
  --r-pill: 9999px;

  /* ========== Shadow ========== */
  --shadow-card: none;
  --shadow-hover: rgba(0,0,0,0.3) 0px 4px 12px;
  --shadow-inset: rgba(255,255,255,0.1) 0px 0.5px 0px 0px inset, rgba(0,0,0,0.4) 0px 0px 0px 0.5px inset, rgba(0,0,0,0.2) 0px 1px 2px 0px;

  /* ========== Focus Ring ========== */
  --ring-focus: 0 0 0 2px rgba(59,130,246,0.50);
  --ring-danger: 0 0 0 2px rgba(196,62,62,0.30);
}
```

#### 4.2 Token usage map
| Area | Default bg | Default border | Hover / selected | Notes |
|------|------------|----------------|------------------|-------|
| Page canvas | `--bg-0` | — | — | Warm dark base |
| Section shells | `--bg-1` | `--border-1` | `--surface-1/2` | Depth via borders |
| Inputs/panels | `--bg-2` | `--border-2` | focus `--ring-focus` | |
| Output cards | `--bg-1` | `--border-1` | `--border-strong` stronger | No fake depth shadows |
| Primary CTA | `--accent-primary` | — | `opacity: 0.85` | Warm-light + inset |
| Links / secondary interaction | — | — | `--accent-interactive` + underline | No saturated filler |

#### 4.3 Brand accents & light theme (optional addendum)

- **Beyond dark:** light themes need **full token redesign** for `--bg-*` / `--text-*`—no naive inversion that nukes contrast.
- **Third-party widgets:** desaturated cyan/blue-gray “info link” styling OK locally—must **not** compete with §**2.2** warm primary CTAs or §**Step 3** blue focus (same spirit as §**3.1** separation).

---

### 5) Typography

#### 5.1 Families
- **UI/body:** `--font-ui` (DM Sans + system stack incl. CJK fallbacks)
- **Code/logs/commands:** `--font-mono`

#### 5.2 Type scale (baseline steps)
- `--fs-12`: meta, timestamps, helper copy
- `--fs-13`: field labels, secondary UI
- `--fs-14`: default body + buttons
- `--fs-16`: emphasized body / mid card titles, `letter-spacing: -0.3px`
- `--fs-18`: intro paragraphs / landing emphasis—use sparingly, `letter-spacing: -0.3px`

#### 5.3 Typesetting discipline (Lovable-inspired)
- **Two weights only:** 400 (body/UI/link/button) and 600 (titles/emphasis)—**no 700**.
- **Negative tracking:** ≥16px sizes use `-0.3px` … `-0.5px`.
- **≤14px body:** normal tracking—no extra letterspacing hacks.

#### 5.4 Alternate stack — IBM Plex (SecManus repo option / current direction)

When adopting **IBM Plex** for institutional tooling cohesion:

- **UI/body:** **IBM Plex Sans** (400/500; if strictly honoring §**5.3**, cap at 400 + **600**, avoid 700).
- **Code/IOC/hash/logs:** **IBM Plex Mono**.
- **Tables:** enable `tabular-nums` (`font-variant-numeric: tabular-nums lining-nums`).
- **Delivery:** Google Fonts CDN (`src/index.css`); self-host woff2 if compliance demands.

> **Relation to §5.1:** DM Sans + CJK in `--font-ui` remains the **documented default sample**; swap literals to Plex families when adopted—**§5.2–5.3 rules unchanged**.

#### 5.5 Tailwind / rem ladder (shadcn alignment)

Base **16px = 1rem**. Cross-check with §**5.2**:

| Token | rem | px | Usage |
|-------|-----|-----|-------|
| text-xs | 0.75 | 12 | Helper labels, table minors |
| text-sm | 0.875 | 14 | Secondary body, field hints |
| text-base | 1 | 16 | Default body |
| text-lg | 1.125 | 18 | Section titles |
| text-xl | 1.25 | 20 | Card titles |
| text-2xl | 1.5 | 24 | Panel titles |
| text-3xl | 1.875 | 30 | Page hero titles—rare |

**Line-height:** body ~**1.5–1.625**; dense lists/tables **1.25–1.375**.

---

### 6) Spacing & layout

#### 6.1 8px rhythm
- Primary rhythm on **8px**: `--sp-8/12/16/20/24/32` for padding/gaps.
- `--sp-2/4/6` for hairline alignment / icon nudging / tight stacks.
- **Coexistence with Tailwind:** default **4px** substeps (e.g. `p-1.5`) supplement §**6.1**—they **don’t replace** the **8px backbone**.

#### 6.2 Two-pane conversational shell (default)
Classic **left ask / right evidence** for SOC workflows.

**Sizing**
- Max page width **1440–1600**
- Left rail **fixed 400px** (tweak **360–420px** OK)
- Right pane fluid, min ~**720px**
- Top chrome **60px** (56–64 acceptable)

**Scrolling**
- Right pane scrolls independently.
- Composer/input anchored bottom-left—always reachable.

**Exception**
- If left history must stay visible, left pane may scroll—but input stays reachable.

#### 6.3 Responsive breakpoints (minimum bar)
- **≥1280px:** two-pane (400px left + fluid right).
- **960–1279px:** two-pane with collapsible left drawer.
- **<960px:** single column or drawer composer.

**Cross-breakpoint guardrail**
- Severity + primary actions stay visible—never bury behind hidden-only routes.

#### 6.4 Shell grid & reading measure

- **Shell:** **grid-disciplined** side/top chrome—no arbitrary magic margins.
- **Reports/longform:** **hybrid** ok—body column **`max-width` ~720–840px** to limit line length fatigue.
- **Radius ladder:** panels `--r-12` (§**7.4**); micro `--r-6`/`--r-8`; avoid uniform mega-radius + shadow spam (§**9.6**).

---

### 7) Core components

#### 7.1 Severity badges (five states)
Tinted chips + softened hues—visible yet calm inside warm dark chrome.

**Guardrail**
- Semantic colors = **text / stroke / icon dot / badge tint**—never whole-panel fills.

**Default sizing**
- Height **24px**
- Type `--fs-12`, weight **500**
- Padding **4px 10px**
- Radius `--r-6`

**Copy-paste CSS**

```css
.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 24px;
  padding: 4px 10px;
  border-radius: var(--r-6);
  font-size: var(--fs-12);
  font-weight: 500;
  border: 1px solid transparent;
}

.badge--critical {
  color: var(--sev-critical);
  background: rgba(196, 62, 62, var(--sev-bg-alpha));
  border-color: rgba(196, 62, 62, 0.25);
}
.badge--high {
  color: var(--sev-high);
  background: rgba(208, 88, 88, var(--sev-bg-alpha));
  border-color: rgba(208, 88, 88, 0.25);
}
.badge--medium {
  color: var(--sev-medium);
  background: rgba(196, 136, 44, var(--sev-bg-alpha));
  border-color: rgba(196, 136, 44, 0.25);
}
.badge--low {
  color: var(--sev-low);
  background: rgba(61, 143, 90, var(--sev-bg-alpha));
  border-color: rgba(61, 143, 90, 0.25);
}
.badge--info {
  color: var(--sev-info);
  background: rgba(74, 128, 184, var(--sev-bg-alpha));
  border-color: rgba(74, 128, 184, 0.25);
}

.badge[role="button"]:hover {
  filter: brightness(1.05);
}
```

#### 7.2 Inputs (incl. multiline + focus)
Minimal chrome + **blue** focus—for left-rail prompts, log paste, queries.

**Defaults**
- Focus: blue border + `--ring-focus`
- Error: red border + `--ring-danger`
- **Conflict:** if error **and** focus—**error wins visually**.

#### 7.3 Buttons
**Primary (warm-light + inset shadow)**
- Fill `--accent-primary` (`#e8e5de`)
- Text `--text-on-primary` (`#1a1916`)
- Shadow `--shadow-inset`
- Hover/active `opacity: 0.85` / `0.8`

**Secondary (outline/ghost-adjacent)**
- Transparent bg
- Border `rgba(232,229,222,0.35)`
- Hover `rgba(232,229,222,0.06)` fill

**Ghost link-style**
- Transparent bg
- Text `--text-1` + underline
- Hover `opacity: 0.8`

**Icon buttons**
- **32×32**, transparent by default; hover lifts surface/border.

#### 7.4 Output cards
Warm panels separated by warm-gray strokes—friendly to logs/code.

**Structure**
- Header / Body (summary + collapsible evidence) / Footer (primary/secondary)

**Look**
- Background `--bg-1`
- Border `--border-1` (`#2e2c28`)
- Radius `--r-12`
- No decorative shadows—borders carry depth

**Density guardrails**
- ≤**3** chips visible—overflow `+N`.
- Title single-line ellipsis.

#### 7.5 Reasoning timelines & tables (shadcn/Tailwind notes)

**Timelines**
- Default **left rail + clear node states**; “running” pulses stay **subtle**—never confuse with `--sev-critical/high`.
- Decoration follows §**3.1** separation—interaction emphasis stays warm/neutral.

**Tables**
- Text left; numerics right + `tabular-nums`.
- Zebra optional—**ultra-low contrast neutrals only**—no full-row semantic washes (§**1** definition).
- Overflow: `truncate` + tooltip/drawer; titles obey §**7.4** ellipsis rules.

---

### 8) Lovable Dark checklist (hard boundaries)
- Surfaces stair-step `--bg-0 → --bg-1 → --bg-2`—not pure black/cold gray decks.
- Copy warm-light `#e8e5de`; neutrals derive from its alpha ramps.
- Semantic hues softened—small areas only.
- Focus isolated to **blue** rings vs alert reds.
- Logs/code: monospace, taller leading, dedicated warm-dark well `#151412`; copy + collapse + horizontal scroll.
- Warm-light primaries ≤ **2** above fold (landing ≤1; settings ≤1).
- Never `#000000` page canvas—use `#1a1916`.
- Never `#ffffff` body text—use `#e8e5de`.

---

### 9) Do’s & Don’ts

#### 9.1 Color
- ❌ Full-container / full-row / gradient semantic washes in reds/oranges/greens/blues.
  ✅ Soft semantics on **text/stroke/icon/badge tint** only—canvas stays warm-neutral tiers.

#### 9.2 Badges
- ❌ Glow loops / heavy shadows on chips.
  ✅ Hover = slight `brightness(1.05)` / border emphasis—no lighthouse beams.

#### 9.3 Buttons
- ❌ Multiple competing warm-light primaries crowding the fold.
  ✅ Default ≤ **2** (landing ≤1; settings ≤1).

#### 9.4 Hierarchy
- ❌ Bury top severity below the fold or inside collapsed-only regions without summary.
  ✅ Above-fold clarity on **level / impact / response**.

#### 9.5 Canvas & copy
- ❌ `#000` backgrounds or `#fff` body copy.
  ✅ `#1a1916` surfaces + `#e8e5de` text.
- ❌ Hyper-saturated brand/neon accents across chrome.
  ✅ Warm-neutral discipline—ramps from warm-light alphas.

#### 9.6 “Template face / AI slop” (tool surfaces)

- ❌ **Purple/violet gradients** driving primary buttons / hero fills.
- ❌ Three-column **feature grids with rainbow icon donuts** in core workspaces (landing marketing slices §**3.2** only—with restraint).
- ❌ **Fully centered** dashboard compositions for dense tooling.
- ❌ **Uniform ultra-round corners + shadow spam** card walls.
- ❌ Collapsing **semantic success/warning hues** into **primary CTA identity** (primaries stay §**2.2** warm-light + §**7.3** spec).

---

### 10) Acceptance checklist
- Warm-light primary count ≤ **2** above fold (landing ≤1; settings ≤1).
- Semantic colors limited to **text/stroke/icon/badge tint**.
- Focus rings **blue** everywhere intentional.
- Evidence blocks **collapsed by default**, **copyable**, **horizontal scroll**, no forced wrap havoc.
- Overflow rules for tags/titles (collapse/ellipsis).
- Canvas warm `#1a1916` (not pure black/cold gray default).
- Copy warm `#e8e5de` (not pure white).
- Accent stack stays warm-neutral.
- Motion matches §**2.5** (functional—no misleading red pulse storms).
- Avoid §**9.6** tropes (purple gradient primaries, workspace icon billboards).
- Tables/timelines obey §**7.5** (no semantic row washes; timeline ≠ alert red confusion).

---

### 11) Decisions log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-05-06 | Draft root `DESIGN.md` (teal / Plex experiment) | Early visual exploration vs templates |
| 2026-05-06 | **v1.2** merged standalone draft sections into canonical standard | Single SoT—guardrails remain warm primary + blue focus + small semantic fills |
| 2026-05-06 | **Removed** `docs/design/design-standards-v1-1.md`; full text lives at root `DESIGN.md` | One file to edit |
| (TBD) | (TBD) | (TBD) |

**Next:** When engineering fully converges to §**4.1** tokens, append a row here and close drift items listed in §**1.2**.
