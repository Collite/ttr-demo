"""Apply the LD layout pack to an explicitly enabled, allow-listed catalog (stdlib only)."""

import argparse
import base64
import copy
import json
import os
import ssl
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener

PACK = Path(__file__).resolve().parents[1] / 'openmetadata/layout'
ADDRESSES = {
    'bp-dsk': 'https://openmetadata.192-168-1-38.nip.io',
    'hartland': 'https://openmetadata.hartland.collite.cz',
}
# LD-C12: later stages fill the empty steps; this stage writes only the first three.
ORDER = ('theme', 'relation_types', 'personas_and_documents', 'accounts_and_team',
         'domains', 'workflow_and_form', 'content_except_reviewers', 'relations',
         'tasks', 'reviewers', 'announcement', 'chat_page')


class LayoutError(ValueError):
    """Only authored diagnostics, never credentials or server response bodies."""


def require(condition, message):
    if not condition:
        raise LayoutError(message)


def read_json(path):
    return json.loads(path.read_text())


def target_url(name, pack=PACK):
    targets = read_json(pack / 'targets.json')
    require(name in ADDRESSES and name in targets, 'unknown target')
    entry = targets[name]
    require(entry.get('address') == ADDRESSES[name], 'target address outside allow-list')
    require(entry.get('enabled') is True, 'target is disabled')
    return entry['address']


def credentials(env):
    token = env.get('OM_TOKEN', '').strip()
    if not token and env.get('OM_TOKEN_FILE'):
        try:
            token = Path(env['OM_TOKEN_FILE']).expanduser().read_text().strip()
        except OSError:
            raise LayoutError('cannot read OM_TOKEN_FILE') from None
    require(bool(token) and not any(c.isspace() for c in token),
            'missing or invalid OM_TOKEN / OM_TOKEN_FILE')
    return token


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Catalog:
    def __init__(self, target, env, pack=PACK):
        self.base = target_url(target, pack) + '/api/v1/'
        self._token = credentials(env)
        context = ssl.create_default_context(cafile=env.get('OM_CA_FILE') or None)
        self._opener = build_opener(NoRedirect(), HTTPSHandler(context=context))

    def request(self, method, path, body=None, missing=False):
        require(not path.startswith(('/', '.')) and '://' not in path,
                'invalid catalog resource')
        headers = {'Authorization': 'Bearer ' + self._token}
        if body is not None:
            headers['Content-Type'] = ('application/json-patch+json' if method == 'PATCH'
                                       else 'application/json')
        request = Request(self.base + path, method=method, headers=headers,
                          data=None if body is None else json.dumps(body).encode())
        try:
            with self._opener.open(request, timeout=30) as response:
                data = response.read()
                return json.loads(data) if data else None
        except HTTPError as error:
            if missing and method == 'GET' and error.code == 404:
                return None
            raise LayoutError('catalog request failed (HTTP ' + str(error.code) + ')') from None
        except Exception:
            raise LayoutError('catalog request failed; check connection and OM_CA_FILE') from None

    def get(self, path, missing=False):
        return self.request('GET', path, missing=missing)

    def write(self, method, path, body=None):
        return self.request(method, path, body)


@dataclass
class Operation:
    label: str
    method: str
    path: str
    body: object
    current: object
    desired: object

    @property
    def action(self):
        return ('unchanged' if self.current == self.desired else
                'create' if self.current is None else 'update')


def merge_relations(current, desired):
    """Keep every unowned type, including all system fields and list positions."""
    names = {item['name'] for item in desired}
    require(len(names) == len(desired), 'duplicate pack relation type')
    replacement = {item['name']: item for item in desired}
    result = copy.deepcopy(current)
    seen = set()
    types = []
    for item in current.get('relationTypes', []):
        name = item['name']
        if name in names:
            require(not item.get('isSystemDefined'), 'pack name collides with a system relation')
            require(name not in seen, 'duplicate catalog relation type')
            types.append(copy.deepcopy(replacement[name]))
            seen.add(name)
        else:
            types.append(copy.deepcopy(item))
    types.extend(copy.deepcopy(item) for item in desired if item['name'] not in seen)
    result['relationTypes'] = types
    return result


