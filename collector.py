
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse, urlencode, parse_qsl

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "jobs.json"

S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; PublicJobMonitor/4.0)"
})

SITES = {
    "사람인": "saramin.co.kr",
    "자소설닷컴": "secure.jasoseol.com",
    "LinkedIn": "linkedin.com/jobs",
    "리멤버": "career.rememberapp.co.kr",
    "한국벤처캐피탈협회": "kvca.or.kr",
    "금융투자협회": "kofia.or.kr",
    "잡코리아": "jobkorea.co.kr",
    "원티드": "wanted.co.kr",
}

TOPICS = {
    "정유·화학": [
        "정유 공정기술",
        "석유화학 생산기술",
        "화학 사업개발",
        "refinery process engineer",
    ],
    "탄소포집": [
        "CCUS 사업개발",
        "CCS 탄소포집",
        "carbon capture Korea",
        "수소 저탄소 사업",
    ],
    "공정안전": [
        "공정안전 PSM",
        "HAZOP LOPA",
        "process safety Korea",
        "위험성평가 공정안전",
    ],
    "금융·컨설팅": [
        "에너지 화학 투자심사",
        "CCUS 투자",
        "에너지 산업 리서치",
        "석유화학 전략 컨설팅",
    ],
}

INDUSTRY = [
    "정유", "석유화학", "화학공정", "화학산업",
    "탄소포집", "ccus", "ccs", "carbon capture",
    "hazop", "lopa", "psm", "공정안전",
    "process safety", "refinery", "petrochemical",
    "process engineering", "수소생산",
    "hydrogen production", "탈탄소",
    "decarbonization", "에너지 산업",
    "energy sector", "oil and gas", "oil & gas",
]

ROLE = [
    "공정기술", "생산기술", "공정엔지니어",
    "사업개발", "신사업", "기술기획", "프로젝트",
    "process engineer", "process safety",
    "business development", "investment",
    "투자심사", "기술실사", "리서치",
    "애널리스트", "컨설팅", "consulting",
    "engineer", "엔지니어", "안전관리",
    "위험성평가",
]

KOREA = [
    "대한민국", "한국", "서울", "경기도", "경기",
    "인천", "부산", "울산", "대구", "광주",
    "대전", "세종", "충북", "충남", "전북",
    "전남", "경북", "경남", "제주", "포항",
    "여수", "대산", "온산", "평택", "판교",
    "seoul", "south korea", "republic of korea",
    "korea", "ulsan", "busan", "incheon",
    "pohang", "yeosu",
]

BAD = [
    "블로그", "뉴스", "기사", "교육과정",
    "강의", "세미나", "가이드", "tutorial",
    "ultimate guide", "what is", "위키",
    "면접후기", "자소서 작성법",
]

NOW = datetime.now(timezone.utc)


def canonical(url):
    p = urlparse(url)

    if p.scheme not in ("https", "http") or not p.netloc:
        return ""

    q = [
        (k, v)
        for k, v in parse_qsl(p.query)
        if not k.lower().startswith(
            ("utm_", "gclid", "fbclid", "campaign", "channel")
        )
    ]

    return urlunparse((
        p.scheme,
        p.netloc.lower(),
        p.path.rstrip("/"),
        "",
        urlencode(q),
        "",
    ))


def search(q):
    r = S.get(
        "https://www.bing.com/search",
        params={"format": "rss", "q": q},
        timeout=20,
    )
    r.raise_for_status()

    soup = BeautifulSoup(r.content, "xml")

    if not soup.find("rss"):
        raise ValueError("RSS format unavailable")

    out = []

    for item in soup.find_all("item"):
        def field(name):
            el = item.find(name)
            return el.get_text(" ", strip=True) if el else ""

        out.append((
            field("title"),
            canonical(field("link")),
        ))

    return out


def text_of(soup):
    for node in soup([
        "script", "style", "nav", "footer", "header"
    ]):
        node.decompose()

    return soup.get_text(" ", strip=True)


def ld_jobs(obj):
    if isinstance(obj, list):
        for x in obj:
            yield from ld_jobs(x)

    elif isinstance(obj, dict):
        typ = obj.get("@type", [])

        if isinstance(typ, str):
            typ = [typ]

        if any(
            str(t).lower().endswith("jobposting")
            for t in typ
        ):
            yield obj

        for val in obj.values():
            if isinstance(val, (list, dict)):
                yield from ld_jobs(val)


def country_from_ld(job):
    locations = job.get("jobLocation", [])

    if isinstance(locations, dict):
        locations = [locations]

    for loc in locations:
        if not isinstance(loc, dict):
            continue

        addr = loc.get("address", {})

        if isinstance(addr, dict):
            country = addr.get("addressCountry", "")

            if isinstance(country, dict):
                country = country.get("name", "")

            if str(country).strip().lower() in (
                "kr", "kor", "korea", "south korea",
                "republic of korea", "대한민국", "한국"
            ):
                return True

            if any(
                k in str(addr).lower()
                for k in KOREA
            ):
                return True

        elif any(
            k in str(addr).lower()
            for k in KOREA
        ):
            return True

    return False


