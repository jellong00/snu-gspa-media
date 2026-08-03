from pathlib import Path
import re

import pandas as pd
import plotly.express as px
import streamlit as st
from wordcloud import WordCloud

st.set_page_config(page_title="주제·키워드 분석", page_icon="🔎", layout="wide")
BASE_DIR = Path(__file__).resolve().parents[1]
STOPWORDS = {"교수", "서울대", "서울대학교", "행정대학원", "기자", "뉴스", "정부", "관련", "대해", "통해", "이번", "대한", "말했다", "밝혔다", "위해", "있는", "한다", "에서", "으로", "하고"}

@st.cache_data(ttl=300)
def load_data():
    p = pd.read_csv(BASE_DIR / "data" / "professors.csv", dtype=str).fillna("")
    a = pd.read_csv(BASE_DIR / "data" / "articles.csv", dtype=str).fillna("")
    a["published_at"] = pd.to_datetime(a["published_at"], errors="coerce", utc=True).dt.tz_convert("Asia/Seoul")
    return p, a


def font_path():
    candidates = ["/usr/share/fonts/truetype/nanum/NanumGothic.ttf", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "C:/Windows/Fonts/malgun.ttf", "/System/Library/Fonts/AppleSDGothicNeo.ttc"]
    return next((p for p in candidates if Path(p).exists()), None)


def keyword_table(df, names):
    rows = []
    names = set(names)
    for idx, text in enumerate((df["title"] + " " + df["summary"]).fillna("")):
        words = [w for w in re.findall(r"[가-힣A-Za-z]{2,}", text) if w not in STOPWORDS and w not in names]
        rows.extend((idx, word) for word in words)
    if not rows: return pd.DataFrame(columns=["키워드", "빈도", "관련 기사 수"])
    t = pd.DataFrame(rows, columns=["doc", "키워드"])
    return pd.concat([t.groupby("키워드").size().rename("빈도"), t.drop_duplicates().groupby("키워드").size().rename("관련 기사 수")], axis=1).sort_values(["관련 기사 수", "빈도"], ascending=False).reset_index()

professors, articles = load_data()
st.title("주제·키워드 분석")
if articles.empty:
    st.info("수집된 기사가 없습니다.")
    st.stop()
df = articles[articles["review_status"].isin(["관련", "검토 필요"])].copy()

mode = st.radio("분석 단위", ["전체 교수", "선택 교수", "선택 연구분야"], horizontal=True)
if mode == "선택 교수":
    selected = st.multiselect("교수", professors["name"].tolist(), default=professors["name"].tolist()[:1])
    if selected: df = df[df["professor_name"].isin(selected)]
elif mode == "선택 연구분야":
    cats = sorted({x for v in professors["research_categories"] for x in v.split(";") if x})
    selected = st.multiselect("연구분야", cats, default=cats[:1])
    names = professors.loc[professors["research_categories"].apply(lambda x: any(c in x.split(";") for c in selected)), "name"] if selected else []
    if selected: df = df[df["professor_name"].isin(names)]

article_topics = df.assign(주제=df["topic"].str.split(";")).explode("주제")
left, right = st.columns(2)
with left:
    topic_df = article_topics.groupby("주제")["canonical_key"].nunique().sort_values().reset_index(name="기사 수")
    st.plotly_chart(px.bar(topic_df, x="기사 수", y="주제", orientation="h", title="분야별 언론 노출"), use_container_width=True)
with right:
    cross = pd.crosstab(article_topics["professor_name"], article_topics["주제"])
    top_names = df["professor_name"].value_counts().head(20).index
    cross = cross.reindex(top_names).fillna(0)
    st.plotly_chart(px.imshow(cross, aspect="auto", labels={"x": "주제", "y": "교수", "color": "기사 수"}, title="교수 × 주제 히트맵"), use_container_width=True)

kw = keyword_table(df, professors["name"].tolist()).head(60)
st.subheader("워드클라우드와 키워드 빈도")
wc_col, table_col = st.columns([1.25, 1])
with wc_col:
    fp = font_path()
    if not kw.empty and fp:
        wc = WordCloud(width=1000, height=520, background_color="white", font_path=fp, collocations=False).generate_from_frequencies(dict(zip(kw["키워드"], kw["빈도"])))
        st.image(wc.to_array(), use_container_width=True)
with table_col:
    st.dataframe(kw.head(25), hide_index=True, use_container_width=True)

if not kw.empty:
    selected_keyword = st.selectbox("월별 추이를 볼 키워드", kw["키워드"].head(40).tolist())
    matched = df[(df["title"] + " " + df["summary"]).str.contains(re.escape(selected_keyword), case=False, na=False)].copy()
    trend = matched.assign(month=matched["published_at"].dt.to_period("M").astype(str)).groupby("month")["canonical_key"].nunique().reset_index(name="기사 수")
    st.plotly_chart(px.line(trend, x="month", y="기사 수", markers=True, title=f"‘{selected_keyword}’ 월별 언급 추이"), use_container_width=True)
