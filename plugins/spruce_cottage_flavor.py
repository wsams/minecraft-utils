"""
Example housegen plugin: forces a cozy spruce cottage palette
and customizes the AI prompt flavor text.

Drop this file in a directory passed via: housegen.py --plugins ./plugins
"""

from __future__ import annotations

from typing import Any, Dict

# HousePlugin is provided by the host when loaded via importlib from housegen;
# for type checkers / direct import, fall back gracefully.
try:
    from housegen import HousePlugin, build_ai_prompt
except ImportError:  # pragma: no cover
    class HousePlugin:  # type: ignore
        name = "base"

        def build_prompt(self, params):
            raise NotImplementedError

        def parse_ai_response(self, text, params):
            raise NotImplementedError

        def modify_params(self, params):
            return params

    def build_ai_prompt(params):  # type: ignore
        return str(params)


class Plugin(HousePlugin):
    name = "spruce_cottage_flavor"

    def modify_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(params)
        out.setdefault("wall_block", "minecraft:spruce_planks")
        out.setdefault("wall_block_alt", "minecraft:spruce_log")
        out.setdefault("floor_block", "minecraft:spruce_planks")
        out.setdefault("roof_style", "gable")
        out["hollow"] = True
        return out

    def build_prompt(self, params: Dict[str, Any]) -> str:
        base = build_ai_prompt(params)
        return (
            base
            + "\n\nStyle hint: cozy spruce cottage, dark oak roof, "
            + "simple rectangular windows, single front door, hollow interior.\n"
        )
