"""3D scene construction for Blender (ADR-006).

scene_blender.py runs INSIDE Blender (stdlib only — Blender's Python has
no pydantic) and builds the .blend from the project's OBJ +
furniture.json + the render taste in project.toml. The strict config
gate ran earlier, in the pipeline's validate step.
"""
