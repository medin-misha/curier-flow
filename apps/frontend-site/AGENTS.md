# MFS Landing

Next.js 15 frontend for May Fleet Solutions. The application has two routes:

- `/` - a scene-based landing page.
- `/apply` - a four-step courier application wizard.

The interface and user-facing validation messages are in Russian.

## Stack And Commands

- Next.js App Router, React 19, TypeScript in strict mode.
- CSS Modules and CSS custom properties.
- Vitest, Testing Library, and jsdom.
- `npm run dev` - local development server.
- `npm run typecheck` - TypeScript validation.
- `npm test` - complete test suite.
- `npm test -- <path>` - focused test run.
- `npm run build` - production build.
- There is no ESLint command in this project.

## Architecture

- `src/app/` contains route entry points, metadata, global styles, and design tokens.
- `src/features/landing/` owns the landing composition, scroll engine, scene UI, and landing-only components.
- `src/features/application/` owns wizard state, validation, submission boundary, and form UI.
- `src/components/` contains UI primitives shared across features.
- `src/content/` contains static typed content and company data.
- Tests are colocated with the code they verify.

Keep route files thin. Business rules and derived values belong in pure functions inside the relevant feature, not in page components.

## Landing Invariants

- `src/content/scenes.ts` is the source of scene order. Navigation targets, scene numbers, active labels, dots, and scroll height must stay derived from the scene array.
- Adding a bike must remain a data-only operation: add media under `public/bikes/<slug>/` and an object to `src/content/bikes.ts`. See `docs/adding-a-bike.md`.
- `useActiveScene` is the single source of the active scene index. Do not introduce a second competing scroll state.
- Preserve the discriminated scene union and the two-item bike specs tuple unless the layout is intentionally redesigned.
- Do not store viewport width in React state. Use the existing CSS breakpoint for responsive behavior.
- Raw `<img>` and `<video>` elements are intentional because the media is pixel art. Do not replace them with `next/image` without validating rendering fidelity.
- Hidden scene content must not remain interactive or exposed incorrectly to assistive technology. Preserve `inert`, reduced-motion behavior, and keyboard access.

## Application Invariants

- Keep validation and display hints consistent, especially age limits, phone normalization, and file requirements.
- Keep validation logic in pure functions and preserve the injectable clock used by age tests.
- `submitApplication.ts` is currently a typed fake transport. Do not describe it as production-ready or treat client-side file checks as a security boundary.
- Changes involving passport or visa uploads require an explicit server-side validation, storage, retention, and privacy design.

## Styling

- Reuse values from `src/app/tokens.css`; do not duplicate colors, stacking levels, bevels, or shared effects in component code.
- Keep component styles colocated in `*.module.css`.
- Express React-driven visual state through `data-*` attributes when practical. Avoid constructing CSS strings in JavaScript.
- Preserve the established pixel-art visual language. Do not introduce generic UI-library styling.

## Workflow

1. Inspect the affected feature and its tests before editing.
2. Read `docs/known-gaps.md` before changing behavior that may be an intentional tradeoff.
3. Make the smallest change that preserves the boundaries above.
4. Run focused tests while iterating.
5. Run `npm run typecheck`, `npm test`, and `npm run build` before considering work complete.
6. For visible UI changes, start `npm run dev` and use the Playwright MCP tools to inspect `/` and `/apply` at desktop and mobile sizes. Check scroll transitions, stacking, form interaction, keyboard behavior, and browser console errors.

Do not update snapshots or weaken assertions merely to make tests pass. Do not perform unrelated refactoring while implementing a focused request.
