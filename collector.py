
import json
import re
import time
import html
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import (
    urlencode,
    urlparse,
    parse_qsl,
    urlunparse,
)

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "jobs.json"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 "
        "(compatible; JobPostingMonitor/3.0)"
    )
})

SITES = {
    "사람인": "saramin.co.kr",
    "자소설닷컴": "jasoseol.com",
    "LinkedIn": "linkedin.com/jobs",
    "리멤버": "career.rememberapp.co.kr",
    "한국벤처캐피탈협회": "kvca.or.kr",
    "금융투자협회": "kofia.or.kr",
    "잡코리아": "jobkorea.co.kr",
    "원티드": "wanted.co.kr",
}

CATEGORIES = {
    "정유·화학": [
        "정유 공정기술",
        "석유화학 생산기술",
        "화학 공정엔지니어",
        "정유 화학 경력 우대",
        "에너지 화학 사업개발",
    ],
    "탄소포집": [
        "CCS CCUS",
        "탄소포집 사업개발",
        "carbon capture",
        "수소 저탄소 사업",
    ],
    "공정안전": [
        "공정안전 PSM",
        "HAZOP LOPA",
        "process safety",
        "공정 위험성평가",
    ],
    "금융·컨설팅": [
        "정유 화학 투자심사",
        "에너지 산업 리서치",
        "CCUS 투자",
        "에너지 전략 컨설팅",
        "에너지 기술실사",
    ],
}

CORE = (
    "정유",
    "석유화학",
    "화학",
    "공정기술",
    "생산기술",
    "탄소포집",
    "ccs",
    "ccus",
    "carbon capture",
    "hazop",
    "lopa",
    "psm",
    "process safety",
    "수소",
    "hydrogen",
    "refinery",
    "petrochemical",
    "process engineering",
    "decarbonization",
)

FINANCE = (
    "투자",
    "금융",
    "컨설팅",
    "consulting",
    "investment",
    "리서치",
    "심사역",
    "project finance",
    "due diligence",
    "애널리스트",
)

JOB_WORDS = (
    "채용",
    "모집",
    "경력",
    "신입",
    "recruit",
    "hiring",
    "job",
    "career",
    "position",
)

BAD_TITLES = (
    "ultimate guide",
    "what is",
    "tutorial",
    "교육과정",
    "세미나",
    "블로그",
    "뉴스",
    "논문",
    "가이드",
    "강의",
    "위키",
    "면접후기",
)

KOREA_CODES = {
    "kr",
    "kor",
    "korea",
    "south korea",
    "republic of korea",
    "대한민국",
    "한국",
}

KOREA_PLACES = (
    "서울",
    "경기",
    "인천",
    "부산",
    "울산",
    "대구",
    "광주",
    "대전",
    "세종",
    "충북",
    "충남",
    "전북",
    "전남",
    "경북",
    "경남",
    "제주",
    "포항",
    "여수",
    "대산",
    "온산",
    "판교",
    "평택",
    "seoul",
    "ulsan",
    "busan",
    "incheon",
    "pohang",
    "yeosu",
)


def clean_url(url):
    p = urlparse(url)

    if p.scheme not in ("http", "https"):
        return ""

    if not p.netloc:
        return ""

    query = [
        (k, v)
        for k, v in parse_qsl(p.query)
        if not k.lower().startswith(
            ("utm_", "fbclid", "gclid")
        )
    ]

    return urlunparse((
        p.scheme,
        p.netloc.lower(),
        p.path.rstrip("/"),
        "",
        urlencode(query),
        "",
    ))


def rss_search(query):
    response = SESSION.get(
        "https://www.bing.com/search",
        params={
            "format": "rss",
            "q": query,
        },
        timeout=20,
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.content,
        "xml",
    )

    if soup.find("rss") is None:
        raise ValueError(
            "검색엔진에서 RSS를 반환하지 않았습니다."
        )

    results = []

    for item in soup.find_all("item"):
        title_tag = item.find("title")
        link_tag = item.find("link")
        desc_tag = item.find("description")

        if not title_tag or not link_tag:
            continue

        title = title_tag.get_text(
            " ", strip=True
        )

        url = clean_url(
            link_tag.get_text(" ", strip=True)
        )

        description = ""

        if desc_tag:
            description = BeautifulSoup(
                html.unescape(
                    desc_tag.get_text(
                        " ", strip=True
                    )
                ),
                "html.parser",
            ).get_text(" ", strip=True)

        if url:
            results.append({
                "title": title,
                "url": url,
                "description": description,
            })

    return results


