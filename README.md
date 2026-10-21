# Backlink Sentinel 🔗

Backlinks die silently. You find out months later when rankings slip — or never.

Backlink Sentinel is a **free, open-source GitHub Action** that watches your backlink portfolio for link rot. List your backlinks in a file, it checks them on a schedule, and tells you exactly which ones died, which redirect, and which are healthy.

- ✅ **100% free** — no API keys, no cloud service, no signup beyond GitHub
- ✅ **Zero dependencies** — pure Python standard library, runs on any runner
- ✅ **Smart checks** — follows redirect chains, retries HEAD→GET, calls out bot-protection (403/429) instead of mislabeling it as dead
- ✅ **Actionable reports** — Markdown report in your job summary + JSON for automation

## Quick start

1. Create a `links.txt` in your repo — one URL per line:
   ```
   https://example.com/my-guest-post, Guest post on Example
   https://directory.com/listings/my-site
   # lines starting with # are ignored
   ```
2. Add the workflow (`.github/workflows/backlinks.yml`):
   ```yaml
   name: Backlink check
   on:
     schedule:
       - cron: "0 9 * * 1"   # every Monday 9am UTC
     workflow_dispatch:        # plus a manual "Run" button

   jobs:
     check:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: saaslisty/backlink-sentinel@v1
           with:
             links-file: links.txt
   ```
3. Done. Every run posts a report to the job summary and **fails with a warning when links die** — so you notice.

## What it detects

| Status | Meaning |
|---|---|
| ✅ Alive | HTTP 2xx, link works |
| 🔀 Redirected | Link now 301/302s somewhere else — the full chain is shown |
| ❌ Dead | 404/500, DNS failure, connection refused — fix or replace |
| ⚠️ Manual check | 403/429 (bot protection) or timeouts — verify by hand, not counted as dead |

## Inputs

| Input | Default | Description |
|---|---|---|
| `links-file` | `links.txt` | File with one URL per line; optional `, label` after a URL |
| `timeout` | `15` | Seconds per request |
| `workers` | `10` | Parallel checks |
| `report-path` | `backlink-report.md` | Where the Markdown report goes |
| `fail-on-dead` | `true` | Fail the run when dead links are found |

## Run it locally

No GitHub required — it's just a Python script:

```bash
python3 check.py links.txt --output report.md
echo $?   # 0 = all healthy, 1 = dead links found
```

## Why this exists

Paid tools (Ahrefs, Semrush) do this for $$$ a month. Everyone else does it with spreadsheets and manual checks. This is the free, automated middle ground — set it once, get pinged when a backlink rots.

Built by [saaslisty](https://saaslisty.com) — don't find an AI tool, find the whole workflow.

## License

MIT — do whatever you want with it.
