# Helper registry

Hand-written helper steps (D33). Each `<name>.ts` exports `name`, an `args` JSON Schema and
`run(page, args)`. Specs call them with `{ "action": "helper", "name": "...", "args": {...} }`;
models can only name helpers registered here. See `docs/TEST_SPEC.md`.
