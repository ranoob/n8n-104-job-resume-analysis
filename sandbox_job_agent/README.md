# Sandbox: Job Market Analysis Agent

This folder is an isolated sandbox for a simple assignment-ready agent prototype.

It does not modify the main project workflow. The agent:

1. Reads a natural-language request.
2. Chooses either the quick wordcloud tool or the full SBERT analysis tool.
3. Calls the existing local API.
4. Saves the returned file into `outputs/`.
5. Writes a short Markdown summary of what it did.

## Files

- `job_market_analysis_agent.py`: the sandbox agent
- `sample_jobs.json`: small sample payload matching the existing API schema
- `outputs/`: created automatically when the script runs

## Usage

Quick overview:

```bash
python3 sandbox_job_agent/job_market_analysis_agent.py \
  --prompt "請幫我分析這批 AI 工程師職缺，先給我一張技能文字雲" \
  --jobs sandbox_job_agent/sample_jobs.json
```

Full semantic analysis:

```bash
python3 sandbox_job_agent/job_market_analysis_agent.py \
  --prompt "請分析這批 AI 工程師職缺，幫我做文字雲和語意分群" \
  --jobs sandbox_job_agent/sample_jobs.json
```

## Notes

- The script defaults to `http://127.0.0.1:5001` because it runs on the host machine.
- The quick wordcloud path only needs the existing TF-IDF API.
- The full bundle path requires the container image to include `sentence-transformers`.
