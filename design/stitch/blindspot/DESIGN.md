---
name: Blindspot
colors:
  surface: '#fcf8fb'
  surface-dim: '#dcd9dc'
  surface-bright: '#fcf8fb'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f6f2f5'
  surface-container: '#f0edf0'
  surface-container-high: '#eae7ea'
  surface-container-highest: '#e5e1e4'
  on-surface: '#1c1b1d'
  on-surface-variant: '#3f4850'
  inverse-surface: '#313032'
  inverse-on-surface: '#f3f0f2'
  outline: '#707881'
  outline-variant: '#bfc7d2'
  surface-tint: '#006398'
  primary: '#006194'
  on-primary: '#ffffff'
  primary-container: '#007bb9'
  on-primary-container: '#fdfcff'
  inverse-primary: '#93ccff'
  secondary: '#006e2d'
  on-secondary: '#ffffff'
  secondary-container: '#7cf994'
  on-secondary-container: '#007230'
  tertiary: '#894d00'
  on-tertiary: '#ffffff'
  tertiary-container: '#ac6200'
  on-tertiary-container: '#fffbff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#cce5ff'
  primary-fixed-dim: '#93ccff'
  on-primary-fixed: '#001d31'
  on-primary-fixed-variant: '#004b73'
  secondary-fixed: '#7ffc97'
  secondary-fixed-dim: '#62df7d'
  on-secondary-fixed: '#002109'
  on-secondary-fixed-variant: '#005320'
  tertiary-fixed: '#ffdcc0'
  tertiary-fixed-dim: '#ffb875'
  on-tertiary-fixed: '#2d1600'
  on-tertiary-fixed-variant: '#6b3b00'
  background: '#fcf8fb'
  on-background: '#1c1b1d'
  surface-variant: '#e5e1e4'
typography:
  display:
    fontFamily: Inter
    fontSize: 2.25rem
    fontWeight: '600'
    lineHeight: 2.75rem
    letterSpacing: -0.03em
  headline-lg:
    fontFamily: Inter
    fontSize: 1.75rem
    fontWeight: '600'
    lineHeight: 2.25rem
    letterSpacing: -0.025em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 1.375rem
    fontWeight: '600'
    lineHeight: 1.75rem
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 1.25rem
    fontWeight: '600'
    lineHeight: 1.625rem
    letterSpacing: -0.02em
  headline-sm:
    fontFamily: Inter
    fontSize: 1rem
    fontWeight: '600'
    lineHeight: 1.375rem
    letterSpacing: -0.015em
  body-lg:
    fontFamily: Inter
    fontSize: 1rem
    fontWeight: '400'
    lineHeight: 1.5rem
    letterSpacing: -0.011em
  body-md:
    fontFamily: Inter
    fontSize: 0.875rem
    fontWeight: '400'
    lineHeight: 1.375rem
    letterSpacing: -0.006em
  body-sm:
    fontFamily: Inter
    fontSize: 0.75rem
    fontWeight: '400'
    lineHeight: 1.125rem
    letterSpacing: 0em
  label-md:
    fontFamily: Inter
    fontSize: 0.8125rem
    fontWeight: '500'
    lineHeight: 1rem
    letterSpacing: -0.005em
  label-sm:
    fontFamily: Inter
    fontSize: 0.6875rem
    fontWeight: '600'
    lineHeight: 0.875rem
    letterSpacing: 0.02em
  data-mono:
    fontFamily: Inter
    fontSize: 0.8125rem
    fontWeight: '500'
    lineHeight: 1.125rem
    letterSpacing: -0.01em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-md: 1.5rem
  margin: 1rem
  margin-md: 2rem
  margin-lg: 3rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
---

## Brand & Style

This design system delivers an ultra-clean, high-density financial intelligence interface engineered for strategic capital clarity. Tailored for quantitative analysts, portfolio architects, and institutional founders, it translates deep financial modeling into immediate, low-latency visual insights.

Drawing inspiration from the refined utility of Linear and Attio, the aesthetic balances austere obsidian typography against vast, surgical white space. The overall tone is calm, razor-sharp, and dependable. Distracting ornamentation is stripped away in favor of exact alignment, hairline borders, and targeted powder blue and mint sage accents that illuminate critical metrics without visual fatigue.

## Colors

The palette employs a restrained, structural light mode that leverages extreme contrast and micro-accentuation.

- **Foundational Neutrals**: Canvases rely on clinical stark whites (`#ffffff`, `#f8fafc`) grounded by deep obsidian tones (`#09090b`, `#18181b`) for high-fidelity typography, structure, and active tool surfaces. Subtle slate dividers (`#e2e8f0`, `#f1f5f9`) establish hairline boundaries.
- **Primary Data & Focus (`#0284c7`)**: Powder sky blue drives the primary interactive layer, primary CTA states, active filters, and systemic pipeline flows. Soft sky washes (`#e0f2fe`, `#bae6fd`) serve as low-impact container backgrounds.
- **Affirmative & Insight (`#16a34a`)**: Mint sage acts as the intelligence accent, illuminating positive spreads, detected anomalies, alpha yield signals, and resolved blindspots. Soft mint containers (`#dcfce7`) host affirmative status metrics.
- **Hierarchy of Color**: Accents are strictly functional. Visual weight is maintained through crisp monochrome balance, ensuring that pastel accents immediately draw attention to changing market dynamics.

## Typography

