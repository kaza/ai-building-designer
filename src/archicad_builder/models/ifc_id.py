"""IFC GlobalId generation and handling (specs/ifc-identity.md).

IFC uses 22-character compressed GUIDs (base64-ish encoding of 128-bit UUIDs).
We use these as our primary identifiers so that the same ID appears in both
our JSON model and the exported IFC file. Traceability across formats.

The identity rule: an id is minted exactly once — when the element is added
(`generate_ifc_id`). IFC-only entities (relationships, openings, psets) have
no life of their own, so their ids are *derived* from what they are
(`derived_ifc_id`) and stay stable across exports.
"""

from __future__ import annotations

import json
import uuid

import ifcopenshell.guid

# Frozen. Changing either constant rewrites every derived id in every export —
# the golden-vector tests in tests/test_identity.py make that a deliberate
# act, not an accident. (uuid5(NAMESPACE_DNS, "archicad-builder.ifc-identity"))
AB_NAMESPACE = uuid.UUID("89ae73f2-fae6-5f6c-8694-41fef8520c5a")
SEED_VERSION = "1"

# The 22-char compressed-GUID alphabet, in ifcopenshell's order. First char
# carries only the top 2 bits of the 128-bit value, so it is always 0-3.
_ALPHABET = set(
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$")


def generate_ifc_id() -> str:
    """Mint a new IFC-compatible GlobalId (22 characters). Call exactly once
    per element lifetime — on add, never on load or rebuild."""
    return ifcopenshell.guid.compress(uuid.uuid4().hex)


def derived_ifc_id(kind: str, *parts: str, index: int = 0) -> str:
    """Stable GlobalId for an IFC-only entity, derived from what it IS.

    `parts` must name every identity-defining participant (e.g. a void
    relation seeds on the host wall id AND the opening owner's id); `index`
    disambiguates genuine one-to-many cases (corner openings, door handles).
    The seed is a JSON array — injective, unlike a joined string — and
    versioned so a grammar change cannot silently reuse old ids.
    """
    seed = json.dumps([SEED_VERSION, kind, list(parts), index],
                      separators=(",", ":"))
    return ifcopenshell.guid.compress(uuid.uuid5(AB_NAMESPACE, seed).hex)


def is_valid_ifc_id(value: object) -> bool:
    """True iff `value` is a well-formed 22-character IFC GlobalId."""
    return (isinstance(value, str) and len(value) == 22
            and value[0] in "0123" and all(c in _ALPHABET for c in value))
