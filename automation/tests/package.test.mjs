// AU-hartland-P2 · S2.1 — the automation package (`automation/automation.ttrm`, `programs.ttrm`) and the world it runs
// in (`automation/worlds/demo.ttrm`): AU design `17` §1–§2 as written for ttr-core grammar 0.16, D-64 (both
// languages), D-67 (`states:`), D-79 / D-76 (`writable:`), D-132 (the decider's credential).
// Mocked/unit: parses `model/` + `automation/` as one project (project-harness.mjs) — what the automation service
// loads — and runs the toolchain's automation validator over it, with the stdlib the toolchain ships. No live DB.
// Run: node --test automation/tests/package.test.mjs (from the hartland repo root).
//
// The tables below ARE the contract (`project/kantheon/features/automation-agents/design/17-recipes-retyped.md`
// §1–§2 + the hartland plan's contracts.md §3–§4): a change here is a change of the contract.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { readFile } from 'node:fs/promises';
import { loadHartlandProject, ACCEPTED_RESIDUAL_CODES, hartlandRoot } from '../../model/tests/project-harness.mjs';

const tatrmanPackages = process.env.TATRMAN_PACKAGES ?? path.resolve(hartlandRoot, '../tatrman/packages');
const { validateWorldDocument, validateAutomationProject } = await import(path.join(tatrmanPackages, 'semantics/dist/index.js'));
const { loadAutomationStdlib } = await import(path.join(tatrmanPackages, 'semantics/dist/node-only.js'));

const project = await loadHartlandProject({ roots: ['model', 'automation'] });
const modelOnly = await loadHartlandProject();
const stdlib = await loadAutomationStdlib();

const own = (p) => [...p.asts].filter(([uri]) => !uri.startsWith('stock://'));
const docsOf = (p) => own(p).map(([, ast]) => ast);
const defs = docsOf(project).flatMap((d) => d.definitions ?? []);
const ofKind = (kind) => new Map(defs.filter((d) => d.kind === kind).map((d) => [d.name, d]));
const entry = (def, key) => (def.entries ?? []).find((e) => e.key === key)?.value;

/** An automation value in the source's spelling (enough for the contract's comparisons). */
function render(v) {
  if (!v) return undefined;
  switch (v.kind) {
    case 'id': return v.path;
    case 'string': return v.value;
    case 'number': return v.raw ?? String(v.value);
    case 'bool': return String(v.value);
    case 'star': return '*';
    case 'duration': return `${v.amount} ${v.unit}`;
    case 'tagged': return `${v.tag} "${v.value}"`;
    case 'autoList': case 'list': return `[${v.items.map(render).join(', ')}]`;
    case 'autoObject': return `{ ${v.entries.map((e) => `${e.key}: ${render(e.value)}`).join(', ')} }`;
    default: return `<${v.kind}>`;
  }
}
const objectOf = (v) => Object.fromEntries((v?.entries ?? []).map((e) => [e.key, render(e.value)]));

// ── the project loads clean ─────────────────────────────────────────────────────────────────────────────────────
// Until the recipe catalog exists (ttr-core P2 generates `def recipe <n>`), a program's recipe is accepted by name with
// an info — the one finding the validator may report here.
const PRECATALOG = 'ttr/automation-recipe-precatalog';

test('S2.1 — model/ + automation/ parse, resolve and lint with nothing outside the accepted residuals', () => {
  const parseErrors = [...project.parseErrorsByFile].filter(([, e]) => e.length).map(([f, e]) => `${f}: ${e[0].message}`);
  assert.deepEqual(parseErrors, []);
  const offenders = [];
  for (const [file, codes] of project.diagnosticsByFile) {
    if (!file.startsWith('automation/')) continue;
    for (const code of codes) if (code === 'ttr/unresolved-reference' || !ACCEPTED_RESIDUAL_CODES.has(code)) offenders.push(`${file}: ${code}`);
  }
  assert.deepEqual(offenders, []);
});

