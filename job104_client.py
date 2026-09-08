#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared 104 search client for scripts and the local API."""

from __future__ import annotations

import json
from typing import Mapping
from urllib import error, parse, request


BASE_URL = "https://www.104.com.tw/jobs/search/api/jobs"
SEARCH_PAGE_URL = "https://www.104.com.tw/jobs/search/"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://www.104.com.tw",
    "Referer": SEARCH_PAGE_URL,
    "X-Requested-With": "XMLHttpRequest",
}


def build_search_url(
    keyword: str,
    page: int = 1,
    pagesize: int = 20,
    order: str = "16",
    rostatus: str = "1024",
    jobsource: str = "m_joblist_search",
) -> str:
    params = {
        "jobsource": jobsource,
        "keyword": keyword,
        "mode": "s",
        "order": str(order),
        "page": str(page),
        "pagesize": str(pagesize),
        "rostatus": str(rostatus),
        "searchJobs": "1",
    }
    return f"{BASE_URL}?{parse.urlencode(params)}"


def build_headers(keyword: str, cookie: str | None = None) -> dict[str, str]:
    headers = dict(DEFAULT_HEADERS)
    headers["Referer"] = f"{SEARCH_PAGE_URL}?keyword={parse.quote(keyword)}"
    if cookie:
        headers["Cookie"] = cookie
    return headers


def detect_cloudflare(headers: Mapping[str, str], body: str) -> bool:
    lowered = {key.lower(): value.lower() for key, value in headers.items()}
    return (
        lowered.get("cf-mitigated") == "challenge"
        or lowered.get("server") == "cloudflare"
        or "challenges.cloudflare.com" in body.lower()
    )


def explain_forbidden(url: str, headers: Mapping[str, str], body: str) -> str:
    details = [
        f"104 rejected the request with HTTP 403 at: {url}",
    ]
    if detect_cloudflare(headers, body):
        details.extend(
            [
                "",
                "The response looks like a Cloudflare anti-bot challenge, not a local permission error.",
                "Browser-like headers alone are usually not enough.",
                "",
                "Recommended next steps:",
                "1. Open the same search page in a real browser and verify it loads normally.",
                "2. In DevTools -> Network, reload the page and find the `jobs/search/api/jobs` request.",
                "3. Copy the request as cURL, especially the Cookie header created after the challenge.",
                "4. Reuse that browser session in n8n or move the fetch step to Playwright/browser automation.",
            ]
        )
    return "\n".join(details)


def fetch_jobs(
    keyword: str,
    page: int = 1,
    pagesize: int = 20,
    order: str = "16",
    rostatus: str = "1024",
    cookie: str | None = None,
) -> dict:
    url = build_search_url(
        keyword=keyword,
        page=page,
        pagesize=pagesize,
        order=order,
        rostatus=rostatus,
    )
    headers = build_headers(keyword=keyword, cookie=cookie)
    api_request = request.Request(url, headers=headers, method="GET")
    with request.urlopen(api_request, timeout=60) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read().decode(charset, errors="replace")
        return json.loads(body)


def fetch_jobs_from_url(url: str, keyword: str, cookie: str | None = None) -> dict:
    headers = build_headers(keyword=keyword, cookie=cookie)
    api_request = request.Request(url, headers=headers, method="GET")
    with request.urlopen(api_request, timeout=60) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read().decode(charset, errors="replace")
        return json.loads(body)


__all__ = [
    "build_headers",
    "build_search_url",
    "detect_cloudflare",
    "error",
    "explain_forbidden",
    "fetch_jobs",
    "fetch_jobs_from_url",
]
