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
PROFESSOR_COLUMNS = [
    "professor_id", "name_en", "name", "rank", "position", "status",
    "external_position", "research_areas", "research_categories",
    "search_terms", "exclude_terms", "strict_affiliation",
]
PROFESSOR_ALIASES = {
    "name_ko": "name", "research_area": "research_areas",
    "research_category": "research_categories",
}

TYPE_RULES = {
    "기고·칼럼": ["기고", "칼럼", "시론", "오피니언", "특별기고"],
    "인터뷰": ["인터뷰", "대담", "일문일답", "만나봤", "초대석"],
    "방송 출연": ["출연", "라디오", "방송", "뉴스특보", "유튜브", "영상"],
    "전문가 인용": ["교수는", "원장은", "전문가는", "진단했다", "지적했다", "설명했다", "분석했다", "전망했다", "강조했다", "밝혔다", "말했다"],
    "연구 소개": ["연구", "논문", "보고서", "조사 결과", "분석 결과", "학술지"],
    "행사·발표": ["세미나", "포럼", "토론회", "학술대회", "발표", "강연", "공청회"],
    "인사·직책": ["임명", "취임", "선임", "원장", "수상", "위촉"],
}
TYPE_WEIGHT = {
    "기고·칼럼": 5.0, "인터뷰": 4.0, "방송 출연": 4.0, "전문가 인용": 3.0,
    "연구 소개": 3.0, "행사·발표": 2.0, "인사·직책": 1.0, "단순 언급": 0.5,
}
TOPIC_RULES = {
    "행정·조직": ["거버넌스", "조직", "인사", "공공관리", "정부혁신", "행정", "윤리", "정책수단", "적극행정", "감사원", "공무원"],
    "재정·경제": ["재정", "예산", "세금", "공기업", "재벌", "기업", "공정거래", "금융", "경제", "회계", "산업"],
    "사회·복지": ["복지", "연금", "사회정책", "인구", "저출생", "이민", "다문화", "탈북", "보건", "교육"],
    "국제·개발": ["국제", "통상", "ODA", "개발협력", "해양", "북한", "동아시아", "글로벌"],
    "디지털·AI": ["인공지능", "AI", "알고리즘", "전자정부", "디지털", "개인정보", "프라이버시", "정보정책"],
    "환경·에너지": ["기후", "환경", "에너지", "탄소", "재해", "방재"],
    "법·안전": ["행정법", "지방자치", "범죄", "경찰", "형사", "안전", "법원", "헌법", "감사"],
    "정책분석·방법론": ["정책평가", "정책분석", "계량", "방법론", "실험", "증거기반", "수요예측"],
}

OTHER_UNIVERSITIES = [
    "연세대", "연세대학교", "고려대", "고려대학교", "성균관대", "성균관대학교",
    "한양대", "한양대학교", "중앙대", "중앙대학교", "경희대", "경희대학교",
    "아주대", "아주대학교", "가천대", "가천대학교", "부산대", "부산대학교",
    "경북대", "경북대학교", "전남대", "전남대학교", "충남대", "충남대학교",
    "한국외대", "한국외국어대학교", "서강대", "서강대학교", "이화여대", "이화여자대학교",
    "건국대", "건국대학교", "동국대", "동국대학교", "홍익대", "홍익대학교",
    "서울시립대", "서울시립대학교", "국민대", "국민대학교", "숭실대", "숭실대학교",
    "세종대", "세종대학교", "단국대", "단국대학교", "숙명여대", "숙명여자대학교",
    "KAIST", "카이스트", "POSTECH", "포항공대",
]
OTHER_SNU_UNITS = [
    "의과대학", "의대", "공과대학", "공대", "경영대학", "경영대", "경영전문대학원",
    "법학전문대학원", "법대", "사회과학대학", "사회대", "인문대학", "인문대",
    "자연과학대학", "자연대", "농업생명과학대학", "농생대", "사범대학", "사범대",
    "미술대학", "미대", "음악대학", "음대", "간호대학", "간호대", "약학대학", "약대",
    "수의과대학", "수의대", "보건대학원", "국제대학원", "환경대학원", "치의학대학원",
    "융합과학기술대학원", "데이터사이언스대학원", "농경제사회학부", "경제학부", "정치외교학부",
    "사회학과", "언론정보학과", "심리학과", "법학과", "의학과", "컴퓨터공학부",
]
OTHER_ORGANIZATION_TERMS = [
    "주식회사", "㈜", "기업", "그룹", "재단", "협회", "연합회", "조합", "법무법인",
    "병원", "의원", "클리닉", "연구원", "연구소", "정책연구원", "경제연구원", "과학기술원",
    "방송", "신문", "일보", "매거진", "언론사", "정당", "국회의원", "시의원", "도의원",
    "시청", "도청", "구청", "군청", "경찰청", "검찰청", "법원", "학교법인", "고등학교",
    "중학교", "초등학교", "대학교병원", "센터", "원장", "대표", "대표이사", "연구위원",
    "기자", "앵커", "의사", "변호사", "회계사", "배우", "가수", "선수", "감독", "코치",
]
GSPA_TERMS = [
    "서울대학교 행정대학원", "서울대 행정대학원", "서울대학교 행정대학원 교수",
    "서울대 행정대학원 교수", "행정대학원 교수",
]
PUBLIC_ADMIN_TERMS = ["행정학", "정책학", "공공관리", "공공정책", "행정정책", "정책대학원"]


