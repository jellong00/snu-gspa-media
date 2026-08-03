from pathlib import Path
import subprocess
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="데이터 품질·관리", page_icon="⚙️", layout="wide")
BASE_DIR = Path(__file__).resolve().parents[1]
ARTICLES_FILE = BASE_DIR / "data" / "articles.csv"
PROFESSORS_FILE = BASE_DIR / "data" / "professors.csv"

PROFESSOR_COLUMNS = [
    "professor_id", "name_en", "name", "rank", "position", "status",
    "external_position", "research_areas", "research_categories",
    "search_terms", "exclude_terms", "strict_affiliation",
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
    "title", "summary", "body", "author", "metadata_text", "publisher", "url", "final_url", "search_query", "source",
    "body_status", "body_char_count", "mention_type", "topic", "relevance_score", "review_status", "media_weight",
]

def load_articles_file(path):
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
    for col in ARTICLE_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[ARTICLE_COLUMNS]

st.title("데이터 품질·관리")
st.warning("Streamlit Community Cloud에서 직접 수집한 파일은 재배포 시 사라질 수 있습니다. 영구 누적은 GitHub Actions가 articles.csv를 저장소에 커밋하는 방식으로 운영하십시오.")
professors = load_professors(PROFESSORS_FILE)
articles = load_articles_file(ARTICLES_FILE)

cols = st.columns(6)
cols[0].metric("등록 교수", len(professors))
cols[1].metric("누적 행", len(articles))
cols[2].metric("원문 기준", articles["canonical_key"].nunique() if len(articles) else 0)
cols[3].metric("검토 필요", (articles["review_status"] == "검토 필요").sum() if len(articles) else 0)
cols[4].metric("본문 추출 성공", (articles["body_status"] == "추출 성공").sum() if len(articles) else 0)
cols[5].metric("본문 추출 실패", (articles["body_status"] != "추출 성공").sum() if len(articles) else 0)

if len(articles):
    status_df = articles["review_status"].value_counts().reset_index(); status_df.columns = ["상태", "건수"]
    left, middle, right = st.columns(3)
    with left: st.plotly_chart(px.bar(status_df, x="상태", y="건수", title="검토 상태 구성"), use_container_width=True)
    with middle:
        body_df = articles["body_status"].replace("", "미수집").value_counts().reset_index(); body_df.columns = ["본문 상태", "건수"]
        st.plotly_chart(px.bar(body_df, x="본문 상태", y="건수", title="본문 추출 상태"), use_container_width=True)
    with right:
        dup = articles.groupby("canonical_key").size().value_counts().sort_index().reset_index(); dup.columns = ["동일 기사 연결 행 수", "기사 수"]
        st.plotly_chart(px.bar(dup, x="동일 기사 연결 행 수", y="기사 수", title="중복·교수 연결 구조"), use_container_width=True)
    st.caption(f"마지막 수집: {articles['collected_at'].max()[:19] if articles['collected_at'].max() else '없음'}")

if st.button("지금 RSS 수집 실행", type="primary"):
    with st.spinner("교수진 관련 기사를 수집하고 있습니다."):
        result = subprocess.run([sys.executable, str(BASE_DIR / "collect_news.py")], cwd=BASE_DIR, capture_output=True, text=True, timeout=1800)
    if result.returncode == 0:
        st.success(result.stdout.strip() or "수집 완료")
        st.cache_data.clear()
        st.rerun()
    else:
        st.error("수집 실패")
        st.code((result.stderr or result.stdout or "오류 로그 없음")[-4000:])

with st.expander("교수진 검색 설정"):
    st.dataframe(professors, hide_index=True, use_container_width=True)
    st.download_button("교수진 CSV 다운로드", professors.to_csv(index=False, encoding="utf-8-sig"), "professors.csv", "text/csv")

if len(articles):
    st.subheader("검토 필요 기사")
    review = articles[articles["review_status"] == "검토 필요"].copy()
    st.dataframe(review[["professor_name", "publisher", "title", "relevance_score", "search_query", "url"]], hide_index=True, use_container_width=True, column_config={"url": st.column_config.LinkColumn("원문")})
st.download_button("전체 기사 CSV 다운로드", articles.to_csv(index=False, encoding="utf-8-sig"), "articles.csv", "text/csv")
