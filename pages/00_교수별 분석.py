from pathlib import Path
import re

import pandas as pd
import plotly.express as px
import streamlit as st
from wordcloud import WordCloud

st.set_page_config(page_title="교수별 분석", page_icon="👤", layout="wide")
BASE_DIR = Path(__file__).resolve().parents[1]

@st.cache_data(ttl=300)
def load_data():
    p = pd.read_csv(BASE_DIR / "data" / "professors.csv", dtype=str).fillna("")
    a = pd.read_csv(BASE_DIR / "data" / "articles.csv", dtype=str).fillna("")
    a["published_at"] = pd.to_datetime(a["published_at"], errors="coerce", utc=True).dt.tz_convert("Asia/Seoul")
    return p, a

STOPWORDS = {"서울대", "서울대학교", "행정대학원", "교수", "기자", "정부", "관련", "대한", "통해", "이번", "뉴스", "말했다", "밝혔다", "위해", "있는", "한다", "에서"}

def tokens(text, professor):
    words = re.findall(r"[가-힣A-Za-z]{2,}", text)
    return [w for w in words if w not in STOPWORDS and w.lower() != professor.lower()]

def font_path():
    candidates = [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "C:/Windows/Fonts/malgun.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    ]
    return next((p for p in candidates if Path(p).exists()), None)

professors, articles = load_data()
st.title("교수별 언론 노출 분석")
name = st.selectbox("교수 선택", professors["name"].tolist())
profile = professors.loc[professors["name"] == name].iloc[0]
st.markdown(f"### {name} · {profile['rank']}")
st.write(profile["position"] or "보직 정보 없음")
st.caption(profile["research_areas"])

df = articles[(articles["professor_name"] == name) & (articles["review_status"].isin(["관련", "검토 필요"]))].copy()
if df.empty:
    st.info("해당 교수의 수집 기사가 없습니다.")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("누적 기사", len(df))
c2.metric("관련 확정", (df["review_status"] == "관련").sum())
c3.metric("인터뷰·기고", df["mention_type"].isin(["인터뷰", "기고·칼럼"]).sum())
c4.metric("언론사", df["publisher"].nunique())

monthly = df.assign(month=df["published_at"].dt.to_period("M").astype(str)).groupby("month").size().reset_index(name="기사 수")
st.plotly_chart(px.line(monthly, x="month", y="기사 수", markers=True, title="월별 기사 추이"), use_container_width=True)

left, right = st.columns(2)
with left:
    pubs = df["publisher"].value_counts().head(12).sort_values().reset_index()
    pubs.columns = ["언론사", "기사 수"]
    st.plotly_chart(px.bar(pubs, x="기사 수", y="언론사", orientation="h", title="주요 언론사"), use_container_width=True)
with right:
    text = " ".join((df["title"] + " " + df["summary"]).tolist())
    word_list = tokens(text, name)
    freq = pd.Series(word_list).value_counts().head(50).to_dict()
    fp = font_path()
    if freq and fp:
        wc = WordCloud(width=900, height=500, background_color="white", font_path=fp, collocations=False).generate_from_frequencies(freq)
        st.image(wc.to_array(), use_container_width=True)
    elif freq:
        st.warning("한글 글꼴을 찾지 못해 워드클라우드 대신 빈도표를 표시합니다. `packages.txt`의 fonts-nanum 설치 여부를 확인하십시오.")
    else:
        st.info("워드클라우드를 만들 단어가 부족합니다.")

freq_df = pd.DataFrame(list(freq.items()), columns=["키워드", "빈도"]).head(20) if 'freq' in locals() else pd.DataFrame()
if not freq_df.empty:
    st.plotly_chart(px.bar(freq_df.sort_values("빈도"), x="빈도", y="키워드", orientation="h", title="상위 키워드"), use_container_width=True)

view = df.sort_values("published_at", ascending=False).copy()
view["게시일"] = view["published_at"].dt.strftime("%Y-%m-%d")
st.dataframe(view[["게시일", "publisher", "title", "mention_type", "topic", "review_status", "url"]], hide_index=True, use_container_width=True, column_config={"url": st.column_config.LinkColumn("원문")})