def load_professors_file() -> pd.DataFrame:
    df = pd.read_csv(PROFESSORS_FILE, dtype=str, encoding="utf-8-sig").fillna("")
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
    for old, new in PROFESSOR_ALIASES.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]
    for col in PROFESSOR_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    if not df["name"].astype(str).str.strip().any():
        raise ValueError("professors.csv에 교수명 열(name 또는 name_ko)이 없습니다.")
    return df[PROFESSOR_COLUMNS]


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


def nearby_text(name: str, text: str, radius: int = 90) -> str:
    positions = [m.start() for m in re.finditer(re.escape(name), text, flags=re.IGNORECASE)]
    if not positions:
        return ""
    return " ".join(text[max(0, p - radius): min(len(text), p + len(name) + radius)] for p in positions)


def _split_terms(value: str) -> list[str]:
    return [x.strip() for x in str(value or "").split(";") if x.strip()]


def _allowed_external_terms(external_position: str) -> list[str]:
    text = str(external_position or "").strip()
    if not text:
        return []
    terms = [text]
    # "한국행정연구원 원장"처럼 기관명만으로도 확인할 수 있게 직책어를 제거한다.
    institution = re.sub(r"\s*(원장|소장|센터장|위원장|교수|이사장|대표|주임).*$", "", text).strip()
    if len(institution) >= 3:
        terms.append(institution)
    return list(dict.fromkeys(terms))


def affiliation_match(
    name: str,
    text: str,
    search_terms: list[str],
    external_position: str = "",
) -> tuple[bool, str]:
    """모든 교수에게 동일한 소속 검증을 적용한다.

    이름만 일치하는 기사는 수집하지 않는다. 행정대학원, 등록된 외부직책,
    또는 이름 주변의 서울대+행정/정책 전공 근거가 있어야 한다.
    """
    lowered = text.lower()
    near = nearby_text(name, text, radius=220)
    near_lower = near.lower()
    has_name = name.lower() in lowered
    if not has_name:
        return False, "교수명 없음"

    has_gspa = any(term.lower() in near_lower for term in GSPA_TERMS)
    allowed_external = _allowed_external_terms(external_position)
    has_allowed_external = any(term.lower() in near_lower for term in allowed_external)

    has_snu_near = "서울대" in near or "서울대학교" in near
    academic_hits = sum(
        1 for term in list(search_terms) + PUBLIC_ADMIN_TERMS
        if term and term.lower() in near_lower
    )

    other_univ_near = any(term.lower() in near_lower for term in OTHER_UNIVERSITIES)
    other_snu_unit_near = any(term.lower() in near_lower for term in OTHER_SNU_UNITS)
    other_org_near = any(term.lower() in near_lower for term in OTHER_ORGANIZATION_TERMS)
    organization_pattern = re.compile(
        r"(?:[가-힣A-Za-z0-9·&-]{2,}(?:기업|그룹|회사|주식회사|재단|협회|연합회|조합|병원|의원|클리닉|연구원|연구소|센터|방송|신문|일보|정당|법무법인))"
        r"|(?:대표이사|대표|연구위원|기자|앵커|의사|변호사|회계사|배우|가수|선수|감독|코치|국회의원|시의원|도의원)"
    )
    if organization_pattern.search(near) and not has_allowed_external:
        other_org_near = True

    # 등록된 실제 외부직책은 허용한다. 그 외 다른 대학·단과대·기관 소속은 제외한다.
    if not has_gspa and not has_allowed_external:
        if other_univ_near:
            return False, "다른 대학 소속"
        if other_snu_unit_near:
            return False, "서울대 다른 학부·대학원 소속"
        if other_org_near:
            return False, "다른 기업·연구원·기관·직업 소속"

    if has_gspa:
        return True, "행정대학원 소속 확인"
    if has_allowed_external:
        return True, "등록된 외부직책 확인"
    if has_snu_near and academic_hits >= 1:
        return True, "서울대 및 행정·정책 전공 근거 확인"
    return False, "행정대학원 소속 근거 부족"


