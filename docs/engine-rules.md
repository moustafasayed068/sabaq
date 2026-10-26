# Plan engine rules

The source of truth is `reference/engine-js/sabaq-engine.js`. This file explains it in words, for review by a coach or physiotherapist and for the Python port. Numbers here are the owner's current choices, not reviewed yet by a specialist.

## Before a plan

- Health screen (PAR-Q style, 8 yes/no questions: heart condition, chest pain in activity, chest pain at rest last month, dizziness/fainting, joint pain made worse by activity, heart/blood-pressure medication, pregnant or gave birth in the last 6 months, any other reason). Any yes → status `blocked` (kind `health`) until the athlete confirms a doctor cleared them.
- Current pain that gets worse with running → `blocked` (kind `pain`).
- Age under 18 → `blocked` (kind `age`).
- Race less than 3 days away → `blocked` (kind `date`).

## Level

- Beginner: fewer than 2 runs a week, or under 10 km a week, or longest run under 5 km.
- Advanced: 30 km a week or more and longest run 12 km or more.
- Otherwise intermediate.
- Very new runners (beginner with under 10 km a week or longest under 4 km) get run-walk sessions and no hard sessions.

## Paces

- From the latest race or time trial (distance + time) using the Daniels & Gilbert VDOT formulas.
- Fractions of VDOT: easy 0.62–0.74 (shown 0.70), marathon 0.80, tempo 0.88, interval 0.975, rep 1.04.
- Times are read the way people type them: `28` = 28 minutes, `28:00` = mm:ss, `1:55` for a half = 1h55. A reading is accepted only if its pace is between 2:30 and 15:00 per km. Otherwise the time is ignored and workouts are written by feel, with a warning.
- Goal time: allowed only within 1% improvement per week left (max 5%) over the current fitness. Otherwise the plan uses the closest realistic time and says so.
- No time → every workout is written by effort ("easy: you can talk in full sentences").

## Feasibility (running)

Minimum long run the athlete must reach before race day: 5K → 4 km, 10K → 7 km, half → 13 km, marathon → 24 km.

- Plan peak long run ≥ minimum → `ok`.
- ≥ 80% of minimum → `risky` (plan made, goal "finish only").
- Less → `blocked` (kind `feasibility`), with alternatives: a shorter distance in the same race that fits, or how many weeks are needed.
- Marathon in under 8 weeks with longest run under 24 km → blocked. Beginner and half or longer in under 8 weeks → blocked.
- A plan regenerated after a weekly check-in is never blocked for feasibility; it becomes `risky` with advice.

Target peak long run by level (beginner / intermediate / advanced): 5K 5/7/10, 10K 8/11/14, half 15/18/20, marathon 28/30/32 km. Peak weekly volume: 5K 15/25/40, 10K 20/32/50, half 28/40/60, marathon 45/55/75 km.

## Weeks

- Weeks are aligned to race day: the last week is the 7 days ending on race day. The first week can be partial (starts on the start date).
- Plans longer than 16 weeks start 16 weeks before the race.
- Weekly volume grows at most 10% per week (7% if age 50+ or any injury history).
- Long run grows at most 2 km per week (1.5 for beginners) and is capped at a share of the week: 45% (50% with 3 days, 38% with 5+ days), unless the athlete already runs longer than that.
- Cutback week (80%) every 4th week in plans of 7+ weeks, never in the last build week.
- Taper: half 1 week (80%) when the plan has 6+ weeks; marathon 2 weeks (80%, 60%) when 8+ weeks. Race week volume: 45% of peak (half and marathon) or 60% (5K/10K). Day before the race: rest. A short race-pace sharpener 3–4 days before (strides for beginners).
- Partial first week gets volume in proportion to the training days it contains.
- The last week is always race week. Very short plans drop the taper first, then the build weeks; a race this week is judged on current fitness.

## Days

- Athlete picks 3 to 6 days. Long run goes on Friday if picked, else Saturday, else the last picked day.
- Hard sessions: 1 a week; 2 only for advanced, 5+ days, under 50. The first hard day is the picked day furthest from the long run; a second one only with at least one day gap from both.
- The hard part of a session is about 18% of the week (15% when there are two).
- Rotations: 5K/10K: hills (non-advanced) / intervals / tempo. Half and marathon: tempo / cruise intervals (1.6 km). Knee injury history: tempo instead of hills.
- In build weeks (not the first), half and marathon long runs end with up to 25% (max 5 km) at race pace, not for beginners.
- Strength: 20 minutes after an easy run, twice a week (once in cutback/taper weeks), never the day before the long run. Exercises depend on kit: none (bodyweight), dumbbells, or gym. Knee history swaps lunges for single-leg bridges.

## Where and how they run

- Treadmill: speed in km/h, incline 1%; hills become 60 s at 5% incline.
- Outdoors without GPS: every distance becomes minutes at the expected pace.
- Track: intervals under 2 km are written in laps of 400 m.

## HYROX

- Weekly roles: compromised run (1 km run + a station, repeated) on the long-run day, stations + strength on the day furthest from it, km intervals at tempo pace on a third day, easy runs on the rest.
- Rounds grow from 3 per session up to 7 (5 for beginners); cutback weeks lighter.
- Race week: one race-effort simulation (3 rounds) 3–4 days before (never two), easy runs, rest the day before.
- Cutback week every 4th week in plans of 7+ weeks, never in the last build week (same rule as running).
- Missing equipment gets a substitute: SkiErg → rower or band pull-downs; Sled push → pushing a switched-off treadmill or wall pushes + walking lunges; Sled pull → heavy dumbbell rows + walking backwards, or a band/rope; Rowing → SkiErg, kettlebell swings, or burpees + squats; Farmers carry → two bags of water bottles; Sandbag lunges → backpack with books or bottles; Wall balls → dumbbell thrusters or a sandbag throw. A warning lists missing stations.
- Open division weights shown to the athlete (confirm with the official rulebook): wall ball 6 kg men / 4 kg women, farmers 2×24 / 2×16 kg, sandbag 20 / 10 kg.
- Longest run under 5 km → `risky`, suggest Doubles or Relay.

## Weekly check-in

Input: sessions done of planned, long run done, feel (easy/ok/hard), pain (none/mild/sharp), sick (none/head cold/chest or fever), sick days, optional new 5K time.

- Sharp pain (worse with running or changes how they run) → plan `paused` until a doctor clears them; restart at 70% of the volume done, injury history set.
- Chest/fever/body aches → rest for sick days + 2, then a week of easy running only, long run at 70%, volume cut 15% (30% if over a week off). Message says to see a doctor if fever lasts over 3 days or any chest pain/shortness of breath.
- Head cold only → 3 days easy only, no increase.
- Mild pain that goes after warm-up → no increase next week.
- Under half the sessions done, or the week felt hard → no increase.
- 75%+ done, not hard, no pain or sickness → progression continues.
- New 5K time → paces recalculated.
- After the check-in the remaining weeks are regenerated from the new state, starting next week.

## Race day text

Pacing (first 2 km 10 s/km slower), water and gels for half and longer, breakfast 2–3 h before (1–2 g carbs per kg if weight given), nothing new on race day.

## Not done yet

- Ramadan rules (needed before selling plans for February races).
- Heat rules beyond advice to run early.
- Specialist review of every number above.
