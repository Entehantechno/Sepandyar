#!/usr/bin/env python3
"""آزمون استقرار: مبدأ امن، آدرس سرور، service worker و قرارداد پوستهٔ اندروید.

چرا این آزمون وجود دارد: چهار باگ واقعی پیدا شد که اپ را در استقرار می‌شکست —
۱) API_BASE در WebView به «file://:4174» تبدیل می‌شد
۲) بارگذاری از file:///android_asset یک مبدأ مات است و fetch/getUserMedia را می‌بندد
۳) مجوز INTERNET در مانیفست اعلام نشده بود
۴) service worker همهٔ GETها از جمله /api/ را کش می‌کرد (دادهٔ کهنهٔ دارو و سلامت)
"""
import json, os, re, sys, threading, http.client, importlib.util, subprocess, shutil
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse

BASE='http://127.0.0.1:4174'
ROOT=os.path.dirname(os.path.abspath(__file__))
failures=[]; total=0
def check(name,cond,detail=''):
    global total
    total+=1
    print(('✅' if cond else '❌'),name,('' if cond else '-> '+str(detail)))
    if not cond: failures.append(name)

def req(base,path,method='GET',data=None):
    u=urlparse(base)
    b=json.dumps(data,ensure_ascii=False).encode() if data is not None else None
    conn=http.client.HTTPConnection(u.hostname,u.port,timeout=60)
    conn.request(method,path,body=b,headers={'Content-Type':'application/json'})
    r=conn.getresponse(); raw=r.read(); code=r.status; conn.close()
    try: return code,json.loads(raw or b'{}')
    except Exception: return code,{'_raw':(raw or b'').decode('utf-8','replace')}

manifest=open(os.path.join(ROOT,'android/app/src/main/AndroidManifest.xml'),encoding='utf-8').read()
main_kt=open(os.path.join(ROOT,'android/app/src/main/java/ai/arena/sepandyar/MainActivity.kt'),encoding='utf-8').read()
gradle=open(os.path.join(ROOT,'android/app/build.gradle.kts'),encoding='utf-8').read()
html=open(os.path.join(ROOT,'index.html'),encoding='utf-8').read()
sw=open(os.path.join(ROOT,'sw.js'),encoding='utf-8').read()
srvsrc=open(os.path.join(ROOT,'server.py'),encoding='utf-8').read()

print('--- 1) مجوزهای شبکه در مانیفست ---')
check('مجوز INTERNET اعلام شده','android.permission.INTERNET' in manifest,'')
check('مجوز ACCESS_NETWORK_STATE اعلام شده','android.permission.ACCESS_NETWORK_STATE' in manifest,'')
check('ترافیک بدون رمز مجاز نیست (فقط https)', 'usesCleartextTraffic="false"' in manifest,'')

print('--- 2) پوستهٔ اندروید: مبدأ امن به‌جای file:// ---')
check('WebViewAssetLoader وارد شده','import androidx.webkit.WebViewAssetLoader' in main_kt,'')
check('WebViewClientCompat وارد شده','import androidx.webkit.WebViewClientCompat' in main_kt,'')
check('WebResourceRequest/Response وارد شده','android.webkit.WebResourceRequest' in main_kt and 'android.webkit.WebResourceResponse' in main_kt,'')
check('هیچ loadUrl با file:// نیست', 'loadUrl("file://' not in main_kt and "loadUrl('file://" not in main_kt, [l for l in main_kt.splitlines() if 'loadUrl' in l])
check('از دامنهٔ رسمی appassets بارگذاری می‌کند','WebViewAssetLoader.DEFAULT_DOMAIN + "/assets/index.html"' in main_kt,'')
check('shouldInterceptRequest به assetLoader وصل است','assetLoader.shouldInterceptRequest(request.url)' in main_kt,'')
check('دسترسی فایل صریحاً خاموش شده','settings.allowFileAccess = false' in main_kt and 'allowUniversalAccessFromFileURLs = false' in main_kt,'')
check('وابستگی androidx.webkit در گریدل است','androidx.webkit:webkit:' in gradle,'')
check('پل getServerUrl وجود دارد','fun getServerUrl()' in main_kt,'')
check('پل saveServerUrl وجود دارد','fun saveServerUrl(' in main_kt,'')
check('آدرس سرور در SharedPreferences می‌ماند','"server_url"' in main_kt,'')