def relevance_score(
    name: str,
    text: str,
    search_terms: list[str],
    exclude_terms: list[str],
    external_position: str = "",
) -> tuple[int, str]:
    lowered = text.lower()
    valid, reason = affiliation_match(name, text, search_terms, external_position)
    if not valid:
        return 0, reason
    score = 40
    if "서울대학교" in text or "서울대" in text:
        score += 15
    if "행정대학원" in text:
        score += 35
    if any(term.lower() in nearby_text(name, text, radius=220).lower() for term in _allowed_external_terms(external_position)):
        score += 25
    score += min(15, 3 * sum(1 for term in search_terms if term and term.lower() in lowered))
    score -= min(80, 40 * sum(1 for term in exclude_terms if term and term.lower() in lowered))
    return max(0, min(100, score)), reason


def build_queries(row: pd.Series) -> list[str]:
    name = str(row["name"]).strip()
    terms = [x.strip() for x in str(row.get("search_terms", "")).split(";") if x.strip()]
    affiliation = f'"{name}" ("서울대학교 행정대학원" OR "서울대 행정대학원" OR "행정대학원")'
    topic_part = " OR ".join(f'"{term}"' for term in terms[:6])
    topic = f'"{name}" ("서울대학교" OR "서울대") ({topic_part})' if topic_part else affiliation
    return list(dict.fromkeys([affiliation, topic]))


def build_institution_queries() -> list[str]:
    return [
        '"서울대학교 행정대학원"',
        '"서울대 행정대학원"',
        '("서울대학교 행정대학원" OR "서울대 행정대학원") (포럼 OR 세미나 OR 토론회 OR 발표 OR 연구 OR 협약 OR 논의)',
    ]


def fetch_feed(query: str, max_items: int = 100) -> list[dict]:
    url = "https://news.google.com/rss/search?q=" + quote(query) + "&hl=ko&gl=KR&ceid=KR:ko"
    feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0 (compatible; SNU-GSPA-Media-Monitor/2.0)"})
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
    df = pd.read_csv(ARTICLES_FILE, dtype=str, encoding="utf-8-sig").fillna("")
    for col in ARTICLE_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[ARTICLE_COLUMNS]


def make_row(target_name: str, title: str, summary: str, publisher: str, published_at: str, url: str,
             query: str, collected_at: str, score: int, review_status: str) -> dict:
    combined = f"{title} {summary}"
    ckey = canonical_key(title, published_at)
    mention_type = classify_type(combined)
    return {
        "article_id": article_id(target_name, ckey), "canonical_key": ckey,
        "professor_name": target_name, "published_at": published_at, "collected_at": collected_at,
        "title": title, "summary": summary, "publisher": publisher, "url": url,
        "search_query": query, "source": "Google News RSS", "mention_type": mention_type,
        "topic": classify_topics(combined), "relevance_score": score,
        "review_status": review_status, "media_weight": TYPE_WEIGHT.get(mention_type, 0.5),
    }


