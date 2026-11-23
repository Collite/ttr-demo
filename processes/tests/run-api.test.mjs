// AU-hartland P3J (D-250, D-253) — every run-level `perform` and `outcome` the composed processes send is a body the
// Server reads (run-api-stub.mjs). The exporter's per-row steps send `keys: [{<key column>: value}]` and
// `outcomes: [{key: {<key column>: value}, …}]` from grammar 0.22.10 (S1.5.10); a scalar key is `400 bad-request` on
// bp-dsk (PE S0.4 ⚑9), so it is refused here too. The deployment-level typed perform (D-168) is not a run action.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { answer, anyRow, evaluate } from './run-api-stub.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..', '..');
const { BpmnModdle } = await import('bpmn-moddle');
const camunda = JSON.parse(await readFile(path.join(here, 'node_modules/camunda-bpmn-moddle/resources/camunda.json'), 'utf8'));
const sets = JSON.parse(await readFile(path.join(root, 'processes/sets.json'), 'utf8'));
const PROCESSES = ['release_order', 'release_morning', 'return_request'];
const KEY = 200117749;

test('the stub refuses a scalar perform key and a scalar outcome key, as the Server does', () => {
  const p = '/automation/runs/r1/actions/hold/perform';
  const o = '/automation/runs/r1/actions/notify/outcome';
  assert.equal(answer(p, { keys: [KEY] }).status, 400);
  assert.deepEqual(answer(p, { keys: [KEY] }).body.error.code, 'bad-request');
  assert.equal(answer(p, { keys: [{ order_number: KEY }] }).status, 200);
  assert.equal(answer(p, {}).status, 200, 'no keys = every key of the action');
  const at = '2026-11-19T09:00:00Z';
  assert.equal(answer(o, { outcomes: [{ key: KEY, status: 'delivered', at }] }).status, 400);
  assert.equal(answer(o, { outcomes: [{ key: { order_number: KEY }, status: 'delivered', at }] }).status, 200);
  assert.equal(answer(o, { outcomes: [{ key: { order_number: KEY }, status: 'sent', at }] }).status, 400);
});

function* walk(el) {
  yield el;
  for (const child of el.flowElements ?? []) yield* walk(child);
}

async function readProcess(file) {
  const moddle = new BpmnModdle({ camunda });
  const { rootElement } = await moddle.fromXML(await readFile(file, 'utf8'), 'bpmn:Definitions');
  return rootElement.rootElements.find((e) => e.$type === 'bpmn:Process');
}