class Layout:
    def __init__(self, catalog, pack=PACK, output=print):
        self.catalog, self.pack, self.output = catalog, pack, output
        require(catalog.get('system/version').get('version') == '2.0.6',
                'expected OpenMetadata 2.0.6')
        self.admin = catalog.get('users/loggedInUser?fields=personas,defaultPersona')
        require(self.admin.get('isAdmin') is True, 'layout requires an admin token')

    def operations(self):
        for step in ORDER:
            yield from getattr(self, step, lambda: [])()

    def theme_value(self, current, removing=False):
        configured = read_json(self.pack / 'theme.json')
        result = copy.deepcopy(current)
        colors = result.setdefault('customTheme', {})
        for key, value in configured['customTheme'].items():
            colors[key] = '' if removing else value
        logos = result.setdefault('customLogoConfig', {})
        for key, value in configured['customLogoConfig'].items():
            if removing or not value:
                logos[key] = ''
            else:
                asset = self.pack / value
                require(asset.resolve().is_relative_to((self.pack / 'brand').resolve()),
                        'brand image outside pack')
                logos[key] = 'data:image/svg+xml;base64,' + base64.b64encode(asset.read_bytes()).decode()
        return result

    def theme(self):
        current = self.catalog.get('system/settings/customUiThemePreference')['config_value']
        desired = self.theme_value(current)
        for field, reason in read_json(self.pack / 'theme.json').get('imageSkips', {}).items():
            self.output(f'skip {field}: {reason}')
        return [Operation('theme', 'PUT', 'system/settings',
                          {'config_type': 'customUiThemePreference', 'config_value': desired},
                          current, desired)]

    def relation_types(self):
        current = self.catalog.get('system/settings/glossaryTermRelationSettings')['config_value']
        desired = merge_relations(current, read_json(self.pack / 'relation-types.json'))
        return [Operation('relation types and inverses', 'PUT', 'system/settings',
                          {'config_type': 'glossaryTermRelationSettings', 'config_value': desired},
                          current, desired)]

    def personas_and_documents(self):
        for desired in read_json(self.pack / 'personas.json'):
            name = desired['name']
            current = self.catalog.get('personas/name/' + quote(name, safe=''), missing=True)
            projected = None if current is None else {k: current.get(k) for k in desired}
            if current is None:
                method, path, body = 'PUT', 'personas', desired
            else:
                method, path = 'PATCH', 'personas/' + quote(current['id'], safe='')
                body = [{'op': 'add', 'path': '/' + k, 'value': v}
                        for k, v in desired.items() if current.get(k) != v]
            yield Operation('persona ' + name, method, path, body, projected, desired)
        for path in sorted((self.pack / 'persona-ui').glob('*.json')):
            desired = read_json(path)
            fqn = desired['fullyQualifiedName']
            require(fqn == 'persona.' + path.stem and
                    path.stem in {'ttr-model-steward', 'ttr-model-reader'},
                    'layout document outside pack ownership')
            current = self.catalog.get('docStore/name/' + quote(fqn, safe=''), missing=True)
            projected = None if current is None else {k: current.get(k) for k in desired}
            yield Operation('document ' + fqn, 'PUT', 'docStore', desired, projected, desired)
        yield self.membership()

    def membership(self):
        admin = self.catalog.get('users/loggedInUser?fields=personas,defaultPersona')
        refs = copy.deepcopy(admin.get('personas') or [])
        current_ids = {ref['id'] for ref in refs}
        stock = None
        for persona in read_json(self.pack / 'personas.json'):
            name = persona['name']
            item = self.catalog.get('personas/name/' + quote(name, safe=''), missing=True)
            ref = {'id': item['id'] if item else 'new:' + name, 'type': 'persona'}
            if ref['id'] not in {r['id'] for r in refs}:
                refs.append(ref)
            if name == 'ttr-stock-view':
                stock = ref
        current = {'personas': sorted(current_ids),
                   'defaultPersona': (admin.get('defaultPersona') or {}).get('id')}
        desired = {'personas': sorted(ref['id'] for ref in refs), 'defaultPersona': stock['id']}
        body = [{'op': 'add', 'path': '/personas', 'value': refs},
                {'op': 'add', 'path': '/defaultPersona', 'value': stock}]
        return Operation('admin personas and Stock view', 'PATCH',
                         'users/' + quote(admin['id'], safe=''), body, current, desired)

    def verify(self, applying=False):
        return 0

    def run(self, verb='plan', execute=False):
        require(verb in ('plan', 'apply', 'verify', 'remove'), 'unknown verb')
        if verb == 'verify':
            return self.verify()
        if verb == 'remove':
            return self.remove(execute)
        for operation in self.operations():
            self.output(f'{operation.action} {operation.label}')
            if verb == 'apply' and operation.action != 'unchanged':
                self.catalog.write(operation.method, operation.path, operation.body)
        return self.verify(applying=True) if verb == 'apply' else 0

    def remove(self, execute=False):
        return 0


def main(argv=None, env=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('verb', choices=('plan', 'apply', 'verify', 'remove'),
                        nargs='?', default='plan')
    parser.add_argument('--target', required=True, choices=tuple(ADDRESSES))
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    require(not args.execute or args.verb == 'remove', '--execute is only for remove')
    env = os.environ if env is None else env
    return Layout(Catalog(args.target, env)).run(args.verb, args.execute)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except LayoutError as error:
        raise SystemExit(str(error)) from None
    except Exception:
        raise SystemExit('layout failed; credentials and response bodies omitted') from None
