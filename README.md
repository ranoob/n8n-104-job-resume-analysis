# 104 Job Market Resume Analysis Workflow

This project combines an `n8n` workflow with a local Flask backend to fetch job postings from 104, analyze job text, compare postings against a sample resume, and send the final visual report by email.

## What It Does

- Fetches 104 job search results through a local proxy API.
- Filters internship-related postings in n8n.
- Writes filtered jobs into Google Sheets.
- Generates a TF-IDF word cloud from job descriptions.
- Uses SBERT embeddings to compare a resume with fetched jobs.
- Produces a resume-fit chart and job cluster map.
- Sends `wordcloud.png`, `resume_fit.png`, `cluster_map.png`, and `job_analysis_bundle.zip` through Gmail.

## Main Files

- `api_server.py`: Flask API used by n8n.
- `analysis_pipeline.py`: text cleaning, TF-IDF, word cloud, SBERT matching, clustering, and zip generation.
- `job104_client.py`: shared 104 search client.
- `job104_fetcher.py`: CLI helper for testing the 104 fetch step.
- `docker-compose.yml`: local Docker setup for n8n and the analysis API.
- `Dockerfile`: runtime image with n8n, Python, and analysis dependencies.
- `tm_final_workflow_EfIzfI0p7tneeCkS.json`: exported n8n workflow.
- `n8n_workflow_handover.md`: detailed workflow handover notes.
- `104_scraping_notes.md`: notes about 104 API access and Cloudflare behavior.

## Local Setup

Start the services:

```bash
docker compose up -d --build
```

Open n8n:

```text
http://localhost:5678
```

The Flask API is exposed at:

```text
http://localhost:5001
```

Inside n8n Docker nodes, use:

```text
http://host.docker.internal:5001
```

## Backend Endpoints

- `GET /health`
- `GET /fetch-104-jobs`
- `GET /sample-resume-profile`
- `POST /generate-wordcloud`
- `POST /generate-resume-fit-visual`
- `POST /generate-cluster-map`
- `POST /generate-analysis-bundle`
- `POST /analyze-resume-fit`

## n8n Workflow

Current main flow:

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

The exported workflow JSON can be imported into n8n:

```text
tm_final_workflow_EfIzfI0p7tneeCkS.json
```

After importing, update credentials for:

- Google Sheets
- Gmail

Also replace the placeholder recipient email and Google Sheet destination with your own values.

## Resume Files

The backend looks for a sample resume PDF in `resume/`.

Personal resume PDFs are intentionally ignored by Git. Add your own PDF locally before running resume matching.

## Outputs

The email attachments are:

- `wordcloud.png`
- `resume_fit.png`
- `cluster_map.png`
- `job_analysis_bundle.zip`

The zip bundle includes:

- image outputs
- TF-IDF terms
- SBERT embeddings
- similar job pairs
- cluster summary
- resume/job match scores
- metadata

## Notes

104 may reject server-like requests with Cloudflare protection. This project routes n8n through a local Python proxy that mimics the browser request shape more reliably.