/** The run-level perform/outcome calls of one composed process: [{id, name, verb, path, body}]. */
async function runActionCalls(file) {
  const proc = await readProcess(file);
  const calls = [];
  for (const task of walk(proc)) {
    if (task.$type !== 'bpmn:ServiceTask') continue;
    const connector = task.extensionElements?.values.find((v) => v.$type === 'camunda:Connector');
    const params = connector?.inputOutput?.inputParameters ?? [];
    const url = params.find((p) => p.name === 'url')?.value ?? '';
    if (!/\/automation\/runs\/"\.concat\(\w+\)\.concat\("\/actions\/\w+\/(perform|outcome)"\)\}$/.test(url)) continue;
    const vars = { ttrRunId: 'r1', ttrRow: anyRow(KEY) };
    const u = new URL(evaluate(url, vars));
    const payload = params.find((p) => p.name === 'payload').value;
    calls.push({ id: task.id, name: task.name, verb: u.pathname.split('/').pop(), path: u.pathname,
      body: JSON.parse(evaluate(payload, vars)) });
  }
  return calls;
}

const releaseOrder = path.join(root, 'processes', 'cz', 'release_order.bpmn');
const originalRunId = '00000000-0000-4000-8000-000000000001';
const instanceId = 'process-instance-1';
const taskId = 'approval-task-1';

test('cz/release_order: the committed timer branch sends the original approval and the same evidence on retry', async () => {
  const proc = await readProcess(releaseOrder);
  const timer = [...walk(proc)].find((e) => e.id === 's41_release_confirmed_lapsed');
  const approval = timer.attachedToRef;
  const fallback = timer.outgoing[0].targetRef;
  assert.equal(timer.cancelActivity, true);
  assert.equal(fallback.asyncBefore, true, 'the timer history must commit before the hold call');
  assert.equal(fallback.$parent, approval.$parent, 'the fallback keeps the approval row scope');
  const rowInputs = approval.$parent.extensionElements.values.find((v) => v.$type === 'camunda:InputOutput');
  assert.ok(rowInputs.inputParameters.some((v) => v.name === 'ttrTaskId'), 'task ID has a slot in the row scope');
  const listener = approval.extensionElements.values.find((v) => v.$type === 'camunda:TaskListener' && v.event === 'create');
  assert.match(listener.script.value, /task\.execution\.setVariable\('ttrTaskId', task\.id\)/);

  const connector = fallback.extensionElements.values.find((v) => v.$type === 'camunda:Connector');
  const input = (name) => connector.inputOutput.inputParameters.find((p) => p.name === name).value;
  assert.equal(input('method'), 'POST');
  assert.equal(new URL(evaluate(input('url'), {})).pathname, '/automation/deployments/release_event_cz/actions/hold/perform');
  assert.ok(fallback.extensionElements.values.some((v) => v.$type === 'camunda:FailedJobRetryTimeCycle'));
  for (const order of [4711, '004711']) {
    const attempt = () => evaluate(input('payload'), {
      ttrRunId: originalRunId, ttrTaskId: taskId, ttrRow: anyRow(order), execution: { processInstanceId: instanceId },
    });
    const first = attempt();
    const body = JSON.parse(first);
    assert.deepEqual(body, {
      key: { order }, params: { department: 'Sales' }, origin: 'engine',
      idempotencyKey: `${instanceId}:lapsed:${JSON.stringify(order)}`,
      expiry: { originalRunId, action: 'release_confirmed', key: { order_number: order }, instanceId, taskId,
        timerActivityId: timer.id },
    });
    assert.equal(attempt(), first);
  }
});

test('cz/release_order: human completion opens the answer with the assignee and task ID', async () => {
  const proc = await readProcess(releaseOrder);
  const timer = [...walk(proc)].find((e) => e.id === 's41_release_confirmed_lapsed');
  const approval = timer.attachedToRef;
  const listener = approval.extensionElements.values.find((v) => v.$type === 'camunda:TaskListener' && v.event === 'complete');
  assert.match(listener.script.value, /task\.execution\.setVariable\('ttrAnsweredBy', task\.assignee\)/);
  assert.equal(approval.outgoing.length, 1);
  const answerStep = approval.outgoing[0].targetRef;
  assert.notEqual(answerStep, timer.outgoing[0].targetRef);
  const io = answerStep.extensionElements.values.find((v) => v.$type === 'camunda:InputOutput');
  const payload = io.inputParameters.find((p) => p.name === 'ttrAnswerOpenBody').value;
  const result = JSON.parse(evaluate(payload, {
    ttrTaskId: taskId, ttrAnsweredBy: 'sales-user', ttrRow: anyRow(4711), ttrAnchor: originalRunId,
    execution: {
      processInstanceId: instanceId, processBusinessKey: 'order:4711', processDefinitionId: 'release-order-1',
      processEngineServices: { repositoryService: { getProcessDefinition: () => ({ deploymentId: 'deployment-1' }) } },
    },
  }).toString());
  assert.deepEqual(result.port.key, { order_number: 4711 });
  assert.deepEqual(result.engine, { instanceId, businessKey: 'order:4711', deploymentId: 'deployment-1', taskId,
    answeredBy: 'sales-user' });
  assert.equal(result.idempotencyKey, `${originalRunId}:answer:${taskId}`);
  assert.equal(result.expiry, undefined);
});

for (const set of Object.keys(sets).filter((k) => !k.startsWith('_'))) {
  const counts = { perform: 0, outcome: 0 };
  for (const name of PROCESSES) {
    test(`${set}/${name}: every run-level perform and outcome body is one the Server reads`, async () => {
      const calls = await runActionCalls(path.join(root, 'processes', set, `${name}.bpmn`));
      const refusals = [];
      for (const c of calls) {
        counts[c.verb] += 1;
        const a = answer(c.path, c.body);
        if (a.status !== 200) refusals.push(`${c.id} "${c.name}" ${c.verb} ${JSON.stringify(c.body)} → ${a.status} ${a.body.error.message}`);
      }
      assert.deepEqual(refusals, [], `${refusals.length} refused:\n${refusals.join('\n')}`);
    });
  }
  test(`${set}: the check saw perform and outcome bodies (it cannot pass on none)`, () => {
    assert.ok(counts.perform > 0 && counts.outcome > 0, JSON.stringify(counts));
  });
}