print('--- 3) حل آدرس سرور در لایهٔ وب ---')
check('تابع resolveApiBase تعریف شده','function resolveApiBase()' in html,'')
check('حالت بسته‌بندی‌شده تشخیص داده می‌شود',"location.hostname==='appassets.androidplatform.net'" in html and "location.protocol==='file:'" in html,'')
check('آدرس ذخیره‌شده اولویت دارد',"localStorage.getItem('sepandyarServer')" in html,'')
check('از پل بومی هم خوانده می‌شود','SepandyarNative.getServerUrl' in html,'')
check('در حالت بسته‌بندی بدون آدرس، API_BASE خالی می‌ماند','if(IS_PACKAGED)return \'\'' in html,'')
check('API_BASE دیگر const نیست (قابل تنظیم است)','let API_BASE=resolveApiBase()' in html,'')
check('تابع ذخیرهٔ آدرس سرور هست','function setServerUrl(' in html,'')
check('صفحهٔ تنظیم سرور هست','function openServerSetup(' in html,'')
check('در نخستین اجرا خودکار باز می‌شود','if(needsServerSetup())setTimeout(openServerSetup' in html,'')
check('هشدار https به کاربر نمایش داده می‌شود','باید با https باشد' in html,'')

print('--- 4) شبیه‌سازی resolveApiBase با node ---')
node=shutil.which('node')
if node:
    js='''
const cases=[
 ['file:///android_asset/index.html',''],
 ['https://appassets.androidplatform.net/assets/index.html',''],
 ['http://192.168.1.20:4174/index.html',''],
 ['https://sepandyar.example.com/index.html',':4174'],
 ['http://localhost:4174/index.html','']
];
function resolve(href,saved){
  const location=new URL(href);
  const IS_PACKAGED=location.protocol==='file:'||location.hostname==='appassets.androidplatform.net';
  const APP_ORIGIN=location.protocol+'//'+location.hostname+(location.port?':'+location.port:'');
  if(saved)return saved.replace(/\\/+$/,'');
  if(IS_PACKAGED)return '';
  return location.port==='4174'?'':APP_ORIGIN.replace(/:\\d+$/,'')+':4174';
}
const out=cases.map(([href,expectSuffix])=>{
  const api=resolve(href,'');
  const url=api+'/api/live/session';
  const bad=url.startsWith('file:')||url.includes('://:');
  return {href,api,url,bad,ok:!bad};
});
console.log(JSON.stringify(out));
'''
    r=subprocess.run([node,'-e',js],capture_output=True,text=True)
    if r.returncode==0:
        for row in json.loads(r.stdout.strip()):
            check('آدرس معتبر برای '+row['href'],row['ok'],row['url'])
        check('در حالت بسته‌بندی آدرس خالی است (تا کاربر وارد کند)',
              all(row['api']=='' for row in json.loads(r.stdout.strip()) if 'file:' in row['href'] or 'appassets' in row['href']),'')
    else:
        check('اجرای node برای شبیه‌سازی',False,r.stderr[:200])
else:
    print('   ⚠ node در دسترس نیست؛ شبیه‌سازی رد شد')

print('--- 5) service worker ---')
check('نسخهٔ کش بالا رفته','sepandyar-v2' in sw,'')
check('درخواست‌های /api/ اصلاً رهگیری نمی‌شوند',re.search(r"pathname\.startsWith\('/api/'\)\)return",sw) is not None,'')
check('کش فقط هم‌مبدأ است','url.origin!==self.location.origin)return' in sw,'')
check('فقط پاسخ basic کش می‌شود',"response.type==='basic'" in sw,'')
check('بازگشت به index.html فقط برای ناوبری',"event.request.mode==='navigate'" in sw,'')
check('کش‌های قدیمی پاک می‌شوند','caches.keys()' in sw,'')
check('درخواست غیر GET رهگیری نمی‌شود',"event.request.method!=='GET')return" in sw,'')

print('--- 6) مسیر OpenAI realtime هم patience را می‌گیرد ---')
spec=importlib.util.spec_from_file_location('srv',os.path.join(ROOT,'server.py')); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
calls=[]
class FakeResp:
    def __init__(s,b): s.b=b
    def read(s): return s.b
    def __enter__(s): return s
    def __exit__(s,*a): return False
orig=m.ureq.urlopen
def fake(r,timeout=None):
    calls.append({'url':r.full_url,'body':json.loads(r.data.decode())})
    return FakeResp(json.dumps({'client_secret':{'value':'ek_fake'}}).encode())
