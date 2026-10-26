// Sanity tests for the Sabaq plan engine: node test.js
const E = require('./sabaq-engine.js');
let fails = 0;
const ok = (cond, msg) => { if (!cond) { fails++; console.log('  FAIL:', msg); } };
const base = {
  startDate: '2026-10-27', age: 28, sex: 'm', weeklyKm: 20, longestKm: 10, runsPerWeek: 3,
  recentKm: 5, recentTime: '28:00', goal: 'finish', days: [6, 1, 3, 5], injury: 'none', pain: 'none',
  health: {}, env: { where: 'outdoor', gps: true, kit: [] },
};
const race = (id, km) => { const r = E.RACES.find((x) => x.id === id); return { raceId: id, raceName: r.name, raceType: r.type, raceDate: (r.dateByDistance && r.dateByDistance[km]) || r.date, distanceKm: km }; };

function checkRunPlan(p, label) {
  const hard = (w) => w && ['quality', 'long'].includes(w.kind);
  let prevKm = null;
  p.weeks.forEach((wk, i) => {
    const days = wk.days.filter((d) => d.role !== 'off');
    const longs = days.filter((d) => d.workout && d.workout.kind === 'long');
    ok(longs.length <= 1, `${label} w${i}: more than one long run`);
    const q = days.filter((d) => d.workout && d.workout.kind === 'quality').length;
    ok(q <= 2, `${label} w${i}: ${q} quality sessions`);
    if (wk.phase !== 'race' && prevKm && wk.days[0].role !== 'off') ok(wk.km <= prevKm * 1.2 + 3, `${label} w${i}: jump ${prevKm} -> ${wk.km}`);
    if (wk.days.every((d) => d.role !== 'off') && wk.phase !== 'race' && wk.phase !== 'cutback') prevKm = wk.km;
  });
  const last = p.weeks[p.weeks.length - 1];
  const raceDay = last.days.find((d) => d.role === 'race');
  ok(raceDay && raceDay.date === p.input.raceDate, `${label}: race day on ${p.input.raceDate}`);
  const before = last.days[last.days.indexOf(raceDay) - 1];
  ok(before && (!before.workout || before.workout.kind === 'rest'), `${label}: rest the day before the race`);
}

function show(p) {
  console.log(`  status=${p.status} level=${p.levelName} peakLong=${p.peakLong} peakWeekly=${p.peakWeekly} paces=${JSON.stringify(p.paces || {})}`);
  p.messages.forEach((m) => console.log('  msg:', m));
  p.weeks.forEach((w) => console.log(`  W${w.index + 1} ${w.start} ${w.phaseName} ~${w.km}km: ` + w.days.filter((d) => d.workout).map((d) => `${d.dayName} ${d.workout.title}${d.workout.km ? ' ' + d.workout.km : ''}`).join(' | ')));
}

console.log('1) Intermediate, Pyramids half, 4 days');
let p = E.generate({ ...base, ...race('pyramids', 21.1) });
show(p); checkRunPlan(p, 'half');
ok(p.status !== 'blocked', 'half should not be blocked');

console.log('2) Beginner wants a marathon in 4 weeks -> blocked with alternatives');
p = E.generate({ ...base, weeklyKm: 5, longestKm: 3, runsPerWeek: 1, ...race('sharm', 42.2) });
show(p); ok(p.status === 'blocked', 'marathon beginner blocked'); console.log('  alts:', p.alternatives.map((a) => a.text));

console.log('3) Beginner 5K, run-walk, treadmill, no time');
p = E.generate({ ...base, weeklyKm: 4, longestKm: 2, runsPerWeek: 1, recentTime: '', env: { where: 'treadmill', gps: false, kit: [] }, ...race('gouna', 5) });
show(p); checkRunPlan(p, '5k');
ok(p.weeks[0].days.some((d) => d.workout && /جري ومشي/.test(d.workout.title)), 'run-walk used');

console.log('4) Health screen yes -> blocked; doctor cleared -> ok');
p = E.generate({ ...base, health: { chestActive: true }, ...race('pyramids', 10) });
ok(p.status === 'blocked' && p.blockKind === 'health', 'health block');
p = E.generate({ ...base, health: { chestActive: true }, doctorCleared: true, ...race('pyramids', 10) });
ok(p.status !== 'blocked', 'doctor cleared');

