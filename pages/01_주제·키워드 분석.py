from pathlib import Path
import os
import re
import tempfile

import requests

import pandas as pd
import plotly.express as px
import streamlit as st
from wordcloud import WordCloud

st.set_page_config(page_title="주제·키워드 분석", page_icon="🔎", layout="wide")
BASE_DIR = Path(__file__).resolve().parents[1]
STOPWORDS = {"교수", "서울대", "서울대학교", "행정대학원", "기자", "뉴스", "정부", "관련", "대해", "통해", "이번", "대한", "말했다", "밝혔다", "위해", "있는", "한다", "에서", "으로", "하고"}

PROFESSOR_COLUMNS = [
    "professor_id", "name_en", "name", "rank", "position", "status",
    "external_position", "research_areas", "research_categories",
    "search_terms", "exclude_terms",
]
PROFESSOR_ALIASES = {
    "name_ko": "name",
    "직급": "rank",
    "보직": "position",
    "재직상태": "status",
    "외부직책": "external_position",
    "research_area": "research_areas",
    "연구분야": "research_areas",
    "research_category": "research_categories",
    "연구분야대분류": "research_categories",
}

def load_professors(path):
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
    for old, new in PROFESSOR_ALIASES.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]
    for col in PROFESSOR_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    if not df["research_categories"].astype(str).str.strip().any():
        df["research_categories"] = "기타"
    else:
        df["research_categories"] = df["research_categories"].replace("", "기타")
    if not df["name"].astype(str).str.strip().any():
        raise ValueError("professors.csv에 교수명 열(name 또는 name_ko)이 없습니다.")
    return df[PROFESSOR_COLUMNS]

ARTICLE_COLUMNS = [
    "article_id", "canonical_key", "professor_name", "published_at", "collected_at",
    "title", "summary", "publisher", "url", "search_query", "source",
    "mention_type", "topic", "relevance_score", "review_status", "media_weight",
]

def load_articles_file(path):
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
    for col in ARTICLE_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[ARTICLE_COLUMNS]

@st.cache_data(ttl=300)
def load_data():
    p = load_professors(BASE_DIR / "data" / "professors.csv")
    a = load_articles_file(BASE_DIR / "data" / "articles.csv")
    a["published_at"] = pd.to_datetime(a["published_at"], errors="coerce", utc=True).dt.tz_convert("Asia/Seoul")
    return p, a


FONT_URLS = [
    "https://raw.githubusercontent.com/google/fonts/main/ofl/nanumgothic/NanumGothic-Regular.ttf",
    "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf",
]


@st.cache_resource
def download_korean_font():
    """시스템 패키지 없이 실행 시점에 한글 TTF를 임시 폴더로 내려받는다."""
    font_path = os.path.join(tempfile.gettempdir(), "NanumGothic-Regular.ttf")
    if os.path.exists(font_path) and os.path.getsize(font_path) > 100_000:
        return font_path
    for url in FONT_URLS:
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            if len(response.content) < 100_000:
                continue
            with open(font_path, "wb") as file:
                file.write(response.content)
            return font_path
        except (requests.RequestException, OSError):
            continue
    return None


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

mode = st.radio("분석 단위", ["전체 교수", "선택 교수", "선택 기사 주제"], horizontal=True)
if mode == "선택 교수":
    selected = st.multiselect("교수", professors["name"].tolist(), default=professors["name"].tolist()[:1])
    if selected: df = df[df["professor_name"].isin(selected)]
elif mode == "선택 기사 주제":
    cats = sorted({x for v in df["topic"].fillna("") for x in str(v).split(";") if x})
    selected = st.multiselect("기사 주제", cats, default=cats[:1])
    if selected:
        df = df[df["topic"].apply(lambda x: any(c in str(x).split(";") for c in selected))]

article_topics = df.assign(주제=df["topic"].str.split(";")).explode("주제")
left, right = st.columns(2)
with left:
    topic_df = article_topics.groupby("주제")["canonical_key"].nunique().sort_values().reset_index(name="기사 수")
    st.plotly_chart(px.bar(topic_df, x="기사 수", y="주제", orientation="h", title="분야별 언론 노출"), use_container_width=True)
with right:
    cross = article_topics.groupby(["professor_name", "주제"], as_index=False).size().pivot(index="professor_name", columns="주제", values="size").fillna(0)
    top_names = df["professor_name"].value_counts().head(20).index.tolist()
    cross = cross.reindex([name for name in top_names if name in cross.index]).fillna(0)
    if cross.empty:
        st.info("히트맵을 그릴 기사 데이터가 없습니다.")
    else:
        st.plotly_chart(px.imshow(cross, aspect="auto", labels={"x": "주제", "y": "교수", "color": "기사 수"}, title="교수 × 기사 주제 히트맵"), use_container_width=True)

kw = keyword_table(df, professors["name"].tolist()).head(60)
st.subheader("워드클라우드와 키워드 빈도")
wc_col, table_col = st.columns([1.25, 1])
with wc_col:
    fp = download_korean_font()
    if not kw.empty and fp:
        wc = WordCloud(width=1000, height=520, background_color="white", font_path=fp, collocations=False).generate_from_frequencies(dict(zip(kw["키워드"], kw["빈도"])))
        st.image(wc.to_array(), use_container_width=True)
    elif not kw.empty:
        st.warning("한글 폰트를 내려받지 못해 워드클라우드를 표시하지 못했습니다. 잠시 후 다시 실행하십시오.")
with table_col:
    st.dataframe(kw.head(25), hide_index=True, use_container_width=True)

if not kw.empty:
    selected_keyword = st.selectbox("월별 추이를 볼 키워드", kw["키워드"].head(40).tolist())
    matched = df[(df["title"] + " " + df["summary"]).str.contains(re.escape(selected_keyword), case=False, na=False)].copy()
    trend = matched.assign(month=matched["published_at"].dt.to_period("M").astype(str)).groupby("month")["canonical_key"].nunique().reset_index(name="기사 수")
    st.plotly_chart(px.line(trend, x="month", y="기사 수", markers=True, title=f"‘{selected_keyword}’ 월별 언급 추이"), use_container_width=True)
