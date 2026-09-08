# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import Counter
from functools import lru_cache
import io
import json
import math
import os
from pathlib import Path
import re
import zipfile

from bs4 import BeautifulSoup
import jieba
import matplotlib
from matplotlib import font_manager
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from wordcloud import WordCloud


matplotlib.use("Agg")
import matplotlib.pyplot as plt


CUSTOM_WORDS = [
    "資料科學", "資料分析", "資料工程", "商業分析", "視覺化分析",
    "自然語言處理", "機器學習", "深度學習", "電腦視覺", "雲端運算",
    "PowerBI", "Tableau", "Python", "SQL", "Excel", "AutoCAD",
    "PyTorch", "TensorFlow", "scikitlearn", "NLP", "LLM",
    "Git", "Linux", "cpp", "ComputerVision", "MachineLearning", "DeepLearning",
]

STOPWORDS = {
    "的", "了", "與", "及", "並", "或", "在", "於", "對", "和", "等", "為", "將", "可", "者",
    "the", "to", "with", "of", "we", "have", "for", "in", "and",
    "歡迎", "加入", "具備", "條件", "尤佳", "相關", "工作", "能力", "經驗", "負責",
    "協助", "進行", "公司", "提供", "我們", "你", "你們", "實習", "實習生", "學生",
    # Common job-board boilerplate that adds noise to word clouds.
    "內容", "事項", "注意", "介紹", "對象", "配合", "需求", "條件",
    "其他", "一定", "以上", "不能", "擁有", "未來", "影響", "全球", "社會",
    # Schedule and application wording that is rarely useful as a skill signal.
    "期間", "時間", "日期", "小時", "中午", "上午", "下午", "月薪",
    "週一", "週二", "週三", "週四", "週五", "週六", "週日",
    "履歷", "投遞", "招募", "專區", "休息",
    # Frequently surfaced template fragments from job boards.
    "學用", "科系", "事項系統",
    # Adjectives / sentiment-like wording that is not useful for matching.
    "感到", "擔心", "迷惘", "錯過", "落差", "一起", "依照", "依據",
    "大四", "大三", "暑期", "員工", "作業", "支援", "資料", "需要",
    # Extra boilerplate and noisy fragments seen in recent word clouds.
    "核定", "事業", "領先", "工具", "計畫", "流程", "文件", "分析",
    "制合約", "應商", "跑啦", "不用",
    # OCR / parsing artifacts and low-signal English fragments.
    "is", "qnity",
}

TERM_REPLACEMENTS = {
    "Power BI": "PowerBI",
    "power bi": "PowerBI",
    "Machine Learning": "MachineLearning",
    "machine learning": "MachineLearning",
    "Deep Learning": "DeepLearning",
    "deep learning": "DeepLearning",
    "Natural Language Processing": "NLP",
    "natural language processing": "NLP",
    "Computer Vision": "ComputerVision",
    "computer vision": "ComputerVision",
    "scikit-learn": "scikitlearn",
    "C++": "cpp",
}

SBERT_MODEL_NAME = os.getenv("SBERT_MODEL_NAME", "paraphrase-multilingual-MiniLM-L12-v2")
COMPANY_SUFFIX_RE = re.compile(
    r"(股份有限公司|有限公司|公司|集團|企業|國際|科技|實業|商行|控股|顧問|管理|服務)$"
)


for word in CUSTOM_WORDS:
    jieba.add_word(word)


def parse_jobs_payload(payload):
    jobs_data = payload.get("jobs", []) if isinstance(payload, dict) and "jobs" in payload else payload
    if isinstance(jobs_data, dict) and "data" in jobs_data:
        jobs_data = jobs_data["data"]
    return jobs_data


def text_series(df, column_name):
    if column_name in df.columns:
        return df[column_name].fillna("").astype(str)
    return pd.Series("", index=df.index, dtype=str)