def find_job_postings(obj):
    found = []

    if isinstance(obj, list):
        for item in obj:
            found.extend(
                find_job_postings(item)
            )

    elif isinstance(obj, dict):
        types = obj.get("@type", [])

        if isinstance(types, str):
            types = [types]

        if any(
            str(t).lower().endswith("jobposting")
            for t in types
        ):
            found.append(obj)

        for value in obj.values():
            if isinstance(value, (dict, list)):
                found.extend(
                    find_job_postings(value)
                )

    return found


def is_korean_location(job):
    locations = job.get(
        "jobLocation", []
    )

    if isinstance(locations, dict):
        locations = [locations]

    for location in locations:
        if not isinstance(location, dict):
            continue

        address = location.get(
            "address", {}
        )

        if isinstance(address, str):
            text = address.lower()

            if any(
                place in text
                for place in KOREA_PLACES
            ):
                return True

            continue

        if not isinstance(address, dict):
            continue

        country = address.get(
            "addressCountry", ""
        )

        if isinstance(country, dict):
            country = country.get(
                "name", ""
            )

        if str(country).strip().lower() in KOREA_CODES:
            return True

        address_text = " ".join(
            str(v)
            for v in address.values()
        ).lower()

        if any(
            place in address_text
            for place in KOREA_PLACES
        ):
            return True

    return False


def get_employer(job):
    employer = job.get(
        "hiringOrganization", {}
    )

    if isinstance(employer, list):
        employer = (
            employer[0]
            if employer
            else {}
        )

    if isinstance(employer, dict):
        return str(
            employer.get("name", "")
        ).strip()

    return str(employer).strip()


def parse_deadline(value):
    if not value:
        return None

    try:
        date = datetime.fromisoformat(
            str(value).replace(
                "Z", "+00:00"
            )
        )

        if date.tzinfo is None:
            date = date.replace(
                tzinfo=timezone.utc
            )

        return date

    except ValueError:
        return None


def determine_status(job):
    deadline = job.get(
        "validThrough", ""
    )

    parsed = parse_deadline(deadline)

    if parsed:
        if parsed < datetime.now(
            timezone.utc
        ):
            return "마감"

        return (
            "마감일 미경과 · "
            "모집 여부 확인 필요"
        )

    return "마감일 미확인"


def relevant_to_user(title, description):
    text = (
        title + " " + description
    ).lower()

    matches = [
        word
        for word in CORE + FINANCE
        if word in text
    ]

    # 금융·컨설팅 공고라도
    # 에너지·화학·CCUS 관련성이 필요
    industry_matches = [
        word
        for word in CORE
        if word in text
    ]

    return bool(
        industry_matches
    ), matches


def verify_job_posting(url):
    try:
        response = SESSION.get(
            url,
            timeout=15,
        )

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type", ""
        ).lower()

        if (
            "html" not in content_type
            and "xhtml" not in content_type
        ):
            return None, "HTML 아님"

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        postings = []

        for script in soup.select(
            'script[type="application/ld+json"]'
        ):
            raw = script.get_text(
                strip=True
            )

            try:
                parsed = json.loads(raw)
            except (ValueError, TypeError):
                continue

            postings.extend(
                find_job_postings(parsed)
            )

        if not postings:
            return None, "JobPosting 데이터 없음"

        for job in postings:
            title = str(
                job.get("title", "")
            ).strip()

            description = BeautifulSoup(
                str(
                    job.get(
                        "description", ""
                    )
                ),
                "html.parser",
            ).get_text(" ", strip=True)

            employer = get_employer(job)

            if not title or not description:
                continue

            if not employer:
                continue

            if not is_korean_location(job):
                continue

            related, matches = relevant_to_user(
                title,
                description,
            )

            if not related:
                continue

            if any(
                bad in title.lower()
                for bad in BAD_TITLES
            ):
                continue

            deadline = job.get(
                "validThrough", ""
            )

            return {
                "title": title,
                "description": description[:1200],
                "employer": employer,
                "deadline": str(deadline),
                "status": determine_status(job),
                "matched_skills": matches,
                "location_check": (
                    "대한민국 근무지 확인"
                ),
                "verified": True,
            }, "검증 성공"

        return None, "국내 근무지·직무·기업 검증 실패"

    except requests.RequestException:
        return None, "원문 접근 실패"

    except Exception as exc:
        return None, (
            "원문 처리 오류: "
            + type(exc).__name__
        )


def fit_score(matches):
    count = len(matches)

    if count >= 3:
        return "상"

    if count >= 1:
        return "중"

    return "하"


