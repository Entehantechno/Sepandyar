"""سپندیار — language

لایهٔ زبان فارسی: نرمال‌سازی نویسه، لهجه، صبر گفتاری، تصویر‌یابی و سنجهٔ ریسک.

این ماژول بزرگ‌ترین بخش منطق غیر-HTTP برنامه است: تطبیق نام دارو با
difflib و الگوهای گویشی، حذف پسوندهای مفعولی، یادگیری نام مستعار، جست‌وجوی
تصویر در Openverse و Commons برای رفع ابهام، و assess_risk() که هر متن
خروجی — حتی در مسیر زنده — از آن می‌گذرد.
"""
import json, sqlite3, os, uuid, datetime, hashlib, re, difflib, time, secrets, hmac, threading, html, math, urllib.request as ureq, urllib.error as uerr
from zoneinfo import ZoneInfo
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, quote, unquote, parse_qs

from .clock import now
from .primitives import rows

# ============= بخش ۹: لایهٔ زبان — گویش و لهجه، ابهام‌زدایی تصویری، ریسک =============
def normalize_fa(t): return str(t or '').replace('ي','ی').replace('ك','ک')

def norm_fa(t): return re.sub(r'[ًٌٍَُِّْ]','',str(t or '').replace('ي','ی').replace('ك','ک').lower()).strip()

SMALLTALK=('سلام','درود','خوبی','خوبید','حالت','ممنون','مرسی','تشکر','خداحافظ','بله','خیر','باشه','چطوری','خوبم','خوب','بد نیستم','سلامت')

def is_smalltalk(t):
 t=norm_fa(t)
 return bool(t) and len(t.split())<=2 and any(k in t for k in SMALLTALK)

# ---- رفع ابهام گفتار سالمند با تصویر (پژوهش‌محور: پرسش کوتاه، تأییدی، بدون نام فنی) ----
IMAGE_UA='Sepandyar/0.3 (elderly voice assistant; contact: team@sepandyar.local)'

OPENVERSE_URL='https://api.openverse.org/v1/images/'

COMMONS_URL='https://commons.wikimedia.org/w/api.php'

# ---- لایه گویش و لهجه (بر پایه بنچمارک PSRB: بدترین دقت فارسی روی لهجه مشهدی و یزدی) ----
DEFAULT_PATIENCE_MS=1800   # پژوهش: آستانه ۱۵۰۰ms برای تماس‌های سلامت/سالمند توصیه شده؛ مکث میان جمله در دهه هشتاد زندگی ۵٫۴ برابر است

OBJ_SUFFIXES=('مو','رو','شو','و')

def get_voice_profile(c,pid='default'):
 r=c.execute('SELECT * FROM voice_profiles WHERE id=?',(pid,)).fetchone()
 if r: return dict(r)
 return {'id':pid,'name':'کاربر','dialect':'standard','secondary_dialect':'','patience_ms':DEFAULT_PATIENCE_MS,'confidence_floor':0.55,'calibrated':0,'updated_at':None}

def normalize_dialect(c,text,dialect=None,secondary=None):
 """واژه‌های گویشی و محاوره‌ای را به فارسی معیار نگاشت می‌کند؛ فهرست قواعد اعمال‌شده را هم برمی‌گرداند.

 نکته ایمنی: قواعد مخصوص یک لهجه فقط وقتی اعمال می‌شوند که پروفایل کاربر همان لهجه را
 اعلام کرده باشد، و جایگزینی فقط روی مرز کلمه انجام می‌شود (بدون دست‌کاری نویسه‌ای)."""
 raw=norm_fa(text)
 if not raw: return '',[]
 accs=[a for a in (dialect,secondary) if a and a!='standard']
 q='SELECT variant,canonical,accent FROM dialect_lexicon WHERE accent IN (%s)'%','.join('?'*(len(accs)+2))
 params=accs+['colloquial','standard']
 if not accs:
  q='SELECT variant,canonical,accent FROM dialect_lexicon WHERE accent IN (?,?)'; params=['colloquial','standard']
 lexc=list(c.execute(q,tuple(params)))
 multi={tuple(norm_fa(r['variant']).split()):(r['canonical'],r['accent']) for r in lexc if len(norm_fa(r['variant']).split())>1}
 single={norm_fa(r['variant']):(r['canonical'],r['accent']) for r in lexc if len(norm_fa(r['variant']).split())==1}
 tokens=raw.split(); applied=[]; out=[]; i=0; maxspan=max((len(k) for k in multi),default=0)
 while i<len(tokens):
  hit=None
  for span in range(min(maxspan,len(tokens)-i),1,-1):
   key=tuple(tokens[i:i+span])
   if key in multi: hit=(span,)+multi[key]; break
  if hit:
   span,can,acc=hit; out.append(norm_fa(can)); applied.append({'from':' '.join(tokens[i:i+span]),'to':can,'accent':acc}); i+=span; continue
  w=tokens[i]
  if w in single:
   can,acc=single[w]; out.append(norm_fa(can)); applied.append({'from':w,'to':can,'accent':acc})
  else:
   stem,note=strip_obj_suffix(w)
   if note: applied.append({'from':w,'to':stem,'accent':'colloquial'})
   if stem in single:
    can,acc=single[stem]; out.append(norm_fa(can)); applied.append({'from':stem,'to':can,'accent':acc})
   else: out.append(stem or w)
  i+=1
 dedup=[w for i,w in enumerate(out) if i==0 or w!=out[i-1]]
 return ' '.join(dedup),applied

