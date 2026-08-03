from __future__ import annotations

import hashlib
import html
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import feedparser
import pandas as pd
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROFESSORS_FILE = DATA_DIR / "professors.csv"
ARTICLES_FILE = DATA_DIR / "articles.csv"

ARTICLE_COLUMNS = [
    "article_id", "canonical_key", "professor_name", "published_at", "collected_at",
    "title", "summary", "publisher", "url", "search_query", "source",
    "mention_type", "topic", "relevance_score", "review_status", "media_weight",
]

TYPE_RULES = {
    "기고·칼럼": ["기고", "칼럼", "시론", "오피니언", "특별기고"],
    "인터뷰": ["인터뷰", "대담", "일문일답", "만나봤", "초대석"],
    "방송 출연": ["출연", "라디오", "방송", "뉴스특보", "유튜브", "영상"],
    "전문가 인용": ["교수는", "전문가는", "진단했다", "지적했다", "설명했다", "분석했다", "전망했다", "말했다"],
    "연구 소개": ["연구", "논문", "보고서", "조사 결과", "분석 결과", "학술지"],
    "행사·발표": ["세미나", "포럼", "토론회", "학술대회", "발표", "강연"],
    "인사·직책": ["임명", "취임", "선임", "원장", "수상", "위촉"],
}
TYPE_WEIGHT = {
    "기고·칼럼": 5.0, "인터뷰": 4.0, "방송 출연": 4.0, "전문가 인용": 3.0,
    "연구 소개": 3.0, "행사·발표": 2.0, "인사·직책": 1.0, "단순 언급": 0.5,
}
TOPIC_RULES = {
    "행정·조직": ["거버넌스", "조직", "인사", "공공관리", "정부혁신", "행정", "윤리", "정책수단"],
    "재정·경제": ["재정", "예산", "세금", "공기업", "재벌", "기업", "공정거래", "금융", "경제", "회계"],
    "사회·복지": ["복지", "연금", "사회정책", "인구", "저출생", "이민", "다문화", "탈북", "보건", "교육"],
    "국제·개발": ["국제", "통상", "ODA", "개발협력", "해양", "북한", "동아시아", "글로벌"],
    "디지털·AI": ["인공지능", "AI", "알고리즘", "전자정부", "디지털", "개인정보", "프라이버시", "정보정책"],
    "환경·에너지": ["기후", "환경", "에너지", "탄소", "재해", "방재"],
    "법·안전": ["행정법", "지방자치", "범죄", "경찰", "형사", "안전", "법원", "헌법"],
    "정책분석·방법론": ["정책평가", "정책분석", "계량", "방법론", "실험", "증거기반", "수요예측"],
}


def clean_text(value: str) -> str:
    text = BeautifulSoup(html.unescape(value or ""), "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", text).strip()


def parse_date(value: str) -> str:
    try:
        dt = date_parser.parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        return ""