os.environ['OPENAI_API_KEY']='FAKE_OPENAI'
srv=ThreadingHTTPServer(('127.0.0.1',0),m.Handler); port=srv.server_address[1]
threading.Thread(target=srv.serve_forever,daemon=True).start()
try:
    m.ureq.urlopen=fake
    st,js=req('http://127.0.0.1:%d'%port,'/api/realtime/session?id=default')
    m.ureq.urlopen=orig
    check('realtime/session 200 است',st==200,(st,js))
    check('یک درخواست به OpenAI زده شد',len(calls)==1,calls)
    _sp,_prof=req('http://127.0.0.1:%d'%port,'/api/voice-profile?id=default')
    _pat=_prof.get('patience_ms')
    td=calls[0]['body']['session']['audio']['input']['turn_detection']
    check('دیگر semantic_vad نیست',td.get('type')!='semantic_vad',td)
    check('server_vad استفاده می‌شود',td.get('type')=='server_vad',td)
    check('silence_duration_ms برابر patience پروفایل است',td.get('silence_duration_ms') == (_pat if _pat is not None else 1800),(td.get('silence_duration_ms'),_pat))
    check('دستور سامانه رد دری را دارد','دری' in calls[0]['body']['session']['instructions'],'')
    check('کلاینت دیگر turn_detection را بازنویسی نمی‌کند',"turn_detection:{type:'semantic_vad'}" not in html,'')
    check('کلاینت پروفایل را به realtime/session می‌فرستد',"/api/realtime/session?id=" in html,'')
    check('مسیر OpenAI هم گاردریل دارد',"conversation.item.input_audio_transcription.completed" in html,'')
finally:
    srv.shutdown(); srv.server_close()
    os.environ.pop('OPENAI_API_KEY',None)
    m.ureq.urlopen=orig

print('--- 7) سرو شدن فایل‌ها از سرور واقعی ---')
for path,needle in [('/index.html','tryLiveVoice'),('/sw.js','sepandyar-v2'),('/manifest.webmanifest','سپندیار')]:
    st,body=req(BASE,path)
    check('GET '+path+' 200 است',st==200,st)
    text=body.get('_raw') or json.dumps(body,ensure_ascii=False)
    check('GET '+path+' محتوا دارد',needle in text,text[:80])

print()
print('--- 8) پایداری در برابر بدنهٔ خراب و تکرار درخواست ---')
# چهار باگ واقعی که در این مرحله پیدا شد:
#  الف) بدنهٔ JSON خراب {} تلقی می‌شد و پروفایل گویش را از نو می‌نوشت (از دست رفتن داده)
#  ب) کلید idempotency پرداخت هرگز جست‌وجو نمی‌شد -> تراکنش تکراری، کرش UNIQUE
#  ج) اتصالِ رهاشدهٔ وسط تراکنش، قفل نوشتن را نگه می‌داشت -> کل API می‌مرد
#  د) [] و null و "x" از try بیرون خطا می‌دادند و اتصال بی‌پاسخ بسته می‌شد

def raw(path,payload,headers=None,hdr=None):
    """بدنهٔ خام می‌فرستد؛ اگر اتصال بی‌پاسخ بسته شود None برمی‌گرداند."""
    u=urlparse(BASE)
    conn=http.client.HTTPConnection(u.hostname,u.port,timeout=30)
    h={'Content-Type':'application/json'}
    if hdr: h.update(hdr)
    try:
        conn.request('POST',path,body=payload,headers=h)
        r=conn.getresponse(); b=r.read(); st=r.status
        conn.close()
        try: return st,json.loads(b or b'{}')
        except Exception: return st,{'_raw':(b or b'').decode('utf-8','replace')}
    except Exception as e:
        try: conn.close()
        except Exception: pass
        return None,{'_err':type(e).__name__}

# --- الف) بدنهٔ خراب باید 400 بدهد، نه 200 ---
for bad in [b'{', b'{"a":', b'\xff\xfe', b'not json at all']:
    st,body=raw('/api/voice-profile',bad)
    check('بدنهٔ خراب %r روی voice-profile -> 400'%(bad[:12],),st==400,st)
    check('بدنهٔ خراب %r کد invalid_json دارد'%(bad[:12],),body.get('error')=='invalid_json',body)

st,body=raw('/api/conversation',b'{')
check('بدنهٔ خراب روی conversation -> 400',st==400,st)
st,body=raw('/api/conversation',json.dumps({'text':'سلام'},ensure_ascii=False).encode('utf-8'))
check('بدنهٔ سالم روی conversation -> 200',st==200,st)

# --- ب) بدنهٔ غیر شیء (JSON معتبر ولی نامناسب) ---
for bad,label in [(b'[]','آرایه'),(b'null','null'),(b'"x"','رشته'),(b'42','عدد')]:
    st,body=raw('/api/voice-profile',bad)
    check('بدنهٔ %s -> 400 (نه اتصال قطع‌شده)'%label,st==400,st)

# --- پ) از دست نرفتن پروفایل ---
req(BASE,'/api/voice-profile','POST',{'id':'default','name':'کاربر اصلی','dialect':'shirazi',
    'patience_ms':2600,'confidence_floor':0.6,'calibrated':True})
