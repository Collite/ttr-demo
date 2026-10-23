"""HE-P1 · S1.1 T3 — the two Hebe seed scripts, driven end to end against a fake `az` (a vault in a directory) and a
fake `curl` (a Keycloak token endpoint), both first on PATH. No cluster, no Azure, no network.

    python3 -B -m unittest scripts/test_seed_hebe_offline_token.py      (`just hebe-seed-test`)

What they must hold (the scripts' headers, HE contracts §3/§9):
  - the password, the client secret and the tokens never reach stdout/stderr or any process's argv;
  - the seed is a password grant on `hebe` with `scope=openid offline_access`, stored only when Keycloak answered an
    Offline token for the right user; a seed already in the vault is not overwritten without --rotate;
  - --verify mints with the refresh_token grant, prints who the token is, and leaves the vault as it was;
  - every temp file is gone when the script exits, whatever the outcome.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OFFLINE = ROOT / "scripts" / "seed-hebe-offline-token.sh"
CLIENT = ROOT / "scripts" / "seed-hebe-client-secret.sh"

CLIENT_SECRET = "c0ffee" * 10 + "abcd"  # 64 hex chars, as seed-hebe-client-secret.sh writes
PASSWORD = "Pa$$ w0rd&=+%"  # characters a form body must encode
SUB = "c7ab4e7f-3627-41ff-ab46-32cb3189963a"

FAKE_AZ = r'''#!/usr/bin/env python3
"""A Key Vault in $FAKE_VAULT (one file per secret). Logs argv to $FAKE_LOG."""
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps({"tool": "az", "argv": args}) + "\n")
def opt(name):
    return args[args.index(name) + 1] if name in args else None
vault = os.environ["FAKE_VAULT"]
if args[:2] == ["account", "show"]:
    print("{}"); sys.exit(0)
if args[:3] == ["keyvault", "secret", "show"]:
    path = os.path.join(vault, opt("--name"))
    if not os.path.exists(path):
        sys.stderr.write("(SecretNotFound) A secret with (name/id) %s was not found\n" % opt("--name")); sys.exit(3)
    value = open(path).read()
    print(value if opt("--query") == "value" else json.dumps({"name": opt("--name"), "value": value}))
    sys.exit(0)
if args[:3] == ["keyvault", "secret", "set"]:
    value = open(opt("--file")).read() if opt("--file") else opt("--value")
    open(os.path.join(vault, opt("--name")), "w").write(value)
    sys.exit(0)
sys.stderr.write("fake az: unsupported %r\n" % args); sys.exit(9)
'''

FAKE_CURL = r'''#!/usr/bin/env python3
"""A Keycloak token endpoint and iris-bff's POST /v1/session, driven by $FAKE_KC (JSON). Logs argv, the decoded form
and the headers to $FAKE_LOG."""
import base64, json, os, sys
args = sys.argv[1:]
form, headers, out, fmt, url, i = {}, [], None, "", "", 0
while i < len(args):
    a = args[i]
    if a == "-H":
        h = args[i + 1]; i += 2
        headers.append(open(h[1:]).read() if h.startswith("@") else h)
        continue
    if a == "--data": i += 2; continue
    if a.startswith("http"): url = a; i += 1; continue
    if a == "--data-urlencode":
        spec = args[i + 1]; i += 2
        name, sep, rest = spec.partition("=")
        if not sep or "@" in name:
            name, _, path = spec.partition("@")
            rest = open(path).read()
        form[name] = rest
        continue
    if a == "-o": out = args[i + 1]; i += 2; continue
    if a == "-w": fmt = args[i + 1]; i += 2; continue
    if a == "-X": i += 2; continue
    i += 1
kc = json.load(open(os.environ["FAKE_KC"]))
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps({"tool": "curl", "argv": args, "form": form, "url": url, "headers": headers}) + "\n")
def jwt(claims):
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return b({"alg": "HS512"}) + "." + b(claims) + ".sig"
def answer(status, body):
    open(out, "w").write(json.dumps(body))
    with open(os.environ["FAKE_LOG"], "a") as f:
        f.write(json.dumps({"tool": "keycloak", "argv": [], "response": body}) + "\n")
    sys.stdout.write(fmt.replace("%{http_code}", str(status)))
    sys.exit(0)
minted = os.path.join(os.path.dirname(os.environ["FAKE_KC"]), "minted_access")
if url.endswith("/v1/session"):
    ok = os.path.exists(minted) and "Authorization: Bearer " + open(minted).read() in headers
    if ok and not kc.get("iris_refuses"):
        answer(201, {"sessionId": "sess-1"})
    answer(401, {"errorCode": "unauthenticated", "message": "bad bearer"})
if form.get("client_id") != "hebe" or form.get("client_secret") != kc["client_secret"]:
    answer(401, {"error": "unauthorized_client", "error_description": "Invalid client or Invalid client credentials"})
access = jwt({"sub": kc["sub"], "preferred_username": kc.get("minted_user", kc["user"]), "azp": kc.get("azp", "hebe"),
              "typ": "Bearer", "exp": 1792780982})
if form.get("grant_type") == "password":
    if form.get("username") != kc["user"] or form.get("password") != kc["password"]:
        answer(401, {"error": "invalid_grant", "error_description": "Invalid user credentials"})
    if kc.get("offline_denied"):
        answer(400, {"error": "not_allowed", "error_description": "Offline tokens not allowed for the user or client"})
    offline = "offline_access" in form.get("scope", "").split()
    typ = kc.get("typ") or ("Offline" if offline else "Refresh")
    answer(200, {"access_token": access, "refresh_token": jwt({"typ": typ, "sid": kc.get("sid", "s1")}),
                 "token_type": "Bearer"})
if form.get("grant_type") == "refresh_token":
    if not kc.get("session_alive", True):
        answer(400, {"error": "invalid_grant", "error_description": "Offline session not active"})
    open(minted, "w").write(access)
    answer(200, {"access_token": access, "refresh_token": jwt({"typ": "Offline", "sid": "rotated"})})
answer(400, {"error": "unsupported_grant_type"})
'''


def jwt(claims: dict) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")  # noqa: E731
    return enc({"alg": "HS512"}) + "." + enc(claims) + ".sig"


class Harness(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="hebe-seed-test-"))
        self.bin = self.dir / "bin"
        self.vault = self.dir / "vault"
        self.tmp = self.dir / "tmp"
        for d in (self.bin, self.vault, self.tmp):
            d.mkdir()
        for name, body in (("az", FAKE_AZ), ("curl", FAKE_CURL)):
            p = self.bin / name
            p.write_text(body)
            p.chmod(0o755)
        self.log = self.dir / "calls.jsonl"
        self.log.touch()
        self.kc = {"client_secret": CLIENT_SECRET, "user": "marketa", "password": PASSWORD, "sub": SUB}

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def put(self, name: str, value: str) -> None:
        (self.vault / name).write_text(value)

    def vault_value(self, name: str) -> str | None:
        p = self.vault / name
        return p.read_text() if p.exists() else None

    def run_script(self, script: Path, *args: str, stdin: str = "", env: dict | None = None) -> subprocess.CompletedProcess:
        (self.dir / "kc.json").write_text(json.dumps(self.kc))
        env = {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "HOME": str(self.dir),
            "TMPDIR": str(self.tmp),
            "FAKE_VAULT": str(self.vault),
            "FAKE_LOG": str(self.log),
            "FAKE_KC": str(self.dir / "kc.json"),
            **(env or {}),
        }
        return subprocess.run(["bash", str(script), *args], input=stdin, capture_output=True, text=True, env=env,
                              timeout=60)

    def calls(self, tool: str) -> list[dict]:
        return [c for c in map(json.loads, self.log.read_text().splitlines()) if c["tool"] == tool]

    def assert_never_shown(self, result: subprocess.CompletedProcess, *secrets: str) -> None:
        """[secrets] and every token Keycloak answered appear in no output and no argv."""
        calls = list(map(json.loads, self.log.read_text().splitlines()))
        argv = [a for c in calls for a in c["argv"]]
        tokens = [v for c in calls for k, v in c.get("response", {}).items() if k.endswith("_token")]
        for s in (*secrets, *tokens):
            self.assertNotIn(s, result.stdout, "a secret on stdout")
            self.assertNotIn(s, result.stderr, "a secret on stderr")
            for a in argv:
                self.assertNotIn(s, a, f"a secret in argv: {a[:40]}…")

    def assert_tmp_clean(self) -> None:
        self.assertEqual(list(self.tmp.iterdir()), [], "the script left temp files behind")


class OfflineTokenSeed(Harness):
    def setUp(self) -> None:
        super().setUp()
        self.put("hebe-client-secret", CLIENT_SECRET)

    def test_seeds_an_offline_token_without_showing_any_secret(self) -> None:
        r = self.run_script(OFFLINE, "marketa", "marketa", stdin=PASSWORD + "\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        seed = self.vault_value("hebe-marketa-offline-token")
        self.assertIsNotNone(seed, "nothing stored")
        self.assertEqual(json.loads(base64.urlsafe_b64decode(seed.split(".")[1] + "=="))["typ"], "Offline")
        self.assertIn(f"{len(seed)} chars, typ=Offline, for marketa", r.stdout)
        [req] = self.calls("curl")
        self.assertEqual(req["form"]["grant_type"], "password")
        self.assertEqual(req["form"]["client_id"], "hebe")
        self.assertEqual(req["form"]["username"], "marketa")
        self.assertEqual(req["form"]["scope"], "openid offline_access")
        self.assertEqual(req["form"]["password"], PASSWORD, "the password must reach Keycloak byte for byte")
        self.assertTrue(any(a.endswith("/realms/kantheon/protocol/openid-connect/token") for a in req["argv"]))
        self.assert_never_shown(r, PASSWORD, CLIENT_SECRET, seed)
        self.assert_tmp_clean()

    def test_refuses_to_overwrite_a_seed_and_rotate_replaces_it(self) -> None:
        self.put("hebe-marketa-offline-token", "old-seed")
        r = self.run_script(OFFLINE, "marketa", "marketa", stdin=PASSWORD + "\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("already holds 'hebe-marketa-offline-token'", r.stderr)
        self.assertEqual(self.calls("curl"), [], "no password grant when the seed exists")
        self.assertEqual(self.vault_value("hebe-marketa-offline-token"), "old-seed")

        r = self.run_script(OFFLINE, "marketa", "marketa", "--rotate", stdin=PASSWORD + "\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotEqual(self.vault_value("hebe-marketa-offline-token"), "old-seed")
        self.assert_tmp_clean()

    def test_an_online_refresh_token_is_not_stored(self) -> None:
        self.kc["typ"] = "Refresh"  # what a client without the offline_access scope answers
        r = self.run_script(OFFLINE, "marketa", "marketa", stdin=PASSWORD + "\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("'Refresh' refresh token, not an Offline one", r.stderr)
        self.assertIsNone(self.vault_value("hebe-marketa-offline-token"))
        self.assert_tmp_clean()

    def test_keycloak_errors_are_named_and_store_nothing(self) -> None:
        cases = [
            ({"password": "something else"}, "Invalid user credentials", "wrong password"),
            ({"client_secret": "rotated-in-keycloak-only"}, "Invalid client", "is the realm PR applied"),
            ({"offline_denied": True}, "Offline tokens not allowed", "lacks the realm role offline_access"),
        ]
        for change, error, hint in cases:
            with self.subTest(error=error):
                self.kc = {"client_secret": CLIENT_SECRET, "user": "marketa", "password": PASSWORD, "sub": SUB, **change}
                r = self.run_script(OFFLINE, "marketa", "marketa", stdin=PASSWORD + "\n")
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(error, r.stderr)
                self.assertIn(hint, r.stderr)
                self.assertIsNone(self.vault_value("hebe-marketa-offline-token"))
                self.assert_never_shown(r, PASSWORD, CLIENT_SECRET)
                self.assert_tmp_clean()

    def test_a_token_for_someone_else_is_not_stored(self) -> None:
        self.kc["minted_user"] = "maya"
        r = self.run_script(OFFLINE, "marketa", "marketa", stdin=PASSWORD + "\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("the token is for 'maya', not 'marketa'", r.stderr)
        self.assertIsNone(self.vault_value("hebe-marketa-offline-token"))

    def test_without_the_client_secret_it_stops_before_asking_keycloak(self) -> None:
        (self.vault / "hebe-client-secret").unlink()
        r = self.run_script(OFFLINE, "marketa", "marketa", stdin=PASSWORD + "\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("seed-hebe-client-secret.sh", r.stderr)
        self.assertEqual(self.calls("curl"), [])

    def test_an_empty_password_stops_it(self) -> None:
        r = self.run_script(OFFLINE, "marketa", "marketa", stdin="\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no password given", r.stderr)
        self.assertEqual(self.calls("curl"), [])

    def test_usage(self) -> None:
        for args in ((), ("marketa",), ("marketa", "marketa", "--bogus"), ("Marketa!", "marketa")):
            with self.subTest(args=args):
                self.assertEqual(self.run_script(OFFLINE, *args).returncode, 2)


class OfflineTokenVerify(Harness):
    def setUp(self) -> None:
        super().setUp()
        self.put("hebe-client-secret", CLIENT_SECRET)
        self.seed = jwt({"typ": "Offline", "sid": "s1"})
        self.put("hebe-marketa-offline-token", self.seed)

    def test_mints_from_the_seed_prints_who_it_is_and_iris_bff_accepts_it(self) -> None:
        r = self.run_script(OFFLINE, "marketa", "marketa", "--verify")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"sub={SUB} preferred_username=marketa azp=hebe exp=2026-10-23T", r.stdout)
        self.assertIn("iris-bff accepted it: POST /v1/session → 201 (session sess-1)", r.stdout)
        req, session = self.calls("curl")
        self.assertEqual(session["url"], "https://iris.hartland.collite.cz/bff/v1/session")
        self.assertEqual(req["form"]["grant_type"], "refresh_token")
        self.assertEqual(req["form"]["refresh_token"], self.seed)
        self.assertNotIn("password", req["form"])
        self.assertEqual(self.vault_value("hebe-marketa-offline-token"), self.seed, "--verify must not touch the vault")
        self.assertEqual([c for c in self.calls("az") if c["argv"][:3] == ["keyvault", "secret", "set"]], [])
        self.assert_never_shown(r, CLIENT_SECRET, self.seed)
        self.assert_tmp_clean()

    def test_iris_bff_refusing_the_bearer_fails_and_names_the_audience(self) -> None:
        self.kc["iris_refuses"] = True
        r = self.run_script(OFFLINE, "marketa", "marketa", "--verify")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("iris-bff answered HTTP 401 to POST /v1/session: unauthenticated", r.stderr)
        self.assertIn("audience", r.stderr)
        self.assert_never_shown(r, CLIENT_SECRET, self.seed)
        self.assert_tmp_clean()

    def test_an_empty_iris_bff_url_skips_the_session(self) -> None:
        r = self.run_script(OFFLINE, "marketa", "marketa", "--verify", env={"IRIS_BFF_URL": ""})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.calls("curl")), 1)

    def test_a_lapsed_offline_session_says_to_reseed(self) -> None:
        self.kc["session_alive"] = False
        r = self.run_script(OFFLINE, "marketa", "marketa", "--verify")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Offline session not active", r.stderr)
        self.assertIn("re-seed with --rotate", r.stderr)
        self.assert_tmp_clean()

    def test_a_seed_for_another_user_fails(self) -> None:
        self.kc["minted_user"] = "maya"
        r = self.run_script(OFFLINE, "marketa", "marketa", "--verify")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("acts as 'maya', not 'marketa'", r.stderr)

    def test_nothing_to_verify(self) -> None:
        (self.vault / "hebe-marketa-offline-token").unlink()
        r = self.run_script(OFFLINE, "marketa", "marketa", "--verify")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nothing to verify", r.stderr)
        self.assertEqual(self.calls("curl"), [])


class ClientSecretSeed(Harness):
    KEYS = ("hebe-client-secret", "hebe-console-oidc-client-secret")

    def test_creates_both_keys_as_64_hex_chars_without_showing_them(self) -> None:
        r = self.run_script(CLIENT)
        self.assertEqual(r.returncode, 0, r.stderr)
        values = [self.vault_value(k) for k in self.KEYS]
        for k, v in zip(self.KEYS, values):
            self.assertIsNotNone(v, f"{k} not stored")
            self.assertRegex(v, r"^[0-9a-f]{64}$", k)
        self.assertNotEqual(values[0], values[1], "two clients, two secrets")
        self.assert_never_shown(r, *values)
        self.assert_tmp_clean()

    def test_is_idempotent_and_keeps_existing_values(self) -> None:
        self.put("hebe-client-secret", "f" * 64)
        r = self.run_script(CLIENT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.vault_value("hebe-client-secret"), "f" * 64)
        self.assertIn("'hebe-client-secret' already present", r.stdout)
        self.assertRegex(self.vault_value("hebe-console-oidc-client-secret") or "", r"^[0-9a-f]{64}$")
        sets = [c["argv"] for c in self.calls("az") if c["argv"][:3] == ["keyvault", "secret", "set"]]
        self.assertEqual([a[a.index("--name") + 1] for a in sets], ["hebe-console-oidc-client-secret"])

    def test_a_short_existing_value_is_reported_not_replaced(self) -> None:
        self.put("hebe-client-secret", "short")
        r = self.run_script(CLIENT)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("only 5 characters", r.stderr)
        self.assertEqual(self.vault_value("hebe-client-secret"), "short")


if __name__ == "__main__":
    unittest.main()
