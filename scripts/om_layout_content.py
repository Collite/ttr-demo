"""Frozen LD content operations. Credentials remain in process memory only."""
import base64
import copy
import html
import json
import secrets
import time
import uuid
from urllib.parse import quote, urlencode


def ref(item, kind):
    return {'id': item['id'], 'type': kind}


REFERENCE_LISTS = {"relatedTerms", "relatedMetrics", "reviewers", "owners", "domains", "tags", "personas"}


def subset(actual, desired, field=None):
    """Compare authored fields while tolerating server reference/default metadata."""
    if isinstance(desired, dict):
        return isinstance(actual, dict) and all(subset(actual.get(k), v, k) for k, v in desired.items())
    if isinstance(desired, list):
        if field in REFERENCE_LISTS:
            return (isinstance(actual, list) and
                    all(any(subset(a, d) for a in actual) for d in desired) and
                    all(any(subset(a, d) for d in desired) for a in actual))
        return isinstance(actual, list) and len(actual) == len(desired) and all(
            subset(a, b) for a, b in zip(actual, desired))
    return actual == desired


class Content:
    def missing_object(self, qname):
        if self.check_skips is not None:
            self.check_skips.add(qname)
        elif qname not in self.reported_missing:
            self.output('skip ' + qname + ': not in this catalog')
            self.reported_missing.add(qname)

    def listing(self, resource, fields='', **filters):
        items, after, seen = [], None, set()
        while True:
            query = dict(filters, limit=100, fields=fields)
            if after:
                query['after'] = after
            page = self.catalog.get(resource + '?' + urlencode(query))
            items.extend(page['data'])
            after = page.get('paging', {}).get('after')
            if not after:
                return items
            self.require(after not in seen, 'repeated catalog cursor')
            seen.add(after)

    def named(self, resource, name, fields=''):
        return self.catalog.get(resource + '/name/' + quote(name, safe='') +
                                ('?fields=' + fields if fields else ''), missing=True)

    def patch_fields(self, label, resource, current, desired):
        projected = {k: current.get(k) for k in desired}
        equal = subset(projected, desired)
        body = [{'op': 'add', 'path': '/' + k, 'value': v}
                for k, v in desired.items() if not subset(current.get(k), v)]
        return self.operation(label, 'PATCH', resource + '/' + current['id'], body,
                              desired if equal else projected, desired)

    def upsert(self, label, resource, desired, fields=''):
        current = self.named(resource, desired['name'], fields)
        if current:
            return self.patch_fields(label, resource, current, desired)
        return self.operation(label, 'POST', resource, desired, None, desired)

    def reference(self, resource, name, kind):
        item = self.named(resource, name)
        result = ref(item, kind) if item else {'id': 'new:' + name, 'type': kind}
        if kind == 'persona':
            # OM 2.0.6 sorts patched user personas by EntityReference.name.
            result['name'] = name
        return result

    def accounts_and_team(self):
        for person in self.content['accounts']:
            desired = copy.deepcopy(person)
            persona = desired.pop('persona', None)
            if persona:
                desired['personas'] = [self.reference('personas', persona, 'persona')]
                desired['defaultPersona'] = desired['personas'][0]
            op = self.upsert('account ' + person['name'], 'users', desired, 'personas,defaultPersona')
            if op.current is None:
                # Construct a password only when executed; it never enters a plan or an Operation.
                def create(desired=desired):
                    body = copy.deepcopy(desired)
                    if not body.get('isBot'):
                        password = self.env.get('OM_DEMO_PASSWORD') or secrets.token_urlsafe(32)
                        body.update(createPasswordType='ADMIN_CREATE', password=password,
                                    confirmPassword=password)
                    else:
                        body['authenticationMechanism'] = {'authType': 'JWT', 'config': {'JWTTokenExpiry': 'OneHour'}}
                    return self.catalog.write('POST', 'users', body)
                op.executor = create
            yield op
        yield self.upsert('team sales-team', 'teams', self.content['team'])

    def actor(self, name):
        if not self.env.get('OM_DEMO_PASSWORD'):
            return self.catalog
        if name in self.actors:
            return self.actors[name]
        user = next(a for a in self.content['accounts'] if a['name'] == name)
        try:
            if user.get('isBot'):
                record = self.named('users', name)
                result = self.catalog.get('users/token/' + record['id'])
                if result.get('JWTTokenExpiresAt', float('inf')) < (time.time() + 300) * 1000:
                    result = self.catalog.write('POST', 'users/generateToken',
                             {'id': record['id'], 'JWTTokenExpiry': 'OneHour'})
                token = result.get('JWTToken')
            else:
                password = base64.b64encode(self.env['OM_DEMO_PASSWORD'].encode()).decode()
                result = self.catalog.write('POST', 'users/login', {'email': user['email'], 'password': password})
                token = result.get('accessToken')
            self.require(bool(token), 'account sign-in returned no access token')
            client = self.catalog.as_token(token)
            self.actors[name] = client
            return client
        except self.error:
            self.output('skip actor ' + name + ': sign-in unavailable; admin performs its actions')
            self.actors[name] = self.catalog
            return self.catalog

    def write_as(self, name, method, path, body):
        client = self.actor(name)
        try:
            return client.write(method, path, body)
        except self.error as error:
            if client is self.catalog or error.status not in (401, 403):
                raise
            self.output('skip actor ' + name + ': HTTP ' + str(error.status) +
                        '; admin performs the refused action')
            return self.catalog.write(method, path, body)

    def domains(self):
        for domain in self.content['domains']:
            yield self.upsert('domain ' + domain['name'], 'domains', domain)

    def workflow_value(self):
        desired = json.loads((self.pack / 'workflow.json').read_text())
        for node in desired['nodes']:
            if node['name'] == 'Publication':
                node['config']['assignees']['candidates'] = [
                    self.reference('users', 'tatrman-maintainer', 'user')]
        return desired

    def workflow_and_form(self):
        yield self.upsert('workflow ttrSuggestionWorkflow', 'governance/workflowDefinitions',
                          self.workflow_value())
        desired = json.loads((self.pack / 'task-form.json').read_text())
        yield self.upsert('form ttrSuggestChange', 'taskFormSchemas', desired)

    def objects(self):
        world = json.loads((self.pack / 'targets.json').read_text())[self.target]['world']
        all_terms = self.listing('glossaryTerms', 'extension,parent,relatedTerms,reviewers,owners,domains')
        terms = {}
        for spec in self.content['terms']:
            matches = [t for t in all_terms if t.get('extension', {}).get('ttrQname') == spec['qname']
                       and t.get('glossary', {}).get('name') == world + ' ' + spec['glossary']]
            self.require(len(matches) <= 1, 'expected one projected term: ' + spec['qname'])
            if not matches and spec['qname'] != 'cn.role.Customer':
                self.missing_object(spec['qname'])
                continue
            self.require(bool(matches), 'expected one projected term: ' + spec['qname'])
            terms[spec['qname']] = matches[0]
        return terms

    def metric_objects(self):
        return self.listing('metrics', 'extension,relatedMetrics,tags,domains')

    def metric_object(self, qname, metrics=None):
        matches = [m for m in (self.metric_objects() if metrics is None else metrics)
                   if m.get('extension', {}).get('ttrQname') == qname]
        self.require(len(matches) <= 1, 'expected one projected metric: ' + qname)
        if not matches:
            self.missing_object(qname)
            return None
        return matches[0]

    def fields(self, current, spec, terms):
        desired = copy.deepcopy(spec['fields'])
        for key in ('extension', 'style'):
            if key in desired:
                desired[key] = dict(current.get(key) or {}, **desired[key])
        for key, resource, kind in [('owners', 'teams', 'team'), ('domains', 'domains', 'domain')]:
            if key in desired:
                desired[key] = [self.reference(resource, name, kind) for name in desired[key]]
        if 'parent' in desired:
            desired['parent'] = ref(terms[desired['parent']], 'glossaryTerm')
        if 'relatedMetrics' in desired:
            metrics = [self.metric_object(q) for q in desired['relatedMetrics']]
            desired['relatedMetrics'] = [ref(m, 'metric') for m in metrics if m is not None]
        if 'glossaryTerm' in desired:
            sale = terms.get(desired.pop('glossaryTerm'))
            if sale:
                kept = [t for t in current.get('tags', []) if t.get('tagFQN') != sale['fullyQualifiedName']]
                desired['tags'] = kept + [{'tagFQN': sale['fullyQualifiedName'], 'source': 'Glossary',
                                          'labelType': 'Manual', 'state': 'Confirmed'}]
        return desired

    def content_except_reviewers(self):
        terms = self.objects()
        for spec in self.content['terms']:
            if spec['qname'] not in terms:
                continue
            current = terms[spec['qname']]
            desired = self.fields(current, spec, terms)
            yield self.patch_fields('term ' + spec['qname'], 'glossaryTerms', current, desired)
        spec = self.content['table']
        table = self.named('tables', spec['fqn'], 'extension,owners,domains')
        if table is None:
            self.missing_object(spec['qname'])
        else:
            self.require(table.get('extension', {}).get('ttrQname') == spec['qname'],
                         'expected projected CZ customer table')
            yield self.patch_fields('CZ customer table', 'tables', table, self.fields(table, spec, terms))
        spec = self.content['metric']
        metric = self.metric_object(spec['qname'])
        if metric is not None:
            yield self.patch_fields('metric ' + spec['qname'], 'metrics', metric, self.fields(metric, spec, terms))

    def relation_value(self, current, target, relation_type):
        # Replace only the plain/owned edge of this pair, preserving every other edge.
        owned = {t['name'] for t in json.loads((self.pack / 'relation-types.json').read_text())}
        related = current.get('relatedTerms') or []
        matches = [r for r in related if r['term']['id'] == target['id'] and
                   r.get('relationType', 'relatedTo') in owned | {'relatedTo'}]
        if len(matches) == 1 and matches[0].get('relationType') == relation_type:
            return related
        kept = [r for r in related if not (r['term']['id'] == target['id'] and
                r.get('relationType', 'relatedTo') in owned | {'relatedTo'})]
        return kept + [{'term': ref(target, 'glossaryTerm'), 'relationType': relation_type}]

    def relations(self):
        types = {t['name']: t for t in json.loads((self.pack / 'relation-types.json').read_text())}
        for source, relation_type, target in self.content['relations']:
            # Re-read for every pair: patching one end hydrates the reciprocal end on OM.
            terms = self.objects()
            if source not in terms or target not in terms:
                continue
            for a, b, typ in [(source, target, relation_type),
                              (target, source, types[relation_type]['inverseRelation'])]:
                current = self.named('glossaryTerms', terms[a]['fullyQualifiedName'], 'relatedTerms')
                desired = {'relatedTerms': self.relation_value(current, terms[b], typ)}
                yield self.patch_fields('relation ' + a + ' ' + typ + ' ' + b,
                                        'glossaryTerms', current, desired)

    def customer(self):
        return self.objects()['cn.role.Customer']

    def task_list(self):
        return self.listing('tasks', 'about,payload,comments,assignees,availableTransitions,createdBy',
                            aboutEntity=self.customer()['fullyQualifiedName'], type='CustomTask')

    def task_for(self, spec):
        customer = self.customer()
        matches = [t for t in self.task_list() if (t.get('about') or {}).get('id') == customer['id']
                   and t.get('payload', {}).get('value') == spec['value']]
        self.require(len(matches) <= 1, 'duplicate demo task: ' + spec['value'])
        if matches:
            task = matches[0]
            form = self.named('taskFormSchemas', 'ttrSuggestChange')
            self.require(form and task.get('taskFormSchemaId') == form['id'],
                         'matching task uses another form: ' + spec['value'])
            return task
        return None

    def task_ready(self, task, spec):
        if not task:
            return False
        messages = [c['message'] for c in task.get('comments', [])]
        expected = [c[1] for c in spec['comments']]
        return (task.get('workflowStageId') == spec['stage'] and task.get('status') == spec['status']
                and messages == expected and
                (spec['stage'] not in ('review', 'publication') or
                 any(a.get('id') == self.reference('users',
                     'petr.novak' if spec['stage'] == 'review' else 'tatrman-maintainer', 'user')['id']
                     for a in task.get('assignees', []))))

    def await_task(self, task, stage=None):
        for attempt in range(20):
            current = self.catalog.get('tasks/' + task['id'] + '?fields=about,payload,comments,assignees,availableTransitions')
            if current.get('workflowStageId') and (not stage or current['workflowStageId'] == stage):
                return current
            time.sleep(.25)
        raise self.error('task workflow did not reach expected stage')

    def walk_task(self, spec):
        task = self.task_for(spec)
        if task is None:
            customer = self.customer()
            body = {'displayName': 'Synonym for Customer: ' + spec['value'],
                    'category': 'Custom', 'type': 'CustomTask',
                    'about': '<#E::glossaryTerm::' + customer['fullyQualifiedName'] + '>',
                    'assignees': ['petr.novak'],
                    'payload': {'what': 'A synonym', 'value': spec['value'], 'language': 'Czech', 'why': spec['why']}}
            # The form is resolved by the server's type/category binding, then checked below.
            task = self.write_as('jana.dvorakova', 'POST', 'tasks', body)
        task = self.await_task(task)
        form = self.named('taskFormSchemas', 'ttrSuggestChange')
        self.require(task.get('taskFormSchemaId') == form['id'], 'server selected another task form')
        self.require(task['workflowStageId'] in ('review', 'publication', 'published'),
                     'demo task is at an unexpected workflow stage')
        if task['workflowStageId'] == 'review' and spec['stage'] != 'review':
            task = self.write_as('petr.novak', 'POST', 'tasks/' + task['id'] + '/resolve',
                      {'transitionId': 'approve', 'comment': spec['comments'][0][1],
                       'payload': {'assignees': [self.reference('users', 'tatrman-maintainer', 'user')]}})
            task = self.await_task(task, 'publication')
        if spec['stage'] == 'publication' and not any(
                a['id'] == self.reference('users', 'tatrman-maintainer', 'user')['id']
                for a in task.get('assignees', [])):
            self.catalog.write('PATCH', 'tasks/' + task['id'],
                [{'op': 'add', 'path': '/assignees',
                  'value': [self.reference('users', 'tatrman-maintainer', 'user')]}])
            task = self.await_task(task, 'publication')
        if spec['stage'] != 'review':
            for author, message in spec['comments']:
                # The terminal publication comment is supplied to resolve, exactly once.
                if spec['stage'] == 'published' and message == spec['comments'][-1][1]:
                    continue
                if message not in [c['message'] for c in task.get('comments', [])]:
                    task = self.write_as(author, 'POST', 'tasks/' + task['id'] + '/comments', {'message': message})
            if spec['stage'] == 'published' and task['workflowStageId'] == 'publication':
                task = self.write_as('tatrman-maintainer', 'POST', 'tasks/' + task['id'] + '/resolve',
                        {'transitionId': 'publish', 'comment': spec['comments'][-1][1]})
        task = self.await_task(task, spec['stage'])
        # OM 2.0.6 may omit the comment on a terminal resolution. Read back before
        # adding it, so both that behavior and a server that stores it are idempotent.
        for author, message in spec['comments']:
            if message not in [c['message'] for c in task.get('comments', [])]:
                task = self.write_as(author, 'POST', 'tasks/' + task['id'] + '/comments', {'message': message})
        self.require(self.task_ready(task, spec), 'demo task did not reach frozen state')

    def tasks(self):
        for spec in self.content['tasks']:
            current = self.task_for(spec)
            ready = self.task_ready(current, spec)
            yield self.operation('task ' + spec['value'], '', '', None,
                                 True if ready else (False if current else None), True,
                                 lambda spec=spec: self.walk_task(spec))

    def approval_tasks(self):
        customer = self.customer()
        return [task for task in self.listing('tasks',
                    'about,payload,assignees,availableTransitions',
                    aboutEntity=customer['fullyQualifiedName'], category='Approval')
                if (task.get('about') or {}).get('id') == customer['id']
                and task.get('type') in ('RequestApproval', 'GlossaryApproval')
                and task.get('status') in ('Open', 'InProgress', 'Pending')
                and any(a.get('id') == self.reference('users', 'petr.novak', 'user')['id']
                        for a in task.get('assignees', []))
                and (task.get('type') == 'GlossaryApproval' or
                     'In Review' in task.get('payload', {}).get('proposedChanges', {})
                     .get('entityStatus', {}).get('added', []))]

    def reviewer_skip(self, customer):
        if self.reviewer_skip_reason:
            return self.reviewer_skip_reason
        # No local state file: an open status approval left behind on an Approved,
        # reviewer-less Customer is the catalog evidence for the removal fallback.
        if not customer.get('reviewers') and customer.get('entityStatus') == 'Approved' and self.approval_tasks():
            return 'server approval remains open after reviewer removal'
        return None

    def reviewers(self):
        customer = self.customer()
        reason = self.reviewer_skip(customer)
        if reason:
            self.output('skip Customer reviewer: ' + reason)
            desired = {'reviewers': []}
        else:
            desired = {'reviewers': [self.reference('users', 'petr.novak', 'user')]}
        yield self.patch_fields('Customer reviewer Petr', 'glossaryTerms', customer, desired)

    def wait_customer_approved(self):
        for _ in range(40):
            if self.customer().get('entityStatus') == 'Approved':
                return
            time.sleep(.25)
        raise self.error('Customer did not end Approved after its approval step')

    def approve_customer(self):
        tasks = self.approval_tasks()
        self.require(len(tasks) == 1, 'expected one open Customer status approval')
        task = tasks[0]
        self.require(any(t.get('id') == 'approve' for t in task.get('availableTransitions', [])),
                     'Customer approval has no approve transition')
        clients, answers = [], []
        for client in (self.actor('petr.novak'), self.catalog):
            if any(client is seen for seen in clients):
                continue
            clients.append(client)
            try:
                client.write('POST', 'tasks/' + task['id'] + '/resolve',
                             {'transitionId': 'approve', 'comment': 'Approve the frozen Customer demo content.'})
            except self.error as error:
                if error.status not in (400, 401, 403, 409):
                    raise
                answers.append('HTTP ' + str(error.status))
                continue
            self.wait_customer_approved()
            return
        # Contracted fallback: remove only the reviewer; never patch entityStatus.
        self.catalog.write('PATCH', 'glossaryTerms/' + self.customer()['id'],
                           [{'op': 'add', 'path': '/reviewers', 'value': []}])
        self.reviewer_skip_reason = 'approval refused: ' + ', '.join(answers)
        self.output('skip Customer reviewer: ' + self.reviewer_skip_reason)
        self.wait_customer_approved()

    def customer_approval(self):
        current = self.customer().get('entityStatus')
        self.require(current in ('Approved', 'In Review'),
                     'Customer has an unexpected status before approval')
        yield self.operation('Customer status approval', '', '', None, current, 'Approved', self.approve_customer)

    def announcement_list(self):
        return self.listing('announcements', entityLink='<#E::glossaryTerm::' + self.customer()['fullyQualifiedName'] + '>')

    def announcement(self):
        desired = dict(self.content['announcement'])
        now = int(time.time() * 1000)
        desired.update(entityLink='<#E::glossaryTerm::' + self.customer()['fullyQualifiedName'] + '>',
                       startTime=now, endTime=now + 90 * 86400 * 1000)
        current = self.named('announcements', desired['name'])
        if current:
            desired['startTime'] = current['startTime']
            op = self.patch_fields('announcement Model published (renew end time)', 'announcements', current, desired)
        else:
            op = self.operation('announcement Model published', 'POST', 'announcements', desired, None, desired)
        yield op

    def chat_value(self):
        task = self.task_for(next(t for t in self.content['tasks'] if t['value'] == 'odběratel'))
        if not task:
            return None
        # OM 2.0.6 has no standalone custom-task route. Changes/tasks opens
        # its newest open task; the frozen odběratel suggestion is raised last.
        number = task.get('taskId') or task['name']
        url = (self.catalog.base.removesuffix('/api/v1/') + '/glossary/' +
               quote(self.customer()['fullyQualifiedName'], safe='') + '/activity_feed/tasks')
        template = (self.pack / 'change-1-golem-chat.html').read_text()
        return template.replace('{{TASK_URL}}', html.escape(url, quote=True)).replace('{{TASK_NO}}', html.escape(number))

    def chat_page(self):
        desired = self.chat_value()
        path = self.chat_path()
        def build():
            self.require(desired is not None, 'chat task is missing')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(desired)
        yield self.operation('offline chat page', '', '', None, path.read_text() if path.exists() else None,
                             desired or 'pending odběratel task', build)

    def chat_path(self):
        return self.pack / 'build' / self.target / 'change-1-golem-chat.html'

    def content_checks(self):
        def workflow():
            actual = self.named('governance/workflowDefinitions', 'ttrSuggestionWorkflow')
            return subset(actual, self.workflow_value())

        def form():
            return subset(self.named('taskFormSchemas', 'ttrSuggestChange'),
                          json.loads((self.pack / 'task-form.json').read_text()))

        def accounts():
            ops = list(self.accounts_and_team()) + list(self.domains())
            return all(op.action == 'unchanged' for op in ops)

        def customer():
            item = self.customer()
            spec = self.content['terms'][0]
            wanted = self.fields(item, spec, self.objects())
            reason = self.reviewer_skip(item)
            wanted['reviewers'] = [] if reason else [self.reference('users', 'petr.novak', 'user')]
            if reason:
                self.output('skip Customer reviewer: ' + reason)
            return subset(item, wanted) and all(t.get('entityStatus') == 'Approved'
                                               for t in self.objects().values())

        def relations():
            return all(op.action == 'unchanged' for op in self.relations())

        def phase():
            terms = self.objects()
            item = terms.get('cn.phase.DebtorCustomer')
            if item is None:
                return True
            return subset(item.get('parent'), ref(terms['cn.role.Customer'], 'glossaryTerm'))

        def assets():
            return all(op.action == 'unchanged' for op in self.content_except_reviewers())

        def tasks():
            return all(self.task_ready(self.task_for(spec), spec) for spec in self.content['tasks'])

        def announcement():
            item = self.named('announcements', self.content['announcement']['name'])
            return bool(item and subset(item, self.content['announcement'])
                        and item.get('startTime', float('inf')) <= time.time() * 1000
                        < item.get('endTime', 0)
                        and any(a['id'] == item['id'] for a in self.announcement_list()))

        def chat():
            path = self.chat_path()
            wanted = self.chat_value()
            open_tasks = self.listing('tasks', 'about,payload',
                aboutEntity=self.customer()['fullyQualifiedName'], statusGroup='open')
            task = self.task_for(self.content['tasks'][2])
            return (wanted is not None and path.is_file() and path.read_text() == wanted
                    and bool(open_tasks) and sorted(open_tasks,
                        key=lambda t: t.get('createdAt', 0), reverse=True)[0]['id'] == task['id'])

        return [('workflow: two stages and four transitions', workflow),
                ('form bound to workflow', form), ('accounts, team and four domains', accounts),
                ('Customer fields and demo terms Approved', customer),
                ('four typed relations without plain duplicates', relations),
                ('phase under Customer', phase), ('table and metric', assets),
                ('three frozen tasks and comments', tasks), ('active Customer announcement', announcement),
                ('offline chat page names odběratel task', chat)]

    def content_removals(self):
        # Delete only the three task identities selected by term + New value + form.
        for spec in self.content['tasks']:
            task = self.task_for(spec)
            if task:
                yield ('delete task ' + spec['value'], 'DELETE', 'tasks/' + task['id'] + '?hardDelete=true', None)
        announcement = self.named('announcements', self.content['announcement']['name'])
        if announcement:
            yield ('delete announcement Model published', 'DELETE',
                   'announcements/' + announcement['id'] + '?hardDelete=true', None)
        for resource, name in [('taskFormSchemas', 'ttrSuggestChange'),
                               ('governance/workflowDefinitions', 'ttrSuggestionWorkflow'),
                               ('teams', 'sales-team')] + [('domains', d['name']) for d in self.content['domains']] + [
                               ('users', a['name']) for a in self.content['accounts']]:
            current = self.named(resource, name)
            if current:
                yield ('delete ' + name, 'DELETE', resource + '/' + current['id'] + '?hardDelete=true', None)

    def restore_command(self):
        # The operator chooses when to restore. Never execute or change the projection here.
        self.output('restore edited terms: kubectl --context ' + self.target +
                    ' -n openmetadata create job "om-project-layout-restore-$(date -u +%s)"' +
                    ' --from=cronjob/om-project-tatrman --dry-run=client -o json' +
                    ' | python3 -c \'import json,sys; d=json.load(sys.stdin); a=d["spec"]["template"]["spec"]["containers"][0]["args"]; a[a.index("--state-file")+1]="/state/"+d["metadata"]["name"]+".json"; json.dump(d,sys.stdout)\'' +
                    ' | kubectl --context ' + self.target + ' -n openmetadata create -f -')