raw('/api/voice-profile',b'{')
st,prof=req(BASE,'/api/voice-profile?id=default')
check('پس از بدنهٔ خراب، لهجهٔ پروفایل حفظ شده',prof.get('dialect')=='shirazi',prof)
check('پس از بدنهٔ خراب، patience حفظ شده',prof.get('patience_ms')==2600,prof)
check('پس از بدنهٔ خراب، calibrated حفظ شده',bool(prof.get('calibrated')),prof)
# به‌روزرسانی جزئی هم نباید لهجه را پاک کند
req(BASE,'/api/voice-profile','POST',{'id':'default','patience_ms':3000})
st,prof=req(BASE,'/api/voice-profile?id=default')
check('به‌روزرسانی جزئی، لهجه را پاک نمی‌کند',prof.get('dialect')=='shirazi',prof)
check('به‌روزرسانی جزئی، patience را عوض می‌کند',prof.get('patience_ms')==3000,prof)

# --- ت) idempotency کیف پول ---
st,before=req(BASE,'/api/wallet')
bal0=before['balance']
k='regress-pay-'+str(os.getpid())
st,a=req(BASE,'/api/wallet/payment','POST',{'amount':15000,'description':'رگرسیون'})
check('پرداخت اول 200 است',st==200,st)
st,b=req(BASE,'/api/wallet/payment','POST',{'amount':15000,'description':'رگرسیون'},)
st2,a2=raw('/api/wallet/payment',json.dumps({'amount':15000,'description':'رگرسیون'}).encode(),hdr={'Idempotency-Key':k})
st3,b2=raw('/api/wallet/payment',json.dumps({'amount':15000,'description':'رگرسیون'}).encode(),hdr={'Idempotency-Key':k})
check('تکرار کلید پرداخت، 200 می‌دهد (نه 500)',st3==200,st3)
check('تکرار کلید پرداخت نشان replayed دارد',b2.get('replayed') is True,b2)
check('تکرار کلید پرداخت، همان تراکنش را برمی‌گرداند',b2.get('transaction_id')==a2.get('transaction_id'),(a2,b2))
st,w=req(BASE,'/api/wallet')
check('تکرار کلید پرداخت، موجودی را دوبار کم نمی‌کند',w['balance']==a2['balance'],(a2['balance'],w['balance']))
# دو شارژ یکسانِ جدا باید هر دو اعمال شوند
st,t1=req(BASE,'/api/wallet/topups','POST',{'amount':40000})
st,t2=req(BASE,'/api/wallet/topups','POST',{'amount':40000})
check('دو شارژ یکسانِ جدا، دو تراکنش می‌سازند',t1['transaction_id']!=t2['transaction_id'],(t1,t2))
check('دو شارژ یکسانِ جا، هر دو به موجودی اضافه می‌شوند',t2['balance']==t1['balance']+40000,(t1,t2))
# مبلغ نامعتبر -> 400 نه 500
st,inv=raw('/api/wallet/topups',b'{"amount":"abc"}')
check('مبلغ غیرعددی -> 400',st==400,st)
check('مبلغ غیرعددی کد invalid_amount دارد',inv.get('error')=='invalid_amount',inv)

# --- ث) سرور پس از همهٔ این‌ها زنده و پایگاه‌داده باز است ---
alive=[]
for ep in ['/api/wallet','/api/dialects','/api/medications','/api/profile','/api/voice-profile?id=default']:
    st,_=req(BASE,ep)
    alive.append((ep,st))
check('پس از بدنه‌های خراب، همهٔ اندپوینت‌ها 200اند',[s for _,s in alive]==[200]*len(alive),alive)
# قفل نوشتن رهاشده نباید باقی بماند
import sqlite3 as _sq
try:
    _c=_sq.connect(os.path.join(ROOT,'sepandyar.db'),timeout=3); _c.execute('BEGIN IMMEDIATE'); _c.rollback(); _c.close()
    locked=False
except Exception as e:
    locked=True
check('قفل نوشتن رهاشده روی پایگاه‌داده نمانده',not locked,'database is locked')

# --- ج) کلاینت: کلید تکرارناپذیری و صف آفلاین ---
check('queueOffline کلید Idempotency-Key می‌سازد',
      "o.headers['Idempotency-Key']=idemId()" in html)
check('صف آفلاین شناسهٔ یکتا برای هر آیتم می‌سازد',"q.push({id:idemId()" in html)
check('همگام‌سازی صف، قفل بازورودی دارد','if(flushingQueue)return;' in html.replace(' ',''))
check('همگام‌سازی صف ادغام می‌کند نه بازنویسی','failed.concat(added)' in html)
check('درخواست‌های تازهٔ حین همگام‌سازی دور ریخته نمی‌شوند','const added=readQueue().filter' in html)
check('سرور کلید تکرارناپذیری پرداخت را جست‌وجو می‌کند',
      "if p=='/api/wallet/payment':" in srvsrc and 'FROM transactions WHERE idempotency_key=?' in srvsrc)