The typographic hierarchy utilizes Inter across all weights, calibrated for analytical density and numerical legibility.

- **Numerical Precision**: Tabular lining figures (`font-variant-numeric: tabular-nums`) must be enforced for all tables, metric callouts, and chart tooltips to prevent jitter during live data streaming.
- **Tracking & Proportion**: Tight, negative letter tracking on titles generates an authoritative, compact editorial feel characteristic of premium productivity software. Smaller data tags and micro-labels adopt neutral or slight positive tracking to preserve glanceability.
- **Rhythm**: Spacing scales strictly with line height, avoiding orphan text in dense analytical dashboards.

## Layout & Spacing

This design system uses a strict 12-column grid anchored by an 8pt base spatial unit, optimized for data-dense dashboards and situational split views.

- **Grid & Boundaries**:
  - **Desktop (1280px+)**: 12 columns, 24px gutters, fixed-width side navigation with dynamic dashboard canvas padding (32px–48px).
  - **Tablet (768px–1279px)**: 8 columns, 16px gutters, collapsible utility rails.
  - **Mobile (<768px)**: 4 columns, 16px margins, single-column vertical flow with horizontally scrollable metric strips.
- **Density Philosophy**: Components favor compact padding (`space-xs` to `space-md`) internally to allow comparative financial analysis without scrolling, relying on sharp divider lines rather than empty space to delineate structural hierarchy.

## Elevation & Depth

Visual hierarchy is communicated through structural layering, precision hairline strokes, and minimal ambient lighting.

- **Hairline Borders**: Structural separation relies on `1px solid #e2e8f0` (default) and `#09090b` (active or selected containers) rather than drop shadows.
- **Layer 0 (Canvas)**: Background base `#ffffff` or muted control areas `#f8fafc`.
- **Layer 1 (Cards & Data Panels)**: Solid white `#ffffff` surfaced with a `1px` border in `#e2e8f0` and an ultra-subtle ambient shadow: `0 1px 2px 0 rgba(9, 9, 11, 0.04)`.
- **Layer 2 (Overlays & Modals)**: Pure `#ffffff` surface with `0 12px 32px -4px rgba(9, 9, 11, 0.08), 0 0 0 1px rgba(9, 9, 11, 0.06)`.
- **Layer 3 (Tooltips & Popovers)**: Solid obsidian `#09090b` with crisp contrast text and zero blur bleed, achieving immediate focus over busy data grids.

## Shapes

The geometric framework is tuned to 8px base corner radiuses (Level 2), projecting institutional precision without the harshness of pure square geometry.

- **Micro Controls (Inputs, Buttons, Badges)**: Bound to `0.5rem` (8px). This consistent radius maintains uniform alignment across inline toolbars.
- **Panels & Cards**: Bound to `0.5rem` (8px) for internal widgets; complex outer wrappers can extend to `0.75rem` (12px) to enclose nested cards smoothly.
- **Data Markers & Pills**: Full roundedness is restricted exclusively to status indicators, numerical counter tags, and circular user avatars.

## Components

### Buttons
- **Primary**: Solid obsidian background (`#09090b`), pure white typography, 8px border radius, 36px height for standard controls. Hover state transitions to `#27272a`.
- **Secondary**: Pure white background, `1px solid #e2e8f0`, deep obsidian text (`#09090b`). Hover shifts to `#f8fafc` with border `#cbd5e1`.
- **Accent (Insight / Intelligence)**: Powder blue tint (`#e0f2fe`) with deep blue text (`#0369a1`), used exclusively for primary intelligence triggers.

### Badges & Chips
- **Neutral**: Background `#f4f4f5`, text `#52525b`, border `#e4e4e7`.
- **Sky Active (Data Flow)**: Background `#e0f2fe`, text `#0284c7`, border `#bae6fd`.
- **Mint Insight (Blindspot Solved)**: Background `#dcfce7`, text `#15803d`, border `#bbf7d0`.
- Badges use 4px vertical by 8px horizontal padding, with uppercase `label-sm` tracking.

### Form Inputs & Selectors
- Background `#ffffff`, border `1px solid #e2e8f0`, radius 8px, height 36px.
- Focus state removes typical browser rings, using an inner stroke `1px solid #09090b` accompanied by a subtle `#0284c7` glow ring (`0 0 0 2px rgba(2, 132, 199, 0.15)`).
- Placeholder text in `#a1a1aa`, input value in `#09090b`.

### Checkboxes & Radios
- Crisp 16px squares with 4px border radius. Border `1px solid #cbd5e1`.
- Checked state: Obsidian fill (`#09090b`) with a white stroke check icon for standard controls, or powder blue (`#0284c7`) in data-filtering contexts.

### Cards & Financial Intelligence Panels
- White canvas (`#ffffff`), `1px solid #e2e8f0`, 8px radius.
- Headers feature an internal 44px border-bottom divider separating panel controls from tabular data.
- Insights cards integrate a 2px left border accent in mint sage (`#16a34a`) or powder blue (`#0284c7`) to signify system-generated intelligence findings.

### Data Tables & Venn Pipelines
- Compact row height (36px to 40px), border-bottom `1px solid #f1f5f9`.
- Dynamic hover rows transition to `#f8fafc`.
- Venn intersections and pipeline diagrams utilize semi-transparent sky blue (`rgba(56, 189, 248, 0.15)`) and mint sage (`rgba(74, 222, 128, 0.15)`) fills bounded by 1.5px solid strokes.