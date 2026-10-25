"""brief_check.py's parses (HE review-152 R9), over the shapes Hebe's console and iris-bff answer with.

    python3 -B -m unittest design/hebe-demo/rig-hb/test_brief_check.py      (`just hebe-verify-test`)
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import brief_check as bc  # noqa: E402

ROUTINES = {
    "routines": [
        {"name": "friday-returns", "lastTurnRef": None, "lastRunAt": None},
        {"name": "monday-brief", "lastTurnRef": "t-mon", "lastRunAt": "2026-10-26T06:00:00Z", "sessionRef": "s-mon"},
    ]
}
INBOX = {
    "items": [
        {"kind": "brief", "turnId": "t-mon", "sessionId": "s-mon", "status": "DONE", "updatedAt": "2026-10-26T06:00:31.2Z"},
        {"kind": "investigation", "turnId": "t-why", "sessionId": "s-x", "status": "RUNNING", "updatedAt": "2026-10-26T05:00:00Z"},
    ],
    "counts": {"running": 1, "needsInput": 0},
}
RECEIPT = {
    "seq": 41,
    "sessionId": "routine:r-1",
    "turnId": "t-mon",
    "tool": "kantheon.question",
    "argsRedacted": '{"routine":"r-1","as":"marketa","status":"DELIVERED","deliveries":2/2}',
    "ok": True,
}
# Hebe's /api/receipts carries the list as a JSON string
RECEIPTS = {"receipts": json.dumps([{**RECEIPT, "turnId": "t-older"}, RECEIPT])}


class Parses(unittest.TestCase):
    def test_the_routine_last_run(self) -> None:
        self.assertEqual(bc.routine_last_run(ROUTINES, "monday-brief"), ("t-mon", "2026-10-26T06:00:00Z"))
        self.assertIsNone(bc.routine_last_run(ROUTINES, "friday-returns"))
        self.assertIsNone(bc.routine_last_run(ROUTINES, "nope"))

    def test_the_inbox_brief_and_a_same_minute_duplicate(self) -> None:
        brief = bc.inbox_brief(INBOX, "t-mon")
        self.assertEqual(brief["status"], "DONE")
        self.assertEqual(bc.duplicates(INBOX, brief), [])
        # the live case: the cut first attempt landed, and the retry 2 minutes later
        twice = {"items": INBOX["items"] + [{**INBOX["items"][0], "turnId": "t-mon-2", "updatedAt": "2026-10-26T06:02:44Z"}]}
        self.assertEqual([i["turnId"] for i in bc.duplicates(twice, bc.inbox_brief(twice, "t-mon"))], ["t-mon-2"])
        # last week's brief of the same routine is not a duplicate
        weekly = {"items": INBOX["items"] + [{**INBOX["items"][0], "turnId": "t-prev", "updatedAt": "2026-10-19T06:00:30Z"}]}
        self.assertEqual(bc.duplicates(weekly, bc.inbox_brief(weekly, "t-mon")), [])

    def test_the_receipt_deliveries_from_the_string_encoded_list(self) -> None:
        self.assertEqual(bc.receipt_deliveries(RECEIPTS, "t-mon"), (2, 2))
        self.assertIsNone(bc.receipt_deliveries(RECEIPTS, "t-none"))


class Verdict(unittest.TestCase):
    def test_all_three_agree(self) -> None:
        self.assertEqual(bc.verdict(ROUTINES, INBOX, RECEIPTS, "monday-brief")[0], "PASS")

    def test_no_scheduled_run_yet_is_open_not_failed(self) -> None:
        # a hand fire sets lastTurnRef only; the row waits for the first scheduled run
        fired = {"routines": [{"name": "monday-brief", "lastTurnRef": "t-hand", "lastRunAt": None, "nextRunAt": "2026-10-26T06:00:00Z"}]}
        self.assertEqual(bc.verdict(fired, INBOX, RECEIPTS, "monday-brief"), ("SKIP", "monday-brief has no scheduled run yet (next 2026-10-26T06:00:00Z)"))
        self.assertEqual(bc.verdict(ROUTINES, INBOX, RECEIPTS, "nope")[0], "FAIL")

    def test_each_disagreement_fails_with_its_reason(self) -> None:
        self.assertIn("not a brief", bc.verdict(ROUTINES, {"items": []}, RECEIPTS, "monday-brief")[1])
        half = {"receipts": json.dumps([{**RECEIPT, "argsRedacted": RECEIPT["argsRedacted"].replace("2/2", "1/2")}])}
        self.assertIn("delivered 1/2", bc.verdict(ROUTINES, INBOX, half, "monday-brief")[1])
        twice = {"items": INBOX["items"] + [{**INBOX["items"][0], "turnId": "t-mon-2"}]}
        self.assertIn("2× within 15 min", bc.verdict(ROUTINES, twice, RECEIPTS, "monday-brief")[1])


if __name__ == "__main__":
    unittest.main()