check('کلید مشتق از بدنه حذف شده (شارژهای یکسان را یکی نمی‌کرد)',
      "hashlib.sha256(json.dumps(d,sort_keys=True)" not in srvsrc)
check('اتصال پایگاه‌داده در پایان درخواست بسته می‌شود','try: c.close()' in srvsrc)
check('do_POST کامل در try پیچیده شده','def _post(self):' in srvsrc)
check('do_GET کامل در try پیچیده شده','def _get(self):' in srvsrc)

# بازگردانی پروفایل به حالت پیش‌فرض تا اجرای بعدی این سوئیت همان نتیجه را بدهد
req(BASE,'/api/voice-profile','POST',{'id':'default','name':'کاربر','dialect':'standard',
    'secondary_dialect':'','patience_ms':1800,'confidence_floor':0.55,'calibrated':False})

print()
print('--- 9) احراز هویت مراقب/ادمین ---')
# باگ‌های امنیتی که در مرحلهٔ ۹ پیدا شد:
#  الف) POST /api/caregiver/session فقط شماره می‌خواست -> هرکس با دو درخواست
#       (خواندن شماره‌ها از GET /api/caregivers، سپس ورود با همان شماره)
#       توکن ۷ روزهٔ دسترسی کامل می‌گرفت
#  ب) /api/admin/* هیچ احراز هویتی نداشت -> بازنویسی دستور سیستمی AI با یک POST
#  ج) GET /api/safety/rules مجموعهٔ گاردریل را لو می‌داد (کمک به دور زدن)
import time as _t
PH='091%08d'%(_t.time_ns()%100000000)   # شمارهٔ یکتا در هر اجرا
st,d=req(BASE,'/api/caregivers','POST',{'name':'مراقب امنیت','phone':PH,'role':'family'})
check('ساخت مراقب 201 است',st==201,st)
INV=d.get('invite_code')
check('کد دعوت در پاسخ ساخت برگردانده می‌شود',bool(INV) and len(INV)>=16,INV)
req(BASE,'/api/consents','POST',{'scope':'health','granted':True})
st,dd=req(BASE,'/api/caregivers','POST',{'name':'مراقب امنیت','phone':PH,'role':'family'})
check('ساخت مراقب با شمارهٔ تکراری -> 409',st==409 and dd.get('error')=='caregiver_exists',(st,dd))

# --- شماره‌ها نباید به تماس‌گیرندهٔ ناشناس لو بروند ---
st,d=req(BASE,'/api/caregivers')
mine=[x for x in d.get('items',[]) if x.get('name')=='مراقب امنیت']
check('GET /api/caregivers پاسخ می‌دهد',st==200,st)
check('شماره برای ناشناس ماسک شده',mine and mine[0].get('phone')!=PH and '*' in str(mine[0].get('phone')),mine[:1])
check('کد دعوت هرگز در GET برنمی‌گردد','invite_code' not in json.dumps(d,ensure_ascii=False),'invite_code لو رفت')

# --- درِ ورود ---
for label,payload in [('فقط شماره',{'phone':PH}),
                      ('کد غلط لاتین',{'phone':PH,'code':'wrong-code'}),
                      ('کد غلط فارسی',{'phone':PH,'code':'کد-اشتباه'}),
                      ('کد خالی',{'phone':PH,'code':''})]:
    st,d=req(BASE,'/api/caregiver/session','POST',payload)
    check('ورود %s -> 403 (نه 500)'%label,st==403,st)
    check('ورود %s کد invalid_credentials دارد'%label,d.get('error')=='invalid_credentials',d)
st,d=req(BASE,'/api/caregiver/session','POST',{'phone':'09990001111','code':INV})
check('شمارهٔ ناشناس + کد درست -> 403',st==403,st)
check('پاسخ یکسان است تا وجود مراقب لو نرود',d.get('error')=='invalid_credentials',d)

# --- سطح ادمین بدون توکن بسته است ---
for ep in ['/api/admin/overview','/api/admin/activity','/api/admin/ai-config','/api/safety/rules']:
    st,d=req(BASE,ep)
    check('GET %s بدون توکن -> 403'%ep,st==403,st)
    check('GET %s کد caregiver_session_required دارد'%ep,d.get('error')=='caregiver_session_required',d)
st,d=req(BASE,'/api/admin/ai-config','POST',{'system_prompt':'دستور مخرب تزریق‌شده'})
check('بازنویسی دستور سیستمی بدون توکن -> 403',st==403,st)
st,d=req(BASE,'/api/admin/ai-config')
check('دستور سیستمی دست‌نخورده مانده','مخرب تزریق‌شده' not in json.dumps(d,ensure_ascii=False),d)