test('S2.1 — the automation validator (with the toolchain\'s stdlib) finds nothing but the pre-catalog recipe names', () => {
  const diags = validateAutomationProject(docsOf(project), { stdlib });
  const defaultNotices = diags.filter((d) => d.code === 'ttr/automation-unknown-property');
  // The reader pin's TS validator ([ttr-core] 0.21) predates CG-2's `by:` (D-144/D-161) and `startable_by:` (D-161); it
  // warns, the pinned compiler ([ttrp] 0.22) reads them. They go when the readers' pin stage moves [ttr-core].
  assert.deepEqual(defaultNotices.map((d) => d.message).sort(), [
    "action 'decide_way': unknown property `by:`", "action 'handoff': unknown property `by:`",
    "action 'propose': unknown property `writer_defaults:`", "action 'record': unknown property `writer_defaults:`",
    "action 'release_confirmed': unknown property `by:`", "deployment 'release_event': unknown property `startable_by:`",
  ]);
  const findings = diags.filter((d) => d.code !== PRECATALOG && !defaultNotices.includes(d)).map((d) => `${d.severity} ${d.code}: ${d.message}`);
  assert.deepEqual(findings, []);
  assert.ok(diags.every((d) => d.severity === (defaultNotices.includes(d) ? 'warning' : 'info')));
});

// The veles view. veles and the lexicon build read `model/` alone; the lexicon build refuses a model that does not
// load, and veles would carry every unresolved automation reference as a load error. So nothing under `model/` may
// name an automation object: the world and the package live in `automation/`, and `model/` only gains `states:`.
test('S2.1 — `model/` alone (what veles and the lexicon build read) holds no automation file and validates clean', () => {
  const stray = own(modelOnly).filter(([, ast]) => ['automation', 'world'].includes(ast.modelDirective?.modelCode)).map(([uri]) => uri);
  assert.deepEqual(stray, []);
  const diags = validateAutomationProject(docsOf(modelOnly), { stdlib });
  assert.deepEqual(diags.map((d) => `${d.code}: ${d.message}`), []);
});

// ── 17 §1: the package ──────────────────────────────────────────────────────────────────────────────────────────
// parameter → [type, value]; `17` §1's nine, then H-3's and H-5's (S2.2 T4; D-129 = data/automation/automation.conf).
const PARAMETERS = {
  tolerance: ['decimal', '0.01'],
  confirmation_threshold: ['decimal', '50000'],
  return_window: ['days', '30'],
  abuse_share: ['decimal', '0.40'],
  small_value: ['decimal', '15'],
  care_threshold: ['decimal', '500'],
  inbound_reminder: ['days', '14'],
  inbound_close: ['days', '30'],
  settlement: ['working_days', '5'],
  cover_target: ['int', '3'],
  order_up_to: ['int', '6'],
  demand_period: ['int', '8'],
  quiet_months: ['int', '12'],
  active_orders: ['int', '4'],
  mail_window: ['days', '92'],
};

test('S2.1 T2 — the parameters, their types and values (17 §1; H-3/H-5 per D-129)', () => {
  const got = Object.fromEntries([...ofKind('parameter')].map(([n, p]) => [n, [p.type?.name, render(entry(p, 'value'))]]));
  assert.deepEqual(got, PARAMETERS);
});

test('S2.1 T2 — every parameter carries a label in English and Czech (D-64)', () => {
  for (const [name, p] of ofKind('parameter')) {
    const l = p.label?.entries ?? {};
    assert.ok(l.en && l.cs, `parameter ${name}: label { en, cs }`);
  }
});

