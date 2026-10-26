# Engine changelog

Every change that can alter a generated plan bumps `ENGINE_VERSION` (engine/__init__.py).
Plans already stored keep the version they were made with.

## 1.1.0 (2026-10-26)

Owner-approved fixes where the reference contradicted docs/engine-rules.md. JS reference,
Python port and golden files changed together.

- Race in 3 to 13 days: the last week is now always race week. Before, a 10K five days
  away had a long run the day before the race and an easy run on race day, and a
  marathon 10 days away had its race day written as a long run.
- HYROX: no cutback in the last build week (a 9-week plan had no peak week).
- HYROX race week: one race simulation at most (two could land 3 and 4 days before).
- Check-in: "أسبوع حلو. كمّل بنفس الخطة." now shows when pain is answered "none".

New golden cases: race-in-5-days, marathon-in-10-days, hyrox-9-weeks,
hyrox-race-week-two-near-days.

## 1.0.0 (2026-10-26)

Python port of reference/engine-js/sabaq-engine.js, identical output.