# --- محدودسازی نرخ، پیش از اعتبارسنجی ---
for i in range(5):
    st,d=req(BASE,'/api/caregiver/session','POST',{'phone':PH,'code':'bad%d'%i})
st,d=req(BASE,'/api/caregiver/session','POST',{'phone':PH,'code':INV})
check('پس از ۵ تلاش ناموفق، حتی کد درست -> 429',st==429,st)
check('پاسخ قفل کد too_many_attempts دارد',d.get('error')=='too_many_attempts',d)
# قفل نباید سراسری باشد
PH2='092%08d'%(_t.time_ns()%100000000)
st,d2=req(BASE,'/api/caregivers','POST',{'name':'مراقب دوم امنیت','phone':PH2,'role':'family'})
st,d2=req(BASE,'/api/caregiver/session','POST',{'phone':PH2,'code':d2.get('invite_code')})
check('قفل فقط روی همان شماره است نه سراسری',st==201 and bool(d2.get('token')),st)
TOK=d2.get('token')
AH={'X-Caregiver-Token':TOK or ''}

# --- با توکن معتبر، همه چیز باز است ---
for ep in ['/api/admin/overview','/api/admin/activity','/api/admin/ai-config','/api/safety/rules']:
    u=urlparse(BASE)
    conn=http.client.HTTPConnection(u.hostname,u.port,timeout=30)
    conn.request('GET',ep,headers=AH); r=conn.getresponse(); r.read(); conn.close()
    check('GET %s با توکن -> 200'%ep,r.status==200,r.status)

# --- اندپوینت‌های سالمند باید باز بمانند (دستگاه تک‌کاربره) ---
for ep in ['/api/profile','/api/medications','/api/dialects','/api/wallet','/api/emergency-card']:
    st,_=req(BASE,ep)
    check('اندپوینت سالمند %s باز است'%ep,st==200,st)
st,_=req(BASE,'/api/caregiver/call-request','POST',{'reason':'تست'})
check('درخواست تماس سالمند بدون توکن کار می‌کند',st==201,st)

# --- نگهبان‌های کد ---
check('توکن نشست با secrets ساخته می‌شود نه uuid4','secrets.token_urlsafe(32)' in srvsrc)
check('مقایسهٔ کد دعوت زمان‌ثابت و بایتی است',
      "hmac.compare_digest(code.encode('utf-8'),stored.encode('utf-8'))" in srvsrc)
check('محافظ ادمین در مسیر GET هست',"p.startswith('/api/admin/')" in srvsrc)
check('نتیجهٔ send() در متغیر ذخیره نمی‌شود','=send(self' not in srvsrc.replace(' ',''))

print()
print('--- 10) ورودی نامعتبر، تزریق SQL و انحراف قرارداد ---')
# باگ‌های این مرحله:
#  الف) /api/appointments وقتی doctor_id نداشت با NameError می‌ترکید (location بیرون از if
#       مقدار نمی‌گرفت) — و شکل درخواستِ خودِ کلاینت دقیقاً همان بود، پس ثبت صوتی نوبت
#       پزشک کاملاً از کار افتاده بود
#  ب) /api/location و /api/safe-zones با فیلد غایب، float(None) -> 500
#  ج) api-contract.json اصلاً JSON معتبر نبود (دو کامای جاافتاده)

# --- الف) ثبت نوبت بدون doctor_id ---
st,d=req(BASE,'/api/appointments','POST',{'title':'نوبت پزشک','provider':'دکتر رضایی',
    'location':'کلینیک','starts_at':'2026-11-01T10:00:00Z','reminder_minutes':60})
check('ثبت نوبت بدون doctor_id -> 201 (رگرسیون NameError)',st==201,st)
check('نوبت provider درست را نگه داشته',d.get('provider')=='دکتر رضایی',d)
st,d=req(BASE,'/api/appointments')
check('فهرست نوبت‌ها خوانده می‌شود',st==200 and any(x.get('provider')=='دکتر رضایی' for x in d.get('items',[])),st)
st,d=req(BASE,'/api/appointments','POST',{})
check('نوبت با بدنهٔ خالی هم 500 نمی‌دهد',st in (201,400),st)

# --- ب) اعتبارسنجی مختصات ---
for label,payload,want in [('بدون مختصات',{},400),('مختصات غیرعددی',{'lat':'abc','lon':51.4},400),
                           ('معتبر',{'lat':35.7,'lon':51.4,'accuracy':10},201)]:
    st,d=req(BASE,'/api/location','POST',payload)
    check('/api/location %s -> %d (نه 500)'%(label,want),st==want,st)
    if want==400: check('/api/location %s کد خطا دارد'%label,d.get('error')=='coordinates_required',d)
