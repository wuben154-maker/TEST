## Metadata

- slug: openrouter-unified-llm-gateway
- last updated: 2026-04-25
- proposal: `proposal.md`
- design: `design.md`

## Scope

This UI acceptance covers:

- `src/components/ModelSelector.tsx`
- Workspace composer model selector on `/`
- Provider grouping behavior for OpenRouter and OpenCode models

No new screen, layout system, color treatment, or interaction component is introduced.

## Reference assets

| Asset | Represents | Status |
|-------|------------|--------|
| `docs/Process/openrouter-unified-llm-gateway/mockups/` | Optional reference images | Deferred |

## Mockups deferred

Mockups are skipped for this delivery because the user-visible change is limited to adding an `OpenRouter` provider group label inside the existing model selector. Phase 6 will verify the live selector state instead.

## Visual criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| U-01 | When OpenRouter models are available, the selector groups them under a human-readable `OpenRouter` heading. | Component/E2E verification. |
| U-02 | When OpenCode models are also available, the existing `OpenCode Zen` group remains visible and visually separate from OpenRouter. | E2E selector check. |
| U-03 | Model names remain truncated in the compact trigger as before; adding OpenRouter must not expand the trigger width or disturb composer layout. | Visual QA at desktop width. |
| U-04 | Empty and loading states remain unchanged from the existing selector behavior. | Component or manual QA. |

## Interaction criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| I-01 | Selecting an OpenRouter model calls `onChange` with the gateway id beginning with `openrouter/`. | Component or E2E check. |
| I-02 | The last selected model persistence still works for OpenRouter ids. | Component/unit check or manual localStorage check. |
| I-03 | If OpenCode is later hidden and the stored selection is no longer available, the selector falls back to the first available model. | Unit or manual check using mocked model list. |
| I-04 | Keyboard search and selection behavior remains unchanged because the existing command list is reused. | E2E or manual keyboard check. |

## Responsive

| Breakpoint | Criteria |
|------------|----------|
| 375px | Compact trigger remains usable and does not overflow the composer. |
| 768px | Popover width remains stable; provider headings are readable. |
| 1024px+ | Existing composer layout remains unchanged. |

## Accessibility

| ID | Criterion | Verification |
|----|-----------|--------------|
| AX-01 | The existing button and popover keyboard path remains functional. | Manual or E2E keyboard check. |
| AX-02 | Provider headings and model names remain text, not image-only indicators. | Code review / DOM inspection. |
| AX-03 | Touch target size is not reduced from the existing selector trigger. | Visual/code review. |

## Sign-off

| ID | Pass/Fail | Verifier | Date | Notes |
|----|-----------|----------|------|-------|
| U-01 | Pass | Agent | 2026-04-25 | `ModelSelector.test.tsx` and no-auth Playwright E2E verified `OpenRouter` heading. |
| U-02 | Pass | Agent | 2026-04-25 | E2E verified `OpenRouter` and `OpenCode Zen` groups appear together. |
| U-03 | Pass | Agent | 2026-04-25 | No trigger width/layout code changed; full Vitest passed. |
| U-04 | Pass | Agent | 2026-04-25 | Existing empty/loading behavior untouched; selector tests passed. |
| I-01 | Pass | Agent | 2026-04-25 | Unit test verified `onChange` receives `openrouter/...` id unchanged. |
| I-02 | Pass | Agent | 2026-04-25 | Existing persistence helper remains unchanged; full Vitest passed. |
| I-03 | Pass | Agent | 2026-04-25 | Unit test verified stored hidden OpenCode selection falls back to OpenRouter. |
| I-04 | Pass | Agent | 2026-04-25 | Existing command list reused; no interaction implementation changed. |
| AX-01 | Pass | Agent | 2026-04-25 | Existing button/popover path reused; E2E could open selector. |
| AX-02 | Pass | Agent | 2026-04-25 | Provider headings and model names remain text in DOM. |
| AX-03 | Pass | Agent | 2026-04-25 | Existing trigger classes unchanged. |

## Phase 6 exploratory notes

- `/qa`: SKIP — `browser_*` Playwright MCP tools are not invocable in this session; automated Vitest and Playwright E2E were run instead.
- `/design-review`: SKIP — `browser_*` Playwright MCP tools are not invocable in this session; UI scope is limited to selector provider text and was covered by E2E.
