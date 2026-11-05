import json, os, re, time, html
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse, parse_qs, unquote, urlencode, urlunparse
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'/'jobs.json'
QUERIES={
 '정유·화학':['정유 공정기술 채용 2026','석유화학 생산기술 경력 채용','화학 공정엔지니어 채용','S-OIL GS칼텍스 SK에너지 채용 공정'],
 '탄소포집':['CCS CCUS 탄소포집 채용 2026','탄소포집 공정 엔지니어 채용','수소 탄소저감 사업개발 채용'],
 '공정안전':['공정안전 PSM 경력 채용','HAZOP LOPA 채용','Process Safety Engineer Korea jobs']}
KEYWORDS={'정유·화학':['정유','화학','공정','생산기술','process','refinery','petrochemical'], '탄소포집':['ccs','ccus','탄소포집','탄소저감','수소','carbon capture'], '공정안전':['공정안전','psm','hazop','lopa','process safety','위험성평가','안전관리']}
EXCLUDE=['블로그','뉴스','기사','위키','나무위키','youtube','유튜브','카페','인스타','지식인','합격자소서','면접후기','연봉정보']
SKILLS=['ccs','ccus','탄소포집','수소','hazop','lopa','psm','공정안전','공정기술','생산기술','moc','process safety','process engineer']

def canonical(url):
 p=urlparse(url)
 if p.scheme not in ('https','http'): return ''
 if p.netloc.lower().endswith('bing.com') and p.path.startswith('/ck/'):
  return ''
 q=[(k,v) for k,values in parse_qs(p.query).items() for v in values if not k.lower().startswith(('utm_','fbclid','gclid'))]
 return urlunparse((p.scheme,p.netloc.lower(),p.path.rstrip('/'),'',urlencode(q),'')).strip()

def search(q):
 url='https://www.bing.com/search?format=rss&q='+quote(q+' 채용')
 r=requests.get(url,timeout=20,headers={'User-Agent':'Mozilla/5.0 (compatible; PublicJobsMonitor/1.0)'})
 r.raise_for_status()
 soup=BeautifulSoup(r.content,'xml')
 if soup.find('rss') is None: raise ValueError('RSS 응답이 아닙니다')
 for item in soup.find_all('item'):
  title=item.find('title'); link=item.find('link'); desc=item.find('description')
  if title and link:
   yield title.get_text(' ',strip=True),canonical(link.get_text(' ',strip=True)),BeautifulSoup(desc.get_text(' ',strip=True) if desc else '','html.parser').get_text(' ',strip=True)

def relevance(title,description,category):
 t=(title+' '+description).lower()
 if not any(x in t for x in KEYWORDS[category]):return False
 if any(x in title.lower() for x in EXCLUDE):return False
 if not any(x in t for x in ['채용','모집','career','job','recruit','engineer','엔지니어','경력','신입']):return False
 return True

def fit(text):
 t=text.lower(); hits=[x for x in SKILLS if x in t]
 return ('상' if len(hits)>=3 else '중' if len(hits)>=1 else '하'),hits

def run():
 now=datetime.now(timezone.utc).isoformat(timespec='seconds')
 try: old=json.loads(DATA.read_text(encoding='utf-8'))
 except (OSError,ValueError):old={'jobs':[]}
 jobs={j['url']:j for j in old.get('jobs',[]) if j.get('url')}
 errors=[]; seen=set(); count=0
 for cat,queries in QUERIES.items():
  for q in queries:
   try:
    for title,url,desc in search(q):
     if not url or not relevance(title,desc,cat):continue
     if url in seen:continue
     seen.add(url)
     score,hits=fit(title+' '+desc)
     prev=jobs.get(url,{})
     changed=bool(prev and (prev.get('title')!=title or prev.get('description')!=desc))
     jobs[url]={**prev,'url':url,'title':title[:250],'description':desc[:700], 'category':prev.get('category',cat),'source':urlparse(url).netloc,'fit':score,'matched_skills':hits,'first_seen':prev.get('first_seen',now),'last_seen':now,'changed_at':now if changed else prev.get('changed_at'),'status':'검색 발견 · 모집 여부 원문 확인 필요'}
     count+=1
   except Exception as e:errors.append(f'{q}: {type(e).__name__}: {str(e)[:140]}')
   time.sleep(0.4)
 # Preserve past results for 30 days, clearly distinguish unverified historical entries.
 from datetime import timedelta
 cutoff=datetime.now(timezone.utc)-timedelta(days=30)
 kept=[]
 for j in jobs.values():
  try: last=datetime.fromisoformat(j['last_seen'].replace('Z','+00:00'))
  except Exception:continue
  if last>=cutoff:
   j['seen_in_latest_run']=j['url'] in seen
   kept.append(j)
 kept.sort(key=lambda j:j.get('first_seen',''),reverse=True)
 output={'updated_at':now,'discovered_this_run':count,'queries_attempted':sum(map(len,QUERIES.values())),'errors':errors,'jobs':kept[:1000], 'notice':'검색 엔진 색인 기반 후보 공고입니다. 실제 채용 진행 여부, 마감일, 경력 인정은 반드시 원문에서 확인하세요.'}
 DATA.parent.mkdir(exist_ok=True)
 DATA.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
 print(f'검색 결과 {count}개, 보관 {len(output["jobs"])}개, 오류 {len(errors)}개')
 if errors:print('\n'.join(errors))

if __name__=='__main__':run()
