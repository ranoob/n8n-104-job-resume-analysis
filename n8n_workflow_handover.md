# n8n Workflow Handover

Last updated: `2026-06-05 06:44:45`

## Overview

This document summarizes the current `n8n` workflow, the backend/API support added for it, the outputs it generates, and the current state of the project.

- Workflow name: `tm_final`
- Workflow ID: `EfIzfI0p7tneeCkS`
- n8n URL: `http://localhost:5678/workflow/EfIzfI0p7tneeCkS`
- Main purpose:
  - Fetch jobs from `104`
  - Filter internship-like jobs
  - Store job rows in Google Sheets
  - Generate analysis visuals and a zip bundle
  - Send the results by Gmail

## Current Flow

The active main path is:

```text
Schedule Trigger
-> Clear sheet
-> Code in JavaScript
-> HTTP Request2
-> Split Out
-> Filter
-> Append row in sheet
-> Aggregate
-> HTTP Wordcloud
-> HTTP Resume Fit
-> HTTP Cluster Map
-> HTTP Request1
-> Send a message
```

There is also one extra node currently present but not connected to the active path:

```text
Read/Write Files from Disk
```

## Node Details

### 1. `Schedule Trigger`
- Type: `n8n-nodes-base.scheduleTrigger`
- Purpose: runs the workflow weekly
- Current schedule:
  - every week
  - day: `1`
  - hour: `7`

### 2. `Clear sheet`
- Type: `n8n-nodes-base.googleSheets`
- Purpose: clears the Google Sheet before writing new job results
- Sheet:
  - document: `1aQbufqN5885icG8rlll5rmaoTr2c7maJnOv7KzkILo4`
  - sheet: `sheet1`
- Setting:
  - `keepFirstRow = true`

### 3. `Code in JavaScript`
- Type: `n8n-nodes-base.code`
- Purpose: creates page numbers for pagination
- Current output:

```js
return [
  { json: { page: 1 } },
  { json: { page: 2 } },
  { json: { page: 3 } },
  { json: { page: 4 } },
  { json: { page: 5 } }
];
```

### 4. `HTTP Request2`
- Type: `n8n-nodes-base.httpRequest`
- Purpose: fetches jobs from local proxy API instead of calling `104` directly
- URL:
  - `http://host.docker.internal:5001/fetch-104-jobs`
- Query params:
  - `keyword = 財務管理 會計`
  - `page = {{$json.page}}`
  - `pagesize = 20`
- Headers:
  - `User-Agent = Mozilla/5.0 ... Chrome/146.0.0.0 ...`
  - `Referer = https://www.104.com.tw/`

How to change the search:
- Edit the `keyword` value in `HTTP Request2`
- Re-run the workflow from the beginning
- Do not only run the later analysis nodes, or they will reuse already-fetched jobs

### 5. `Split Out`
- Type: `n8n-nodes-base.splitOut`
- Purpose: splits the `data` array from the job API into one item per job
- Field:
  - `fieldToSplitOut = data`

### 6. `Filter`
- Type: `n8n-nodes-base.filter`
- Purpose: keeps internship-like roles
- Current conditions:
  - `jobName contains 實習`
  - `jobName contains intern`
- Combinator:
  - `or`

### 7. `Append row in sheet`
- Type: `n8n-nodes-base.googleSheets`
- Purpose: appends filtered jobs into Google Sheets
- Current mapped columns:
  - `appearDate`
  - `company`
  - `description`
  - `jobAddress`
  - `jobName`
  - `link`
  - `major`
  - `salarylow`
  - `salaryhigh`
  - `MNC`
  - `languageRequirements`
  - `pcSkills`

### 8. `Aggregate`
- Type: `n8n-nodes-base.aggregate`
- Purpose: collects all filtered jobs into one payload for the analysis APIs
- Output field:
  - `jobs`

### 9. `HTTP Wordcloud`
- Type: `n8n-nodes-base.httpRequest`
- Purpose: generates the word cloud image
- URL:
  - `http://host.docker.internal:5001/generate-wordcloud`