def date_hint(s):
    m = re.search(
        r"(?<!\d)(20\d{2})[.\-/]\s*"
        r"(0?[1-9]|1[0-2])[.\-/]\s*"
        r"(0?[1-9]|[12]\d|3[01])(?!\d)",
        s,
    )

    if not m:
        return ""

    return (
        f"{int(m[1]):04d}-"
        f"{int(m[2]):02d}-"
        f"{int(m[3]):02d}"
    )


def status(deadline):
    if not deadline:
        return "마감일 미확인"

    try:
        d = datetime.fromisoformat(
            str(deadline).replace("Z", "+00:00")
        )

        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)

        return (
            "마감"
            if d < NOW
            else "마감일 미경과 · 모집 여부 확인 필요"
        )

    except ValueError:
        return "마감일 미확인"


def validate(url):
    try:
        r = S.get(url, timeout=14)
        r.raise_for_status()

        if "html" not in r.headers.get(
            "Content-Type", ""
        ).lower():
            return None, "HTML 아님"

        soup = BeautifulSoup(r.text, "html.parser")
        structured = []

        for script in soup.select(
            'script[type="application/ld+json"]'
        ):
            try:
                structured.extend(
                    ld_jobs(json.loads(script.get_text()))
                )
            except (ValueError, TypeError):
                pass

        # 1. 구조화된 채용공고 검증
        for j in structured:
            title = str(j.get("title", "")).strip()

            desc = BeautifulSoup(
                str(j.get("description", "")),
                "html.parser",
            ).get_text(" ", strip=True)

            org = j.get("hiringOrganization", {})

            employer = (
                org.get("name", "")
                if isinstance(org, dict)
                else str(org)
            )

            if (
                title
                and employer
                and desc
                and country_from_ld(j)
            ):
                return {
                    "title": title,
                    "description": desc[:1600],
                    "employer": employer,
                    "deadline": str(
                        j.get("validThrough", "")
                    ),
                    "location_check": "대한민국 근무 확인",
                    "evidence": "JobPosting 구조화 데이터",
                }, "OK"

        # 2. 공개 채용공고 페이지 형식 검증
        host = urlparse(url).netloc.lower()
        path = urlparse(url).path.lower()

        remember = (
            "rememberapp.co.kr" in host
            and re.search(r"/job/postings?/\d+", path)
        )

        kvca = (
            "kvca.or.kr" in host
            and "listbody.html" in path
            and "po_no=" in url
        )

        if not (remember or kvca):
            return None, "검증 가능한 공고 형식 없음"

        main = (
            soup.select_one("main")
            or soup.select_one("article")
            or soup.body
        )

        if main is None:
            return None, "본문 없음"

        body = text_of(
            BeautifulSoup(str(main), "html.parser")
        )[:14000]

        if remember:
            heading = soup.find("h1")

            title = (
                heading.get_text(" ", strip=True)
                if heading
                else ""
            )

            employer = (
                soup.title.get_text(
                    " ", strip=True
                ).split(" 채용")[0]
                if soup.title
                else ""
            )

            location = (
                bool(re.search(
                    r"근무지\s*.{0,90}", body
                ))
                and any(
                    k in body.lower()
                    for k in KOREA
                )
            )

            structure = (
                all(
                    x in body
                    for x in ("자격 요건", "주요업무")
                )
                or all(
                    x in body
                    for x in ("자격요건", "주요업무")
                )
            )

            deadline_match = re.search(
                r"마감일\s*"
                r"(20\d{2}[.\-/]\s*\d{1,2}"
                r"[.\-/]\s*\d{1,2})",
                body,
            )

            deadline = (
                date_hint(deadline_match.group(1))
                if deadline_match
                else ""
            )

        else:
            title_match = re.search(
                r"채용명\s*[:|]?\s*"
                r"(.{4,110}?)\s*채용구분",
                body,
            )

            title = (
                title_match.group(1).strip()
                if title_match
                else ""
            )

            employer = (
                title.split("]")[0].lstrip("[")
                if "[" in title
                else title.split(" ")[0]
            )

            location = (
                bool(re.search(
                    r"근무\s*지\s*[:：]?\s*.{0,100}",
                    body,
                ))
                and any(
                    k in body.lower()
                    for k in KOREA
                )
            )

            structure = all(
                x in body
                for x in (
                    "채용마감일",
                    "채용구분",
                    "채용명",
                )
            )

            deadline_match = re.search(
                r"채용마감일\s*"
                r"(20\d{2}[.\-/]\s*\d{1,2}"
                r"[.\-/]\s*\d{1,2})",
                body,
            )

            deadline = (
                date_hint(deadline_match.group(1))
                if deadline_match
                else ""
            )

        if not (
            title and employer
            and location and structure
        ):
            return None, "기업·직무·국내 근무지 확인 실패"

        return {
            "title": title,
            "description": body[:1600],
            "employer": employer,
            "deadline": deadline,
            "location_check": "대한민국 근무 확인",
            "evidence": "공개 채용공고 본문",
        }, "OK"

    except requests.RequestException:
        return None, "원문 접근 실패"

    except Exception as e:
        return None, (
            "파싱 오류 " + type(e).__name__
        )


