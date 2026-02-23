"""IFC GlobalId generation and handling.

IFC uses 22-character compressed GUIDs (base64-ish encoding of 128-bit UUIDs).
We use these as our primary identifiers so that the same ID appears in both
our JSON model and the exported IFC file. Traceability across formats.
"""

from __future__ import annotations

import uuid

import ifcopenshell.guid


def generate_ifc_id() -> str:
    """Generate a new IFC-compatible GlobalId (22 characters)."""
    return ifcopenshell.guid.compress(uuid.uuid4().hex)


def is_valid_ifc_id(value: str) -> bool:
    """Check if a string is a valid 22-character IFC GlobalId."""
    return isinstance(value, str) and len(value) == 22