def build_queries():
    queries = []

    for category, terms in CATEGORIES.items():
        for term in terms:
            queries.append((
                category,
                term + " 채용 2026 대한민국",
                "전체 웹",
            ))

            queries.append((
                category,
                term + " 2026 마감 채용",
                "과거 공고",
            ))

        # 사이트별 검색
        for site_name, domain in SITES.items():
            for term in (
                terms[0],
                terms[-1],
            ):
                queries.append((
                    category,
                    (
                        f"site:{domain} "
                        f"{term} 채용 2026"
                    ),
                    site_name,
                ))

    return queries


def main():
    now = datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")

    try:
        previous = json.loads(
            OUT.read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError):
        previous = {}

    # 이전 데이터 중 검증된 공고만 보존
    archive = {}

    for job in previous.get(
        "jobs", []
    ):
        if (
            isinstance(job, dict)
            and job.get("url")
            and job.get("verified") is True
        ):
            archive[job["url"]] = job

    diagnostics = {
        "queries": 0,
        "rss_results": 0,
        "candidates": 0,
        "verified": 0,
        "rejected": {},
        "sources": {},
    }

    errors = []
    seen = set()

    queries = build_queries()

    for category, query, source in queries:
        diagnostics["queries"] += 1

        diagnostics["sources"].setdefault(
            source,
            {
                "queries": 0,
                "results": 0,
                "verified": 0,
            },
        )

        diagnostics["sources"][source][
            "queries"
        ] += 1

        try:
            results = rss_search(
                query
            )

            diagnostics["rss_results"] += len(
                results
            )

            diagnostics["sources"][source][
                "results"
            ] += len(results)

            for result in results:
                url = result["url"]

                if url in seen:
                    continue

                seen.add(url)

                diagnostics["candidates"] += 1

                verified, reason = (
                    verify_job_posting(url)
                )

                if verified is None:
                    diagnostics["rejected"][
                        reason
                    ] = (
                        diagnostics["rejected"].get(
                            reason, 0
                        ) + 1
                    )
                    continue

                diagnostics["verified"] += 1

                diagnostics["sources"][source][
                    "verified"
                ] += 1

                old = archive.get(
                    url, {}
                )

                archive[url] = {
                    **old,
                    "url": url,
                    "title": verified["title"],
                    "description": verified[
                        "description"
                    ],
                    "employer": verified[
                        "employer"
                    ],
                    "category": category,
                    "source": urlparse(
                        url
                    ).netloc,
                    "discovered_via": source,
                    "fit": fit_score(
                        verified[
                            "matched_skills"
                        ]
                    ),
                    "matched_skills": verified[
                        "matched_skills"
                    ],
                    "first_seen": old.get(
                        "first_seen", now
                    ),
                    "last_seen": now,
                    "seen_in_latest_run": True,
                    "location_check": verified[
                        "location_check"
                    ],
                    "deadline": verified[
                        "deadline"
                    ],
                    "status": verified[
                        "status"
                    ],
                    "verified": True,
                    "historical": True,
                }

        except Exception as exc:
            errors.append(
                f"{source} / {query}: "
                f"{type(exc).__name__}: "
                f"{str(exc)[:120]}"
            )

        time.sleep(0.15)

    for url, job in archive.items():
        if url not in {
            j["url"]
            for j in archive.values()
            if j.get("last_seen") == now
        }:
            job["seen_in_latest_run"] = False

    jobs = sorted(
        archive.values(),
        key=lambda j: j.get(
            "first_seen", ""
        ),
        reverse=True,
    )

    result = {
        "updated_at": now,
        "discovered_this_run": diagnostics[
            "verified"
        ],
        "queries_attempted": diagnostics[
            "queries"
        ],
        "errors": errors,
        "diagnostics": diagnostics,
        "jobs": jobs,
        "notice": (
            "원문 JobPosting 구조화 데이터에서 "
            "기업명·직무·대한민국 근무지를 "
            "확인한 채용공고만 표시합니다. "
            "마감일이 미래여도 모집 중임을 "
            "보장하지는 않습니다. "
            "2026년 과거 공고도 보관합니다."
        ),
    }

    OUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUT.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "검색:", diagnostics["queries"],
        "RSS 결과:", diagnostics["rss_results"],
        "검증 후보:", diagnostics["candidates"],
        "실제 공고 검증:", diagnostics["verified"],
        "오류:", len(errors),
    )

    print(
        "검증 제외 이유:",
        json.dumps(
            diagnostics["rejected"],
            ensure_ascii=False,
        ),
    )

    print(
        "사이트별 결과:",
        json.dumps(
            diagnostics["sources"],
            ensure_ascii=False,
        ),
    )

    for error in errors[:10]:
        print("ERROR:", error)


if __name__ == "__main__":
    main()