- Body:
  - `{{ $('Aggregate').first().json.jobs }}`
- Response:
  - file
  - output property: `wordcloud`

### 10. `HTTP Resume Fit`
- Type: `n8n-nodes-base.httpRequest`
- Purpose: generates the resume/job fit visualization
- URL:
  - `http://host.docker.internal:5001/generate-resume-fit-visual`
- Body:
  - `{{ $('Aggregate').first().json.jobs }}`
- Response:
  - file
  - output property: `resume_fit`

### 11. `HTTP Cluster Map`
- Type: `n8n-nodes-base.httpRequest`
- Purpose: generates the job clustering visualization
- URL:
  - `http://host.docker.internal:5001/generate-cluster-map`
- Body:
  - `{{ $('Aggregate').first().json.jobs }}`
- Response:
  - file
  - output property: `cluster_map`

### 12. `HTTP Request1`
- Type: `n8n-nodes-base.httpRequest`
- Purpose: generates the full analysis zip bundle
- URL:
  - `http://host.docker.internal:5001/generate-analysis-bundle`
- Body:
  - `{{ $('Aggregate').first().json.jobs }}`
- Response:
  - file
  - output property: `bundle`

### 13. `Send a message`
- Type: `n8n-nodes-base.gmail`
- Purpose: sends the final email with job list and attachments
- Current recipients in the GitHub export:
  - `To: your-email@example.com`
  - `CC: your-email@example.com`
- Subject:
  - `你好！New Internship Found!🤩`
- Attachments:
  - `wordcloud`
  - `resume_fit`
  - `cluster_map`
  - `bundle`

Note:
- The email body still mentions the word cloud specifically, even though the workflow now also attaches:
  - resume fit chart
  - cluster map
  - zip bundle

### 14. `Read/Write Files from Disk`
- Type: `n8n-nodes-base.readWriteFile`
- Status: currently not connected to the active path
- Purpose:
  - can write zip files into the Docker container
- Current path template:

```text
/home/node/.n8n-files/job_analysis_bundle_{{$now.toFormat('yyyyLLdd_HHmmss')}}.zip
```

## Backend / API Support

These APIs are currently used or available in the local Flask service:

### Health
- `GET /health`

### 104 Proxy
- `GET /fetch-104-jobs`

### Resume Support
- `GET /sample-resume-profile`
- `POST /analyze-resume-fit`

### Visual Outputs
- `POST /generate-wordcloud`
- `POST /generate-resume-fit-visual`
- `POST /generate-cluster-map`

### Full Bundle
- `POST /generate-analysis-bundle`

Backend implementation files:
- [api_server.py](/Users/hankchou/Documents/NTHU/2026_1/Text%20mining/TM%20workshop/TxM%20project%20data/n8n_python/api_server.py)
- [analysis_pipeline.py](/Users/hankchou/Documents/NTHU/2026_1/Text%20mining/TM%20workshop/TxM%20project%20data/n8n_python/analysis_pipeline.py)
- [job104_client.py](/Users/hankchou/Documents/NTHU/2026_1/Text%20mining/TM%20workshop/TxM%20project%20data/n8n_python/job104_client.py)
- [job104_fetcher.py](/Users/hankchou/Documents/NTHU/2026_1/Text%20mining/TM%20workshop/TxM%20project%20data/n8n_python/job104_fetcher.py)

## Resume Analysis Behavior

Resume processing was moved to the backend to avoid fragile PDF-processing nodes in n8n.

Current behavior:
- backend reads a sample resume from `resume/`
- if only one PDF is present, it will use that PDF automatically
- resume/job fit is based on `SBERT`
- visual outputs are generated from the backend and returned as images

Relevant outputs:
- `resume_fit.png`
- `cluster_map.png`
- `resume_job_matches.csv` inside zip
- `resume_profile.json` inside zip

## Current Output Attachments

The workflow is currently designed to send these four attachments:

1. `wordcloud.png`
2. `resume_fit.png`
3. `cluster_map.png`
4. `job_analysis_bundle.zip`

