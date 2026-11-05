
import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote, urlparse, parse_qs, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "jobs.json"

# 기존 대시보드의 세 가지 카테고리 유지
QUERIES = {
    "정유·화학": [
        "정유 석유화학 공정기술 채용 한국",
        "화학 생산기술 공정엔지니어 경력 채용 국내",
        "정유 석유화학 신사업개발 채용",
        "에너지 화학 산업 경력 우대 채용 사업개발",
        "site:jobkorea.co.kr 정유 화학 경력 우대 채용",
        "site:saramin.co.kr 석유화학 공정 경력 채용",
        "site:linkedin.com/jobs Korea refinery petrochemical process engineer",
        "에너지 화학 산업 리서치 애널리스트 채용",
        "에너지 석유화학 프로젝트 파이낸싱 투자심사 채용",
        "정유 화학 산업 전략 컨설턴트 채용",
        "energy chemicals strategy consulting Seoul careers",
    ],
    "탄소포집": [
        "CCS CCUS 탄소포집 채용 대한민국",
        "탄소포집 CCUS 경험 우대 채용",
        "CCUS 사업개발 프로젝트 엔지니어 채용",
        "탄소포집 수소 저탄소 기술 사업개발 채용",
        "CCUS 탄소중립 투자 금융 채용",
        "탄소포집 탈탄소 컨설팅 채용",
        "site:linkedin.com/jobs Korea carbon capture CCUS",
        "site:jobkorea.co.kr CCUS CCS 채용",
        "carbon capture CCS consulting Seoul hiring",
    ],
    "공정안전": [
        "공정안전 PSM HAZOP 경력 채용 국내",
        "LOPA HAZOP 공정안전 우대 채용",
        "Process Safety Engineer Korea hiring",
        "공정안전 위험성평가 기술실사 컨설팅 채용",
        "site:saramin.co.kr PSM HAZOP 채용",
        "site:jobkorea.co.kr 공정안전 경력 채용",
    ],
}

KEYWORDS = {
    "정유·화학": [
        "정유", "석유화학", "화학", "공정기술",
        "생산기술", "process engineer", "refinery",
        "petrochemical", "energy", "chemicals",
    ],
    "탄소포집": [
        "ccs", "ccus", "탄소포집", "탄소저감",
        "수소", "carbon capture", "decarbonization",
    ],
    "공정안전": [
        "공정안전", "psm", "hazop", "lopa",
        "process safety", "위험성평가",
    ],
}

SKILLS = [
    "ccs", "ccus", "탄소포집", "수소",
    "hazop", "lopa", "psm", "공정안전",
    "공정기술", "생산기술", "moc",
    "process safety", "process engineer",
    "석유화학", "정유",
]

JOB_TERMS = [
    "채용", "모집", "입사지원", "recruitment",
    "recruiting", "hiring", "job opening",
    "job posting", "apply now", "careers",
    "career opportunity", "경력직",
    "우대사항", "자격요건",
]

BAD_TERMS = [
    "ultimate guide", "what is", "how to",
    "tutorial", "교육과정", "교육안내",
    "강의", "자격증", "합격자소서",
    "면접후기", "연봉정보", "뉴스",
    "블로그", "가이드", "위키", "논문",
    "보고서", "세미나", "웨비나",
    "기술자료", "백서",
]

BAD_HOSTS = [
    "youtube.com", "wikipedia.org",
    "namu.wiki", "tobeprocessengineer.com",
    "medium.com", "tistory.com",
    "blog.naver.com", "news.naver.com",
]

JOB_HOST_HINTS = [
    "jobkorea.co.kr", "saramin.co.kr",
    "wanted.co.kr", "linkedin.com/jobs",
    "indeed.com", "incruit.com",
    "recruit", "career", "jobs",
    "greenhouse.io", "lever.co",
    "workdayjobs.com",
]

KOREA_TERMS = [
    "대한민국", "한국", "국내", "서울",
    "경기", "인천", "대전", "세종",
    "충북", "충남", "전북", "전남",
    "경북", "경남", "부산", "울산",
    "대구", "광주", "포항", "여수",
    "대산", "온산", "평택", "판교",
    "송도", "seoul", "south korea",
    "republic of korea", "korea",
    "ulsan", "busan", "incheon",
    "pohang", "yeosu",
]

FOREIGN_ONLY = [
    "united states", "united kingdom",
    "canada", "singapore", "australia",
    "dubai", "remote - us",
    "미국 근무", "캐나다 근무", "싱가포르 근무",
]

FINANCE = [
    "금융", "투자", "증권", "자산운용",
    "pf", "project finance", "investment",
    "equity research", "애널리스트",
    "리서치", "인프라펀드",
]

CONSULTING = [
    "컨설팅", "컨설턴트", "consulting",
    "consultant", "advisory",
    "실사", "due diligence",
]


def canonical(url):
    p = urlparse(url)

    if p.scheme not in ("http", "https") or not p.netloc:
        return ""

    if p.netloc.lower().endswith("bing.com") and p.path.startswith("/ck/"):
        return ""

    q = [
        (k, v)
        for k, vs in parse_qs(p.query).items()
        for v in vs
        if not k.lower().startswith(("utm_", "fbclid", "gclid"))
    ]

    return urlunparse((
        p.scheme,
        p.netloc.lower(),
        p.path.rstrip("/"),
        "",
        urlencode(q),
        "",
    ))


