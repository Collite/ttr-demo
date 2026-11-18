// AU-hartland P4·S4.1 T1 — the authored processes (processes/<set>/*.bpmn), read with bpmn-moddle (JDK-free).
// `npm ci --prefix processes/tests` once; then `just verify-model` (or `node --test processes/tests`).
//
// What holds for every process of every deployment set (processes/sets.json):
//   * it parses, and nothing but the exporter's own `ttr:contract` is unknown to the BPMN + Camunda schemas;
//   * it carries camunda:historyTimeToLive, and its start is asyncAfter (process-engine contracts §1–§2);
//   * it calls only deployments of its own set that the world declares (one set per engine, review-236 P2);
//   * it is the composition of the set's exports: every element not added by the composer (`s41_*`) is an element of
//     one of the set's emitted skeletons, and `compose-processes.py --check` finds no drift (Found A: the templates are
//     single-call Opens, so the run chain is kept as emitted instead of rebuilt from templates);
//   * every authored HTTP step calls the egress on a run-API path the Server serves;
//   * every user task is offered to a `def role`'s Keycloak group; every approval task has a due date;
//   * the messages it starts on / waits for are the driver's (scripts/automation-events.py, D-143).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..', '..');

let BpmnModdle, camunda;
try {
  ({ BpmnModdle } = await import('bpmn-moddle'));
  camunda = JSON.parse(await readFile(path.join(here, 'node_modules/camunda-bpmn-moddle/resources/camunda.json'), 'utf8'));
} catch (e) {
  throw new Error(`processes/tests needs its parser: npm ci --prefix processes/tests (${e.message})`);
}

