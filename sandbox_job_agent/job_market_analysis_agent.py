#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sandbox agent prototype for assignment demo."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import textwrap
import zipfile
from urllib import error, request


DEFAULT_BASE_URL = "http://127.0.0.1:5001"

FULL_ANALYSIS_KEYWORDS = {
    "完整", "分群", "語意", "semantic", "cluster", "embedding",
    "sbert", "bundle", "相似", "similarity", "分析包",
}


@dataclass
class AgentDecision:
    mode: str
    endpoint: str
    output_filename: str
    rationale: str


def choose_tool(prompt: str) -> AgentDecision:
    lowered = prompt.lower()
    if any(keyword in lowered for keyword in FULL_ANALYSIS_KEYWORDS):
        return AgentDecision(
            mode="full_analysis",
            endpoint="/generate-analysis-bundle",
            output_filename="job_analysis_bundle.zip",
            rationale="The request mentions semantic analysis, clustering, or embeddings, so the agent chose the full SBERT bundle tool.",
        )

    return AgentDecision(
        mode="quick_overview",
        endpoint="/generate-wordcloud",
        output_filename="wordcloud.png",
        rationale="The request asks for a quick overview, so the agent chose the TF-IDF wordcloud tool.",
    )


def load_jobs_payload(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as input_file:
        return json.load(input_file)


def call_api(base_url: str, endpoint: str, payload: dict) -> tuple[bytes, str]:
    api_request = request.Request(
        url=f"{base_url}{endpoint}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(api_request, timeout=180) as response:
            return response.read(), response.headers.get_content_type()
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"API call failed with status {exc.code} at {endpoint}.\n{body}"
        ) from exc
    except error.URLError as exc:
        raise RuntimeError(
            f"Could not reach the local API at {base_url}. "
            "Make sure wordcloud-api is running and port 5001 is mapped to the host."
        ) from exc


def extract_jobs(payload: dict) -> list[dict]:
    if isinstance(payload, dict) and "jobs" in payload and isinstance(payload["jobs"], list):
        return payload["jobs"]
    if isinstance(payload, list):
        return payload
    return []


def parse_descriptions(items):
    values = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and item.get("description"):
                values.append(str(item["description"]))
    return values


def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z+#]{1,30}", text.lower())


def build_top_terms(jobs: list[dict], top_k: int = 15) -> list[tuple[str, int]]:
    stopwords = {"the", "and", "for", "with", "data", "using", "support"}
    counts = {}
    for job in jobs:
        parts = [
            str(job.get("jobName", "")),
            str(job.get("description", "")),
            *parse_descriptions(job.get("pcSkills", [])),
            *parse_descriptions(job.get("languageRequirements", [])),
        ]
        for token in tokenize(" ".join(parts)):
            if token in stopwords:
                continue
            counts[token] = counts.get(token, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:top_k]


def offline_quick_artifact(jobs: list[dict], output_path: Path) -> tuple[Path, str]:
    top_terms = build_top_terms(jobs)
    lines = [
        "# Offline Quick Wordcloud Summary",
        "",
        "The live API was unavailable, so the sandbox agent generated a lightweight local summary instead.",
        "",
        f"- Job count: {len(jobs)}",
        "",
        "## Top Terms",
        "",
    ]
    for rank, (term, count) in enumerate(top_terms, start=1):
        lines.append(f"{rank}. `{term}` ({count})")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path, "text/markdown"


def offline_full_artifact(jobs: list[dict], output_path: Path) -> tuple[Path, str]:
    top_terms = build_top_terms(jobs)
    projection_rows = []
    cluster_rows = {}
    for index, job in enumerate(jobs):
        cluster_id = index % 2
        skills = parse_descriptions(job.get("pcSkills", []))
        skill_text = ", ".join(skills)
        projection_rows.append([
            index,
            job.get("company", ""),
            job.get("jobName", ""),
            cluster_id,
            len(job.get("description", "")),
            len(skills),
            skill_text,
        ])
        cluster_rows.setdefault(cluster_id, []).append(job.get("jobName", ""))

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        summary_lines = [
            "# Offline Full Analysis Summary",
            "",
            "The live SBERT API was unavailable, so the sandbox agent created a lightweight local analysis bundle.",
            "",
            f"- Job count: {len(jobs)}",
            "- Simulated cluster count: 2",
            "",
            "## Top Terms",
            "",
        ]
        for rank, (term, count) in enumerate(top_terms, start=1):
            summary_lines.append(f"{rank}. `{term}` ({count})")
        bundle.writestr("offline_summary.md", "\n".join(summary_lines))

        projection_csv = ["job_index,company,job_name,cluster_id,description_length,skill_count,skills"]
        for row in projection_rows:
            projection_csv.append(",".join(f"\"{str(value).replace('\"', '\"\"')}\"" for value in row))
        bundle.writestr("job_projection.csv", "\n".join(projection_csv))

        cluster_csv = ["cluster_id,cluster_size,sample_jobs"]
        for cluster_id, names in sorted(cluster_rows.items()):
            cluster_csv.append(f"\"{cluster_id}\",\"{len(names)}\",\"{' | '.join(names)}\"")
        bundle.writestr("cluster_summary.csv", "\n".join(cluster_csv))

    return output_path, "application/zip"


def local_fallback_artifact(decision: AgentDecision, payload: dict, outputs_dir: Path) -> tuple[Path, str, str]:
    jobs = extract_jobs(payload)
    if decision.mode == "full_analysis":
        output_path = outputs_dir / "offline_analysis_bundle.zip"
        saved_path, mime_type = offline_full_artifact(jobs, output_path)
    else:
        output_path = outputs_dir / "offline_wordcloud_summary.md"
        saved_path, mime_type = offline_quick_artifact(jobs, output_path)

    note = (
        "The live local API was unavailable, so the sandbox agent switched to an offline fallback mode "
        "using the sample jobs payload."
    )
    return saved_path, mime_type, note


def write_summary(
    summary_path: Path,
    prompt: str,
    jobs_path: Path,
    base_url: str,
    decision: AgentDecision,
    output_path: Path,
    mime_type: str,
    execution_note: str,
) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    summary = textwrap.dedent(
        f"""\
        # Job Market Analysis Agent Run

        - Timestamp: `{timestamp}`
        - Prompt: `{prompt}`
        - Input jobs file: `{jobs_path}`
        - Tool base URL: `{base_url}`
        - Chosen mode: `{decision.mode}`
        - Chosen endpoint: `{decision.endpoint}`
        - Rationale: {decision.rationale}
        - Output file: `{output_path.name}`
        - Output MIME type: `{mime_type}`
        - Execution note: {execution_note}

        ## What Happened

        The sandbox agent read the natural-language request, selected the matching analysis tool, executed the available tool path, and saved the returned artifact into the sandbox output folder.
        """
    )
    summary_path.write_text(summary, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sandbox Job Market Analysis Agent")
    parser.add_argument("--prompt", required=True, help="Natural-language analysis request")
    parser.add_argument(
        "--jobs",
        default="sandbox_job_agent/sample_jobs.json",
        help="Path to jobs payload JSON file",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Base URL for the local analysis API",
    )
    args = parser.parse_args()

    sandbox_dir = Path(__file__).resolve().parent
    outputs_dir = sandbox_dir / "outputs"
    outputs_dir.mkdir(exist_ok=True)

    jobs_path = Path(args.jobs)
    if not jobs_path.is_absolute():
        jobs_path = (Path.cwd() / jobs_path).resolve()

    payload = load_jobs_payload(jobs_path)
    decision = choose_tool(args.prompt)
    try:
        content, mime_type = call_api(args.base_url, decision.endpoint, payload)
        output_path = outputs_dir / decision.output_filename
        output_path.write_bytes(content)
        execution_note = "Live API call succeeded."
    except RuntimeError as exc:
        output_path, mime_type, execution_note = local_fallback_artifact(decision, payload, outputs_dir)
        execution_note = f"{execution_note} Original API error: {exc}"

    summary_path = outputs_dir / "run_summary.md"
    write_summary(summary_path, args.prompt, jobs_path, args.base_url, decision, output_path, mime_type, execution_note)

    print(f"Agent mode: {decision.mode}")
    print(f"Endpoint: {decision.endpoint}")
    print(f"Saved output: {output_path}")
    print(f"Saved summary: {summary_path}")
    print(f"Execution note: {execution_note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
