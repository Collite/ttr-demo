"""Specs for scripts/automation-events.py (the demo day's event driver, AU contracts §6) — no cluster, no network:
the timeline check, the POST body, the speed mapping, the retry/stop rules (httpx.MockTransport), the config.

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
DEPLOYMENTS = {"order_placed": "release_native_event", "line_received": "decide_native_event",
               "receipt_posted": "inbound_native_event", "settlement_posted": "settle_native_event"}


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


class BodySpec(unittest.TestCase):
    def test_the_body_is_the_connectors_inbound_event_shape(self):
        e = ae.load(write(TIMELINE))[1]
        self.assertEqual(ae.body(e, "us", DEPLOYMENTS), {
            "deployment": "decide_native_event", "event": "line_received",
            "payload": {"line_id": 1000231}, "idempotencyKey": "events:us:2"})

    def test_dry_run_prints_one_body_per_event_and_posts_nothing(self):
        csv, cfg = write(TIMELINE), write(json.dumps({"deployments": DEPLOYMENTS}))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = ae.main(["replay", "--world", "cz", "--csv", str(csv), "--config", str(cfg), "--dry-run"])
        self.assertEqual(rc, 0)
        lines = [json.loads(line) for line in out.getvalue().splitlines() if line.startswith("{")]
        self.assertEqual([b["idempotencyKey"] for b in lines], ["events:cz:1", "events:cz:2", "events:cz:3", "events:cz:4"])
        self.assertEqual(lines[0]["deployment"], "release_native_event")

    def test_select_by_window_and_demo(self):
        events = ae.load(write(TIMELINE))
        frm = dt.datetime.fromisoformat("2026-10-26T00:00:00+01:00")
        self.assertEqual([e.seq for e in ae.select(events, frm, None, False)], [3, 4])
        self.assertEqual([e.seq for e in ae.select(events, None, None, True)], [3, 4])
        to = dt.datetime.fromisoformat("2026-10-25T10:00:00+01:00")
        self.assertEqual([e.seq for e in ae.select(events, None, to, False)], [1])


class SpeedSpec(unittest.TestCase):
    def test_gaps_become_wall_time_divided_by_the_speed(self):
        events = ae.load(write(TIMELINE))
        self.assertEqual(ae.wall_delays(events, 60), [0.0, 48 * 60 / 60, (22 * 60 + 58) * 60 / 60, 30 * 60 / 60])

    def test_speed_zero_means_as_fast_as_possible(self):
        self.assertEqual(ae.wall_delays(ae.load(write(TIMELINE)), 0), [0.0, 0.0, 0.0, 0.0])


class PostSpec(unittest.TestCase):
    def client(self, statuses: list[int], seen: list[httpx.Request]) -> httpx.Client:
        it = iter(statuses)

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            status = next(it)
            return httpx.Response(status, json={"runId": f"run-{len(seen)}"} if status < 300 else {"error": "x"})
        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_a_5xx_is_retried_with_backoff(self):
        seen: list[httpx.Request] = []
        naps: list[float] = []
        status, run = ae.post(self.client([503, 502, 200], seen), "http://x/events", {"a": 1}, "tok", sleep=naps.append)
        self.assertEqual((status, run), (200, "run-3"))
        self.assertEqual(len(seen), 3)
        self.assertEqual(naps, [1.0, 2.0])
        self.assertEqual(seen[0].headers["authorization"], "Bearer tok")

    def test_it_gives_up_after_three_retries(self):
        seen: list[httpx.Request] = []
        status, _ = ae.post(self.client([500, 500, 500, 500], seen), "http://x/events", {}, None, sleep=lambda s: None)
        self.assertEqual(status, 500)
        self.assertEqual(len(seen), 4)
        self.assertNotIn("authorization", seen[0].headers)

    def test_replay_goes_on_after_a_409_and_stops_at_any_other_4xx(self):
        seen: list[httpx.Request] = []
        csv, cfg = write(TIMELINE), write(json.dumps({"deployments": DEPLOYMENTS}))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = ae.replay_events(ae.load(csv), "us", "http://x/events", DEPLOYMENTS, None, 0,
                                  self.client([200, 409, 400, 200], seen), sleep=lambda s: None)
        self.assertEqual(rc, 1)
        self.assertEqual(len(seen), 3)                      # the 4th was never sent
        printed = out.getvalue().splitlines()
        self.assertIn("1 order_placed 200004711 → 200 run-1", printed)
        self.assertIn("2 line_received 1000231 → 409 (already posted)", printed)
        self.assertTrue(any(line.startswith("3 receipt_posted 1000188 → 400") for line in printed))


class ConfigSpec(unittest.TestCase):
    def test_init_config_reads_the_deployments_from_automation_conf(self):
        conf = write(textwrap.dedent("""\
            -- comment
            \\set events_deployment_order_placed 'release_native_event'
            \\set events_deployment_line_received 'decide_native_event'
            \\set events_deployment_receipt_posted 'inbound_native_event'
            \\set events_deployment_settlement_posted 'settle_native_event'
            \\set events_demo 15
            """))
        self.assertEqual(ae.deployments_from_conf(conf), DEPLOYMENTS)

    def test_the_committed_conf_maps_every_kind(self):
        self.assertEqual(set(ae.deployments_from_conf(ae.CONF)), set(ae.KINDS))


if __name__ == "__main__":
    unittest.main()