// action → [columns, transition, set, sinks, approval] — `20` §1 (engine actions carry no native sink)
const ACTIONS = {
  release: [['order:order.order_number'], 'order.state -> released from [placed, held]', undefined,
    { native: 'transition', n8n: 'door', process_engine: 'door' }, 'none'],
  release_confirmed: [['order:order.order_number', 'value:order.value'], 'order.state -> released from [placed, held]', undefined,
    { native: 'transition', n8n: 'door', process_engine: 'door' }, 'required'],
  hold: [['order:order.order_number', 'department:text'], 'order.state -> held from [placed]', 'order.held_for = department',
    { native: 'transition', n8n: 'door', process_engine: 'door' }, 'none'],
  notify: [['who:role', 'detail:rows', 'template:text?'], undefined, undefined,
    { process_engine: 'send task', n8n: 'n8n-nodes-base.emailSend', hebe: 'message' }, 'none'],
  notify_customer: [['customer:customer.sk', 'to:customer.email', 'template:text'], undefined, undefined,
    { process_engine: 'send task', n8n: 'n8n-nodes-base.emailSend' }, 'none'],
  review: [['who:role', 'about:text', 'detail:rows?'], undefined, undefined,
    { process_engine: 'user task', hebe: 'task', n8n: 'door' }, 'none'],
  set_state: [['line:return_request_line.line_id', 'to:text', 'way:text?'], 'return_request_line.state -> {to} from []',
    'return_request_line.way = way', { native: 'transition', n8n: 'door', process_engine: 'door' }, 'none'],
  decide_way: [['line:return_request_line.line_id', 'request:return_request.request_number', 'to:text', 'way:text'],
    'return_request_line.state -> {to} from []', 'return_request_line.way = way', { native: 'transition', process_engine: 'door' }, 'required'],
  expect: [['line:return_request_line.line_id', 'kind:text', 'due:date'], undefined, undefined, { native: 'obligation' }, 'none'],
  fulfil: [['line:return_request_line.line_id', 'kind:text', 'to:text'], 'obligation.state -> {to} from []', undefined,
    { native: 'obligation' }, 'none'],
  handoff: [['process:text', 'rows:rows'], undefined, undefined, { process_engine: 'call activity' }, 'required'],
  propose: [['item:reorder_proposal.item', 'warehouse:reorder_proposal.warehouse', 'on_hand:reorder_proposal.on_hand',
    'weekly_demand:reorder_proposal.weekly_demand', 'proposed_qty:reorder_proposal.proposed_qty',
    'proposal_id:reorder_proposal.proposal_id?', 'run:reorder_proposal.run?', 'state:reorder_proposal.state?'], undefined, undefined,
  { native: 'writer' }, 'none'],
  emit: [['customer:customer.sk', 'to:customer.email', 'offer:text'], undefined, undefined,
    { process_engine: 'send task', n8n: 'n8n-nodes-base.emailSend' }, 'none'],
  record: [['customer:winback_mail.customer', 'offer:winback_mail.offer', 'quarter:winback_mail.quarter?',
    'run:winback_mail.run?', 'mailed_at:winback_mail.mailed_at?'], undefined, undefined, { native: 'writer' }, 'none'],
};

test('S2.1 T2 — the actions: columns, transition, set, sinks, approval (20 §1; propose/emit/record S2.2 T4, handoff P3E)', () => {
  const columnsOf = (a) => (a.columns ?? []).map((c) => {
    const optional = (c.properties ?? c.entries ?? []).some?.((e) => e.key === 'optional') || c.optional === true;
    return `${c.name}:${c.type?.name}${optional ? '?' : ''}`;
  });
  const got = Object.fromEntries([...ofKind('action')].map(([n, a]) => [n, [
    columnsOf(a),
    a.transition ? `${a.transition.attribute} -> ${a.transition.to ?? `{${a.transition.toColumn}}`} from [${a.transition.from.join(', ')}]` : undefined,
    a.set ? `${a.set.attribute} = ${a.set.column}` : undefined,
    objectOf(entry(a, 'sinks')),
    render(entry(a, 'approval')),
  ]]));
  assert.deepEqual(got, ACTIONS);
});

