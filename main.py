from pathlib import Path
import re
import subprocess
import sys

import pandas as pd
import plotly.express as px
import streamlit as st
from wordcloud import WordCloud

st.set_page_config(page_title="서울대 행정대학원 언론 모니터링", page_icon="📰", layout="wide")
BASE_DIR = Path(__file__).resolve().parent
ARTICLES_FILE = BASE_DIR / "data" / "articles.csv"
PROFESSORS_FILE = BASE_DIR / "data" / "professors.csv"

STOPWORDS = {"교수", "서울대", "서울대학교", "행정대학원", "기자", "뉴스", "정부", "관련", "대해", "통해", "이번", "대한", "말했다", "밝혔다", "위해", "있는", "한다", "에서", "으로", "하고"}
MAJOR_MEDIA = {"연합뉴스", "KBS", "MBC", "SBS", "JTBC", "YTN", "조선일보", "중앙일보", "동아일보", "한겨레", "경향신문", "한국일보", "매일경제", "한국경제", "서울신문", "국민일보"}

@st.cache_data(ttl=300)
def load_data():
    professors = pd.read_csv(PROFESSORS_FILE, dtype=str).fillna("")
    articles = pd.read_csv(ARTICLES_FILE, dtype=str).fillna("")
    for col in ["published_at", "collected_at"]:
        articles[col] = pd.to_datetime(articles[col], errors="coerce", utc=True).dt.tz_convert("Asia/Seoul")
    articles["relevance_score"] = pd.to_numeric(articles["relevance_score"], errors="coerce").fillna(0)
    articles["media_weight"] = pd.to_numeric(articles["media_weight"], errors="coerce").fillna(0.5)
    return professors, articles


def run_collection():
    return subprocess.run([sys.executable, str(BASE_DIR / "collect_news.py")], cwd=BASE_DIR, capture_output=True, text=True, timeout=300)