def parse_skill_text(value):
    if isinstance(value, list):
        return " ".join(
            item.get("description", "")
            for item in value
            if isinstance(item, dict) and item.get("description")
        )

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""

    try:
        if isinstance(value, str):
            value = value.replace("'", '"')
            items = json.loads(value)
            return " ".join(
                item.get("description", "")
                for item in items
                if isinstance(item, dict) and item.get("description")
            )
    except Exception:
        pass

    return str(value)


def clean_job_text(text):
    if pd.isna(text):
        return ""

    text = BeautifulSoup(str(text), "html.parser").get_text(" ")
    text = re.sub(r"http\S+|www\.\S+", " ", text)
    text = re.sub(r"\S+@\S+", " ", text)
    text = re.sub(r"Line\S*|LINE\S*|line\S*", " ", text)
    text = re.sub(r"\d{2,4}[-－]?\d{3,4}[-－]?\d{3,4}", " ", text)

    for source, target in TERM_REPLACEMENTS.items():
        text = text.replace(source, target)

    text = re.sub(r"[►➤➸☀★☆●■◆※◎▶▌▍▋┏┓┗┛━•]", " ", text)
    text = re.sub(r"[^\u4e00-\u9fffA-Za-z_+# ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def company_name_variants(company_name):
    if company_name is None or (isinstance(company_name, float) and pd.isna(company_name)):
        return []

    cleaned_name = clean_job_text(company_name)
    variants = set()
    for candidate in [str(company_name).strip(), cleaned_name, cleaned_name.replace(" ", "")]:
        candidate = candidate.strip()
        if len(candidate) < 2:
            continue
        variants.add(candidate)
        simplified = COMPANY_SUFFIX_RE.sub("", candidate).strip()
        if len(simplified) >= 2:
            variants.add(simplified)

    return sorted(variants, key=len, reverse=True)


def strip_company_name(clean_text, company_name):
    if not clean_text:
        return ""

    stripped_text = str(clean_text)
    for variant in company_name_variants(company_name):
        stripped_text = stripped_text.replace(variant, " ")

    return re.sub(r"\s+", " ", stripped_text).strip()


def extract_pdf_text(pdf_path):
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "pypdf is not installed. Please add it to the environment before using resume PDF features."
        ) from exc

    reader = PdfReader(str(pdf_path))
    page_texts = [(page.extract_text() or "") for page in reader.pages]
    combined_text = "\n".join(text for text in page_texts if text.strip()).strip()
    if not combined_text:
        raise ValueError(f"No extractable text found in PDF: {pdf_path}")
    return combined_text


def tokenize_job_text(text):
    tokens = []
    for token in jieba.cut(text, cut_all=False):
        token = token.strip()
        if not token or token in STOPWORDS:
            continue
        if len(token) == 1 and re.match(r"[\u4e00-\u9fff]", token):
            continue
        tokens.append(token)
    return tokens


def top_unique_tokens(tokens, limit=20):
    unique_tokens = []
    seen = set()
    for token in tokens:
        if token not in seen:
            seen.add(token)
            unique_tokens.append(token)
        if len(unique_tokens) >= limit:
            break
    return unique_tokens


def resolve_resume_pdf(resume_dir, filename=None):
    resume_dir_path = Path(resume_dir)
    if not resume_dir_path.exists():
        return None

    if filename:
        candidate_path = resume_dir_path / filename
        return candidate_path if candidate_path.exists() else None

    pdf_candidates = sorted(resume_dir_path.glob("*.pdf"))
    return pdf_candidates[0] if pdf_candidates else None


def load_sample_resume_profile(resume_dir, filename=None, required=False):
    pdf_path = resolve_resume_pdf(resume_dir, filename=filename)
    if pdf_path is None:
        if required:
            raise FileNotFoundError(
                f"No resume PDF found in {resume_dir}" + (f" for filename {filename}" if filename else "")
            )
        return None

    raw_text = extract_pdf_text(pdf_path)
    clean_text = clean_job_text(raw_text)
    tokens = tokenize_job_text(clean_text)
    return {
        "resume_filename": pdf_path.name,
        "resume_path": str(pdf_path),
        "raw_text": raw_text,
        "clean_text": clean_text,
        "tokens": tokens,
        "text_for_tfidf": " ".join(tokens),
        "token_count": int(len(tokens)),
        "char_count": int(len(clean_text)),
        "preview": clean_text[:240],
    }


