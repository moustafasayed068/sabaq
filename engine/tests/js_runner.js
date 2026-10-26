// Runs the JS reference engine on cases read from stdin (JSON array), for the differential test.
const E = require('../../reference/engine-js/sabaq-engine.js');
let raw = '';
process.stdin.on('data', (c) => { raw += c; });
process.stdin.on('end', () => {
  const out = JSON.parse(raw).map((c) => {
    const plan = E.generate(c.input);
    if (!c.feedback) return { output: plan };
    if (!plan.weeks.length) return { skipped: true };
    const res = E.checkIn(c.input, plan, 0, c.feedback);
    return { checkIn: res, nextPlan: res.action === 'paused' ? null : E.generate(res.input) };
  });
  process.stdout.write(JSON.stringify(out));
});
