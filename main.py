from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="서울대 행정대학원 언론 모니터링", page_icon="📰", layout="wide")
BASE_DIR = Path(__file__).resolve().parent

@st.cache_data(ttl=300)
def load_data():
    professors = pd.read_csv(BASE_DIR / "data" / "professors.csv", dtype=str).fillna("")
    articles = pd.read_csv(BASE_DIR / "data" / "articles.csv", dtype=str).fillna("")
    articles["published_at"] = pd.to_datetime(articles["published_at"], errors="coerce", utc=True).dt.tz_convert("Asia/Seoul")
    articles["relevance_score"] = pd.to_numeric(articles["relevance_score"], errors="coerce").fillna(0)
    return professors, articles

professors, articles = load_data()
st.title("서울대학교 행정대학원 언론 모니터링")
st.caption("Google 뉴스 RSS 기반 시범 대시보드 · 제목과 RSS 요약을 중심으로 분석")

if articles.empty:
    st.warning("수집된 기사가 없습니다. 로컬에서 `python collect_news.py`를 실행하거나 GitHub Actions를 수동 실행하십시오.")
    st.stop()

min_date = articles["published_at"].min().date()
max_date = articles["published_at"].max().date()
with st.sidebar:
    st.header("필터")
    date_range = st.date_input("기간", value=(max(min_date, max_date - pd.Timedelta(days=29)), max_date), min_value=min_date, max_value=max_date)
    selected_professors = st.multiselect("교수", professors["name"].tolist())
    selected_types = st.multiselect("기사 유형", sorted(articles["mention_type"].dropna().unique()))
    selected_topics = st.multiselect("주제", sorted(articles["topic"].dropna().unique()))
    include_review = st.checkbox("검토 필요 포함", value=False)

start_date, end_date = date_range if isinstance(date_range, tuple) and len(date_range) == 2 else (date_range, date_range)
filtered = articles[
    articles["published_at"].dt.date.between(start_date, end_date)
].copy()
filtered = filtered[filtered["review_status"].isin(["관련", "검토 필요"] if include_review else ["관련"])]
if selected_professors:
    filtered = filtered[filtered["professor_name"].isin(selected_professors)]
if selected_types:
    filtered = filtered[filtered["mention_type"].isin(selected_types)]
if selected_topics:
    filtered = filtered[filtered["topic"].isin(selected_topics)]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("기사 수", f"{len(filtered):,}")
c2.metric("노출 교수", f"{filtered['professor_name'].nunique():,}")
c3.metric("언론사", f"{filtered['publisher'].nunique():,}")
c4.metric("인터뷰·기고", f"{filtered['mention_type'].isin(['인터뷰', '기고·칼럼']).sum():,}")
c5.metric("오늘 신규", f"{(filtered['collected_at'].str[:10] == pd.Timestamp.now(tz='Asia/Seoul').strftime('%Y-%m-%d')).sum():,}")

left, right = st.columns([1.6, 1])
with left:
    st.subheader("일별 기사 추이")
    daily = filtered.assign(date=filtered["published_at"].dt.date).groupby("date").size().reset_index(name="기사 수")
    st.plotly_chart(px.line(daily, x="date", y="기사 수", markers=True), use_container_width=True)
with right:
    st.subheader("기사 유형")
    types = filtered["mention_type"].value_counts().reset_index()
    types.columns = ["기사 유형", "기사 수"]
    st.plotly_chart(px.bar(types, x="기사 수", y="기사 유형", orientation="h"), use_container_width=True)

left, right = st.columns(2)
with left:
    st.subheader("교수별 기사 수")
    ranking = filtered["professor_name"].value_counts().head(15).sort_values().reset_index()
    ranking.columns = ["교수", "기사 수"]
    st.plotly_chart(px.bar(ranking, x="기사 수", y="교수", orientation="h"), use_container_width=True)
with right:
    st.subheader("주제별 기사 수")
    topics = filtered["topic"].value_counts().reset_index()
    topics.columns = ["주제", "기사 수"]
    st.plotly_chart(px.bar(topics, x="기사 수", y="주제", orientation="h"), use_container_width=True)

st.subheader("최근 기사")
view = filtered.sort_values("published_at", ascending=False).head(50).copy()
view["게시일"] = view["published_at"].dt.strftime("%Y-%m-%d %H:%M")
st.dataframe(
    view[["게시일", "professor_name", "publisher", "title", "mention_type", "topic", "url"]],
    hide_index=True,
    use_container_width=True,
    column_config={
        "professor_name": "교수",
        "publisher": "언론사",
        "title": "기사 제목",
        "mention_type": "유형",
        "topic": "주제",
        "url": st.column_config.LinkColumn("원문"),
    },
)
