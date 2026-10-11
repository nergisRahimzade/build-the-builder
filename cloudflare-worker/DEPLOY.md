# Deploy the final-case mock

The Worker is ready in this directory. `worker.js` includes a `const RECORDS = ...` table generated from the organizer's full `test-environment/test-customers.json`: **34 customers, 617 service-response records**. Do not enter balances or customers by hand, create a D1/KV table, replace errors with success, or use practice bank data.

The immutable fixture table is the mock's data. It is not part of the builder's decision logic. Even the change/send endpoints return their prescribed fixture responses; they do not rewrite other fixtures. The pack explicitly requires those exact responses on each call.

## 1. Open PowerShell in the Worker directory

```powershell
cd 'D:\NR\Build-the-Builder\build-the-builder-v3\build-the-builder\cloudflare-worker'
node --version
```

Use a current Node LTS supported by Wrangler. This workspace has Node 24.12.0. You need a Cloudflare account, but no database and no real bank credentials.

## 2. Know what is in the table

| Endpoint after `/voice/v1/` | Table lookup |
|---|---|
| `cards.list` | customer number |
| `cards.balance` | exact masked card number from card list |
| `statement.week.get` | exact card number |
| `statement.week.decide` | exact card number, then requested week |
| `statement.week.change` | exact card number, then requested week |
| `contact.email.get` | customer number |
| `statement.pdf.send` | customer number, as specified by the fixtures |

Each entry's `http` becomes the HTTP status; its `response` becomes the body. `delaySeconds` delays the response and is not included in the body. One balance response waits 12 seconds. Missing currency blocks stay missing. A malicious-looking product name in the fixtures stays literal data; the phone agent must not follow it as an instruction.

The Worker returns the contract's errors for missing/unknown inputs. Unresolved panel placeholders do not silently select a different customer. For testing, use an actual synthetic number from the fixture file. `/oauth2/token` returns a synthetic test token; authentication is not checked in the organizer's test environment.

If the organizer updates the fixture file, regenerate the table (from this directory):

```powershell
python -B generate_worker.py '../cases/Build the Builder - Final Case/test-environment/test-customers.json'
```

## 3. Run the local checks

```powershell
node --test worker.test.mjs
npx wrangler dev
```

Leave that terminal running. In another PowerShell window:

```powershell
Invoke-RestMethod 'http://localhost:8787/health'
$body = @{ data = @{ customerNo = '90000001'; aiFlow = 'CardOps' }; call = @{ lang = 'tr' } } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri 'http://localhost:8787/voice/v1/cards.list' -ContentType 'application/json' -Body $body
```

The customer above is an organizer-supplied synthetic example, not a new record to add. To verify every response against the supplied data, run from this directory:

```powershell
python -B verify_remote.py http://localhost:8787
```

Expect `total: 617`, `passed: 617`, and an empty failures list. Expected HTTP 400/404/500 fixtures count as passes when status and body match exactly. This tests the mock, not the phone agent's conversations.

## 4. Deploy

You may change the `name` in `wrangler.toml` before deploying; the current name is `freya-statement-mock`.

```powershell
npx wrangler login
npx wrangler deploy
```

Complete Cloudflare login in the browser. Deployment prints your actual URL, for example `https://freya-statement-mock.YOUR-SUBDOMAIN.workers.dev`. The example URL is a placeholder. Keep the service available until results are announced.

If you prefer Cloudflare's dashboard editor, create a Worker, paste **the entire generated `worker.js`** into its editor, and deploy. It has no imports or external data dependencies. Do not paste only the table or the organizer's `/ping` example.

## 5. Verify the public service

```powershell
Invoke-RestMethod 'https://YOUR-WORKER.workers.dev/health'
python -B verify_remote.py https://YOUR-WORKER.workers.dev
```

Use the real URL from deployment. Fix any mismatch before building the phone agent; a healthy `/health` endpoint alone does not verify the bank services.

## 6. Connect the builder and make the submission

Return to the kit directory. Copy `submission-config.example.json` to `submission-config.json`, then fill the team, members, repository and **actual deployed `mock_url`**. The builder passes that URL into its generated tools while preserving contract paths and envelopes.

```powershell
cd ..
python -m pip install -r requirements-builder.txt
```

Configure the required API keys using your existing `env.sh`/environment setup. Never commit `env.sh`. Commit the builder source, dependencies, skill, supplied case folder and Worker before a submission run. Check the staged files before committing:

```powershell
git add -- my-agents my-skills freya.py tools requirements-builder.txt .gitignore cloudflare-worker cases submission-config.json submission-config.example.json
git diff --cached --stat
git commit -m 'Prepare final case builder and fixture mock'
python -B my-agents/agent_builder.py 'cases/Build the Builder - Final Case' --submission
```

This records the source commit and command used, passes the configured mock URL, and saves the input folder, trace, console log and exported agent together. The model's build/test/repair loop must complete within the event limit. Packaging rejects a recorded duration over 30 minutes; this is not a guaranteed process kill at the deadline.

After a successful run, select its actual directory:

```powershell
python -B my-agents/submission.py --final-run 'submissions/ACTUAL-RUN-ID' --output submission.json --zip submission-package.zip
git add -- submission.json 'submissions/ACTUAL-RUN-ID'
git diff --cached --stat
git commit -m 'Add final workflow and matching builder trace'
```

The pack's final-case form requires one agent, so use `--final-run`. The older website's two-brief `--run` command remains available but is not the form in this ZIP. The generated JSON's commit remains the source commit used for the run; the later commit contains the output artifacts.

Send `submission.json`, its referenced exported workflow, and its referenced trace to **yavuz@freyavoice.ai** before **11 October 2026, 20:00 UTC / 23:00 Istanbul / 1:00 PM Los Angeles**. The optional ZIP preserves paths for convenient packaging. No email is sent by these scripts. Do not manually edit the generated agent after the run.

Official Cloudflare references: https://developers.cloudflare.com/workers/get-started/guide/ and https://developers.cloudflare.com/workers/wrangler/install-and-update/ .
