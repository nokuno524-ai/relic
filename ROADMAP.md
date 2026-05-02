# Gemini 3.1 Pro Expert Review — Relic Roadmap

## Rating: 7/10 → Target 10/10

## Key Insights

### What Separates 7/10 from 10/10
1. **Macro-to-Micro Hierarchies (Zoom Callouts)** — show whole system, then zoom into a block
2. **Tensor Dimensionality Cues** — 3D blocks, stacked planes for multi-dimensional data
3. **Data Flow vs Architecture** — distinguish operations (boxes) from data (tensors/lines)
4. **Trunk/Bus Routing** — merge multiple streams into single bus line

## Priority Features (from Gemini 3.1 Pro)

### P1: Advanced ML Primitives (Tensors & Stacks)
```relic
InputEmbed [tensor3d, width: 20mm, height: 8mm, depth: 5mm, label: "$X$", fill: blue!20]
  annotate top: "$N$"
  annotate right: "$d_{model}$"

container EncoderStack [flow-v, stack-count: "$N\times$", stack-offset: "-2mm, 2mm"]:
  MHA_Enc [box, label: "Multi-Head Attention"]
  FFN_Enc [box, label: "Feed Forward"]
```
- tensor3d: custom TikZ \pic or 3d library cuboid
- stack-count: loop in TikZ, offset rectangles with lower opacity

### P2: Macro-to-Micro Callouts
```relic
TransformerBlock [box, label: "Transformer Block"]

container BlockInternals [flow-v, gap: 5mm]:
  MHA [box, label: "MHA"]
  FFN [box, label: "FFN"]

callout TransformerBlock -> BlockInternals [style: dashed, fill: gray!10]
```
- Callout acts as rank-breaker in resolver
- Draws transparent trapezoid connecting source corners to target bbox

### P3: Bus Routing & Edge Bundling
```relic
bus AttentionInputs [layout: flow-h, gap: 5mm]:
  Q [box, label: "$Q$"]
  K [box, label: "$K$"]
  V [box, label: "$V$"]

arrow AttentionInputs -> MHA [route: bundled-orthogonal]
```
- Calculate central "trunk" coordinate
- Q/K/V route orthogonally to trunk, merge, single thick arrow to target

### P4: Aesthetics & Micro-Typography
- `shadow: true` → `drop shadow={opacity=0.15}`
- Port syntax: `arrow A.south -> B.north`
- `blur shadow` on all nodes
- Standardized corner radii (3pt)
- `\sffamily` font for modern look

## Agent-First Loop Design

### Semantic Constraints (not coordinates)
```
DecoderStack positioned right-of EncoderStack
```
Compiler decides "right-of" = 15mm gap by default.

### Smart Defaults (LLM Safety Net)
- `arrow A -> B` — compiler picks route automatically based on rank positions
- Same rank → straight line
- Adjacent ranks, aligned → straight vertical
- Offset → `|-` or bundled
- LLM should almost NEVER specify `[route]`

### LLM System Prompt
"You are an expert academic figure designer. Write Relic code. Follow these rules:
1. Identify logical containers first (Encoder, Decoder)
2. Populate containers using [flow-v] or [flow-h] — let compiler handle alignment
3. Define arrows strictly by source and target names — do NOT hardcode waypoints
4. Use [fill: theme-color] semantics (accent-blue, bg-light) rather than hex codes"

### Error Feedback Loop
Bad: `ResolveError: Node 'PosEnc' not found`
Good: `ResolveError: Arrow target 'PosEnc' does not exist. Did you mean 'PosEncEnc' or 'PosEncDec'? Declare the node in a container before routing.`

## Target TikZ Blueprint
See `examples/ideal_multihead_attention.tex` for the 10/10 target.
