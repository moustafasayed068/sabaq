/*
 * Sabaq plan engine (محرّك خطط سبق)
 * Builds a full race plan from a small workout library + safety rules.
 * Pure functions, no DOM. Works in the browser (window.SabaqEngine) and Node (module.exports).
 *
 * Main entry points:
 *   screen(healthAnswers)            -> { ok, reasons[] }
 *   generate(input)                  -> plan  (status: 'ok' | 'risky' | 'blocked')
 *   checkIn(input, plan, weekIndex, feedback) -> { action, messages[], input }  (feed result.input back into generate)
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.SabaqEngine = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // ---------------------------------------------------------------- dates (UTC, 'YYYY-MM-DD')
  const DAY = 86400000;
  const toDate = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(Date.UTC(y, m - 1, d)); };
  const iso = (d) => d.toISOString().slice(0, 10);
  const addDays = (s, n) => iso(new Date(toDate(s).getTime() + n * DAY));
  const diffDays = (a, b) => Math.round((toDate(b) - toDate(a)) / DAY);
  const weekday = (s) => toDate(s).getUTCDay(); // 0 = Sunday
  // Egyptian week runs Saturday -> Friday. Position 0..6 in that week.
  const egPos = (wd) => (wd + 1) % 7;
  const DAY_NAMES = ['الأحد', 'الاتنين', 'التلات', 'الأربع', 'الخميس', 'الجمعة', 'السبت'];

  // ---------------------------------------------------------------- races
  const RACES = [
    { id: 'hyrox-cairo', name: 'HYROX Cairo', type: 'hyrox', date: '2026-11-14', note: 'السباق يومين 14 و15 نوفمبر: اختار يوم موجتك.' },
    { id: 'gouna', name: 'نص ماراثون الجونة', type: 'run', date: '2026-11-21', distances: [5, 10, 21.1] },
    { id: 'hyrox-dubai', name: 'HYROX Dubai', type: 'hyrox', date: '2026-11-27' },
    { id: 'sharm', name: 'ماراثون شرم الشيخ', type: 'run', date: '2026-11-28', distances: [5, 10, 21.1, 42.2] },
    { id: 'pyramids', name: 'نص ماراثون الأهرامات', type: 'run', date: '2026-12-12', distances: [5, 10, 21.1], dateByDistance: { 5: '2026-12-11' } },
    { id: 'luxor', name: 'ماراثون الأقصر', type: 'run', date: '2027-01-08', distances: [5, 10, 21.1, 42.2] },
  ];
  const DIST_NAME = { 5: '5 كم', 10: '10 كم', 21.1: 'نص ماراثون (21.1 كم)', 42.2: 'ماراثون (42.2 كم)' };

  // ---------------------------------------------------------------- health screen (PAR-Q style)
  const HEALTH_QUESTIONS = [
    { id: 'heart', text: 'دكتور قالك قبل كده إن عندك مشكلة في القلب، أو إنك تتمرن تحت إشراف طبي بس؟' },
    { id: 'chestActive', text: 'بتحس بوجع في صدرك وانت بتتمرن أو بتعمل مجهود؟' },
    { id: 'chestRest', text: 'حسيت بوجع في صدرك وانت مرتاح في آخر شهر؟' },
    { id: 'dizzy', text: 'بتدوخ لدرجة إنك تفقد توازنك، أو أغمى عليك قبل كده؟' },
    { id: 'joint', text: 'عندك وجع دلوقتي في عضمة أو مفصل بيزيد مع الحركة؟' },
    { id: 'meds', text: 'بتاخد دوا للضغط أو للقلب؟' },
    { id: 'pregnant', text: 'حامل أو ولدتي في آخر 6 شهور؟' },
    { id: 'other', text: 'في أي سبب تاني تعرفه يخليك متتمرنش؟' },
  ];
  function screen(answers) {
    const reasons = HEALTH_QUESTIONS.filter((q) => answers && answers[q.id]).map((q) => q.id);
    return { ok: reasons.length === 0, reasons };
  }

  // ---------------------------------------------------------------- paces (Daniels & Gilbert VDOT formulas)
  const vo2At = (v) => -4.6 + 0.182258 * v + 0.000104 * v * v; // v in m/min
  const pctMax = (t) => 0.8 + 0.1894393 * Math.exp(-0.012778 * t) + 0.2989558 * Math.exp(-0.1932605 * t); // t in min
  const vdotFrom = (km, sec) => { const t = sec / 60; return vo2At((km * 1000) / t) / pctMax(t); };
  const speedForVo2 = (vo2) => { const a = 0.000104, b = 0.182258, c = -(4.6 + vo2); return (-b + Math.sqrt(b * b - 4 * a * c)) / (2 * a); };
  const paceAt = (vdot, frac) => 60000 / speedForVo2(vdot * frac); // sec per km
  function predictTime(vdot, km) { // seconds
    let lo = 5, hi = 900;
    for (let i = 0; i < 60; i++) { const mid = (lo + hi) / 2; if (vdotFrom(km, mid * 60) > vdot) lo = mid; else hi = mid; }
    return ((lo + hi) / 2) * 60;
  }
  function paceTable(vdot) {
    return {
      easySlow: paceAt(vdot, 0.62), easy: paceAt(vdot, 0.70), easyFast: paceAt(vdot, 0.74),
      marathon: paceAt(vdot, 0.80), tempo: paceAt(vdot, 0.88), interval: paceAt(vdot, 0.975), rep: paceAt(vdot, 1.04),
    };
  }
  const fmtPace = (s) => { s = Math.round(s); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
  const fmtTime = (s) => { s = Math.round(s); const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60; return h ? `${h}:${String(m).padStart(2, '0')}:${String(x).padStart(2, '0')}` : `${m}:${String(x).padStart(2, '0')}`; };
  const parseTime = (str) => { if (!str) return null; const p = String(str).trim().split(':').map(Number); if (p.some(isNaN)) return null; return p.reduce((a, b) => a * 60 + b, 0) || null; };
  // "28" = 28 minutes, "28:00" = mm:ss, "1:55" for a half = h:mm, Arabic digits and "." or "," accepted.
  // A reading counts only if its pace is between 2:30 and 15:00 per km.
  const MIN_PACE = 150, MAX_PACE = 900;
  function parseDuration(str, km) {
    if (str === null || str === undefined || String(str).trim() === '' || !km) return null;
    const norm = String(str).trim().replace(/[٠-٩]/g, (d) => '٠١٢٣٤٥٦٧٨٩'.indexOf(d)).replace(/[.,،:؛]+/g, ':');
    const p = norm.split(':').filter((x) => x !== '').map(Number);
    if (!p.length || p.length > 3 || p.some((x) => !isFinite(x) || x < 0)) return null;
    const cands = p.length === 1 ? [p[0] * 60, p[0] * 3600] : p.length === 2 ? [p[0] * 60 + p[1], p[0] * 3600 + p[1] * 60] : [p[0] * 3600 + p[1] * 60 + p[2]];
    return cands.find((sec) => sec / km >= MIN_PACE && sec / km <= MAX_PACE) || null;
  }

  // ---------------------------------------------------------------- targets per distance and level
  const TARGET = {
    5: { peakLong: { beginner: 5, intermediate: 7, advanced: 10 }, minLong: 4, peakWeekly: { beginner: 15, intermediate: 25, advanced: 40 } },
    10: { peakLong: { beginner: 8, intermediate: 11, advanced: 14 }, minLong: 7, peakWeekly: { beginner: 20, intermediate: 32, advanced: 50 } },
    21.1: { peakLong: { beginner: 15, intermediate: 18, advanced: 20 }, minLong: 13, peakWeekly: { beginner: 28, intermediate: 40, advanced: 60 } },
    42.2: { peakLong: { beginner: 28, intermediate: 30, advanced: 32 }, minLong: 24, peakWeekly: { beginner: 45, intermediate: 55, advanced: 75 } },
  };
  const LEVEL_NAME = { beginner: 'مبتدئ', intermediate: 'متوسط', advanced: 'متقدم' };
  function levelOf(inp) {
    const w = +inp.weeklyKm || 0, L = +inp.longestKm || 0, r = +inp.runsPerWeek || 0;
    if (r < 2 || w < 10 || L < 5) return 'beginner';
    if (w < 30 || L < 12) return 'intermediate';
    return 'advanced';
  }

  // ---------------------------------------------------------------- equipment
  // input.env = { where: 'outdoor'|'treadmill'|'track'|'mixed', gps: bool, kit: ['dumbbells','gym','rower','skierg','sled','wallball','sandbag'] }
  const has = (env, k) => !!(env && env.kit && env.kit.includes(k)) || (k === 'treadmill' && env && (env.where === 'treadmill' || env.where === 'mixed')) || (k === 'dumbbells' && env && env.kit && env.kit.includes('gym'));
  const EFFORT = {
    easy: 'سهل: تقدر تتكلم جمل كاملة', long: 'سهل: تقدر تتكلم جمل كاملة', marathon: 'ثابت ومريح: تقدر تتكلم جمل قصيرة',
    tempo: 'صعب بس متحكم فيه: تقدر تقول كلمتين', interval: 'صعب: الكلام صعب', race: 'سرعة السباق', rep: 'سريع ومرتاح، مش سباق',
  };
  // fallback paces (sec/km) when we have no race time: used only to turn km into minutes
  const DEFAULT_EASY = { beginner: 465, intermediate: 405, advanced: 345 };
  const REL = { easy: 1, long: 1.02, marathon: 0.9, tempo: 0.85, interval: 0.79, rep: 0.75, race: 0.88 };

  function paceFor(ctx, key) {
    if (ctx.paces) return key === 'race' ? ctx.racePace : key === 'long' ? ctx.paces.easy * 1.02 : ctx.paces[key];
    return null;
  }
  function roughPace(ctx, key) { return paceFor(ctx, key) || DEFAULT_EASY[ctx.level] * (REL[key] || 1); }

  // one run segment, written for where and how the athlete runs
  function seg(ctx, km, key) {
    const env = ctx.env, p = paceFor(ctx, key);
    const kmTxt = km >= 1 ? `${round1(km)} كم` : `${Math.round(km * 1000)} م`;
    if (env.where === 'treadmill') {
      return p ? `${kmTxt} على المشاية بسرعة ${round1(3600 / p)} كم/س، ميل 1%` : `${kmTxt} على المشاية، ${EFFORT[key]}، ميل 1%`;
    }
    if (env.where === 'track' && km < 2) {
      const laps = (km * 1000) / 400;
      const lapTxt = laps === 1 ? 'لفة' : `${round1(laps)} لفة`;
      return p ? `${lapTxt} (${Math.round(km * 1000)} م) في ${fmtPace(p * km)}` : `${lapTxt} (${Math.round(km * 1000)} م)، ${EFFORT[key]}`;
    }
    if (!env.gps && env.where === 'outdoor') {
      const mins = Math.max(1, Math.round((roughPace(ctx, key) * km) / 60));
      return p ? `${mins} دقيقة بسرعة ${fmtPace(p)} /كم تقريبًا` : `${mins} دقيقة، ${EFFORT[key]}`;
    }
    return p ? `${kmTxt} بسرعة ${fmtPace(p)} /كم` : `${kmTxt}، ${EFFORT[key]}`;
  }
  const round1 = (x) => Math.round(x * 10) / 10;
  const roundHalf = (x) => Math.round(x * 2) / 2;

  // ---------------------------------------------------------------- strength library
  function strengthSession(ctx, light) {
    const sets = light ? 2 : 3;
    let moves;
    if (has(ctx.env, 'gym')) moves = [`سكوات بالبار أو ليج بريس ${sets} × 8`, `رفعة رومانية ${sets} × 8`, `ستيب أب ${sets} × 8 لكل رجل`, `رفع سمانة على الجهاز ${sets} × 15`, `بلانك ${sets} × 45 ثانية`];
    else if (has(ctx.env, 'dumbbells')) moves = [`جوبلت سكوات بدمبل ${sets} × 10`, `رفعة رومانية بالدمبل ${sets} × 10`, `ستيب أب على كرسي بدمبل ${sets} × 8 لكل رجل`, `رفع سمانة بدمبل ${sets} × 15`, `بلانك جانبي ${sets} × 30 ثانية لكل ناحية`];
    else moves = [`سكوات ${sets} × 15`, `لانجز ${sets} × 10 لكل رجل`, `رفع سمانة على رجل واحدة ${sets} × 15`, `جسر (Glute bridge) ${sets} × 15`, `بلانك ${sets} × 40 ثانية`];
    if (ctx.injury === 'knee') moves = moves.map((m) => m.replace(/لانجز[^]*/, `جسر على رجل واحدة ${sets} × 10 لكل رجل`));
    return moves;
  }

  // ---------------------------------------------------------------- HYROX stations, with substitutes
  const STATIONS = [
    { id: 'ski', name: 'SkiErg', race: '1000 م', kit: 'skierg', work: (r) => `SkiErg ${r * 250} م`, subs: [{ kit: 'rower', text: (r) => `تجديف ${r * 250} م (بدل SkiErg)` }, { kit: null, text: () => 'أستك أو حبل: سحب لتحت بدراع مفرود 4 × 40 ثانية (بدل SkiErg)' }] },
    { id: 'push', name: 'Sled Push', race: '50 م', kit: 'sled', work: (r) => `Sled Push ${r} × 12.5 م تقيل`, subs: [{ kit: 'treadmill', text: () => 'زق المشاية وهي مقفولة 4 × 20 ثانية (بدل Sled Push)' }, { kit: null, text: () => 'زق الحيطة بكل قوتك 4 × 20 ثانية + لانجز ماشي 4 × 10 م (بدل Sled Push)' }] },
    { id: 'pull', name: 'Sled Pull', race: '50 م', kit: 'sled', work: (r) => `Sled Pull ${r} × 12.5 م`, subs: [{ kit: 'dumbbells', text: () => 'تجديف بدمبل تقيل 4 × 10 لكل إيد + مشي لورا 4 × 20 م (بدل Sled Pull)' }, { kit: null, text: () => 'حبل أو أستك مربوط: سحب وانت ماشي لورا 4 × 20 م (بدل Sled Pull)' }] },
    { id: 'bbj', name: 'Burpee Broad Jumps', race: '80 م', kit: null, work: (r) => `Burpee Broad Jumps ${r * 20} م` },
    { id: 'row', name: 'Rowing', race: '1000 م', kit: 'rower', work: (r) => `تجديف ${r * 250} م`, subs: [{ kit: 'skierg', text: (r) => `SkiErg ${r * 250} م (بدل التجديف)` }, { kit: 'dumbbells', text: () => 'سوينج بالكيتل أو الدمبل 4 × 20 (بدل التجديف)' }, { kit: null, text: () => 'بيربي 4 × 10 + سكوات 4 × 20 (بدل التجديف)' }] },
    { id: 'farm', name: 'Farmers Carry', race: '200 م', kit: 'dumbbells', work: (r, sex) => `Farmers Carry ${r * 50} م بـ ${sex === 'f' ? '2 × 16' : '2 × 24'} كجم`, subs: [{ kit: null, text: (r) => `شيل شنطتين مليانين أزايز مية وامشي ${r * 50} م (بدل Farmers Carry)` }] },
    { id: 'lunge', name: 'Sandbag Lunges', race: '100 م', kit: 'sandbag', work: (r, sex) => `Sandbag Lunges ${r * 25} م بـ ${sex === 'f' ? '10' : '20'} كجم`, subs: [{ kit: null, text: (r) => `لانجز ماشي بشنطة ضهر فيها كتب أو أزايز ${r * 25} م (بدل Sandbag Lunges)` }] },
    { id: 'wb', name: 'Wall Balls', race: '100 رمية', kit: 'wallball', work: (r, sex) => `Wall Balls ${r * 25} رمية بكورة ${sex === 'f' ? '4' : '6'} كجم`, subs: [{ kit: 'dumbbells', text: (r) => `Thrusters بالدمبل ${r * 15} عدة (بدل Wall Balls)` }, { kit: null, text: (r) => `سكوات + رمي شنطة رمل لفوق ${r * 20} عدة (بدل Wall Balls)` }] },
  ];
  function stationText(ctx, st, r) {
    if (!st.kit || has(ctx.env, st.kit)) return st.work(r, ctx.sex);
    const sub = st.subs.find((s) => s.kit === null || has(ctx.env, s.kit));
    return sub.text(r);
  }
  const missingStations = (ctx) => STATIONS.filter((s) => s.kit && !has(ctx.env, s.kit)).map((s) => s.name);

  // ---------------------------------------------------------------- workouts (each returns a day entry)
  const W = {
    easy(ctx, km, opts = {}) {
      if (ctx.runWalk) {
        const run = Math.min(2 + ctx.weekIdx, 6), sets = Math.max(4, Math.round((roughPace(ctx, 'easy') * km) / 60 / (run + 1)));
        return day('easy', 'جري ومشي', 1, km, [`إحماء: مشي سريع 5 دقايق`, `جري ${run} دقايق + مشي دقيقة، كرر ${sets} مرات`, 'جري الجزء ده سهل جدًا، المهم تكمّل.'], opts);
      }
      const steps = [seg(ctx, km, 'easy')];
      if (opts.strides) steps.push('في الآخر: 6 × 20 ثانية أسرع شوية، ومشي دقيقة بينهم');
      return day('easy', opts.strides ? 'جري سهل + تسارعات' : 'جري سهل', 1, km, steps, opts);
    },
    long(ctx, km, opts = {}) {
      const steps = [];
      if (ctx.runWalk) {
        const run = Math.min(3 + ctx.weekIdx, 8), sets = Math.max(4, Math.round((roughPace(ctx, 'long') * km) / 60 / (run + 1)));
        steps.push(`جري ${run} دقايق + مشي دقيقة، كرر ${sets} مرات`);
      } else if (opts.racePaceKm) {
        steps.push(seg(ctx, km - opts.racePaceKm, 'long'), `آخر ${opts.racePaceKm} كم بسرعة السباق: ${seg(ctx, opts.racePaceKm, 'race')}`);
      } else steps.push(seg(ctx, km, 'long'));
      if (km >= 14) steps.push('خد مية معاك، ولو الجري أكتر من ساعة جرّب جل أو تمر كل 40 دقيقة زي يوم السباق.');
      return day('long', 'الجري الطويل', 2, km, steps, opts);
    },
    strides(ctx, km) {
      return W.easy(ctx, km, { strides: true });
    },
    tempo(ctx, mins) {
      const tp = paceFor(ctx, 'tempo') || roughPace(ctx, 'tempo');
      const km = round1((mins * 60) / tp);
      return day('quality', 'تيمبو', 3, round1(km + 3.5), [`إحماء: ${seg(ctx, 2, 'easy')}`, `${mins} دقيقة تيمبو: ${seg(ctx, km, 'tempo')}`, `تهدئة: ${seg(ctx, 1.5, 'easy')}`]);
    },
    cruise(ctx, reps, km) {
      return day('quality', 'تيمبو متقطع', 3, round1(reps * km + 3.5), [`إحماء: ${seg(ctx, 2, 'easy')}`, `${reps} × (${seg(ctx, km, 'tempo')})، وراحة دقيقة جري خفيف`, `تهدئة: ${seg(ctx, 1.5, 'easy')}`]);
    },
    intervals(ctx, reps, km, restMin) {
      return day('quality', 'إنترفال', 4, round1(reps * km + 3.5), [`إحماء: ${seg(ctx, 2, 'easy')} + 4 تسارعات قصيرة`, `${reps} × (${seg(ctx, km, 'interval')})، وراحة ${restMin} دقيقة جري خفيف أو مشي`, `تهدئة: ${seg(ctx, 1.5, 'easy')}`]);
    },
    hills(ctx, reps) {
      const work = ctx.env.where === 'treadmill' ? `${reps} × 60 ثانية جري على ميل 5% بمجهود صعب، ونزّل الميل وامشي 90 ثانية بينهم` : `${reps} × 60 ثانية طلوع على طلعة أو كوبري بمجهود صعب، وانزل ماشي`;
      return day('quality', 'طلعات', 3, round1(3.5 + reps * 0.25), [`إحماء: ${seg(ctx, 2, 'easy')}`, work, `تهدئة: ${seg(ctx, 1.5, 'easy')}`]);
    },
    sharpener(ctx) {
      if (ctx.runWalk || ctx.level === 'beginner') return W.easy(ctx, 3, { strides: true });
      return day('quality', 'تنشيط قبل السباق', 2, 6, [`إحماء: ${seg(ctx, 2, 'easy')}`, `3 × (${seg(ctx, 1, 'race')})، وراحة دقيقتين`, `تهدئة: ${seg(ctx, 1, 'easy')}`, 'خفيف ومريح. الهدف إن رجلك تفتكر سرعة السباق، مش إنك تتعب.']);
    },
    shakeout(ctx) {
      return day('easy', 'جري خفيف جدًا', 1, 2.5, [seg(ctx, 2.5, 'easy'), 'جهّز لبسك ورقمك والأكل اللي هتاكله الصبح من النهارده.']);
    },
    // HYROX
    compromised(ctx, rounds, raceEffort) {
      const order = STATIONS.slice(0, rounds);
      const steps = [`إحماء: ${seg(ctx, 1.5, 'easy')}`];
      order.forEach((st, i) => steps.push(`${i + 1}. ${seg(ctx, 1, raceEffort ? 'race' : 'tempo')} ← ثم ${stationText(ctx, st, raceEffort ? 2 : 3)}`));
      steps.push('بعد كل محطة اطلع تجري على طول، ده أهم جزء في التمرين.');
      return day('quality', raceEffort ? 'محاكاة السباق' : 'جري + محطات', 4, rounds + 1.5, steps);
    },
    stations(ctx, sets) {
      const picks = ctx.weekIdx % 2 === 0 ? ['push', 'pull', 'farm', 'wb'] : ['ski', 'row', 'lunge', 'bbj'];
      const steps = picks.map((id) => `${stationText(ctx, STATIONS.find((s) => s.id === id), sets)}`);
      steps.unshift(`${sets} جولات، راحة دقيقتين بين كل جولة:`);
      steps.push(...strengthSession(ctx, sets < 3).slice(0, 2).map((m) => `قوة: ${m}`));
      return day('strength', 'محطات وقوة', 3, 0, steps);
    },
    hyroxIntervals(ctx, reps) {
      return day('quality', 'إنترفال كيلومترات', 4, reps + 3.5, [`إحماء: ${seg(ctx, 2, 'easy')}`, `${reps} × (${seg(ctx, 1, 'tempo')})، وراحة 90 ثانية`, `تهدئة: ${seg(ctx, 1.5, 'easy')}`, 'دي نفس سرعة الكيلوهات اللي هتجريها في السباق.']);
    },
  };
  function day(kind, title, intensity, km, steps, opts = {}) {
    return { kind, title, intensity, km: round1(km), steps, extra: opts.extra || null };
  }

  // ---------------------------------------------------------------- weekly layout
  // returns role per Egyptian-week position for the chosen days
  function layout(daysPos, nQuality) {
    const pos = [...daysPos].sort((a, b) => a - b);
    const roles = {};
    const dist = (a, b) => Math.min(Math.abs(a - b), 7 - Math.abs(a - b));
    let long = pos.includes(6) ? 6 : pos.includes(0) ? 0 : pos[pos.length - 1];
    roles[long] = 'long';
    const picked = [long];
    for (let q = 0; q < nQuality; q++) {
      const cand = pos.filter((p) => !picked.includes(p)).map((p) => ({ p, d: Math.min(...picked.map((x) => dist(p, x))) })).sort((a, b) => b.d - a.d || a.p - b.p);
      if (!cand.length) break;
      if (q > 0 && cand[0].d < 2) break; // second hard day only with a gap
      roles[cand[0].p] = q === 0 ? 'q1' : 'q2';
      picked.push(cand[0].p);
    }
    pos.forEach((p) => { if (!roles[p]) roles[p] = 'easy'; });
    return roles;
  }

  // ---------------------------------------------------------------- main generator
  function generate(raw) {
    const input = normalise(raw);
    const out = { input, status: 'ok', messages: [], warnings: [], weeks: [], alternatives: [] };

    const scr = screen(input.health);
    if (!scr.ok && !input.doctorCleared) {
      out.status = 'blocked';
      out.blockKind = 'health';
      out.messages.push('قبل ما نبدأ، لازم تكشف وتاخد موافقة دكتور على التمرين. لما الدكتور يوافق، علّم «الدكتور وافق» وهنعملك الخطة.');
      return out;
    }
    if (input.pain === 'now') {
      out.status = 'blocked';
      out.blockKind = 'pain';
      out.messages.push('عندك وجع دلوقتي. الخطة مش هتبدأ غير لما تكشف ويقولك تقدر تجري.');
      return out;
    }
    if (input.age < 18) {
      out.status = 'blocked';
      out.blockKind = 'age';
      out.messages.push('سبق دلوقتي للي سنهم 18 سنة وأكبر.');
      return out;
    }

    const level = levelOf(input);
    const ctx = { env: input.env, level, sex: input.sex, injury: input.injury, weekIdx: 0 };
    out.level = level;
    out.levelName = LEVEL_NAME[level];

    // paces
    const rt = parseDuration(input.recentTime, +input.recentKm);
    if (input.recentTime && String(input.recentTime).trim() && !rt) out.warnings.push(`الوقت «${input.recentTime}» مش منطقي لـ ${input.recentKm} كم، فمشيناها بالإحساس. اكتبه دقايق:ثواني، زي 28:00.`);
    if (rt && input.recentKm) {
      out.timeRead = `فهمنا آخر وقت ليك: ${fmtTime(rt)} في ${input.recentKm} كم (${fmtPace(rt / input.recentKm)} /كم).`;
      const vdot = vdotFrom(+input.recentKm, rt);
      ctx.vdot = vdot;
      ctx.paces = paceTable(vdot);
      const raceKm = input.raceType === 'hyrox' ? 1 : input.distanceKm;
      ctx.predicted = input.raceType === 'hyrox' ? null : predictTime(vdot, raceKm);
      ctx.racePace = input.raceType === 'hyrox' ? ctx.paces.tempo * 1.03 : ctx.predicted / raceKm;
      const goal = parseDuration(input.goalTime, raceKm);
      if (input.goal === 'time' && input.goalTime && !goal && input.raceType !== 'hyrox') out.warnings.push(`الهدف «${input.goalTime}» مش منطقي لـ ${raceKm} كم، فالخطة معمولة على سرعتك المتوقعة. اكتبه ساعات:دقايق:ثواني، زي 2:05:00.`);
      if (input.goal === 'time' && goal && input.raceType !== 'hyrox') {
        const weeksLeft = Math.ceil(diffDays(input.startDate, input.raceDate) / 7);
        const allowed = Math.min(0.01 * weeksLeft, 0.05);
        const vGoal = vdotFrom(raceKm, goal);
        if (vGoal <= vdot * (1 + allowed)) {
          ctx.racePace = goal / raceKm;
          out.goalVerdict = { ok: true, text: `هدفك ${fmtTime(goal)} واقعي.` };
        } else {
          const realistic = predictTime(vdot * (1 + allowed), raceKm);
          ctx.racePace = realistic / raceKm;
          out.goalVerdict = { ok: false, text: `هدفك ${fmtTime(goal)} صعب في الوقت ده. الأقرب للواقع حوالي ${fmtTime(realistic)}، فالخطة معمولة عليه.` };
        }
      }
      out.paces = {
        easy: `${fmtPace(ctx.paces.easyFast)}–${fmtPace(ctx.paces.easySlow)}`, tempo: fmtPace(ctx.paces.tempo), interval: fmtPace(ctx.paces.interval), race: fmtPace(ctx.racePace),
        predicted: ctx.predicted ? fmtTime(ctx.predicted) : null,
      };
    } else {
      out.warnings.push('معندناش وقت حديث ليك، فالسرعات مكتوبة بالإحساس. بعد أول أسبوع اجري 5 كم بأحسن مجهود وسجّل الوقت، والخطة هتتظبط بالأرقام.');
    }

    // dates and weeks
    const totalDays = diffDays(input.startDate, input.raceDate);
    if (totalDays < 3) { out.status = 'blocked'; out.blockKind = 'date'; out.messages.push('السباق قريب جدًا على خطة. ارتاح، ونام كويس، واجري على راحتك.'); return out; }
    let start = input.startDate;
    // weeks are aligned to race day: the last week is the 7 days that end on race day
    let N = Math.ceil((totalDays + 1) / 7);
    if (N > 16) {
      N = 16;
      start = addDays(input.raceDate, -16 * 7 + 1);
      out.messages.push(`السباق لسه بعيد. الخطة هتبدأ يوم ${start}، ولحد ساعتها كمّل جري سهل 3 مرات في الأسبوع.`);
    }
    const weekStart = (i) => addDays(input.raceDate, -6 - 7 * (N - 1 - i));

    if (input.raceType === 'hyrox') return buildHyrox(input, ctx, out, N, weekStart, start);
    return buildRun(input, ctx, out, N, weekStart, start);
  }

  function normalise(raw) {
    const r = Object.assign({}, raw);
    r.age = +r.age || 30;
    r.weeklyKm = Math.max(0, +r.weeklyKm || 0);
    r.longestKm = Math.max(0, +r.longestKm || 0);
    r.runsPerWeek = Math.max(0, +r.runsPerWeek || 0);
    r.distanceKm = +r.distanceKm || 21.1;
    r.days = (r.days || [6, 1, 3, 5]).map(Number);
    r.env = Object.assign({ where: 'outdoor', gps: true, kit: [] }, r.env || {});
    r.weightKg = +r.weightKg || null;
    r.flags = Object.assign({}, r.flags || {});
    return r;
  }

  function progressionRate(input) {
    let p = 1.1;
    if (input.age >= 50 || (input.injury && input.injury !== 'none')) p = 1.07;
    return p;
  }

  // ---------------------------------------------------------------- running plans
  function buildRun(input, ctx, out, N, weekStart, start) {
    const D = input.distanceKm, T = TARGET[D];
    const lvl = ctx.level;
    ctx.runWalk = lvl === 'beginner' && (input.weeklyKm < 10 || input.longestKm < 4);
    // the last week is always race week: very short plans drop the taper first, then the build weeks
    const taper = Math.max(0, Math.min(D === 42.2 ? (N >= 8 ? 2 : 1) : D === 21.1 && N >= 6 ? 1 : 0, N - 2));
    const buildWeeks = N - 1 - taper;
    const p = progressionRate(input);
    const longStep = lvl === 'beginner' ? 1.5 : 2;
    const daysCount = input.days.length;
    const longShare = daysCount <= 3 ? 0.5 : daysCount >= 5 ? 0.38 : 0.45;
    const nQuality = ctx.runWalk ? 0 : lvl === 'advanced' && daysCount >= 5 && !(input.age >= 50) ? 2 : 1;

    // simulate weekly volume and long run
    const floor = { beginner: 8, intermediate: 15, advanced: 25 }[lvl];
    let weekly = Math.max(input.weeklyKm, Math.min(floor, input.weeklyKm * 1.1 + 4));
    let long = Math.max(ctx.runWalk ? 3 : 4, input.longestKm);
    const plan = [];
    let peakWeekly = 0, peakLong = 0;
    for (let i = 0; i < buildWeeks; i++) {
      const cutback = N >= 7 && i > 0 && i < buildWeeks - 1 && (i + 1) % 4 === 0;
      if (i > 0 && !cutback && !(i === 1 && input.flags.noIncreaseFirstWeek)) {
        weekly = Math.min(weekly * p, T.peakWeekly[lvl]);
        long = Math.min(long + longStep, T.peakLong[lvl], D === 42.2 ? 32 : D);
      }
      if (i === 0 && input.flags.progressNow) { weekly = Math.min(weekly * p, T.peakWeekly[lvl]); long = Math.min(long + longStep, T.peakLong[lvl], D === 42.2 ? 32 : D); }
      const wk = cutback ? weekly * 0.8 : weekly;
      const lg = cutback ? long * 0.8 : Math.min(long, Math.max(wk * longShare, input.longestKm));
      plan.push({ phase: cutback ? 'cutback' : i === buildWeeks - 1 ? 'peak' : 'build', weekly: wk, long: lg });
      if (!cutback) { peakWeekly = Math.max(peakWeekly, wk); peakLong = Math.max(peakLong, lg); }
    }
    if (buildWeeks === 0) { // race this week: judge it on current fitness
      peakWeekly = weekly;
      peakLong = Math.min(long, Math.max(weekly * longShare, input.longestKm));
    }
    // taper weeks
    for (let t = 0; t < taper; t++) {
      const f = taper === 2 ? [0.8, 0.6][t] : 0.8;
      plan.push({ phase: 'taper', weekly: peakWeekly * f, long: peakLong * (taper === 2 ? [0.75, 0.55][t] : 0.7) });
    }
    plan.push({ phase: 'race', weekly: peakWeekly * (D >= 21.1 ? 0.45 : 0.6), long: 0 });

    // feasibility
    const minLong = T.minLong;
    out.peakLong = round1(peakLong);
    out.peakWeekly = Math.round(peakWeekly);
    if (D === 42.2 && N < 8 && input.longestKm < 24) out.status = 'blocked';
    else if (lvl === 'beginner' && D >= 21.1 && N < 8) out.status = 'blocked';
    else if (peakLong >= minLong) out.status = 'ok';
    else if (peakLong >= minLong * 0.8) out.status = 'risky';
    else out.status = 'blocked';

    if (out.status !== 'ok') {
      // alternatives: shorter distances that fit, or weeks needed
      [5, 10, 21.1].filter((d) => d < D).forEach((d) => { if (peakLong >= TARGET[d].minLong) out.alternatives.push({ kind: 'distance', distanceKm: d, text: `ادخل ${DIST_NAME[d]} في نفس السباق` }); });
      const weeksNeeded = Math.ceil(Math.max(0, minLong - Math.max(4, input.longestKm)) / longStep) + 2 + taper;
      out.alternatives.push({ kind: 'later', weeks: weeksNeeded, text: `أو اختار سباق ${DIST_NAME[D]} بعد ${weeksNeeded} أسبوع على الأقل` });
    }
    if (out.status === 'blocked' && input.flags.continuing) {
      out.status = 'risky';
      out.messages.push(`بعد الأسبوع اللي فات، أطول جري هتوصله حوالي ${round1(peakLong)} كم قبل السباق. خلي هدفك إنك تخلّص وبس، أو انقل لمسافة أقصر.`);
    }
    if (out.status === 'blocked') {
      out.blockKind = 'feasibility';
      out.messages.push(`مش هننصحك تجري ${DIST_NAME[D]} في ${N} أسابيع من مستواك الحالي. أطول جري هتوصله حوالي ${round1(peakLong)} كم، والأمان إنك توصل ${minLong} كم على الأقل قبل السباق.`);
      return out;
    }
    if (out.status === 'risky' && out.goalVerdict && out.goalVerdict.ok) out.goalVerdict.text = `سرعتك تسمح بهدف ${out.goalVerdict.text.match(/[0-9:]+/)[0]}، بس المسافة هي المشكلة مش السرعة. خلي الوقت هدف إضافي، والأهم إنك تخلّص سليم.`;
    if (out.status === 'risky' && !input.flags.continuing) out.messages.push(`ينفع، بس هيبقى صعب: أطول جري هيوصل حوالي ${round1(peakLong)} كم. خلي هدفك إنك تخلّص، ومتجريش بسرعة.`);
    if (ctx.runWalk) out.messages.push('هنبدأ بجري ومشي بالتبادل. ده مش ضعف: ده أأمن طريقة توصل بيها خط النهاية من غير إصابة.');

    // weeks
    for (let i = 0; i < N; i++) {
      ctx.weekIdx = i;
      const spec = plan[i];
      const ws = weekStart(i);
      const days = [];
      const roles = layout(input.days.map(Number).map(egPos), spec.phase === 'race' ? 0 : nQuality);
      for (let d = 0; d < 7; d++) {
        const date = addDays(ws, d);
        days.push({ date, dayName: DAY_NAMES[weekday(date)], role: roles[egPos(weekday(date))] || 'rest', workout: null });
      }
      // drop days outside the plan window
      days.forEach((x) => { if (x.date < start || x.date > input.raceDate) x.role = 'off'; });
      if (input.flags.restUntil) days.forEach((x) => { if (x.date <= input.flags.restUntil && x.role !== 'off') x.role = 'rest-sick'; });

      if (spec.phase === 'race') fillRaceWeek(input, ctx, days, spec);
      else fillRunWeek(input, ctx, days, spec, i, N, D, nQuality);
      const km = days.reduce((a, x) => a + (x.workout && x.workout.kind !== 'race' ? x.workout.km : 0), 0);
      out.weeks.push({ index: i, start: ws, phase: spec.phase, phaseName: PHASE_NAME[spec.phase], targetKm: Math.round(spec.weekly), km: round1(km), days });
    }
    out.raceDayTips = raceDayTips(input, ctx);
    return out;
  }

  const PHASE_NAME = { build: 'بناء', peak: 'أعلى أسبوع', cutback: 'أسبوع أخف', taper: 'تخفيف قبل السباق', race: 'أسبوع السباق' };

  function fillRunWeek(input, ctx, days, spec, i, N, D, nQuality) {
    const active = days.filter((x) => ['long', 'q1', 'q2', 'easy'].includes(x.role));
    if (!active.length) return;
    const lvl = ctx.level;
    const easyOnly = input.flags.easyOnlyUntil;
    // a partial first week (or sick days) gets a share of the volume
    const weekly = spec.weekly * Math.min(1, active.length / Math.max(1, input.days.length));
    // the hard part of a quality session is about 18% of the week
    const budget = Math.max(2.5, weekly * (nQuality === 2 ? 0.15 : 0.18));
    const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
    const tempoMins = () => clamp(Math.round((budget * (paceFor(ctx, 'tempo') || roughPace(ctx, 'tempo'))) / 60 / 5) * 5, 10, 40);
    let qualityKm = 0;
    const quality = (role) => {
      if (spec.phase === 'cutback' || spec.phase === 'taper') {
        if (role === 'q2') return null;
        return D >= 21.1 ? W.tempo(ctx, Math.max(10, tempoMins() - 5)) : W.intervals(ctx, 4, D === 5 ? 0.4 : 0.8, 2);
      }
      if (input.injury === 'knee' && role === 'q1' && i % 3 === 0) return W.tempo(ctx, tempoMins());
      if (role === 'q2') return W.intervals(ctx, clamp(Math.round(weekly * 0.1), 3, 6), 1, 2);
      if (D <= 10) {
        const rot = i % 3;
        if (rot === 0 && lvl !== 'advanced') return W.hills(ctx, clamp(6 + i, 6, 10));
        const rk = D === 5 ? 0.4 : 0.8;
        if (rot === 1 || rot === 0) return W.intervals(ctx, clamp(Math.round(budget / rk), 4, 10), rk, D === 5 ? 1.5 : 2);
        return W.tempo(ctx, tempoMins());
      }
      if (i % 2 === 0) return W.tempo(ctx, tempoMins());
      return W.cruise(ctx, clamp(Math.round(budget / 1.6), 2, 6), 1.6);
    };
    // quality days first
    active.forEach((x) => {
      if (x.role === 'q1' || x.role === 'q2') {
        const w = easyOnly && x.date <= easyOnly ? null : quality(x.role);
        if (w) { x.workout = w; qualityKm += w.km; } else x.role = 'easy';
      }
    });
    const longDay = active.find((x) => x.role === 'long');
    let longKm = roundHalf(spec.long);
    if (longDay && easyOnly && longDay.date <= easyOnly) longKm = roundHalf(longKm * 0.7);
    if (longDay) {
      const rp = !ctx.runWalk && lvl !== 'beginner' && spec.phase === 'build' && i > 0 && i % 2 === 1 && D >= 10 && !(easyOnly && longDay.date <= easyOnly) ? Math.min(Math.round(longKm * 0.25), 5) : 0;
      longDay.workout = W.long(ctx, longKm, { racePaceKm: rp });
    } else longKm = 0;
    const easyDays = active.filter((x) => x.role === 'easy');
    const minEasy = ctx.runWalk ? 2.5 : 3;
    const share = easyDays.length ? Math.max(minEasy, Math.min(12, (weekly - longKm - qualityKm) / easyDays.length)) : 0;
    // strength: on up to 2 easy days that are not the day before the long run
    const longIdx = longDay ? days.indexOf(longDay) : -1;
    let strengthLeft = spec.phase === 'taper' || spec.phase === 'cutback' ? 1 : 2;
    easyDays.forEach((x, k) => {
      const strides = !ctx.runWalk && k === 0 && spec.phase !== 'cutback';
      x.workout = W.easy(ctx, roundHalf(share), { strides });
      const idx = days.indexOf(x);
      if (strengthLeft > 0 && idx !== longIdx - 1) { x.workout.extra = { title: 'قوة 20 دقيقة بعد الجري', steps: strengthSession(ctx, spec.phase !== 'build' && spec.phase !== 'peak') }; strengthLeft--; }
    });
    days.forEach((x) => {
      if (x.role === 'rest-sick') x.workout = day('rest', 'راحة لحد ما تخف', 0, 0, ['متجريش. نام كويس واشرب مية كتير.']);
    });
  }

  function fillRaceWeek(input, ctx, days, spec) {
    const raceIdx = days.findIndex((x) => x.date === input.raceDate);
    days.forEach((x, idx) => {
      if (idx > raceIdx || x.role === 'off') { x.role = 'off'; return; }
      if (idx === raceIdx) {
        x.role = 'race';
        x.workout = day('race', input.raceType === 'hyrox' ? input.raceName : `${input.raceName}: ${DIST_NAME[input.distanceKm]}`, 5, input.raceType === 'hyrox' ? 8 : input.distanceKm, []);
        return;
      }
      if (x.role === 'rest' || x.role === 'rest-sick') return;
      const before = raceIdx - idx;
      if (before === 1) { x.role = 'rest'; x.workout = day('rest', 'راحة', 0, 0, ['راحة كاملة. كُل أكل فيه نشويات كويس، ونام بدري.']); return; }
      x.role = before >= 3 && before <= 4 && !days.some((y) => y.workout && (y.workout.title === 'تنشيط قبل السباق' || y.workout.title === 'محاكاة السباق')) ? 'q1' : 'easy';
      if (input.raceType === 'hyrox') {
        x.workout = x.role === 'q1' ? W.compromised(ctx, 3, true) : W.easy(ctx, 3, { strides: before === 2 });
      } else x.workout = x.role === 'q1' ? W.sharpener(ctx) : before === 2 ? W.shakeout(ctx) : W.easy(ctx, roundHalf(Math.max(3, spec.weekly / 4)));
    });
    // race day itself is always on the plan
    if (raceIdx < 0) return;
    days[raceIdx].workout.steps = raceDayTips(input, ctx).steps;
  }

  function raceDayTips(input, ctx) {
    const steps = [];
    if (input.raceType === 'hyrox') {
      steps.push(ctx.paces ? `اجري الكيلوهات بسرعة حوالي ${fmtPace(ctx.racePace)} /كم، وأول كيلو أبطأ شوية.` : 'أول كيلو أبطأ من إحساسك. السباق طويل.');
      steps.push('في المحطات: نفس ثابت، ومتقفش غير لو لازم.');
      steps.push('أوزان فئة Open: كورة 6 كجم للرجالة و4 للستات، Farmers 2 × 24 و2 × 16، الشنطة 20 و10. اتأكد من القواعد الرسمية للسباق.');
    } else {
      steps.push(ctx.racePace ? `سرعتك في السباق: ${fmtPace(ctx.racePace)} /كم. أول 2 كم أبطأ 10 ثواني في الكيلو.` : 'ابدأ أبطأ من إحساسك في أول 2 كم، وبعدين ثبّت.');
      if (input.distanceKm >= 21.1) steps.push('اشرب مية في كل محطة، ولو هتجري أكتر من ساعة خد جل أو تمر كل 40 دقيقة.');
    }
    if (input.weightKg) steps.push(`فطار قبل السباق بـ 2–3 ساعات: حوالي ${Math.round(input.weightKg)}–${Math.round(input.weightKg * 2)} جرام نشويات (عيش، شوفان، موز)، وأكل اتعودت عليه.`);
    else steps.push('فطار خفيف اتعودت عليه قبل السباق بـ 2–3 ساعات: عيش أو شوفان وموز.');
    steps.push('متجربش أي حاجة جديدة يوم السباق: لا جزمة، ولا لبس، ولا أكل.');
    return { steps };
  }

  // ---------------------------------------------------------------- HYROX plans
  function buildHyrox(input, ctx, out, N, weekStart, start) {
    ctx.runWalk = false;
    const lvl = ctx.level;
    out.peakLong = null;
    if (input.longestKm < 5) {
      out.status = 'risky';
      out.messages.push('السباق فيه 8 كم جري بين المحطات. لو مش بتقدر تجري 5 كم ورا بعض، ادخل Doubles أو Relay، أو امشي جزء من الكيلوهات.');
    }
    const miss = missingStations(ctx);
    if (miss.length) out.warnings.push(`مش عندك: ${miss.join('، ')}. حطينا تمارين بديلة، وحاول تتمرن على الأجهزة الحقيقية مرتين على الأقل قبل السباق.`);
    const daysCount = input.days.length;
    const plan = [];
    for (let i = 0; i < N - 1; i++) plan.push({ phase: N >= 7 && i > 0 && i < N - 2 && (i + 1) % 4 === 0 ? 'cutback' : i === N - 2 ? 'peak' : 'build' });
    plan.push({ phase: 'race' });
    for (let i = 0; i < N; i++) {
      ctx.weekIdx = i;
      const spec = plan[i];
      const ws = weekStart(i);
      const days = [];
      const pos = input.days.map(Number).map(egPos).sort((a, b) => a - b);
      // HYROX roles: compromised on the long-run day, stations far from it, intervals in between
      const r = layout(pos, Math.min(2, daysCount - 1));
      const roleMap = { long: 'comp', q1: 'stations', q2: 'hint', easy: 'easy' };
      if (daysCount >= 3 && !pos.some((x) => r[x] === 'q2')) { const e = pos.find((x) => r[x] === 'easy'); if (e !== undefined) r[e] = 'q2'; }
      for (let d = 0; d < 7; d++) { const date = addDays(ws, d); const ep = egPos(weekday(date)); days.push({ date, dayName: DAY_NAMES[weekday(date)], role: r[ep] ? roleMap[r[ep]] : 'rest', workout: null }); }
      days.forEach((x) => { if (x.date < start || x.date > input.raceDate) x.role = 'off'; });
      if (input.flags.restUntil) days.forEach((x) => { if (x.date <= input.flags.restUntil && x.role !== 'off') x.role = 'rest-sick'; });

      if (spec.phase === 'race') {
        fillRaceWeek(input, ctx, days, { weekly: 12 });
      } else {
        const light = spec.phase === 'cutback';
        const rounds = light ? 3 : Math.min(3 + i, lvl === 'beginner' ? 5 : 7, 8);
        const easyOnly = input.flags.easyOnlyUntil;
        days.forEach((x) => {
          const blocked = easyOnly && x.date <= easyOnly;
          if (x.role === 'comp') x.workout = blocked ? W.easy(ctx, 4) : W.compromised(ctx, rounds, false);
          else if (x.role === 'stations') x.workout = blocked ? W.easy(ctx, 4) : W.stations(ctx, light ? 2 : lvl === 'beginner' ? 3 : 4);
          else if (x.role === 'hint') x.workout = blocked ? W.easy(ctx, 4) : W.hyroxIntervals(ctx, light ? 4 : Math.min(4 + i, 8));
          else if (x.role === 'easy') x.workout = W.easy(ctx, roundHalf(lvl === 'beginner' ? 4 : 6), { strides: true });
          else if (x.role === 'rest-sick') x.workout = day('rest', 'راحة لحد ما تخف', 0, 0, ['متتمرنش. نام كويس واشرب مية كتير.']);
        });
      }
      const km = days.reduce((a, x) => a + (x.workout && x.workout.kind !== 'race' ? x.workout.km : 0), 0);
      out.weeks.push({ index: i, start: ws, phase: spec.phase, phaseName: PHASE_NAME[spec.phase], targetKm: null, km: round1(km), days });
    }
    out.raceDayTips = raceDayTips(input, ctx);
    return out;
  }

  // ---------------------------------------------------------------- weekly check-in -> next input
  // feedback = { done: n, planned: n, feel: 'easy'|'ok'|'hard', pain: 'none'|'mild'|'sharp', sick: 'none'|'head'|'chest', sickDays: n, newTime: 'mm:ss' }
  function checkIn(rawInput, plan, weekIndex, fb) {
    const input = normalise(rawInput);
    const wk = plan.weeks[weekIndex];
    const next = Object.assign({}, input, { flags: { continuing: true } });
    const messages = [];
    const nextStart = addDays(wk.start, 7);
    next.startDate = nextStart > input.startDate ? nextStart : input.startDate;
    const planned = wk.days.filter((d) => d.workout && d.workout.kind !== 'rest').length || 1;
    const ratio = Math.max(0, Math.min(1, (fb.done || 0) / planned));
    const kmDone = wk.km * ratio;
    const longPlanned = Math.max(0, ...wk.days.filter((d) => d.workout && d.workout.kind === 'long').map((d) => d.workout.km));
    const longDone = fb.longDone ? longPlanned : 0;
    let action = 'continue';

    if (fb.pain === 'sharp') {
      action = 'paused';
      messages.push('الوجع اللي بيزيد مع الجري أو بيغيّر طريقة جريك ممكن يبقى إصابة. وقّف الجري واكشف عند دكتور أو أخصائي علاج طبيعي.');
      messages.push('الخطة واقفة لحد ما تقول إن الدكتور سمحلك. لما ترجع، هنبدأ أخف من الأول.');
      next.pain = 'now';
      next.injury = next.injury && next.injury !== 'none' ? next.injury : 'other';
      next.weeklyKm = Math.round(kmDone * 0.7);
      return { action, messages, input: next };
    }

    // fitness does not vanish in one week: base the next week on at least 75% of what was planned
    next.weeklyKm = Math.round(wk.km * Math.max(ratio, 0.75));
    next.longestKm = longDone || Math.round(input.longestKm * (ratio < 0.5 ? 0.9 : 1) * 10) / 10;
    next.runsPerWeek = input.runsPerWeek; // one missed week does not change the athlete's level

    if (fb.sick === 'chest') {
      const restDays = (fb.sickDays || 3) + 2;
      next.flags.restUntil = addDays(next.startDate, restDays - 1);
      next.flags.easyOnlyUntil = addDays(next.startDate, restDays + 6);
      next.weeklyKm = Math.round(next.weeklyKm * (restDays > 7 ? 0.7 : 0.85));
      messages.push(`عندك حرارة أو كحة من الصدر أو تكسير: متجريش خالص. ريّح ${restDays} أيام (لحد ما تخف + يومين)، وبعدها أسبوع جري سهل بس قبل أي تمرين صعب.`);
      messages.push('لو الحرارة مكملة أكتر من 3 أيام، أو حسيت بوجع في صدرك أو ضيق نفس، اكشف.');
      action = 'sick';
    } else if (fb.sick === 'head') {
      next.flags.easyOnlyUntil = addDays(next.startDate, 2);
      next.flags.noIncreaseFirstWeek = true;
      messages.push('برد خفيف (رشح أو زور بس): ينفع تجري سهل لو حاسس إنك كويس، ولو تعبان ريّح. أول 3 أيام جري سهل بس.');
      action = 'sick';
    }
    if (fb.pain === 'mild') {
      next.flags.noIncreaseFirstWeek = true;
      messages.push('وجع خفيف بيروح بعد الإحماء: مش هنزوّد المسافة الأسبوع ده. لو زاد أو بقى بيوجعك وانت ماشي، علّم «وجع بيزيد» في التسجيل الجاي.');
    }
    if (ratio < 0.5) {
      next.flags.noIncreaseFirstWeek = true;
      messages.push('فوّت أكتر من نص التمارين: الأسبوع الجاي هيبقى بنفس الحجم، مش أكتر.');
    } else if (ratio < 1) messages.push('فوّت تمرين أو اتنين: مفيش مشكلة، كمّل عادي.');
    if (fb.feel === 'hard') { next.flags.noIncreaseFirstWeek = true; messages.push('الأسبوع كان تقيل عليك، فهنثبّت الحجم أسبوع.'); }
    if (fb.feel === 'easy' && ratio === 1 && (!fb.pain || fb.pain === 'none')) messages.push('أسبوع حلو. كمّل بنفس الخطة.');
    if (action === 'continue' && ratio >= 0.75 && fb.feel !== 'hard' && (!fb.pain || fb.pain === 'none')) next.flags.progressNow = true;
    if (fb.newTime) { next.recentKm = 5; next.recentTime = fb.newTime; messages.push('حدّثنا سرعاتك على وقت الـ 5 كم الجديد.'); }
    return { action, messages, input: next };
  }

  return { parseDuration, RACES, DIST_NAME, HEALTH_QUESTIONS, STATIONS, LEVEL_NAME, generate, checkIn, screen, levelOf, vdotFrom, predictTime, paceTable, fmtPace, fmtTime, addDays, diffDays };
});
