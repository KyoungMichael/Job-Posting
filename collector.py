
"""Public search-index candidate collector. No login, bypass or guaranteed completeness."""
import json, re, time, html
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'data' / 'jobs.json'
YEAR = 2026

SITES = {
    '사람인': 'saramin.co.kr',
    '자소설닷컴': 'jasoseol.com',
    'LinkedIn': 'linkedin.com/jobs',
    '리멤버': 'career.rememberapp.co.kr',
    '한국벤처캐피탈협회': 'kvca.or.kr',
    '금융투자협회': 'kofia.or.kr',
    '잡코리아': 'jobkorea.co.kr',
    '원티드': 'wanted.co.kr'
}

CATEGORIES = {
    '정유·화학': [
        '정유 공정기술',
        '석유화학 생산기술',
        '화학 공정엔지니어',
        '정유 화학 경력 우대',
        'energy chemicals 사업개발'
    ],
    '탄소포집': [
        'CCS CCUS',
        '탄소포집 사업개발',
        'carbon capture Korea',
        '수소 저탄소 사업'
    ],
    '공정안전': [
        '공정안전 PSM',
        'HAZOP LOPA',
        'process safety Korea',
        '위험성평가 공정'
    ],
    '금융·컨설팅': [
        '정유 화학 투자심사',
        '에너지 산업 리서치',
        'CCUS 투자',
        '에너지 전략 컨설팅',
        '에너지 기술실사'
    ]
}

CORE = (
    '정유', '석유화학', '화학', '공정', '탄소포집',
    'ccus', 'ccs', 'carbon capture', 'hazop',
    'lopa', 'psm', 'process safety', '수소',
    'energy', '에너지', '탈탄소', '저탄소'
)

FIN = (
    '투자', '금융', '컨설팅', 'consult',
    'investment', '리서치', '심사역',
    'pf', 'due diligence', '애널리스트'
)

JOB = (
    '채용', '모집', '경력', '신입', '공고',
    'recruit', 'hiring', 'job', 'career',
    'position', 'apply', 'employment', '인재'
)

NEG = (
    'ultimate guide', 'what is', 'tutorial',
    '교육과정', '세미나', '블로그', '뉴스',
    '논문', '가이드', '강의', '교재',
    '위키', '면접후기', '합격자소서'
)

KOREA = (
    '한국', '대한민국', '서울', '경기', '인천',
    '대전', '울산', '부산', '여수', '포항',
    '대산', '판교', '수원', '충북', '충남',
    '경북', '경남', '전남', '전북', '광주',
    '대구', '세종', 'seoul', 'korea',
    'ulsan', 'busan', 'incheon'
)

SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': (
        'Mozilla/5.0 '
        '(compatible; JobsDashboard/2.0; public search results)'
    )
})


def clean_url(u):
    p = urlparse(u)
    if p.scheme not in ('http', 'https') or not p.netloc:
        return ''

    q = [
        (k, v)
        for k, v in parse_qsl(p.query)
        if not k.lower().startswith(('utm_', 'fbclid', 'gclid'))
    ]

    return urlunparse((
        p.scheme, p.netloc.lower(),
        p.path.rstrip('/'), '',
        urlencode(q), ''
    ))


def rss(query):
    r = SESSION.get(
        'https://www.bing.com/search',
        params={'format': 'rss', 'q': query},
        timeout=22
    )
    r.raise_for_status()

    soup = BeautifulSoup(r.content, 'xml')
    if soup.find('rss') is None:
        raise ValueError('RSS 응답 형식 아님')

    items = []

    for item in soup.select('item'):
        def get(tag):
            el = item.find(tag)
            return el.get_text(' ', strip=True) if el else ''

        items.append((
            get('title'),
            clean_url(get('link')),
            BeautifulSoup(
                html.unescape(get('description')),
                'html.parser'
            ).get_text(' ', strip=True)
        ))

    return items


def accept(title, desc, url, category):
    text = (title + ' ' + desc).lower()
    t = title.lower()
    path = (
        urlparse(url).netloc + urlparse(url).path
    ).lower()

    if not url or any(x in t for x in NEG):
        return False, '자료/비공고'

    if not any(x in text for x in CORE):
        if not (
            category == '금융·컨설팅'
            and any(x in text for x in FIN)
        ):
            return False, '직무 연관성 없음'

    if not (
        any(x in text for x in JOB)
        or any(
            x in path
            for x in (
                '/jobs', '/job', '/recruit',
                '/career', '/position', '/recruitment'
            )
        )
    ):
        return False, '채용 단서 없음'

    return True, '후보'


