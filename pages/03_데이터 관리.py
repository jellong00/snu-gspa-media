from pathlib import Path
import subprocess
import sys

import pandas as pd
import streamlit as st

st.set_page_config(page_title="데이터 관리", page_icon="⚙️", layout="wide")
BASE_DIR = Path(__file__).resolve().parents[1]
ARTICLES_FILE = BASE_DIR / "data" / "articles.csv"
PROFESSORS_FILE = BASE_DIR / "data" / "professors.csv"

st.title("데이터 관리")
st.warning("Streamlit Community Cloud에서 수동 수집한 파일 변경은 재부팅·재배포 때 사라질 수 있습니다. 영구 누적은 GitHub Actions가 저장소에 커밋하도록 운영하십시오.")

professors = pd.read_csv(PROFESSORS_FILE, dtype=str).fillna("")
articles = pd.read_csv(ARTICLES_FILE, dtype=str).fillna("")

c1, c2, c3 = st.columns(3)
c1.metric("등록 교수", len(professors))
c2.metric("누적 행", len(articles))
c3.metric("마지막 수집", articles["collected_at"].max()[:19] if len(articles) else "없음")

with st.expander("교수진 검색 설정"):
    st.dataframe(professors, hide_index=True, use_container_width=True)
    st.download_button("교수진 CSV 다운로드", professors.to_csv(index=False, encoding="utf-8-sig"), "professors.csv", "text/csv")

if st.button("지금 RSS 수집 실행", type="primary"):
    with st.spinner("기사를 수집하고 있습니다..."):
        result = subprocess.run([sys.executable, str(BASE_DIR / "collect_news.py")], cwd=BASE_DIR, capture_output=True, text=True, timeout=240)
    if result.returncode == 0:
        st.success(result.stdout.strip() or "수집이 완료되었습니다.")
        st.cache_data.clear()
    else:
        st.error(result.stderr.strip() or "수집에 실패했습니다.")

st.download_button("전체 기사 CSV 다운로드", articles.to_csv(index=False, encoding="utf-8-sig"), "articles.csv", "text/csv")
