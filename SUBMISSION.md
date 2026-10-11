# Submission

The final briefs arrive Sunday, October 11, 2026 at 17:00 UTC (10:00 AM Los Angeles). Submit before 20:00 UTC (1:00 PM Los Angeles). These times come from the supplied organizer instructions.

Run from the kit repository directory with the required API keys already configured. Copy `submission-config.example.json` to `submission-config.json` and fill in `team`, `members` (name and email), `repo`, and `mock_url`. Use the address of your actual mock; no mock is deployed by this packaging code. Commit the builder source and configuration before the final run. Submission mode rejects uncommitted builder source so the recorded commit identifies the code that ran. Generated output and trace changes do not block a run.

The actual organizer ZIP contains one final case and asks for the singular eight-field form. Deploy and verify the mock first; follow [the deployment guide](cloudflare-worker/DEPLOY.md). Keep the case and configuration inside the repository so the recorded command is portable. Run on the entire folder:

```text
python my-agents/agent_builder.py "cases/Build the Builder - Final Case" --submission
```

The builder reads the folder's documents and retains the entire case folder in the input snapshot. A workflow PDF is attached visually only when the case entry documents explicitly identify it as an accompanying workflow. Choose one successful run. The runner applies a 30-minute timeout and packaging rejects an overlong run, including tests. The phone agent may only be repaired during a new builder run, never manually after a run. The builder defaults to GPT-5.4 with high reasoning; `--model` overrides the builder only, never the event's Freya phone model.

The required package is `submission.json`, the exported workflow, and the builder's trace. Each successful `--submission` run creates these together in `submissions/<run-id>/`:

- `agent-1.workflow.json`: the platform agent exported automatically through `freya.export_workflow` after building and testing finish.
- `trace.jsonl`: complete streamed SDK events, tool calls/results, start/end time, usage, and exported workflow/agent IDs.
- `submission.json`: exactly the organizer's eight fields: `team`, `members`, `repo`, `commit`, `run_command`, `workflow`, `trace`, and `mock_url`. The workflow and trace paths are relative to the repository root, not to the JSON file. The commit is captured before the run; the command uses repository-relative input paths and runs from the repository root in Bash/Git Bash.

Use the final-case packager after choosing a successful run:

```text
python my-agents/submission.py --final-run submissions/ACTUAL-RUN-ID --output submission.json --zip submission-package.zip
```

It verifies the artifact hashes and packages the existing export and trace without editing the agent. The ZIP preserves repository-relative paths. `ACTUAL-RUN-ID` is a placeholder for the directory printed by your run.

The older website's two-brief format remains supported separately: run each brief with its own `--tool-api`, then use `python my-agents/submission.py --run hidden-1=submissions/RUN-1 --run hidden-2=submissions/RUN-2`. Do not use this format in place of the singular form required by this ZIP.

The custom builder uses the OpenAI Agents SDK directly, so `trace.jsonl` is its run log. If using Claude Code or Codex instead, include that agent's actual session log of the run; a summary or a trace from another run is not a substitute.

Additional supporting artifacts retained in the run folder:

- `console.log`: everything printed by the runner, including tool output and errors.
- `saves.jsonl`: successful workflow saves associated with this run.
- `inputs/`: copies of the complete case folder, or the supplied brief and API file.
- `source/`: the builder, skill, Freya client, and supporting kit files used at run start.
- `manifest.json`: input mapping, agent IDs, export paths and artifact SHA-256 hashes for auditing. This is separate from the organizer's submission schema.

A folder with `FAILED.txt` or without `submission.json` is not ready for submission. Practice runs retain exports, logs and a manifest but do not generate an organizer submission. The JSON confirms packaging, not test success: check the matching trace for validation and test results. Hidden briefs without matching supplied tests are not tested against practice cases.

After choosing the final run:

1. Check that the export and trace belong to this case. Do not edit the phone agent or exported JSON after the run. Rebuild if changes are needed.
2. Commit `submission.json` and the selected run folder, including the export and matching trace. Review the selected files for credentials before committing; never include `env.sh` or API keys. Builder source must already be committed before the run.

```text
git add -- submission.json submissions/ACTUAL-RUN-ID
git diff --cached --stat
git commit -m "Add final agents and matching builder traces"
```

3. Leave the JSON's `commit` pointing to the earlier builder run commit, as requested by the organizer; the artifact commit records the resulting files.
4. Email `submission.json`, its referenced workflow export and trace to **yavuz@freyavoice.ai**, as specified in the ZIP, before **11 October 2026, 20:00 UTC / 23:00 Istanbul / 1:00 PM Los Angeles**. The scripts do not send email.

No hidden-brief run, final export commit, or delivery has been performed merely by adding this workflow.
