"""Structural validation for building models.

Per-story validators:
- structural: door/window fits in wall, element references valid
- connectivity: wall endpoint connections, gap detection
- snap: auto-fix small endpoint gaps

Building-level validators:
- building: bearing wall alignment, staircase presence, slab completeness, wall closure
"""