st,d=req(BASE,'/api/safe-zones','POST',{'name':'خانه','lat':35.7,'lon':51.4,'radius_m':200})
check('/api/safe-zones معتبر -> 201',st==201,st)
for label,payload,want,err in [('بدون مختصات',{'name':'خانه'},400,'coordinates_required'),
                               ('شعاع صفر',{'name':'خانه','lat':35.7,'lon':51.4,'radius_m':0},400,'invalid_radius'),
                               ('شعاع منفی',{'name':'خانه','lat':35.7,'lon':51.4,'radius_m':-5},400,'invalid_radius')]:
    st,d=req(BASE,'/api/safe-zones','POST',payload)
    check('/api/safe-zones %s -> 400 (نه 500)'%label,st==want,st)
    check('/api/safe-zones %s کد %s دارد'%(label,err),d.get('error')==err,d)
# تشخیص خروج از محدوده باید سالم بماند
st,d=req(BASE,'/api/location','POST',{'lat':36.9,'lon':52.9,'source':'test'})
check('موقعیت بیرون از محدوده شناسایی می‌شود',st==201 and len(d.get('outside_zones',[]))>=1,(st,d))

# --- پ) تزریق SQL نباید چیزی را بشکند ---
inj=["' OR '1'='1","'; DROP TABLE caregivers;--","1; DELETE FROM wallet","' UNION SELECT token,phone FROM caregiver_sessions--"]
broken=[]
for path in ['/api/caregivers','/api/medications','/api/symptoms','/api/contacts','/api/appointments','/api/conversation']:
    for pay in inj:
        st,d=req(BASE,path,'POST',{'name':pay,'text':pay,'symptom':pay,'title':pay,'phone':pay})
        if st is None or st>=500: broken.append((path,pay[:18],st))
check('هیچ payload تزریقی 500 نمی‌دهد',not broken,broken[:4])
alive=[]
for ep,want in [('/api/caregivers',200),('/api/wallet',200),('/api/medications',200),
                ('/api/dialects',200),('/api/safety/rules',403)]:  # قواعد پشت احراز هویت است
    st,_=req(BASE,ep); alive.append((ep,st,want))
check('همهٔ جدول‌ها پس از حملهٔ تزریق سالم‌اند',all(s==w for _,s,w in alive),alive)

# --- ت) api-contract.json باید JSON معتبر باشد ---
try:
    _cj=json.load(open(os.path.join(ROOT,'api-contract.json'),encoding='utf-8'))
    check('api-contract.json یک JSON معتبر است',True)
    check('api-contract.json وضعیت پیش‌نویس بودن را اعلام می‌کند',bool(_cj.get('_status')),'')
    check('انحراف اندازه‌گیری‌شده در قرارداد ثبت شده',bool(_cj.get('_measured_drift')),'')
except Exception as e:
    check('api-contract.json یک JSON معتبر است',False,type(e).__name__)

# --- ث) جاروی خودکار: هیچ اندپوینت POST نباید با بدنهٔ خالی 500 بدهد ---
import re as _re
_postsrc=srvsrc[srvsrc.find(' def _post(self):'):]
_eps=sorted(set(_re.findall(r"if p=='(/api/[a-z0-9/_-]*)':",_postsrc)))
_sweep=[]
for _e in _eps:
    try:
        _st,_d=req(BASE,_e,'POST',{})
        # 503 با ai_not_configured پاسخ درست «کلید API نیست» است، نه خطای سرور
        if _st is None or (_st>=500 and not (_st==503 and _d.get('error')=='ai_not_configured_or_unavailable')):
            _sweep.append((_e,_st,_d.get('error')))
    except Exception as _ex: _sweep.append((_e,type(_ex).__name__))
check('جاروی %d اندپوینت POST: هیچ‌کدام 500 نمی‌دهد'%len(_eps),not _sweep,_sweep[:6])

print()
print('--- 11) XSS ذخیره‌شده در داشبوردها ---')
# زنجیرهٔ حملهٔ اثبات‌شده:
#   ۱) POST /api/symptoms (بی‌احراز هویت) با symptom = <img src=x onerror=...>
#   ۲) سرور دست‌نخورده ذخیره و در /api/caregiver/panel برمی‌گرداند
#   ۳) caregiver.html با الحاق رشته در innerHTML می‌گذاشت -> اسکریپت در مبدأ مراقب
#      اجرا می‌شد و localStorage['cgToken'] را می‌دزدید
# دفاع، رمزگذاری خروجی در نقطهٔ رندر است (پژوهش: این «اصلاحی است که آسیب‌پذیری را
# تمام می‌کند»). CSP با unsafe-inline بیشتر هدف CSP را نابود می‌کند و nonce ها هم
# handler های درون‌خطی را پوشش نمی‌دهند، پس در این کدبیس راه اصلی نیست.

