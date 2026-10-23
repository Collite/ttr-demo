"""edge_login.py's Keycloak form parsing — no network.

    python3 -B -m unittest design/hebe-demo/rig-hb/test_edge_login.py      (`just hebe-verify-test`; a model-gate step)

The fixture is the form tag hartland's Keycloak 26 serves (2026-10-23, the session ids replaced): the action carries
`&amp;`-escaped query parameters that must be unescaped before the POST.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location("edge_login", Path(__file__).with_name("edge_login.py"))
edge_login = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(edge_login)

LIVE_FORM = (
    '<form id="kc-form-login" onsubmit="login.disabled = true; return true;" '
    'action="https://keycloak.hartland.collite.cz/realms/kantheon/login-actions/authenticate?session_code=SC&amp;'
    'execution=e63ff153-631c-4e6b-8988-dc20904ff928&amp;client_id=hebe-console&amp;tab_id=TAB&amp;client_data=CD" '
    'method="post">'
)


class LoginFormAction(unittest.TestCase):
    def test_the_live_form_action_unescaped(self) -> None:
        page = f"<html><body><div>{LIVE_FORM}<input name='username'></form></div></body></html>"
        self.assertEqual(
            edge_login.login_form_action(page),
            "https://keycloak.hartland.collite.cz/realms/kantheon/login-actions/authenticate?session_code=SC&"
            "execution=e63ff153-631c-4e6b-8988-dc20904ff928&client_id=hebe-console&tab_id=TAB&client_data=CD",
        )

    def test_action_before_id_also_found(self) -> None:
        page = '<form action="https://kc/x?a=1&amp;b=2" id="kc-form-login" method="post">'
        self.assertEqual(edge_login.login_form_action(page), "https://kc/x?a=1&b=2")

    def test_a_page_without_the_login_form(self) -> None:
        # e.g. Keycloak's error page, or the console answering directly
        self.assertIsNone(edge_login.login_form_action('<form id="kc-error" action="/x"></form>'))
        self.assertIsNone(edge_login.login_form_action("<html>console</html>"))


if __name__ == "__main__":
    unittest.main()