def prepare_jobs_dataframe(jobs_data):
    df = pd.DataFrame(jobs_data)
    if df.empty:
        raise ValueError("No data received")

    df = df.copy()
    df["job_index"] = np.arange(len(df))
    df["company_name"] = text_series(df, "custName")
    df["pcSkills_text"] = df.get("pcSkills", pd.Series(dtype=str)).apply(parse_skill_text)
    df["lang_text"] = df.get("languageRequirements", pd.Series(dtype=str)).apply(parse_skill_text)

    df["analysis_text_raw"] = (
        text_series(df, "jobName") + " " +
        text_series(df, "description") + " " +
        df["pcSkills_text"].fillna("") + " " +
        df["pcSkills_text"].fillna("") + " " +
        df["lang_text"].fillna("")
    )

    description_series = text_series(df, "description")
    df["description_clean"] = description_series.apply(clean_job_text)
    df["analysis_text_clean_base"] = df["analysis_text_raw"].apply(clean_job_text)
    df["clean_text"] = df.apply(
        lambda row: strip_company_name(row["analysis_text_clean_base"], row["company_name"]),
        axis=1,
    )
    df["embedding_text"] = df["description_clean"].where(
        df["description_clean"].str.len() > 0,
        df["analysis_text_clean_base"],
    )
    df["tokens"] = df["clean_text"].apply(tokenize_job_text)
    df["text_for_tfidf"] = df["tokens"].apply(lambda tokens: " ".join(tokens))
    return df


def build_tfidf_artifacts(df):
    document_count = len(df)
    min_df = 2 if document_count >= 5 else 1
    max_df = 0.95 if document_count >= 5 else 1.0

    vectorizer = TfidfVectorizer(
        max_features=500,
        ngram_range=(1, 2),
        min_df=min_df,
        max_df=max_df,
    )

    tfidf_matrix = vectorizer.fit_transform(df["text_for_tfidf"])
    feature_names = vectorizer.get_feature_names_out()
    tfidf_sum_scores = np.asarray(tfidf_matrix.sum(axis=0)).ravel()

    if len(feature_names) == 0:
        raise ValueError("TF-IDF could not extract any terms. Please check the input job descriptions.")

    word_scores = dict(zip(feature_names, tfidf_sum_scores))
    top_terms_df = pd.DataFrame(
        sorted(word_scores.items(), key=lambda item: item[1], reverse=True),
        columns=["term", "tfidf_score"],
    )

    return {
        "vectorizer": vectorizer,
        "tfidf_matrix": tfidf_matrix,
        "word_scores": word_scores,
        "top_terms_df": top_terms_df,
    }


def generate_wordcloud_png(word_scores, font_path):
    if not os.path.exists(font_path):
        raise FileNotFoundError(f"Font file not found: {font_path}")

    wordcloud = WordCloud(
        font_path=font_path,
        width=1200,
        height=600,
        background_color="white",
        colormap="ocean",
        max_words=100,
    )
    wordcloud.generate_from_frequencies(word_scores)

    plt.figure(figsize=(12, 6))
    plt.imshow(wordcloud, interpolation="bilinear")
    plt.axis("off")
    plt.tight_layout()

    image_buffer = io.BytesIO()
    plt.savefig(image_buffer, format="png", dpi=300)
    image_buffer.seek(0)
    plt.close()
    return image_buffer.getvalue()


def build_font_properties(font_path, size=12):
    if not os.path.exists(font_path):
        raise FileNotFoundError(f"Font file not found: {font_path}")
    return font_manager.FontProperties(fname=font_path, size=size)


