// Writes golden outputs for the Python port: node make-golden.js
// Each case = an input (and optional check-in) and the exact plan the JS engine produced.
const fs = require('fs');
const path = require('path');
const E = require('./sabaq-engine.js');
const race = (id, km) => { const r = E.RACES.find((x) => x.id === id); return { raceId: id, raceName: r.name, raceType: r.type, raceDate: (r.dateByDistance && r.dateByDistance[km]) || r.date, distanceKm: km }; };
const base = { startDate: '2026-10-27', age: 28, sex: 'm', weightKg: 72, weeklyKm: 20, longestKm: 10, runsPerWeek: 3, recentKm: 5, recentTime: '28:00', goal: 'finish', days: [6, 1, 3, 5], injury: 'none', pain: 'none', health: {}, env: { where: 'outdoor', gps: true, kit: [] } };
const cases = {
  'half-intermediate': { ...base, ...race('pyramids', 21.1) },
  'half-goal-time': { ...base, goal: 'time', goalTime: '1:55:00', ...race('pyramids', 21.1) },
  'time-as-bare-minutes': { ...base, recentTime: '28', ...race('pyramids', 10) },
  'time-nonsense': { ...base, recentTime: '3:00', ...race('pyramids', 10) },
  '5k-beginner-treadmill': { ...base, weeklyKm: 4, longestKm: 2, runsPerWeek: 1, recentTime: '', env: { where: 'treadmill', gps: false, kit: [] }, ...race('gouna', 5) },
  '10k-outdoor-no-gps': { ...base, env: { where: 'outdoor', gps: false, kit: [] }, ...race('pyramids', 10) },
  '10k-track-knee-50plus': { ...base, age: 54, injury: 'knee', env: { where: 'track', gps: true, kit: ['dumbbells'] }, ...race('pyramids', 10) },
  'marathon-beginner-blocked': { ...base, weeklyKm: 5, longestKm: 3, runsPerWeek: 1, ...race('sharm', 42.2) },
  'marathon-advanced-5days': { ...base, weeklyKm: 50, longestKm: 22, runsPerWeek: 5, recentTime: '21:30', days: [6, 0, 1, 3, 5], env: { where: 'mixed', gps: true, kit: ['gym'] }, ...race('luxor', 42.2) },
  'hyrox-home-kit-female': { ...base, sex: 'f', days: [6, 0, 2, 4], env: { where: 'outdoor', gps: true, kit: ['dumbbells'] }, ...race('hyrox-cairo') },
  'hyrox-full-gym': { ...base, days: [6, 1, 3, 5], env: { where: 'mixed', gps: true, kit: ['gym', 'rower', 'skierg', 'sled', 'wallball', 'sandbag'] }, ...race('hyrox-dubai') },
  'health-blocked': { ...base, health: { chestActive: true }, ...race('pyramids', 10) },
  'health-cleared': { ...base, health: { chestActive: true }, doctorCleared: true, ...race('pyramids', 10) },
  'pain-now-blocked': { ...base, pain: 'now', ...race('pyramids', 10) },
  'under-18-blocked': { ...base, age: 16, ...race('pyramids', 10) },
  'race-in-5-days': { ...base, startDate: '2026-12-07', ...race('pyramids', 10) },
  'marathon-in-10-days': { ...base, weeklyKm: 60, longestKm: 28, runsPerWeek: 5, startDate: '2026-12-29', ...race('luxor', 42.2) },
  'hyrox-9-weeks': { ...base, startDate: '2026-09-30', ...race('hyrox-dubai') },
  'hyrox-race-week-two-near-days': { ...base, days: [2, 3, 5], ...race('hyrox-cairo') },
};
const checkins = {
  'checkin-chest-cold': ['half-intermediate', { done: 2, feel: 'hard', pain: 'none', sick: 'chest', sickDays: 3, longDone: false }],
  'checkin-head-cold': ['half-intermediate', { done: 3, feel: 'ok', pain: 'none', sick: 'head', longDone: true }],
  'checkin-sharp-pain': ['half-intermediate', { done: 3, feel: 'ok', pain: 'sharp', sick: 'none' }],
  'checkin-good-week': ['half-intermediate', { done: 4, feel: 'easy', pain: 'none', sick: 'none', longDone: true }],
  'checkin-missed-most': ['10k-outdoor-no-gps', { done: 1, feel: 'ok', pain: 'none', sick: 'none', longDone: false }],
  'checkin-new-time': ['half-intermediate', { done: 4, feel: 'ok', pain: 'mild', sick: 'none', longDone: true, newTime: '26:40' }],
};
const dir = path.join(__dirname, 'golden');
fs.mkdirSync(dir, { recursive: true });
for (const [name, input] of Object.entries(cases)) fs.writeFileSync(path.join(dir, `${name}.json`), JSON.stringify({ input, output: E.generate(input) }, null, 2));
for (const [name, [caseName, fb]] of Object.entries(checkins)) {
  const input = cases[caseName]; const plan = E.generate(input); const res = E.checkIn(input, plan, 0, fb);
  fs.writeFileSync(path.join(dir, `${name}.json`), JSON.stringify({ input, feedback: fb, checkIn: res, nextPlan: res.action === 'paused' ? null : E.generate(res.input) }, null, 2));
}
console.log('golden files:', fs.readdirSync(dir).length);
