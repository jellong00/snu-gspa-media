from pathlib import Path
import re

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="주제·키워드 분석", page_icon="🔎", layout="wide")
BASE_DIR = Path(__file__).resolve().parents[1]

@st.cache_data(ttl=300)
def load_articles():
    df = pd.read_csv(BASE_DIR / "data" / "articles.csv", dtype=str).fillna("")
    df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce", utc=True).dt.tz_convert("Asia/Seoul")
    return df

STOPWORDS = {"서울대", "서울대학교", "행정대학원", "교수", "기자", "정부", "관련", "대한", "통해", "이번", "뉴스", "말했다", "밝혔다", "위해", "있는", "한다", "에서"}

df = load_articles()
df = df[df["review_status"].isin(["관련", "검토 필요"])].copy()
st.title("주제·키워드 분석")

if df.empty:
    st.info("수집된 기사가 없습니다.")
    st.stop()

col1, col2 = st.columns(2)
with col1:
    topics = df["topic"].value_counts().reset_index()
    topics.columns = ["주제", "기사 수"]
    st.plotly_chart(px.bar(topics, x="기사 수", y="주제", orientation="h", title="주제별 기사 수"), use_container_width=True)
with col2:
    cross = pd.crosstab(df["professor_name"], df["topic"])
    top_names = df["professor_name"].value_counts().head(15).index
    cross = cross.reindex(top_names).fillna(0)
    st.plotly_chart(px.imshow(cross, aspect="auto", labels={"x": "주제", "y": "교수", "color": "기사 수"}, title="교수 × 주제 히트맵"), use_container_width=True)

text = " ".join((df["title"] + " " + df["summary"]).tolist())
words = [w for w in re.findall(r"[가-힣A-Za-z]{2,}", text) if w not in STOPWORDS and w not in set(df["professor_name"])]
freq = pd.Series(words).value_counts().head(40).reset_index()
freq.columns = ["키워드", "빈도"]
st.plotly_chart(px.bar(freq.head(25).sort_values("빈도"), x="빈도", y="키워드", orientation="h", title="전체 상위 키워드"), use_container_width=True)

selected = st.selectbox("추이를 볼 키워드", freq["키워드"].tolist() if not freq.empty else [""])
if selected:
    matched = df[(df["title"] + " " + df["summary"]).str.contains(re.escape(selected), case=False, na=False)].copy()
    trend = matched.assign(month=matched["published_at"].dt.to_period("M").astype(str)).groupby("month").size().reset_index(name="기사 수")
    st.plotly_chart(px.line(trend, x="month", y="기사 수", markers=True, title=f"‘{selected}’ 월별 언급 추이"), use_container_width=True)