def shorten_label(text, limit=36):
    text = str(text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


@lru_cache(maxsize=1)
def get_sbert_model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is not installed. Please add it to the environment before using SBERT features."
        ) from exc

    return SentenceTransformer(SBERT_MODEL_NAME)


def choose_cluster_count(job_count):
    if job_count < 4:
        return 1
    return min(6, max(2, int(math.sqrt(job_count))))


def project_embeddings(embeddings):
    if len(embeddings) == 1:
        return np.zeros((1, 2)), None

    pca = PCA(n_components=2, random_state=42)
    return pca.fit_transform(embeddings), pca


def build_similarity_pairs(df, similarity_matrix, top_k=10):
    pair_rows = []
    row_indices, col_indices = np.triu_indices(len(df), k=1)

    for left_idx, right_idx in zip(row_indices, col_indices):
        pair_rows.append({
            "job_index_a": int(df.iloc[left_idx]["job_index"]),
            "jobName_a": df.iloc[left_idx].get("jobName", ""),
            "company_a": df.iloc[left_idx].get("company", ""),
            "job_index_b": int(df.iloc[right_idx]["job_index"]),
            "jobName_b": df.iloc[right_idx].get("jobName", ""),
            "company_b": df.iloc[right_idx].get("company", ""),
            "cosine_similarity": float(similarity_matrix[left_idx, right_idx]),
        })

    if not pair_rows:
        return pd.DataFrame(columns=[
            "rank", "job_index_a", "jobName_a", "company_a",
            "job_index_b", "jobName_b", "company_b", "cosine_similarity",
        ])

    pair_df = pd.DataFrame(pair_rows).sort_values("cosine_similarity", ascending=False).head(top_k).reset_index(drop=True)
    pair_df.insert(0, "rank", np.arange(1, len(pair_df) + 1))
    return pair_df


def build_cluster_summary(df, cluster_labels):
    rows = []
    cluster_sizes = pd.Series(cluster_labels).value_counts().sort_index()

    for cluster_id in sorted(cluster_sizes.index):
        cluster_mask = cluster_labels == cluster_id
        cluster_jobs = df.loc[cluster_mask]
        token_counter = Counter()
        for tokens in cluster_jobs["tokens"]:
            token_counter.update(tokens)

        rows.append({
            "cluster_id": int(cluster_id),
            "cluster_size": int(cluster_sizes[cluster_id]),
            "top_keywords": ", ".join(term for term, _ in token_counter.most_common(10)),
            "sample_job_names": " | ".join(text_series(cluster_jobs, "jobName").head(3).tolist()),
            "sample_companies": " | ".join(text_series(cluster_jobs, "company").head(3).tolist()),
        })

    return pd.DataFrame(rows)


def build_embedding_artifacts(df):
    model = get_sbert_model()
    texts = df["embedding_text"].fillna("").astype(str).tolist()
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False, normalize_embeddings=False)

    if embeddings.ndim == 1:
        embeddings = embeddings.reshape(1, -1)

    norms = np.linalg.norm(embeddings, axis=1)
    normalized = embeddings / np.clip(norms[:, None], 1e-12, None)
    similarity_matrix = cosine_similarity(normalized)
    projection, projection_model = project_embeddings(embeddings)

    cluster_count = choose_cluster_count(len(df))
    if cluster_count == 1:
        cluster_labels = np.zeros(len(df), dtype=int)
    else:
        cluster_labels = KMeans(n_clusters=cluster_count, n_init=10, random_state=42).fit_predict(embeddings)

    cluster_sizes = pd.Series(cluster_labels).value_counts()
    projection_df = pd.DataFrame({
        "job_index": df["job_index"].astype(int),
        "appearDate": text_series(df, "appearDate"),
        "company": text_series(df, "company"),
        "jobName": text_series(df, "jobName"),
        "cluster_id": cluster_labels.astype(int),
        "cluster_size": [int(cluster_sizes[label]) for label in cluster_labels],
        "embedding_norm": norms,
        "pca_x": projection[:, 0],
        "pca_y": projection[:, 1],
        "description_preview": df["embedding_text"].str.slice(0, 160),
    })

    raw_records = []
    for _, row in projection_df.iterrows():
        record_df = df.loc[df["job_index"] == row["job_index"]].iloc[0]
        embedding_vector = embeddings[int(row["job_index"])].tolist()
        raw_records.append({
            "job_index": int(row["job_index"]),
            "appearDate": str(record_df.get("appearDate", "")),
            "company": str(record_df.get("company", "")),
            "jobName": str(record_df.get("jobName", "")),
            "cluster_id": int(row["cluster_id"]),
            "embedding_dimension": int(embeddings.shape[1]),
            "embedding_text": str(record_df.get("embedding_text", "")),
            "embedding": [float(value) for value in embedding_vector],
        })

    return {
        "model_name": SBERT_MODEL_NAME,
        "embedding_dimension": int(embeddings.shape[1]),
        "embeddings": embeddings,
        "normalized_embeddings": normalized,
        "projection_model": projection_model,
        "projection_df": projection_df,
        "similarity_df": build_similarity_pairs(df, similarity_matrix),
        "cluster_df": build_cluster_summary(df, cluster_labels),
        "raw_records": raw_records,
    }


