# SiLing app icon

Generated with the built-in imagegen tool. The final master is
`orchestrator-1024.png`; macOS packaging uses it for the complete ICNS size set.
Compile and run `scripts/build-app-icons.m` using the commands at its top from
the repository root on macOS to derive the web sizes. Standard icons preserve alpha; Apple Touch and maskable
icons composite onto an opaque graphite background. The older SVG remains for
cached clients; current UI and install metadata use the new PNG assets.

Final generation prompt:

> Use case: logo-brand. Asset type: production macOS app icon and PWA icon for SiLing, an AI agent orchestrator with terminal panes. Primary request: redesign the icon into a refined, distinctive professional app symbol. Subject: a bold luminous terminal command chevron and cursor integrated with a simple three-node orchestration motif, composed as one coherent compact mark. Style: polished restrained macOS icon, dark graphite rounded-square tile, electric blue and cool cyan accents consistent with the existing blue terminal identity; subtle dimensional bevel and soft internal illumination, precise clean edges, generous negative space, excellent silhouette and legibility at 32 pixels. Composition: one centered front-facing icon, square 1024x1024 canvas, tile occupies about 88 percent of canvas with modest transparent margin; all meaningful glyph details comfortably inside central 65 percent so the design also works with maskable icons. Background outside the tile must be truly transparent alpha, no white fringe. No letters, words, watermark, mockup, surrounding UI, perspective tilt, extra decorative circuits, or tiny detail. Deliver a single finished icon, not a concept sheet.
