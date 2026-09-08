# -*- coding: utf-8 -*-
from flask import Flask, jsonify, request, send_file
import io
import os

from analysis_pipeline import (
    SBERT_MODEL_NAME,
    build_analysis_bundle,
    build_resume_fit_response,
    build_tfidf_artifacts,
    generate_cluster_map_png,
    generate_wordcloud_png,
    generate_resume_fit_png,
    load_sample_resume_profile,
    parse_jobs_payload,
    prepare_jobs_dataframe,
    build_embedding_artifacts,
    build_resume_match_artifacts,
)
from job104_client import error as job104_error
from job104_client import explain_forbidden, fetch_jobs


app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "NotoSansTC-VariableFont_wght.ttf")
RESUME_DIR = os.path.join(BASE_DIR, "resume")


@app.route("/health", methods=["GET"])
def health():
    return {
        "status": "ok",
        "sbert_model": SBERT_MODEL_NAME,
    }, 200


@app.route("/fetch-104-jobs", methods=["GET"])
def fetch_104_jobs():
    keyword = request.args.get("keyword", "資料科學")
    page = request.args.get("page", default=1, type=int)
    pagesize = request.args.get("pagesize", default=20, type=int)
    order = request.args.get("order", default="16")
    rostatus = request.args.get("rostatus", default="1024")
    cookie = request.headers.get("X-Job104-Cookie") or os.environ.get("JOB104_COOKIE")

    try:
        payload = fetch_jobs(
            keyword=keyword,
            page=page,
            pagesize=pagesize,
            order=order,
            rostatus=rostatus,
            cookie=cookie,
        )
        return jsonify(payload)
    except job104_error.HTTPError as exc:
        charset = exc.headers.get_content_charset() or "utf-8"
        body = exc.read().decode(charset, errors="replace")
        if exc.code == 403:
            return jsonify(
                {
                    "status": "error",
                    "message": explain_forbidden(exc.url, exc.headers, body),
                }
            ), 502
        return jsonify(
            {
                "status": "error",
                "message": f"104 returned HTTP {exc.code}",
                "body_preview": body[:800],
            }
        ), 502
    except job104_error.URLError as exc:
        return jsonify(
            {
                "status": "error",
                "message": f"Could not reach 104: {exc}",
            }
        ), 502


@app.route("/sample-resume-profile", methods=["GET"])
def sample_resume_profile():
    try:
        resume_filename = request.args.get("filename")
        resume_profile = load_sample_resume_profile(
            RESUME_DIR,
            filename=resume_filename,
            required=True,
        )
        return jsonify(
            {
                "status": "ok",
                "resume_filename": resume_profile["resume_filename"],
                "resume_path": resume_profile["resume_path"],
                "resume_text": resume_profile["clean_text"],
                "resume_raw_text": resume_profile["raw_text"],
                "resume_tokens": resume_profile["tokens"],
                "resume_token_count": resume_profile["token_count"],
                "resume_char_count": resume_profile["char_count"],
                "resume_preview": resume_profile["preview"],
            }
        )
    except Exception as exc:
        return _handle_api_error(exc)


@app.route("/analyze-resume-fit", methods=["POST"])
def analyze_resume_fit():
    try:
        raw_payload = request.get_json(silent=True)
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        jobs_data = parse_jobs_payload(raw_payload if raw_payload is not None else payload)
        df = prepare_jobs_dataframe(jobs_data)
        resume_filename = payload.get("resume_filename")
        top_k = int(payload.get("top_k", 10))
        resume_profile = load_sample_resume_profile(
            RESUME_DIR,
            filename=resume_filename,
            required=True,
        )
        response_payload = build_resume_fit_response(df, resume_profile, top_k=top_k)
        return jsonify(response_payload)
    except Exception as exc:
        return _handle_api_error(exc)


