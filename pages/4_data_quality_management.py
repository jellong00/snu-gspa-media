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

st.title("데이터 품질·관리")
st.warning("Streamlit Community Cloud에서 직접 수집한 파일은 재배포 시 사라질 수 있습니다. 영구 누적은 GitHub Actions가 articles.csv를 저장소에 커밋하는 방식으로 운영하십시오.")
professors = pd.read_csv(PROFESSORS_FILE, dtype=str).fillna("")
articles = pd.read_csv(ARTICLES_FILE, dtype=str).fillna("")

cols = st.columns(5)
cols[0].metric("등록 교수", len(professors))
cols[1].metric("누적 행", len(articles))
cols[2].metric("원문 기준", articles["canonical_key"].nunique() if len(articles) else 0)
cols[3].metric("검토 필요", (articles["review_status"] == "검토 필요").sum() if len(articles) else 0)
cols[4].metric("제외 후보", (articles["review_status"] == "제외 후보").sum() if len(articles) else 0)

if len(articles):
    status_df = articles["review_status"].value_counts().reset_index(); status_df.columns = ["상태", "건수"]
    left, right = st.columns(2)
    with left: st.plotly_chart(px.bar(status_df, x="상태", y="건수", title="검토 상태 구성"), use_container_width=True)
    with right:
        dup = articles.groupby("canonical_key").size().value_counts().sort_index().reset_index(); dup.columns = ["동일 기사 연결 행 수", "기사 수"]
        st.plotly_chart(px.bar(dup, x="동일 기사 연결 행 수", y="기사 수", title="중복·교수 연결 구조"), use_container_width=True)
    st.caption(f"마지막 수집: {articles['collected_at'].max()[:19] if articles['collected_at'].max() else '없음'}")

if st.button("지금 RSS 수집 실행", type="primary"):
    with st.spinner("교수진 관련 기사를 수집하고 있습니다."):
        result = subprocess.run([sys.executable, str(BASE_DIR / "collect_news.py")], cwd=BASE_DIR, capture_output=True, text=True, timeout=300)
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