def strip_obj_suffix(w):
 """پسوند مفعولی محاوره‌ای را فقط وقتی برمی‌دارد که ریشه باقی‌مانده خودش یک کلمه معتبر باشد."""
 for suf in OBJ_SUFFIXES:
  if w.endswith(suf) and len(w)-len(suf)>=3: return w[:-len(suf)],'obj'
 return w,''

def find_alias(c,text,pid='default'):
 t=norm_fa(text); best=None; score=0
 for r in c.execute('SELECT * FROM utterance_aliases'):
  a=norm_fa(r['transcript'])
  if not a: continue
  s=0
  if a==t: s=1000
  elif a in t or t in a: s=700
  else:
   ratio=difflib.SequenceMatcher(None,a,t).ratio()
   if ratio>=0.78: s=int(ratio*600)
  if s: s+=r['weight']
  if s>score: score=s; best=r
 return (best,score) if best else (None,0)

def learn_alias(c,transcript,intent_id,source='disambiguation',pid='default'):
 t=norm_fa(transcript)
 if not t or len(t)<2: return False
 hit=c.execute('SELECT * FROM utterance_aliases WHERE transcript=?',(t,)).fetchone()
 if hit: c.execute('UPDATE utterance_aliases SET intent_id=?,weight=weight+1,source=? WHERE id=?',(intent_id,source,hit['id']))
 else: c.execute('INSERT INTO utterance_aliases VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),t,intent_id,source,1,now()))
 c.commit(); return True

def match_candidates(c,text,limit=2,dialect=None,secondary=None,pid='default'):
 t=norm_fa(text)
 if not t: return []
 al,asc=find_alias(c,t,pid)
 if al: return [{'id':al['intent_id'],'label':(c.execute('SELECT label FROM intent_lexicon WHERE id=?',(al['intent_id'],)).fetchone() or {'label':al['intent_id']})['label'],'action':al['intent_id'],'image_query':(c.execute('SELECT image_query FROM intent_lexicon WHERE id=?',(al['intent_id'],)).fetchone() or {'image_query':'elderly care'})['image_query'],'score':asc,'source':'personal_alias'}]
 canon,applied=normalize_dialect(c,t,dialect,secondary)
 scored=[]
 for r in rows(c,'SELECT * FROM intent_lexicon ORDER BY priority DESC'):
  best=0
  for kw in json.loads(r['keywords'] or '[]'):
   k=norm_fa(kw)
   if not k: continue
   for probe in (t,canon):
    if k in probe or probe in k: best=max(best,100); continue
    ratio=difflib.SequenceMatcher(None,k,probe).ratio()
    for w in probe.split():
     if len(w)>2: ratio=max(ratio,difflib.SequenceMatcher(None,k,w).ratio())
    if ratio>=0.62: best=max(best,int(ratio*90))
  if best>0: scored.append((best,r))
 scored.sort(key=lambda x:-x[0])
 return [{'id':r['id'],'label':r['label'],'action':r['action'],'image_query':r['image_query'],'score':s,'source':'dialect_lexicon' if applied else 'keyword'} for s,r in scored[:limit]]

def net_json(url,timeout=6):
 req=ureq.Request(url,headers={'User-Agent':IMAGE_UA,'Accept':'application/json'})
 with ureq.urlopen(req,timeout=timeout) as r: return json.loads(r.read())

def images_from_openverse(query,count):
 data=net_json(OPENVERSE_URL+'?q='+quote(query)+'&page_size='+str(max(count,2)))
 out=[]
 for it in (data.get('results') or [])[:count]:
  lic=str(it.get('license') or '').upper()
  if it.get('license_version'): lic=(lic+' '+str(it.get('license_version'))).strip()
  out.append({'url':it.get('url'),'thumbnail':it.get('thumbnail') or it.get('url'),'title':(it.get('title') or '')[:120],'author':it.get('creator') or '','license':lic,'attribution':it.get('attribution') or '','source':'openverse','page_url':it.get('foreign_landing_url')})
 return out

def images_from_commons(query,count):
 url=(COMMONS_URL+'?action=query&format=json&generator=search&gsrnamespace=6&gsrlimit='+str(max(count,2))+'&gsrsearch='+quote(query)+'&prop=imageinfo&iiprop=url|extmetadata&iiurlwidth=640')
 data=net_json(url); pages=((data.get('query') or {}).get('pages') or {})
 out=[]
 for pg in list(pages.values())[:count]:
  ii=(pg.get('imageinfo') or [{}])[0]; em=ii.get('extmetadata') or {}
  def meta(k): return re.sub('<[^>]+>','',(em.get(k) or {}).get('value','') or '').strip()
  lic=meta('LicenseShortName'); artist=meta('Artist')
  out.append({'url':ii.get('url'),'thumbnail':ii.get('thumburl') or ii.get('url'),'title':pg.get('title','').replace('File:','')[:120],'author':artist,'license':lic,'attribution':((artist+' — ') if artist else '')+(lic+'، از Wikimedia Commons') if (artist or lic) else 'Wikimedia Commons','source':'commons','page_url':ii.get('descriptionurl')})
 return out

IMAGE_NET={'blocked_until':0.0}

def fetch_images(c,query,count=2):
 """جست‌وجوی تصویر با کش محلی؛ اگر اینترنت در دسترس نبود، پاسخ آفلاین برمی‌گرداند تا پاپ‌آپ هرگز خالی نماند."""
 q=norm_fa(query)
 hit=c.execute('SELECT * FROM image_cache WHERE query=?',(q,)).fetchone()
 if hit:
  try: return json.loads(hit['items'])
  except Exception: pass
 items=[]; source='offline'
 if time.time()>=IMAGE_NET['blocked_until']:
  for fn in (images_from_openverse,images_from_commons):
   try:
    items=fn(query,count)
    if items: source=items[0].get('source') or 'online'; break
   except Exception: items=[]
  if not items: IMAGE_NET['blocked_until']=time.time()+90
 if not items:
  items=[{'url':None,'thumbnail':None,'title':query,'author':'','license':'','attribution':'','source':'offline','page_url':None} for _ in range(count)]
 try: c.execute('INSERT INTO image_cache VALUES(?,?,?,?)',(q,json.dumps(items,ensure_ascii=False),source,now()))
 except sqlite3.IntegrityError: c.execute('UPDATE image_cache SET items=?,source=?,fetched_at=? WHERE query=?',(json.dumps(items,ensure_ascii=False),source,now(),q))
 c.commit(); return items

# ======================== بخش ۱۱: مراقب، هشدار و رضایت ========================
# احراز هویت مراقب، صف اقدام‌ها، هشدارها و بررسی رضایت سالمند.
FA_CLITICS=('مان','تان','شان','های','ها','ام','ات','ش','م','ی','ای')

def _stem(w):
 w=norm_fa(w).replace('\u200c','')
 for suf in FA_CLITICS:
  if len(w)>len(suf)+2 and w.endswith(suf): return w[:-len(suf)]
 return w

def _pattern_hits(pattern,text):
 """ابتدا زیررشتهٔ دقیق، و در نبود آن تطبیق واژه‌به‌واژهٔ بی‌ترتیب با ریشه‌یابی سبک.

 علت: «درد شدید قفسه سینه» و «سینه‌ام درد می‌کند» هر دو باید قاعدهٔ «درد قفسه سینه» را
 بزنند؛ تطبیق زیررشتهٔ صرف هر دو را از دست می‌داد. سوگیری عمداً به سمت recall است:
 در سامانهٔ سالمند، یک هشدار اضافی بسیار کم‌خطرتر از یک اورژانسِ ازدست‌رفته است.
"""
 p=norm_fa(pattern); t=norm_fa(text)
 if not p or not t: return False
 if p in t: return True
 toks=[x for x in p.split() if x]
 if len(toks)<2: return False
 stems=[_stem(w) for w in t.split() if w]
 return all(any(_stem(x)==s or (_stem(x) in s) or (s in _stem(x)) for s in stems) for x in toks)

def assess_risk(c,text):
 t=normalize_fa(text).lower()
 for r in c.execute("SELECT * FROM safety_rules ORDER BY CASE level WHEN 'critical' THEN 0 ELSE 1 END, pattern").fetchall():
  if _pattern_hits(r['pattern'],t): return {'level':r['level'],'matched':r['pattern'],'action':r['action'],'reply':r['reply']}
 return {'level':'normal','matched':None,'action':None,'reply':None}