def build_resume_match_artifacts(df, embedding_artifacts, resume_profile, top_k=15):
    model = get_sbert_model()
    resume_vector = model.encode(
        [resume_profile["clean_text"]],
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=False,
    )
    if resume_vector.ndim == 1:
        resume_vector = resume_vector.reshape(1, -1)

    resume_norm = np.linalg.norm(resume_vector, axis=1)
    normalized_resume = resume_vector / np.clip(resume_norm[:, None], 1e-12, None)
    scores = cosine_similarity(normalized_resume, embedding_artifacts["normalized_embeddings"]).ravel()
    projection_df = embedding_artifacts["projection_df"].set_index("job_index")
    projection_model = embedding_artifacts.get("projection_model")
    if projection_model is None:
        resume_projection = np.zeros((1, 2))
    else:
        resume_projection = projection_model.transform(resume_vector)

    rows = []
    resume_token_set = set(resume_profile["tokens"])
    for row_number, score in enumerate(scores):
        job_row = df.iloc[row_number]
        projection_row = projection_df.loc[int(job_row["job_index"])]
        job_tokens = job_row.get("tokens", [])
        overlap_tokens = [token for token in top_unique_tokens(job_tokens, limit=50) if token in resume_token_set]
        missing_resume_tokens = [
            token for token in top_unique_tokens(resume_profile["tokens"], limit=50)
            if token not in set(job_tokens)
        ]
        rows.append({
            "job_index": int(job_row["job_index"]),
            "appearDate": str(job_row.get("appearDate", "")),
            "company": str(job_row.get("company", "")),
            "jobName": str(job_row.get("jobName", "")),
            "cluster_id": int(projection_row["cluster_id"]),
            "cluster_size": int(projection_row["cluster_size"]),
            "resume_job_similarity": float(score),
            "match_score_pct": round(float(score) * 100, 2),
            "matched_keywords": overlap_tokens[:12],
            "matched_keyword_count": int(len(overlap_tokens)),
            "resume_keywords_not_seen_in_job": missing_resume_tokens[:12],
            "job_description_preview": str(job_row.get("embedding_text", ""))[:160],
        })

    match_df = pd.DataFrame(rows).sort_values(
        "resume_job_similarity",
        ascending=False,
    ).head(top_k).reset_index(drop=True)
    match_df.insert(0, "rank", np.arange(1, len(match_df) + 1))

    return {
        "model_name": SBERT_MODEL_NAME,
        "resume_embedding_dimension": int(resume_vector.shape[1]),
        "resume_embedding_norm": float(resume_norm[0]),
        "resume_projection": {
            "pca_x": float(resume_projection[0, 0]),
            "pca_y": float(resume_projection[0, 1]),
        },
        "match_df": match_df,
    }


