# AI House Generation — Project Specs

This document captures the direction for a Minecraft house / structure generator that builds hollow homes from terrain-aware ground points, with AI in the loop. It is intended as the design brief for a local mod project and supporting Python tooling.

Related prior art in this repo: `mkmcfunction.py` (image → `.mcfunction`), `stl2mcfunction.py` (STL mesh → fill commands). This project pivots away from mesh/image printing toward **parametric, livable hollow structures**.

---

## 1. Goals

1. Generate **hollow** Minecraft homes (and eventually other structures) from a rich set of tunable parameters.
2. Define a **footprint from ground / corner points** so foundations follow uneven terrain.
3. Derive **floor (bottom) and roof (top)** heights from the height coordinate of those points (plus style parameters).
4. Emit Minecraft-ready output (`.mcfunction` now; in-game mod placement later).
5. Keep **AI optional but first-class**: prompts can drive parameters, plugins can wrap AI I/O, or scripts can export prompts for external models.
6. Use **requested block palettes** (walls, floors, roofs, accents, glass, doors, etc.).

Non-goals for v1: full interior furniture packs, redstone systems, village-scale planning, or replacing vanilla structure generation wholesale.

---

## 2. Core Concept: Build Up From Ground Points

### 2.1 Ground points

A house footprint is defined by an ordered list of **ground points** (Minecraft world coordinates):

```text
(x, y, z)   # y = height (vertical)
```

- Points form a closed polygon (first point implied to connect to last, or explicitly closed).
- Minimum practical footprint: **3 points** (triangle); typical homes: **4+** (rectangle, L-shape, irregular).
- Each point’s **y** is the local ground / foundation height at that corner (or along that edge).

### 2.2 Bottom of the house (foundation)

- **Foundation base** at each column is interpolated from neighboring ground-point y values across the footprint (bilinear / barycentric / edge-walk — TBD in implementation).
- Optional parameters:
  - `foundation_depth` — how many blocks below local ground to dig / fill (basement / stilts).
  - `foundation_mode`: `follow_terrain` | `flatten_to_lowest` | `flatten_to_highest` | `flatten_to_average` | `stilts`.
  - `slab_level` — force a uniform internal floor y after foundation work.

### 2.3 Top of the house (walls + roof)

- **Wall height** is measured upward from the local floor (or from a chosen reference: lowest corner, average, etc.).
- Parameters:
  - `wall_height` — interior clear height in blocks.
  - `story_count` — number of floors.
  - `story_height` — blocks per story (default derived from `wall_height`).
  - `roof_style`: `flat` | `gable` | `hip` | `shed` | `dome` | `none`.
  - `roof_pitch` / `roof_overhang`.
- The **top** of the shell is wall height (+ roof) above the chosen vertical reference, not a single global y, so hillside homes step correctly.

### 2.4 Hollow interiors

- Default: place **shell only** — floors, exterior walls, roof; interior volume is `air` (or left untouched).
- Optional hollow refinements:
  - Interior floor slabs per story.
  - Ceiling under roof.
  - Partition walls / rooms (later).
  - Doors / windows as openings in the shell (not solid fill).

Never fill the entire AABB with solid blocks unless an explicit `solid=true` debug mode is set.

---

## 3. Parameter Surface (Fine Tuning)

The generator should accept a large, structured parameter set (JSON/YAML/CLI). Groupings below are the intended schema for both the Python CLI and a future mod UI / datapack.

### 3.1 Identity & placement

| Parameter | Description |
|-----------|-------------|
| `name` | Output function / structure id |
| `origin` | Optional world origin offset `(x, y, z)` |
| `rotation` | `0` / `90` / `180` / `270` (yaw) |
| `mirror` | none / x / z |
| `seed` | RNG seed for procedural ornaments |

### 3.2 Footprint

| Parameter | Description |
|-----------|-------------|
| `ground_points` | List of `{x, y, z}` corners |
| `footprint_closed` | bool |
| `wall_thickness` | blocks (default 1) |
| `corner_style` | square / beveled / round (approx) |

### 3.3 Vertical structure

| Parameter | Description |
|-----------|-------------|
| `foundation_mode` | see §2.2 |
| `foundation_depth` | int |
| `foundation_block` | block id |
| `wall_height` | int |
| `story_count` | int |
| `story_height` | int |
| `floor_block` | block id |
| `ceiling_block` | block id / none |
| `hollow` | bool (default true) |

