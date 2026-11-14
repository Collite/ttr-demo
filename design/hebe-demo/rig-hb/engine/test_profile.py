"""Five profile behaviours: selection, required engine, image, N/A, state isolation."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('he_engine_profile', HERE / 'profile.py')
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


def sourced(args='', body='echo "$PROFILE|$CONTEXT|$HOST|$STATE"', env=None):
    return subprocess.run(['bash', '-c', f'source "{HERE.parent / "verify.sh"}" {args}; {body}'],
                          text=True, capture_output=True, env={**os.environ, **(env or {})})


class EngineProfile(unittest.TestCase):
    def test_selection_is_explicit_and_requires_ca(self):
        self.assertIn('full|hartland|hebe.hartland.collite.cz', sourced().stdout)
        self.assertNotEqual(sourced('--profile typo').returncode, 0)
        self.assertNotEqual(sourced('--profile engine', env={'HEBE_VERIFY_CA_FILE': ''}).returncode, 0)
        with tempfile.NamedTemporaryFile() as ca:
            result = sourced('--profile engine', env={'HEBE_VERIFY_CA_FILE': ca.name,
                                                     'CONTEXT': 'hartland', 'HOST': 'wrong'})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('engine|bp-dsk|hebe.192-168-1-38.nip.io', result.stdout)

    def test_missing_or_failed_engine_and_durability_fail(self):
        names = ['Process engine', 'OBO mint', 'State durability', 'Console admission',
                 'Console token keys', 'Receipts signing key']
        checks = [{'name': n, 'status': 'pass', 'message': 'OK'} for n in names]
        checks[2]['message'] = 'workspace=postgres receipts=postgres (fs.durability=ephemeral)'
        self.assertIn('six', profile.doctor('log\n' + json.dumps({'checks': checks})))
        for broken in [checks[1:], [{**c, 'status': 'fail'} if c['name'] == names[0] else c for c in checks]]:
            with self.assertRaises(ValueError):
                profile.doctor(json.dumps({'checks': broken}))
        checks[2]['message'] = 'workspace=filesystem receipts=filesystem'
        with self.assertRaises(ValueError):
            profile.doctor(json.dumps({'checks': checks}))
        with self.assertRaises(ValueError):
            profile.doctor('connection failed')

    def test_exact_image_requires_app_init_and_only_new_pod(self):
        deploy = {'spec': {'replicas': 1, 'template': {'spec': {'containers': [{'image': profile.IMAGE}]}}},
                  'status': {'readyReplicas': 1}}
        pod = {'metadata': {}, 'status': {
            'containerStatuses': [{'ready': True, 'imageID': 'ghcr.io/collite/hebe@' + profile.DIGEST}],
            'initContainerStatuses': [{'imageID': 'ghcr.io/collite/hebe@' + profile.DIGEST,
                                      'state': {'terminated': {'exitCode': 0}}}]}}
        self.assertIn('Ready', profile.image(deploy, {'items': [pod]}))
        for field in ['containerStatuses', 'initContainerStatuses']:
            bad = copy.deepcopy(pod)
            bad['status'][field][0]['imageID'] = 'ghcr.io/collite/hebe@sha256:wrong'
            with self.assertRaises(ValueError):
                profile.image(deploy, {'items': [bad]})
        with self.assertRaises(ValueError):
            profile.image(deploy, {'items': [pod, pod]})
        deploy['spec']['template']['spec']['containers'][0]['image'] = 'ghcr.io/collite/hebe:0.11.9'
        with self.assertRaises(ValueError):
            profile.image(deploy, {'items': [pod]})

    def test_only_phone_rows_are_na_in_engine_profile(self):
        cm = json.dumps({'data': {'config.toml': '[channels.telegram]\nenabled=false\n[engine]\ndeliver_channels=["web"]\nrest_url="http://process-engine.process-engine.svc/engine-rest"'}})
        with tempfile.NamedTemporaryFile() as ca:
            body = 'kc(){ printf "%s" "$FAKE_CM"; }; check_phone; echo "na=$NA open=$OPEN"'
            result = sourced('--profile engine', body,
                             {'HEBE_VERIFY_CA_FILE': ca.name, 'FAKE_CM': cm})
            self.assertEqual(result.stdout.count('N/A'), 2)
            self.assertIn('na=2 open=0', result.stdout)
            self.assertNotIn('brief', result.stdout)
            result = sourced('--profile engine', body,
                             {'HEBE_VERIFY_CA_FILE': ca.name, 'FAKE_CM': cm.replace('false', 'true')})
            self.assertIn('FAIL', result.stdout)
            self.assertFalse(any(line.startswith('N/A') for line in result.stdout.splitlines()))
        text = (HERE.parent / 'verify.sh').read_text()
        self.assertIn('if [ "$PROFILE" = full ]; then check_brief', text)

    def test_state_is_separate_by_cluster_and_profile(self):
        with tempfile.NamedTemporaryFile() as ca:
            env = {'HEBE_VERIFY_CA_FILE': ca.name, 'HEBE_VERIFY_STATE': '/tmp/cert-state'}
            full = sourced(env=env).stdout
            engine = sourced('--profile engine', env=env).stdout
            self.assertIn('|/tmp/cert-state\n', full)
            self.assertIn('|/tmp/cert-state/bp-dsk/engine/marketa.json', engine)
            self.assertNotEqual(full, engine)


if __name__ == '__main__':
    unittest.main()