// `20` rule 2: "needs approval" is on the action — the approving role and the user task's due date; nothing is
// deliverable any more (D-142: delivery is a send task).
test('S2.1 T2 — every approval-required action names its role and due date (20 rule 2); nothing is deliverable (D-142)', () => {
  const actions = ofKind('action');
  const required = Object.fromEntries([...actions].filter(([, a]) => render(entry(a, 'approval')) === 'required')
    .map(([n, a]) => [n, `${render(entry(a, 'by'))} ${render(entry(a, 'due'))}`]));
  assert.deepEqual(required, {
    release_confirmed: 'role.sales_manager 2 working_days', decide_way: 'role.customer_care 3 working_days',
    handoff: 'role.buyer 2 working_days',
  });
  for (const [n, a] of actions) assert.equal(entry(a, 'deliverable'), undefined, n);
});

// The n8n export sends an emailSend action's mail to exactly one addressing column: a role (`who`), whose address
// is configured per estate, or the row's own address (`to`, typed `customer.email`). An action without one would
// export a mail with an empty recipient (review-189 R2).
test('every n8n emailSend action has exactly one addressing column: a `who` role or a `to` address', () => {
  for (const [name, a] of ofKind('action')) {
    if (objectOf(entry(a, 'sinks')).n8n !== 'n8n-nodes-base.emailSend') continue;
    const addressing = (a.columns ?? []).filter((c) => (c.name === 'who' && c.type?.name === 'role')
      || (c.name === 'to' && c.type?.name === 'customer.email'));
    assert.equal(addressing.length, 1, `action ${name}: one addressing column (who: role | to: customer.email)`);
  }
});

test('S2.1 T2 — every action has a dry-run text in English and Czech (D-64)', () => {
  for (const [name, a] of ofKind('action')) {
    const d = objectOf(entry(a, 'dry_run'));
    assert.ok(d.en && d.cs, `action ${name}: dry_run { en, cs }`);
  }
});

// The sink kinds an action may name (ttr-core contracts §2): `native` is one of the Server's; another target names its
// own node / task — a string (`"n8n-nodes-base.emailSend"`) or a word (`door`, Hebe's `message` / `task`).
// `20` §1: the writer's three; `deliver`, `task`, `start` are cut (D-142) — an engine action has no native sink.
const NATIVE_SINKS = new Set(['transition', 'writer', 'obligation']);
const TARGETS = new Set(['native', 'n8n', 'process_engine', 'hebe']);
test('S2.1 T1 — every action\'s sinks name only the sink kinds the ttr-core contract allows', () => {
  for (const [name, a] of ofKind('action')) {
    const sinks = entry(a, 'sinks');
    assert.equal(sinks?.kind, 'autoObject', `${name}: sinks`);
    for (const e of sinks.entries) {
      assert.ok(TARGETS.has(e.key), `${name}: target ${e.key}`);
      if (e.key === 'native') assert.ok(NATIVE_SINKS.has(render(e.value)), `${name}: native ${render(e.value)}`);
      else assert.ok(['string', 'id'].includes(e.value.kind), `${name}: ${e.key} is a node / task name (\`door\`, \`message\`, "send task", …)`);
    }
  }
});

const ROLES = {
  sales: 'hartland-sales', ar: 'hartland-ar', sales_manager: 'hartland-sales-managers', customer_care: 'hartland-care',
  finance: 'hartland-finance', logistics: 'hartland-logistics', process_owner: 'hartland-process-owners', ops: 'hartland-ops',
  buyer: 'hartland-buyers',
};
test('S2.1 T2 — the roles resolve to their Keycloak groups (17 §1, contracts §9; `buyer` S2.2 T4)', () => {
  const got = Object.fromEntries([...ofKind('role')].map(([n, r]) => [n, entry(r, 'resolve')?.tag === 'keycloak_group' ? entry(r, 'resolve').value : render(entry(r, 'resolve'))]));
  assert.deepEqual(got, ROLES);
});

test('S2.1 T2 — the four approvals (17 §1)', () => {
  const got = Object.fromEntries([...ofKind('approval')].map(([n, a]) => [n, `${render(entry(a, 'by'))} × ${render(entry(a, 'quorum'))}`]));
  assert.deepEqual(got, {
    recipe: 'role.process_owner × 1', values: 'role.process_owner × 1', program: 'role.process_owner × 1', deployment: 'role.ops × 1',
  });
});