cghtml=open(os.path.join(ROOT,'caregiver.html'),encoding='utf-8').read()
adhtml=open(os.path.join(ROOT,'admin.html'),encoding='utf-8').read()

for name,src in [('caregiver.html',cghtml),('admin.html',adhtml),('index.html',html)]:
    check(name+' تابع esc() دارد','function esc(v)' in src)
    check(name+" esc هر پنج نویسهٔ خطرناک را می‌گیرد",
          all(t in src for t in ["&amp;","&lt;","&gt;","&quot;","&#39;"]))

# caregiver/index مقادیری داخل onclick دارند -> jsa لازم است
for name,src in [('caregiver.html',cghtml),('index.html',html)]:
    check(name+' تابع jsa() برای بافت onclick دارد','function jsa(v)' in src)

# --- رفتار واقعی رمزگذارها، با اجرای node روی خودِ توابع فایل ---
def node_check(fns,js):
    code=fns+"\n"+js
    r=subprocess.run(['node','-e',code],capture_output=True,text=True,timeout=30)
    return r.stdout.strip(),r.stderr.strip()

def extract_fns(src):
    i=src.find('function esc(v)')
    j=src.find('function jsa(v)')
    if j<0: return src[i:src.find('\n',src.find('}',i)+1)]
    k=src.find('\n',src.find('return esc(',j)+1)
    return src[i:k]

esc_care=extract_fns(cghtml)
out,err=node_check(esc_care,
  "const v='<img src=x onerror=\"alert(1)\">';"
  "const h=esc(v);"
  "console.log(JSON.stringify({lt:h.includes('<img'),amp:h.includes('&lt;'),raw:h===v}));")
try:
    r=json.loads(out)
    check('esc() برچسب را به متن تبدیل می‌کند',r['lt'] is False and r['amp'] is True,(out,err))
except Exception:
    check('esc() برچسب را به متن تبدیل می‌کند',False,(out,err))

# payload داخل onclick نباید از رشتهٔ JS بیرون بزند
out,err=node_check(esc_care,
  "let fired=[];global.alert=x=>fired.push('alert:'+x);global.saveSymptom=n=>fired.push('sym:'+n);"
  "function dec(h){return h.replace(/&quot;/g,'\"').replace(/&#39;/g,\"'\").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&')}"
  "const evil=\"a');alert('PWNED');//\";"
  "const attr=\"saveSymptom('\"+jsa(evil)+\"')\";"
  "try{eval(dec(attr))}catch(e){}"
  "console.log(JSON.stringify({fired:fired}));")
try:
    r=json.loads(out)
    check('payload داخل onclick اجرا نمی‌شود',
          not any(str(x).startswith('alert:') for x in r['fired']),(out,err))
    check('payload به‌عنوان داده به تابع می‌رسد',
          any(str(x).startswith('sym:') for x in r['fired']),(out,err))
except Exception:
    check('payload داخل onclick اجرا نمی‌شود',False,(out,err))

# --- سرور داده را دست‌نخورده نگه می‌دارد (دفاع در رندر است نه در ذخیره) ---
PAY='<img src=x onerror="alert(document.domain)">'
st,d=req(BASE,'/api/symptoms','POST',{'symptom':PAY,'severity':'متوسط','source':'test'})
check('ذخیرهٔ علامت با payload پذیرفته می‌شود',st==201,st)
st,d=req(BASE,'/api/symptoms')
check('سرور payload را دست‌نخورده برمی‌گرداند (رمزگذاری در رندر است)',
      any(PAY==x.get('symptom') for x in d.get('items',[])),'')

# --- هیچ الحاق بی‌رمزِ دادهٔ سرور در رندر نمانده باشد ---
import re as _re2
for name,src in [('caregiver.html',cghtml),('admin.html',adhtml)]:
    leaks=[]
    for m in _re2.finditer(r'innerHTML=',src):
        seg=src[m.start():m.start()+900]
        e=_re2.search(r"';(?:const|document|if|let|var|function|await|return|window)\b",seg)
        if e: seg=seg[:e.start()+1]
        for f in _re2.finditer(r"'\s*\+\s*([A-Za-z_$][\w$]*\.[\w$]+)\s*\+\s*'",seg):
            leaks.append(f.group(1))
    check(name+' الحاق بی‌رمز دادهٔ سرور در innerHTML ندارد',not leaks,leaks[:6])

print()
print('بررسی‌ها: %d · شکست: %d'%(total,len(failures)))
if failures:
    print('شکست‌ها:'); [print(' -',f) for f in failures]
sys.exit(1 if failures else 0)
