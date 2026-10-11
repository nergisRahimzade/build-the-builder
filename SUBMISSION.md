# Submission

The final briefs arrive Sunday, October 11, 2026 at 17:00 UTC (10:00 AM Los Angeles). Submit before 20:00 UTC (1:00 PM Los Angeles). These times come from the supplied organizer instructions.

Run from the kit repository directory with the required API keys already configured. Copy `submission-config.example.json` to `submission-config.json` and fill in `team`, `members` (name and email), `repo`, and `mock_url`. Use the address of your actual mock; no mock is deployed by this packaging code. Commit the builder source and configuration before the final run. Submission mode rejects uncommitted builder source so the recorded commit identifies the code that ran. Generated output and trace changes do not block a run.

Keep brief, API and configuration files inside the repository so the recorded command is portable. Run separately for each hidden brief, supplying its own tool API:

```text
python my-agents/agent_builder.py path/to/hidden-brief-1.md --tool-api path/to/hidden-api-1.json --submission
python my-agents/agent_builder.py path/to/hidden-brief-2.md --tool-api path/to/hidden-api-2.json --submission
```

Paths above are placeholders. Do not run them until the actual input files are available. If a brief has multiple source documents, provide an entry document referencing all its source documents and retain those originals with the submission. The builder may be run more than once. Choose exactly one successful run per hidden brief. Keep each run within the kit's 30-minute limit, including tests; the runner does not currently enforce that limit.

The required package is `submission.json`, the exported workflow, and the builder's trace. Each successful `--submission` run creates these together in `submissions/<run-id>/`:

- `agent-1.workflow.json`: the platform agent exported automatically through `freya.export_workflow` after building and testing finish.
- `trace.jsonl`: complete streamed SDK events, tool calls/results, start/end time, usage, and exported workflow/agent IDs.
- `submission.json`: exactly the organizer's eight fields: `team`, `members`, `repo`, `commit`, `run_command`, `workflow`, `trace`, and `mock_url`. The workflow and trace paths are relative to the repository root, not to the JSON file. The commit is captured before the run; the command uses repository-relative input paths and runs from the repository root in Bash/Git Bash.

The organizer's schema describes one workflow. Each chosen brief therefore has its own `submission.json`; keep both selected run folders. Do not combine workflows into an invented array schema.

The custom builder uses the OpenAI Agents SDK directly, so `trace.jsonl` is its run log. If using Claude Code or Codex instead, include that agent's actual session log of the run; a summary or a trace from another run is not a substitute.

Additional supporting artifacts retained in the run folder:

- `console.log`: everything printed by the runner, including tool output and errors.
- `saves.jsonl`: successful workflow saves associated with this run.
- `inputs/`: copies of the supplied brief and API file.
- `source/`: the builder, skill, Freya client, and supporting kit files used at run start.
- `manifest.json`: input mapping, agent IDs, export paths and artifact SHA-256 hashes for auditing. This is separate from the organizer's submission schema.

A folder with `FAILED.txt` or without `submission.json` is not ready for submission. Practice runs retain exports, logs and a manifest but do not generate an organizer submission. The JSON confirms packaging, not test success: check the matching trace for validation and test results. Hidden briefs without matching supplied tests are not tested against practice cases.

After choosing the two runs:

1. Check that each export and trace belongs to the corresponding hidden brief and API. Do not edit the phone agent or exported JSON after the run. Rebuild if changes are needed.
2. Commit both selected run folders, including the exports and matching traces, plus your builder code and skill. Review the selected files for credentials before committing; never include `env.sh` or API keys.

```text
git add -- submissions/<selected-run-1> submissions/<selected-run-2>
git diff --cached --stat
git commit -m "Add final agents and matching builder traces"
```

3. Record the repository URL and artifact commit, and the two selected package paths for delivery. Each includes `submission.json`, the exported workflow and the matching trace. Leave the JSON's `commit` pointing to the earlier builder run commit, as requested by the organizer; the artifact commit records the resulting files.
4. Deliver the packages through the organizer's designated channel before the deadline. No recipient or delivery channel has been provided here; repository preparation alone does not complete delivery.

No hidden-brief run, final export commit, or delivery has been performed merely by adding this workflow.