console.log('5) Outdoor without GPS -> minutes; track -> laps');
p = E.generate({ ...base, env: { where: 'outdoor', gps: false, kit: [] }, ...race('pyramids', 10) });
ok(JSON.stringify(p.weeks).includes('دقيقة بسرعة'), 'time-based steps');
p = E.generate({ ...base, env: { where: 'track', gps: true, kit: [] }, ...race('pyramids', 10) });
ok(JSON.stringify(p.weeks).includes('لفة'), 'track laps');

console.log('6) HYROX Cairo, home kit only (dumbbells) -> substitutes');
p = E.generate({ ...base, sex: 'f', days: [6, 0, 2, 4], env: { where: 'outdoor', gps: true, kit: ['dumbbells'] }, ...race('hyrox-cairo') });
show(p); p.warnings.forEach((w) => console.log('  warn:', w));
const txt = JSON.stringify(p.weeks);
ok(txt.includes('بدل Sled Push') && txt.includes('بدل Wall Balls'), 'station substitutes');
ok(txt.includes('2 × 16'), 'female farmers weight');

console.log('7) Long plan (Luxor marathon, advanced, 5 days) -> cutbacks + 2-week taper');
p = E.generate({ ...base, weeklyKm: 50, longestKm: 22, runsPerWeek: 5, recentTime: '21:30', days: [6, 0, 1, 3, 5], ...race('luxor', 42.2) });
show(p); checkRunPlan(p, 'marathon');
ok(p.weeks.filter((w) => w.phase === 'taper').length === 2, 'two taper weeks');

console.log('8) Check-in: chest cold after week 1');
p = E.generate({ ...base, ...race('pyramids', 21.1) });
let c = E.checkIn(p.input, p, 0, { done: 2, feel: 'hard', pain: 'none', sick: 'chest', sickDays: 3, longDone: false });
c.messages.forEach((m) => console.log('  ci:', m));
let p2 = E.generate(c.input); show(p2);
ok(p2.weeks[0].days.some((d) => d.workout && d.workout.kind === 'rest'), 'rest days after sickness');
ok(!p2.weeks[0].days.some((d) => d.workout && d.workout.kind === 'quality' && d.date <= c.input.flags.easyOnlyUntil), 'no quality before easyOnlyUntil');

console.log('9) Check-in: sharp pain -> paused');
c = E.checkIn(p.input, p, 0, { done: 3, feel: 'ok', pain: 'sharp', sick: 'none' });
ok(c.action === 'paused' && E.generate(c.input).status === 'blocked', 'paused');

console.log('10) Check-in: good week -> progression');
c = E.checkIn(p.input, p, 0, { done: 4, feel: 'easy', pain: 'none', sick: 'none', longDone: true });
p2 = E.generate(c.input);
console.log(`  week1 ${p.weeks[0].km} -> next ${p2.weeks[0].km}`);
ok(p2.weeks[0].km >= p.weeks[1].km * 0.85, 'keeps progressing');

console.log('11) Paces sanity: 5K 20:00 -> half ~1:32-1:34');
const v = E.vdotFrom(5, 1200); const t = E.predictTime(v, 21.0975);
console.log('  vdot', v.toFixed(1), 'half', E.fmtTime(t)); ok(t > 5480 && t < 5700, 'half prediction');

console.log('12) Times as people type them');
const pd = (x, km) => E.parseDuration(x, km);
ok(pd('28', 5) === 1680, '"28" for 5K = 28 min');
ok(pd('28:00', 5) === 1680, '28:00');
ok(pd('٢٨:٣٠', 5) === 1710, 'Arabic digits');
ok(pd('1:55', 21.1) === 6900, '"1:55" for a half = 1h55');
ok(pd('2', 21.1) === 7200, '"2" for a half = 2h');
ok(pd('0:28', 5) === 1680, '"0:28" = 28 min'); ok(pd('3:00', 5) === null && pd('abc', 5) === null, 'nonsense ignored');
p = E.generate({ ...base, recentTime: '28', goal: 'time', goalTime: '2:05:00', ...race('pyramids', 21.1) });
console.log('  "28" ->', JSON.stringify(p.paces), 'w1', p.weeks[0].km);
ok(p.paces.tempo === '5:52', 'paces from 28 minutes');
ok(p.weeks.every((w) => w.km < 45), 'no absurd weekly km');
p = E.generate({ ...base, recentTime: '3:00', ...race('pyramids', 21.1) });
ok(!p.paces && p.warnings.some((w) => w.includes('مش منطقي')), 'bad time -> effort + warning');

console.log(fails ? `\n${fails} FAILED` : '\nall passed');
process.exit(fails ? 1 : 0);
