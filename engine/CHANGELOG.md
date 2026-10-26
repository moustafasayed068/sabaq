# Engine changelog

Every change that can alter a generated plan bumps `ENGINE_VERSION` (engine/__init__.py).
Plans already stored keep the version they were made with.

## Unreleased

- `resume_after_clearance()`: the plan-lab "doctor cleared me" button, ported as is (pain none,
  doctor cleared, first week easy only with no increase). No change to generated plans.

## 1.2.0 (2026-10-26)

Owner-approved: keep the planned week close to its target for low-volume runners.
On 3,700 generated build weeks, weeks more than 15% over target went from 1,360 to 856,
and no week has fewer runs than the athlete does now.

- Start week: at most 10% above the athlete's current weekly km. The "+4 km" start
  only stays for run-walk beginners (floor 8 km). A runner at 10 km a week used to
  start at 15 km and run about 20 km from week 2; now 11 km, then about 14 km.
- Quality sessions in small weeks get a shorter warm-up and cool-down: warm-up
  12% of the week (1 to 2 km), cool-down 8% (1 to 1.5 km), rounded to 0.5 km.
  Unchanged from about 19 km a week up.
- Easy runs shrink (never under 2 km) to keep the week within 10% of its target.
  If that is not enough, an easy day becomes rest (the day before the long run
  first), but never below the runs the athlete does now (and at least 2).
- Cutback week long run is 80% of the long run that week would have had. Before,
  it could equal or exceed the build week before it.

Known remainder for the coach review: very small weeks (under ~15 km) with a long
current longest run can still be 15%+ over target, because the long run never drops
below the athlete's current longest.

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