// ── 20 §1: the programs ─────────────────────────────────────────────────────────────────────────────────────────
// program → [recipe, port, mode, as_of]
const PROGRAMS = {
  morning_release: ['release_order', 'none', 'batch', 'run'],
  morning_release_cz: ['release_order', 'none', 'batch', 'run'],
  release_on_placement: ['release_order', 'key', 'on_event', 'event'],
  release_on_placement_cz: ['release_order', 'key', 'on_event', 'event'],
  decide_on_request: ['decide_return', 'key', 'on_event', 'event'],
  decide_on_request_cz: ['decide_return', 'key', 'on_event', 'event'],
  decide_catch_up: ['decide_return', 'none', 'batch', 'run'],
  decide_catch_up_cz: ['decide_return', 'none', 'batch', 'run'],
  inbound_on_receipt: ['monitor_inbound', 'key', 'on_event', 'event'],
  inbound_daily: ['monitor_inbound', 'none', 'batch', 'run'],
  settle_on_document: ['settle', 'key', 'on_event', 'event'],
  settle_daily: ['settle', 'none', 'batch', 'run'],
  reorder_weekly: ['reorder_proposals', 'none', 'batch', 'run'],
  winback_monthly: ['winback', 'none', 'batch', 'run'],
  no_run_since_hourly: ['no_run_since', 'none', 'batch', 'run'],
  obligation_due_passed_hourly: ['obligation_due_passed', 'none', 'batch', 'run'],
};
// The eight recipes of contracts §4 (the recipe name is the file stem under automation/, `ops/` included).
export const RECIPES = ['release_order', 'decide_return', 'monitor_inbound', 'settle', 'reorder_proposals', 'winback',
  'no_run_since', 'obligation_due_passed'];

test('S2.1 T3 — the programs bind the recipes with the port, mode and as-of of 20 §1', () => {
  const got = Object.fromEntries([...ofKind('program')].map(([n, p]) => [n, ['recipe', 'port', 'mode', 'as_of'].map((k) => render(entry(p, k)))]));
  assert.deepEqual(got, PROGRAMS);
});

// `20` rule 4: a program keeps its mode and loses its trigger — no deliver, schedule, event port or event schema.
test('S2.1 T3 — every program names one of the eight recipes; none carries deliver, schedule or event (20 rule 4)', () => {
  for (const [name, p] of ofKind('program')) {
    assert.ok(RECIPES.includes(render(entry(p, 'recipe'))), `${name}: ${render(entry(p, 'recipe'))}`);
    for (const k of ['deliver', 'schedule', 'event']) assert.equal(entry(p, k), undefined, `${name}: ${k}`);
  }
  assert.deepEqual([...ofKind('schema')], []);
});

test('S2.1 T3 — the ops programs write the protocol only for a routed run (D-80)', () => {
  const programs = ofKind('program');
  for (const n of ['no_run_since_hourly', 'obligation_due_passed_hourly']) assert.equal(render(entry(programs.get(n), 'protocol')), 'on_route', n);
});

// ── 20 §2 + contracts §3: the world ─────────────────────────────────────────────────────────────────────────────
const worlds = own(project).filter(([, ast]) => ast.modelDirective?.modelCode === 'world')
  .flatMap(([uri, ast]) => (ast.definitions ?? []).filter((d) => d.kind === 'world').map((w) => ({ uri, ast, w, qname: `${ast.packageDecl?.name}.${w.name}` })));

test('S2.1 T4 — `hartland.worlds.demo` is the one world; it lives in automation/worlds/ beside the package', () => {
  assert.deepEqual(worlds.map((x) => x.qname), ['hartland.worlds.demo']);
  assert.equal(path.relative(hartlandRoot, worlds[0].uri.replace('file://', '')), 'automation/worlds/demo.ttrm');
});

