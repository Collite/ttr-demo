"""Specs for scripts/automation-events.py (the demo day's event driver, AU contracts §6 as amended at P4·S4.1: engine
messages, D-143) — no cluster, no network: the timeline check, the message bodies, the speed mapping, the retry/stop
rules (httpx.MockTransport), the conf's message map, the instance check.

    just automation-events-test   # = uv run --with pyyaml --with httpx python3 -B -m unittest scripts/test_automation_events.py
"""

from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import textwrap
import unittest

import httpx

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("automation_events", HERE / "automation-events.py")
ae = importlib.util.module_from_spec(spec)
sys.modules["automation_events"] = ae  # dataclasses resolve annotations through sys.modules
spec.loader.exec_module(ae)

TIMELINE = textwrap.dedent("""\
    seq,kind,at,payload,demo
    1,order_placed,2026-10-25 09:14:00+01,"{""order_number"": 200004711}",false
    2,line_received,2026-10-25 10:02:00+01,"{""line_id"": 1000231}",false
    3,receipt_posted,2026-10-26 09:00:00+01,"{""line_id"": 1000188}",true
    4,settlement_posted,2026-10-26 09:30:00+01,"{""line_id"": 1000190}",true
    """)
MESSAGES = {"order_placed": "order_placed", "line_received": "return_requested",
            "receipt_posted": "receipt_posted", "settlement_posted": "settlement_posted"}


def write(text: str) -> pathlib.Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
    f.write(text)
    f.close()
    return pathlib.Path(f.name)


class TimelineSpec(unittest.TestCase):
    def test_a_good_timeline_checks_clean(self):
        events = ae.load(write(TIMELINE))
        self.assertEqual([e.seq for e in events], [1, 2, 3, 4])
        self.assertEqual(events[0].payload, {"order_number": 200004711})
        self.assertTrue(events[2].demo)
        self.assertEqual(ae.check(events), [])

    def test_time_running_backwards_is_refused(self):
        bad = TIMELINE.replace("2026-10-25 10:02:00+01", "2026-10-25 08:00:00+01")
        self.assertTrue(any("before" in p for p in ae.check(ae.load(write(bad)))))

    def test_a_gap_in_seq_is_refused(self):
        bad = TIMELINE.replace("\n3,receipt_posted", "\n5,receipt_posted")
        self.assertTrue(any("seq" in p for p in ae.check(ae.load(write(bad)))))

    def test_a_payload_must_name_its_kinds_key_and_nothing_else(self):
        bad = TIMELINE.replace('{""line_id"": 1000231}', '{""order_number"": 1000231}')
        self.assertTrue(any("payload" in p for p in ae.check(ae.load(write(bad)))))
        extra = TIMELINE.replace('{""line_id"": 1000231}', '{""line_id"": 1000231, ""x"": 1}')
        self.assertTrue(any("payload" in p for p in ae.check(ae.load(write(extra)))))

    def test_an_unknown_kind_is_refused(self):
        bad = TIMELINE.replace("receipt_posted", "receipt_lost")
        self.assertTrue(any("kind" in p for p in ae.check(ae.load(write(bad)))))