### 3.4 Envelope & openings

| Parameter | Description |
|-----------|-------------|
| `wall_block` | primary wall material |
| `wall_block_alt` | secondary / trim |
| `window_block` | e.g. `minecraft:glass_pane` |
| `window_spacing` | blocks between windows |
| `window_width` / `window_height` | size |
| `window_sill_height` | from floor |
| `door_block` / `door_facing` | door spec |
| `door_positions` | edge midpoints or explicit coords |
| `include_corners_solid` | keep corners filled (no window cutouts) |

### 3.5 Roof

| Parameter | Description |
|-----------|-------------|
| `roof_style` | flat / gable / hip / shed / dome / none |
| `roof_block` | primary |
| `roof_trim_block` | eaves / ridge |
| `roof_pitch` | rise/run or degrees |
| `roof_overhang` | blocks beyond walls |
| `gable_direction` | axis of ridge |

### 3.6 Style presets (optional shortcuts)

Named presets expand into full parameter sets, e.g.:

- `cottage_oak`
- `modern_quartz`
- `spruce_cabin`
- `desert_adobe`
- `deepslate_fort`

Presets are data, not hard-coded logic — AI or plugins can invent new presets.

### 3.7 Output

| Parameter | Description |
|-----------|-------------|
| `output_format` | `mcfunction` / `json_schematic` / `prompt` / `mod_packet` |
| `relative_coords` | use `~` relative fills |
| `chunk_commands` | split files if command count exceeds limit (~65k) |
| `clear_interior` | fill interior with air explicitly |

---

## 4. Generation Pipeline

```text
Ground points + params
        │
        ▼
┌───────────────────┐
│  Footprint mesh   │  polygon, edge list, interior mask
└─────────┬─────────┘
          ▼
┌───────────────────┐
│  Height field     │  per-column foundation y + floor y
└─────────┬─────────┘
          ▼
┌───────────────────┐
│  Shell builder    │  walls, floors, roof (hollow)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│  Openings         │  doors, windows, optional chimney
└─────────┬─────────┘
          ▼
┌───────────────────┐
│  Emitter          │  .mcfunction / schematic / mod API
└───────────────────┘
```

Optional AI stages can sit **before** (params from prompt) or **after** (critique / refine params) the shell builder — see §5.

---

## 5. AI Integration Ideas (Undecided — Capture for Later)

These are intentional options to evaluate when building the mod on a local machine. None are mandatory for the first working generator.

### 5.1 Option A — Script generates a prompt

1. User (or mod) collects ground points + coarse intent (“two-story spruce cabin, big windows”).
2. Script serializes the structured params + constraints into a **prompt** for an LLM.
3. LLM returns either:
   - completed JSON params, or
   - `.mcfunction` / block-placement plan (riskier; prefer JSON params).
4. Deterministic builder validates and builds the hollow house.

**Pros:** Clear separation; LLM never has to invent fill syntax.  
**Cons:** Needs a good schema + validation loop.

### 5.2 Option B — Plugin system with AI I/O

A host script loads plugins. Each plugin can:

- **ingest** free-text or multimodal AI output and map it to params;
- **emit** custom prompts tailored to that plugin’s style (Japanese townhouse, hobbit hole, etc.);
- **transform** an existing house graph (add porch, change roof);
- **post-process** block choices (palette swap, weathering).

Suggested plugin interface (Python sketch):

```python
class HousePlugin:
    name: str

    def build_prompt(self, context: HouseContext) -> str:
        """Optional: create an LLM prompt from current params / points."""

    def parse_ai_response(self, text: str, context: HouseContext) -> dict:
        """Optional: map AI text → parameter overrides."""

    def modify_params(self, params: dict) -> dict:
        """Deterministic param transforms (no AI required)."""

    def modify_structure(self, structure: StructureGraph) -> StructureGraph:
        """Optional: edit walls/floors/openings after shell build."""
```

Discovery: `plugins/*.py` or entry points. The core always remains able to run **without** AI or plugins.

### 5.3 Option C — Hybrid (recommended default to explore)

- Core = deterministic hollow builder from ground points + params.
- `prompt` subcommand exports a filled prompt template (Option A).
- Plugins (Option B) optionally call out to AI APIs or accept pasted responses.
- Mod UI later: player selects corners in-world → sends context to local/cloud AI → applies returned params → builds.

