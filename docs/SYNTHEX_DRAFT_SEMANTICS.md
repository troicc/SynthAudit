# SynthEx paper-draft semantics

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

Adapter identity: **`synthaudit.synthex-paper-draft/0.1`**.

At `schwallergroup/synthex@5f41a6b21e3906fde93e84c88bb91f9dc4d37e6f`, the official repository contains a README and figures but no code, license file, ReactionJSON schema, RouteJSON schema, reference implementation, or fixtures. The README names ten primitives and shows:

```json
[
  {"op": "break_bond", "map_a": 11, "map_b": 13},
  {"op": "change_bond_order", "map_a": 8, "map_b": 16, "delta": 1}
]
```

The draft adapter is therefore explicitly experimental and must never be described as official SynthEx compatibility. `SynthExOfficialAdapter` always raises `UpstreamSpecificationUnavailable` until a pinned specification exists; it never calls the draft adapter.

## Draft input envelope

SynthAudit accepts either an operation list or an object containing `operations`, together with a separately supplied mapped product when it is not in the payload. The adapter preserves the full source payload and records `adapter_id`, version, assumptions, warnings, and unsupported fields.

## Supported operation names

| Name | Draft normalization rule |
|---|---|
| `break_bond` | `map_a` and `map_b` identify an existing product bond; optional declared order must match. |
| `add_bond` | Two existing mapped atoms and an explicit positive `order` are required. |
| `change_bond_order` | Existing bond plus exactly one of explicit `order` or numeric `delta`; delta is applied to the product bond and validated. |
| `change_atom` | Requires a mapped atom and an explicit supported field (`formal_charge`, `explicit_h`, `isotope`, `aromatic`, or `atomic_number`). |
| `set_explicit_h` | Requires atom map and non-negative integer count. |
| `add_group` | Requires a parseable mapped or unmapped fragment SMILES, explicit fragment attachment atom, and one or more product attachment maps. |
| `remove_group` | Requires explicit mapped atoms or an explicit fragment identity; no substructure match is guessed. |
| `invert_stereocenter` | Requires a mapped atom. Execution validates that stereochemistry is meaningful. |
| `clear_stereocenter` | Requires a mapped atom. |
| `set_bond_stereo` | Requires mapped bond endpoints, explicit `E`/`Z`, and, where ambiguous, stereo-neighbour maps. |

Fresh maps for `add_group` are assigned sequentially above the maximum existing map in deterministic fragment atom order. Existing nonzero fragment maps must not collide. Multi-attachment groups require an explicit connection list. Null and charge-only completion use canonical ReactionIR edit types rather than invented SynthEx fields.

## Rejection rules

The draft adapter rejects missing maps, ambiguous fragment attachment atoms, duplicate/colliding maps, conflicting `order` and `delta`, unsupported atom properties, unknown operations, implicit atom mapping, ambiguous group removal, and operation orders that reference atoms not yet present. Rejection is preferable to semantic guessing.

## Undocumented official semantics

The official version/envelope, field names beyond the one README example, order defaults, group grammar, atom-change representation, stereo-neighbour convention, errors, route identifiers/dependencies, intermediate representation, condition model, provenance, and canonicalization/round-trip guarantees remain undocumented.

No draft serialization is claimed to round-trip to future official ReactionJSON or RouteJSON.

## Draft route envelope

The separate route namespace is **`synthaudit.synthex-paper-draft-route/0.1`**.
It is a local SynthAudit interoperability envelope, not official RouteJSON. The route object
must declare that exact schema, a mapped target, and ordered steps. Each step has an explicit
`step_id`, a reaction payload in the reaction-draft namespace, and optional `depends_on`,
`consumes`, `produces`, strategy text, key-step flag, and metadata. Route-level starting
materials, intermediates, strategy text, and metadata are preserved in `RouteIRV1`.

Unknown route and step fields are reported with their source paths. Step reactions retain
their own unsupported-field reports and warnings. Dependency validation belongs to the
canonical `RouteIRV1` schema and route-audit stage; no undocumented SynthEx ordering,
intermediate, or condition semantics are inferred.