// engine → type; storage → [type, via, hosts, staging]. The engine's name is the credential name (`TTR_CONN_ERP`,
// `TTR_CONN_AUTOMATION` — ttr-p contracts §5), so the names are part of the contract. (Moved from
// model/tests/automation-extension.test.mjs with the world, P2.)
test('S2.1 T4 — the engines and storages of contracts §3', () => {
  const { w } = worlds[0];
  assert.deepEqual(Object.fromEntries(w.engines.map((e) => [e.name, e.type])), { erp: 'postgres', automation: 'postgres' });
  assert.deepEqual(
    Object.fromEntries(w.storages.map((s) => [s.name, [s.type, s.via, s.hosts, s.staging === true]])),
    { erp_db: ['postgres', 'erp', ['hartland'], false], automation_db: ['postgres', 'automation', [], false], stage: ['local_dir', undefined, [], true] },
  );
});

test('S2.1 T4 — the world validates clean against the project\'s packages (one staging, known hosts)', () => {
  const known = new Set(docsOf(project).map((d) => d.packageDecl?.name).filter(Boolean));
  assert.ok(known.has('hartland'), 'the control: the project declares package hartland');
  assert.deepEqual(validateWorldDocument(worlds[0].ast, known).map((d) => `${d.code}: ${d.message}`), []);
});

// D-79 / D-76: the writer's targets are a contract.
test('S2.1 T4 — `writable:` on erp_db and automation_db is exactly contracts §3\'s list (D-79, D-76)', () => {
  const writable = Object.fromEntries(worlds[0].w.storages.filter((s) => s.manifest?.writable).map((s) => [s.name, render(s.manifest.writable)]));
  assert.deepEqual(writable, {
    erp_db: '[order.state, order.held_for, return_request_line.state, return_request_line.way, reorder_proposal, winback_mail]',
    automation_db: '[obligation, state_history, *_verdict, *_verdict_detail, *_verdict_current, approvals]',
  });
});

test('S2.1 T4 — the identities (D-132, D-150, D-158); the three executors, the engine with its egress (20 §2, D-145)', () => {
  const { w } = worlds[0];
  assert.deepEqual(w.identities.map((i) => [i.name, render(entry(i, 'principal')), render(entry(i, 'credential'))]), [
    ['automation_decider', 'svc-hartland-automation', 'TTR_CONN_AUTOMATION_DECIDER'],
    ['process_engine', 'process-engine', 'TTR_CONN_PROCESS_ENGINE'],
    ['maya', 'persona-maya', 'TTR_CONN_PERSONA_MAYA'],
  ]);
  assert.deepEqual(Object.fromEntries(w.executors.map((e) => [e.name, e.extends])), { engine: 'process_engine', n8n: 'n8n_l1', py: 'python_client' });
  assert.equal(render(w.executors.find((e) => e.name === 'n8n').manifest.connection), 'n8n_hartland');
  const engine = w.executors.find((e) => e.name === 'engine').manifest;
  assert.deepEqual(['url', 'egress_url', 'connection'].map((k) => render(engine[k])), [
    'http://process-engine.process-engine.svc/engine-rest', 'http://process-engine-egress.process-engine.svc/automation', 'engine_bp_dsk',
  ]);
});

test('S2.1 T4 — the four grants (D-91, D-158), as triples', () => {
  assert.deepEqual(worlds[0].w.grants.map((g) => ['who', 'program', 'as'].map((k) => render(entry(g, k))).join(' / ')), [
    'identity.process_engine / * / identity.automation_decider',
    'role.ops / * / identity.automation_decider',
    'role.sales_manager / release_on_placement / identity.maya',
    'role.process_owner / * / identity.automation_decider',
  ]);
});

