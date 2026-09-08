# 104 API Access Notes

The endpoint below currently returns `403 Forbidden` from Cloudflare when called directly from a server-style client:

```text
https://www.104.com.tw/jobs/search/api/jobs?jobsource=m_joblist_search&keyword=資料科學&mode=s&order=16&page=1&pagesize=20&rostatus=1024&searchJobs=1
```

## What this means

This is not a local filesystem permission problem.
It is an anti-bot challenge on the 104 side.

Typical response markers:

- `HTTP/1.1 403 Forbidden`
- `Server: cloudflare`
- `Cf-Mitigated: challenge`

## Reliable ways to proceed

1. Fetch through a real browser session.
2. Export the browser request from DevTools and reuse its cookies for a short-lived session.
3. Use Playwright or another browser automation step before the API request.
4. Use a provider that is meant for server-to-server access instead of calling 104 directly.

## Local test script

Use [job104_fetcher.py](/Users/hankchou/Documents/NTHU/2026_1/Text mining/TM workshop/TxM project data/n8n_python/job104_fetcher.py) to verify the behavior:

```bash
python3 job104_fetcher.py --keyword 資料科學
```

If you already copied a live browser `Cookie` header:

```bash
JOB104_COOKIE='paste-browser-cookie-here' python3 job104_fetcher.py --keyword 資料科學
```

## Local proxy endpoint

The existing Flask app now also exposes a local proxy route:

```text
GET /fetch-104-jobs?keyword=資料科學&page=1&pagesize=20
```

Example:

```bash
curl 'http://127.0.0.1:5001/fetch-104-jobs?keyword=%E8%B3%87%E6%96%99%E7%A7%91%E5%AD%B8&page=1&pagesize=20'
```

If you need to pass a browser cookie without changing environment variables, send it in the `X-Job104-Cookie` header.

## n8n suggestion

If your workflow must stay inside n8n, the more stable direction is:

1. n8n calls your local Flask route instead of calling 104 directly.
2. The Flask route fetches the 104 JSON using the Python request shape that works on this machine.
3. If 104 tightens protection later, add a browser cookie through `JOB104_COOKIE` or `X-Job104-Cookie`.
4. The returned JSON is passed to your existing analysis flow.
