# The layout demo — show sheet

Show the frozen content on **bp-dsk** or **hartland**, signed in as **Petr Novák** (`petr.novak`,
Model steward). Jana Dvořáková (`jana.dvorakova`, Model reader) can walk the same
addresses; her Home omits My Tasks. Nothing is raised, approved or published during
this showing. Both catalogs use `demo Concepts` and `demo Entities`.

From the repo root, set the admin token file and the supplied `OM_DEMO_PASSWORD`,
then run `just om-layout apply <target>` and `just om-layout verify <target>`
(`bp-dsk` or `hartland`). Use that target’s own token and CA bundle. The
projection's demo objects must already exist. Open the local chat in a separate
browser tab. Sign in as Petr in another browser window and follow this order.

| # | Screen | bp-dsk address | Signed in | Point at | hartland (P2) |
|---|---|---|---|---|---|
| 1 | Home · model steward | [Home](https://openmetadata.192-168-1-38.nip.io/my-data) | Petr | Welcome, Petr; My Tasks includes the business-review suggestion; four Domains; Curated Assets contains the Sales glossary terms; Model published announcement. | [Home](https://openmetadata.hartland.collite.cz/my-data) |
| 2 | Concept · Customer | [Customer Overview](https://openmetadata.192-168-1-38.nip.io/glossary/demo%20Concepts.%22cn.role.Customer%22/overview) | Petr | Approved; description, six synonyms, yellow role; four typed relations; Petr reviewer, Sales team and Sales; six renamed tabs. | [Customer Overview](https://openmetadata.hartland.collite.cz/glossary/demo%20Concepts.%22cn.role.Customer%22/overview) |
| 3 | Entity · customer | [Entity Overview](https://openmetadata.192-168-1-38.nip.io/glossary/demo%20Entities.customer/overview) | Petr | Navy entity; grounded-by link back to the concept; custom properties, owner and domain. Its attributes are under Narrower terms. | [Entity Overview](https://openmetadata.hartland.collite.cz/glossary/demo%20Entities.customer/overview) |
| 4 | Table · customer (CZ) | [Customer Columns](https://openmetadata.192-168-1-38.nip.io/table/hartland-pg.hartland_cz.public.customer/schema) | Petr | Columns and their bound glossary terms; Description left, Glossary Terms and Custom Properties right; Sales and Sales team in the header. Only four tabs. | [Customer Columns](https://openmetadata.hartland.collite.cz/table/hartland-pg.hartland_cz.public.customer/schema) |
| 5 | Measure · revenue | [Revenue Overview](https://openmetadata.192-168-1-38.nip.io/metric/revenue/overview) | Petr | Description; Custom Properties and Sale on the right; Sales in the header. Scroll down the left for Related Metrics: quantity, orderCount, lineCount, returnAmount. | [Revenue Overview](https://openmetadata.hartland.collite.cz/metric/revenue/overview) |
| 6 | Model map | [Customer Model map](https://openmetadata.192-168-1-38.nip.io/glossary/demo%20Concepts.%22cn.role.Customer%22/relations_graph) | Petr | Four typed edges, including the grounding across demo Concepts and demo Entities. | [Customer Model map](https://openmetadata.hartland.collite.cz/glossary/demo%20Concepts.%22cn.role.Customer%22/relations_graph) |
| 7 | Change 1 · the Golem's chat | [Local chat](build/bp-dsk/change-1-golem-chat.html) — open `openmetadata/layout/build/bp-dsk/change-1-golem-chat.html` in the browser | Petr in the catalog tab; local file has no account | The frozen conversation confirms the meaning of odběratel; Open task links to screen 8. This page works offline. | [Local chat](build/hartland/change-1-golem-chat.html) — open `openmetadata/layout/build/hartland/change-1-golem-chat.html` |
| 8 | Change 2 · business review | [Customer Changes / Tasks](https://openmetadata.192-168-1-38.nip.io/glossary/demo%20Concepts.%22cn.role.Customer%22/activity_feed/tasks) | Petr | #8 on bp-dsk / #3 on hartland, odběratel, raised by Jana, assigned to Petr; Approve is the available action. Do not press it. | [Customer Changes / Tasks](https://openmetadata.hartland.collite.cz/glossary/demo%20Concepts.%22cn.role.Customer%22/activity_feed/tasks) — **#3 (TASK-00003)** |
| 9 | Change 3 · awaiting publication | [Customer Changes / Tasks](https://openmetadata.192-168-1-38.nip.io/glossary/demo%20Concepts.%22cn.role.Customer%22/activity_feed/tasks), then select **#7** in the open list | Petr | kupující (#7 on bp-dsk / #2 on hartland); Published with the model action; Petr's agreement, then the maintainer's pull-request reference and model-check comments. Do not transition it. | [Customer Changes / Tasks](https://openmetadata.hartland.collite.cz/glossary/demo%20Concepts.%22cn.role.Customer%22/activity_feed/tasks); select **#2 (TASK-00002)** in the open list |
| 10 | Change 4 · published | [Customer Overview](https://openmetadata.192-168-1-38.nip.io/glossary/demo%20Concepts.%22cn.role.Customer%22/overview) | Petr | klient is among the synonyms. In Changes / Tasks, choose Closed and #6 on bp-dsk / #1 on hartland for the completed suggestion and its three comments; Home carries the announcement. | [Customer Overview](https://openmetadata.hartland.collite.cz/glossary/demo%20Concepts.%22cn.role.Customer%22/overview); Changes / Tasks → Closed → **#1 (TASK-00001)** |

Differences accepted by the layout contract: Metric Dimensions and Metric Measures
stay where the editor keeps them (⚑AR-21); Related Metrics is below them on the left.
Table/Metric do not offer separate Owners/Domain widgets, so the stock header shows
those fields. Home's picker has no separate Recently Viewed widget; it is omitted
under LD-C7, while the stock welcome panel retains recent-item shortcuts. Widget and
menu labels remain OpenMetadata's. Custom tasks show `message.custom-task-message`;
the values, actions and comments identify the suggestion and its frozen stage.

OpenMetadata 2.0.6 has no standalone route for these custom tasks. The Changes/tasks
address opens the newest open suggestion (#8 on bp-dsk; #3 on hartland); screen 9
needs #7 on bp-dsk or #2 on hartland. Check 15 verifies the chat lands on odběratel. The maintainer's
publication resolve used the documented admin fallback; comments remain named.

On the morning of a showing, set that catalog’s admin token and run
`just om-layout verify <target>`. Expect **16 of 16**. If it is not 16/16, run
`just om-layout apply <target>`, then verify again before opening the sheet:
the nightly projection may have rewritten a demo term. Leave the projection alone.
Open the chat from `build/<target>/` so its task link reaches the same catalog.

Hartland’s projection was repaired before this pack was applied (XM S3.4, AR D-83).
All seven demo objects and all four Customer relations are present; no missing-object
skip is used on hartland. The maintainer’s publication resolve used the documented
admin fallback. The three people-facing task numbers differ between catalogs as
shown above. Bora can walk the ten screens in either column after the PR merge.
