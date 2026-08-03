from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="기사 탐색", page_icon="📄", layout="wide")
BASE_DIR = Path(__file__).resolve().parents[1]

@st.cache_data(ttl=300)
def load_articles():
    df = pd.read_csv(BASE_DIR / "data" / "articles.csv", dtype=str).fillna("")
    df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce", utc=True).dt.tz_convert("Asia/Seoul")
    df["relevance_score"] = pd.to_numeric(df["relevance_score"], errors="coerce").fillna(0).astype(int)
    return df

df = load_articles()
st.title("기사 탐색 및 검토")

keyword = st.text_input("제목·요약 검색")
col1, col2, col3 = st.columns(3)
with col1:
    professors = st.multiselect("교수", sorted(df["professor_name"].unique()))
with col2:
    statuses = st.multiselect("검토 상태", sorted(df["review_status"].unique()), default=[x for x in ["관련", "검토 필요"] if x in df["review_status"].unique()])
with col3:
    min_score = st.slider("최소 관련도", 0, 100, 45)

filtered = df[df["relevance_score"] >= min_score].copy()
if keyword:
    filtered = filtered[(filtered["title"] + " " + filtered["summary"]).str.contains(keyword, case=False, na=False)]
if professors:
    filtered = filtered[filtered["professor_name"].isin(professors)]
if statuses:
    filtered = filtered[filtered["review_status"].isin(statuses)]

st.write(f"검색 결과: {len(filtered):,}건")
filtered = filtered.sort_values("published_at", ascending=False)
filtered["게시일"] = filtered["published_at"].dt.strftime("%Y-%m-%d %H:%M")
st.dataframe(
    filtered[["게시일", "professor_name", "publisher", "title", "mention_type", "topic", "relevance_score", "review_status", "url"]],
    hide_index=True,
    use_container_width=True,
    column_config={"url": st.column_config.LinkColumn("원문"), "relevance_score": st.column_config.ProgressColumn("관련도", min_value=0, max_value=100)},
)

st.download_button("검색 결과 CSV 다운로드", filtered.to_csv(index=False, encoding="utf-8-sig"), file_name="media_search_results.csv", mime="text/csv")