class MessageSpec(unittest.TestCase):
    def test_a_start_carries_the_port_as_a_json_object_variable(self):
        e = ae.load(write(TIMELINE))[1]
        body = ae.message(e, MESSAGES)
        self.assertEqual(body["messageName"], "return_requested")
        self.assertEqual(body["businessKey"], "1000231")
        self.assertTrue(body["resultEnabled"])
        var = body["processVariables"]["ttrInput"]
        self.assertEqual(var["type"], "Object")
        self.assertEqual(var["valueInfo"], {"objectTypeName": "java.util.LinkedHashMap",
                                            "serializationDataFormat": "application/json"})
        self.assertEqual(json.loads(var["value"]), {"key": {"line_id": 1000231}, "at": "2026-10-25T10:02:00+01:00"})

    def test_a_wake_carries_the_events_time_and_no_port(self):
        e = ae.load(write(TIMELINE))[2]
        body = ae.message(e, MESSAGES)
        self.assertEqual(body["messageName"], "receipt_posted")
        self.assertEqual(body["processVariables"], {"ttrEventAt": {"value": "2026-10-26T09:00:00+01:00", "type": "String"}})

    def test_the_knobs_reach_only_their_process(self):
        order, line = ae.load(write(TIMELINE))[:2]
        o = ae.message(order, MESSAGES, approval_due="PT2M", loop_period="PT1M")["processVariables"]
        l_ = ae.message(line, MESSAGES, approval_due="PT2M", loop_period="PT1M")["processVariables"]
        self.assertEqual(o["ttrApprovalDueOverride"]["value"], "PT2M")
        self.assertNotIn("ttrLoopPeriod", o)
        self.assertEqual(l_["ttrLoopPeriod"]["value"], "PT1M")
        self.assertNotIn("ttrApprovalDueOverride", l_)

    def test_dry_run_prints_one_message_per_event_and_sends_nothing(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = ae.main(["replay", "--world", "cz", "--csv", str(write(TIMELINE)), "--dry-run"])
        self.assertEqual(rc, 0)
        lines = [json.loads(line) for line in out.getvalue().splitlines() if line.startswith("{")]
        self.assertEqual([b["messageName"] for b in lines],
                         ["order_placed", "return_requested", "receipt_posted", "settlement_posted"])

    def test_check_dry_lists_the_days_messages_in_order(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = ae.main(["check", "--world", "cz", "--csv", str(write(TIMELINE)), "--day", "2026-10-26", "--dry"])
        self.assertEqual(rc, 0)
        lines = [json.loads(line) for line in out.getvalue().splitlines() if line.startswith("{")]
        self.assertEqual([(b["messageName"], b["businessKey"]) for b in lines],
                         [("receipt_posted", "1000188"), ("settlement_posted", "1000190")])

    def test_select_by_window_day_and_demo(self):
        events = ae.load(write(TIMELINE))
        frm = dt.datetime.fromisoformat("2026-10-26T00:00:00+01:00")
        self.assertEqual([e.seq for e in ae.select(events, frm, None, False)], [3, 4])
        self.assertEqual([e.seq for e in ae.select(events, None, None, True)], [3, 4])
        to = dt.datetime.fromisoformat("2026-10-25T10:00:00+01:00")
        self.assertEqual([e.seq for e in ae.select(events, None, to, False)], [1])
        self.assertEqual([e.seq for e in ae.select(events, None, None, False, dt.date(2026, 10, 25))], [1, 2])


class SpeedSpec(unittest.TestCase):
    def test_gaps_become_wall_time_divided_by_the_speed(self):
        events = ae.load(write(TIMELINE))
        self.assertEqual(ae.wall_delays(events, 60), [0.0, 48 * 60 / 60, (22 * 60 + 58) * 60 / 60, 30 * 60 / 60])

    def test_speed_zero_means_as_fast_as_possible(self):
        self.assertEqual(ae.wall_delays(ae.load(write(TIMELINE)), 0), [0.0, 0.0, 0.0, 0.0])


class SendSpec(unittest.TestCase):
    def client(self, answers: list[tuple[int, object]], seen: list[httpx.Request]) -> httpx.Client:
        it = iter(answers)

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            status, body = next(it)
            return httpx.Response(status, json=body)
        return httpx.Client(transport=httpx.MockTransport(handler))

    STARTED = [{"resultType": "ProcessDefinition", "processInstance": {"id": "pi-1"}}]
    WOKEN = [{"resultType": "Execution", "execution": {"processInstanceId": "pi-2"}}]
    UNMATCHED = {"type": "RestException", "message": "org.cibseven.bpm.engine.MismatchingMessageCorrelationException: "
                 "Cannot correlate message 'receipt_posted': No process definition or execution matches the parameters"}

    def test_a_5xx_is_retried_with_backoff_and_the_bearer_is_sent(self):
        seen: list[httpx.Request] = []
        naps: list[float] = []
        status, pi = ae.send(self.client([(503, {}), (502, {}), (200, self.STARTED)], seen), "http://e/message", {},
                             "tok", sleep=naps.append)
        self.assertEqual((status, pi), (200, "pi-1"))
        self.assertEqual(naps, [1.0, 2.0])
        self.assertEqual(seen[0].headers["authorization"], "Bearer tok")

    def test_it_gives_up_after_three_retries(self):
        seen: list[httpx.Request] = []
        status, _ = ae.send(self.client([(500, {})] * 4, seen), "http://e/message", {}, None, sleep=lambda s: None)
        self.assertEqual((status, len(seen)), (500, 4))
        self.assertNotIn("authorization", seen[0].headers)

    def test_replay_reports_an_unmatched_wake_and_stops_at_a_401(self):
        seen: list[httpx.Request] = []
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = ae.replay_events(ae.load(write(TIMELINE)), MESSAGES, "http://e/message", "tok", 0,
                                  self.client([(200, self.STARTED), (200, self.WOKEN), (400, self.UNMATCHED),
                                               (401, {"message": "unauthorized"})], seen), sleep=lambda s: None)
        self.assertEqual(rc, 1)
        printed = out.getvalue().splitlines()
        self.assertIn("1 2026-10-25T09:14:00+01:00 order_placed 200004711 → pi-1", printed)
        self.assertIn("2 2026-10-25T10:02:00+01:00 return_requested 1000231 → pi-2", printed)
        self.assertIn("3 2026-10-26T09:00:00+01:00 receipt_posted 1000188 → no waiting instance", printed)
        self.assertTrue(printed[-1].endswith("401 unauthorized — stopping"))
        self.assertEqual(json.loads(seen[0].content)["messageName"], "order_placed")

    def test_the_instance_check_asks_the_history_by_process_and_key(self):
        seen: list[httpx.Request] = []
        events = ae.load(write(TIMELINE))
        problems = ae.check_instances(events, MESSAGES, "http://e", "tok",
                                      self.client([(200, [{"id": "pi-1"}]), (200, [])], seen))
        self.assertEqual([r.url.params["processDefinitionKey"] for r in seen], ["release_order", "return_request"])
        self.assertEqual(problems, ["seq 2: no return_request instance for 1000231"])


class ConfigSpec(unittest.TestCase):
    def test_the_conf_names_the_engine_message_of_every_kind(self):
        conf = write(textwrap.dedent("""\
            -- comment
            \\set events_message_order_placed 'order_placed'
            \\set events_message_line_received 'return_requested'
            \\set events_message_receipt_posted 'receipt_posted'
            \\set events_message_settlement_posted 'settlement_posted'
            \\set events_demo 15
            """))
        self.assertEqual(ae.messages_from_conf(conf), MESSAGES)

    def test_the_committed_conf_is_the_message_map(self):
        self.assertEqual(ae.messages_from_conf(ae.CONF), MESSAGES)

    def test_every_message_the_processes_catch_is_one_the_driver_sends(self):
        # processes/<set>/*.bpmn declare the messages; the driver sends exactly those (D-143)
        declared = set()
        for f in (ae.ROOT / "processes").glob("*/*.bpmn"):
            declared |= set(__import__("re").findall(r'<bpmn:message id="[^"]+" name="([^"]+)"', f.read_text(encoding="utf-8")))
        self.assertEqual(declared, set(MESSAGES.values()))


if __name__ == "__main__":
    unittest.main()