@app.route("/generate-resume-fit-visual", methods=["POST"])
def generate_resume_fit_visual():
    try:
        raw_payload = request.get_json(silent=True)
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        jobs_data = parse_jobs_payload(raw_payload if raw_payload is not None else payload)
        df = prepare_jobs_dataframe(jobs_data)
        resume_filename = payload.get("resume_filename")
        top_k = int(payload.get("top_k", 10))
        resume_profile = load_sample_resume_profile(
            RESUME_DIR,
            filename=resume_filename,
            required=True,
        )
        embedding_artifacts = build_embedding_artifacts(df)
        resume_artifacts = build_resume_match_artifacts(df, embedding_artifacts, resume_profile, top_k=top_k)
        image_bytes = generate_resume_fit_png(resume_artifacts, resume_profile, FONT_PATH)
        return send_file(
            io.BytesIO(image_bytes),
            mimetype="image/png",
            download_name="resume_fit.png",
        )
    except Exception as exc:
        return _handle_api_error(exc)


@app.route("/generate-cluster-map", methods=["POST"])
def generate_cluster_map():
    try:
        raw_payload = request.get_json(silent=True)
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        jobs_data = parse_jobs_payload(raw_payload if raw_payload is not None else payload)
        df = prepare_jobs_dataframe(jobs_data)
        resume_filename = payload.get("resume_filename")
        top_k = int(payload.get("top_k", 10))
        resume_profile = load_sample_resume_profile(
            RESUME_DIR,
            filename=resume_filename,
            required=True,
        )
        embedding_artifacts = build_embedding_artifacts(df)
        resume_artifacts = build_resume_match_artifacts(df, embedding_artifacts, resume_profile, top_k=top_k)
        image_bytes = generate_cluster_map_png(embedding_artifacts, resume_artifacts, resume_profile, FONT_PATH)
        return send_file(
            io.BytesIO(image_bytes),
            mimetype="image/png",
            download_name="cluster_map.png",
        )
    except Exception as exc:
        return _handle_api_error(exc)


@app.route("/generate-wordcloud", methods=["POST"])
def generate_wordcloud():
    try:
        print("\n--- 📥 Received request from n8n, starting TF-IDF wordcloud processing ---")
        payload = request.get_json(silent=True)
        jobs_data = parse_jobs_payload(payload)
        df = prepare_jobs_dataframe(jobs_data)

        tfidf_artifacts = build_tfidf_artifacts(df)
        top_terms = tfidf_artifacts["top_terms_df"].head(15).to_dict(orient="records")
        for term_info in top_terms:
            print(f"{term_info['term']}: {term_info['tfidf_score']:.4f}")

        image_bytes = generate_wordcloud_png(tfidf_artifacts["word_scores"], FONT_PATH)
        print("✅ Word cloud generated successfully. Returning PNG to n8n...")
        return send_file(
            io.BytesIO(image_bytes),
            mimetype="image/png",
            download_name="wordcloud.png",
        )
    except Exception as exc:
        return _handle_api_error(exc)


@app.route("/generate-analysis-bundle", methods=["POST"])
def generate_analysis_bundle():
    try:
        print("\n--- 📥 Received request from n8n, starting TF-IDF + SBERT bundle processing ---")
        raw_payload = request.get_json(silent=True)
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        jobs_data = parse_jobs_payload(raw_payload if raw_payload is not None else payload)
        df = prepare_jobs_dataframe(jobs_data)
        include_sample_resume = bool(payload.get("include_sample_resume", True))
        resume_filename = payload.get("resume_filename")
        resume_profile = None
        if include_sample_resume:
            resume_profile = load_sample_resume_profile(
                RESUME_DIR,
                filename=resume_filename,
                required=False,
            )

        analysis_result = build_analysis_bundle(df, FONT_PATH, resume_profile=resume_profile)
        print(
            "✅ Analysis bundle generated successfully. "
            f"Jobs: {analysis_result['metadata']['job_count']}, "
            f"Embedding dim: {analysis_result['metadata']['embedding_dimension']}, "
            f"Resume: {analysis_result['metadata'].get('resume_analysis', {}).get('resume_filename', 'none')}"
        )
        return send_file(
            io.BytesIO(analysis_result["bundle_bytes"]),
            mimetype="application/zip",
            download_name="job_analysis_bundle.zip",
        )
    except Exception as exc:
        return _handle_api_error(exc)


def _handle_api_error(exc):
    import traceback

    error_message = f"Error occurred: {exc}\n{traceback.format_exc()}"
    print(f"❌ {error_message}")
    return error_message, 500


if __name__ == "__main__":
    print("🚀 API Server starting... waiting for data from n8n... (Port: 5001)")
    app.run(host="0.0.0.0", port=5001)
