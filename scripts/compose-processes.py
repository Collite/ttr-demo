#!/usr/bin/env python3
"""AU-hartland P4·S4.1 — compose the authored processes from the exporter's per-deployment skeletons (⚑20-1).

    python3 scripts/compose-processes.py [--set cz] [--check]

Reads `processes/sets.json` (the deployment set of one cluster) and the skeletons under `exports/<deployment>/`
(`just automation-export <set>` writes them), and writes `processes/<set>/<process>.bpmn`. `--check` writes nothing and
exits 1 when a committed process differs from what the exports compose to (the drift gate, like check-recipe-drift).

Why a composer, not a hand drawing: the skeleton of a deployment is the whole run chain (Open → evaluate → status →
routes → close → approvals → answer), ~200 KB of generated BPMN that every toolchain move regenerates. The analyst's part
is small and stable — where the process starts, what happens when a confirmation lapses, how the batch's notices go
out — so it is written here once, as named transforms over the skeleton, and re-applied to every re-export. Everything
the skeleton carries is kept as emitted (no hidden input is edited: the stage's fence); the composer only
  * renames the process, and gives it its start (a message or a timer);
  * adds, around each approval user task, the due date, the lapse (a timer boundary → a typed `perform`), the
    one-open-approval-per-key guard (D-98) and the task-visible variables Hebe reads (HE-8);
  * adds the batch digest (D-148) and the recipients of the send tasks;
  * stitches several skeletons into one per-line flow (H-2, `return_request`).
Each transform is named in the element ids it adds (`s41_…`), so `processes/tests/processes.test.mjs` can tell the
authored layer from the emitted one. Stdlib only.
"""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "camunda": "http://camunda.org/schema/1.0/bpmn",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "di": "http://www.omg.org/spec/DD/20100524/DI",
    "modeler": "http://camunda.org/schema/modeler/1.0",
    "ttr": "https://tatrman.org/schema/automation-export/1",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}
for _p, _u in NS.items():
    ET.register_namespace(_p, _u)


def q(name: str) -> str:
    prefix, local = name.split(":")
    return f"{{{NS[prefix]}}}{local}"


B, C = "bpmn", "camunda"
WORKING_DAYS_GROOVY = """\
// AU-hartland S4.1 (authored): the confirmation's due date — `def action @ACTION@ {{ due: @DAYS@ working_days }}`.
// A working day is not a weekend and not a holiday of the world (D-82, contracts §1: date_dim.d_working_day); the
// holidays are the world's public-holiday rules of data/calendar/calendar.sql (world @WORLD@), counted on the Prague
// clock from the engine's clock — the one the boundary timer is due on. A process variable ttrApprovalDueOverride
// (an ISO-8601 duration, e.g. PT2M) replaces it: the shortened lapse of a certification walk.
def zone = java.time.ZoneId.of('Europe/Prague')
def now = java.time.ZonedDateTime.ofInstant(org.cibseven.bpm.engine.impl.util.ClockUtil.getCurrentTime().toInstant(), zone)
def fixedDays = [@FIXED@] as Set
def easterOffsets = [@EASTER@]
def easter = {{ int y ->
    int a = y % 19, b = y.intdiv(100), c = y % 100, d = b.intdiv(4), e = b % 4, f = (b + 8).intdiv(25)
    int g = (b - f + 1).intdiv(3), h = (19 * a + b - d - g + 15) % 30, i = c.intdiv(4), k = c % 4
    int l = (32 + 2 * e + 2 * i - h - k) % 7, m = (a + 11 * h + 22 * l).intdiv(451)
    java.time.LocalDate.of(y, (h + l - 7 * m + 114).intdiv(31), (h + l - 7 * m + 114) % 31 + 1)
}}
def workingDay = {{ java.time.LocalDate day ->
    if (day.getDayOfWeek().getValue() > 5) return false
    if (fixedDays.contains(String.format('%02d-%02d', day.getMonthValue(), day.getDayOfMonth()))) return false
    def e = easter(day.getYear())
    return !easterOffsets.any {{ day == e.plusDays(it as long) }}
}}
def override = execution.getVariable('ttrApprovalDueOverride')
def due = now
if (override != null && override.toString().trim()) {{
    due = now.plus(java.time.Duration.parse(override.toString().trim()))
}} else {{
    int left = @DAYS@
    while (left > 0) {{
        due = due.plusDays(1)
        if (workingDay(due.toLocalDate())) left--
    }}
}}
execution.setVariableLocal('ttrApprovalDue', java.util.Date.from(due.toInstant()))
"""
CALENDAR_SQL = ROOT / "data" / "calendar" / "calendar.sql"


def world_holidays(world: str) -> tuple[list[str], list[int]]:
    """The world's public-holiday rules, read from data/calendar/calendar.sql (the one source date_dim.d_holiday is
    written from): its fixed (month, day) list and its Easter offsets. Only rules of that shape are drawn — a world
    whose holidays move by weekday (us: observed days, n-th Mondays) stops the composer."""
    sql = CALENDAR_SQL.read_text(encoding="utf-8")
    fixed = re.search(r"\(VALUES ((?:\(\d+, \d+\),?\s*)+)\) f\(m, dd\)\s*WHERE :'world' = '" + world + "'", sql)
    easter = re.search(r"cal_easter\(y\) \+ x FROM _cal_year, \(VALUES ((?:\(-?\d+\),? ?)+)\) e\(x\) WHERE :'world' = '"
                       + world + "'", sql)
    if not fixed or not easter or f"WHERE :'world' = '{world}'" in sql.replace(fixed.group(0), "").replace(easter.group(0), ""):
        raise SystemExit(f"{CALENDAR_SQL.relative_to(ROOT)}: the holidays of world {world!r} are not fixed days + "
                         "Easter offsets only — the due-date script cannot draw them")
    days = [f"{int(m):02d}-{int(d):02d}" for m, d in re.findall(r"\((\d+), (\d+)\)", fixed.group(1))]
    offsets = [int(x) for x in re.findall(r"\((-?\d+)\)", easter.group(1))]
    return days, offsets


def due_script(action: str, days: int, world: str) -> str:
    fixed, offsets = world_holidays(world)
    src = WORKING_DAYS_GROOVY.replace("{{", "{").replace("}}", "}")
    return (src.replace("@ACTION@", action).replace("@DAYS@", str(days)).replace("@WORLD@", world)
            .replace("@FIXED@", ", ".join(f"'{d}'" for d in fixed)).replace("@EASTER@", ", ".join(map(str, offsets))))


TASK_VISIBLE_GROOVY = """\
// AU-hartland S4.1 (authored): what Hebe and the D-98 guard read from the task itself (HE-8): the action and its key.
task.setVariableLocal('ttr_action', '{action}')
task.setVariableLocal('ttr_about', String.valueOf(task.getVariable('ttrKey')))
"""
RECIPIENTS_GROOVY = """\
// AU-hartland S4.1 (authored): the send tasks' recipients (the skeleton reads TTR_MAIL_RECIPIENTS["role.<r>"]);
// one address per role of the deployment set (processes/sets.json). A caller may pass its own map.
if (execution.getVariable('TTR_MAIL_RECIPIENTS') == null) {{
    def variables
    try {{ variables = Class.forName('org.cibseven.bpm.engine.variable.Variables') }}
    catch (ClassNotFoundException e) {{ variables = Class.forName('org.camunda.bpm.engine.variable.Variables') }}
    def recipients = new LinkedHashMap({mail})
    execution.setVariable('TTR_MAIL_RECIPIENTS',
        variables.objectValue(recipients).serializationDataFormat('application/json').create())
}}
"""
HTTP_RESULT_GROOVY = """\
def BpmnError; try {{ BpmnError = Class.forName('org.cibseven.bpm.engine.delegate.BpmnError') }} catch (ClassNotFoundException e) {{ BpmnError = Class.forName('org.camunda.bpm.engine.delegate.BpmnError') }}
def code = ((Number) statusCode).intValue()
if (code == 409) throw BpmnError.getConstructor(String, String).newInstance('TTR_STALE', '{what}: HTTP 409')
if (code >= 400 && code < 500 && code != 408 && code != 429) throw BpmnError.getConstructor(String, String).newInstance('TTR_REFUSED', '{what}: HTTP ' + code + ': ' + response.toString().take(256))
if (code < 200 || code >= 300) throw new IllegalStateException('{what}: HTTP ' + code)
def SpinClass; try {{ SpinClass = Class.forName('org.cibseven.spin.Spin') }} catch (ClassNotFoundException e) {{ SpinClass = Class.forName('org.camunda.spin.Spin') }}
return SpinClass.JSON(response)
"""


