"""Building generation tools.

Pure functions that create or modify Building models:
- Shell generator: footprint + floors → exterior walls + slabs
- Vertical core: elevator shaft + staircase placement
- Corridor carving: access from core to apartment zones
- Template stamping: replicate floor layouts
"""

from archicad_builder.generators.shell import generate_shell
from archicad_builder.generators.core import place_vertical_core
from archicad_builder.generators.corridor import carve_corridor
from archicad_builder.generators.template import stamp_floor_template
from archicad_builder.generators.apartments import subdivide_apartments

__all__ = [
    "generate_shell",
    "place_vertical_core",
    "carve_corridor",
    "stamp_floor_template",
    "subdivide_apartments",
]