// deployment → [program, target, run_as] — `20` §2: one program on one target; no trigger, no process, no native (D-167: no debug)
const DEPLOYMENTS = {
  release_morning: ['morning_release', 'engine', 'identity.automation_decider'],
  release_event: ['release_on_placement', 'engine', 'identity.automation_decider'],
  release_n8n: ['release_on_placement', 'n8n', 'identity.automation_decider'],
  release_py: ['release_on_placement', 'py', 'identity.automation_decider'],
  decide_event: ['decide_on_request', 'engine', 'identity.automation_decider'],
  inbound_event: ['inbound_on_receipt', 'engine', 'identity.automation_decider'],
  settle_event: ['settle_on_document', 'engine', 'identity.automation_decider'],
  decide_batch: ['decide_catch_up', 'engine', 'identity.automation_decider'],
  inbound_batch: ['inbound_daily', 'engine', 'identity.automation_decider'],
  settle_batch: ['settle_daily', 'engine', 'identity.automation_decider'],
};

test('S2.1 T4 — the deployments: four H-1, six H-2 on the engine; no process, trigger or debug (20 §2, D-167); ops await Server P4', () => {
  const { w } = worlds[0];
  const got = Object.fromEntries(w.deployments.map((d) => [d.name, [render(entry(d, 'program')), d.target?.path, render(entry(d, 'run_as'))]]));
  assert.deepEqual(got, DEPLOYMENTS);
  for (const d of w.deployments) for (const k of ['trigger', 'process', 'debug']) assert.equal(entry(d, k), undefined, `${d.name}: ${k}`);
  assert.equal(render(entry(w.deployments.find((d) => d.name === 'release_n8n'), 'granularity')), 'parts');
  assert.equal(render(entry(w.deployments.find((d) => d.name === 'release_event'), 'startable_by')), 'role.sales_manager');
  assert.deepEqual(w.processes ?? [], []);
});

// ── D-67: the lifecycles on the attributes ──────────────────────────────────────────────────────────────────────
// entity.attribute → [states, transitions (absent ⇒ any)]
const LIFECYCLES = {
  'order.state': [['placed', 'held', 'released', 'cancelled'], { placed: ['held', 'released', 'cancelled'], held: ['released', 'cancelled'] }],
  'invoice.status': [['open', 'paid'], undefined],
  'return_request_line.state': [['received', 'rejected', 'settling', 'awaiting_goods', 'goods_received', 'not_returned', 'closed'],
    { received: ['rejected', 'settling', 'awaiting_goods'], awaiting_goods: ['goods_received', 'not_returned'], settling: ['closed'], goods_received: ['closed'] }],
  'reorder_proposal.state': [['proposed', 'approved', 'rejected', 'started'], undefined],
};

test('S2.1 T5 — `states:` / `transitions:` on the four lifecycle attributes (D-67, the graph of 17)', () => {
  const got = {};
  for (const e of defs.filter((d) => d.kind === 'entity')) {
    for (const a of e.attributes ?? []) {
      if (!a.states) continue;
      got[`${e.name}.${a.name}`] = [a.states, a.transitions ? Object.fromEntries(a.transitions.map((t) => [t.from, t.to])) : undefined];
    }
  }
  assert.deepEqual(got, LIFECYCLES);
});

test('S2.1 T5 — every value a lifecycle declares has a value label, and every value label is a declared state', () => {
  for (const [ref, [states]] of Object.entries(LIFECYCLES)) {
    const [entity, attribute] = ref.split('.');
    const a = defs.find((d) => d.kind === 'entity' && d.name === entity).attributes.find((x) => x.name === attribute);
    const labelled = (a.valueLabels?.entries ?? []).map((e) => e.key).sort();
    assert.deepEqual(labelled, [...states].sort(), ref);
  }
});


test('S2.3 — the Server roots exclude the ops authoring stubs', async () => {
  assert.ok(docsOf(project).every((d) => d.packageDecl?.name !== 'automation.ops'));
  assert.ok(!ofKind('entity').has('deployment'));
  const manifest = await readFile(path.join(hartlandRoot, 'modeler.toml'), 'utf8');
  assert.match(manifest, /extra-model-roots = \["model", "automation", "authoring-stubs"\]/);
  const stub = await readFile(path.join(hartlandRoot, 'authoring-stubs/automation/ops/automation-ops.ttrm'), 'utf8');
  assert.match(stub, /package automation\.ops/);
});