def font_path():
    candidates = [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "C:/Windows/Fonts/malgun.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    ]
    return next((p for p in candidates if Path(p).exists()), None)


def keyword_table(df, professor_names):
    if df.empty:
        return pd.DataFrame(columns=["키워드", "빈도", "관련 기사 수"])
    names = set(professor_names)
    token_rows = []
    for idx, text in enumerate((df["title"] + " " + df["summary"]).fillna("")):
        tokens = [w for w in re.findall(r"[가-힣A-Za-z]{2,}", text) if w not in STOPWORDS and w not in names]
        for word in tokens:
            token_rows.append((idx, word))
    if not token_rows:
        return pd.DataFrame(columns=["키워드", "빈도", "관련 기사 수"])
    t = pd.DataFrame(token_rows, columns=["doc", "키워드"])
    freq = t.groupby("키워드").size().rename("빈도")
    docfreq = t.drop_duplicates().groupby("키워드").size().rename("관련 기사 수")
    return pd.concat([freq, docfreq], axis=1).sort_values(["관련 기사 수", "빈도"], ascending=False).reset_index()

professors, articles = load_data()
st.title("서울대학교 행정대학원 언론 모니터링")
st.caption("Google 뉴스 RSS 기반 시범 대시보드 · 기사 제목과 RSS 요약을 중심으로 분석")

if articles.empty:
    st.info("최초 실행 상태입니다. 기사 데이터를 자동으로 수집합니다.")
    if "initial_collection_attempted" not in st.session_state:
        st.session_state.initial_collection_attempted = True
        with st.spinner("교수진 관련 뉴스를 처음 수집하고 있습니다."):
            result = run_collection()
        st.cache_data.clear()
        if result.returncode == 0:
            st.success(result.stdout.strip() or "수집이 완료되었습니다.")
            st.rerun()
        else:
            st.error("자동 수집에 실패했습니다.")
            st.code((result.stderr or result.stdout or "오류 로그 없음")[-4000:])
    if st.button("기사 수집 다시 실행", type="primary"):
        with st.spinner("기사를 수집하고 있습니다."):
            result = run_collection()
        st.cache_data.clear()
        if result.returncode == 0:
            st.success(result.stdout.strip())
            st.rerun()
        st.error((result.stderr or "수집 실패")[-4000:])
    st.stop()

valid_dates = articles["published_at"].dropna()
if valid_dates.empty:
    st.error("기사 행은 있으나 게시일을 읽지 못했습니다. 데이터 관리 페이지에서 CSV를 확인하십시오.")
    st.stop()
min_date, max_date = valid_dates.min().date(), valid_dates.max().date()
today = pd.Timestamp.now(tz="Asia/Seoul").date()

with st.sidebar:
    st.header("필터")
    preset = st.radio("기간", ["오늘", "최근 7일", "최근 30일", "올해", "사용자 지정"], index=2, horizontal=True)
    if preset == "오늘": start_date, end_date = today, today
    elif preset == "최근 7일": start_date, end_date = today - pd.Timedelta(days=6), today
    elif preset == "최근 30일": start_date, end_date = today - pd.Timedelta(days=29), today
    elif preset == "올해": start_date, end_date = pd.Timestamp(today.year, 1, 1).date(), today
    else:
        chosen = st.date_input("사용자 지정 기간", value=(max(min_date, today - pd.Timedelta(days=29)), min(today, max_date)), min_value=min_date, max_value=max(today, max_date))
        start_date, end_date = chosen if isinstance(chosen, tuple) and len(chosen) == 2 else (chosen, chosen)
    selected_professors = st.multiselect("교수명", professors["name"].tolist())
    selected_ranks = st.multiselect("직급", sorted(professors["rank"].unique()))
    categories = sorted({x for value in professors["research_categories"] for x in value.split(";") if x})
    selected_categories = st.multiselect("연구분야", categories)
    selected_publishers = st.multiselect("언론사", sorted(articles["publisher"].dropna().unique()))
    selected_types = st.multiselect("기사 유형", sorted(articles["mention_type"].dropna().unique()))
    selected_sources = st.multiselect("수집 출처", sorted(articles["source"].dropna().unique()))
    include_review = st.checkbox("검토 필요 기사 포함", value=False)
    show_all_professors = st.checkbox("교수 순위 전체 보기", value=False)

eligible_names = set(professors["name"])
if selected_ranks:
    eligible_names &= set(professors.loc[professors["rank"].isin(selected_ranks), "name"])
if selected_categories:
    eligible_names &= set(professors.loc[professors["research_categories"].apply(lambda x: any(c in x.split(";") for c in selected_categories)), "name"])
if selected_professors:
    eligible_names &= set(selected_professors)

filtered = articles[articles["published_at"].dt.date.between(start_date, end_date)].copy()
filtered = filtered[filtered["professor_name"].isin(eligible_names)]
filtered = filtered[filtered["review_status"].isin(["관련", "검토 필요"] if include_review else ["관련"])]
if selected_publishers: filtered = filtered[filtered["publisher"].isin(selected_publishers)]
if selected_types: filtered = filtered[filtered["mention_type"].isin(selected_types)]
if selected_sources: filtered = filtered[filtered["source"].isin(selected_sources)]

raw_count = len(filtered)
unique_count = filtered["canonical_key"].nunique()
today_new = filtered[filtered["collected_at"].dt.date == today]["canonical_key"].nunique()
active_count = filtered["professor_name"].nunique()
active_media = filtered["mention_type"].isin(["인터뷰", "기고·칼럼", "방송 출연"]).sum()
major_count = filtered[filtered["publisher"].isin(MAJOR_MEDIA)]["canonical_key"].nunique()

cols = st.columns(5)
cols[0].metric("원문 기준 기사", f"{unique_count:,}", help="정규화한 제목과 게시일이 같은 기사를 하나로 계산")
cols[1].metric("중복·전재 포함", f"{raw_count:,}")
cols[2].metric("오늘 신규", f"{today_new:,}")
cols[3].metric("언론 노출 교수", f"{active_count:,}")
cols[4].metric("인터뷰·기고·방송", f"{active_media:,}")
st.caption(f"주요 언론 보도: **{major_count:,}건** · 내부 가중 노출점수: **{filtered['media_weight'].sum():,.1f}점** (성과평가용 객관 지표가 아닌 내부 참고값)")

left, right = st.columns([1.6, 1])
with left:
    st.subheader("일별 언론 노출 추이")
    daily = filtered.assign(date=filtered["published_at"].dt.date).groupby("date")["canonical_key"].nunique().reset_index(name="기사 수")
    fig = px.line(daily, x="date", y="기사 수", markers=True)
    st.plotly_chart(fig, use_container_width=True)
with right:
    st.subheader("기사 유형 구성")
    type_df = filtered.groupby("mention_type")["canonical_key"].nunique().reset_index(name="기사 수")
    st.plotly_chart(px.pie(type_df, names="mention_type", values="기사 수", hole=0.48), use_container_width=True)

left, right = st.columns(2)
with left:
    st.subheader("교수별 기사 수")
    rank_df = filtered.groupby("professor_name")["canonical_key"].nunique().sort_values(ascending=False)
    if not show_all_professors: rank_df = rank_df.head(10)
    rank_df = rank_df.sort_values().reset_index(name="기사 수")
    st.plotly_chart(px.bar(rank_df, x="기사 수", y="professor_name", orientation="h", labels={"professor_name": "교수"}), use_container_width=True)
with right:
    st.subheader("연구분야별 언론 노출")
    merged = filtered.merge(professors[["name", "research_categories"]], left_on="professor_name", right_on="name", how="left")
    exploded = merged.assign(연구분야=merged["research_categories"].str.split(";")).explode("연구분야")
    category_df = exploded.groupby("연구분야")["canonical_key"].nunique().sort_values().reset_index(name="기사 수")
    st.plotly_chart(px.bar(category_df, x="기사 수", y="연구분야", orientation="h"), use_container_width=True)

st.subheader("주요 키워드")
kw = keyword_table(filtered, professors["name"].tolist()).head(40)
wc_col, table_col = st.columns([1.25, 1])
with wc_col:
    fp = font_path()
    if not kw.empty and fp:
        wc = WordCloud(width=1000, height=500, background_color="white", font_path=fp, collocations=False).generate_from_frequencies(dict(zip(kw["키워드"], kw["빈도"])))
        st.image(wc.to_array(), use_container_width=True)
    elif not kw.empty:
        st.warning("한글 글꼴을 찾지 못했습니다. packages.txt의 fonts-nanum 설치를 확인하십시오.")
    else:
        st.info("키워드 데이터가 부족합니다.")
with table_col:
    st.dataframe(kw.head(20), hide_index=True, use_container_width=True)

st.subheader("최근 기사")
view = filtered.sort_values("published_at", ascending=False).head(100).copy()
view["게시일"] = view["published_at"].dt.strftime("%Y-%m-%d %H:%M")
st.dataframe(view[["게시일", "professor_name", "publisher", "title", "mention_type", "topic", "relevance_score", "review_status", "url"]], hide_index=True, use_container_width=True, column_config={"professor_name": "교수", "publisher": "언론사", "title": "기사 제목", "mention_type": "유형", "topic": "주제", "relevance_score": st.column_config.ProgressColumn("관련도", min_value=0, max_value=100), "review_status": "검토 상태", "url": st.column_config.LinkColumn("원문")})
