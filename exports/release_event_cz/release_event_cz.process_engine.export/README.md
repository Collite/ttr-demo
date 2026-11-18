# release_event_cz — the estate's process engine (Camunda 7 dialect)

`release_order.c7.bpmn` and the DMN files deploy to the process engine with `ttrp emit --deployment release_event_cz --deploy`. This is an L1 orchestration
skeleton; SQL and governed writes stay on the Server.
The Modeler opening follows the repair re-review and is Bora's manual acceptance; XSD/structure checks
do not certify a live engine. The file declares Camunda Platform 7.24.0 or Camunda Cloud 8.6.0 as its
execution platform. C8 requires at least 8.6: [converging inclusive gateways](https://unsupported.docs.camunda.io/8.6/docs/components/modeler/bpmn/inclusive-gateways/),
[zeebe:userTask](https://unsupported.docs.camunda.io/8.6/docs/components/modeler/bpmn/user-tasks/) and
[FEEL timezone conversion](https://unsupported.docs.camunda.io/8.5/docs/components/modeler/feel/builtin-functions/feel-built-in-functions-conversion/)
are available there (timezone conversion is already documented in 8.5).

Every HTTP step is Camunda Connect's http-connector calling the executor's egress, http://process-engine-egress.process-engine.svc/automation.
The egress injects the process-engine client's bearer; this BPMN carries no token and no connector secret.
The engine needs Spin JSON and Groovy for Retry-After normalization. Start this one-program BPMN through
the engine (REST, Tasklist or a message); configure scheduling and composition in the engine modeller.
Start with a nonblank business key: every Open records engine.instanceId, engine.businessKey and
engine.deploymentId (the running process definition's deployment id, read through the repository service).
The engine templates also retain ttrInput.at in keyed ports; batch ports remain {none: true}.
Approval completion captures task.id/assignee; its answer Open additionally carries engine.taskId and
engine.answeredBy, with idempotencyKey = ttrAnchor + ':answer:' + ttrTaskId and the approved row's key.
An approval-required action whose rows the Server holds (native sink transition, writer or obligation) becomes
this user task; the engine never performs it directly. The Server holds those rows at the run's close, so the
engine asks after the close: closed ends the evaluation, waiting asks each row whose key has the action
selected, anything else refuses. The answer Open is the row's one call. It runs within task completion (no
asyncBefore); a transient failure, or a 202 for the same key still in flight, rolls back completion and the
user completes again. Its port.key is the row's key as a column-named object. The Server decides the approved
key and closes the answer run at that Open. The row continues only when the response says status closed and
answer.decision commit; anything else (waiting, 409, another 4xx) reaches run refused and is never counted as
decided. A non-2xx refusal keeps the Server's status and body in ttrRefusedReason; a 2xx that does not commit
leaves it null, and the answer's status is the row-local ttrAnswerStatus in the history. The row reads no
route again, so the approval is never asked twice. ttrAnswerRunId, ttrAnswerStatus and ttrAnswerDecision are
row-local. Only the engine client may assert an answer.
Deploy: `ttrp emit --deployment release_event_cz --deploy` posts this BPMN and the DMN files as one engine
deployment named release_event_cz, with duplicate filtering and deployment-source ttrp:<bundle fingerprint>.
The bearer comes from TTR_BEARER (or --token-env); it is never written to output or export files.
`--deploy --check` reads the newest deployment of the name and answers absent, current, stale or foreign;
`--deploy` creates for absent or stale, does nothing for current and refuses foreign unless --force.
`--engine-url` overrides the executor's url, e.g. for a port-forward.
startable_by: role.sales_manager (Keycloak group hartland-sales-managers). The process carries camunda:candidateStarterGroups="hartland-sales-managers"; the engine's provisioner grants START_INSTANCE to these groups (D-161).

Start with ttrInput={key:..., at:"offset ISO instant"}, keys, or event. Event payload is nested under event;
at is separate. On C7, ttrInput is a Java Map, including nested maps/lists for events or keys; a REST
Object variable must deserialize to a Map, rather than a Spin Json variable. This input contract is
expression-tested; no REST start on a live C7 engine is certified here. On-event deduplication requires a
stable at; absent at is a new run. A batch program uses the engine execution id
(C8 saves ttrExecutionId, generating one if absent). The Open body and its clock are saved once;
retries reuse that body. Start each batch once: retrying an external start on C7 or n8n
creates another engine instance and caller key; deduplication across those instances is not provided.

201 alone drives evaluation. 200 replay completes the step; 202 polls, closed/waiting completes,
abandoned/failed allows one re-open. A second non-201 recovery refuses. 409 raises TTR_STALE and reaches
export outdated. The HTTP response policy for every call, including perform/outcome/close, is:

| Response | Result |
| --- | --- |
| 2xx | Continue with the response body |
| 409 | TTR_STALE boundary → export outdated |
| Other 4xx except 408/429 | TTR_REFUSED boundary → run refused; inspect evidence |
| 408/429, 5xx, transport errors | Connector retries, then incident |

C8 uses the error response's numeric or HTTP-date Retry-After when retrying HTTP errors, defaulting to
15 seconds, with a 1 second minimum and a cap of the program budget + 2 min.
C7 Connect failed jobs use R3/PT15S: its output exception cannot commit a dynamic retry delay.
Successful handle/evaluation polls in both dialects honour Retry-After and are bounded by budget + 2 min.
Failed/abandoned evaluation refuses immediately; running/open or null-verdict evidence keeps polling.
Run-level route forks and joins are inclusive for every switchMode: exclusivity holds per row and is
enforced by the Server. Read every route page using offset and the Server's default page size; do not
override its displayRows limit. Empty/short pages before rowCount or inconsistent counts refuse before
any row action. Missing obligations/actions refuse, never count as empty evidence.
Compose obligation watching and digest policies in the engine; recipe process/delivery/schedule
constructs were removed in grammar 0.22.

Send tasks are customer template nodes using TTR_CONN_MAIL (C7 external task / C8 job type). Their worker
belongs to Platform and is not bundled. Resolve TTR_MAIL_RECIPIENTS for role recipients; per-row addresses
come from the declared route column. The worker must refuse a missing/empty recipient and report success
only after delivery; only then does BPMN report delivered to the Server. Both deployment and status must
explicitly be wet, with the action selected for this key. Required approval is a Camunda user task carrying
ttrAction/ttrKey; connect its completion to the exchange's task/approval integration before deployment.

Stale when model, recipe text/values/labels, program, deployment, world, toolchain or target version
differs from the served bundle: re-export. The manifest inventories all emitted artifacts. The structure
driver checks routes, tasks, named calls, template bindings and DMN associations offline; it does not
execute connectors or compare verdicts.

Authoring artifacts:
- `dmn/er.query.placed_order_q_decision.dmn`
- `dmn/er.query.report_returns_review_q_decision.dmn`
- `dmn/er.query.returns_monthly_by_category_decision.dmn`
- `dmn/er.query.returns_review_decision.dmn`
- `dmn/er.query.returns_union_decision.dmn`
- `dmn/er.query.revenue_per_customer_decision.dmn`
- `dmn/er.query.sales_union_decision.dmn`
- `dmn/er.query.stockouts_monthly_dc_decision.dmn`
- `dmn/query.query.buyer_age_profile_decision.dmn`
- `dmn/query.query.category_revenue_decision.dmn`
- `dmn/query.query.channel_revenue_monthly_decision.dmn`
- `dmn/query.query.channel_revenue_monthly_yoy_decision.dmn`
- `dmn/query.query.channel_revenue_yoy_decision.dmn`
- `dmn/query.query.customer_running_total_decision.dmn`
- `dmn/query.query.inventory_on_hand_series_decision.dmn`
- `dmn/query.query.marketplace_revenue_by_warehouse_decision.dmn`
- `dmn/query.query.promo_share_decision.dmn`
- `dmn/query.query.returns_by_reason_decision.dmn`
- `dmn/query.query.returns_rate_by_channel_decision.dmn`
- `dmn/query.query.revenue_by_customer_state_decision.dmn`
- `dmn/query.query.store_sales_by_month_decision.dmn`
- `dmn/query.query.top_items_by_revenue_decision.dmn`
- `dmn/query.query.warehouse_stockout_week_count_decision.dmn`
- `dmn/query.query.warehouse_stockout_weeks_decision.dmn`
- `templates/c7/decide_catch_up.json`
- `templates/c7/decide_catch_up_cz.json`
- `templates/c7/decide_on_request.json`
- `templates/c7/decide_on_request_cz.json`
- `templates/c7/er.query.placed_order_q.json`
- `templates/c7/er.query.report_returns_review_q.json`
- `templates/c7/er.query.returns_monthly_by_category.json`
- `templates/c7/er.query.returns_review.json`
- `templates/c7/er.query.returns_union.json`
- `templates/c7/er.query.revenue_per_customer.json`
- `templates/c7/er.query.sales_union.json`
- `templates/c7/er.query.stockouts_monthly_dc.json`
- `templates/c7/inbound_daily.json`
- `templates/c7/inbound_on_receipt.json`
- `templates/c7/morning_release.json`
- `templates/c7/morning_release_cz.json`
- `templates/c7/query.query.buyer_age_profile.json`
- `templates/c7/query.query.category_revenue.json`
- `templates/c7/query.query.channel_revenue_monthly.json`
- `templates/c7/query.query.channel_revenue_monthly_yoy.json`
- `templates/c7/query.query.channel_revenue_yoy.json`
- `templates/c7/query.query.customer_running_total.json`
- `templates/c7/query.query.inventory_on_hand_series.json`
- `templates/c7/query.query.marketplace_revenue_by_warehouse.json`
- `templates/c7/query.query.promo_share.json`
- `templates/c7/query.query.returns_by_reason.json`
- `templates/c7/query.query.returns_rate_by_channel.json`
- `templates/c7/query.query.revenue_by_customer_state.json`
- `templates/c7/query.query.store_sales_by_month.json`
- `templates/c7/query.query.top_items_by_revenue.json`
- `templates/c7/query.query.warehouse_stockout_week_count.json`
- `templates/c7/query.query.warehouse_stockout_weeks.json`
- `templates/c7/release_on_placement.json`
- `templates/c7/release_on_placement_cz.json`
- `templates/c7/settle_daily.json`
- `templates/c7/settle_on_document.json`

Install templates/c7 in the Modeler project's .camunda/element-templates
directory, then restart Modeler. Choose the world program or query in the dropdown.
Inputs map by parameter name; query outputs expose the typed row columns and row_count
as task variables. Configure the governed program/query HTTP task and its variables
derivation in Modeler.

DMN files are empty DMN 1.3 FIRST tables. Author business rules and the outcome before
execution; the export invents no rules. Inline SQL and Golem questions have no generated
DMN skeleton.

The host reads deployed programs from this world, recipe parameter declarations from
.ttrp sources, and query columns from the metadata query compiler. Keep other programs'
sources in the project even when --bundle supplies the selected program's verified bundle.
Those other sources are unverified: they are not checked against served bundles or approvals,
and the model fingerprint covers .ttrm files, not those .ttrp files. Review their defaults
(recipe values, without program overrides) before use and re-export after source changes.

DMN types use DMN 1.3/FEEL names. C7 may ignore number/time/dateTime typeRef values;
map them to engine-supported types when authoring C7 rules. The query compiler surface
represents model date/time as dateTime; an explicit SQL CAST preserves date/time.
Parameter defaults are authoring suggestions. Review date/time and expression-like text
defaults in Modeler before use; program overrides are not applied.

Templates carry their implementation: Camunda Connect's http-connector to the executor's egress
(it injects the bearer). A world program step opens a run of the World deployment property
(ttr_deployment) with the port from ttrInput; a world query step posts {query, parameters} to
the egress's /query. The response is the ttr_response variable; non-2xx raises an incident.
version is 1 (default 1). Raise --template-version whenever a regenerated
template metadata.fingerprint differs: Modeler prefers the highest version of an id.
Regenerate into a new export folder and reinstall its templates. Preserve authored DMN
rules separately; regeneration creates fresh skeletons. The manifest inventories every
exported artifact.

Omitted world queries:
- TTRP-EXPORT-QUERY: query.query.customer_channel_overlap: Aggregate function 'bool_or' is not in the v1 wire format