def classify_type(text: str) -> str:
    lowered = text.lower()
    scores = {category: sum(1 for keyword in words if keyword.lower() in lowered) for category, words in TYPE_RULES.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else "단순 언급"


def classify_topics(text: str) -> str:
    lowered = text.lower()
    matched = [category for category, words in TOPIC_RULES.items() if any(word.lower() in lowered for word in words)]
    return ";".join(matched) if matched else "기타"


def relevance_score(name: str, text: str, search_terms: list[str], exclude_terms: list[str]) -> int:
    lowered = text.lower()
    score = 0
    if name.lower() in lowered:
        score += 45
    if "서울대학교" in text or "서울대" in text:
        score += 25
    if "행정대학원" in text:
        score += 20
    score += min(20, 5 * sum(1 for term in search_terms if term and term.lower() in lowered))
    score -= min(70, 35 * sum(1 for term in exclude_terms if term and term.lower() in lowered))
    other_university = re.search(r"(?:연세대|고려대|성균관대|한양대|중앙대|경희대|부산대|경북대|전남대|충남대)\s*(?:학교)?", text)
    if other_university and "서울대" not in text and "서울대학교" not in text:
        score -= 25
    return max(0, min(100, score))


def build_queries(row: pd.Series) -> list[str]:
    name = str(row["name"]).strip()
    terms = [x.strip() for x in str(row.get("search_terms", "")).split(";") if x.strip()]
    affiliation = f'"{name}" ("서울대학교" OR "서울대" OR "행정대학원")'
    topic_part = " OR ".join(f'"{term}"' for term in terms[:5])
    topic = f'"{name}" ({topic_part})' if topic_part else affiliation
    return list(dict.fromkeys([affiliation, topic]))


def fetch_feed(query: str, max_items: int = 100) -> list[dict]:
    url = "https://news.google.com/rss/search?q=" + quote(query) + "&hl=ko&gl=KR&ceid=KR:ko"
    feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0 (compatible; SNU-GSPA-Media-Monitor/1.0)"})
    if getattr(feed, "bozo", False) and not feed.entries:
        raise RuntimeError(str(getattr(feed, "bozo_exception", "RSS parsing failed")))
    return list(feed.entries[:max_items])


def normalize_title(title: str) -> str:
    title = re.sub(r"\s*[-|–—]\s*[^-|–—]{2,30}$", "", title)
    return re.sub(r"[^0-9A-Za-z가-힣]", "", title).lower()


def canonical_key(title: str, published_at: str) -> str:
    raw = f"{normalize_title(title)}|{published_at[:10]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def article_id(professor_name: str, canonical: str) -> str:
    return hashlib.sha256(f"{professor_name}|{canonical}".encode("utf-8")).hexdigest()[:24]


def load_existing() -> pd.DataFrame:
    if not ARTICLES_FILE.exists() or ARTICLES_FILE.stat().st_size == 0:
        return pd.DataFrame(columns=ARTICLE_COLUMNS)
    df = pd.read_csv(ARTICLES_FILE, dtype=str).fillna("")
    for col in ARTICLE_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[ARTICLE_COLUMNS]


def collect(max_items: int = 100, sleep_seconds: float = 0.15) -> tuple[int, int]:
    DATA_DIR.mkdir(exist_ok=True)
    professors = pd.read_csv(PROFESSORS_FILE, dtype=str).fillna("")
    existing = load_existing()
    known_ids = set(existing["article_id"].astype(str))
    rows: list[dict] = []
    failures = 0
    collected_at = datetime.now(timezone.utc).isoformat()

    for _, professor in professors.iterrows():
        name = professor["name"].strip()
        search_terms = [x.strip() for x in professor.get("search_terms", "").split(";") if x.strip()]
        exclude_terms = [x.strip() for x in professor.get("exclude_terms", "").split(";") if x.strip()]
        for query in build_queries(professor):
            try:
                entries = fetch_feed(query, max_items=max_items)
            except Exception as exc:
                failures += 1
                print(f"[WARN] {name} / {query}: {exc}")
                continue
            for entry in entries:
                title = clean_text(entry.get("title", ""))
                summary = clean_text(entry.get("summary", ""))
                publisher = clean_text(entry.get("source", {}).get("title", "")) or "미상"
                published_at = parse_date(entry.get("published", ""))
                url = str(entry.get("link", "")).strip()
                if not title:
                    continue
                combined = f"{title} {summary}"
                score = relevance_score(name, combined, search_terms, exclude_terms)
                ckey = canonical_key(title, published_at)
                aid = article_id(name, ckey)
                if aid in known_ids:
                    continue
                mention_type = classify_type(combined)
                rows.append({
                    "article_id": aid,
                    "canonical_key": ckey,
                    "professor_name": name,
                    "published_at": published_at,
                    "collected_at": collected_at,
                    "title": title,
                    "summary": summary,
                    "publisher": publisher,
                    "url": url,
                    "search_query": query,
                    "source": "Google News RSS",
                    "mention_type": mention_type,
                    "topic": classify_topics(combined),
                    "relevance_score": score,
                    "review_status": "관련" if score >= 70 else ("검토 필요" if score >= 45 else "제외 후보"),
                    "media_weight": TYPE_WEIGHT.get(mention_type, 0.5),
                })
                known_ids.add(aid)
            time.sleep(sleep_seconds)

    updated = pd.concat([existing, pd.DataFrame(rows)], ignore_index=True) if rows else existing
    if not updated.empty:
        updated["published_at"] = pd.to_datetime(updated["published_at"], errors="coerce", utc=True)
        updated = updated.sort_values("published_at", ascending=False, na_position="last")
        updated["published_at"] = updated["published_at"].astype(str).replace("NaT", "")
    updated.to_csv(ARTICLES_FILE, index=False, encoding="utf-8-sig")
    return len(rows), failures


if __name__ == "__main__":
    new_count, failure_count = collect()
    print(f"Collection complete. New rows={new_count}, failed queries={failure_count}")
