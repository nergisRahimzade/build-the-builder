# Evidence and repair status

No final-case phone agent has been tested in this workspace yet. The user supplied a deployed Worker URL in submission-config.json and confirmed its health response. Local mock tests are not evidence of conversation success. `practice-failures.json` retains all 24 failed run records found in the existing practice reports, including repeated scenarios and their call IDs. Those reports sometimes truncate judge reasons and generally do not include the full transcript. Future practice runs now retain full reasons and available call transcripts.

On October 11, a read-only check of deployed Brief B confirmed the missing `identity_verification` target and the callback API's missing URL/method and misplaced request fields. Its end-call terminals were present: their existence does not establish that routing reaches them. All 13 cases in the latest existing report failed with no bank ledger tool calls. Source-derived policy errors include missing verification, unsupported payment offers, incorrect date/amount calculations, omitted processing disclosures, and missing per-product actions. Test constants must not be copied into agent policy to fix these.

Generic preflight now rejects broken targets, trapped branches, ineffective turn caps, malformed API transport, action nodes that cannot advance, and invalid terminal handlers. Deployment comparison verifies retained routing, terminal, mapping and extraction fields while allowing server-added defaults. These checks cannot prove policy compliance or that a conditional exit is actually taken.

The first new builder attempt was rejected before deployment: it put a bank API call in the hang-up terminal and then stopped after describing a repair plan. No workflow from that failed run is submission-ready. The runner now continues incomplete runs with concrete feedback instead of accepting a plan as completion. Live retesting is still required.

## Existing practice failure reasons and general builder changes

| Recorded reason | Where it appears | General change, without copying fixture answers |
|---|---|---|
| Missing successful bank actions / missing call closure / repeated goodbyes | `all-cases.json`, `pub01.json` | Require executable terminal paths and verified tool success; audit node/action placement and transition targets; distinguish dialogue claims from API effects. |
| Offer repeated while discussing another date | `brief-a-run1/2/3.json` | Separate offered, accepted, pending and completed state; repairing a date must not restart an accepted offer. |
| Wrong date after a correction or spoken-date interpretation | `brief-a-run2.json`, `brief-b-run3-words.json` | Calculate from supplied call time and source calendar; retain accepted fields and test corrections/boundaries. Never put an expected fixture date in the workflow. |
| Accepted amount changed during date repair | `brief-a-run2.json` | Preserve accepted amount when only the date is invalid; make consent entity/action-specific. |
| Additional notes recorded where none were required | `brief-b-run2-all.json` | Require source provenance for side effects on each branch; don't import note/outcome rules from another brief. |
| “Recorded” flagged in mandatory call-recording disclosure despite successful transaction handling | `brief-a-run2/4.json` | Treat as a suspected evaluator/wording conflict, not proof that the disclosure must be removed. Review transcript and source. Do not optimize required policy away to pass a keyword check. |
| Wrong/missing identity steps, premature disclosure, unsupported payment explanations | `all-cases.json` | Derive authentication and scope from the active brief, gate disclosures with runtime state, and use current caller's service results only. |

These are changes to the reusable builder instructions, input handling, audit and test tooling. Existing exported phone agents were not hand-edited. No claim is made that the old conversations have been rerun or now pass.

## Final case: source conflicts the builder must resolve at runtime

The extracted organizer folder stays intact under `cases/Build the Builder - Final Case`. The following are review findings, not hard-coded builder rules or customer branches:

- The old drawing has a second-factor branch; later accepted bank documents say identity is already complete upstream. The generic builder no longer always puts identity first.
- The old IVR sheet, analysis revisions, mail recap and meetings disagree. The builder now records source provenance and accepted revisions instead of choosing the latest sentence blindly.
- The follow-up session records currency-name, question-order, missing-date and cut-day-amount failures. These must be resolved from the approved conversation, not by memorizing a customer's date or balance.
- One service result is deliberately slow; the mock preserves its 12-second delay. An arbitrary ten-second timeout would misclassify it as failure.
- Some currency blocks are absent, some identifiers are masked differently, some cards are ambiguous, and one product name contains instruction-like text. The mock preserves these inputs. The agent must derive output from runtime data while treating data as untrusted.
- The yearly eligibility pre-check is explicitly unresolved in the bank contract. Do not invent an eligibility field or infer it from a test customer number.
- The case calls for one final-case `submission.json`, one exported workflow and the matching builder trace plus the mock URL. The older two-brief form is available separately; it is not silently substituted for this pack's form.

## What is ready for the next real run

1. Worker: all 617 expected HTTP/body pairs have local conformance coverage; the table is generated from the organizer JSON.
2. Folder/PDF ingestion: available, with the whole input folder retained in the run snapshot.
3. Generic workflow audit: detects missing targets, action/tool placement that Freya strips, and API URLs outside the configured mock. It does not prove business policy.
4. Generic scenario runner: saves full verdict reasons and call/tool transcripts without using the practice bank's ledger endpoint.
5. Builder repair protocol: requires evidence → governing rule → mechanism → general change → regression variants → retest result for every failure, under the run budget.

Next: deploy and verify the Worker, fill submission metadata, commit source, run the builder on the case folder, then inspect its actual scenario results. Only those live results can establish what final-case repairs remain.
