# The layout demo — show sheet

Show the frozen content on **bp-dsk**, signed in as **Petr Novák** (`petr.novak`,
Model steward). Jana Dvořáková (`jana.dvorakova`, Model reader) can walk the same
addresses; her Home omits My Tasks. Nothing is raised, approved or published during
this showing. The hartland column stays empty until Bora calls P2.

From the repo root, set the admin token file and the supplied `OM_DEMO_PASSWORD`,
then run `just om-layout apply bp-dsk` and `just om-layout verify bp-dsk`. The
projection's demo objects must already exist. Open the local chat in a separate
browser tab. Sign in as Petr in another browser window and follow this order.

| # | Screen | bp-dsk address | Signed in | Point at | hartland (P2) |
|---|---|---|---|---|---|
| 1 | Home · model steward | [Home](https://openmetadata.192-168-1-38.nip.io/my-data) | Petr | Welcome, Petr; My Tasks includes #8; four Domains; Curated Assets contains the Sales glossary terms; Model published announcement. | |
| 2 | Concept · Customer | [Customer Overview](https://openmetadata.192-168-1-38.nip.io/glossary/demo%20Concepts.%22cn.role.Customer%22/overview) | Petr | Approved; description, six synonyms, yellow role; four typed relations; Petr reviewer, Sales team and Sales; six renamed tabs. | |
| 3 | Entity · customer | [Entity Overview](https://openmetadata.192-168-1-38.nip.io/glossary/demo%20Entities.customer/overview) | Petr | Navy entity; grounded-by link back to the concept; custom properties, owner and domain. Its attributes are under Narrower terms. | |
| 4 | Table · customer (CZ) | [Customer Columns](https://openmetadata.192-168-1-38.nip.io/table/hartland-pg.hartland_cz.public.customer/schema) | Petr | Columns and their bound glossary terms; Description left, Glossary Terms and Custom Properties right; Sales and Sales team in the header. Only four tabs. | |
| 5 | Measure · revenue | [Revenue Overview](https://openmetadata.192-168-1-38.nip.io/metric/revenue/overview) | Petr | Description; Custom Properties and Sale on the right; Sales in the header. Scroll down the left for Related Metrics: quantity, orderCount, lineCount, returnAmount. | |
| 6 | Model map | [Customer Model map](https://openmetadata.192-168-1-38.nip.io/glossary/demo%20Concepts.%22cn.role.Customer%22/relations_graph) | Petr | Four typed edges, including the grounding across demo Concepts and demo Entities. | |
| 7 | Change 1 · the Golem's chat | [Local chat](build/change-1-golem-chat.html) — open `openmetadata/layout/build/change-1-golem-chat.html` in the browser | Petr in the catalog tab; local file has no account | The frozen conversation confirms the meaning of odběratel; Open task links to screen 8. This page works offline. | |
| 8 | Change 2 · business review | [Customer Changes / Tasks](https://openmetadata.192-168-1-38.nip.io/glossary/demo%20Concepts.%22cn.role.Customer%22/activity_feed/tasks) | Petr | #8 (TASK-00008), odběratel, raised by Jana, assigned to Petr; Approve is the available action. Do not press it. | |
| 9 | Change 3 · awaiting publication | [Customer Changes / Tasks](https://openmetadata.192-168-1-38.nip.io/glossary/demo%20Concepts.%22cn.role.Customer%22/activity_feed/tasks), then select **#7** in the open list | Petr | kupující; Published with the model action; Petr's agreement, then the maintainer's pull-request reference and model-check comments. Do not transition it. | |
| 10 | Change 4 · published | [Customer Overview](https://openmetadata.192-168-1-38.nip.io/glossary/demo%20Concepts.%22cn.role.Customer%22/overview) | Petr | klient is among the synonyms. In Changes / Tasks, choose Closed and #6 for the completed suggestion and its three comments; Home carries the announcement. | |

Differences accepted by the layout contract: Metric Dimensions and Metric Measures
stay where the editor keeps them (⚑AR-21); Related Metrics is below them on the left.
Table/Metric do not offer separate Owners/Domain widgets, so the stock header shows
those fields. Home's picker has no separate Recently Viewed widget; it is omitted
under LD-C7, while the stock welcome panel retains recent-item shortcuts. Widget and
menu labels remain OpenMetadata's. Custom tasks show `message.custom-task-message`;
the values, actions and comments identify the suggestion and its frozen stage.

OpenMetadata 2.0.6 has no standalone route for these custom tasks. The Changes/tasks
address opens the newest open suggestion (#8); screen 9 needs the #7 selection.
The pack's check 15 verifies that the chat still lands on #8. The maintainer's
publication resolve used the documented admin fallback; comments remain named.

Bora's P1·A acceptance walk follows the S1.3 merge: open each address, check the
account and point-at column, and send any difference beyond these accepted limits
to the planner. A showing on hartland remains gated on Bora's call.
