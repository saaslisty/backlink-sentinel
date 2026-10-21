#!/usr/bin/env python3
"""
backlink-sentinel: check a list of backlink URLs and report which are
alive, redirected, or dead.

Usage:
    python check.py links.txt [--output report.md] [--timeout 15] [--workers 10]

Input file: one URL per line. Blank lines and lines starting with # are ignored.
A line may optionally carry a label after a comma:  https://example.com/post, My guest post

Exit code: 0 if every link is alive, 1 if any link is dead/errored.
"""

import argparse
import concurrent.futures
import json
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from dataclasses import dataclass, field


@dataclass
class LinkResult:
    url: str
    label: str = ""
    status: str = "unknown"      # alive | redirected | dead | error
    http_code: int | None = None
    final_url: str = ""
    redirect_chain: list = field(default_factory=list)
    detail: str = ""
    checked_in_s: float = 0.0


USER_AGENT = (
    "Mozilla/5.0 (compatible; backlink-sentinel/1.0; +https://github.com/saaslisty/backlink-sentinel)"
)


def fetch(url: str, timeout: int) -> LinkResult:
    """Check one URL: try HEAD first (cheap), fall back to GET."""
    started = time.time()
    res = LinkResult(url=url)
    chain: list[str] = []

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None  # we track redirects manually

    opener = urllib.request.build_opener(NoRedirect)
    current = url
    try:
        for _hop in range(10):  # manual redirect following, max 10 hops
            for method in ("HEAD", "GET"):
                req = urllib.request.Request(
                    current, method=method,
                    headers={"User-Agent": USER_AGENT},
                )
                try:
                    with opener.open(req, timeout=timeout) as resp:
                        code = resp.getcode()
                        break
                except urllib.error.HTTPError as e:
                    code = e.code
                    # 405/501 on HEAD -> retry with GET; otherwise take the code
                    if method == "HEAD" and code in (405, 501):
                        continue
                    break
            else:  # pragma: no cover - defensive
                code = 0

            res.http_code = code
            if code in (301, 302, 303, 307, 308):
                # re-issue to capture the Location header
                req = urllib.request.Request(
                    current, method="GET", headers={"User-Agent": USER_AGENT}
                )
                try:
                    with opener.open(req, timeout=timeout) as resp:
                        loc = resp.headers.get("Location", "")
                except urllib.error.HTTPError as e:
                    loc = e.headers.get("Location", "") if e.headers else ""
                if not loc:
                    res.status, res.detail = "error", "redirect with no Location header"
                    break
                nxt = urllib.parse.urljoin(current, loc)
                chain.append(f"{code} -> {nxt}")
                current = nxt
                continue
            break  # not a redirect: done

        res.redirect_chain = chain
        res.final_url = current
        code = res.http_code or 0
        if 200 <= code < 300:
            res.status = "redirected" if chain else "alive"
            res.detail = f"HTTP {code}" + (f" after {len(chain)} redirect(s)" if chain else "")
        elif 300 <= code < 400:
            res.status = "redirected"
            res.detail = f"HTTP {code} (max hops reached)"
        elif code in (403, 429):
            # Likely bot protection, not a dead link — say so explicitly.
            res.status = "error"
            res.detail = f"HTTP {code} (blocked by bot protection — verify manually)"
        elif code:
            res.status = "dead"
            res.detail = f"HTTP {code}"
        else:
            res.status = "error"
            res.detail = "no response"
    except urllib.error.URLError as e:
        res.status = "dead" if "Name or service not known" in str(e.reason) else "error"
        res.detail = f"URL error: {e.reason}"
    except Exception as e:  # timeouts land here too
        res.status = "error"
        res.detail = f"{type(e).__name__}: {e}"
    finally:
        res.checked_in_s = round(time.time() - started, 2)
    return res


def load_links(path: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "," in line:
                url, label = line.split(",", 1)
                links.append((url.strip(), label.strip()))
            else:
                links.append((line, ""))
    # de-dupe while keeping order
    seen, out = set(), []
    for url, label in links:
        if url not in seen:
            seen.add(url)
            out.append((url, label))
    return links


def markdown_report(results: list[LinkResult]) -> str:
    alive = [r for r in results if r.status == "alive"]
    redir = [r for r in results if r.status == "redirected"]
    dead = [r for r in results if r.status == "dead"]
    err = [r for r in results if r.status == "error"]

    lines = [
        "# Backlink Sentinel report",
        "",
        f"Checked {len(results)} links — "
        f"**{len(alive)} alive**, {len(redir)} redirected, "
        f"**{len(dead)} dead**, {len(err)} needs-manual-check.",
        "",
    ]
    if dead:
        lines += ["## ❌ Dead links (fix these first)", ""]
        for r in dead:
            lines.append(f"- `{r.url}` — {r.detail}" + (f" ({r.label})" if r.label else ""))
        lines.append("")
    if redir:
        lines += ["## 🔀 Redirected links", ""]
        for r in redir:
            lines.append(
                f"- `{r.url}` → `{r.final_url}` — {r.detail}"
                + (f" ({r.label})" if r.label else "")
            )
        lines.append("")
    if err:
        lines += ["## ⚠️ Needs a manual check", ""]
        for r in err:
            lines.append(f"- `{r.url}` — {r.detail}" + (f" ({r.label})" if r.label else ""))
        lines.append("")
    if alive:
        lines += ["<details>", "<summary>✅ Alive links "
                  f"({len(alive)}) — click to expand</summary>", ""]
        for r in alive:
            lines.append(f"- `{r.url}` — {r.detail}" + (f" ({r.label})" if r.label else ""))
        lines += ["", "</details>", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Check backlink URLs for link rot.")
    ap.add_argument("input", help="text file with one URL per line")
    ap.add_argument("--output", "-o", default="report.md", help="markdown report path")
    ap.add_argument("--json", default="report.json", help="json report path")
    ap.add_argument("--timeout", type=int, default=15, help="seconds per request")
    ap.add_argument("--workers", type=int, default=10, help="parallel checks")
    args = ap.parse_args()

    links = load_links(args.input)
    if not links:
        print("No links found in input file.", file=sys.stderr)
        return 2

    print(f"Checking {len(links)} links with {args.workers} workers…", flush=True)
    results: list[LinkResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch, url, args.timeout): (url, label) for url, label in links}
        for fut in concurrent.futures.as_completed(futs):
            url, label = futs[fut]
            r = fut.result()
            r.url, r.label = url, label
            results.append(r)
            mark = {"alive": "✅", "redirected": "🔀", "dead": "❌"}.get(r.status, "⚠️")
            print(f"  {mark} {url} — {r.detail} ({r.checked_in_s}s)", flush=True)

    # keep input order in the reports
    order = {url: i for i, (url, _) in enumerate(links)}
    results.sort(key=lambda r: order.get(r.url, 0))

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(markdown_report(results))
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump([r.__dict__ for r in results], f, indent=2)

    dead = sum(1 for r in results if r.status in ("dead", "error"))
    print(f"\nDone: {len(results) - dead}/{len(results)} healthy. "
          f"Report -> {args.output}")
    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main())