def search(query):
    url = "https://www.bing.com/search?format=rss&q=" + quote(query)

    r = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; PublicJobsMonitor/3.0)"
        },
    )

    r.raise_for_status()

    soup = BeautifulSoup(r.content, "xml")

    if soup.find("rss") is None:
        raise ValueError("RSS 응답이 아닙니다")

    for item in soup.find_all("item"):
        title = item.find("title")
        link = item.find("link")
        desc = item.find("description")

        if title and link:
            description = BeautifulSoup(
                desc.get_text(" ", strip=True) if desc else "",
                "html.parser",
            ).get_text(" ", strip=True)

            yield (
                title.get_text(" ", strip=True),
                canonical(link.get_text(" ", strip=True)),
                description,
            )


def relevant(title, desc, url, category):
    t = title.lower()
    d = desc.lower()
    combined = t + " " + d

    hostpath = (urlparse(url).netloc + urlparse(url).path).lower()

    if any(x in hostpath for x in BAD_HOSTS):
        return False

    if any(x in t for x in BAD_TERMS):
        return False

    if not any(x in combined for x in KEYWORDS[category]):
        return False

    if not any(x in combined for x in JOB_TERMS):
        return False

    if not (
        any(x in t for x in JOB_TERMS)
        or any(x in hostpath for x in JOB_HOST_HINTS)
    ):
        return False

    if (
        any(x in combined for x in FOREIGN_ONLY)
        and not any(x in combined for x in KOREA_TERMS)
    ):
        return False

    return True


def location_status(title, desc):
    combined = (title + " " + desc).lower()

    if any(x in combined for x in KOREA_TERMS):
        return "국내 근무지 추정 · 원문 확인 필요"

    return "근무지 미확인 · 국내 여부 확인 필요"


def sector(title, desc):
    s = (title + " " + desc).lower()

    if any(x in s for x in FINANCE):
        return "금융·투자"

    if any(x in s for x in CONSULTING):
        return "컨설팅"

    return "산업·기술"


def fit(text):
    hits = [x for x in SKILLS if x in text.lower()]

    if len(hits) >= 3:
        score = "상"
    elif hits:
        score = "중"
    else:
        score = "하"

    return score, hits


def run():
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    try:
        old = json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {"jobs": []}

    jobs = {}

    # 기존 데이터 중 오분류된 항목 제거
    for j in old.get("jobs", []):
        url = canonical(j.get("url", ""))
        category = j.get("category", "")

        if (
            url
            and category in QUERIES
            and relevant(
                j.get("title", ""),
                j.get("description", ""),
                url,
                category,
            )
        ):
            jobs[url] = j

    errors = []
    seen = set()
    discovered = 0

    for cat, queries in QUERIES.items():
        for q in queries:
            try:
                for title, url, desc in search(q):
                    if not url:
                        continue

                    if not relevant(title, desc, url, cat):
                        continue

                    if url in seen:
                        continue

                    seen.add(url)

                    prev = jobs.get(url, {})
                    score, hits = fit(title + " " + desc)

                    changed = bool(
                        prev and (
                            prev.get("title") != title
                            or prev.get("description") != desc
                        )
                    )

                    jobs[url] = {
                        **prev,
                        "url": url,
                        "title": title[:250],
                        "description": desc[:700],
                        "category": prev.get("category", cat),
                        "sector": sector(title, desc),
                        "location_check": location_status(title, desc),
                        "source": urlparse(url).netloc,
                        "fit": score,
                        "matched_skills": hits,
                        "first_seen": prev.get("first_seen", now),
                        "last_seen": now,
                        "changed_at": (
                            now if changed else prev.get("changed_at")
                        ),
                        "status": (
                            "검색 발견 · 국내 근무 및 "
                            "모집 여부 원문 확인 필요"
                        ),
                    }

                    discovered += 1

            except Exception as exc:
                errors.append(
                    f"{q}: {type(exc).__name__}: {str(exc)[:140]}"
                )

            time.sleep(0.4)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    kept = []

    for j in jobs.values():
        try:
            last = datetime.fromisoformat(
                j["last_seen"].replace("Z", "+00:00")
            )
        except (KeyError, ValueError):
            continue

        if last >= cutoff:
            j["seen_in_latest_run"] = j["url"] in seen
            kept.append(j)

    kept.sort(
        key=lambda j: j.get("first_seen", ""),
        reverse=True,
    )

    output = {
        "updated_at": now,
        "discovered_this_run": discovered,
        "queries_attempted": sum(
            map(len, QUERIES.values())
        ),
        "errors": errors,
        "jobs": kept[:1000],
        "notice": (
            "한국 근무지와 정유·화학/CCUS/공정안전 경험 "
            "연관성을 검색한 후보입니다. 금융·컨설팅 포함. "
            "실제 국내 근무 여부, 모집 중 여부, "
            "마감일 및 우대조건은 원문 확인이 필요합니다."
        ),
    }

    DATA.parent.mkdir(parents=True, exist_ok=True)

    DATA.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f'검색 후보 {discovered}개, '
        f'보관 {len(output["jobs"])}개, '
        f'오류 {len(errors)}개'
    )

    if errors:
        print("\n".join(errors))


if __name__ == "__main__":
    run()

