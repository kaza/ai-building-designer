# Findings — static load takedown (2026-08-08)

1. **The roof of villa-maketa rests on glass, structurally speaking.**
   Every band window / glass slider with head at 2.80 m leaves a 0.20 m
   wall band; under Eurocode roof dead+snow at ULS those bands fail as
   unreinforced sections by 6–144× and even as minimally reinforced
   2Ø12 ring beams by 1.4–20× (attempt 01). The model needs explicit
   lintel/beam elements (RC downstand or steel) over every opening wider
   than ~1.5 m, or the roof must span onto cross walls. Win2: 25× plain;
   Win7: 57× plain — the owner's suspicion was correct.

2. **The takedown method is promotable.** From building.json alone
   (walls with load_bearing, roof outlines+thickness, opening geometry)
   a tributary-strip takedown + band check produces defensible,
   actionable per-opening verdicts in <1 s. Suitable as a framework
   validator phase (structural plausibility, E06x class): flag any
   opening whose band utilization exceeds 1.0 with a reinforced-band
   assumption, warn when a lintel element is missing. Model gap: the
   schema has no lintel/beam element to satisfy the check with — the
   feature needs that first.

3. **The as-modeled roof (0.45 m solid slab) is itself unrealistic** —
   11.25 kN/m² dead. Real flat roof ≈ 0.20 m RC + build-up ≈ 7 kN/m².
   The 0.45 in the model is a visual thickness (fascia look), which a
   structural phase must not take literally; scenario B exists for this.
