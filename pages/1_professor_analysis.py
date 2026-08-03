from pathlib import Path
import re

import pandas as pd
import plotly.express as px
import streamlit as st
from wordcloud import WordCloud

st.set_page_config(page_title="교수별 분석", page_icon="👤", layout="wide")
BASE_DIR = Path(__file__).resolve().parents[1]
STOPWORDS = {"교수", "서울대", "서울대학교", "행정대학원", "기자", "뉴스", "정부", "관련", "대해", "통해", "이번", "대한", "말했다", "밝혔다", "위해", "있는", "한다", "에서", "으로", "하고"}
MAJOR_MEDIA = {"연합뉴스", "KBS", "MBC", "SBS", "JTBC", "YTN", "조선일보", "중앙일보", "동아일보", "한겨레", "경향신문", "한국일보", "매일경제", "한국경제", "서울신문", "국민일보"}

@st.cache_data(ttl=300)
def load_data():
    p = pd.read_csv(BASE_DIR / "data" / "professors.csv", dtype=str).fillna("")
    a = pd.read_csv(BASE_DIR / "data" / "articles.csv", dtype=str).fillna("")
    a["published_at"] = pd.to_datetime(a["published_at"], errors="coerce", utc=True).dt.tz_convert("Asia/Seoul")
    a["media_weight"] = pd.to_numeric(a["media_weight"], errors="coerce").fillna(0.5)
    a["relevance_score"] = pd.to_numeric(a["relevance_score"], errors="coerce").fillna(0)
    return p, a


def font_path():
    candidates = ["/usr/share/fonts/truetype/nanum/NanumGothic.ttf", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "C:/Windows/Fonts/malgun.ttf", "/System/Library/Fonts/AppleSDGothicNeo.ttc"]
    return next((p for p in candidates if Path(p).exists()), None)


def keyword_table(df, professor):
    rows = []
    for idx, text in enumerate((df["title"] + " " + df["summary"]).fillna("")):
        words = [w for w in re.findall(r"[가-힣A-Za-z]{2,}", text) if w not in STOPWORDS and w.lower() != professor.lower()]
        rows.extend((idx, word) for word in words)
    if not rows:
        return pd.DataFrame(columns=["키워드", "빈도", "관련 기사 수"])
    t = pd.DataFrame(rows, columns=["doc", "키워드"])
    return pd.concat([t.groupby("키워드").size().rename("빈도"), t.drop_duplicates().groupby("키워드").size().rename("관련 기사 수")], axis=1).sort_values(["관련 기사 수", "빈도"], ascending=False).reset_index()

professors, articles = load_data()
st.title("교수별 언론 노출 분석")
if articles.empty:
    st.info("수집된 기사가 없습니다. 종합 현황 또는 데이터 품질·관리 페이지에서 수집을 실행하십시오.")
    st.stop()
name = st.selectbox("교수 선택", professors["name"].tolist())
profile = professors.loc[professors["name"] == name].iloc[0]
st.markdown(f"### {name} · {profile['rank']}")
meta = [x for x in [profile["position"], f"외부직책: {profile['external_position']}" if profile["external_position"] else "", f"상태: {profile['status']}"] if x]
st.write(" · ".join(meta))
st.caption(profile["research_areas"].replace(";", ", "))

include_review = st.checkbox("검토 필요 기사 포함", value=True)
df = articles[(articles["professor_name"] == name) & articles["review_status"].isin(["관련", "검토 필요"] if include_review else ["관련"])].copy()
if df.empty:
    st.info("해당 교수의 수집 기사가 없습니다.")
    st.stop()

today = pd.Timestamp.now(tz="Asia/Seoul")
last30 = df[df["published_at"] >= today - pd.Timedelta(days=30)]["canonical_key"].nunique()
ytd = df[df["published_at"].dt.year == today.year]["canonical_key"].nunique()
active = df[df["mention_type"].isin(["인터뷰", "기고·칼럼", "방송 출연"])]["canonical_key"].nunique()
major = df[df["publisher"].isin(MAJOR_MEDIA)]["publisher"].nunique()
this_month = df[df["published_at"].dt.to_period("M") == today.to_period("M")]["canonical_key"].nunique()
prev = today - pd.offsets.MonthBegin(1)
prev_month = df[df["published_at"].dt.to_period("M") == prev.to_period("M")]["canonical_key"].nunique()
change = None if prev_month == 0 else (this_month - prev_month) / prev_month * 100
cols = st.columns(5)
cols[0].metric("최근 30일", f"{last30:,}")
cols[1].metric("올해 누적", f"{ytd:,}")
cols[2].metric("인터뷰·기고·방송", f"{active:,}")
cols[3].metric("주요 언론사 수", f"{major:,}")
cols[4].metric("전월 대비", "비교 불가" if change is None else f"{change:+.1f}%")
st.caption(f"내부 가중 노출점수: **{df['media_weight'].sum():,.1f}점** · 객관적 성과평가 지표가 아닌 참고값")

period = st.radio("시계열 단위", ["월별", "주별"], horizontal=True)
if period == "월별":
    trend = df.assign(period=df["published_at"].dt.to_period("M").astype(str)).groupby("period")["canonical_key"].nunique().reset_index(name="기사 수")
else:
    trend = df.assign(period=df["published_at"].dt.to_period("W").astype(str)).groupby("period")["canonical_key"].nunique().reset_index(name="기사 수")
st.plotly_chart(px.line(trend, x="period", y="기사 수", markers=True, title=f"{period} 기사 추이"), use_container_width=True)

left, right = st.columns(2)
with left:
    pubs = df.groupby("publisher")["canonical_key"].nunique().nlargest(12).sort_values().reset_index(name="기사 수")
    st.plotly_chart(px.bar(pubs, x="기사 수", y="publisher", orientation="h", title="주요 언론사", labels={"publisher": "언론사"}), use_container_width=True)
with right:
    type_df = df.groupby("mention_type")["canonical_key"].nunique().reset_index(name="기사 수")
    st.plotly_chart(px.pie(type_df, names="mention_type", values="기사 수", hole=0.45, title="기사 유형 구성"), use_container_width=True)

kw = keyword_table(df, name).head(50)
st.subheader("주요 키워드")
wc_col, table_col = st.columns([1.25, 1])
with wc_col:
    fp = font_path()
    if not kw.empty and fp:
        wc = WordCloud(width=1000, height=520, background_color="white", font_path=fp, collocations=False).generate_from_frequencies(dict(zip(kw["키워드"], kw["빈도"])))
        st.image(wc.to_array(), use_container_width=True)
    elif not kw.empty:
        st.warning("한글 글꼴을 찾지 못했습니다.")
with table_col:
    st.dataframe(kw.head(20), hide_index=True, use_container_width=True)
if not kw.empty:
    st.plotly_chart(px.bar(kw.head(20).sort_values("관련 기사 수"), x="관련 기사 수", y="키워드", orientation="h", title="상위 키워드 기사 빈도"), use_container_width=True)

st.subheader("교수별 기사 목록")
view = df.sort_values("published_at", ascending=False).copy()
view["날짜"] = view["published_at"].dt.strftime("%Y-%m-%d")
st.dataframe(view[["날짜", "publisher", "title", "mention_type", "relevance_score", "review_status", "url"]], hide_index=True, use_container_width=True, column_config={"publisher": "언론사", "title": "기사 제목", "mention_type": "유형", "relevance_score": st.column_config.ProgressColumn("관련도", min_value=0, max_value=100), "review_status": "검토 상태", "url": st.column_config.LinkColumn("원문")})
