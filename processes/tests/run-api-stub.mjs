// AU-hartland P3J (D-250, D-253) — the run API's `perform` and `outcome` as the Server reads their bodies, so a local
// check cannot pass a body bp-dsk refuses (S4.1x Found 1: only a stub ever accepted `keys: [200117749]`).
//
// Modelled on ttr-server services/automation (master): `writer/Perform.kt` — `PerformRequest { keys: List<JsonObject>?,
// group }`, `OutcomeRequest { outcomes: List<OutcomeItem { key: JsonObject, status, at, detail? }> }`,
// `OUTCOMES = delivered | failed | skipped` — and `api/Errors.kt`: a body that does not decode is a Ktor
// BadRequestException, answered `400 {error: {code: "bad-request", message}}`.
//
// Also: a tiny Spin shim (S, prop, append, value, elements, toString) to evaluate the C7 payload expressions the
// exporter emits, so the spec checks the body the engine would send, not the expression's text.

const RUN_ACTION = /^\/automation\/runs\/[^/]+\/actions\/(\w+)\/(perform|outcome)$/;
const OUTCOMES = ['delivered', 'failed', 'skipped'];

const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

function refused(message) {
  return { status: 400, body: { error: { code: 'bad-request', message } } };
}

const undecodable = (cls) => refused(`Failed to convert request body to class org.tatrman.automation.writer.${cls}`);

/** The Server's answer to `POST <path>` with the JSON `body`; `null` for a path this stub does not model. */
export function answer(path, body) {
  const m = path.match(RUN_ACTION);
  if (!m) return null;
  const [, action, verb] = m;
  if (verb === 'perform') {
    if (!isObject(body)) return undecodable('PerformRequest');
    const { keys } = body;
    if (keys != null && !(Array.isArray(keys) && keys.every(isObject))) return undecodable('PerformRequest');
    return { status: 200, body: { performed: (keys ?? []).map((key) => ({ key, batchRows: [1] })), skipped: [] } };
  }
  if (!isObject(body) || !Array.isArray(body.outcomes)) return undecodable('OutcomeRequest');
  for (const o of body.outcomes) {
    if (!isObject(o) || !isObject(o.key) || typeof o.status !== 'string' || typeof o.at !== 'string') {
      return undecodable('OutcomeRequest');
    }
  }
  if (body.outcomes.some((o) => !OUTCOMES.includes(o.status))) {
    return refused(`an outcome is one of [${OUTCOMES.join(', ')}]`);
  }
  return { status: 200, body: { action, outcomes: body.outcomes.length } };
}

// ── Spin, as far as the emitted payloads use it ─────────────────────────────────────────────────────────────────

class SpinNode {
  constructor(v) { this.v = v; }
  prop(name, ...set) {
    if (set.length === 0) {
      const x = this.v?.[name];
      if (x === undefined) throw new Error(`SPIN/JACKSON-JSON: Unable to find '${name}'`);
      return new SpinNode(x);
    }
    this.v[name] = unwrap(set[0]);
    return this;
  }
  append(x) { this.v.push(unwrap(x)); return this; }
  value() { return this.v; }
  stringValue() { return String(this.v); }
  numberValue() { return Number(this.v); }
  elements() { return this.v.map((x) => new SpinNode(x)); }
  hasProp(name) { return isObject(this.v) && name in this.v; }
  isNull() { return this.v === null; }
  toString() { return JSON.stringify(this.v); }
}

const unwrap = (x) => (x instanceof SpinNode ? x.v : x);

/** A row whose every column holds `value` (the key column is whatever the exporter reads). */
export function anyRow(value) {
  return new SpinNode(new Proxy({}, { get: (_, k) => (typeof k === 'string' ? value : undefined), has: () => true }));
}

/** Evaluate a `${…}` expression of the exporter's C7 dialect with the given variables. */
export function evaluate(expression, vars) {
  const m = expression.trim().match(/^\$\{([\s\S]*)\}$/);
  if (!m) throw new Error(`not an expression: ${expression}`);
  const scope = {
    S: (json) => new SpinNode(JSON.parse(json)),
    dateTime: () => ({ toString: () => '2026-11-19T09:00:00.000+01:00' }),
    ...vars,
  };
  return new Function(...Object.keys(scope), `return (${m[1]});`)(...Object.values(scope));
}