def generate_resume_fit_png(resume_artifacts, resume_profile, font_path):
    match_df = resume_artifacts["match_df"].head(10).iloc[::-1].reset_index(drop=True)
    if match_df.empty:
        raise ValueError("No resume-job match data available for visualization.")

    font_prop = build_font_properties(font_path, size=10)
    title_prop = build_font_properties(font_path, size=16)
    label_prop = build_font_properties(font_path, size=11)

    labels = [
        shorten_label(f"{row['company']} | {row['jobName']}", limit=40)
        for _, row in match_df.iterrows()
    ]
    scores = match_df["match_score_pct"].astype(float).tolist()
    cluster_ids = match_df["cluster_id"].astype(int).tolist()
    unique_clusters = sorted(set(cluster_ids))
    color_map = plt.cm.get_cmap("tab10", max(3, len(unique_clusters)))
    cluster_color_lookup = {
        cluster_id: color_map(index % color_map.N)
        for index, cluster_id in enumerate(unique_clusters)
    }
    bar_colors = [cluster_color_lookup[cluster_id] for cluster_id in cluster_ids]

    fig, ax = plt.subplots(figsize=(13, 7.5))
    y_positions = np.arange(len(match_df))
    bars = ax.barh(y_positions, scores, color=bar_colors, alpha=0.9)

    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels, fontproperties=font_prop)
    ax.set_xlim(0, max(100, max(scores) + 12))
    ax.set_xlabel("Resume-job SBERT match score (%)", fontproperties=label_prop)
    ax.set_title(
        f"Top Resume Matches | {resume_profile['resume_filename']}",
        fontproperties=title_prop,
        pad=18,
    )
    ax.grid(axis="x", linestyle="--", alpha=0.25)
    ax.set_axisbelow(True)

    for bar, (_, row) in zip(bars, match_df.iterrows()):
        ax.text(
            bar.get_width() + 1.2,
            bar.get_y() + bar.get_height() / 2,
            f"{row['match_score_pct']:.1f}% | " + ", ".join(row["matched_keywords"][:4]),
            va="center",
            fontproperties=font_prop,
            fontsize=9,
        )

    legend_handles = [
        plt.Line2D([0], [0], color=cluster_color_lookup[cluster_id], lw=8, label=f"Cluster {cluster_id}")
        for cluster_id in unique_clusters
    ]
    ax.legend(handles=legend_handles, loc="lower right", frameon=False, prop=font_prop)

    fig.text(
        0.02,
        0.02,
        "Matched keywords highlight direct overlap between the resume and the job description / skills.",
        fontproperties=font_prop,
        fontsize=9,
        alpha=0.8,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))

    image_buffer = io.BytesIO()
    fig.savefig(image_buffer, format="png", dpi=220, bbox_inches="tight")
    image_buffer.seek(0)
    plt.close(fig)
    return image_buffer.getvalue()