def clean_existing(existing: pd.DataFrame, professors: pd.DataFrame) -> pd.DataFrame:
    if existing.empty:
        return existing
    info = {row["name"]: row for _, row in professors.iterrows()}
    kept = []
    for _, row in existing.iterrows():
        name = str(row["professor_name"]).strip()
        combined = f"{row['title']} {row['summary']}"
        row = row.copy()
        row["topic"] = classify_topics(combined)
        row["mention_type"] = classify_type(combined)
        row["media_weight"] = TYPE_WEIGHT.get(row["mention_type"], 0.5)
        if name == "대학원 전체":
            if any(term in combined for term in GSPA_TERMS):
                row["relevance_score"] = 100
                row["review_status"] = "관련"
                kept.append(row)
            continue
        professor = info.get(name)
        if professor is None:
            continue
        terms = [x.strip() for x in str(professor["search_terms"]).split(";") if x.strip()]
        excludes = [x.strip() for x in str(professor["exclude_terms"]).split(";") if x.strip()]
        external_position = str(professor.get("external_position", "")).strip()
        score, _ = relevance_score(name, combined, terms, excludes, external_position)
        row["relevance_score"] = score
        row["review_status"] = "관련" if score >= 70 else ("검토 필요" if score >= 45 else "제외 후보")
        if score >= 45:
            kept.append(row)
    return pd.DataFrame(kept, columns=ARTICLE_COLUMNS) if kept else pd.DataFrame(columns=ARTICLE_COLUMNS)


def collect(max_items: int = 100, sleep_seconds: float = 0.15) -> tuple[int, int]:
    DATA_DIR.mkdir(exist_ok=True)
    professors = load_professors_file()
    existing = clean_existing(load_existing(), professors)
    known_ids = set(existing["article_id"].astype(str))
    rows: list[dict] = []
    failures = 0
    collected_at = datetime.now(timezone.utc).isoformat()

    for _, professor in professors.iterrows():
        name = professor["name"].strip()
        search_terms = [x.strip() for x in professor["search_terms"].split(";") if x.strip()]
        exclude_terms = [x.strip() for x in professor["exclude_terms"].split(";") if x.strip()]
        external_position = str(professor.get("external_position", "")).strip()
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
                score, _ = relevance_score(name, combined, search_terms, exclude_terms, external_position)
                if score < 45:
                    continue
                row = make_row(name, title, summary, publisher, published_at, url, query, collected_at,
                               score, "관련" if score >= 70 else "검토 필요")
                if row["article_id"] not in known_ids:
                    rows.append(row)
                    known_ids.add(row["article_id"])
            time.sleep(sleep_seconds)

    # 교수명이 제목·요약에 없어도 대학원 자체가 등장하는 기사 수집
    professor_names = professors["name"].tolist()
    for query in build_institution_queries():
        try:
            entries = fetch_feed(query, max_items=max_items)
        except Exception as exc:
            failures += 1
            print(f"[WARN] 대학원 전체 / {query}: {exc}")
            continue
        for entry in entries:
            title = clean_text(entry.get("title", ""))
            summary = clean_text(entry.get("summary", ""))
            publisher = clean_text(entry.get("source", {}).get("title", "")) or "미상"
            published_at = parse_date(entry.get("published", ""))
            url = str(entry.get("link", "")).strip()
            combined = f"{title} {summary}"
            if not title or not any(term in combined for term in GSPA_TERMS):
                continue
            matched_names = [name for name in professor_names if name in combined]
            validated_targets = []
            for target in matched_names:
                professor = professors.loc[professors["name"] == target].iloc[0]
                terms = _split_terms(professor.get("search_terms", ""))
                excludes = _split_terms(professor.get("exclude_terms", ""))
                external_position = str(professor.get("external_position", "")).strip()
                score, _ = relevance_score(target, combined, terms, excludes, external_position)
                if score >= 45:
                    validated_targets.append((target, score))
            targets = validated_targets or [("대학원 전체", 100)]
            for target, score in targets:
                row = make_row(target, title, summary, publisher, published_at, url, query, collected_at, score, "관련")
                if row["article_id"] not in known_ids:
                    rows.append(row)
                    known_ids.add(row["article_id"])
        time.sleep(sleep_seconds)

    updated = pd.concat([existing, pd.DataFrame(rows)], ignore_index=True) if rows else existing
    if not updated.empty:
        updated = updated.drop_duplicates(subset=["article_id"], keep="last")
        updated["published_at"] = pd.to_datetime(updated["published_at"], errors="coerce", utc=True)
        updated = updated.sort_values("published_at", ascending=False, na_position="last")
        updated["published_at"] = updated["published_at"].astype(str).replace("NaT", "")
    updated.to_csv(ARTICLES_FILE, index=False, encoding="utf-8-sig")
    return len(rows), failures


if __name__ == "__main__":
    new_count, failure_count = collect()
    print(f"Collection complete. New rows={new_count}, failed queries={failure_count}")
