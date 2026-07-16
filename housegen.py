#!/usr/bin/env python3
"""
Parametric hollow Minecraft house generator.

Builds a shell (foundation, walls, floors, optional roof) from ground points
and a large parameter set, then emits .mcfunction fill/setblock commands.

See SPECS.md for the full design (AI prompts, plugins, mod direction).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

Coord = Tuple[int, int, int]
Block = str


# ---------------------------------------------------------------------------
# Defaults & schema helpers
# ---------------------------------------------------------------------------

DEFAULTS: Dict[str, Any] = {
    "name": "house",
    "origin": [0, 0, 0],
    "rotation": 0,
    "mirror": "none",
    "seed": 0,
    "ground_points": [],
    "footprint_closed": True,
    "wall_thickness": 1,
    "corner_style": "square",
    "foundation_mode": "flatten_to_lowest",
    "foundation_depth": 0,
    "foundation_block": "minecraft:cobblestone",
    "wall_height": 4,
    "story_count": 1,
    "story_height": None,  # derived from wall_height when null
    "floor_block": "minecraft:oak_planks",
    "ceiling_block": None,
    "hollow": True,
    "wall_block": "minecraft:oak_planks",
    "wall_block_alt": "minecraft:oak_log",
    "window_block": "minecraft:glass_pane",
    "window_spacing": 3,
    "window_width": 1,
    "window_height": 2,
    "window_sill_height": 1,
    "door_block": "minecraft:oak_door",
    "door_width": 1,
    "door_height": 2,
    "door_edge_index": 0,  # which polygon edge gets the door (midpoint)
    "include_corners_solid": True,
    "roof_style": "gable",
    "roof_block": "minecraft:oak_stairs",
    "roof_slab_block": "minecraft:oak_slab",
    "roof_trim_block": "minecraft:oak_log",
    "roof_pitch": 1,
    "roof_overhang": 1,
    "gable_direction": "x",  # ridge runs along this horizontal axis
    "relative_coords": True,
    "clear_interior": True,
    "place_windows": True,
    "place_door": True,
}


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path) -> Dict[str, Any]:
    with path.open() as f:
        data = json.load(f)
    return deep_merge(DEFAULTS, data)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def _orient(a: Coord, b: Coord, c: Coord) -> int:
    """Cross-product sign in XZ plane (Minecraft: Y is up)."""
    v = (b[0] - a[0]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[0] - a[0])
    if v > 0:
        return 1
    if v < 0:
        return -1
    return 0


def point_in_polygon(x: int, z: int, polygon: Sequence[Coord]) -> bool:
    """Ray casting in the XZ plane. Vertices are (x, y, z)."""
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, _, z1 = polygon[i]
        x2, _, z2 = polygon[(i + 1) % n]
        if ((z1 > z) != (z2 > z)) and (
            x < (x2 - x1) * (z - z1) / (z2 - z1 + 0.0) + x1
        ):
            inside = not inside
    return inside


def bresenham_2d(x0: int, z0: int, x1: int, z1: int) -> List[Tuple[int, int]]:
    points: List[Tuple[int, int]] = []
    dx = abs(x1 - x0)
    dz = abs(z1 - z0)
    sx = 1 if x0 < x1 else -1
    sz = 1 if z0 < z1 else -1
    err = dx - dz
    x, z = x0, z0
    while True:
        points.append((x, z))
        if x == x1 and z == z1:
            break
        e2 = 2 * err
        if e2 > -dz:
            err -= dz
            x += sx
        if e2 < dx:
            err += dx
            z += sz
    return points


def polygon_edges(points: Sequence[Coord], closed: bool = True) -> List[Tuple[Coord, Coord]]:
    edges = [(points[i], points[i + 1]) for i in range(len(points) - 1)]
    if closed and len(points) >= 3:
        edges.append((points[-1], points[0]))
    return edges


def footprint_bounds(points: Sequence[Coord]) -> Tuple[int, int, int, int]:
    xs = [p[0] for p in points]
    zs = [p[2] for p in points]
    return min(xs), max(xs), min(zs), max(zs)


def interpolate_corner_height(x: int, z: int, points: Sequence[Coord]) -> float:
    """
    Inverse-distance weighting from corner y values.
    Used for follow_terrain foundation mode.
    """
    weights = []
    values = []
    for px, py, pz in points:
        dist = math.hypot(x - px, z - pz)
        if dist < 1e-6:
            return float(py)
        w = 1.0 / (dist * dist)
        weights.append(w)
        values.append(py)
    total = sum(weights)
    return sum(w * v for w, v in zip(weights, values)) / total


# ---------------------------------------------------------------------------
# Structure graph
# ---------------------------------------------------------------------------

@dataclass
class Placement:
    x: int
    y: int
    z: int
    block: Block
    role: str = "block"


@dataclass
class StructureGraph:
    placements: Dict[Coord, Placement] = field(default_factory=dict)

    def set(self, x: int, y: int, z: int, block: Block, role: str) -> None:
        self.placements[(x, y, z)] = Placement(x, y, z, block, role)

    def get(self, x: int, y: int, z: int) -> Optional[Placement]:
        return self.placements.get((x, y, z))

    def clear(self, x: int, y: int, z: int) -> None:
        self.placements.pop((x, y, z), None)

    def items(self) -> Iterable[Placement]:
        return self.placements.values()


# ---------------------------------------------------------------------------
# House builder
# ---------------------------------------------------------------------------

class HouseBuilder:
    def __init__(self, params: Dict[str, Any]):
        self.params = params
        self.points: List[Coord] = [
            (int(p[0]), int(p[1]), int(p[2]))
            if not isinstance(p, dict)
            else (int(p["x"]), int(p["y"]), int(p["z"]))
            for p in params["ground_points"]
        ]
        if len(self.points) < 3:
            raise ValueError("ground_points requires at least 3 corners")

        story_height = params.get("story_height")
        if story_height is None:
            story_height = max(3, int(params["wall_height"]))
        self.story_height = int(story_height)
        self.story_count = max(1, int(params["story_count"]))
        self.total_wall = self.story_height * self.story_count

        self.min_x, self.max_x, self.min_z, self.max_z = footprint_bounds(self.points)
        self.base_y = self._resolve_base_y()
        self.structure = StructureGraph()
        self.wall_columns: Set[Tuple[int, int]] = set()
        self.interior_columns: Set[Tuple[int, int]] = set()

    def _resolve_base_y(self) -> int:
        ys = [p[1] for p in self.points]
        mode = self.params["foundation_mode"]
        if mode == "flatten_to_highest":
            return max(ys)
        if mode == "flatten_to_average":
            return int(round(sum(ys) / len(ys)))
        if mode in ("flatten_to_lowest", "stilts", "follow_terrain"):
            return min(ys)
        return min(ys)

    def column_foundation_y(self, x: int, z: int) -> int:
        mode = self.params["foundation_mode"]
        if mode == "follow_terrain":
            return int(round(interpolate_corner_height(x, z, self.points)))
        if mode == "stilts":
            return self.base_y
        # flatten_* modes: uniform floor at base_y
        return self.base_y

    def build(self) -> StructureGraph:
        self._classify_columns()
        self._build_foundation_and_floors()
        self._build_walls()
        if self.params.get("clear_interior") and self.params.get("hollow", True):
            self._clear_interior_air()
        if self.params.get("place_windows"):
            self._cut_windows()
        if self.params.get("place_door"):
            self._cut_door()
        self._build_roof()
        return self.structure

    def _classify_columns(self) -> None:
        # Edge columns via Bresenham along polygon edges
        for a, b in polygon_edges(self.points, self.params["footprint_closed"]):
            for x, z in bresenham_2d(a[0], a[2], b[0], b[2]):
                self.wall_columns.add((x, z))

        # Interior = inside polygon, not on wall ring
        for x in range(self.min_x, self.max_x + 1):
            for z in range(self.min_z, self.max_z + 1):
                if (x, z) in self.wall_columns:
                    continue
                if point_in_polygon(x, z, self.points):
                    self.interior_columns.add((x, z))

        # Thicken walls inward if requested
        thickness = max(1, int(self.params["wall_thickness"]))
        if thickness > 1:
            extra: Set[Tuple[int, int]] = set()
            for _ in range(thickness - 1):
                candidates = set(self.interior_columns)
                for x, z in candidates:
                    neighbors = ((x - 1, z), (x + 1, z), (x, z - 1), (x, z + 1))
                    if any(n in self.wall_columns for n in neighbors):
                        extra.add((x, z))
                for col in extra:
                    self.wall_columns.add(col)
                    self.interior_columns.discard(col)
                extra.clear()

    def _build_foundation_and_floors(self) -> None:
        foundation_block = self.params["foundation_block"]
        floor_block = self.params["floor_block"]
        depth = max(0, int(self.params["foundation_depth"]))
        all_cols = self.wall_columns | self.interior_columns

        for x, z in all_cols:
            fy = self.column_foundation_y(x, z)
            # foundation below floor
            for d in range(1, depth + 1):
                self.structure.set(x, fy - d, z, foundation_block, "foundation")
            # floor at each story
            for story in range(self.story_count):
                y = fy + story * self.story_height
                role = "floor"
                block = floor_block if story > 0 or (x, z) in self.interior_columns else foundation_block
                if story == 0 and (x, z) in self.wall_columns:
                    block = foundation_block
                    role = "foundation"
                elif story == 0:
                    block = floor_block
                self.structure.set(x, y, z, block, role)

            # stilts: pillars under walls down to lowest
            if self.params["foundation_mode"] == "stilts" and (x, z) in self.wall_columns:
                for y in range(self.base_y, fy):
                    self.structure.set(x, y, z, foundation_block, "foundation")

    def _build_walls(self) -> None:
        wall = self.params["wall_block"]
        alt = self.params["wall_block_alt"]
        corners = {(p[0], p[2]) for p in self.points}

        for x, z in self.wall_columns:
            fy = self.column_foundation_y(x, z)
            is_corner = (x, z) in corners
            block = alt if is_corner else wall
            for dy in range(1, self.total_wall + 1):
                # skip floor levels already placed except we want walls above floor
                y = fy + dy
                # don't overwrite story floors on wall columns with wall unless not floor row
                if dy % self.story_height == 0 and dy < self.total_wall:
                    # intermediate floor ring on exterior — keep floor block
                    continue
                self.structure.set(x, y, z, block, "wall")

    def _clear_interior_air(self) -> None:
        for x, z in self.interior_columns:
            fy = self.column_foundation_y(x, z)
            for dy in range(1, self.total_wall + 1):
                if dy % self.story_height == 0 and dy < self.total_wall:
                    continue  # keep interior floor slabs
                y = fy + dy
                existing = self.structure.get(x, y, z)
                if existing and existing.role in ("wall", "roof"):
                    continue
                self.structure.set(x, y, z, "minecraft:air", "air_clear")

    def _edge_midpoint(self, edge_index: int) -> Tuple[int, int, int, int, int]:
        edges = polygon_edges(self.points, True)
        edge_index = edge_index % len(edges)
        a, b = edges[edge_index]
        mx = (a[0] + b[0]) // 2
        mz = (a[2] + b[2]) // 2
        # outward-ish facing hint from edge direction
        dx = b[0] - a[0]
        dz = b[2] - a[2]
        return mx, mz, dx, dz, edge_index

    def _cut_door(self) -> None:
        mx, mz, dx, dz, _ = self._edge_midpoint(int(self.params["door_edge_index"]))
        # snap to nearest wall column
        if (mx, mz) not in self.wall_columns:
            nearest = min(
                self.wall_columns,
                key=lambda c: (c[0] - mx) ** 2 + (c[1] - mz) ** 2,
            )
            mx, mz = nearest

        fy = self.column_foundation_y(mx, mz)
        height = int(self.params["door_height"])
        width = int(self.params["door_width"])

        # door along the edge direction
        if abs(dx) >= abs(dz):
            offsets = [(i, 0) for i in range(width)]
        else:
            offsets = [(0, i) for i in range(width)]

        for ox, oz in offsets:
            x, z = mx + ox, mz + oz
            if (x, z) not in self.wall_columns:
                continue
            for h in range(1, height + 1):
                # Prefer air opening; door block lower half if single door
                if width == 1 and h == 1:
                    self.structure.set(x, fy + h, z, self.params["door_block"], "door")
                elif width == 1 and h == 2:
                    # upper half: still air/opening — mc doors are block entities;
                    # emit air so the shell is open; place lower door only.
                    self.structure.set(x, fy + h, z, "minecraft:air", "door")
                else:
                    self.structure.set(x, fy + h, z, "minecraft:air", "door")

    def _cut_windows(self) -> None:
        spacing = max(2, int(self.params["window_spacing"]))
        width = max(1, int(self.params["window_width"]))
        height = max(1, int(self.params["window_height"]))
        sill = max(1, int(self.params["window_sill_height"]))
        glass = self.params["window_block"]
        corners = {(p[0], p[2]) for p in self.points}
        keep_corners = bool(self.params["include_corners_solid"])

        for a, b in polygon_edges(self.points, True):
            line = bresenham_2d(a[0], a[2], b[0], b[2])
            # skip endpoints (corners)
            if len(line) < 5:
                continue
            i = 2
            while i < len(line) - 2:
                # place a window cluster of `width` then skip spacing
                for w in range(width):
                    if i + w >= len(line) - 2:
                        break
                    x, z = line[i + w]
                    if keep_corners and (x, z) in corners:
                        continue
                    if (x, z) not in self.wall_columns:
                        continue
                    fy = self.column_foundation_y(x, z)
                    for h in range(height):
                        y = fy + sill + 1 + h
                        if y >= fy + self.total_wall:
                            break
                        self.structure.set(x, y, z, glass, "window")
                i += width + spacing

    def _build_roof(self) -> None:
        style = self.params["roof_style"]
        if style in (None, "none"):
            return
        if style == "flat":
            self._roof_flat()
        elif style == "shed":
            self._roof_shed()
        else:
            # gable / hip fallback to gable approximation on AABB
            self._roof_gable()

    def _roof_flat(self) -> None:
        block = self.params.get("roof_slab_block") or self.params["roof_block"]
        overhang = int(self.params["roof_overhang"])
        top = self.base_y + self.total_wall
        for x in range(self.min_x - overhang, self.max_x + overhang + 1):
            for z in range(self.min_z - overhang, self.max_z + overhang + 1):
                # cover footprint plus overhang near bounds
                if (
                    self.min_x - overhang <= x <= self.max_x + overhang
                    and self.min_z - overhang <= z <= self.max_z + overhang
                ):
                    if point_in_polygon(x, z, self.points) or self._near_footprint(x, z, overhang):
                        self.structure.set(x, top + 1, z, block, "roof")

    def _near_footprint(self, x: int, z: int, overhang: int) -> bool:
        for wx, wz in self.wall_columns:
            if abs(wx - x) + abs(wz - z) <= overhang:
                return True
        return False

    def _roof_shed(self) -> None:
        pitch = max(1, int(self.params["roof_pitch"]))
        block = self.params["roof_block"]
        overhang = int(self.params["roof_overhang"])
        span = max(1, self.max_z - self.min_z)
        top = self.base_y + self.total_wall
        for x in range(self.min_x - overhang, self.max_x + overhang + 1):
            for z in range(self.min_z - overhang, self.max_z + overhang + 1):
                if not (
                    point_in_polygon(x, z, self.points) or self._near_footprint(x, z, overhang)
                ):
                    continue
                rise = ((z - self.min_z) * pitch) // span
                self.structure.set(x, top + 1 + rise, z, block, "roof")

    def _roof_gable(self) -> None:
        pitch = max(1, int(self.params["roof_pitch"]))
        block = self.params["roof_block"]
        trim = self.params["roof_trim_block"]
        overhang = int(self.params["roof_overhang"])
        axis = self.params.get("gable_direction", "x")
        top = self.base_y + self.total_wall

        if axis == "x":
            # ridge parallel to X — height from distance to center Z
            mid = (self.min_z + self.max_z) / 2.0
            half = max(1.0, (self.max_z - self.min_z) / 2.0)
            for x in range(self.min_x - overhang, self.max_x + overhang + 1):
                for z in range(self.min_z - overhang, self.max_z + overhang + 1):
                    if not (
                        point_in_polygon(x, z, self.points)
                        or self._near_footprint(x, z, overhang)
                    ):
                        continue
                    dist = abs(z - mid)
                    rise = int((1.0 - dist / half) * pitch * half)
                    rise = max(0, rise)
                    b = trim if dist < 0.75 else block
                    self.structure.set(x, top + 1 + rise, z, b, "roof")
        else:
            mid = (self.min_x + self.max_x) / 2.0
            half = max(1.0, (self.max_x - self.min_x) / 2.0)
            for x in range(self.min_x - overhang, self.max_x + overhang + 1):
                for z in range(self.min_z - overhang, self.max_z + overhang + 1):
                    if not (
                        point_in_polygon(x, z, self.points)
                        or self._near_footprint(x, z, overhang)
                    ):
                        continue
                    dist = abs(x - mid)
                    rise = int((1.0 - dist / half) * pitch * half)
                    rise = max(0, rise)
                    b = trim if dist < 0.75 else block
                    self.structure.set(x, top + 1 + rise, z, b, "roof")


# ---------------------------------------------------------------------------
# Emitters
# ---------------------------------------------------------------------------

def emit_mcfunction(
    structure: StructureGraph,
    params: Dict[str, Any],
    out_path: Path,
) -> None:
    ox, oy, oz = [int(v) for v in params.get("origin", [0, 0, 0])]
    relative = bool(params.get("relative_coords", True))
    lines: List[str] = []

    # Deterministic order for stable diffs
    for p in sorted(structure.items(), key=lambda pl: (pl.y, pl.z, pl.x)):
        if p.block == "minecraft:air" and p.role == "air_clear":
            # still emit air clears so interiors empty when rebuilding
            pass
        x, y, z = p.x + ox, p.y + oy, p.z + oz
        if relative:
            # interpret ground points as offsets from player
            lines.append(f"setblock ~{x} ~{y} ~{z} {p.block}")
        else:
            lines.append(f"setblock {x} {y} {z} {p.block}")

    out_path.write_text("\n".join(lines) + ("\n" if lines else ""))
    print(f"Wrote {len(lines)} commands to {out_path}")


def build_ai_prompt(params: Dict[str, Any]) -> str:
    """
    Option A from SPECS.md: serialize current intent into an LLM prompt
    that must return strict JSON matching the house parameter schema.
    """
    schema_hint = {
        k: DEFAULTS[k]
        for k in (
            "name",
            "ground_points",
            "foundation_mode",
            "foundation_depth",
            "foundation_block",
            "wall_height",
            "story_count",
            "story_height",
            "hollow",
            "wall_block",
            "wall_block_alt",
            "floor_block",
            "window_block",
            "window_spacing",
            "window_width",
            "window_height",
            "window_sill_height",
            "door_block",
            "door_edge_index",
            "roof_style",
            "roof_block",
            "roof_pitch",
            "roof_overhang",
            "gable_direction",
            "place_windows",
            "place_door",
            "clear_interior",
        )
    }
    current = {k: params.get(k, DEFAULTS.get(k)) for k in schema_hint}
    return f"""You are helping design a hollow Minecraft house for a parametric builder.

