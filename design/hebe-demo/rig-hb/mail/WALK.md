# S3.6 human webmail walk — bp-dsk

The agent prepares the fixtures and reads the results; a person performs these
mail actions as Markéta. Keep the actual result sheet in the stage PR description,
with identifiers and observations, never credentials or a proof folder in project/.

Webmail: https://webmail.192-168-1-38.nip.io/ (Keycloak SSO as `marketa`).
Console: https://hebe.192-168-1-38.nip.io/ (the same persona).
Tasklist/Cockpit: https://process.192-168-1-38.nip.io/webapp/ (claim as `bora` only
where specified). Use separate browser sessions for the two people.

Use the existing **Kontrola uvolnění objednávky — certifikace Hebe** process,
key `hebe_p2_cert`, rather than the H-2 return-request process. Send a new start
request in the console: `spusť kontrolu uvolnění pro 4711`. If process selection
appears, choose the certification definition by its displayed number, then send
a separate `ano` to its named confirmation. The agent records the instance/task
and corresponding receipts. Never send a second start while awaiting the first.

| Task | Person's action | Observation to record in the PR |
|---|---|---|
| T4 / Beat 10 | Start the first certification instance through the console. Open its card mail in webmail. | Subject/ref, instance/task IDs, ten detail rows plus `+ 2 more`, task link, actual-Reply instructions and positive/negative commands. |
| T4 | Use webmail's actual **Reply** on that card. Type `schválit`, then send. | Reply and outcome remain in the card thread. Agent verifies COMPLETED, answered by `marketa`, one `engine.answer` receipt with `channel=email`; record receipt ID. |
| T5 | Start a second instance. With its card open in webmail, answer `schválit 4711` in the console. | The outcome appears in that same mail thread. Record instance/task IDs, thread subject and console answer receipt. |
| T5 | Start a third instance. Claim its task in Tasklist as `bora`. | Its mail thread gains `vyřízeno jinde`. Record task/instance IDs and subject. Finish that controlled task as Bora in Tasklist so no active fixture remains. |
| T5 | In an existing card thread, use actual **Reply** and send a free-text sentence rather than a command. | Not-understood guidance stays in that thread. Agent checks the matching window contains no model call for this reply. Record subject, reply time and receipt/event references. |
| T6 / Beat 11 | Open Jana's complaint `[HE-S36 <run>] Reklamace objednávky 4711`. Use **Forward**, addressed to `hebe-marketa@hartland.example`, and add `spusť kontrolu uvolnění pro 4711` above the forwarded text. | A named proposal arrives with the note warning/length. Record proposal subject and ID. If process selection appears, choose the certification definition and wait for its new named proposal. |
| T6 | Use actual **Reply** on that proposal, type `ano`, send once. | Agent verifies one instance and its `ttr_note` containing Markéta's instruction and Jana's text, plus `ttr_source=mail:<Message-ID>`. Record instance/start receipt IDs and proposal subject. Finish its controlled task so no active fixture remains. |
| T6 | Forward the original complaint again without any text of your own. | The three-way question appears: 1 summary, 2 start, 3 nothing. Use actual **Reply**, type `3`, send. Record the subject and closing result; no new instance. |

For every card/proposal outcome, record that it stayed with the intended original
thread and did not attach to a different task's thread. Use the mail client's actual
Reply action; a fresh compose with a matching subject does not carry reply headers.
The webmail walk does not replace the rig's required live checks or its two green
post-walk runs. T4–T6 remain incomplete until their observations and agent checks
are recorded; this blank walk sheet is preparation, not evidence of execution.