def generate_cluster_map_png(embedding_artifacts, resume_artifacts, resume_profile, font_path):
    projection_df = embedding_artifacts["projection_df"].copy()
    if projection_df.empty:
        raise ValueError("No projection data available for visualization.")

    font_prop = build_font_properties(font_path, size=10)
    title_prop = build_font_properties(font_path, size=16)
    label_prop = build_font_properties(font_path, size=11)

    unique_clusters = sorted(projection_df["cluster_id"].astype(int).unique().tolist())
    color_map = plt.cm.get_cmap("tab10", max(3, len(unique_clusters)))
    cluster_color_lookup = {
        cluster_id: color_map(index % color_map.N)
        for index, cluster_id in enumerate(unique_clusters)
    }

    fig, ax = plt.subplots(figsize=(11.5, 8))
    for cluster_id in unique_clusters:
        cluster_df = projection_df.loc[projection_df["cluster_id"] == cluster_id]
        ax.scatter(
            cluster_df["pca_x"],
            cluster_df["pca_y"],
            s=90,
            alpha=0.78,
            color=cluster_color_lookup[cluster_id],
            label=f"Cluster {cluster_id}",
        )

    top_matches = resume_artifacts["match_df"].head(5)
    top_indices = set(top_matches["job_index"].astype(int).tolist())
    for _, row in projection_df.iterrows():
        if int(row["job_index"]) not in top_indices:
            continue
        ax.scatter(
            [row["pca_x"]],
            [row["pca_y"]],
            s=190,
            facecolors="none",
            edgecolors="black",
            linewidths=1.8,
        )
        ax.text(
            row["pca_x"] + 0.02,
            row["pca_y"] + 0.02,
            shorten_label(row["jobName"], limit=22),
            fontproperties=font_prop,
            fontsize=9,
        )

    resume_point = resume_artifacts["resume_projection"]
    ax.scatter(
        [resume_point["pca_x"]],
        [resume_point["pca_y"]],
        marker="*",
        s=520,
        color="#d62828",
        edgecolors="black",
        linewidths=1.2,
        label="Resume",
        zorder=5,
    )
    ax.text(
        resume_point["pca_x"] + 0.03,
        resume_point["pca_y"] + 0.03,
        shorten_label(resume_profile["resume_filename"], limit=24),
        fontproperties=font_prop,
        fontsize=10,
        color="#7f0000",
    )

    ax.set_title(
        "Job Cluster Map with Resume Position",
        fontproperties=title_prop,
        pad=16,
    )
    ax.set_xlabel("PCA axis 1", fontproperties=label_prop)
    ax.set_ylabel("PCA axis 2", fontproperties=label_prop)
    ax.grid(linestyle="--", alpha=0.18)
    ax.legend(frameon=False, prop=font_prop, loc="best")

    fig.text(
        0.02,
        0.02,
        "Each dot is a job posting in SBERT semantic space. The star marks the resume; black-ringed points are the top matches.",
        fontproperties=font_prop,
        fontsize=9,
        alpha=0.82,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))

    image_buffer = io.BytesIO()
    fig.savefig(image_buffer, format="png", dpi=220, bbox_inches="tight")
    image_buffer.seek(0)
    plt.close(fig)
    return image_buffer.getvalue()


def build_resume_fit_response(df, resume_profile, top_k=10):
    embedding_artifacts = build_embedding_artifacts(df)
    resume_artifacts = build_resume_match_artifacts(
        df,
        embedding_artifacts,
        resume_profile,
        top_k=top_k,
    )
    match_records = resume_artifacts["match_df"].to_dict(orient="records")
    return {
        "status": "ok",
        "resume_filename": resume_profile["resume_filename"],
        "resume_preview": resume_profile["preview"],
        "resume_token_count": resume_profile["token_count"],
        "job_count": int(len(df)),
        "sbert_model": resume_artifacts["model_name"],
        "top_matches": match_records,
    }


def build_analysis_metadata(df, top_terms_df, embedding_artifacts, resume_profile=None, resume_artifacts=None):
    top_terms_preview = top_terms_df.head(15).to_dict(orient="records")
    metadata = {
        "job_count": int(len(df)),
        "sbert_model": embedding_artifacts["model_name"],
        "embedding_dimension": embedding_artifacts["embedding_dimension"],
        "cluster_count": int(embedding_artifacts["cluster_df"]["cluster_id"].nunique()) if not embedding_artifacts["cluster_df"].empty else 0,
        "generated_outputs": [
            "wordcloud.png",
            "top_tfidf_terms.csv",
            "job_embedding_projection.csv",
            "similar_job_pairs.csv",
            "cluster_summary.csv",
            "job_embeddings.jsonl",
            "analysis_metadata.json",
        ],
        "top_tfidf_terms_preview": top_terms_preview,
    }
    if resume_profile and resume_artifacts:
        metadata["resume_analysis"] = {
            "resume_filename": resume_profile["resume_filename"],
            "resume_char_count": resume_profile["char_count"],
            "resume_token_count": resume_profile["token_count"],
            "resume_text_preview": resume_profile["preview"],
            "resume_embedding_dimension": resume_artifacts["resume_embedding_dimension"],
            "top_resume_match_preview": resume_artifacts["match_df"].head(5).to_dict(orient="records"),
        }
        metadata["generated_outputs"].extend([
            "resume_clean_text.txt",
            "resume_profile.json",
            "resume_job_matches.csv",
            "resume_fit.png",
            "cluster_map.png",
        ])
    return metadata


