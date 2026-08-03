from __future__ import annotations

import hashlib
import html
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import feedparser
import pandas as pd
import requests
import trafilatura
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROFESSORS_FILE = DATA_DIR / "professors.csv"
ARTICLES_FILE = DATA_DIR / "articles.csv"

ARTICLE_COLUMNS = [
    "article_id", "canonical_key", "professor_name", "published_at", "collected_at",
    "title", "summary", "body", "publisher", "url", "final_url", "search_query", "source",
    "body_status", "body_char_count", "mention_type", "topic", "relevance_score", "review_status", "media_weight",
]
PROFESSOR_COLUMNS = [
    "professor_id", "name_en", "name", "rank", "position", "status",
    "external_position", "research_areas", "research_categories",
    "search_terms", "exclude_terms", "known_affiliations", "strict_affiliation",
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


def _allowed_external_terms(external_position: str, known_affiliations: str = "") -> list[str]:
    """CSV에 등록된 현재·과거 외부직책 및 별도 소속 단서를 반환한다."""
    raw_values = _split_terms(external_position) + _split_terms(known_affiliations)
    terms: list[str] = []
    for text in raw_values:
        text = str(text or "").strip()
        if not text:
            continue
        terms.append(text)
        institution = re.sub(r"\s*(원장|소장|센터장|위원장|위원|교수|이사장|대표|주임).*$", "", text).strip()
        if len(institution) >= 3:
            terms.append(institution)
    return list(dict.fromkeys(terms))


def affiliation_match(
    name: str,
    text: str,
    search_terms: list[str],
    external_position: str = "",
    known_affiliations: str = "",
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
    allowed_external = _allowed_external_terms(external_position, known_affiliations)
    has_allowed_external = any(term.lower() in near_lower for term in allowed_external)

    # "고길곤 서울대 교수", "서울대 교수 고길곤", "서울대 고길곤 교수"처럼
    # 행정대학원 명칭이 생략된 통상적인 언론 표기도 명확한 긍정 근거로 인정한다.
    escaped_name = re.escape(name)
    snu_professor_patterns = [
        rf"{escaped_name}\s*(?:서울대학교|서울대)\s*교수",
        rf"(?:서울대학교|서울대)\s*교수\s*{escaped_name}",
        rf"(?:서울대학교|서울대)\s*{escaped_name}\s*교수",
    ]
    has_snu_professor = any(re.search(pattern, near, flags=re.IGNORECASE) for pattern in snu_professor_patterns)

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

    # 명시적인 행정대학원·서울대 교수 표기 또는 등록된 실제 외부직책은 우선 인정한다.
    # 같은 기사에 다른 기관 인사가 함께 언급돼도 해당 교수의 명확한 소속 근거가 있으면 제외하지 않는다.
    if has_gspa:
        return True, "행정대학원 소속 확인"
    if has_snu_professor:
        return True, "서울대 교수 소속 확인"
    if has_allowed_external:
        return True, "등록된 현재·과거 외부직책 확인"

    # 명확한 긍정 근거가 없을 때만 다른 대학·단과대·기관 소속을 배제한다.
    if not has_gspa and not has_allowed_external:
        if other_univ_near:
            return False, "다른 대학 소속"
        if other_snu_unit_near:
            return False, "서울대 다른 학부·대학원 소속"
        if other_org_near:
            return False, "다른 기업·연구원·기관·직업 소속"

    if has_snu_near and academic_hits >= 1:
        return True, "서울대 및 행정·정책 전공 근거 확인"
    return False, "행정대학원 소속 근거 부족"


def relevance_score(
    name: str,
    text: str,
    search_terms: list[str],
    exclude_terms: list[str],
    external_position: str = "",
    known_affiliations: str = "",
) -> tuple[int, str]:
    lowered = text.lower()
    valid, reason = affiliation_match(name, text, search_terms, external_position, known_affiliations)
    if not valid:
        return 0, reason
    score = 40
    if "서울대학교" in text or "서울대" in text:
        score += 15
    if "행정대학원" in text:
        score += 35
    # 명시적인 "서울대 교수" 표기와 등록된 외부직책은 기본 화면에서 숨겨지지 않도록
    # 관련 기사 기준(70점) 이상을 부여한다.
    if reason == "서울대 교수 소속 확인":
        score += 20
    if any(term.lower() in nearby_text(name, text, radius=220).lower() for term in _allowed_external_terms(external_position, known_affiliations)):
        score += 35
    score += min(15, 3 * sum(1 for term in search_terms if term and term.lower() in lowered))
    score -= min(80, 40 * sum(1 for term in exclude_terms if term and term.lower() in lowered))
    return max(0, min(100, score)), reason


def build_queries(row: pd.Series) -> list[str]:
    name = str(row["name"]).strip()
    terms = [x.strip() for x in str(row.get("search_terms", "")).split(";") if x.strip()]
    affiliation = f'"{name}" ("서울대학교 행정대학원" OR "서울대 행정대학원" OR "행정대학원")'
    topic_part = " OR ".join(f'"{term}"' for term in terms[:6])
    topic = f'"{name}" ("서울대학교" OR "서울대") ({topic_part})' if topic_part else affiliation
    broad = f'"{name}"'
    return list(dict.fromkeys([affiliation, topic, broad]))


def build_backfill_queries(row: pd.Series, start_year: int = 2018) -> list[str]:
    """검색 결과 상위 몇 건에 밀린 과거 기사를 연도별로 다시 찾는다.

    Google 일반 검색과 News RSS 결과 범위가 다르므로, 해당 교수의 누적 데이터가
    한 건도 없을 때만 연도별 검색을 수행한다.
    """
    name = str(row["name"]).strip()
    current_year = datetime.now(timezone.utc).year
    return [
        f'"{name}" ("서울대" OR "서울대학교" OR "행정대학원") after:{year}-01-01 before:{year + 1}-01-01'
        for year in range(start_year, current_year + 1)
    ]


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



REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
}

def _external_url_from_google_html(html_text: str, base_url: str) -> str:
    soup = BeautifulSoup(html_text or "", "html.parser")
    candidates = []
    for selector, attr in [("link[rel='canonical']", "href"), ("meta[property='og:url']", "content")]:
        node = soup.select_one(selector)
        if node and node.get(attr):
            candidates.append(node.get(attr))
    refresh = soup.select_one("meta[http-equiv='refresh']")
    if refresh and refresh.get("content"):
        match = re.search(r"url=(.+)$", refresh.get("content"), re.I)
        if match:
            candidates.append(match.group(1).strip(" '\""))
    for a in soup.select("a[href]"):
        candidates.append(urljoin(base_url, a.get("href")))
    for candidate in candidates:
        parsed = urlparse(candidate)
        host = parsed.netloc.lower()
        if parsed.scheme in {"http", "https"} and host and "google." not in host and "gstatic." not in host:
            return candidate
    return ""

def resolve_and_extract_body(url: str, timeout: int = 18) -> dict:
    result = {"final_url": url, "body": "", "body_status": "추출 실패", "body_char_count": 0}
    if not url:
        result["body_status"] = "URL 없음"
        return result
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        final_url = response.url
        html_text = response.text
        if "news.google." in urlparse(final_url).netloc.lower():
            external = _external_url_from_google_html(html_text, final_url)
            if external:
                response = requests.get(external, headers=REQUEST_HEADERS, timeout=timeout, allow_redirects=True)
                response.raise_for_status()
                final_url = response.url
                html_text = response.text
        result["final_url"] = final_url
        content_type = response.headers.get("content-type", "").lower()
        if "html" not in content_type and not html_text.lstrip().startswith("<"):
            result["body_status"] = "HTML 아님"
            return result
        body = trafilatura.extract(
            html_text, url=final_url, include_comments=False, include_tables=False,
            favor_precision=True, deduplicate=True, output_format="txt"
        ) or ""
        body = clean_text(body)
        if len(body) < 180:
            soup = BeautifulSoup(html_text, "html.parser")
            for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form"]):
                tag.decompose()
            container = soup.find("article") or soup.find("main") or soup.body
            paragraphs = [clean_text(x.get_text(" ")) for x in container.find_all("p")] if container else []
            fallback = " ".join(x for x in paragraphs if len(x) >= 20)
            if len(fallback) > len(body):
                body = fallback
        body = re.sub(r"\s+", " ", body).strip()[:50000]
        if len(body) >= 180:
            result.update(body=body, body_status="추출 성공", body_char_count=len(body))
        else:
            result.update(body=body, body_status="본문 부족", body_char_count=len(body))
    except requests.RequestException as exc:
        result["body_status"] = f"접속 실패: {type(exc).__name__}"
    except Exception as exc:
        result["body_status"] = f"추출 오류: {type(exc).__name__}"
    return result

def content_text(title: str, summary: str, body: str) -> str:
    return f"{title or ''} {summary or ''} {body or ''}".strip()

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


def make_row(target_name: str, title: str, summary: str, body: str, publisher: str, published_at: str, url: str, final_url: str,
             body_status: str, body_char_count: int, query: str, collected_at: str, score: int, review_status: str) -> dict:
    combined = content_text(title, summary, body)
    ckey = canonical_key(title, published_at)
    mention_type = classify_type(combined)
    return {
        "article_id": article_id(target_name, ckey), "canonical_key": ckey,
        "professor_name": target_name, "published_at": published_at, "collected_at": collected_at,
        "title": title, "summary": summary, "body": body, "publisher": publisher, "url": url, "final_url": final_url or url,
        "search_query": query, "source": "Google News RSS + 원문", "body_status": body_status, "body_char_count": body_char_count, "mention_type": mention_type,
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
        combined = content_text(row.get("title", ""), row.get("summary", ""), row.get("body", ""))
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
        known_affiliations = str(professor.get("known_affiliations", "")).strip()
        score, _ = relevance_score(name, combined, terms, excludes, external_position, known_affiliations)
        row["relevance_score"] = score
        row["review_status"] = "관련" if score >= 70 else ("검토 필요" if score >= 45 else "제외 후보")
        if score >= 45:
            kept.append(row)
    return pd.DataFrame(kept, columns=ARTICLE_COLUMNS) if kept else pd.DataFrame(columns=ARTICLE_COLUMNS)


def _entry_to_candidate(entry: dict, query: str) -> dict:
    return {
        "title": clean_text(entry.get("title", "")),
        "summary": clean_text(entry.get("summary", "")),
        "publisher": clean_text(entry.get("source", {}).get("title", "")) or "미상",
        "published_at": parse_date(entry.get("published", "")),
        "url": str(entry.get("link", "")).strip(),
        "query": query,
    }

def _candidate_key(candidate: dict) -> str:
    return candidate.get("url") or canonical_key(candidate.get("title", ""), candidate.get("published_at", ""))

def collect(max_items: int = 60, sleep_seconds: float = 0.05) -> tuple[int, int]:
    DATA_DIR.mkdir(exist_ok=True)
    professors = load_professors_file()
    existing = clean_existing(load_existing(), professors)
    collected_at = datetime.now(timezone.utc).isoformat()
    failures = 0

    professor_candidates: dict[str, dict[str, dict]] = {}
    professor_meta: dict[str, pd.Series] = {}
    for _, professor in professors.iterrows():
        name = professor["name"].strip()
        professor_meta[name] = professor
        pool: dict[str, dict] = {}
        existing_counts = existing["professor_name"].astype(str).value_counts().to_dict() if not existing.empty else {}
        queries = build_queries(professor)
        # 누적 기사가 거의 없는 교수는 과거 기사도 연도별로 보강한다.
        if int(existing_counts.get(name, 0)) < 5:
            queries += build_backfill_queries(professor)
        for query in list(dict.fromkeys(queries)):
            try:
                entries = fetch_feed(query, max_items=max_items)
            except Exception as exc:
                failures += 1
                print(f"[WARN] {name} / {query}: {exc}")
                continue
            for entry in entries:
                candidate = _entry_to_candidate(entry, query)
                if not candidate["title"] or not candidate["url"]:
                    continue
                if len(pool) < 500:
                    pool.setdefault(_candidate_key(candidate), candidate)
            time.sleep(sleep_seconds)
        professor_candidates[name] = pool

    institution_pool: dict[str, dict] = {}
    for query in build_institution_queries():
        try:
            entries = fetch_feed(query, max_items=max_items)
        except Exception as exc:
            failures += 1
            print(f"[WARN] 대학원 전체 / {query}: {exc}")
            continue
        for entry in entries:
            candidate = _entry_to_candidate(entry, query)
            if candidate["title"] and candidate["url"] and len(institution_pool) < 180:
                institution_pool.setdefault(_candidate_key(candidate), candidate)
        time.sleep(sleep_seconds)

    all_candidates: dict[str, dict] = {}
    for pool in professor_candidates.values():
        all_candidates.update(pool)
    all_candidates.update(institution_pool)

    extraction_cache: dict[str, dict] = {}
    urls = [c["url"] for c in all_candidates.values() if c.get("url")]
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(resolve_and_extract_body, url): url for url in dict.fromkeys(urls)}
        for future in as_completed(futures):
            url = futures[future]
            try:
                extraction_cache[url] = future.result()
            except Exception as exc:
                extraction_cache[url] = {"final_url": url, "body": "", "body_status": f"추출 오류: {type(exc).__name__}", "body_char_count": 0}

    rows: list[dict] = []
    known_ids: set[str] = set()
    for name, pool in professor_candidates.items():
        professor = professor_meta[name]
        terms = _split_terms(professor.get("search_terms", ""))
        excludes = _split_terms(professor.get("exclude_terms", ""))
        external_position = str(professor.get("external_position", "")).strip()
        known_affiliations = str(professor.get("known_affiliations", "")).strip()
        for candidate in pool.values():
            ext = extraction_cache.get(candidate["url"], {"final_url": candidate["url"], "body": "", "body_status": "미수집", "body_char_count": 0})
            combined = content_text(candidate["title"], candidate["summary"], ext["body"])
            score, _ = relevance_score(name, combined, terms, excludes, external_position, known_affiliations)
            if score < 45:
                continue
            row = make_row(name, candidate["title"], candidate["summary"], ext["body"], candidate["publisher"],
                           candidate["published_at"], candidate["url"], ext["final_url"], ext["body_status"],
                           ext["body_char_count"], candidate["query"], collected_at, score,
                           "관련" if score >= 70 else "검토 필요")
            if row["article_id"] not in known_ids:
                rows.append(row); known_ids.add(row["article_id"])

    professor_names = professors["name"].tolist()
    for candidate in institution_pool.values():
        ext = extraction_cache.get(candidate["url"], {"final_url": candidate["url"], "body": "", "body_status": "미수집", "body_char_count": 0})
        combined = content_text(candidate["title"], candidate["summary"], ext["body"])
        if not any(term in combined for term in GSPA_TERMS):
            continue
        validated = []
        for target in [n for n in professor_names if n in combined]:
            professor = professor_meta[target]
            score, _ = relevance_score(target, combined, _split_terms(professor.get("search_terms", "")),
                                       _split_terms(professor.get("exclude_terms", "")),
                                       str(professor.get("external_position", "")).strip(),
                                       str(professor.get("known_affiliations", "")).strip())
            if score >= 45:
                validated.append((target, score))
        targets = validated or [("대학원 전체", 100)]
        for target, score in targets:
            row = make_row(target, candidate["title"], candidate["summary"], ext["body"], candidate["publisher"],
                           candidate["published_at"], candidate["url"], ext["final_url"], ext["body_status"],
                           ext["body_char_count"], candidate["query"], collected_at, score, "관련")
            if row["article_id"] not in known_ids:
                rows.append(row); known_ids.add(row["article_id"])

    fresh = pd.DataFrame(rows, columns=ARTICLE_COLUMNS) if rows else pd.DataFrame(columns=ARTICLE_COLUMNS)
    # 기존 누적 데이터는 재검증하여 유지하고, 이번 수집에서 같은 기사를 다시 찾으면 본문 데이터로 갱신한다.
    updated = pd.concat([existing, fresh], ignore_index=True) if not existing.empty or not fresh.empty else fresh
    if not updated.empty:
        updated = updated.drop_duplicates(subset=["article_id"], keep="last")
        updated["published_at"] = pd.to_datetime(updated["published_at"], errors="coerce", utc=True)
        updated = updated.sort_values("published_at", ascending=False, na_position="last")
        updated["published_at"] = updated["published_at"].astype(str).replace("NaT", "")
    updated.to_csv(ARTICLES_FILE, index=False, encoding="utf-8-sig")
    return len(updated), failures


if __name__ == "__main__":
    new_count, failure_count = collect()
    print(f"Collection complete. New rows={new_count}, failed queries={failure_count}")