const sets = JSON.parse(await readFile(path.join(root, 'processes/sets.json'), 'utf8'));
const world = await readFile(path.join(root, 'automation/worlds/demo.ttrm'), 'utf8');
const automation = await readFile(path.join(root, 'automation/automation.ttrm'), 'utf8');
const worldDeployments = new Set([...world.matchAll(/def deployment (\w+)/g)].map((m) => m[1]));
const roleGroups = new Set([...automation.matchAll(/def role \w+\s*\{\s*resolve:\s*keycloak_group\s*"([^"]+)"/g)].map((m) => m[1]));
const STARTS = new Set(['order_placed', 'return_requested']);
const WAKES = new Set(['receipt_posted', 'settlement_posted']);
const PROCESSES = ['release_order', 'release_morning', 'return_request'];
// the run-API paths an authored step may call (Server contracts: status, routes, digest D-148, typed perform D-168)
const AUTHORED_CALLS = [
  /^\/runs\/"\.concat\(\w+\)$/,
  /^\/runs\/"\.concat\(\w+\)\.concat\("\/routes\/\w+"\)$/,
  /^\/runs\/"\.concat\(\w+\)\.concat\("\/digest\?action=notify&lang=(cs|en)"\)$/,
  /^\/deployments\/(\w+)\/actions\/(\w+)\/perform"$/,
];

async function parse(file) {
  const xml = await readFile(file, 'utf8');
  const moddle = new BpmnModdle({ camunda });
  const { rootElement, warnings } = await moddle.fromXML(xml, 'bpmn:Definitions');
  return { xml, defs: rootElement, warnings };
}

function* walk(el) {
  yield el;
  for (const child of el.flowElements ?? []) yield* walk(child);
}

async function exportIds(set) {
  const ids = new Set();
  for (const d of Object.values(sets[set].deployments)) {
    const dir = path.join(root, 'exports', d);
    const [exp] = (await readdir(dir)).filter((f) => f.endsWith('.export'));
    const [bpmn] = (await readdir(path.join(dir, exp))).filter((f) => f.endsWith('.c7.bpmn'));
    const xml = await readFile(path.join(dir, exp, bpmn), 'utf8');
    for (const m of xml.matchAll(/ id="([^"]+)"/g)) ids.add(m[1]);
  }
  return ids;
}

for (const set of Object.keys(sets).filter((k) => !k.startsWith('_'))) {
  const own = new Set(Object.values(sets[set].deployments));

  test(`${set}: the deployment set names only deployments the world declares`, () => {
    for (const d of own) assert.ok(worldDeployments.has(d), `${d} is not a def deployment of the world`);
  });

  test(`${set}: processes/${set} is exactly what the exports compose to (no drift)`, () => {
    const r = spawnSync('python3', ['scripts/compose-processes.py', '--set', set, '--check'], { cwd: root, encoding: 'utf8' });
    assert.equal(r.status, 0, r.stdout + r.stderr);
  });

  const emitted = await exportIds(set);
  for (const name of PROCESSES) {
    const file = path.join(root, 'processes', set, `${name}.bpmn`);

    test(`${set}/${name}: parses; only the exporter's ttr:contract is foreign`, async () => {
      const { defs, warnings } = await parse(file);
      const foreign = warnings.filter((w) => !/ttr:contract|automation-export/.test(w.message));
      assert.deepEqual(foreign.map((w) => w.message), []);
      const processes = defs.rootElements.filter((e) => e.$type === 'bpmn:Process');
      assert.deepEqual(processes.map((p) => p.id), [name]);
    });

    test(`${set}/${name}: TTL on the process, asyncAfter on its start`, async () => {
      const { defs } = await parse(file);
      const proc = defs.rootElements.find((e) => e.$type === 'bpmn:Process');
      assert.ok(proc.historyTimeToLive, 'camunda:historyTimeToLive');
      const starts = proc.flowElements.filter((e) => e.$type === 'bpmn:StartEvent');
      assert.equal(starts.length, 1);
      assert.equal(starts[0].asyncAfter, true, 'the start commits at once (contracts §1, review-208)');
    });

    test(`${set}/${name}: calls only its set's deployments`, async () => {
      const { xml } = await parse(file);
      const named = [...xml.matchAll(/prop\("deployment","(\w+)"\)/g), ...xml.matchAll(/\/deployments\/(\w+)\/actions\//g)]
        .map((m) => m[1]);
      assert.ok(named.length > 0);
      for (const d of named) assert.ok(own.has(d), `${d} is not in the ${set} set`);
    });

    test(`${set}/${name}: every element is emitted or authored (s41_*)`, async () => {
      const { defs } = await parse(file);
      const proc = defs.rootElements.find((e) => e.$type === 'bpmn:Process');
      const strangers = [...walk(proc)].slice(1).map((e) => e.id).filter((id) => !id.startsWith('s41_') && !emitted.has(id));
      assert.deepEqual(strangers, []);
    });

    test(`${set}/${name}: authored HTTP steps call the run API through the egress`, async () => {
      const { defs } = await parse(file);
      const proc = defs.rootElements.find((e) => e.$type === 'bpmn:Process');
      const authored = [...walk(proc)].filter((e) => e.id.startsWith('s41_') &&
        ['bpmn:ServiceTask', 'bpmn:SendTask'].includes(e.$type) && e.extensionElements);
      for (const task of authored) {
        const connector = task.extensionElements.values.find((v) => v.$type === 'camunda:Connector');
        if (!connector) continue;                       // a send task is an external task (TTR_CONN_MAIL)
        const url = connector.inputOutput.inputParameters.find((p) => p.name === 'url').value;
        const m = url.match(/^\$\{"(https?:\/\/[^"/]+(?:\/[^"/]+)*?\/automation)(.*)\}$/);
        assert.ok(m, `${task.id}: ${url}`);
        assert.match(m[1], /process-engine-egress/);
        assert.ok(AUTHORED_CALLS.some((re) => re.test(m[2])), `${task.id} calls ${m[2]}`);
        const perform = m[2].match(AUTHORED_CALLS[3]);
        if (perform) assert.ok(own.has(perform[1]), `${task.id} performs on ${perform[1]}`);
      }
    });

    test(`${set}/${name}: every user task is offered to a def role's group; approvals have a due date`, async () => {
      const { defs } = await parse(file);
      const proc = defs.rootElements.find((e) => e.$type === 'bpmn:Process');
      const tasks = [...walk(proc)].filter((e) => e.$type === 'bpmn:UserTask');
      assert.ok(tasks.length > 0);
      for (const t of tasks) {
        assert.ok(t.candidateGroups, `${t.id} (${t.name}) has no candidate group`);
        for (const g of t.candidateGroups.split(',')) assert.ok(roleGroups.has(g.trim()), `${t.id}: ${g} is no def role's group`);
      }
      const approvals = tasks.filter((t) => /^(Potvrďte|Confirm|Rozhodněte|Decide)/.test(t.name));
      for (const t of approvals) assert.equal(t.dueDate, '${ttrApprovalDue}', `${t.id} has no due date`);
    });

    test(`${set}/${name}: starts on and waits for the driver's messages only`, async () => {
      const { defs } = await parse(file);
      const proc = defs.rootElements.find((e) => e.$type === 'bpmn:Process');
      const events = [...walk(proc)].filter((e) => ['bpmn:StartEvent', 'bpmn:IntermediateCatchEvent'].includes(e.$type));
      for (const e of events) {
        const def = (e.eventDefinitions ?? []).find((d) => d.$type === 'bpmn:MessageEventDefinition');
        if (!def) continue;
        const pool = e.$type === 'bpmn:StartEvent' ? STARTS : WAKES;
        assert.ok(pool.has(def.messageRef.name), `${e.id} catches ${def.messageRef.name}`);
      }
    });
  }

  test(`${set}: release_order — the confirmation lapses into perform hold {Sales}; D-98 guards the start`, async () => {
    const { defs, xml } = await parse(path.join(root, 'processes', set, 'release_order.bpmn'));
    const proc = defs.rootElements.find((e) => e.$type === 'bpmn:Process');
    const all = [...walk(proc)];
    const start = all.find((e) => e.$type === 'bpmn:StartEvent');
    assert.equal(start.eventDefinitions[0].messageRef.name, 'order_placed');
    assert.ok(all.some((e) => e.id === 's41_pending_guard'));
    const lapse = all.find((e) => e.id === 's41_release_confirmed_lapsed');
    assert.equal(lapse.attachedToRef.$type, 'bpmn:UserTask');
    assert.equal(lapse.cancelActivity, true);
    assert.match(xml, /\/deployments\/release_event\w*\/actions\/hold\/perform/);
    assert.match(xml, /prop\("params", S\('\{\}'\)\.prop\("department", "Sales"\)\)/);
  });

  test(`${set}: release_morning — a timer start and one digest send per group`, async () => {
    const { defs } = await parse(path.join(root, 'processes', set, 'release_morning.bpmn'));
    const proc = defs.rootElements.find((e) => e.$type === 'bpmn:Process');
    const all = [...walk(proc)];
    const start = all.find((e) => e.$type === 'bpmn:StartEvent');
    assert.equal(start.eventDefinitions[0].$type, 'bpmn:TimerEventDefinition');
    const sends = all.filter((e) => e.$type === 'bpmn:SendTask');
    assert.deepEqual(sends.map((s) => s.id), ['s41_digest_send'], 'the per-row mail is bypassed in the batch');
    assert.equal(sends[0].loopCharacteristics.collection, '${ttrDigest.prop("groups").elements()}');
  });

  test(`${set}: return_request — care decides through a form and perform; two loops on their messages`, async () => {
    const { defs } = await parse(path.join(root, 'processes', set, 'return_request.bpmn'));
    const proc = defs.rootElements.find((e) => e.$type === 'bpmn:Process');
    const all = [...walk(proc)];
    const care = all.find((e) => e.id === 's41_care');
    assert.equal(care.candidateGroups, 'hartland-care');
    const form = care.extensionElements.values.find((v) => v.$type === 'camunda:FormData');
    assert.deepEqual(form.fields.map((f) => [f.id, f.type, f.values.map((v) => v.id)]),
      [['way', 'enum', ['refund_no_return', 'replacement_no_return', 'exchange', 'refund_after_return']]]);
    assert.ok(!all.some((e) => e.name === 'ask each to_customer_care row'), 'the skeleton\'s approval ask of decide_way is gone (D-171)');
    for (const loop of ['inbound', 'settle']) {
      const wait = all.find((e) => e.id === `s41_${loop}_wait`);
      assert.equal(wait.$type, 'bpmn:EventBasedGateway');
      assert.equal(all.find((e) => e.id === `s41_${loop}`).$type, 'bpmn:SubProcess');
    }
  });
}