def classify_date(title, desc):
    text = title + ' ' + desc

    m = re.search(
        r'(?<!\d)(2026)[.\-/]\s*'
        r'(0?[1-9]|1[0-2])[.\-/]\s*'
        r'(0?[1-9]|[12]\d|3[01])(?!\d)',
        text
    )

    if m:
        return (
            f'{int(m[1]):04d}-'
            f'{int(m[2]):02d}-'
            f'{int(m[3]):02d}'
        )

    return None


def main():
    now = datetime.now(
        timezone.utc
    ).isoformat(timespec='seconds')

    try:
        old = json.loads(
            OUT.read_text(encoding='utf-8')
        )
    except (ValueError, OSError):
        old = {}

    archive = {
        j['url']: j
        for j in old.get('jobs', [])
        if isinstance(j, dict) and j.get('url')
    }

    diagnostics = {
        'queries': 0,
        'rss_results': 0,
        'rejected': {},
        'accepted': 0,
        'sources': {}
    }

    errors = []
    seen = set()
    tasks = []

    # 일반 검색 + 2026년 과거 공고 검색 + 사이트별 검색
    for cat, terms in CATEGORIES.items():
        for term in terms:
            tasks.append((
                cat,
                term + ' 채용 2026 대한민국',
                '전체 웹'
            ))

            tasks.append((
                cat,
                term + ' 2026 마감 채용',
                '과거 공고'
            ))

            for name, domain in SITES.items():
                if term != terms[0] and term != terms[-1]:
                    continue

                tasks.append((
                    cat,
                    f'site:{domain} {term} 채용 2026',
                    name
                ))

    for cat, q, source in tasks:
        diagnostics['queries'] += 1

        try:
            rows = rss(q)
            diagnostics['rss_results'] += len(rows)

            diagnostics['sources'].setdefault(
                source,
                {'queries': 0, 'results': 0, 'accepted': 0}
            )

            diagnostics['sources'][source]['queries'] += 1
            diagnostics['sources'][source]['results'] += len(rows)

            for title, url, desc in rows:
                ok, reason = accept(
                    title, desc, url, cat
                )

                if not ok:
                    diagnostics['rejected'][reason] = (
                        diagnostics['rejected'].get(reason, 0) + 1
                    )
                    continue

                if url in seen:
                    continue

                seen.add(url)
                diagnostics['accepted'] += 1
                diagnostics['sources'][source]['accepted'] += 1

                prev = archive.get(url, {})

                relevant = [
                    k for k in CORE + FIN
                    if k in (title + ' ' + desc).lower()
                ]

                archive[url] = {
                    **prev,
                    'url': url,
                    'title': title[:240],
                    'description': desc[:700],
                    'category': cat,
                    'source': urlparse(url).netloc,
                    'discovered_via': source,
                    'fit': (
                        '상' if len(relevant) >= 3
                        else '중' if relevant else '하'
                    ),
                    'matched_skills': relevant[:12],
                    'first_seen': prev.get('first_seen', now),
                    'last_seen': now,
                    'seen_in_latest_run': True,
                    'location_check': (
                        '국내 관련 단서 있음 · 확인 필요'
                        if any(
                            k in (title + ' ' + desc).lower()
                            for k in KOREA
                        )
                        else '근무지 미확인'
                    ),
                    'posting_date_hint': classify_date(
                        title, desc
                    ),
                    'status': '모집 여부 확인 필요',
                    'historical': True
                }

        except Exception as exc:
            errors.append(
                f'{source} / {q}: '
                f'{type(exc).__name__}: {str(exc)[:100]}'
            )

        time.sleep(0.12)

    for url, j in archive.items():
        if url not in seen:
            j['seen_in_latest_run'] = False

    # 과거 공고 자동 삭제하지 않음
    jobs = sorted(
        archive.values(),
        key=lambda j: j.get('first_seen', ''),
        reverse=True
    )

    result = {
        'updated_at': now,
        'discovered_this_run': diagnostics['accepted'],
        'queries_attempted': diagnostics['queries'],
        'errors': errors,
        'diagnostics': diagnostics,
        'jobs': jobs,
        'notice': (
            '공개 검색 결과 기반 채용 후보 목록. '
            '2026년 과거 공고 포함. '
            '마감 여부·근무지·우대사항은 '
            '원문 검증 전까지 미확인입니다.'
        )
    }

    OUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    OUT.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        ),
        encoding='utf-8'
    )

    print(
        '검색:', diagnostics['queries'],
        'RSS 결과:', diagnostics['rss_results'],
        '채택:', diagnostics['accepted'],
        '오류:', len(errors)
    )

    print('제외 이유:', diagnostics['rejected'])
    print(
        '출처별:',
        json.dumps(
            diagnostics['sources'],
            ensure_ascii=False
        )
    )

    for e in errors[:10]:
        print('ERROR:', e)


if __name__ == '__main__':
    main()