### 5.4 Prompt contract (shared)

Any AI path should ask the model to return **strict JSON** matching the parameter schema (§3), including:

- `ground_points` (echoed or lightly adjusted)
- materials
- stories / roof / openings
- `hollow: true`

Reject / repair responses that solid-fill interiors or omit required fields.

### 5.5 Safety & playability

- Cap footprint size and wall height (server / lag protection).
- Validate block ids against a known allow-list.
- Prefer relative `~` coordinates when building at the player.
- Log seed + params for reproducibility.

---

## 6. Minecraft Mod Direction (Local Project)

When starting the Fabric/Forge/NeoForge (TBD) mod:

1. **Wand / item** to mark ground points in order (right-click corners).
2. **Preview** ghost blocks or particle outline of footprint + height.
3. **Config screen** for materials, stories, roof, hollow, etc.
4. **Generate** button → runs the same algorithm as the Python tool (port or call shared logic).
5. **AI button** (optional): “Suggest style” / “Describe your house” → fills params via prompt pipeline (§5).
6. Persist last params as JSON for re-roll and sharing.

The Python repo remains the **spec + prototype** lab: iterate algorithms here, then port hot paths into the mod.

---

## 7. Output Formats

### 7.1 `.mcfunction` (near-term)

Same datapack workflow as `mkmcfunction.py`:

- `fill` / `setblock` for shell voxels.
- Relative coords from player or absolute from origin.
- Split into multiple functions if command count is large.

### 7.2 Intermediate structure graph (recommended internal)

Before emitting commands, represent the house as:

- voxels or sparse placement list `(x, y, z, block)`
- metadata: role = `foundation` | `wall` | `floor` | `roof` | `window` | `door` | `air_clear`

This makes plugins and AI post-edits easier than regex on `.mcfunction`.

### 7.3 Future

- Structure NBT / `.nbt` templates
- Litematica / WorldEdit schematics
- Direct mod world writes

---

## 8. Relationship to Existing Scripts

| Script | Role going forward |
|--------|--------------------|
| `mkmcfunction.py` | Keep for image prints; unrelated to homes |
| `stl2mcfunction.py` | Experimental mesh path; not the house pipeline |
| `housegen.py` (new) | Parametric hollow homes from ground points |
| `SPECS.md` (this file) | Design brief for mod + AI/plugin exploration |

Possible later reuse: STL silhouettes as **roof ornaments** or **sculpture props** beside houses — not as the primary home generator.

---

## 9. Milestones

### M0 — Specs & prototype CLI (this pass)

- [x] `SPECS.md` with goals, params, AI options, mod notes
- [ ] `housegen.py` accepts JSON config with ground points
- [ ] Emits hollow rectangular / polygonal shell as `.mcfunction`
- [ ] Example config + prompt export

### M1 — Terrain-aware foundations

- [ ] Per-column height from corner y values
- [ ] Foundation modes (`follow_terrain`, flatten variants, stilts)
- [ ] Multi-story floors + simple gable roof

### M2 — Openings & materials

- [ ] Doors / windows cut from walls
- [ ] Palettes / presets
- [ ] Command chunking

### M3 — Plugin + AI hooks

- [ ] Plugin loader + sample “prompt exporter” plugin
- [ ] JSON schema validation for AI responses
- [ ] Document prompt templates

### M4 — In-game mod

- [ ] Point-selection wand
- [ ] Preview + build
- [ ] Optional AI suggest panel

---

## 10. Open Questions

1. Fabric vs NeoForge for the first mod target?
2. Should ground-point y mean “block the player clicked” or “top of that block + 1”?
3. How aggressive should AI be allowed to move / add ground points?
4. Room graphs (bedrooms, kitchen) in v1 or defer to plugins?
5. Run AI client-side, server-side, or external only via exported prompts?

Record decisions here as they are made.

---

## 11. Glossary

- **Ground point** — A corner (or control point) of the footprint with world `(x, y, z)`.
- **Height field** — Per-column foundation / floor y derived from ground points.
- **Shell** — Exterior walls + floors + roof; interior hollow.
- **Structure graph** — Internal placement representation before command emission.
- **Preset** — Named bundle of materials + proportions.
- **Plugin** — Optional module that prompts AI, parses AI, or edits params/structure.