def http_result(what: str) -> str:
    return HTTP_RESULT_GROOVY.format(what=what.replace("\\", "\\\\").replace("'", "\\'"))


class Bpmn:
    """One skeleton, loaded for editing: the tree, an id index, the parent map and the diagram plane."""

    def __init__(self, path: pathlib.Path):
        self.path = path
        self.tree = ET.parse(path)
        self.defs = self.tree.getroot()
        self.reindex()

    def reindex(self) -> None:
        self.byid = {e.get("id"): e for e in self.defs.iter() if e.get("id")}
        self.parent = {c: p for p in self.defs.iter() for c in p}

    @property
    def process(self) -> ET.Element:
        return self.defs.find(q("bpmn:process"))

    @property
    def plane(self) -> ET.Element:
        return self.defs.find(f"{q('bpmndi:BPMNDiagram')}/{q('bpmndi:BPMNPlane')}")

    def named(self, tag: str, name: str, scope: ET.Element | None = None) -> ET.Element:
        found = [e for e in (scope if scope is not None else self.defs).iter(q(tag)) if e.get("name") == name]
        if len(found) != 1:
            raise SystemExit(f"{self.path}: expected one {tag} named {name!r}, found {len(found)}")
        return found[0]

    def flows_into(self, target: str) -> list[ET.Element]:
        return [f for f in self.defs.iter(q("bpmn:sequenceFlow")) if f.get("targetRef") == target]

    def flows_from(self, source: str) -> list[ET.Element]:
        return [f for f in self.defs.iter(q("bpmn:sequenceFlow")) if f.get("sourceRef") == source]

    def bounds(self, element_id: str) -> tuple[float, float, float, float]:
        for s in self.plane.iter(q("bpmndi:BPMNShape")):
            if s.get("bpmnElement") == element_id:
                b = s.find(q("dc:Bounds"))
                return tuple(float(b.get(k)) for k in ("x", "y", "width", "height"))  # type: ignore[return-value]
        raise SystemExit(f"{self.path}: no diagram shape for {element_id}")

    # ---- building -------------------------------------------------------------------------------------------------
    def add(self, scope: ET.Element, tag: str, attrs: dict, *, before: ET.Element | None = None) -> ET.Element:
        e = ET.Element(q(tag), {k: v for k, v in attrs.items() if v is not None})
        if before is not None:
            scope.insert(list(scope).index(before), e)
        else:
            # keep sequence flows after the nodes, as the emitter writes them
            flows = [i for i, c in enumerate(scope) if c.tag == q("bpmn:sequenceFlow")]
            if tag != "bpmn:sequenceFlow" and flows:
                scope.insert(flows[0], e)
            else:
                scope.append(e)
        if e.get("id"):
            self.byid[e.get("id")] = e
            self.parent[e] = scope
        return e

    def shape(self, element_id: str, x: float, y: float, w: float, h: float) -> None:
        s = ET.SubElement(self.plane, q("bpmndi:BPMNShape"), {"bpmnElement": element_id, "id": f"{element_id}_di"})
        ET.SubElement(s, q("dc:Bounds"), {"height": f"{h:g}", "width": f"{w:g}", "x": f"{x:g}", "y": f"{y:g}"})

    def edge(self, flow_id: str, points: list[tuple[float, float]]) -> None:
        e = ET.SubElement(self.plane, q("bpmndi:BPMNEdge"), {"bpmnElement": flow_id, "id": f"{flow_id}_di"})
        for x, y in points:
            ET.SubElement(e, q("di:waypoint"), {"x": f"{x:g}", "y": f"{y:g}"})

    def reroute_edge(self, flow_id: str, points: list[tuple[float, float]]) -> None:
        for e in self.plane.iter(q("bpmndi:BPMNEdge")):
            if e.get("bpmnElement") == flow_id:
                for w in list(e):
                    e.remove(w)
                for x, y in points:
                    ET.SubElement(e, q("di:waypoint"), {"x": f"{x:g}", "y": f"{y:g}"})
                return

    def flow(self, scope: ET.Element, fid: str, source: str, target: str, *, name: str | None = None,
             condition: str | None = None) -> ET.Element:
        f = self.add(scope, "bpmn:sequenceFlow", {"id": fid, "name": name, "sourceRef": source, "targetRef": target})
        if condition is not None:
            c = ET.SubElement(f, q("bpmn:conditionExpression"), {q("xsi:type"): "bpmn:tFormalExpression"})
            c.text = condition
        self._link(source, fid, "outgoing")
        self._link(target, fid, "incoming")
        return f

    def _link(self, node_id: str, flow_id: str, kind: str) -> None:
        node = self.byid[node_id]
        el = ET.Element(q(f"bpmn:{kind}"))
        el.text = flow_id
        # the schema order is extensionElements, incoming*, outgoing*, then the rest (C7 validates it on deploy)
        before = (q("bpmn:extensionElements"), q("bpmn:incoming")) if kind == "incoming" else \
            (q("bpmn:extensionElements"), q("bpmn:incoming"), q("bpmn:outgoing"))
        pos = 0
        for i, c in enumerate(list(node)):
            if c.tag in before:
                pos = i + 1
        node.insert(pos, el)

    def retarget(self, flow: ET.Element, new_target: str) -> None:
        old = flow.get("targetRef")
        for inc in self.byid[old].findall(q("bpmn:incoming")):
            if inc.text == flow.get("id"):
                self.byid[old].remove(inc)
        flow.set("targetRef", new_target)
        self._link(new_target, flow.get("id"), "incoming")

    def resource(self, out: pathlib.Path) -> bytes:
        # every sequence flow drawn: a flow the composer added without waypoints gets a straight edge
        drawn = {e.get("bpmnElement") for e in self.plane.iter(q("bpmndi:BPMNEdge"))}
        centre = {}
        for s in self.plane.iter(q("bpmndi:BPMNShape")):
            b = s.find(q("dc:Bounds"))
            centre[s.get("bpmnElement")] = (float(b.get("x")) + float(b.get("width")) / 2,
                                            float(b.get("y")) + float(b.get("height")) / 2)
        for f in self.defs.iter(q("bpmn:sequenceFlow")):
            if f.get("id") not in drawn and f.get("sourceRef") in centre and f.get("targetRef") in centre:
                self.edge(f.get("id"), [centre[f.get("sourceRef")], centre[f.get("targetRef")]])
        ET.indent(self.tree, space="  ")
        body = ET.tostring(self.defs, encoding="unicode")
        return ('<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n").encode("utf-8")


def ext(node: ET.Element) -> ET.Element:
    found = node.find(q("bpmn:extensionElements"))
    if found is None:
        found = ET.Element(q("bpmn:extensionElements"))
        node.insert(0, found)
    return found


def groovy(parent: ET.Element, tag: str, attrs: dict, source: str) -> ET.Element:
    el = ET.SubElement(parent, q(tag), attrs)
    s = ET.SubElement(el, q("camunda:script"), {"scriptFormat": "groovy"})
    s.text = source
    return el


def input_value(node: ET.Element, name: str) -> str | None:
    io = node.find(f"{q('bpmn:extensionElements')}/{q('camunda:inputOutput')}")
    if io is None:
        return None
    for p in io.findall(q("camunda:inputParameter")):
        if p.get("name") == name:
            return p.text
    return None


def egress_of(doc: Bpmn) -> str:
    """The executor's egress base (…/automation), as the skeleton's Open calls it."""
    for p in doc.defs.iter(q("camunda:inputParameter")):
        m = re.search(r'"(https?://[^"]+?/automation)/recipes/', p.text or "")
        if p.get("name") == "url" and m:
            return m.group(1)
    raise SystemExit(f"{doc.path}: no Open url to read the egress from")


def deployment_of(doc: Bpmn) -> str:
    contract = doc.process.find(f"{q('bpmn:extensionElements')}/{q('ttr:contract')}")
    return json.loads(contract.text)["deployment"]


# ---- the transforms ----------------------------------------------------------------------------------------------

def rename(doc: Bpmn, pid: str, name: str) -> None:
    doc.process.set("id", pid)
    doc.process.set("name", name)
    doc.plane.set("bpmnElement", pid)


def recipients(doc: Bpmn, mail: dict[str, str]) -> None:
    """A process start listener sets TTR_MAIL_RECIPIENTS (the skeleton's send tasks read it)."""
    # the skeleton looks up "role.sales"; the digest groups by the wiring's `who` literal — register both spellings
    both = {}
    for k, v in mail.items():
        both[k] = v
        if k.startswith("role."):
            both.setdefault(k[len("role."):], v)
    literal = "[" + ", ".join(f"'{k}': '{v}'" for k, v in both.items()) + "]"
    groovy(ext(doc.process), "camunda:executionListener", {"event": "start"}, RECIPIENTS_GROOVY.format(mail=literal))


def repairs(doc: Bpmn) -> None:
    """The skeleton's repair tasks ("export outdated", "run refused; inspect evidence") name no group, so only an engine
    admin would see them: they go to ops (`def role ops`, hartland-ops — admin on the engine, D-161)."""
    for task in doc.defs.iter(q("bpmn:userTask")):
        if task.get(q("camunda:candidateGroups")) is None and task.get(q("camunda:assignee")) is None:
            task.set(q("camunda:candidateGroups"), "hartland-ops")


def message_start(doc: Bpmn, start_label: str, message: str) -> ET.Element:
    start = doc.named("bpmn:startEvent", "start with ttrInput key", doc.process)
    start.set("name", start_label)
    mid = f"s41_message_{message}"
    msg = ET.Element(q("bpmn:message"), {"id": mid, "name": message})
    errors = doc.defs.findall(q("bpmn:error"))
    doc.defs.insert(list(doc.defs).index(errors[-1]) + 1 if errors else 0, msg)
    ET.SubElement(start, q("bpmn:messageEventDefinition"), {"id": f"{mid}_definition", "messageRef": mid})
    return start


BUSINESS_KEY_GROOVY = """\
// AU-hartland S4.1 (authored): a timer start carries no business key, and every Open records engine.businessKey
// (the skeleton's README: "start with a nonblank business key") — the batch's key is the process and its Prague day.
if (!execution.getProcessBusinessKey()) {{
    execution.setProcessBusinessKey('{pid}:' + java.time.LocalDate.now(java.time.ZoneId.of('Europe/Prague')).toString())
}}
"""


def timer_start(doc: Bpmn, start_label: str, cron: str) -> ET.Element:
    start = doc.named("bpmn:startEvent", "start with ttrInput key", doc.process)
    start.set("name", start_label)
    groovy(ext(doc.process), "camunda:executionListener", {"event": "start"},
           BUSINESS_KEY_GROOVY.format(pid=doc.process.get("id")))
    t = ET.SubElement(start, q("bpmn:timerEventDefinition"), {"id": "s41_morning_timer"})
    ET.SubElement(t, q("bpmn:timeCycle"), {q("xsi:type"): "bpmn:tFormalExpression"}).text = cron
    return start


# D-98 as a read: a committed open task of the action for the key. It is not a lock — two instances that reach it at
# the same moment both read zero and both open a task (review-365 B3, reproduced 3/10 on CIB seven). Atomic needs a
# per-key primitive the BPMN does not have (a unique constraint or a lock): S4.1 Found L hands it over.
PENDING = ("execution.processEngineServices.taskService.createTaskQuery().active()"
           ".taskVariableValueEquals('ttr_action', '{action}').taskVariableValueEquals('ttr_about', {key}).count() > 0")


def start_guard(doc: Bpmn, start: ET.Element, action: str, key_expr: str, labels: dict) -> None:
    """D-98 at the start: an order whose confirmation is already open anywhere (this process or the morning batch)
    is not decided again — the instance ends at once."""
    out = doc.flows_from(start.get("id"))[0]
    first = out.get("targetRef")
    gw = doc.add(doc.process, "bpmn:exclusiveGateway",
                 {"id": "s41_pending_guard", "name": labels["pending_q"], "default": "s41_pending_no"})
    end = doc.add(doc.process, "bpmn:endEvent", {"id": "s41_pending_end", "name": labels["pending_end"]})
    doc.retarget(out, gw.get("id"))
    doc.flow(doc.process, "s41_pending_no", gw.get("id"), first, name=labels["no"])
    doc.flow(doc.process, "s41_pending_yes", gw.get("id"), end.get("id"), name=labels["yes"],
             condition="${" + PENDING.format(action=action, key=key_expr) + "}")
    sx, sy, sw, sh = doc.bounds(start.get("id"))
    doc.shape(gw.get("id"), sx + sw + 10, sy - 7, 50, 50)
    doc.shape(end.get("id"), sx + sw + 17, sy + 90, 36, 36)
    doc.reroute_edge(out.get("id"), [(sx + sw, sy + sh / 2), (sx + sw + 10, sy + sh / 2)])
    doc.edge("s41_pending_no", [(sx + sw + 60, sy + sh / 2), (sx + sw + 90, sy + sh / 2)])
    doc.edge("s41_pending_yes", [(sx + sw + 35, sy + 43), (sx + sw + 35, sy + 90)])


def approvals(doc: Bpmn, lapses: dict, labels: dict, egress: str, deployment: str, world: str) -> list[str]:
    """Every approval user task of the skeleton (a userTask with a ttrAction input) gets the D-98 guard, its due date,
    the task-visible variables and — when `lapses` names the action — a timer boundary that performs the fallback."""
    done = []
    for task in list(doc.defs.iter(q("bpmn:userTask"))):
        raw = input_value(task, "ttrAction")
        if not raw or not (doc.parent[task].get("name") or "").startswith("ask each "):
            continue
        action = re.fullmatch(r'\$\{"(\w+)"\}', raw).group(1)
        key_raw = input_value(task, "ttrKey")                       # ${ttrRow.prop("order_number").value()}
        key_col = re.search(r'prop\("(\w+)"\)', key_raw).group(1)
        spec = lapses.get(action)
        scope = doc.parent[task]
        tid = task.get("id")
        n = f"s41_{action}"
        if spec and spec.get("label"):
            task.set("name", spec["label"])
        task.set(q("camunda:dueDate"), "${ttrApprovalDue}")
        groovy(ext(task), "camunda:taskListener", {"event": "create"}, TASK_VISIBLE_GROOVY.format(action=action))

        # the guard and the due date sit on the flow that opens the task
        into = doc.flows_into(tid)
        if len(into) != 1:
            raise SystemExit(f"{doc.path}: {tid} has {len(into)} incoming flows")
        complete = doc.named("bpmn:exclusiveGateway", f"{action} complete", scope)
        guard = doc.add(scope, "bpmn:exclusiveGateway",
                        {"id": f"{n}_guard", "name": labels["pending_q"], "default": f"{n}_guard_no"})
        due = doc.add(scope, "bpmn:scriptTask", {"id": f"{n}_due", "name": labels["due"], "scriptFormat": "groovy"})
        ET.SubElement(due, q("bpmn:script")).text = due_script(action, spec["days"] if spec else 2, world)
        doc.retarget(into[0], guard.get("id"))
        doc.flow(scope, f"{n}_guard_no", guard.get("id"), due.get("id"), name=labels["no"])
        doc.flow(scope, f"{n}_guard_yes", guard.get("id"), complete.get("id"), name=labels["yes"],
                 condition="${" + PENDING.format(action=action, key=f'ttrRow.prop("{key_col}").value().toString()') + "}")
        doc.flow(scope, f"{n}_due_task", due.get("id"), tid)
        tx, ty, tw, th = doc.bounds(tid)
        doc.shape(guard.get("id"), tx - 190, ty + th / 2 - 25 + 130, 50, 50)
        doc.shape(due.get("id"), tx - 110, ty + 130, 90, th)
        doc.edge(f"{n}_guard_no", [(tx - 140, ty + 130 + th / 2), (tx - 110, ty + 130 + th / 2)])
        doc.edge(f"{n}_due_task", [(tx - 20, ty + 130 + th / 2), (tx + tw / 2, ty + 130 + th / 2), (tx + tw / 2, ty + th)])
        cx, cy, cw, ch = doc.bounds(complete.get("id"))
        doc.edge(f"{n}_guard_yes", [(tx - 165, ty + 130 + th / 2 + 25), (tx - 165, ty + 260), (cx + cw / 2, ty + 260),
                                    (cx + cw / 2, cy + ch)])
        doc.reroute_edge(into[0].get("id"), [(tx - 260, ty + 130 + th / 2), (tx - 190, ty + 130 + th / 2)])

        if spec:
            perform = spec["perform"]
            timer = doc.add(scope, "bpmn:boundaryEvent",
                            {"id": f"{n}_lapsed", "name": labels["lapsed"], "attachedToRef": tid, "cancelActivity": "true"})
            td = ET.SubElement(timer, q("bpmn:timerEventDefinition"), {"id": f"{n}_lapsed_timer"})
            ET.SubElement(td, q("bpmn:timeDate"), {q("xsi:type"): "bpmn:tFormalExpression"}).text = "${ttrApprovalDue}"
            act = doc.add(scope, "bpmn:serviceTask",
                          {"id": f"{n}_perform", "name": spec["perform_label"], q("camunda:asyncBefore"): "true"})
            key_json = "".join(f'.prop("{k}", ttrRow.prop("{v}"))' for k, v in perform["key"].items())
            params_json = "".join(f'.prop("{k}", "{v}")' for k, v in perform.get("params", {}).items())
            payload = ('${S(\'{}\').prop("key", S(\'{}\')' + key_json + ').prop("params", S(\'{}\')' + params_json + ')'
                       '.prop("origin", "engine").prop("idempotencyKey", execution.processInstanceId.concat(":lapsed:")'
                       f'.concat(ttrRow.prop("{key_col}").toString())).toString()}}')
            e = ext(act)
            conn = ET.SubElement(e, q("camunda:connector"))
            ET.SubElement(conn, q("camunda:connectorId")).text = "http-connector"
            io = ET.SubElement(conn, q("camunda:inputOutput"))
            ET.SubElement(io, q("camunda:inputParameter"), {"name": "method"}).text = "POST"
            ET.SubElement(io, q("camunda:inputParameter"), {"name": "url"}).text = \
                f'${{"{egress}/deployments/{deployment}/actions/{perform["action"]}/perform"}}'
            hdr = ET.SubElement(io, q("camunda:inputParameter"), {"name": "headers"})
            m = ET.SubElement(hdr, q("camunda:map"))
            ET.SubElement(m, q("camunda:entry"), {"key": "Content-Type"}).text = "application/json"
            ET.SubElement(io, q("camunda:inputParameter"), {"name": "payload"}).text = payload
            groovy(io, "camunda:outputParameter", {"name": "ttrLapsed"},
                   http_result(f"perform {perform['action']} after the lapse"))
            ET.SubElement(io, q("camunda:outputParameter"), {"name": "ttrLapsedCode"}).text = "${statusCode}"
            ET.SubElement(e, q("camunda:failedJobRetryTimeCycle")).text = "R3/PT15S"
            doc.flow(scope, f"{n}_lapsed_perform", timer.get("id"), act.get("id"))
            doc.flow(scope, f"{n}_perform_done", act.get("id"), complete.get("id"))
            doc.shape(timer.get("id"), tx + tw / 2 - 18, ty + th - 18, 36, 36)
            doc.shape(act.get("id"), tx + tw / 2 + 40, ty + th + 40, 100, 80)
            doc.edge(f"{n}_lapsed_perform", [(tx + tw / 2, ty + th + 18), (tx + tw / 2, ty + th + 80), (tx + tw / 2 + 40, ty + th + 80)])
            doc.edge(f"{n}_perform_done", [(tx + tw / 2 + 140, ty + th + 80), (cx + cw / 2, ty + th + 80), (cx + cw / 2, cy + ch)])
        done.append(action)
    return done


def digest(doc: Bpmn, labels: dict, egress: str, lang: str) -> None:
    """D-148: the batch's notices go out as one digest per `who` group after the close — GET /runs/{id}/digest, one
    send task per group. The per-row send of the skeleton is bypassed in a batch (its outcome is still posted)."""
    for send in list(doc.defs.iter(q("bpmn:sendTask"))):
        scope = doc.parent[send]
        into = doc.flows_into(send.get("id"))
        out = doc.flows_from(send.get("id"))
        # the conditional flow into the send task now goes straight to what followed it ("notify delivered")
        for f in into:
            doc.retarget(f, out[0].get("targetRef"))
        for f in out:
            scope.remove(f)
            for inc in doc.byid[f.get("targetRef")].findall(q("bpmn:incoming")):
                if inc.text == f.get("id"):
                    doc.byid[f.get("targetRef")].remove(inc)
        scope.remove(send)
        for s in list(doc.plane):
            if s.get("bpmnElement") in {send.get("id"), *(f.get("id") for f in out)}:
                doc.plane.remove(s)
    doc.reindex()

    end = doc.named("bpmn:endEvent", "complete", doc.process)
    into = doc.flows_into(end.get("id"))[0]
    fetch = doc.add(doc.process, "bpmn:serviceTask",
                    {"id": "s41_digest_fetch", "name": labels["digest_fetch"], q("camunda:asyncBefore"): "true"})
    e = ext(fetch)
    conn = ET.SubElement(e, q("camunda:connector"))
    ET.SubElement(conn, q("camunda:connectorId")).text = "http-connector"
    io = ET.SubElement(conn, q("camunda:inputOutput"))
    ET.SubElement(io, q("camunda:inputParameter"), {"name": "method"}).text = "GET"
    ET.SubElement(io, q("camunda:inputParameter"), {"name": "url"}).text = \
        f'${{"{egress}/runs/".concat(ttrAnchor).concat("/digest?action=notify&lang={lang}")}}'
    groovy(io, "camunda:outputParameter", {"name": "ttrDigest"}, http_result("the run digest"))
    ET.SubElement(e, q("camunda:failedJobRetryTimeCycle")).text = "R3/PT15S"

    send = doc.add(doc.process, "bpmn:sendTask", {"id": "s41_digest_send", "name": labels["digest_send"],
                                                    q("camunda:type"): "external", q("camunda:topic"): "TTR_CONN_MAIL"})
    se = ext(send)
    sio = ET.SubElement(se, q("camunda:inputOutput"))
    for name, value in (
        ("ttrRecipient", '${TTR_MAIL_RECIPIENTS[ttrDigestGroup.prop("who").stringValue()]}'),
        ("ttrText", '${ttrDigestGroup.prop("text").stringValue()}'),
        ("ttrHtml", '${ttrDigestGroup.prop("html").stringValue()}'),
        ("ttrAction", '${"notify"}'),
        ("ttrKey", '${ttrDigestGroup.prop("who").stringValue()}'),
    ):
        ET.SubElement(sio, q("camunda:inputParameter"), {"name": name}).text = value
    mi = ET.SubElement(send, q("bpmn:multiInstanceLoopCharacteristics"),
                       {"isSequential": "true", q("camunda:collection"): '${ttrDigest.prop("groups").elements()}',
                        q("camunda:elementVariable"): "ttrDigestGroup"})
    del mi
    doc.retarget(into, fetch.get("id"))
    doc.flow(doc.process, "s41_digest_fetched", fetch.get("id"), send.get("id"))
    doc.flow(doc.process, "s41_digest_sent", send.get("id"), end.get("id"))
    ex, ey, ew, eh = doc.bounds(end.get("id"))
    doc.shape(fetch.get("id"), ex, ey + 100, 100, 80)
    doc.shape(send.get("id"), ex + 140, ey + 100, 100, 80)
    doc.edge("s41_digest_fetched", [(ex + 100, ey + 140), (ex + 140, ey + 140)])
    doc.edge("s41_digest_sent", [(ex + 190, ey + 100), (ex + 190, ey + eh / 2), (ex + ew, ey + eh / 2)])


# ---- the processes ---------------------------------------------------------------------------------------------

LABELS = {
    "cs": {
        "pending_q": "Potvrzení už čeká?", "pending_end": "potvrzení už čeká", "yes": "ano", "no": "ne",
        "due": "Termín potvrzení", "lapsed": "Termín uplynul",
        "digest_fetch": "Souhrn běhu", "digest_send": "Odeslat souhrn skupině",
    },
    "en": {
        "pending_q": "Confirmation already pending?", "pending_end": "confirmation already pending", "yes": "yes",
        "no": "no", "due": "Confirmation due date", "lapsed": "Confirmation lapsed",
        "digest_fetch": "The run's digest", "digest_send": "Send the digest to the group",
    },
}
RELEASE_LAPSE = {
    "cs": {"label": "Potvrďte uvolnění objednávky ${ttrKey}", "perform_label": "Zadržet objednávku pro obchod"},
    "en": {"label": "Confirm the release of order ${ttrKey}", "perform_label": "Hold the order for Sales"},
}


def release_lapses(lang: str) -> dict:
    # `def action release_confirmed { due: 2 working_days }` → on the lapse `perform hold { order, department: Sales }`
    # (`20` §3: the analyst's fallback; D-168's typed perform).
    return {"release_confirmed": {"days": 2, **RELEASE_LAPSE[lang],
                                  "perform": {"action": "hold", "key": {"order": "order_number"},
                                              "params": {"department": "Sales"}}}}


def export_bpmn(deployment: str) -> pathlib.Path:
    found = sorted((ROOT / "exports" / deployment).glob("*.export/*.c7.bpmn"))
    if len(found) != 1:
        raise SystemExit(f"exports/{deployment}: expected one emitted *.c7.bpmn, found {len(found)} — "
                         f"run `just automation-export <set>`")
    return found[0]


def compose_release_order(s: dict) -> Bpmn:
    lang, labels = s["lang"], LABELS[s["lang"]]
    doc = Bpmn(export_bpmn(s["deployments"]["release_event"]))
    egress, deployment = egress_of(doc), deployment_of(doc)
    rename(doc, "release_order", "H-1 · uvolnění objednávky při založení" if lang == "cs" else "H-1 · release on placement")
    recipients(doc, s["mail"])
    start = message_start(doc, "objednávka založena" if lang == "cs" else "order placed", "order_placed")
    start_guard(doc, start, "release_confirmed", "ttrInput['key']['order_number'].toString()", labels)
    approvals(doc, release_lapses(lang), labels, egress, deployment, s["world"])
    return doc


def compose_release_morning(s: dict) -> Bpmn:
    lang, labels = s["lang"], LABELS[s["lang"]]
    doc = Bpmn(export_bpmn(s["deployments"]["release_morning"]))
    egress, deployment = egress_of(doc), deployment_of(doc)
    rename(doc, "release_morning", "H-1 · ranní uvolnění" if lang == "cs" else "H-1 · the morning release")
    recipients(doc, s["mail"])
    # 06:00 Prague = 05:00 UTC in winter: the engine's cron runs on its JVM zone (UTC on bp-dsk), and a C7 cron
    # carries no zone — in summer (CEST) this is 07:00 Prague.
    timer_start(doc, "každé ráno v 6:00 (SEČ)" if lang == "cs" else "every morning at 06:00 (CET)", "0 0 5 * * ?")
    approvals(doc, release_lapses(lang), labels, egress, deployment, s["world"])
    digest(doc, labels, egress, lang)
    return doc


# ---- H-2: one instance per return line, three skeletons stitched (`20` §4.4, D-147, D-171) ---------------------

def bypass(doc: Bpmn, node: ET.Element) -> None:
    """Take a node out of its flow: what came into it goes to what followed it; the node, its outgoing flow and their
    diagram elements go."""
    scope = doc.parent[node]
    into, out = doc.flows_into(node.get("id")), doc.flows_from(node.get("id"))
    if len(out) != 1:
        raise SystemExit(f"{doc.path}: cannot bypass {node.get('name')!r} with {len(out)} outgoing flows")
    nxt = out[0].get("targetRef")
    for f in into:
        doc.retarget(f, nxt)
    for inc in doc.byid[nxt].findall(q("bpmn:incoming")):
        if inc.text == out[0].get("id"):
            doc.byid[nxt].remove(inc)
    scope.remove(out[0])
    scope.remove(node)
    gone = {node.get("id"), out[0].get("id")} | {e.get("id") for e in node.iter() if e.get("id")}
    for s in list(doc.plane):
        if s.get("bpmnElement") in gone:
            doc.plane.remove(s)
    doc.reindex()


def http_task(doc: Bpmn, scope: ET.Element, tid: str, name: str, method: str, url: str, result: str, what: str,
              payload: str | None = None, tag: str = "bpmn:serviceTask") -> ET.Element:
    """An authored HTTP step to the egress, shaped like the skeleton's (async, R3/PT15S, 409 → TTR_STALE,
    other 4xx → TTR_REFUSED, 5xx → retry then incident)."""
    task = doc.add(scope, tag, {"id": tid, "name": name, q("camunda:asyncBefore"): "true"})
    e = ext(task)
    conn = ET.SubElement(e, q("camunda:connector"))
    ET.SubElement(conn, q("camunda:connectorId")).text = "http-connector"
    io = ET.SubElement(conn, q("camunda:inputOutput"))
    ET.SubElement(io, q("camunda:inputParameter"), {"name": "method"}).text = method
    ET.SubElement(io, q("camunda:inputParameter"), {"name": "url"}).text = url
    if payload is not None:
        hdr = ET.SubElement(io, q("camunda:inputParameter"), {"name": "headers"})
        ET.SubElement(ET.SubElement(hdr, q("camunda:map")), q("camunda:entry"), {"key": "Content-Type"}).text = "application/json"
        ET.SubElement(io, q("camunda:inputParameter"), {"name": "payload"}).text = payload
    groovy(io, "camunda:outputParameter", {"name": result}, http_result(what))
    ET.SubElement(e, q("camunda:failedJobRetryTimeCycle")).text = "R3/PT15S"
    return task


ROUND_GROOVY = """\
// AU-hartland S4.1 (authored): this round's port {{key, at}} — the line's key from the message that started the
// instance, and the round's clock: the `at` of the message that woke it (the driver sends the timeline's time), else
// now on the Prague clock. A fresh `at` per round: on-event runs deduplicate on it, so a reused one would replay.
def variables
try {{ variables = Class.forName('org.cibseven.bpm.engine.variable.Variables') }}
catch (ClassNotFoundException e) {{ variables = Class.forName('org.camunda.bpm.engine.variable.Variables') }}
def first = execution.getVariable('ttrInput')
def at = execution.getVariable('ttrEventAt')
if (at == null || !at.toString().trim()) at = java.time.OffsetDateTime.now(java.time.ZoneId.of('Europe/Prague')).toString()
execution.removeVariable('ttrEventAt')
def round = new LinkedHashMap([key: first['key'], at: at.toString()])
execution.setVariable('ttrInput', variables.objectValue(round).serializationDataFormat('application/json').create())
"""
CARE_BY_GROOVY = """\
// AU-hartland S4.1 (authored): who decided (D-168's `by`), as the engine saw the completion.
task.execution.setVariable('ttrCareBy', task.getAssignee())
"""
WAYS = ("refund_no_return", "replacement_no_return", "exchange", "refund_after_return")
WAY_LABELS = {
    "cs": {"refund_no_return": "Vrácení peněz bez vrácení zboží", "replacement_no_return": "Náhrada bez vrácení zboží",
           "exchange": "Výměna zboží", "refund_after_return": "Vrácení peněz po vrácení zboží"},
    "en": {"refund_no_return": "Refund, no return", "replacement_no_return": "Replacement, no return",
           "exchange": "Exchange", "refund_after_return": "Refund after the return"},
}
H2 = {
    "cs": {"name": "H-2 · reklamace řádku", "start": "reklamace přijata", "verdict": "Výsledek rozhodnutí",
           "way": "Způsob?", "care": "Rozhodněte o způsobu vyřízení řádku ${ttrInput['key']['line_id']}",
           "care_field": "Způsob vyřízení", "care_row": "Řádek pro péči", "care_perform": "Provést rozhodnutí péče",
           "care_way": "Zvolený způsob?", "instructions": "Pokyny k vrácení zákazníkovi", "rejected": "zamítnuto",
           "inbound_wait": "Čekat na příjem zboží", "receipt": "příjemka zaúčtována", "daily": "denně",
           "inbound": "Kontrola příjmu zboží", "inbound_round": "Kolo kontroly příjmu", "inbound_verdict": "Výsledek kontroly",
           "inbound_route": "Stav příjmu?", "not_returned": "zboží nevráceno",
           "settle_wait": "Čekat na vyrovnání", "settlement": "doklad vyrovnání zaúčtován",
           "settle": "Vyrovnání", "settle_round": "Kolo vyrovnání", "settle_verdict": "Výsledek vyrovnání",
           "settle_route": "Vyrovnáno?", "closed": "uzavřeno", "stopped": "zastaveno k opravě",
           "review": "Posuďte řádek reklamace ${ttrKey}", "other": "jinak"},
    "en": {"name": "H-2 · a return line", "start": "return requested", "verdict": "The decision",
           "way": "Which way?", "care": "Decide the way of return line ${ttrInput['key']['line_id']}",
           "care_field": "The way", "care_row": "The care row", "care_perform": "Perform care's decision",
           "care_way": "The chosen way?", "instructions": "Return instructions to the customer", "rejected": "rejected",
           "inbound_wait": "Wait for the goods", "receipt": "receipt posted", "daily": "daily",
           "inbound": "Monitor the inbound goods", "inbound_round": "Inbound round", "inbound_verdict": "The inbound verdict",
           "inbound_route": "Inbound state?", "not_returned": "not returned",
           "settle_wait": "Wait for the settlement", "settlement": "settlement posted",
           "settle": "Settle", "settle_round": "Settlement round", "settle_verdict": "The settlement verdict",
           "settle_route": "Settled?", "closed": "closed", "stopped": "stopped for repair",
           "review": "Review return line ${ttrKey}", "other": "otherwise"},
}


def has_route(verdict: str, route: str) -> str:
    return (f'${{{verdict}.prop("verdict").prop("routes").hasProp("{route}") && '
            f'{verdict}.prop("verdict").prop("routes").prop("{route}").prop("rowCount").numberValue() > 0}}')


def review_groups() -> dict[str, str]:
    """route → the Keycloak group of `review { who: role.<r> }` in the recipes (monitor_inbound, settle)."""
    groups = dict(re.findall(r'def role (\w+)\s*\{\s*resolve:\s*keycloak_group\s*"([^"]+)"',
                             (ROOT / "automation" / "automation.ttrm").read_text(encoding="utf-8")))
    found = {}
    for recipe in ("monitor_inbound", "settle"):
        text = (ROOT / "automation" / recipe / f"{recipe}.ttrp").read_text(encoding="utf-8")
        for route, role in re.findall(r"\w+\.(\w+)\s*->\s*review\s*\{\s*who:\s*role\.(\w+)", text):
            found[route] = groups[role]
    return found


def reviews(doc: Bpmn, labels: dict) -> None:
    """The recipes' `review` rows render as user tasks with no candidate group: give each its route's group."""
    groups = review_groups()
    for task in doc.defs.iter(q("bpmn:userTask")):
        if input_value(task, "ttrAction") != '${"review"}':
            continue
        route = re.fullmatch(r"each (\w+) row", doc.parent[task].get("name") or "").group(1)
        task.set(q("camunda:candidateGroups"), groups[route])
        task.set("name", labels["review"])
        groovy(ext(task), "camunda:taskListener", {"event": "create"}, TASK_VISIBLE_GROOVY.format(action="review"))


def embed(doc: Bpmn, other: Bpmn, wid: str, name: str, dx: float, dy: float) -> ET.Element:
    """Wrap another skeleton's whole process in an embedded subprocess of `doc`: its start → … → its `complete`.
    A terminate end in a subprocess would only end the subprocess, so `stopped for repair` becomes an error end the
    wrapper's boundary turns into the root's terminate end."""
    wrapper = doc.add(doc.process, "bpmn:subProcess", {"id": wid, "name": name})
    contract = other.process.find(f"{q('bpmn:extensionElements')}/{q('ttr:contract')}")
    if contract is not None:
        ext(wrapper).append(copy.deepcopy(contract))
    for child in list(other.process):
        if child.tag == q("bpmn:extensionElements"):
            continue
        wrapper.append(copy.deepcopy(child))
    for end in wrapper.findall(q("bpmn:endEvent")):
        term = end.find(q("bpmn:terminateEventDefinition"))
        if term is not None:
            end.remove(term)
            ET.SubElement(end, q("bpmn:errorEventDefinition"), {"errorRef": "s41_stopped"})
    xs, ys, xe, ye = [], [], [], []
    for s in other.plane:
        el = copy.deepcopy(s)
        for b in el.iter(q("dc:Bounds")):
            b.set("x", f"{float(b.get('x')) + dx:g}")
            b.set("y", f"{float(b.get('y')) + dy:g}")
            xs.append(float(b.get("x"))); ys.append(float(b.get("y")))
            xe.append(float(b.get("x")) + float(b.get("width"))); ye.append(float(b.get("y")) + float(b.get("height")))
        for w in el.iter(q("di:waypoint")):
            w.set("x", f"{float(w.get('x')) + dx:g}")
            w.set("y", f"{float(w.get('y')) + dy:g}")
        doc.plane.append(el)
    doc.reindex()
    doc.shape(wid, min(xs) - 30, min(ys) - 30, max(xe) - min(xs) + 60, max(ye) - min(ys) + 60)
    shape = doc.plane[-1]
    shape.set(q("bpmndi:isExpanded"), "true")
    doc.plane.remove(shape)
    doc.plane.insert(0, shape)
    return wrapper


def compose_return_request(s: dict) -> Bpmn:
    lang, labels, t = s["lang"], LABELS[s["lang"]], H2[s["lang"]]
    deps = s["deployments"]
    doc = Bpmn(export_bpmn(deps["decide_event"]))
    egress = egress_of(doc)
    decide_deployment = deployment_of(doc)
    rename(doc, "return_request", t["name"])
    recipients(doc, s["mail"])
    start = message_start(doc, t["start"], "return_requested")
    P = doc.process

    # care decides outside the run (D-171): the skeleton's approval ask of decide_way goes
    bypass(doc, doc.named("bpmn:subProcess", "ask each to_customer_care row", P))

    # the stop for repair, shared by the three chains
    stopped_err = ET.Element(q("bpmn:error"), {"id": "s41_stopped", "errorCode": "TTR_STOPPED", "name": "stopped for repair"})
    errors = doc.defs.findall(q("bpmn:error"))
    doc.defs.insert(list(doc.defs).index(errors[-1]) + 1, stopped_err)

    plane_shapes = [s_ for s_ in doc.plane if s_.find(q("dc:Bounds")) is not None]
    max_y = max(float(s_.find(q("dc:Bounds")).get("y")) + float(s_.find(q("dc:Bounds")).get("height")) for s_ in plane_shapes)
    max_x = max(float(s_.find(q("dc:Bounds")).get("x")) + float(s_.find(q("dc:Bounds")).get("width")) for s_ in plane_shapes)
    band = max_y + 150          # the authored flow runs below the decide chain, the two loops below it
    X = lambda i: 200 + i * 170  # noqa: E731

    # ---- after Decide: read its verdict, branch on the way ----
    decide_end = doc.named("bpmn:endEvent", "complete", P)
    into_end = doc.flows_into(decide_end.get("id"))
    remember = doc.add(P, "bpmn:scriptTask", {"id": "s41_decide_run", "name": t["verdict"], "scriptFormat": "groovy"})
    ET.SubElement(remember, q("bpmn:script")).text = "execution.setVariable('ttrDecideRun', execution.getVariable('ttrAnchor'))"
    for f in into_end:
        doc.retarget(f, remember.get("id"))
    P.remove(decide_end)
    for s_ in list(doc.plane):
        if s_.get("bpmnElement") == decide_end.get("id"):
            doc.plane.remove(s_)
    verdict = http_task(doc, P, "s41_decide_verdict", t["verdict"], "GET",
                        f'${{"{egress}/runs/".concat(ttrDecideRun)}}', "ttrVerdict", "the decision's status")
    doc.flow(P, "s41_f_remember", "s41_decide_run", "s41_decide_verdict")
    way = doc.add(P, "bpmn:exclusiveGateway", {"id": "s41_way", "name": t["way"], "default": "s41_f_way_rejected"})
    doc.flow(P, "s41_f_verdict_way", "s41_decide_verdict", "s41_way")
    rejected = doc.add(P, "bpmn:endEvent", {"id": "s41_rejected", "name": t["rejected"]})
    doc.flow(P, "s41_f_way_rejected", "s41_way", "s41_rejected", name=t["rejected"])

    # ---- the care route: a form task, then a typed perform of decide_way {to, way} (D-171, D-168) ----
    care_row = http_task(doc, P, "s41_care_row", t["care_row"], "GET",
                         f'${{"{egress}/runs/".concat(ttrDecideRun).concat("/routes/to_customer_care")}}',
                         "ttrCareRows", "the care route's row")
    care = doc.add(P, "bpmn:userTask", {"id": "s41_care", "name": t["care"], q("camunda:candidateGroups"): "hartland-care",
                                       q("camunda:dueDate"): "${ttrApprovalDue}"})
    ce = ext(care)
    form = ET.SubElement(ce, q("camunda:formData"))
    field = ET.SubElement(form, q("camunda:formField"), {"id": "way", "label": t["care_field"], "type": "enum"})
    ET.SubElement(ET.SubElement(field, q("camunda:validation")), q("camunda:constraint"), {"name": "required"})
    for w in WAYS:
        ET.SubElement(field, q("camunda:value"), {"id": w, "name": WAY_LABELS[lang][w]})
    cio = ET.SubElement(ce, q("camunda:inputOutput"))
    ET.SubElement(cio, q("camunda:inputParameter"), {"name": "ttrAction"}).text = '${"decide_way"}'
    ET.SubElement(cio, q("camunda:inputParameter"), {"name": "ttrKey"}).text = "${ttrInput['key']['line_id']}"
    groovy(ce, "camunda:taskListener", {"event": "create"}, TASK_VISIBLE_GROOVY.format(action="decide_way"))
    groovy(ce, "camunda:taskListener", {"event": "complete"}, CARE_BY_GROOVY)
    # an IO-mapped activity keeps what is set in it local: the form's way and the completer leave by output mappings
    ET.SubElement(cio, q("camunda:outputParameter"), {"name": "way"}).text = "${way}"
    ET.SubElement(cio, q("camunda:outputParameter"), {"name": "ttrCareBy"}).text = "${ttrCareBy}"
    care_due = doc.add(P, "bpmn:scriptTask", {"id": "s41_care_due", "name": labels["due"], "scriptFormat": "groovy"})
    ET.SubElement(care_due, q("bpmn:script")).text = due_script("decide_way", 3, s["world"])
    to_expr = "(way == 'exchange' || way == 'refund_after_return' ? 'awaiting_goods' : 'settling')"
    perform = http_task(
        doc, P, "s41_care_perform", t["care_perform"], "POST",
        f'${{"{egress}/deployments/{decide_deployment}/actions/decide_way/perform"}}', "ttrCarePerformed",
        "perform decide_way",
        payload=("${S('{}').prop(\"key\", S('{}').prop(\"line\", ttrCareRows.prop(\"rows\").elements().get(0).prop(\"line_id\")))"
                 f".prop(\"params\", S('{{}}').prop(\"to\", {to_expr}).prop(\"way\", way))"
                 ".prop(\"by\", ttrCareBy).prop(\"origin\", \"engine\")"
                 ".prop(\"idempotencyKey\", execution.processInstanceId.concat(\":care\")).toString()}"))
    care_way = doc.add(P, "bpmn:exclusiveGateway", {"id": "s41_care_way", "name": t["care_way"], "default": "s41_f_care_settle"})
    instructions = doc.add(P, "bpmn:sendTask", {"id": "s41_instructions", "name": t["instructions"],
                                                q("camunda:type"): "external", q("camunda:topic"): "TTR_CONN_MAIL"})
    iio = ET.SubElement(ext(instructions), q("camunda:inputOutput"))
    for k, v in (("ttrRecipient", '${ttrCareRows.prop("rows").elements().get(0).prop("customer_email").stringValue()}'),
                 ("ttrRow", '${ttrCareRows.prop("rows").elements().get(0)}'),
                 ("ttrAction", '${"notify_customer"}'), ("ttrTemplate", '${"return-instructions"}'),
                 ("ttrKey", "${ttrInput['key']['line_id']}")):
        ET.SubElement(iio, q("camunda:inputParameter"), {"name": k}).text = v
    doc.flow(P, "s41_f_way_care", "s41_way", "s41_care_row", name="to_customer_care",
             condition=has_route("ttrVerdict", "to_customer_care"))
    doc.flow(P, "s41_f_care_row_due", "s41_care_row", "s41_care_due")
    doc.flow(P, "s41_f_care_due_task", "s41_care_due", "s41_care")
    doc.flow(P, "s41_f_care_perform", "s41_care", "s41_care_perform")
    doc.flow(P, "s41_f_care_performed", "s41_care_perform", "s41_care_way")

    # ---- the two loops: wait (message | daily timer) → a round → the recipe's verdict → again or on (D-147) ----
    def loop(prefix: str, deployment: str, message: str, i_wait: str, wait_label: str, msg_label: str,
             wrap_label: str, round_label: str, verdict_label: str, route_label: str, row_y: float) -> dict:
        other = Bpmn(export_bpmn(deployment))
        merge = doc.add(P, "bpmn:exclusiveGateway", {"id": f"s41_{prefix}_again", "name": wait_label})
        wait = doc.add(P, "bpmn:eventBasedGateway", {"id": f"s41_{prefix}_wait", "name": wait_label})
        msg_id = f"s41_message_{message}"
        if doc.byid.get(msg_id) is None:
            msg = ET.Element(q("bpmn:message"), {"id": msg_id, "name": message})
            doc.defs.insert(list(doc.defs).index(doc.defs.find(q("bpmn:process"))), msg)
            doc.byid[msg_id] = msg
        catch = doc.add(P, "bpmn:intermediateCatchEvent", {"id": f"s41_{prefix}_message", "name": msg_label})
        ET.SubElement(catch, q("bpmn:messageEventDefinition"), {"id": f"s41_{prefix}_message_def", "messageRef": msg_id})
        timer = doc.add(P, "bpmn:intermediateCatchEvent", {"id": f"s41_{prefix}_timer", "name": t["daily"]})
        td = ET.SubElement(timer, q("bpmn:timerEventDefinition"), {"id": f"s41_{prefix}_timer_def"})
        ET.SubElement(td, q("bpmn:timeDuration"), {q("xsi:type"): "bpmn:tFormalExpression"}).text = \
            "${execution.getVariable('ttrLoopPeriod') != null ? ttrLoopPeriod : 'P1D'}"
        rnd = doc.add(P, "bpmn:scriptTask", {"id": f"s41_{prefix}_round", "name": round_label, "scriptFormat": "groovy"})
        ET.SubElement(rnd, q("bpmn:script")).text = ROUND_GROOVY
        wrapper = embed(doc, other, f"s41_{prefix}", wrap_label, dx=300, dy=row_y)
        stopped = doc.add(P, "bpmn:boundaryEvent", {"id": f"s41_{prefix}_stopped", "name": t["stopped"],
                                                    "attachedToRef": wrapper.get("id"), "cancelActivity": "true"})
        ET.SubElement(stopped, q("bpmn:errorEventDefinition"), {"errorRef": "s41_stopped"})
        stop_end = doc.add(P, "bpmn:endEvent", {"id": f"s41_{prefix}_stop_end", "name": t["stopped"]})
        ET.SubElement(stop_end, q("bpmn:terminateEventDefinition"))
        verdict = http_task(doc, P, f"s41_{prefix}_verdict", verdict_label, "GET",
                            f'${{"{egress}/runs/".concat(ttrAnchor)}}', "ttrVerdict", f"the {prefix} verdict")
        gw = doc.add(P, "bpmn:exclusiveGateway", {"id": f"s41_{prefix}_route", "name": route_label,
                                                  "default": f"s41_f_{prefix}_again"})
        doc.flow(P, f"s41_f_{prefix}_merge_wait", merge.get("id"), wait.get("id"))
        doc.flow(P, f"s41_f_{prefix}_wait_message", wait.get("id"), catch.get("id"))
        doc.flow(P, f"s41_f_{prefix}_wait_timer", wait.get("id"), timer.get("id"))
        doc.flow(P, f"s41_f_{prefix}_message_round", catch.get("id"), rnd.get("id"))
        doc.flow(P, f"s41_f_{prefix}_timer_round", timer.get("id"), rnd.get("id"))
        doc.flow(P, f"s41_f_{prefix}_round_run", rnd.get("id"), wrapper.get("id"))
        doc.flow(P, f"s41_f_{prefix}_run_verdict", wrapper.get("id"), verdict.get("id"))
        doc.flow(P, f"s41_f_{prefix}_verdict_route", verdict.get("id"), gw.get("id"))
        doc.flow(P, f"s41_f_{prefix}_again", gw.get("id"), merge.get("id"), name=t["other"])
        doc.flow(P, f"s41_f_{prefix}_stopped", stopped.get("id"), stop_end.get("id"))
        # diagram: the wait band above the wrapper
        wy = row_y - 120
        for i, el in enumerate((merge, wait)):
            doc.shape(el.get("id"), X(i), wy, 50, 50)
        doc.shape(catch.get("id"), X(2), wy - 40, 36, 36)
        doc.shape(timer.get("id"), X(2), wy + 50, 36, 36)
        doc.shape(rnd.get("id"), X(3), wy, 100, 80)
        doc.shape(verdict.get("id"), X(5), wy, 100, 80)
        doc.shape(gw.get("id"), X(6), wy, 50, 50)
        doc.shape(stopped.get("id"), X(4), wy + 80, 36, 36)
        doc.shape(stop_end.get("id"), X(4) + 60, wy + 80, 36, 36)
        return {"merge": merge.get("id"), "route": gw.get("id")}

    inbound = loop("inbound", deps["inbound_event"], "receipt_posted", "", t["inbound_wait"], t["receipt"],
                   t["inbound"], t["inbound_round"], t["inbound_verdict"], t["inbound_route"], band + 600)
    settle_y = band + 600 + 1600
    settle = loop("settle", deps["settle_event"], "settlement_posted", "", t["settle_wait"], t["settlement"],
                  t["settle"], t["settle_round"], t["settle_verdict"], t["settle_route"], settle_y)

    # the way → the loops
    for w, target in (("exchange", inbound["merge"]), ("refund_after_return", inbound["merge"]),
                      ("refund_no_return", settle["merge"]), ("replacement_no_return", settle["merge"])):
        doc.flow(P, f"s41_f_way_{w}", "s41_way", target, name=w, condition=has_route("ttrVerdict", w))
    doc.flow(P, "s41_f_care_inbound", "s41_care_way", "s41_instructions", name="exchange · refund_after_return",
             condition="${way == 'exchange' || way == 'refund_after_return'}")
    doc.flow(P, "s41_f_instructions_inbound", "s41_instructions", inbound["merge"])
    doc.flow(P, "s41_f_care_settle", "s41_care_way", settle["merge"], name="refund_no_return · replacement_no_return")
    # inbound: complete → settle · expired → end
    doc.flow(P, "s41_f_inbound_complete", inbound["route"], settle["merge"], name="complete",
             condition=has_route("ttrVerdict", "complete"))
    not_returned = doc.add(P, "bpmn:endEvent", {"id": "s41_not_returned", "name": t["not_returned"]})
    doc.flow(P, "s41_f_inbound_expired", inbound["route"], "s41_not_returned", name="expired",
             condition=has_route("ttrVerdict", "expired"))
    closed = doc.add(P, "bpmn:endEvent", {"id": "s41_closed", "name": t["closed"]})
    doc.flow(P, "s41_f_settle_closed", settle["route"], "s41_closed", name="closed",
             condition=has_route("ttrVerdict", "closed"))
    del rejected, care_way, perform, verdict, remember, way, not_returned, closed, care, care_due, care_row

    # diagram of the decide band
    for i, nid in enumerate(("s41_decide_run", "s41_decide_verdict", "s41_way", "s41_rejected", "s41_care_row",
                             "s41_care_due", "s41_care", "s41_care_perform", "s41_care_way", "s41_instructions",
                             "s41_not_returned", "s41_closed")):
        el = doc.byid[nid]
        w_, h_ = (50, 50) if "Gateway" in el.tag else (36, 36) if "Event" in el.tag else (100, 80)
        doc.shape(nid, X(i), band, w_, h_)
    reviews(doc, H2[lang])
    del max_x, start
    return doc


PROCESSES = {"release_order": compose_release_order, "release_morning": compose_release_morning,
             "return_request": compose_return_request}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--set", default="cz")
    ap.add_argument("--check", action="store_true", help="exit 1 if a committed process differs; write nothing")
    args = ap.parse_args(argv)
    sets = json.loads((ROOT / "processes" / "sets.json").read_text(encoding="utf-8"))
    if args.set not in sets:
        raise SystemExit(f"no deployment set {args.set!r} in processes/sets.json")
    out_dir = ROOT / "processes" / args.set
    drift = []
    for name, build in PROCESSES.items():
        doc = build(sets[args.set])
        repairs(doc)
        body = doc.resource(out_dir)
        path = out_dir / f"{name}.bpmn"
        if args.check:
            if not path.exists() or path.read_bytes() != body:
                drift.append(str(path.relative_to(ROOT)))
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            print(f"wrote {path.relative_to(ROOT)} ({len(body)} bytes)")
    for d in drift:
        print(f"drift: {d} differs from what exports/ composes to — python3 scripts/compose-processes.py --set {args.set}")
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
