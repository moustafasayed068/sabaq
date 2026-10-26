# 0002: Plan engine as pure Python, ported from the JS reference

Date: 2026-10-26. Status: accepted.

## Context

The training rules were first built and tried in JavaScript (`reference/engine-js/sabaq-engine.js`, used by `reference/plan-lab.html`). The product runs on Django, and the rules are safety rules (health screen, pain stop, increase caps, taper, sickness), so the Python version must behave exactly the same. A rewrite "in the same spirit" would silently change plans.

## Decision

- `engine/` is a line-by-line port: plain functions and dataclasses in, plain data out. No Django, no database, no network (a test checks its imports). Django calls it and stores the result with the exact input and `ENGINE_VERSION`.
- The JS reference is the spec. Python must reproduce every `reference/engine-js/golden/*.json` exactly, including dates, roles, titles, km and step text. When they differ, the JS reference wins unless the owner approves a change.
- JavaScript number behaviour is copied on purpose:
  - `js_round(x) = floor(x + 0.5)` everywhere the JS uses `Math.round`.
  - `fmt_num` prints numbers the way JS does (`3`, not `3.0`).
  - `js_number` and `num_or` copy `+x || default`.
  - `js_sum` adds left to right, because Python 3.12's `sum()` is compensated and can differ in the last bit.
- Reference quirks are kept and documented, not fixed during the port. Any rule change is proposed to the owner first.
- Three layers of tests:
  1. Golden files.
  2. `test.js` ported to pytest.
  3. A differential test that runs 1,500 seeded random inputs through both engines and requires identical output. 20,000 cases were checked once with no difference.

## Consequences

- We can trust that the Python plans are the plans the owner reviewed in the prototype.
- Changing a rule is deliberate:
  1. The owner approves the change.
  2. Change the JS reference and the Python port together.
  3. Regenerate the golden files with `node reference/engine-js/make-golden.js`.
  4. Bump `ENGINE_VERSION`.
  5. Stored plans keep their old version.
- The port mirrors the JS structure (long functions, positional arguments), which costs some Python style for easy side-by-side review. Once the owner retires the JS reference, the engine can be refactored freely behind the golden tests.
