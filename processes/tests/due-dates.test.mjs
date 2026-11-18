// AU-hartland P4·S4.1 (review-365 B1) — the approval due dates count the world's working days (D-82: not a weekend,
// not a holiday of data/calendar/calendar.sql), and the lapse fires on that date.
//
// Runs the due-date script exactly as composed into processes/<set>/*.bpmn on Groovy 5.0.4 — the jar bp-dsk's engine
// image (cibseven run4-2.2.0) ships — with the engine clock (ClockUtil) set to fixed instants. Needs a JDK on PATH and
// the jar: `just processes-tools` fetches it (sha-pinned) to processes/tests/.tools/; TTR_GROOVY_JAR overrides.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdtemp, access } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..', '..');
const jar = process.env.TTR_GROOVY_JAR ?? path.join(here, '.tools', 'groovy-5.0.4.jar');
try {
  await access(jar);
} catch {
  throw new Error(`processes/tests needs Groovy 5.0.4 to run the due-date scripts: just processes-tools (looked for ${jar})`);
}
const sets = JSON.parse(await readFile(path.join(root, 'processes/sets.json'), 'utf8'));

// The engine's side of a script task: ClockUtil (the engine clock) and the execution's variables. Each case is
// `<engine clock instant>|<ttrApprovalDueOverride or empty>`; the script's ttrApprovalDue is printed as an instant.
const HARNESS = `
def gcl = new GroovyClassLoader(this.class.classLoader)
gcl.parseClass('''package org.cibseven.bpm.engine.impl.util
class ClockUtil { static Date now; static Date getCurrentTime() { now } }''')
def clock = gcl.loadClass('org.cibseven.bpm.engine.impl.util.ClockUtil')
def src = new File(args[0]).getText('UTF-8')
args[1..-1].each { c ->
    def parts = c.split('\\\\|', -1)
    clock.now = Date.from(java.time.Instant.parse(parts[0]))
    def local = [:]
    def exec = new Expando(getVariable: { n -> n == 'ttrApprovalDueOverride' && parts[1] ? parts[1] : null },
                           setVariableLocal: { n, v -> local[n] = v })
    new GroovyShell(gcl, new Binding([execution: exec])).evaluate(src)
    println local.ttrApprovalDue.toInstant()
}
`;

const unescape = (s) => s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, '&');

// every due-date script of a process: { id, action, days, source }
async function dueScripts(file) {
  const xml = await readFile(file, 'utf8');
  const out = [];
  for (const m of xml.matchAll(/<bpmn:scriptTask id="(s41_\w+_due)"[^>]*>[\s\S]*?<bpmn:script>([\s\S]*?)<\/bpmn:script>/g)) {
    const source = unescape(m[2]);
    const head = source.match(/def action (\w+) \{ due: (\d+) working_days \}/);
    assert.ok(head, `${m[1]}: the due-date script names its action and days`);
    out.push({ id: m[1], action: head[1], days: Number(head[2]), source, xml });
  }
  return out;
}

let tmp;
async function run(source, cases) {
  tmp ??= await mkdtemp(path.join(tmpdir(), 's41-due-'));
  const script = path.join(tmp, 'due.groovy');
  const harness = path.join(tmp, 'harness.groovy');
  await writeFile(script, source);
  await writeFile(harness, HARNESS);
  const r = spawnSync('java', ['-cp', jar, 'groovy.ui.GroovyMain', harness, script, ...cases], { encoding: 'utf8' });
  assert.equal(r.status, 0, `groovy failed: ${r.stderr || r.error}`);
  return r.stdout.trim().split('\n');
}

// [engine clock, override, expected due] per working-day count — Prague clock, CZ holidays (zákon 245/2000 Sb.)
const CASES = {
  2: [
    // review-365 B1: Monday 16 Nov 2026, Tuesday 17 Nov is a holiday → Thursday 19 Nov, same time of day
    ['2026-11-16T08:00:00Z', '', '2026-11-19T08:00:00Z'],
    // a weekend only: Friday → Tuesday
    ['2026-11-20T08:00:00Z', '', '2026-11-24T08:00:00Z'],
    // Christmas: Wed 23 Dec 2026, 24–26 Dec are holidays → Tue 29 Dec
    ['2026-12-23T08:00:00Z', '', '2026-12-29T08:00:00Z'],
    // Easter 2027 (Sunday 28 Mar): Good Friday 26 and Easter Monday 29 Mar; 09:00 CET → 09:00 CEST on Wed 31 Mar
    ['2027-03-25T08:00:00Z', '', '2027-03-31T07:00:00Z'],
    // the certification override replaces the calendar
    ['2026-11-16T08:00:00Z', 'PT2M', '2026-11-16T08:02:00Z'],
  ],
  3: [
    // the care task (decide_way, 3 working days): Monday 16 Nov → 18, 19, 20 Nov
    ['2026-11-16T08:00:00Z', '', '2026-11-20T08:00:00Z'],
    // Friday 6 Nov 2026 → 9, 10, 11 Nov (no holiday)
    ['2026-11-06T08:00:00Z', '', '2026-11-11T08:00:00Z'],
  ],
};

for (const set of Object.keys(sets).filter((k) => !k.startsWith('_'))) {
  for (const name of ['release_order', 'release_morning', 'return_request']) {
    test(`${set}: ${name} — every due date counts the world's working days, and the lapse fires on it`, async () => {
      const scripts = await dueScripts(path.join(root, 'processes', set, `${name}.bpmn`));
      assert.ok(scripts.length > 0, `${name} has a due-date script`);
      for (const s of scripts) {
        const cases = CASES[s.days];
        assert.ok(cases, `${s.id}: no cases for ${s.days} working days`);
        const got = await run(s.source, cases.map(([at, ov]) => `${at}|${ov}`));
        assert.deepEqual(got, cases.map((c) => c[2]), `${s.id} (${s.action}, ${s.days} working days)`);
      }
      // the task's due date and the lapse's timer both read the script's ttrApprovalDue
      const xml = scripts[0].xml;
      const dated = [...xml.matchAll(/<bpmn:userTask\b[^>]*\bcamunda:dueDate="([^"]+)"/g)];
      assert.equal(dated.length, scripts.length, 'one dated task per due-date script');
      for (const m of dated) assert.equal(m[1], '${ttrApprovalDue}', 'the task is due on the script\'s date');
      const timers = [...xml.matchAll(/<bpmn:timerEventDefinition id="(s41_\w+_lapsed_timer)">\s*<bpmn:timeDate[^>]*>([^<]+)</g)];
      assert.equal(timers.length, name === 'return_request' ? 0 : scripts.length, 'one lapse timer per H-1 confirmation');
      for (const m of timers) assert.equal(m[2], '${ttrApprovalDue}', `${m[1]}: the lapse fires on the due date`);
    });
  }
}