def build_analysis_bundle(df, font_path, resume_profile=None):
    tfidf_artifacts = build_tfidf_artifacts(df)
    wordcloud_png = generate_wordcloud_png(tfidf_artifacts["word_scores"], font_path)
    embedding_artifacts = build_embedding_artifacts(df)
    resume_artifacts = None
    resume_fit_png = None
    cluster_map_png = None
    if resume_profile:
        resume_artifacts = build_resume_match_artifacts(df, embedding_artifacts, resume_profile)
        resume_fit_png = generate_resume_fit_png(resume_artifacts, resume_profile, font_path)
        cluster_map_png = generate_cluster_map_png(embedding_artifacts, resume_artifacts, resume_profile, font_path)
    metadata = build_analysis_metadata(
        df,
        tfidf_artifacts["top_terms_df"],
        embedding_artifacts,
        resume_profile=resume_profile,
        resume_artifacts=resume_artifacts,
    )

    bundle_buffer = io.BytesIO()
    with zipfile.ZipFile(bundle_buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("wordcloud.png", wordcloud_png)
        bundle.writestr(
            "top_tfidf_terms.csv",
            tfidf_artifacts["top_terms_df"].to_csv(index=False, encoding="utf-8-sig"),
        )
        bundle.writestr(
            "job_embedding_projection.csv",
            embedding_artifacts["projection_df"].to_csv(index=False, encoding="utf-8-sig"),
        )
        bundle.writestr(
            "similar_job_pairs.csv",
            embedding_artifacts["similarity_df"].to_csv(index=False, encoding="utf-8-sig"),
        )
        bundle.writestr(
            "cluster_summary.csv",
            embedding_artifacts["cluster_df"].to_csv(index=False, encoding="utf-8-sig"),
        )

        jsonl_lines = [json.dumps(record, ensure_ascii=False) for record in embedding_artifacts["raw_records"]]
        bundle.writestr("job_embeddings.jsonl", "\n".join(jsonl_lines))
        bundle.writestr(
            "analysis_metadata.json",
            json.dumps(metadata, ensure_ascii=False, indent=2),
        )
        if resume_profile and resume_artifacts:
            bundle.writestr("resume_clean_text.txt", resume_profile["clean_text"])
            bundle.writestr(
                "resume_profile.json",
                json.dumps(
                    {
                        "resume_filename": resume_profile["resume_filename"],
                        "resume_path": resume_profile["resume_path"],
                        "raw_text": resume_profile["raw_text"],
                        "clean_text": resume_profile["clean_text"],
                        "tokens": resume_profile["tokens"],
                        "token_count": resume_profile["token_count"],
                        "char_count": resume_profile["char_count"],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            bundle.writestr(
                "resume_job_matches.csv",
                resume_artifacts["match_df"].to_csv(index=False, encoding="utf-8-sig"),
            )
            bundle.writestr("resume_fit.png", resume_fit_png)
            bundle.writestr("cluster_map.png", cluster_map_png)

    bundle_buffer.seek(0)
    return {
        "bundle_bytes": bundle_buffer.getvalue(),
        "wordcloud_png": wordcloud_png,
        "tfidf_artifacts": tfidf_artifacts,
        "embedding_artifacts": embedding_artifacts,
        "resume_profile": resume_profile,
        "resume_artifacts": resume_artifacts,
        "resume_fit_png": resume_fit_png,
        "cluster_map_png": cluster_map_png,
        "metadata": metadata,
    }
