"""verify.sh's helpers, sourced into bash with a fake kubectl — no cluster.

    python3 -B -m unittest design/hebe-demo/rig-hb/test_verify_helpers.py      (`just hebe-verify-test`; a model-gate step)

The fixtures are the shapes hartland answered with on 2026-10-24: capabilities-mcp pretty-prints its JSON over many
lines (the first live run read that as "not registered"), Hebe's /ready answers on one line, and a non-2xx answer
reaches the script as kubectl's error line with the body after its prefix.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

VERIFY = Path(__file__).with_name("verify.sh")

PRETTY = """{
    "capability": {
        "kind": "agent",
        "agent": {
            "agentId": "hebe-marketa",
            "nonRoutable": true
        }
    },
    "messages": []
}
"""
ONE_LINE = '{"ok":true,"checks":[{"name":"db","ok":true}]}\n'
ERROR_LINE = 'Error from server (ServiceUnavailable): {"ok":false,"checks":[{"name":"identity","ok":false}]}\n'


def run(script: str, kubectl_out: str = "", env: dict[str, str] | None = None) -> str:
    """Source verify.sh in bash with a fake kubectl that prints `kubectl_out`, run `script`, return stdout."""
    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp, "kubectl")
        Path(tmp, "out").write_text(kubectl_out)
        fake.write_text(f'#!/bin/sh\n[ -n "$KUBECTL_LOG" ] && echo "$@" >>"$KUBECTL_LOG"\ncat "{tmp}/out"\n')
        fake.chmod(0o755)
        full_env = {**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}", **(env or {})}
        res = subprocess.run(
            ["bash", "-c", f'source "{VERIFY}"; {script}'], capture_output=True, text=True, env=full_env, timeout=30
        )
        if res.returncode != 0:
            raise AssertionError(f"bash exited {res.returncode}: {res.stderr}")
        return res.stdout


class ProxyGet(unittest.TestCase):
    def test_pretty_printed_json_comes_back_whole_on_one_line(self) -> None:
        out = run("proxy_get capabilities-mcp:7501 /v1/capabilities/hebe-marketa", PRETTY)
        self.assertEqual(out.count("\n"), 1)
        self.assertEqual(json.loads(out)["capability"]["agent"]["nonRoutable"], True)

    def test_the_registry_check_reads_it(self) -> None:
        out = run("proxy_get x /y | jq_py \"(d.get('capability') or {}).get('agent', {}).get('nonRoutable')\"", PRETTY)
        self.assertEqual(out.strip(), "True")

    def test_one_line_json_unchanged(self) -> None:
        self.assertEqual(json.loads(run("proxy_get hebe:8765 /ready", ONE_LINE)), json.loads(ONE_LINE))

    def test_the_body_inside_kubectl_error_line(self) -> None:
        self.assertEqual(json.loads(run("proxy_get hebe:8765 /ready", ERROR_LINE))["ok"], False)

    def test_no_json_at_all_is_empty(self) -> None:
        self.assertEqual(run("proxy_get hebe:8765 /ready", "Error from server (NotFound): the server could not find it\n"), "\n")


class PodProxy(unittest.TestCase):
    """review-152 R3 — /ready is read through the pod proxy, which answers for a pod that is not Ready."""

    DEPLOY = json.dumps(
        {"spec": {"selector": {"matchLabels": {"app.kubernetes.io/name": "hebe", "app.kubernetes.io/instance": "hebe"}}}}
    )

    def test_the_selector_comes_from_the_deployment(self) -> None:
        out = run(f"selector_of <<<'{self.DEPLOY}'")
        self.assertEqual(out.strip(), "app.kubernetes.io/instance=hebe,app.kubernetes.io/name=hebe")

    def test_the_pod_proxy_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp, "args")
            out = run(
                "pod_proxy_get hebe-7c9d:8765 /ready",
                ONE_LINE,
                env={"KUBECTL_LOG": str(log)},
            )
            self.assertEqual(json.loads(out)["ok"], True)
            self.assertIn("get --raw /api/v1/namespaces/kantheon/pods/hebe-7c9d:8765/proxy/ready", log.read_text())


class Isolation(unittest.TestCase):
    def test_unset_is_manual_with_the_probe_line(self) -> None:
        out = run('check_isolation; echo "open=$OPEN"', env={"HEBE_VERIFY_ISOLATION": ""})
        self.assertIn("MANUAL  isolation", out)
        self.assertIn("x-forwarded-user: marketa", out)
        self.assertIn("open=1", out)

    def test_refused_passes(self) -> None:
        out = run('check_isolation; echo "pass=$PASS"', env={"HEBE_VERIFY_ISOLATION": "refused"})
        self.assertIn("PASS    isolation", out)


class Phone(unittest.TestCase):
    def test_not_performed_is_na_and_holds_nothing_open(self) -> None:
        out = run(
            'check_phone; echo "open=$OPEN fail=$FAIL na=$NA"',
            env={"HEBE_VERIFY_TELEGRAM": "ok", "HEBE_VERIFY_STRANGER": "not-performed"},
        )
        self.assertIn("N/A     unmapped-chat", out)
        self.assertIn("open=0 fail=0 na=1", out)

    def test_unset_stranger_stays_manual(self) -> None:
        out = run('check_phone; echo "open=$OPEN"', env={"HEBE_VERIFY_TELEGRAM": "ok", "HEBE_VERIFY_STRANGER": ""})
        self.assertIn("MANUAL  unmapped-chat", out)
        self.assertIn("open=1", out)


if __name__ == "__main__":
    unittest.main()