def relevant(job, category):
    text = (
        job["title"] + " "
        + job["description"]
    ).lower()

    hits = [
        x for x in INDUSTRY
        if x in text
    ]

    if not hits:
        return False, []

    if category == "금융·컨설팅":
        finance_terms = [
            "투자", "금융", "리서치",
            "컨설팅", "consult",
            "investment", "애널리스트",
            "심사역", "due diligence",
        ]

        if not any(
            x in text for x in finance_terms
        ):
            return False, []

    if not any(
        x in text for x in ROLE
    ):
        return False, []

    if any(
        x in job["title"].lower()
        for x in BAD
    ):
        return False, []

    return True, hits


def main():
    try:
        old = json.loads(
            OUT.read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        old = {}

    # 검증되지 않은 기존 결과는 제거
    archive = {
        j["url"]: j
        for j in old.get("jobs", [])
        if (
            isinstance(j, dict)
            and j.get("verified") is True
            and j.get("url")
        )
    }

    stats = {
        "queries": 0,
        "rss_results": 0,
        "unique_urls": 0,
        "verified": 0,
        "rejected": {},
        "by_source": {},
    }

    errors = []
    visited = set()
    fresh = set()
    tasks = []

    for cat, terms in TOPICS.items():
        for term in terms:
            tasks.append((
                cat,
                term + " 채용 2026 대한민국",
                "전체",
            ))

            tasks.append((
                cat,
                term + " 2026 마감 공고",
                "과거",
            ))

        for name, domain in SITES.items():
            for term in (
                terms[0],
                terms[-1],
            ):
                tasks.append((
                    cat,
                    f"site:{domain} "
                    f"{term} 채용 2026",
                    name,
                ))

    for cat, q, source in tasks:
        stats["queries"] += 1

        stats["by_source"].setdefault(
            source,
            {
                "queries": 0,
                "rss": 0,
                "verified": 0,
            },
        )["queries"] += 1

        try:
            rows = search(q)

            stats["rss_results"] += len(rows)
            stats["by_source"][source]["rss"] += len(rows)

            for _, url in rows:
                if not url or url in visited:
                    continue

                visited.add(url)
                stats["unique_urls"] += 1

                job, reason = validate(url)

                if job:
                    ok, hits = relevant(job, cat)

                    if not ok:
                        job = None
                        reason = "직무 관련성 불충분"

                if not job:
                    stats["rejected"][reason] = (
                        stats["rejected"].get(
                            reason, 0
                        ) + 1
                    )
                    continue

                prev = archive.get(url, {})
                deadline = job["deadline"]

                archive[url] = {
                    **prev,
                    **job,
                    "url": url,
                    "category": cat,
                    "source": urlparse(url).netloc,
                    "fit": (
                        "상"
                        if len(hits) >= 3
                        else "중"
                    ),
                    "matched_skills": hits,
                    "first_seen": prev.get(
                        "first_seen",
                        NOW.isoformat(),
                    ),
                    "last_seen": NOW.isoformat(),
                    "seen_in_latest_run": True,
                    "status": status(deadline),
                    "posting_date_hint": deadline,
                    "verified": True,
                }

                fresh.add(url)
                stats["verified"] += 1

                stats["by_source"][source][
                    "verified"
                ] += 1

        except Exception as e:
            errors.append(
                f"{q}: "
                f"{type(e).__name__} "
                f"{str(e)[:100]}"
            )

        time.sleep(0.15)

    for url, j in archive.items():
        j["seen_in_latest_run"] = (
            url in fresh
        )

    result = {
        "updated_at": NOW.isoformat(),
        "queries_attempted": stats["queries"],
        "discovered_this_run": stats["verified"],
        "diagnostics": stats,
        "errors": errors,
        "jobs": sorted(
            archive.values(),
            key=lambda j: j.get(
                "first_seen", ""
            ),
            reverse=True,
        ),
        "notice": (
            "검증된 국내 채용공고 후보. "
            "과거 공고 보존. "
            "사이트 접근 제한으로 일부 공고 "
            "누락 가능. 마감일 미경과가 "
            "실제 모집 중임을 보장하지 않음."
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
        "검색:", stats["queries"],
        "RSS:", stats["rss_results"],
        "URL:", stats["unique_urls"],
        "검증:", stats["verified"],
        "오류:", len(errors),
    )

    print(
        "제외 이유:",
        json.dumps(
            stats["rejected"],
            ensure_ascii=False,
        ),
    )

    print(
        "출처별:",
        json.dumps(
            stats["by_source"],
            ensure_ascii=False,
        ),
    )

    for e in errors[:10]:
        print("ERROR:", e)


if __name__ == "__main__":
    main()