Constraints:
- The house MUST be hollow (interior air, shell only).
- Respect the provided ground_points; you may lightly adjust materials and style, not erase the footprint.
- Return ONLY valid JSON matching the schema below. No markdown fences, no commentary.
- Use full Minecraft block ids (e.g. minecraft:oak_planks).
- Y is vertical height. Ground point y values define terrain / foundation height at each corner.

Current parameters (edit and complete as needed):
{json.dumps(current, indent=2)}

Schema defaults / allowed keys:
{json.dumps(schema_hint, indent=2)}

foundation_mode one of: follow_terrain, flatten_to_lowest, flatten_to_highest, flatten_to_average, stilts
roof_style one of: flat, gable, hip, shed, dome, none
"""


# ---------------------------------------------------------------------------
# Plugin stubs (Option B) — loadable later
# ---------------------------------------------------------------------------

class HousePlugin:
    name = "base"

    def build_prompt(self, params: Dict[str, Any]) -> str:
        return build_ai_prompt(params)

    def parse_ai_response(self, text: str, params: Dict[str, Any]) -> Dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("AI response must be a JSON object")
        if data.get("hollow") is False:
            raise ValueError("AI attempted to disable hollow builds")
        return deep_merge(params, data)

    def modify_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return params


def load_plugins(directory: Optional[Path]) -> List[HousePlugin]:
    """
    Minimal plugin loader. Any .py file in directory defining `Plugin(HousePlugin)`
    is instantiated. Fails soft if directory missing.
    """
    plugins: List[HousePlugin] = [HousePlugin()]
    if directory is None or not directory.is_dir():
        return plugins

    import importlib.util

    for path in sorted(directory.glob("*.py")):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        plugin_cls = getattr(module, "Plugin", None)
        if plugin_cls is None:
            continue
        plugins.append(plugin_cls())
        print(f"Loaded plugin: {getattr(plugins[-1], 'name', path.stem)}")
    return plugins


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a hollow Minecraft house .mcfunction from ground points + params."
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        help="JSON config with ground_points and style parameters",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output .mcfunction path (default: <name>.mcfunction)",
    )
    parser.add_argument(
        "--prompt",
        action="store_true",
        help="Print an AI prompt for this config instead of building",
    )
    parser.add_argument(
        "--prompt-out",
        type=Path,
        help="Write AI prompt to a file",
    )
    parser.add_argument(
        "--apply-ai",
        type=Path,
        help="JSON file from an AI response to merge into config before build",
    )
    parser.add_argument(
        "--plugins",
        type=Path,
        default=None,
        help="Directory of house plugins (optional)",
    )
    parser.add_argument(
        "--dump-graph",
        type=Path,
        help="Optional path to write structure graph JSON",
    )
    parser.add_argument(
        "--write-defaults",
        type=Path,
        help="Write a starter JSON config with defaults + sample rectangle and exit",
    )
    args = parser.parse_args(argv)

    if args.write_defaults:
        sample = dict(DEFAULTS)
        sample["name"] = "sample_cottage"
        sample["ground_points"] = [
            {"x": 0, "y": 64, "z": 0},
            {"x": 10, "y": 64, "z": 0},
            {"x": 10, "y": 65, "z": 8},
            {"x": 0, "y": 64, "z": 8},
        ]
        sample["wall_block"] = "minecraft:spruce_planks"
        sample["wall_block_alt"] = "minecraft:spruce_log"
        sample["floor_block"] = "minecraft:spruce_planks"
        sample["foundation_block"] = "minecraft:cobblestone"
        sample["roof_block"] = "minecraft:dark_oak_stairs"
        sample["roof_slab_block"] = "minecraft:dark_oak_slab"
        sample["roof_trim_block"] = "minecraft:spruce_log"
        sample["relative_coords"] = True
        # For relative mode, y in ground points is used as absolute in builder;
        # origin shifts the whole structure. Sample uses small local coords:
        sample["ground_points"] = [
            {"x": 0, "y": 0, "z": 0},
            {"x": 10, "y": 0, "z": 0},
            {"x": 10, "y": 1, "z": 8},
            {"x": 0, "y": 0, "z": 8},
        ]
        sample["foundation_mode"] = "follow_terrain"
        args.write_defaults.write_text(json.dumps(sample, indent=2) + "\n")
        print(f"Wrote starter config to {args.write_defaults}")
        return 0

    if not args.config:
        parser.error("--config is required unless using --write-defaults")

    params = load_config(args.config)
    plugins = load_plugins(args.plugins)
    for plugin in plugins:
        params = plugin.modify_params(params)

    if args.apply_ai:
        text = args.apply_ai.read_text()
        # Prefer last plugin's parser, fall back to base
        parser_plugin = plugins[-1]
        params = parser_plugin.parse_ai_response(text, params)

    if args.prompt or args.prompt_out:
        prompt = plugins[-1].build_prompt(params)
        if args.prompt_out:
            args.prompt_out.write_text(prompt)
            print(f"Wrote AI prompt to {args.prompt_out}")
        if args.prompt:
            print(prompt)
        if not args.output and not args.dump_graph:
            return 0

    builder = HouseBuilder(params)
    structure = builder.build()

    if args.dump_graph:
        graph = [
            {"x": p.x, "y": p.y, "z": p.z, "block": p.block, "role": p.role}
            for p in sorted(structure.items(), key=lambda pl: (pl.y, pl.z, pl.x))
        ]
        args.dump_graph.write_text(json.dumps(graph, indent=2) + "\n")
        print(f"Wrote structure graph ({len(graph)} blocks) to {args.dump_graph}")

    out = args.output or Path(f"{params.get('name', 'house')}.mcfunction")
    emit_mcfunction(structure, params, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
