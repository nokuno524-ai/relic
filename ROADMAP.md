# Relic Roadmap: v0.1 → Publication Quality

## v0.1 ✅ (Current)
- Lexer, parser, AST, DAG resolver
- TikZ backend with relative positioning
- Container grouping (fit + backgrounds)
- Flow arrows (auto-generated)
- Academic theme with styles
- 50/50 tests passing

## v0.2 🔄 (In Progress)
### P0: Math Labels
- Full LaTeX math in labels: `$\mathbf{W}_Q$`, `$\sum_{i=1}^N$`
- Auto-detect math delimiters in label strings
- Pass through to TikZ as-is (TikZ handles LaTeX natively)

### P1: Image Embedding
- `image` primitive: `InputImg [image, src: "cat.png", width: 30mm]`
- TikZ: `\node[inner sep=0pt] (name) {\includegraphics[width=30mm]{cat.png}};`

### P2: ML Component Library
- `add` — circle with ⊕ symbol
- `multiply` — circle with ⊗ symbol
- `concat` — vertical bar node
- `softmax` — rounded box with special styling
- `loss` — diamond shape with function label

### P3: Bezier Arrows
- `arrow A -> B [bezier]` — smooth S-curve
- `arrow A -> B [orthogonal]` — right-angle routing
- Arrow label positioning: `label-pos: 0.5` (midpoint), `0.3` (near source)

### P4: Opacity / Ghosting
- `opacity: 0.2` on any object or container
- `ghost: true` shorthand for 20% opacity
- TikZ: `opacity=0.2, fill opacity=0.2`

### P5: Comment Support
- `//` line comments in .relic source
- `/* ... */` block comments

### P6: Professional Color Palettes
- `nord` theme (muted blues, grays)
- `viridis` theme (scientific)
- `pastel` theme (soft)
- Rule of Three: primary/neutral/highlight colors

## v0.3 (Future)
- Data viz primitives (plots, heatmaps)
- Tensor visualization (3D blocks)
- Zoom-in callouts
- Clipping masks
- Grid container layout
- SVG backend

## v0.4 (Future)
- Live preview (VS Code extension)
- Template library (common architectures)
- TikZ → Relic round-trip parser
