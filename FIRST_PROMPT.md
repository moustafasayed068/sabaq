# أول رسالة لـ Claude Code

افتح الفولدر ده في Claude Code، وابعتله الرسالة دي زي ما هي:

---

Read CLAUDE.md and every file in docs/ first. Then look at reference/engine-js/ and open reference/plan-lab.html to understand the product.

Your job now is milestone M0 in docs/roadmap.md, in this order:

1. Propose the exact folder structure, packages (with versions) and CI pipeline for M0 in a short plan. Follow docs/architecture.md and docs/security.md. Wait for my OK before writing code.
2. After my OK, set up the repository foundation (settings split, custom user, Docker Compose, tooling, pre-commit, GitHub Actions with every gate, apps/core). Commit in small steps with passing tests.
3. Port the plan engine from reference/engine-js/sabaq-engine.js to engine/ in typed, pure Python. Port test.js to pytest, and add a golden test that runs every file in reference/engine-js/golden/ and compares the full output. All must pass. Use js_round for every Math.round.
4. Write ADR 0001 (modular monolith) and ADR 0002 (engine ported from the JS reference).
5. Tick the finished tasks in docs/roadmap.md and give me a short summary: what is done, how to run it, and anything you need from me.

Rules: never change an engine or safety rule without asking me. If something in the docs is unclear or contradicts itself, ask before guessing. Explain things to me in Egyptian Arabic; code, comments and commits in English.

---

بعد ما يخلّص M0، ابعتله: «كمّل M1 من docs/roadmap.md، مهمة مهمة، وكل مهمة في PR لوحدها.»
