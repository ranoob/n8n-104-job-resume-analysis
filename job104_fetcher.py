#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch 104 job search results and explain common Cloudflare failures."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from job104_client import build_search_url, error, explain_forbidden, fetch_jobs


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch 104 search results")
    parser.add_argument("--keyword", default="資料科學", help="Search keyword")
    parser.add_argument("--page", type=int, default=1, help="Page number")
    parser.add_argument("--pagesize", type=int, default=20, help="Result size")
    parser.add_argument(
        "--output",
        default="104_jobs_response.json",
        help="Path to write the JSON response",
    )
    parser.add_argument(
        "--cookie",
        default=os.environ.get("JOB104_COOKIE"),
        help="Cookie header copied from a real browser session",
    )
    args = parser.parse_args()

    url = build_search_url(args.keyword, args.page, args.pagesize)

    try:
        payload = fetch_jobs(
            keyword=args.keyword,
            page=args.page,
            pagesize=args.pagesize,
            cookie=args.cookie,
        )
    except error.HTTPError as exc:
        charset = exc.headers.get_content_charset() or "utf-8"
        body = exc.read().decode(charset, errors="replace")
        if exc.code == 403:
            print(explain_forbidden(url, exc.headers, body), file=sys.stderr)
            return 2
        print(f"HTTP {exc.code} while requesting {url}", file=sys.stderr)
        print(body[:800], file=sys.stderr)
        return 1
    except error.URLError as exc:
        print(f"Network error while requesting {url}: {exc}", file=sys.stderr)
        return 1

    output_path = Path(args.output).resolve()
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Saved {len(payload.get('data', []))} jobs to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