## Zip Bundle Contents

The backend zip bundle currently includes:

- `wordcloud.png`
- `resume_fit.png`
- `cluster_map.png`
- `top_tfidf_terms.csv`
- `job_embedding_projection.csv`
- `similar_job_pairs.csv`
- `cluster_summary.csv`
- `job_embeddings.jsonl`
- `resume_clean_text.txt`
- `resume_profile.json`
- `resume_job_matches.csv`
- `analysis_metadata.json`

## Word Cloud Cleaning / Stopwords Progress

The word cloud pipeline has been improved in two major ways:

### Company Name Removal
- company names are removed before TF-IDF/word cloud generation
- this prevents company names from dominating the visual

### Stopwords Expansion
The stopword list was expanded to remove:
- generic job-board boilerplate
- schedule/time wording
- application process wording
- noisy fragments from OCR or poorly segmented text
- some adjectives and low-signal descriptive terms

Examples of recently added stopwords:
- `內容`
- `事項`
- `注意`
- `期間`
- `時間`
- `履歷`
- `投遞`
- `感到`
- `擔心`
- `迷惘`
- `錯過`
- `落差`
- `一起`
- `支援`
- `工具`
- `流程`
- `文件`
- `跑啦`
- `qnity`

Special note:
- `word` was briefly added to stopwords, then removed again so `Word/PowerPoint/Excel`-related signals can still show up

## Major Progress Completed

### 1. 104 API Access
- direct `104` calls from n8n were blocked
- local proxy endpoint was added
- n8n now calls local Flask instead of calling `104` directly

### 2. Resume Processing
- attempted n8n PDF/file-node approach
- later simplified by moving resume processing to backend
- backend now auto-loads sample resume from `resume/`

### 3. Visual Attachments Outside Zip
- workflow was extended to generate:
  - standalone word cloud
  - standalone resume-fit visual
  - standalone cluster map
- Gmail now attaches those files directly instead of only sending a zip

### 4. Resume/Job Fit Analysis
- SBERT-based resume fit support was added
- resume/job matching results are included in both:
  - API responses
  - zip bundle

### 5. Word Cloud Cleanup
- company names removed
- stopwords expanded
- low-signal adjective/template words reduced

## Current Basic Settings

### Search / Crawl Settings
- keyword: `財務管理 會計`
- page range: `1` to `5`
- page size: `20`

### Google Sheet
- Spreadsheet in the local workflow:
  - `https://docs.google.com/spreadsheets/d/1aQbufqN5885icG8rlll5rmaoTr2c7maJnOv7KzkILo4/edit?usp=sharing`
- Tab:
  - `sheet1`

For a fresh GitHub import, replace this with your own Google Sheet and reconnect Google Sheets credentials.

### Local API Host
- `http://host.docker.internal:5001`

### Font
- local font file:
  - [NotoSansTC-VariableFont_wght.ttf](/Users/hankchou/Documents/NTHU/2026_1/Text%20mining/TM%20workshop/TxM%20project%20data/n8n_python/NotoSansTC-VariableFont_wght.ttf)

### Resume Folder
- [resume](/Users/hankchou/Documents/NTHU/2026_1/Text%20mining/TM%20workshop/TxM%20project%20data/n8n_python/resume)

## Known Caveats

- `104` keyword search is broad, so results may still contain jobs whose descriptions mention adjacent domains
- the `Filter` node currently only filters by internship wording in `jobName`
- the Gmail HTML message text has not yet been updated to fully describe all four attachments
- `Read/Write Files from Disk` exists but is not currently part of the active attachment flow

## Suggested Next Improvements

1. Update Gmail body so it explicitly mentions all four attachments.
2. Add stronger n8n filters for unwanted domains such as finance/accounting when needed.
3. Consider a second `Filter` layer for excluding terms in `jobName` or `description`.
4. Optionally split stopwords into:
   - conservative mode
   - aggressive mode
5. Remove or archive disconnected nodes once the workflow is stable.
