# 에너지·화학 채용 모니터 (온라인 웹 대시보드)

PC가 꺼져 있어도 GitHub Actions에서 한국시간 매일 오전 8시경 공개 Bing RSS 검색 결과를 수집하고 GitHub Pages 대시보드를 갱신합니다. GitHub의 예약 작업은 정각 실행을 보장하지 않으며, 무료 사용량과 Pages 이용 가능 여부는 계정·저장소 설정에 따릅니다.

## 처음 배포하기 (GitHub 계정 필요)

1. GitHub에서 **새 공개(public) 저장소**를 만듭니다. 예: `energy-jobs`.
2. 이 ZIP 파일의 **내부 파일과 폴더** (`.github`, `site`, `data`, `collector.py`, `requirements.txt`, `README.md`)를 저장소 최상위에 업로드합니다. `.github`는 숨김 폴더이므로 빠뜨리지 마세요. GitHub 웹 업로드에서 숨김 폴더가 누락되면 Git CLI 또는 GitHub Desktop으로 업로드하세요.
3. 저장소 **Settings → Pages → Build and deployment → Source: GitHub Actions**를 선택합니다.
4. 저장소 **Settings → Actions → General → Workflow permissions**에서 **Read and write permissions**를 허용합니다. 조직 정책으로 제한되면 관리자가 변경해야 합니다.
5. **Actions → Daily jobs collection and site deployment → Run workflow**를 눌러 최초 수집·배포를 실행합니다.
6. 실행 완료 후 **Settings → Pages**에서 공개 URL을 확인합니다. 보통 `https://사용자명.github.io/energy-jobs/` 형식입니다.

이후 매일 오전 8시(한국시간) 전후 자동 실행됩니다. 저장소가 비활성화되거나 예약 실행이 제한될 수 있으니 Actions 기록을 가끔 확인하세요.

## 주요 기능

- 정유·화학 / 탄소포집·CCUS / 공정안전 탭
- 검색, 적합도 필터, 최근 발견순 정렬, CSV 내보내기
- 최초 발견 및 최근 검색 발견 여부, 최근 24시간 신규 표시
- 검색 결과 저장 및 30일 동안 미발견 항목 보관
- 외부 원문 링크 제공

## 주의 사항

- **검색 결과는 채용 후보입니다.** 현재 채용 중인지, 마감일과 지원 자격은 자동 검증하지 않습니다.
- 적합도는 쉘캐나다 경력과 관련된 키워드 매칭으로 추정하며 실제 채용 가능성과 다릅니다.
- Bing RSS가 차단되거나 검색 결과를 제공하지 않으면 빈 결과 또는 오류가 표시될 수 있습니다. 검색 엔진 색인 범위 밖의 채용은 수집되지 않습니다.
- 공개 저장소의 수집 데이터와 코드가 공개됩니다. 비밀번호나 개인정보를 업로드하지 마세요.
- 이 버전은 외부 서버 없이 GitHub의 정적 호스팅과 예약 작업으로 동작합니다.

## 로컬 테스트

```bash
python -m pip install -r requirements.txt
python collector.py
mkdir -p site/data
cp data/jobs.json site/data/jobs.json
python -m http.server 8000 --directory site
```

브라우저에서 `http://localhost:8000`을 열어 확인합니다. Windows에서는 `cp` 대신 `copy data\\jobs.json site\\data\\jobs.json`을 사용하세요.
