from pathlib import Path
import re

import pandas as pd
import streamlit as st

st.set_page_config(page_title="기사 탐색", page_icon="📄", layout="wide")
BASE_DIR = Path(__file__).resolve().parents[1]

ARTICLE_COLUMNS = [
    "article_id", "canonical_key", "professor_name", "published_at", "collected_at",
    "title", "summary", "body", "publisher", "url", "final_url", "search_query", "source",
    "body_status", "body_char_count", "mention_type", "topic", "relevance_score", "review_status", "media_weight",
]

def load_articles_file(path):
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
    for col in ARTICLE_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[ARTICLE_COLUMNS]

@st.cache_data(ttl=300)
def load_articles():
    df = load_articles_file(BASE_DIR / "data" / "articles.csv")
    df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce", utc=True).dt.tz_convert("Asia/Seoul")
    df["relevance_score"] = pd.to_numeric(df["relevance_score"], errors="coerce").fillna(0).astype(int)
    df["body_char_count"] = pd.to_numeric(df["body_char_count"], errors="coerce").fillna(0).astype(int)
    return df

df = load_articles()
st.title("기사 탐색")
if df.empty:
    st.info("수집된 기사가 없습니다.")
    st.stop()
keyword = st.text_input("제목·요약·본문 검색")
cols = st.columns(4)
with cols[0]: professors = st.multiselect("교수", sorted(df["professor_name"].unique()))
with cols[1]: publishers = st.multiselect("언론사", sorted(df["publisher"].unique()))
with cols[2]: types = st.multiselect("기사 유형", sorted(df["mention_type"].unique()))
with cols[3]: statuses = st.multiselect("검토 상태", sorted(df["review_status"].unique()), default=[x for x in ["관련", "검토 필요"] if x in df["review_status"].unique()])
min_score = st.slider("최소 관련도", 0, 100, 45)
filtered = df[df["relevance_score"] >= min_score].copy()
if keyword: filtered = filtered[(filtered["title"].fillna("") + " " + filtered["summary"].fillna("") + " " + filtered["body"].fillna("")).str.contains(re.escape(keyword), case=False, na=False)]
if professors: filtered = filtered[filtered["professor_name"].isin(professors)]
if publishers: filtered = filtered[filtered["publisher"].isin(publishers)]
if types: filtered = filtered[filtered["mention_type"].isin(types)]
if statuses: filtered = filtered[filtered["review_status"].isin(statuses)]
st.write(f"검색 결과: {len(filtered):,}행 · 원문 기준 {filtered['canonical_key'].nunique():,}건")
filtered = filtered.sort_values("published_at", ascending=False)
filtered["게시일"] = filtered["published_at"].dt.strftime("%Y-%m-%d %H:%M")
filtered["본문 미리보기"] = filtered["body"].str.slice(0, 250)
st.dataframe(filtered[["게시일", "professor_name", "publisher", "title", "mention_type", "topic", "body_status", "body_char_count", "본문 미리보기", "relevance_score", "review_status", "source", "final_url"]], hide_index=True, use_container_width=True, column_config={"professor_name": "교수", "publisher": "언론사", "title": "기사 제목", "mention_type": "유형", "topic": "주제", "relevance_score": st.column_config.ProgressColumn("관련도", min_value=0, max_value=100), "review_status": "검토 상태", "body_status": "본문 상태", "body_char_count": "본문 글자 수", "본문 미리보기": "본문 미리보기", "source": "수집 출처", "final_url": st.column_config.LinkColumn("원문")})
st.download_button("검색 결과 CSV 다운로드", filtered.to_csv(index=False, encoding="utf-8-sig"), file_name="media_search_results.csv", mime="text/csv")
