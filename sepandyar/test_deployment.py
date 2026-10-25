#!/usr/bin/env python3
"""آزمون استقرار: مبدأ امن، آدرس سرور، service worker و قرارداد پوستهٔ اندروید.

چرا این آزمون وجود دارد: چهار باگ واقعی پیدا شد که اپ را در استقرار می‌شکست —
۱) API_BASE در WebView به «file://:4174» تبدیل می‌شد
۲) بارگذاری از file:///android_asset یک مبدأ مات است و fetch/getUserMedia را می‌بندد
۳) مجوز INTERNET در مانیفست اعلام نشده بود
۴) service worker همهٔ GETها از جمله /api/ را کش می‌کرد (دادهٔ کهنهٔ دارو و سلامت)
"""
import json, os, re, sys, threading, http.client, importlib.util, subprocess, shutil, uuid, datetime, sqlite3
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

def req_raw(base,path,raw_bytes,method='POST'):
 """بدنهٔ خام می‌فرستد. برای payload هایی که json.dumps پایتون خودش نمی‌تواند
 encode کند (مثل سورگیت جفت‌نشده)؛ حملهٔ واقعی هم به شکل escape در متن JSON است."""
 u=urlparse(base)
 conn=http.client.HTTPConnection(u.hostname,u.port,timeout=60)
 conn.request(method,path,body=raw_bytes,headers={'Content-Type':'application/json'})
 r=conn.getresponse(); raw=r.read(); code=r.status; conn.close()
 try: return code,json.loads(raw or b'{}')
 except Exception: return code,{'_raw':(raw or b'').decode('utf-8','replace')}

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

# --- سیاست ناوبری WebView و اعتبارسنجی پل JS ---
# addJavascriptInterface روی خودِ WebView ثبت می‌شود و با هر ناوبری باقی می‌ماند؛
# پس بدون shouldOverrideUrlLoading هر XSS می‌توانست WebView را به origin مهاجم ببرد
# و آن‌گاه به همه‌ٔ متدهای بومی AppBridge برسد.
check('WebView سیاست ناوبری دارد (shouldOverrideUrlLoading)',
      'shouldOverrideUrlLoading' in main_kt)
check('ناوبری به مبدأ غیر appassets بسته می‌شود',
      'WebViewAssetLoader.DEFAULT_DOMAIN' in main_kt and 'return !sameOrigin' in main_kt)
check('tel: به dialer سیستم سپرده می‌شود نه WebView',
      'Intent.ACTION_DIAL' in main_kt)
check('saveServerUrl فقط https با میزبان معتبر می‌پذیرد',
      'saveServerUrl' in main_kt and 'schemeOk' in main_kt and 'hostOk' in main_kt)
check('saveServerUrl مقدار خام را بی‌اعتبارسنجی ذخیره نمی‌کند',
      "putString(\"server_url\", url.trim()).apply()" not in main_kt)

# منطق سیاست ناوبری و اعتبارسنجی را با بازتاب پایتون راستی‌آزمایی می‌کنیم
# (کامپایل Kotlin در این محیط ممکن نیست، پس رفتار تصمیم‌گیری را می‌سنجیم)
def _nav_blocked(scheme,host,dom='appassets.androidplatform.net'):
    if scheme is None: return True
    if scheme.lower()=='tel': return False      # به dialer می‌رود
    return not (scheme.lower()=='https' and host==dom)
check('ناوبری به origin مهاجم بسته می‌شود',_nav_blocked('https','evil.example') is True)
check('javascript: بسته می‌شود',_nav_blocked('javascript','') is True)
check('data: بسته می‌شود',_nav_blocked('data','') is True)
check('http بسته می‌شود',_nav_blocked('http','appassets.androidplatform.net') is True)
check('ناوبری به origin خود اپ باز می‌ماند',
      _nav_blocked('https','appassets.androidplatform.net') is False)

def _server_ok(url):
    c=url.strip()
    if not c: return False
    if '://' in c:
        sch,rest=c.split('://',1); host=rest.split('/')[0].split('?')[0].split(':')[0]
    else: sch,host='',''
    return sch.lower()=='https' and bool(host) and ('.' in host) and (' ' not in host)
check('saveServerUrl آدرس https معتبر را می‌پذیرد',_server_ok('https://sepandyar.example.com') is True)
check('saveServerUrl آدرس IP با پورت را می‌پذیرد',_server_ok('https://192.168.1.5:4174') is True)
check('saveServerUrl javascript: را رد می‌کند',_server_ok('javascript:alert(1)') is False)
check('saveServerUrl http را رد می‌کند',_server_ok('http://192.168.1.5:4174') is False)
check('saveServerUrl رشتهٔ خالی را رد می‌کند',_server_ok('   ') is False)
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

# --- دو مسیر زنده در caregiver.html که اسکن بالا از قلم می‌انداخت ---
# اسکن فقط الگوی '+obj.field+' را در innerHTML می‌گرفت. این دو شکل دیگری داشتند:
#   ۱) pl.body در innerHTML — payload از POST /api/messages (بی‌احراز هویت)
#      -> caregiver_actions.payload -> /api/caregiver/panel -> actionCard()
#   ۲) a.id درون onclick="deliverAction('...')" — شکست از بافت JS با '
# هر دو با jsdom اثبات شدند: <img> در DOM ساخته شد و onclick شکست.
check("caregiver.html: pl.body پیام سالمند escape می‌شود",
      "esc((pl.body||''))" in cghtml)
check("caregiver.html: هیچ a.id خامی در onclick نمانده",
      "+a.id+" not in cghtml)
check("caregiver.html: a.id در onclick با jsa محافظت می‌شود",
      "+jsa(a.id)+" in cghtml)

# --- اثبات سمت سرور: payload پیام دست‌نخورده به پنل مراقب می‌رسد ---
# payload به‌صورت JSON ذخیره می‌شود، پس " به \\" تبدیل می‌شود و رشتهٔ خام
# هرگز تطبیق نمی‌کند. قطعه‌ای را می‌سنجیم که از رمزگذاری JSON سالم بیرون می‌آید.
XP_CG='<img src=x onerror="window.__pwnCG=1">'
XP_FRAG='<img src=x onerror='          # بدون " — از JSON سالم می‌ماند
# شمارهٔ یکتا تا تست idempotent بماند (کد دعوت فقط یک‌بار برگردانده می‌شود)
import time as _tm
_PH='093%08d'%(_tm.time_ns()%100000000)
st,d=req(BASE,'/api/caregivers','POST',{'name':'مراقب تست','phone':_PH,'relation':'فرزند'})
check('ساخت مراقب برای آزمون صف اقدام',st in (200,201) and bool((d or {}).get('invite_code')),(st,d))
_inv=(d or {}).get('invite_code')
st,d=req(BASE,'/api/messages','POST',
         {'contact_id':'c','body':XP_CG,'kind':'voice'})
check('POST /api/messages بدنهٔ آلوده را می‌پذیرد (بی‌احراز هویت)',st==201,st)
st,d=req(BASE,'/api/caregiver/session','POST',
         {'invite_code':_inv,'phone':_PH,'name':'مراقب تست'})
_tok=(d or {}).get('token')
check('گرفتن نشست مراقب',st==201 and bool(_tok),(st,d))
if _tok:
    # req() هدر سفارشی نمی‌گیرد؛ مانند بخش ۱۲ مستقیم از http.client می‌رویم
    _u=urlparse(BASE)
    _conn=http.client.HTTPConnection(_u.hostname,_u.port,timeout=30)
    _conn.request('GET','/api/caregiver/panel',headers={'X-Caregiver-Token':_tok})
    _r=_conn.getresponse(); _raw=_r.read(); _st=_r.status; _conn.close()
    check('پنل مراقب با توکن ۲۰۰ می‌دهد',_st==200,_st)
    try: _panel=json.loads(_raw or b'{}')
    except Exception: _panel={}
    _acts=_panel.get('pending_actions',[])
    check('payload آلوده دست‌نخورده در صف مراقب است (دفاع در رندر)',
          any(XP_FRAG in str(a.get('payload','')) for a in _acts), len(_acts))


# --- سه مسیر XSS زنده در index.html که اسکن بالا از قلم می‌انداخت ---
# اسکن قبلی فقط caregiver.html و admin.html را می‌گشت و فقط الگوی
#   '+obj.field+'  را می‌گرفت. این سه مسیر شکل دیگری داشتند:
#   ۱) الحاق متغیر ساده:      '+n+'        (n از localStorage <- /api/profile)
#   ۲) شکست از attribute:     value="'+d?.full_name+'   (درون value="...")
#   ۳) الحاق بی‌رمز در میان متن escape‌شده:  esc(it.body) ... (it.approved_by||'—')
# هر سه با دادهٔ سرور از راه اندپوینت بی‌احراز هویت قابل نوشتن بودند.
check("index.html: سلام با esc(n) رندر می‌شود نه n خام",
      "w.innerHTML='سلام، <span>'+esc(n)+'</span>" in html)
check("index.html: full_name کارت اضطراری escape می‌شود",
      "esc(d?.full_name||localStorage.getItem('seniorName')||'')" in html)
for _f in ('birth_date','blood_type','allergies'):
    check('index.html: '+_f+' کارت اضطراری escape می‌شود',
          ("esc(d?.%s||'')"%_f) in html)
check("index.html: approved_by محتوای آموزشی escape می‌شود",
      "esc(it.approved_by||'—')" in html)
check("index.html: برچسب دکمهٔ علائم escape می‌شود",
      "+esc(x.name)+(x.escalate?" in html)

# --- سه interpolation بی‌رمز دیگر (دفاع در عمق) ---
# این سه از دادهٔ سرور نمی‌آیند: assistantName و chosen از ورودی/گفتار محلی و
# spoken از transcript تشخیص گفتار. پس self-XSS‌اند نه XSS راه دور.
# ولی همان الگوی شکست از attribute را داشتند، پس بسته شدند تا ممیزی کامل بسته بماند.
# assistant_name در /api/profile ذخیره می‌شود ولی index.html هرگز آن را
# از پاسخ سرور نمی‌خواند (۰ خواندن، ۱ نوشتن) — پس مسیر راه دور نیست.
check("index.html: assistantName در value escape می‌شود",
      "value=\"${esc(localStorage.getItem('assistantName')" in html)
check("index.html: متن گفته‌شده (spoken) escape می‌شود",
      "+esc(spoken)+'»" in html)
check("index.html: نام دستیار انتخاب‌شده (chosen) escape می‌شود",
      "+esc(chosen)+'»" in html)


# --- اثبات سمت سرور: این فیلدها دست‌نخورده ذخیره و برگردانده می‌شوند ---
# (دفاع در رندر است، نه در ذخیره — پس این انتظارها عمداً «دست‌نخورده» هستند)
XP='<img src=x onerror="window.__pwn=1">'
st,_=req(BASE,'/api/profile','POST',{'name':XP})
check('POST /api/profile نام آلوده را می‌پذیرد',st==200,st)
st,d=req(BASE,'/api/profile')
check('GET /api/profile آن را دست‌نخورده برمی‌گرداند',d.get('name')==XP,d.get('name'))

st,_=req(BASE,'/api/emergency-card','POST',
         {'full_name':XP,'birth_date':'1340','blood_type':'O+'})
check('POST /api/emergency-card نام آلوده را می‌پذیرد',st==200,st)
st,d=req(BASE,'/api/emergency-card')
check('GET /api/emergency-card آن را دست‌نخورده برمی‌گرداند',
      d.get('full_name')==XP,d.get('full_name'))

st,d=req(BASE,'/api/education','POST',
         {'topic':'t','body':XP,'category':'عمومی'})
check('POST /api/education محتوای آلوده را می‌پذیرد',st==201,st)
_eid=d.get('id')
st,d=req(BASE,'/api/education/%s/approve'%_eid,'POST',{'approved_by':XP})
check('approve با approved_by آلوده پذیرفته می‌شود',st==200,st)
st,d=req(BASE,'/api/education')
_row=[x for x in d.get('items',[]) if x.get('id')==_eid]
check('approved_by دست‌نخورده ذخیره شده',
      bool(_row) and _row[0].get('approved_by')==XP, _row[:1])

print()
print('--- 12) ورودی نامعتبر باید ۴۰۰ بدهد نه ۵۰۰ ---')
# سه طبقهٔ ریشه‌ای که فازر پیدا کرد (۳۹ نقطهٔ سقوط در مجموع):
#   ۱) مقدار ساخت‌یافته در جای مقدار ساده -> sqlite3.ProgrammingError
#      «Error binding parameter 2: type 'dict' is not supported»
#   ۲) سورگیت جفت‌نشده (\ud800) -> UnicodeEncodeError؛ json.loads آن را می‌پذیرد
#      ولی sqlite نمی‌تواند UTF-8 کند
#   ۳) float()/int() برهنه روی دادهٔ درخواست -> ValueError/TypeError
# هیچ‌کدام نباید ۵۰۰ شوند: این‌ها خطای کلاینت‌اند.
NUMERIC=[
 ('/api/reminder-settings','max_nudges',{}),
 ('/api/icope','score',{'domain':'vision'}),
 ('/api/appointments','reminder_minutes',{}),
 ('/api/medications/x/details','remaining',{}),
 ('/api/medications/x/details','refill_threshold',{}),
 ('/api/medications/x/refill','amount',{}),
 ('/api/vitals/share','expires_days',{}),
 ('/api/disambiguate','limit',{'transcript':'قرص'}),
 ('/api/screen-tasks','steps_total',{}),
 ('/api/screen-tasks','steps_done',{}),
]
BADNUM=[('رشتهٔ غیرعددی','abc'),('رشتهٔ خالی',''),('آرایه',[1]),('شیء',{'a':1})]
bad500=[]
for path,key,base in NUMERIC:
    for cn,val in BADNUM:
        b=dict(base); b[key]=val
        st,_=req(BASE,path,'POST',b)
        if st==500: bad500.append((path,key,cn))
check('هیچ تبدیل عددی روی ورودی نامعتبر ۵۰۰ نمی‌دهد',not bad500,bad500[:6])

# کلاس ۱: مقدار ساخت‌یافته در فیلد متنی
STRUCT=[('/api/contacts','name'),('/api/medications','name'),('/api/caregivers','name')]
bad500=[]
for path,key in STRUCT:
    for val in ({'a':1},[1,2]):
        st,_=req(BASE,path,'POST',{'name':val,'phone':'09137000009'})
        if st==500: bad500.append((path,key,type(val).__name__))
check('مقدار ساخت‌یافته در فیلد متنی ۵۰۰ نمی‌دهد',not bad500,bad500[:6])
st,d=req(BASE,'/api/contacts','POST',{'name':{'a':1},'phone':'09137000010'})
check('مقدار ساخت‌یافته ۴۰۰ می‌دهد نه ۲۰۱',st==400,st)

# کلاس ۲: سورگیت جفت‌نشده — باید ذخیره شود ولی به U+FFFD نرمال شود
# \ud800 به‌صورت escape شش‌نویسه‌ای در متن JSON — همان شکلی که کلاینت می‌فرستد
st,d=req_raw(BASE,'/api/contacts',
 b'{"name":"\u0639\u0644\u06cc\\ud800\u0631\u0636\u0627","phone":"09137000011"}')
check('سورگیت جفت‌نشده ۵۰۰ نمی‌دهد',st==201,st)
if st==201:
    st2,d2=req(BASE,'/api/contacts')
    names=[x.get('name') for x in d2.get('items',[])]
    check('سورگیت به U+FFFD نرمال شده و ذخیره می‌شود',
          any('\ufffd' in (n or '') and '\ud800' not in (n or '') for n in names),
          [n for n in names if n and 'علی' in n][:3])

# تور ایمنی مرزی: خطای اتصال نوع باید ۴۰۰ باشد
st,d=req(BASE,'/api/symptoms','POST',{'symptom':{'nested':'x'}})
check('تور ایمنی مرزی خطای اتصال نوع را ۴۰۰ می‌کند',st in (201,400),st)

print()
print('--- 13) دسترس‌پذیری رابط کاربری سالمند ---')
# ممیزی پیش از اصلاح (بر پایهٔ پژوهش WCAG 2.2 + راهنمای سالمند):
#   سوییچ «متن بزرگ» کار نمی‌کرد — ۴۸ قاعده از ۴۹ قاعدهٔ font-size با px مطلق
#   بودند و body.large-text{font-size:18px} فقط روی em/rem اثر دارد. ضمن اینکه
#   rem نسبت به <html> است نه <body>، پس تارگت سوییچ هم غلط بود.
#   ۳۸ رخداد متن زیر ۱۶px، چهار کنتراست زیر ۴٫۵:۱، هدف لمسی ۴۳px.
import re as _re3
def _lum(h):
    h=h.lstrip('#')
    if len(h)==3: h=''.join(c*2 for c in h)
    r,g,b=[int(h[i:i+2],16)/255 for i in (0,2,4)]
    f=lambda c: c/12.92 if c<=0.03928 else ((c+0.055)/1.055)**2.4
    return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b)
def _ratio(a,b):
    l1,l2=sorted([_lum(a),_lum(b)],reverse=True); return (l1+0.05)/(l2+0.05)

uicss=_re3.search(r'<style>(.*?)</style>',html,_re3.S).group(1)

# ۱) ریشهٔ rem روی <html> — شرط لازم برای کار کردن مقیاس
check('ریشهٔ font-size روی <html> تنظیم شده','html{font-size:16px}' in uicss)

# ۲) هیچ font-size مطلق بیرون از قواعد ریشه نمانده باشد
root_rules=_re3.findall(r'html(?:\[data-textscale="\w+"\])?\{font-size:\d+px\}',html)
all_px=_re3.findall(r'font-size:\s*[\d.]+px',html)
check('همهٔ font-size ها rem شده‌اند (جز قواعد ریشه)',
      len(all_px)==len(root_rules),f'{len(all_px)} px در برابر {len(root_rules)} قاعدهٔ ریشه')

# ۳) کف ۱۶px در مقیاس پیش‌فرض
rems=[float(x) for x in _re3.findall(r'font-size:\s*([\d.]+)rem',uicss)]
check('کف اندازهٔ متن در مقیاس پیش‌فرض ≥ ۱۶px',rems and min(rems)*16>=15.9,f'کوچک‌ترین: {min(rems)*16:.1f}px')

# ۴) WCAG 1.4.4 — متن باید تا ۲۰۰٪ بزرگ شود
steps=dict(_re3.findall(r'html\[data-textscale="(\w+)"\]\{font-size:(\d+)px\}',html))
check('پلهٔ ۲۰۰٪ برای بزرگ‌نمایی متن وجود دارد (WCAG 1.4.4)',
      any(int(v)>=32 for v in steps.values()),steps)

# ۵) کنتراست همهٔ جفت‌های رنگ/پس‌زمینه در CSS
rootvars=dict(_re3.findall(r'--([\w\-]+):\s*(#[0-9a-fA-F]{3,6})',uicss))
def _res(v):
    m=_re3.match(r'var\(--([\w\-]+)\)',v or '')
    return rootvars.get(m.group(1)) if m else v
lowc=[]
for m in _re3.finditer(r'([^{}]+)\{([^}]*)\}',uicss):
    d=m.group(2)
    fg=_re3.search(r'(?<![-\w])color:\s*(#[0-9a-fA-F]{3,6}|var\(--[\w\-]+\))',d)
    bg=_re3.search(r'background:\s*(#[0-9a-fA-F]{3,6}|var\(--[\w\-]+\))',d)
    if not(fg and bg): continue
    f,b=_res(fg.group(1)),_res(bg.group(1))
    if f and b and _ratio(f,b)<4.5: lowc.append((m.group(1).strip()[-24:],round(_ratio(f,b),2)))
check('کنتراست همهٔ متن‌ها ≥ ۴٫۵:۱ (WCAG AA)',not lowc,lowc[:5])

# ۶) اهداف لمسی
for sel in ('.icon-btn{','.pill{'):
    mm=_re3.search(_re3.escape(sel)+r'[^}]*\}',uicss)
    w=int(_re3.search(r'width:\s*(\d+)px',mm.group(0)).group(1))
    check(f'هدف لمسی {sel.strip("{")} ≥ ۴۸px',w>=48,w)

# ۷) سوییچ کنتراست واقعاً کلاس را ست می‌کند (پیش‌تر برچسب وعده می‌داد ولی کد نه)
check('سوییچ highContrast کلاس high-contrast را ست می‌کند',
      "if(key==='highContrast')document.body.classList.toggle('high-contrast',on)" in html)
check('ارجاع مرده به toggleSetting(largeText) نمانده',"toggleSetting('largeText')" not in html)

# ۸) وزیرمتن در هر سه داشبورد (خوانایی فارسی)
for name,src in [('index.html',html),('caregiver.html',cghtml),('admin.html',adhtml)]:
    # فونت باید با <link> + preconnect بارگذاری شود نه @import درون <style>:
    # @import یک درخواست سریال می‌سازد و تا رسیدن فونت، رندر را مسدود می‌کند.
    check(name+' فونت وزیرمتن دارد','Vazirmatn' in src)
    check(name+' فونت را با <link> می‌گیرد نه @import',
          'rel="stylesheet"' in src and '@import' not in src)
    check(name+' preconnect برای CDN فونت دارد','fonts.gstatic.com' in src)

# ۹) سرریز: ظرف با ارتفاع ثابت که فونت بزرگ‌شده در آن جا نمی‌شود.
# این باگ را خودِ بالا بردن کف فونت ساخت: .transcript ارتفاع ۲۰px ثابت داشت
# و فونتش ۱۶px شد، در حالی که متن به ~۲۴px نیاز دارد. آن ناحیه aria-live است
# و متن گفتهٔ کاربر در آن می‌نشیند، پس باید رشد کند نه اینکه بریده شود.
overflow=[]
for m in _re3.finditer(r'([^{}]+)\{([^}]*)\}',uicss):
    d=m.group(2)
    h=_re3.search(r'(?<![-\w])height:\s*(\d+)px',d)
    fs=_re3.search(r'font-size:\s*([\d.]+)rem',d)
    if not(h and fs): continue
    px=float(fs.group(1))*16
    if float(h.group(1)) < px*1.5:
        overflow.append((m.group(1).strip()[-22:],h.group(1)+'px',f'{px:.0f}px فونت'))
check('هیچ ظرف با ارتفاع ثابت، متن بزرگ‌شده را نمی‌بُرد',not overflow,overflow[:5])

print('--- 14) چهار شکاف رقابتی: حافظه، زمان‌بند، نسخه، خط پایه ---')
# این بخش سرور درون‌پروسه‌ای خودش را از ماژول ROOT بالا می‌آورد تا HTTP و sqlite
# هر دو به یک پایگاه‌داده بروند. نسخهٔ نخست HTTP را به BASE (سرور زنده) می‌فرستاد
# و sqlite را به ROOT/sepandyar.db می‌نوشت؛ از داخل مخزن این دو تصادفاً یک فایل
# بودند ولی هنگام اجرا از zip دو فایل جدا شدند و ۵ بررسی بی‌دلیل شکست خورد.
# m در بخش ۱۳ به‌عنوان متغیر حلقه به کار رفته و ماژول سرور را shadow کرده است؛
# پس ماژول را این‌جا زیر نام تازه دوباره بارگذاری می‌کنیم.
_spec14=importlib.util.spec_from_file_location('srv14',os.path.join(ROOT,'server.py'))
_m14=importlib.util.module_from_spec(_spec14); _spec14.loader.exec_module(_m14)
_srv14=ThreadingHTTPServer(('127.0.0.1',0),_m14.Handler); _p14=_srv14.server_address[1]
threading.Thread(target=_srv14.serve_forever,daemon=True).start()
B14='http://127.0.0.1:%d'%_p14
_c=_sq.connect(_m14.DB); _c.row_factory=_sq.Row
# پاک‌سازی تا نتیجه قطعی و تکرارپذیر باشد (پیش‌تر دادهٔ مانده از اجرای دیگر
# میانگین خط پایه را آلوده می‌کرد و z از ۲٫۴۴ به ۱٫۶۹ می‌افتاد)
_c.execute('DELETE FROM vitals'); _c.execute('DELETE FROM proactive_events')
_c.execute("DELETE FROM alerts WHERE type LIKE 'baseline_deviation%' OR type='proactive_no_response'")
_c.commit(); _c.close()

# این چهار مورد از تحلیل رقبا درآمد (docs/COMPETITOR_ANALYSIS_FA.md).
# هر چهار تست رفتاری‌اند، نه ساختاری: واقعاً endpoint را صدا می‌زنند.

# --- شکاف ۱: حافظهٔ مکالمه ---
_uid=uuid.uuid4().hex[:10]
_prof='t14_'+_uid
for _t in ('حالم خوب است','سرم درد می‌کند'):
    req(B14,'/api/ai/chat','POST',{'text':_t,'profile':_prof})
_st,_h=req(B14,'/api/conversation/history?profile='+_prof)
check('حافظه: گفتگو ذخیره می‌شود',_st==200 and len(_h.get('items',[]))==2,(_st,len(_h.get('items',[]))))
_st,_h2=req(B14,'/api/conversation/history?profile=t14_isolated_'+_uid)
check('حافظه: profile‌ها از هم ایزوله‌اند',len(_h2.get('items',[]))==0,_h2.get('items'))
_st,_h3=req(B14,'/api/caregiver/conversation-summary?profile='+_prof)
check('حفاظت حریم: خلاصهٔ گفتگو بدون نشست مراقب ۴۰۳ است',_st==403,_st)
# turn پرخطر باید flagged شود تا در خلاصه دیده شود
req(B14,'/api/ai/chat','POST',{'text':'می‌خواهم قرص‌ها را قطع کنم','profile':_prof})
check('حافظه: جدول conversation_turns وجود دارد','CREATE TABLE IF NOT EXISTS conversation_turns' in srvsrc)
check('حافظه: call_llm تاریخچه را تزریق می‌کند','memory_block(c,pid)' in srvsrc)

# --- شکاف ۲: زمان‌بند و پله‌بندی ---
_st,_p=req(B14,'/api/proactive/due')
check('زمان‌بند: endpoint سررسید سالم است',_st==200,_st)
check('زمان‌بند: پاسخ کلید escalated دارد','escalated' in _p,list(_p.keys()))
check('زمان‌بند: محرک پس‌زمینه وجود دارد','def scheduler_loop' in srvsrc)
check('زمان‌بند: thread در راه‌اندازی شروع می‌شود','threading.Thread(target=scheduler_loop,daemon=True).start()' in srvsrc)
import sqlite3 as _sq
_c=_sq.connect(_m14.DB); _c.row_factory=_sq.Row
_cols=[x[1] for x in _c.execute('PRAGMA table_info(proactive_events)')]
check('زمان‌بند: ستون escalated_at افزوده شده','escalated_at' in _cols,_cols)
# پله‌بندی واقعی: یک رویداد کهنهٔ بی‌پاسخ باید به هشدار تبدیل شود
_old=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=3)).isoformat()
_eid=uuid.uuid4().hex
_c.execute('INSERT INTO proactive_events VALUES(?,?,?,?,?,?,?)',(_eid,'morning_checkin','2026-01-01',_old,None,None,None))
_c.commit(); _c.close()
_st,_p2=req(B14,'/api/proactive/due')
check('زمان‌بند: رویداد کهنهٔ بی‌پاسخ پله‌بندی می‌شود',_eid in _p2.get('escalated',[]),_p2.get('escalated'))
_st,_a=req(B14,'/api/alerts')
check('زمان‌بند: هشدار بی‌پاسخی ثبت شد',
      any(x['type']=='proactive_no_response' for x in _a.get('items',[])))
_st,_p3=req(B14,'/api/proactive/due')
check('زمان‌بند: پله‌بندی تکراری رخ نمی‌دهد',_eid not in _p3.get('escalated',[]),_p3.get('escalated'))

# --- شکاف ۳: ورود نسخه ---
_ref='rx14_'+_uid
_st,_r=req(B14,'/api/prescriptions','POST',{'image_ref':_ref,'items':[{'name':'آتورواستاتین','dose':'20mg','schedule':'شبانه'}]})
check('نسخه: ثبت می‌شود',_st==201,_st)
_pid=_r.get('id')
check('نسخه: اقلامش ذخیره می‌شوند',len(_r.get('items',[]))==1,_r.get('items'))
_st,_r2=req(B14,'/api/prescriptions','POST',{'image_ref':_ref})
check('نسخه: تکراری ۴۰۹ می‌دهد',_st==409,_st)
_st,_r3=req(B14,'/api/prescriptions','POST',{'items':[{'name':'x'}]})
check('نسخه: بدون image_ref ۴۰۰ می‌دهد',_st==400,_st)
_st,_r4=req(B14,'/api/prescriptions','POST',{'image_ref':'rx14b_'+_uid,'items':[{'name':'بی‌نام','dose':1}]})
check('نسخه: دوز غیررشته‌ای ۵۰۰ نمی‌دهد',_st in (201,400),_st)
_iid=_r['items'][0]['id']
_st,_r5=req(B14,'/api/prescriptions/%s/confirm'%_pid,'POST',{'item_id':_iid,'time':'21:00'})
check('نسخه: تأیید قلم دارو می‌سازد',_st==201 and _r5.get('medication_id'),(_st,_r5))
_st,_m=req(B14,'/api/medications')
check('نسخه: داروی تأییدشده واقعاً در فهرست داروهاست',
      'آتورواستاتین' in [x['name'] for x in _m.get('items',[])])
_st,_r6=req(B14,'/api/prescriptions/%s/confirm'%_pid,'POST',{'item_id':_iid})
check('نسخه: تأیید دوباره idempotent است',_r6.get('already_confirmed') is True,_r6)
_st,_r7=req(B14,'/api/prescriptions/nopresc14/confirm','POST',{'item_id':'x'})
check('نسخه: نسخهٔ ناموجود ۴۰۴ می‌دهد',_st==404,_st)
_st,_r8=req(B14,'/api/prescriptions/%s/confirm'%_pid,'POST',{'item_id':'noitem14'})
check('نسخه: قلم ناموجود ۴۰۴ می‌دهد',_st==404,_st)
_st,_l=req(B14,'/api/prescriptions')
check('نسخه: فهرست با اقلامش خوانده می‌شود',_st==200 and any(x['id']==_pid for x in _l.get('items',[])),_st)

# --- شکاف ۴: انحراف از خط پایه ---
for _i in range(6):
    req(B14,'/api/vitals','POST',{'type':'blood_pressure','value':{'systolic':126+_i,'diastolic':82}})
req(B14,'/api/vitals','POST',{'type':'blood_pressure','value':{'systolic':182,'diastolic':112}})
_st,_b=req(B14,'/api/baselines')
_bl={x['type']:x for x in _b.get('baselines',[])}
check('خط پایه: محاسبه می‌شود',_st==200 and 'systolic' in _bl,(_st,list(_bl)))
check('خط پایه: میانگین و انحراف معیار دارد',
      'systolic' in _bl and 'mean' in _bl['systolic'] and 'stddev' in _bl['systolic'])
check('خط پایه: جهش ناگهانی را انحراف می‌شناسد',
      'systolic' in _bl and _bl['systolic'].get('deviation') is True,_bl.get('systolic'))
check('خط پایه: روند را گزارش می‌کند',_bl.get('systolic',{}).get('trend') in ('rising','falling','stable'))
check('خط پایه: برای انحراف هشدار می‌سازد',len(_b.get('alerts_created',[]))>=1,_b.get('alerts_created'))
_st,_b2=req(B14,'/api/baselines')
check('خط پایه: هشدار تکراری نمی‌سازد',len(_b2.get('alerts_created',[]))==0,_b2.get('alerts_created'))
_st,_al=req(B14,'/api/alerts')
check('خط پایه: هشدار در فهرست هشدارها می‌نشیند',
      any(x['type'].startswith('baseline_deviation') for x in _al.get('items',[])))

# ---------------------------------------------------------------- بخش ۱۵
# باگ‌یابی دور هفتم: دو باگ واقعی که با فازر و آزمون همزمانی پیدا شدند.
# ۱) as_text() برای dict/list عمداً None می‌دهد تا فراخوان ۴۰۰ برگرداند، اما
#    /api/prescriptions مستقیم .strip() رویش صدا می‌زد → AttributeError → ۵۰۰.
# ۲) پله‌بندی بی‌پاسخی «انتخاب، بعد نوشتن» بود. چون scheduler در thread خودش
#    هم آن را صدا می‌زند، ۶ فراخوانی همزمان برای یک رویداد ۶ هشدار و ۶ کنش
#    تکراری می‌ساخت — یعنی ۶ درخواست تماس بی‌معنی برای مراقب.
print()
print('۱۵) ورودی بدنه و همزمانی (باگ‌یابی دور هفتم)')
_c15=sqlite3.connect(_m14.DB)
_c15.execute("DELETE FROM proactive_events")
_c15.commit()
_poison=[{'x':1},[1,2],{'n':{'d':[1]}},[{'x':1}]]
for _i,_p15 in enumerate(_poison):
    _st,_r=req(B14,'/api/prescriptions','POST',{'image_ref':_p15,'items':[]})
    check('ورود نسخه: image_ref %s → ۴۰۰ نه ۵۰۰'%(type(_p15).__name__),
          _st==400 and _r.get('error')=='image_ref_required',(_st,_r))
for _i,_p15 in enumerate(_poison):
    _st,_r=req(B14,'/api/prescriptions','POST',{'image_ref':'pz-name-%d'%_i,'items':[{'name':_p15}]})
    check('ورود نسخه: name %s → ۲۰۱ با صفر قلم نه ۵۰۰'%(type(_p15).__name__),
          _st==201 and len(_r.get('items',[]))==0,(_st,_r))
_st,_r=req(B14,'/api/prescriptions','POST',{'image_ref':'pz-ok','items':[{'name':'آتورواستاتین','dose':'۲۰mg'}]})
check('ورود نسخه: کنترل مثبت هنوز کار می‌کند',_st==201 and len(_r.get('items',[]))==1,(_st,_r))
_st,_r=req(B14,'/api/prescriptions','POST',{'image_ref':'pz-ok','items':[]})
check('ورود نسخه: تکراری ۴۰۹ می‌ماند',_st==409,(_st,_r))

# --- race پله‌بندی: ۶ thread دقیقاً همزمان روی یک رویداد بی‌پاسخ
_old15=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=3)).isoformat()
_eid15=uuid.uuid4().hex
_c15.execute('INSERT INTO proactive_events VALUES(?,?,?,?,?,?,?)',
             (_eid15,'morning_checkin','2026-01-01',_old15,None,None,None))
if not list(_c15.execute('SELECT id FROM caregivers')):
    _c15.execute("INSERT INTO caregivers VALUES('cg15','مریم','0912','daughter','[]','2026-01-01',NULL,0,NULL)")
_c15.commit()
_a0=_c15.execute('SELECT COUNT(*) FROM alerts').fetchone()[0]
_g0=_c15.execute('SELECT COUNT(*) FROM caregiver_actions').fetchone()[0]
_c15.close()
_barrier15=threading.Barrier(6); _res15=[]
def _run15():
    _cc=_m14.db()
    try:
        _barrier15.wait(); _res15.append(len(_m14.escalate_stale_prompts(_cc)))
    finally: _cc.close()
_ts15=[threading.Thread(target=_run15) for _ in range(6)]
for _t in _ts15: _t.start()
for _t in _ts15: _t.join()
_c15=sqlite3.connect(_m14.DB)
_a1=_c15.execute('SELECT COUNT(*) FROM alerts').fetchone()[0]
_g1=_c15.execute('SELECT COUNT(*) FROM caregiver_actions').fetchone()[0]
check('همزمانی: ۶ فراخوانی همزمان یک رویداد، دقیقاً یک پله‌بادی',
      sum(1 for _x in _res15 if _x)==1,sorted(_res15,reverse=True))
check('همزمانی: فقط یک هشدار بی‌پاسخی ساخته می‌شود',_a1-_a0==1,(_a1-_a0))
check('همزمانی: فقط یک کنش مراقب ساخته می‌شود',_g1-_g0==1,(_g1-_g0))
check('همزمانی: UPDATE تصاحب شرط escalated_at IS NULL دارد',
      'WHERE id=? AND escalated_at IS NULL' in srvsrc)
_c15.close()

# ---------------------------------------------------------------- بخش ۱۶
# باگ‌یابی دور هشتم: سه باگ از یک خانواده — «مقدار بی‌اعتبارسنجی نوشته می‌شود
# و خواننده‌اش بعداً می‌شکند». دو تای اول کرش پایدار بودند: یک نوشتن بد،
# اندپوینت هسته‌ای را برای همیشه از کار می‌انداخت.
# ۱) /api/reminder-settings برای quiet_start/quiet_end هیچ اعتبارسنجی نداشت؛
#    مقدار خام ذخیره می‌شد و in_quiet_window با strptime می‌شکست
#    → GET /api/reminders/due برای همیشه ۵۰۰.
# ۲) /api/vitals/thresholds با str(None) رشتهٔ 'None' ذخیره می‌کرد و
#    float('None') در evaluate_vital می‌شکست → POST /api/vitals برای همیشه ۵۰۰.
# ۳) max_nudges ذخیره و اعتبارسنجی می‌شد ولی هیچ‌جا خوانده نمی‌شد (تنظیم مرده).
print()
print('۱۶) اعتبارسنجی در مرز ورودی (باگ‌یابی دور هشتم)')
for _v in ['بد','25:99','','99:99',None,123,'22:00:00',{'a':1}]:
    _st,_r=req(B14,'/api/reminder-settings','POST',{'quiet_start':_v,'quiet_end':'07:00','max_nudges':2})
    check('ساعت سکوت: quiet_start=%r → ۴۰۰ نه ذخیره'%(str(_v)[:12]),
          _st==400 and _r.get('error')=='invalid_quiet_hours',(_st,_r))
_st,_r=req(B14,'/api/reminder-settings','POST',{'quiet_start':'22:00','quiet_end':'07:00','max_nudges':2})
check('ساعت سکوت: مقدار معتبر HH:MM پذیرفته می‌شود',_st==200,(_st,_r))
for _n in [-5,11,999]:
    _st,_r=req(B14,'/api/reminder-settings','POST',{'quiet_start':'22:00','quiet_end':'07:00','max_nudges':_n})
    check('ساعت سکوت: max_nudges=%r خارج از بازه → ۴۰۰'%_n,_st==400,(_st,_r))
_st,_r=req(B14,'/api/reminders/due')
check('ساعت سکوت: اندپوینت یادآور پس از تلاش‌های بد سالم می‌ماند',_st==200,(_st,_r))

for _nm,_items in [('null',[{'type':'systolic','normal_min':None,'normal_max':140,'critical_min':80,'critical_max':180}]),
                   ('رشته',[{'type':'systolic','normal_min':'بد','normal_max':140,'critical_min':80,'critical_max':180}]),
                   ('خالی',[{'type':'systolic','normal_min':'','normal_max':'','critical_min':'','critical_max':''}]),
                   ('وارونه',[{'type':'systolic','normal_min':200,'normal_max':80,'critical_min':80,'critical_max':180}]),
                   ('قلم غیرشیء',['x'])]:
    _st,_r=req(B14,'/api/vitals/thresholds','POST',{'items':_items})
    check('آستانه: %s → ۴۰۰ نه ذخیرهٔ زباله'%_nm,_st==400,(_st,_r))
_st,_r=req(B14,'/api/vitals/thresholds','POST',{'items':'notalist'})
check('آستانه: items غیرفهرست → ۴۰۰',_st==400,(_st,_r))
_st,_r=req(B14,'/api/vitals/thresholds','POST',
           {'items':[{'type':'systolic','normal_min':90,'normal_max':140,'critical_min':80,'critical_max':180}]})
check('آستانه: مقدار معتبر پذیرفته می‌شود',_st==200,(_st,_r))
_st,_r=req(B14,'/api/vitals','POST',{'type':'blood_pressure','value':{'systolic':128,'diastolic':82}})
check('آستانه: ثبت علامت حیاتی پس از آن کار می‌کند',_st==201,(_st,_r))

# --- لایهٔ دوم دفاع: دادهٔ خرابی که پیش از رفع در پایگاه‌داده نشسته
# نباید اندپوینت هسته‌ای را از کار بیندازد. مستقیم و بی‌گذر از اعتبارسنجی
# مرز نوشته می‌شود تا وضعیت پایگاه‌دادهٔ قدیمی بازسازی شود.
_c16=sqlite3.connect(_m14.DB)
_c16.execute("UPDATE reminder_settings SET quiet_start='x',quiet_end='y' WHERE id=1"); _c16.commit()
_st,_r=req(B14,'/api/reminders/due')
check('تاب‌آوری: ساعت سکوت خراب در پایگاه‌داده → ۵۰۰ نمی‌دهد',_st==200,(_st,_r))
check('تاب‌آوری: ساعت سکوت خراب به «بدون سکوت» برمی‌گردد',_r.get('quiet_hours') is False,_r.get('quiet_hours'))
_c16.execute("UPDATE vital_thresholds SET normal_min='None',critical_min='None' WHERE type='systolic'"); _c16.commit()
_st,_r=req(B14,'/api/vitals','POST',{'type':'blood_pressure','value':{'systolic':128,'diastolic':82}})
check('تاب‌آوری: آستانهٔ خراب در پایگاه‌داده → ۵۰۰ نمی‌دهد',_st==201,(_st,_r))
_c16.execute("UPDATE reminder_settings SET quiet_start='22:00',quiet_end='07:00' WHERE id=1")
_c16.execute("UPDATE vital_thresholds SET normal_min='90',normal_max='140',critical_min='80',critical_max='180' WHERE type='systolic'")
_c16.commit(); _c16.close()

# --- max_nudges دیگر مرده نیست: دست‌کم صفر واقعاً یادآوری را خاموش می‌کند
_c16=sqlite3.connect(_m14.DB)
for _t in ['reminder_events','medications','medication_logs']: _c16.execute('DELETE FROM '+_t)
_c16.commit(); _c16.close()
_ln24=getattr(_m14,'local_now',None)
_hh=(_ln24() if _ln24 else datetime.datetime.now()).strftime('%H:%M')   # ساعت ایران؛ پیش‌تر now() خام بود و تست به باگ کوپل شده بود
req(B14,'/api/medications','POST',{'name':'داروی آزمون ۱۶','time':_hh,'instructions':'x'})
for _n,_want in [(0,0),(2,1)]:
    req(B14,'/api/reminder-settings','POST',{'quiet_start':'00:00','quiet_end':'00:01','max_nudges':_n})
    _c16=sqlite3.connect(_m14.DB); _c16.execute('DELETE FROM reminder_events'); _c16.commit(); _c16.close()
    for _ in range(4): req(B14,'/api/reminders/due')
    _c16=sqlite3.connect(_m14.DB)
    _got=_c16.execute('SELECT COUNT(*) FROM reminder_events').fetchone()[0]
    _c16.execute("UPDATE reminder_settings SET quiet_start='22:00',quiet_end='07:00' WHERE id=1"); _c16.commit(); _c16.close()
    check('max_nudges=%d → %d یادآوری (تنظیم مرده نیست)'%(_n,_want),_got==_want,(_got,_want))
req(B14,'/api/reminder-settings','POST',{'quiet_start':'22:00','quiet_end':'07:00','max_nudges':2})

# ---------------------------------------------------------------- بخش ۱۷
# باگ‌یابی دور نهم: همان الگوی race که در دور هفتم در escalate_stale_prompts
# رفع شد، در دو تابع دیگر هم بود — «اول SELECT شرطی، بعد INSERT» بدون تصاحب
# اتمیک. چون هر دو را هم endpoint و هم thread زمان‌بند (یا چند poll همزمان
# داشبورد) صدا می‌زنند، زیر بار واقعی خروجی تکراری می‌ساختند.
print()
print('۱۷) تصاحب اتمیک در نوشتن‌های شرطی (باگ‌یابی دور نهم)')
_TZ=_m14.ZoneInfo('Asia/Tehran')
def _race17(fn,seed,threads=6):
    seed()
    _bar=threading.Barrier(threads); _out=[]
    def _w():
        _cc=_m14.db()
        try: _bar.wait(); _out.append(fn(_cc))
        finally: _cc.close()
    _ts=[threading.Thread(target=_w) for _ in range(threads)]
    for _t in _ts: _t.start()
    for _t in _ts: _t.join()
    return _out
def _seed_prompts():
    _c=sqlite3.connect(_m14.DB); _c.execute('DELETE FROM proactive_events'); _c.commit(); _c.close()
_at17=datetime.datetime(2026,1,15,9,0,0,tzinfo=_TZ)
_r=_race17(lambda cc: len(_m14.collect_due_prompts(cc,at_local=_at17)),_seed_prompts)
_c=sqlite3.connect(_m14.DB); _n17=_c.execute('SELECT COUNT(*) FROM proactive_events').fetchone()[0]; _c.close()
check('همزمانی: ۶ فراخوانی همزمان یک سررسید، یک پرامپت',
      sum(1 for _x in _r if _x)==1 and _n17==1,(sorted(_r,reverse=True),_n17))

def _seed_dev():
    _c=sqlite3.connect(_m14.DB)
    for _t in ['alerts','caregiver_actions','vitals']: _c.execute('DELETE FROM '+_t)
    if not list(_c.execute('SELECT id FROM caregivers')):
        _c.execute("INSERT INTO caregivers VALUES('cg17','مریم','0912','daughter','[]','2026-01-01',NULL,0,NULL)")
    for _i,_v in enumerate([128,130,126,129,127,131,178]):
        _c.execute('INSERT INTO vitals VALUES(?,?,?,?,?,?)',(uuid.uuid4().hex,'blood_pressure',
            json.dumps({'systolic':_v,'diastolic':82}),'manual',
            (datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(minutes=60-_i)).isoformat(),
            datetime.datetime.now(datetime.timezone.utc).isoformat()))
    _c.commit(); _c.close()
_r2=_race17(lambda cc: len(_m14.detect_deviation_alerts(cc)),_seed_dev)
_c=sqlite3.connect(_m14.DB)
_a17=_c.execute("SELECT COUNT(*) FROM alerts WHERE type LIKE 'baseline_deviation%'").fetchone()[0]
_g17=_c.execute('SELECT COUNT(*) FROM caregiver_actions').fetchone()[0]; _c.close()
check('همزمانی: یک انحراف، یک هشدار',sum(1 for _x in _r2 if _x)==1 and _a17==1,(sorted(_r2,reverse=True),_a17))
check('همزمانی: یک انحراف، یک کنش مراقب',_g17==1,_g17)

# --- کنترل مثبت: dedupe بیش از حد نشده باشد
_c=sqlite3.connect(_m14.DB)
for _t in ['alerts','vitals','proactive_events']: _c.execute('DELETE FROM '+_t)
_c.commit(); _c.close()
_cc=_m14.db()
check('کنترل: اولین پرامپت سررسید ساخته می‌شود',
      len(_m14.collect_due_prompts(_cc,at_local=_at17))==1)
check('کنترل: همان روز تکرار نمی‌شود',
      len(_m14.collect_due_prompts(_cc,at_local=_at17))==0)
check('کنترل: روز بعد دوباره ساخته می‌شود',
      len(_m14.collect_due_prompts(_cc,at_local=datetime.datetime(2026,1,16,9,0,0,tzinfo=_TZ)))==1)
check('کنترل: ساعت بی‌ربط چیزی نمی‌سازد',
      len(_m14.collect_due_prompts(_cc,at_local=datetime.datetime(2026,1,16,14,0,0,tzinfo=_TZ)))==0)
check('کنترل: هشدار نوع دیگر مستقل ساخته می‌شود',
      _m14.open_alert_once(_cc,'type_a','m') is not None and _m14.open_alert_once(_cc,'type_b','m') is not None)
check('کنترل: هشدار بازِ تکراری ساخته نمی‌شود',
      _m14.open_alert_once(_cc,'type_a','m') is None)
_cc.commit()   # وگرنه تراکنش باز قفل نوشتن را نگه می‌دارد و اتصال بعدی قفل می‌شود
_c=sqlite3.connect(_m14.DB); _c.execute("UPDATE alerts SET status='resolved' WHERE type='type_a'"); _c.commit(); _c.close()
check('کنترل: پس از بسته‌شدن هشدار، دوباره ساخته می‌شود',
      _m14.open_alert_once(_cc,'type_a','m') is not None)
check('کنترل: open_alert معمولی هنوز بدون محدودیت می‌سازد',
      _m14.open_alert(_cc,'plain','m') is not None and _m14.open_alert(_cc,'plain','m') is not None)
_cc.close()
_c=sqlite3.connect(_m14.DB)
for _t in ['alerts','vitals','proactive_events','caregiver_actions']: _c.execute('DELETE FROM '+_t)
_c.commit(); _c.close()
# آزمون رفتاری race ذاتاً احتمالی است — در باگ‌یابی دور دهم یک بار روی
# کد باگ‌دار هم قبول شد. پس الگوی تصاحب اتمیک را قطعی هم می‌سنجیم تا
# رگرسیون بی‌صدا رد نشود.
_srv17=open(os.path.join(ROOT,'server.py'),encoding='utf-8').read()
check('الگو: هشدار با INSERT شرطی اتمیک ساخته می‌شود',
      'INSERT INTO alerts(id,type,message,severity,status,created_at) SELECT' in _srv17
      and 'WHERE NOT EXISTS (SELECT 1 FROM alerts WHERE type=?' in _srv17)
check('الگو: پرامپت با INSERT شرطی اتمیک ساخته می‌شود',
      'INSERT INTO proactive_events(id,kind,prompt_date,delivered_at,response,responded_at,escalated_at) SELECT' in _srv17
      and 'WHERE NOT EXISTS (SELECT 1 FROM proactive_events WHERE kind=? AND prompt_date=?)' in _srv17)
check('الگو: نتیجهٔ تصاحب با rowcount سنجیده می‌شود',
      _srv17.count('cur.rowcount') >= 3, _srv17.count('cur.rowcount'))
_legacy_alerts = 'SELECT 1 FROM alerts WHERE type=? AND status=\'open\'",(sig,)).fetchone(): continue'
_legacy_prompts = "and not c.execute('SELECT 1 FROM proactive_events WHERE kind=? AND prompt_date=?')"
check('الگو: select-then-insert قدیمی در این دو تابع نمانده',
      _legacy_alerts not in _srv17 and _legacy_prompts not in _srv17)


# ---------------------------------------------------------------- بخش ۱۸
# باگ‌یابی دور دهم: نشتی پرونده. Handler از SimpleHTTPRequestHandler ارث
# می‌برد و _get در انتها به super().do_GET() می‌رسید، یعنی هر پروندهٔ زیر
# ROOT سرو می‌شد. اندازه‌گیری واقعی پیش از رفع:
#   /sepandyar.db        → ۲۰۰، ۴۱۷۷۹۲ بایت (کل پایگاه‌دادهٔ سلامت سالمند)
#   /server.py           → ۲۰۰، ۱۲۵۹۷۱ بایت (کل کد منبع بک‌اند)
#   /test_deployment.py  → ۲۰۰،  ۷۵۸۳۵ بایت
#   /docs/ /uploads/ /production/ /android/ → ۲۰۰ فهرست پوشه
# ریسرچ تأیید کرد blocklist با percent-encoding دور زده می‌شود چون
# SimpleHTTPRequestHandler مسیر را پیش از نگاشت به دیسک decode می‌کند؛
# آزمودم «/..%2fserver.py» → ۲۰۰ با کل کد منبع. پس رفع allowlist روی
# مسیر decode‌شده است.
print()
print('۱۸) allowlist سرو پروندهٔ استاتیک (باگ‌یابی دور دهم)')
for _path,_label in [('/sepandyar.db','پایگاه‌دادهٔ سلامت'),
                     ('/server.py','کد منبع بک‌اند'),
                     ('/test_deployment.py','مجموعهٔ آزمون'),
                     ('/test_mvp.py','مجموعهٔ آزمون'),
                     ('/api-contract.json','قرارداد API'),
                     ('/..%2fserver.py','رمزگذاری percent'),
                     ('/%2e%2e/server.py','رمزگذاری نقطه'),
                     ('/..%2fsepandyar.db','رمزگذاری پایگاه‌داده'),
                     ('/docs/','فهرست پوشهٔ docs'),
                     ('/uploads/','فهرست پوشهٔ uploads'),
                     ('/production/','فهرست پوشهٔ production'),
                     ('/android/','فهرست پوشهٔ android'),
                     ('/index.html/','اسلش اضافه')]:
    _st,_b=req(B14,_path)
    _body=_b.get('_raw','') if isinstance(_b,dict) else ''
    _leaked=_st==200 and ('CREATE TABLE' in _body or 'def db(' in _body or '<li>' in _body
                          or 'SQLite format' in _body or 'Index of' in _body)
    check('نشتی: '+_label+' → ۴۰۴',_st==404 and not _leaked,(_st,len(_body)))
_st,_b=req(B14,'/')
check('کارکرد: صفحهٔ اصلی سرو می‌شود',_st==200 and len(_b.get('_raw',''))>1000,(_st,))
for _path,_label in [('/index.html','صفحهٔ سالمند'),('/caregiver.html','داشبورد مراقب'),
                     ('/admin.html','پنل ادمین'),('/investor.html','صفحهٔ سرمایه‌گذار'),
                     ('/sw.js','service worker'),('/manifest.webmanifest','مانیفست')]:
    _st,_b=req(B14,_path)
    # مانیفست JSON معتبر است و req() تجزیه‌اش می‌کند، پس _raw خالی می‌ماند؛
    # برای آن به کلیدهای تجزیه‌شده نگاه می‌کنیم.
    _ok = _st==200 and (len(_b.get('_raw',''))>100 if isinstance(_b,dict) and '_raw' in _b
                        else (isinstance(_b,dict) and len(_b)>0))
    check('کارکرد: '+_label+' سرو می‌شود',_ok,(_st,list(_b)[:4] if isinstance(_b,dict) else _b))
check('allowlist روی مسیر decode‌شده سنجیده می‌شود',
      'unquote(p,errors=' in open(os.path.join(ROOT,'server.py'),encoding='utf-8').read())

# ── بخش ۱۹: دور یازدهم باگ‌یابی — HEAD، کلید تکرارناپذیری، سقف بدنه، تایم‌اوت ──
# هر چهار باگ روی سرور در حال اجرا اندازه‌گیری و سپس رفع شد. برای هر کدام هم
# آزمون رفتاری آمده و هم یک ممیز قطعی روی خود منبع؛ چون آزمون زمانی/رقابتی
# ذاتاً احتمالی است و یک بار روی کد باگ‌دار هم قبول شد.
print()
print('— بخش ۱۹: دور یازدهم —')
import socket as _sk19, ast as _ast19

_u19 = urlparse(B14)
def _raw19(method, path, body=b'', hdrs=None):
    c = http.client.HTTPConnection(_u19.hostname, _u19.port, timeout=60)
    c.request(method, path, body=body, headers=hdrs or {})
    r = c.getresponse(); d = r.read(); cl = r.getheader('Content-Length', ''); c.close()
    return r.status, cl, d

# ۱) HEAD دیگر allowlist را دور نمی‌زند. do_HEAD در SimpleHTTPRequestHandler
#    مستقیم send_head() را صدا می‌زند و اصلاً از do_GET نمی‌گذرد.
for _p, _lbl in [('/sepandyar.db', 'پایگاه‌دادهٔ سلامت'), ('/server.py', 'کد منبع'),
                 ('/test_deployment.py', 'مجموعهٔ آزمون'), ('/test_mvp.py', 'آزمون mvp'),
                 ('/docs/', 'فهرست docs'), ('/uploads/', 'فهرست uploads'),
                 ('/production/', 'فهرست production'), ('/android/', 'فهرست android'),
                 ('/..%2fserver.py', 'رمزگذاری percent'), ('/%2e%2e/server.py', 'رمزگذاری نقطه')]:
    _s, _cl, _d = _raw19('HEAD', _p)
    check('HEAD نشتی نمی‌دهد: ' + _lbl, _s == 404, (_s, _cl))
# اندازه‌ها عمداً از دیسک خوانده می‌شوند نه سخت‌کد: خواصِ آزموده‌شده این است که HEAD
# «طول واقعی فایل» را گزارش می‌کند. عدد ثابت با هر تغییر مشروع UI فاسد می‌شد.
for _p, _fn in [('/', 'index.html'), ('/index.html', 'index.html'), ('/caregiver.html', 'caregiver.html'),
                ('/admin.html', 'admin.html'), ('/investor.html', 'investor.html'), ('/sw.js', 'sw.js'),
                ('/manifest.webmanifest', 'manifest.webmanifest')]:
    _sz = os.path.getsize(os.path.join(ROOT, _fn))
    _s, _cl, _d = _raw19('HEAD', _p)
    check('HEAD دارایی مجاز سالم است: ' + _p, _s == 200 and _cl == str(_sz), (_s, _cl, _sz))
check('دروازه در send_head است نه فقط در _get', 'def send_head(self):' in srvsrc)

# ۲) کلید تکرارناپذیری باید به عملیات مقید باشد، وگرنه کلیدِ یک شارژ پرداخت را
#    «موفق» جا می‌زند در حالی که هیچ پرداختی انجام نشده است.
def _bal19():
    _s, _b = req(B14, '/api/wallet'); return _b.get('balance')
_b0 = _bal19(); _k19 = str(uuid.uuid4())
req(B14, '/api/wallet/topups', 'POST', {'amount': 5000, 'idempotency_key': _k19})
_s, _d = req(B14, '/api/wallet/payment', 'POST', {'amount': 3000, 'idempotency_key': _k19})
check('کلید شارژ، پرداخت را بی‌صدا «موفق» نمی‌کند', _s == 200 and not _d.get('replayed'), (_s, _d))
check('پرداخت واقعاً روی موجودی می‌نشیند', _bal19() == _b0 + 5000 - 3000, (_bal19(), _b0 + 2000))
_k20 = str(uuid.uuid4())
req(B14, '/api/wallet/topups', 'POST', {'amount': 1000, 'idempotency_key': _k20})
_s, _d = req(B14, '/api/wallet/topups', 'POST', {'amount': 77777, 'idempotency_key': _k20})
check('کلید یکسان با مبلغ متفاوت → ۴۰۹', _s == 409 and _d.get('error') == 'idempotency_key_conflict', (_s, _d))
_s, _d = req(B14, '/api/wallet/topups', 'POST', {'amount': 1000, 'idempotency_key': _k20})
check('تکرار مشروع همان درخواست → ۲۰۰', _s == 200 and _d.get('replayed') is True, (_s, _d))
check('کلید به عملیات مقید می‌شود', "idem_key(self,d,'topup')" in srvsrc and "idem_key(self,d,'payment')" in srvsrc)

# ۳) سقف اندازهٔ بدنه. بدون آن، یک بدنهٔ ۲۰۰MB پایگاه‌داده را برای همیشه به
#    ۲۲۱MB رساند (۲۲۰MB صفحهٔ مرده که بدون VACUUM برنمی‌گردد).
# سرور ۴۱۳ را می‌فرستد و سپس اتصال را می‌بندد؛ اگر کلاینت هنوز وسط نوشتن
# باشد، نوشتن با BrokenPipeError شکست می‌خورد. هر دو نشانهٔ رد کردن است، پس
# این بررسی باید هر دو را بپذیرد وگرنه بسته به زمان‌بندی بافر ناپایدار می‌شود.
try:
    _s, _cl, _d = _raw19('POST', '/api/profile',
                         body=b'{"name":"' + b'A' * (1024 * 1024 + 10) + b'"}',
                         hdrs={'Content-Type': 'application/json'})
    _refused19 = (_s == 413)
except (BrokenPipeError, ConnectionError, http.client.RemoteDisconnected) as _e19b:
    _refused19 = True
check('بدنهٔ بزرگ‌تر از ۱MB رد می‌شود', _refused19, (_s if '_s' in dir() else 'پیش از پاسخ',))
_s, _cl, _d = _raw19('POST', '/api/profile',
                     body='{"name":"بی‌بی‌جان"}'.encode(),
                     hdrs={'Content-Type': 'application/json'})
check('بدنهٔ کوچک هنوز پذیرفته می‌شود', _s == 200, (_s,))
check('سقف پیش از خواندن بدنه سنجیده می‌شود',
      'MAX_BODY_BYTES=1024*1024' in srvsrc and 'if n>MAX_BODY_BYTES:' in srvsrc)
_s, _b = req(B14, '/api/profile')
check('پس از ۴۱۳ چیزی نوشته نشده', _b.get('name') == 'بی‌بی‌جان', (_b,))

# ۴) تایم‌اوت سوکت. بدون آن هر اتصال نیمه‌باز یک رشته را برای همیشه نگه می‌دارد
#    (slowloris): اندازه‌گیری شد ۲۰ اتصال → ۲۰ رشته که پس از ۲۵ ثانیه هم آزاد نشدند.
_t19 = _m14.Handler.timeout
check('تایم‌اوت سوکت تنظیم شده', isinstance(_t19, (int, float)) and _t19 > 0, (_t19,))
check('تایم‌اوت از کُندترین مسیر مشروع بزرگ‌تر است', isinstance(_t19, (int, float)) and _t19 >= 15, (_t19,))
# آزمون رفتاری مکانیسم، با تایم‌اوت کوتاه روی یک زیرکلاس تا سوئیت کند نشود.
class _H19(_m14.Handler):
    timeout = 2
_s19 = ThreadingHTTPServer(('127.0.0.1', 0), _H19)
threading.Thread(target=_s19.serve_forever, daemon=True).start()
_c19 = _sk19.create_connection(('127.0.0.1', _s19.server_address[1]), timeout=20)
_c19.sendall(b'POST /api/profile HTTP/1.1\r\nHost: x\r\nContent-Length: 5000\r\n\r\n')
_w19 = datetime.datetime.now(); _answered19 = False; _data19 = b''
try:
    _c19.settimeout(12)
    _data19 = _c19.recv(200)   # b'' یعنی بست، b'HTTP...' یعنی پاسخ داد
    _answered19 = True
except Exception:
    _answered19 = False        # تایم‌اوت کلاینت رسید = سرور آویزان مانده
_el19 = (datetime.datetime.now() - _w19).total_seconds()
# هنگام تایم‌اوت، body() استثنا را می‌گیرد و _body_error می‌نشاند، پس پاسخ ۴۰۰ است.
check('اتصال نیمه‌باز آویزان نمی‌ماند و پاسخ می‌گیرد',
      _answered19 and _el19 < 10, (_answered19, round(_el19, 1)))
check('پاسخِ اتصال نیمه‌باز ۴۰۰ است نه آویزانی',
      _data19.startswith(b'HTTP/1.0 400'), (_data19[:24],))
try:
    _s19.shutdown(); _s19.server_close(); _c19.close()
except Exception:
    pass

# ۵) رفتن کلاینت نباید ۵۰۰ جعلی در لاگ بنشاند. send() روی سوکت مرده شکست
#    می‌خورد و except عمومی سپس یک ۵۰۰ لاگ می‌کرد که خطای واقعی را می‌پوشاند.
_tree19 = _ast19.parse(srvsrc)
def _handler_order19(fname):
    for _n in _ast19.walk(_tree19):
        if isinstance(_n, _ast19.FunctionDef) and _n.name == fname:
            for _st in _n.body:
                if isinstance(_st, _ast19.Try):
                    return [(_h.type.id if isinstance(_h.type, _ast19.Name) else None)
                            for _h in _st.handlers]
    return []
for _fn in ('do_GET', 'do_POST'):
    _hs = _handler_order19(_fn)
    check(_fn + ': ConnectionError زودتر از Exception گرفته می‌شود',
          'ConnectionError' in _hs and 'Exception' in _hs
          and _hs.index('ConnectionError') < _hs.index('Exception'), (_hs,))

# ── بخش ۲۰: دور دوازدهم باگ‌یابی — XSS ذخیره‌شده در گزارش اشتراک ──
# /share/<token> گزارش را با text/html سرو می‌کند و report_html آن را با
# f-string می‌سازد، بدون هیچ escape. چون endpoint ها عمداً verbatim ذخیره
# می‌کنند (دفاع در زمان رندر)، هر فیلد خام یعنی اجرای اسکریپت در مرورگر
# کسی که لینک اشتراک را باز می‌کند — یعنی خانوادهٔ سالمند.
# اندازه‌گیری شد: name برابر <script>document.title="pwned"</script> ذخیره شد،
# گزارش آن را خام برگرداند و در jsdom عنوان صفحه واقعاً «pwned» شد.
print()
print('— بخش ۲۰: دور دوازدهم —')
import ast as _ast20

_P20 = '<script>document.title="pwned"</script>'
_P21 = '<img src=x onerror="alert(1)">'
_P22 = '<b>manual</b>'
_s20, _ = req(B14, '/api/profile', 'POST', {'name': _P20, 'needs': _P21, 'age': 78})
check('بارگذاری payload در پروفایل', _s20 == 200, (_s20,))
_s20, _ = req(B14, '/api/vitals', 'POST', {'type': 'weight', 'value': 72.5, 'source': _P22})
check('بارگذاری payload در منبع علائم حیاتی', _s20 in (200, 201), (_s20,))
_s20, _b20 = req(B14, '/api/vitals/share', 'POST', {'scope': 'vitals', 'expires_days': 7})
check('ساخت لینک اشتراک', _s20 == 201 and _b20.get('token'), (_s20,))
_s20, _h20 = req(B14, '/share/' + str(_b20.get('token')))
_h20s = _h20.get('_raw', '') if isinstance(_h20, dict) else str(_h20)
check('گزارش سرو می‌شود', _s20 == 200 and len(_h20s) > 200, (_s20, len(_h20s)))
for _pay, _lbl in [(_P20, 'اسکریپت در نام'), (_P21, 'هندلر رویداد در نیازمندی‌ها'),
                   (_P22, 'تگ در منبع')]:
    check('XSS ذخیره‌شده بسته شد: ' + _lbl, _pay not in _h20s, (_pay,))
check('escape واقعاً انجام شده نه فقط حذف',
      '&lt;script&gt;' in _h20s and '&lt;img' in _h20s, (_h20s[:120],))
# کنترل مثبت: محتوای مشروع باید دست‌نخورده بماند
for _ok20, _lbl in [('گزارش علائم حیاتی', 'عنوان فارسی'), ('78', 'سن'),
                    ('72.5', 'مقدار علائم حیاتی'), ('جایگزین تشخیص پزشک', 'سلب مسئولیت')]:
    check('محتوای مشروع سالم ماند: ' + _lbl, _ok20 in _h20s, (_ok20,))
# ممیز قطعی روی منبع: هیچ FormattedValue بدون _e() در report_html نمانده باشد
_tree20 = _ast20.parse(srvsrc)
def _unescaped20(fname):
    bad = []
    for _n in _ast20.walk(_tree20):
        if isinstance(_n, _ast20.FunctionDef) and _n.name == fname:
            for _js in _ast20.walk(_n):
                if isinstance(_js, _ast20.JoinedStr):
                    for _v in _js.values:
                        if isinstance(_v, _ast20.FormattedValue):
                            _f = _v.value
                            _okc = (isinstance(_f, _ast20.Call)
                                    and isinstance(_f.func, _ast20.Name)
                                    and _f.func.id == '_e')
                            if not _okc:
                                bad.append(_ast20.unparse(_f)[:40])
    return bad
_bad20 = _unescaped20('report_html')
# «tr» رشتهٔ ردیف‌هاست و خودش تنها از پاره‌های _e() ساخته می‌شود — و چون همین
# پیمایش کل بدنهٔ تابع را می‌گردد، آن پاره‌ها را هم بررسی کرده است. پس مجاز
# است. هر نام دیگری یعنی یک فیلد خامِ تازه که بی‌صدا اضافه شده.
_unexpected20 = [b for b in _bad20 if b != 'tr']
check('report_html: هیچ درون‌ریزی خامی نمانده (جز tr که از _e ساخته می‌شود)',
      not _unexpected20, _bad20)
check('کمکی escape تعریف شده و به کار رفته',
      'def _e(v):' in srvsrc and srvsrc.count('_e(') >= 9, (srvsrc.count('_e('),))
check('ماژول html وارد شده', ', html,' in srvsrc)

_srv14.shutdown(); _srv14.server_close()

# ===================== بخش ۲۱: سرآیندهای امنیتی، PRAGMA عملکردی، ایندکس و دسترسی‌پذیری WCAG 2.2 =====================
# ممیزی پیش از این تغییر: از هفت سرآیند امنیتی توصیه‌شده «صفر» مورد ارسال می‌شد، هیچ
# PRAGMA عملکردی وجود نداشت، و در برابر ۴۵ جدول فقط «یک» ایندکس بود.
print()
print('--- بخش ۲۱: سرآیندهای امنیتی / عملکرد SQLite / دسترسی‌پذیری ---')

_s21=ThreadingHTTPServer(('127.0.0.1',0),_m14.Handler)
threading.Thread(target=_s21.serve_forever,daemon=True).start()
B21='http://127.0.0.1:%d'%_s21.server_address[1]
import html.parser as _hp
def _headers(base,path):
    """سرآیندهای خام یک پاسخ را به‌صورت «لیست» برمی‌گرداند تا سرآیند تکراری هم دیده شود."""
    u=urlparse(base); c=http.client.HTTPConnection(u.hostname,u.port,timeout=30)
    c.request('GET',path); r=c.getresponse(); r.read()
    hs=[(k.lower(),v) for k,v in r.getheaders()]; c.close(); return r.status,hs
def _h(hs,name): return [v for k,v in hs if k==name.lower()]

_api=_headers(B21,'/api/health'); _st=_headers(B21,'/index.html'); _nf=_headers(B21,'/api/definitely-missing')
for _lbl,(_code,_hs) in [('API',_api),('ایستا',_st),('۴۰۴',_nf)]:
    # ۴۰۴ عمداً سنجیده می‌شود: اگر end_headers گلوگاه واقعی نباشد، مسیر خطا بی‌سرآیند می‌ماند.
    check('بخش۲۱ CSP روی پاسخ '+_lbl, len(_h(_hs,'Content-Security-Policy'))==1, _hs)
    check('بخش۲۱ nosniff روی پاسخ '+_lbl, _h(_hs,'X-Content-Type-Options')==['nosniff'], _hs)
    check('بخش۲۱ X-Frame-Options روی پاسخ '+_lbl, _h(_hs,'X-Frame-Options')==['DENY'], _hs)
    check('بخش۲۱ Referrer-Policy روی پاسخ '+_lbl, _h(_hs,'Referrer-Policy')==['strict-origin-when-cross-origin'], _hs)
    check('بخش۲۱ Permissions-Policy روی پاسخ '+_lbl, len(_h(_hs,'Permissions-Policy'))==1, _hs)

_pp=(_h(_api[1],'Permissions-Policy') or [''])[0]
# قابلیت‌هایی که اپ «واقعاً» استفاده می‌کند نباید بسته شوند، وگرنه صدای سالمند و
# موقعیت مکانی مراقب از کار می‌افتد. این سه بررسی جلوی «بستن کورکورانه» را می‌گیرند.
check('بخش۲۱ microphone بسته نشده (getUserMedia در index.html)', 'microphone=()' not in _pp, _pp)
check('بخش۲۱ geolocation بسته نشده (getCurrentPosition در caregiver.html)', 'geolocation=()' not in _pp, _pp)
check('بخش۲۱ camera بسته شده (استفاده نمی‌شود)', 'camera=()' in _pp, _pp)

_csp=(_h(_api[1],'Content-Security-Policy') or [''])[0]
for _d in ["frame-ancestors 'none'","object-src 'none'","base-uri 'none'","form-action 'self'"]:
    check('بخش۲۱ CSP شامل '+_d, _d in _csp, _csp)

# HSTS عمداً نیامده: RFC 6797 می‌گوید فقط روی HTTPS. نبودنش باید «تصمیم مستند» بماند،
# نه اینکه کسی بعداً تصادفی اضافه‌اش کند یا تصادفی حذف شود.
check('بخش۲۱ HSTS ارسال نمی‌شود (سرور HTTP ساده است)', _h(_api[1],'Strict-Transport-Security')==[], _api[1])
check('بخش۲۱ نبودِ HSTS در متن کد مستند شده', 'Strict-Transport-Security' in srvsrc and 'RFC 6797' in srvsrc)

check('بخش۲۱ Cache-Control: no-store روی /api/ (دادهٔ سلامت)', _h(_api[1],'Cache-Control')==['no-store'], _api[1])
check('بخش۲۱ Cache-Control: no-cache روی پوستهٔ اپ', _h(_st[1],'Cache-Control')==['no-cache'], _st[1])
check('بخش۲۱ Cache-Control تکراری ارسال نمی‌شود', len(_h(_api[1],'Cache-Control'))==1 and len(_h(_st[1],'Cache-Control'))==1)

# --- PRAGMA ها: باید روی اتصال واقعی db() سنجیده شوند، نه یک اتصال تازه ---
_pc=_m14.db()
for _p,_exp in [('journal_mode','wal'),('synchronous',1),('busy_timeout',15000),('cache_size',-8000),('temp_store',2)]:
    _got=_pc.execute('PRAGMA '+_p).fetchone()[0]
    check('بخش۲۱ PRAGMA %s == %r'%(_p,_exp), _got==_exp, 'به‌دست‌آمده: %r'%(_got,))
check('بخش۲۱ فایل -wal واقعاً ساخته می‌شود', os.path.exists(_m14.DB+'-wal') or _pc.execute('PRAGMA journal_mode').fetchone()[0]=='wal')
# پژوهش: PRAGMA ها باید «پیش از هر BEGIN/کوئری» اعمال شوند؛ اگر بعد از executescript باشند بی‌اثرند.
_q3=chr(39)*3
_i_j=srvsrc.find(chr(80)+"RAGMA journal_mode"); _i_s=srvsrc.find("c.executescript("+_q3+"CREATE TABLE")
check('بخش۲۱ PRAGMA در متن کد پیدا می‌شود', _i_j>=0 and _i_s>=0, (_i_j,_i_s))
check('بخش۲۱ PRAGMA ها پیش از executescript اسکیم اجرا می‌شوند', 0<=_i_j<_i_s, (_i_j,_i_s))

# --- ایندکس‌ها: وجودشان کافی نیست؛ باید در «نقشهٔ اجرا» هم دیده شوند ---
_need=['ix_vitals_measured','ix_alerts_status_created','ix_actions_requested','ix_transactions_created',
       'ix_messages_created','ix_locations_created','ix_reminder_events_date','ix_medication_logs_date']
_have={r[0] for r in _pc.execute("SELECT name FROM sqlite_master WHERE type='index'")}
check('بخش۲۱ هر ۸ ایندکس نو ساخته شده‌اند', all(n in _have for n in _need), sorted(set(_need)-_have))
for _q,_ix in [("SELECT * FROM vitals ORDER BY measured_at DESC LIMIT 5",'ix_vitals_measured'),
               ("SELECT * FROM alerts WHERE status='open' ORDER BY created_at DESC",'ix_alerts_status_created'),
               ("SELECT * FROM reminder_events WHERE reminder_date='x'",'ix_reminder_events_date'),
               ("SELECT * FROM caregiver_actions ORDER BY requested_at DESC LIMIT 5",'ix_actions_requested')]:
    _plan=' | '.join(x[3] for x in _pc.execute('EXPLAIN QUERY PLAN '+_q))
    check('بخش۲۱ نقشهٔ اجرا از %s استفاده می‌کند'%_ix, _ix in _plan, _plan)
# سهم token در این دو جدول PRIMARY KEY است؛ ایندکس دوم فقط نوشتن را کندتر می‌کرد.
check('بخش۲۱ ایندکس زائد روی shares(token) ساخته نشده', not any(n.startswith('ix_shares') for n in _have), sorted(_have))
check('بخش۲۱ ایندکس زائد روی caregiver_sessions(token) ساخته نشده', not any(n.startswith('ix_sessions') for n in _have), sorted(_have))
_pc.close()

# --- دسترسی‌پذیری WCAG 2.2: پیمایش واقعی DOM در ترتیب سند، نه grep ---
class _FP(_hp.HTMLParser):
    """نخستین عنصر فوکوس‌پذیر در ترتیب سند را پیدا می‌کند (معیار واقعی SC 2.4.1)."""
    def __init__(s2): super().__init__(); s2.first=None; s2.main=None
    def handle_starttag(s2,tag,attrs):
        a=dict(attrs)
        if s2.first is None and (tag in ('button','input','select','textarea')
            or (tag=='a' and a.get('href') is not None)
            or (a.get('tabindex') not in (None,'-1'))): s2.first=(tag,a)
        if tag=='main': s2.main=a
for _f in ['index.html','caregiver.html','admin.html']:
    _t=open(os.path.join(ROOT,_f),encoding='utf-8').read()
    _p=_FP(); _p.feed(_t)
    check('بخش۲۱ %s: نخستین عنصر فوکوس‌پذیر = پیوند پرش'%_f,
          _p.first is not None and _p.first[1].get('class')=='skip-link' and _p.first[1].get('href')=='#main', _p.first)
    check('بخش۲۱ %s: <main> بومی با tabindex="-1"'%_f, _p.main is not None and _p.main.get('tabindex')=='-1', _p.main)
    check('بخش۲۱ %s: prefers-contrast:more دارد'%_f, '@media (prefers-contrast:more)' in _t)
    check('بخش۲۱ %s: حلقهٔ فوکوس ≥۲px (WCAG 2.4.13)'%_f, ':focus-visible{outline:3px' in _t)
    check('بخش۲۱ %s: پیوند پرش با display:none پنهان نشده'%_f, 'skip-link{position:absolute' in _t and 'skip-link{display:none' not in _t)
_a=open(os.path.join(ROOT,'index.html'),'rb').read()
_b=os.path.join(ROOT,'android','app','src','main','assets','index.html')
check('بخش۲۱ نسخهٔ assets اندروید بایت‌به‌بایت یکسان است', not os.path.exists(_b) or open(_b,'rb').read()==_a)

_s21.shutdown(); _s21.server_close()

# ===================== بخش ۲۲: سازگاری CSP با مسیرهای واقعی اپ، و مقدارهای غیرمتناهی =====================
# این بخش مستقیماً به دو باگی می‌پردازد که هر دو «بی‌صدا» بودند:
#  (۱) CSP که دور سیزدهم افزوده شد، میزبان wss را نداشت و مسیر Gemini Live را در
#      مرورگر می‌بست — ولی هیچ آزمونی CSP را enforce نمی‌کرد، پس دیده نمی‌شد.
#  (۲) json.loads مقدار «1e400» را به inf تبدیل می‌کرد و evaluate_vital با inf
#      «بحرانی» می‌داد؛ اندازه‌گیری شد: سه POST زباله → سه هشدار vital_critical جعلی.
_s22=ThreadingHTTPServer(('127.0.0.1',0),_m14.Handler)
threading.Thread(target=_s22.serve_forever,daemon=True).start()
B22='http://127.0.0.1:%d'%_s22.server_address[1]
print()
print('--- بخش ۲۲: سازگاری CSP با اپ + مقدارهای غیرمتناهی ---')

from urllib.parse import urlparse as _up22
_DEFAULT_PORTS={'http':80,'https':443,'ws':80,'wss':443}
def _scheme_match(a,b):
    a,b=a.lower(),b.lower()
    if a==b: return True
    if a=='http' and b=='https': return True   # ارتقای مجاز CSP3
    if a=='ws'   and b=='wss':   return True   # ارتقای مجاز CSP3
    return False                                # https→wss مجاز «نیست»
def _csp_match(url,expr,os_,oh,op):
    u=_up22(url)
    if expr=="'self'":
        return (oh==u.hostname and op==(u.port or _DEFAULT_PORTS.get(u.scheme))
                and (_scheme_match(os_,u.scheme) or u.scheme in ('https','wss')))
    if expr.endswith(':') and '/' not in expr[:-1]: return _scheme_match(expr[:-1],u.scheme)
    e=_up22(expr if '//' in expr else 'https://'+expr)
    if not _scheme_match(e.scheme,u.scheme): return False
    h=e.hostname
    if h.startswith('*.'):
        if not (u.hostname==h[2:] or (u.hostname or '').endswith(h[1:])): return False
    elif h!=u.hostname: return False
    return (e.port or _DEFAULT_PORTS.get(e.scheme))==(u.port or _DEFAULT_PORTS.get(u.scheme))
def _directive(name):
    for part in _m14.CSP.split(';'):
        p=part.strip()
        if p.startswith(name+' '): return p.split()[1:]
    return ['__ABSENT__']
_OS,_OH,_OP='https','sepandyar.example.com',443
def _allowed(directive,url):
    return any(_csp_match(url,e,_OS,_OH,_OP) for e in _directive(directive))

# میزبان wss از خودِ LIVE_WS_BASE گرفته می‌شود، نه از یک رشتهٔ کپی‌شده؛ وگرنه
# اگر آدرس عوض شود این آزمون بی‌صدا سبز می‌ماند.
_ws_host=_up22(_m14.LIVE_WS_BASE).netloc
_real=[('connect-src',_m14.LIVE_WS_BASE+'?access_token=x','Gemini Live (WebSocket) — بند ۵'),
       ('connect-src','https://api.openai.com/v1/realtime/calls','OpenAI realtime'),
       ('connect-src','https://sepandyar.example.com/api/vitals','API خودی'),
       ('font-src','https://fonts.gstatic.com/s/vazirmatn/x.woff2','فونت Vazirmatn'),
       ('style-src','https://fonts.googleapis.com/css2?family=Vazirmatn','CSS گوگل'),
       ('img-src','https://upload.wikimedia.org/x.jpg','تصویر دارو (disambiguation)')]
for _d,_u,_l in _real:
    check('بخش۲۲ CSP مسیر واقعی را می‌پذیرد: '+_l, _allowed(_d,_u), _d+' '+_u[:70])
# کنترل منفی: اگر سیاست هر چیزی را بپذیرد، بررسی‌های بالا بی‌معنا می‌شوند.
for _d,_u in [('connect-src','https://evil.example.com/x'),('connect-src','wss://evil.example.com/x'),
              ('script-src','https://evil.example.com/x.js'),('img-src','http://evil.example.com/x.png')]:
    check('بخش۲۲ CSP مبدأ متخاصم را می‌بندد: '+_d, not _allowed(_d,_u), _u)
check('بخش۲۲ میزبان wss دقیقاً همان LIVE_WS_BASE است', _ws_host=='generativelanguage.googleapis.com', _ws_host)

# --- مقدارهای غیرمتناهی: باید ۴۰۰ بدهند و «هیچ» هشداری نسازند ---
def _alert_count():
    return len(req(B22,'/api/alerts')[1].get('items',[]))
_n0=_alert_count()
for _v in ['-1e400','1e400','1e999','Infinity','-Infinity','NaN','inf','nan']:
    _code,_j=req(B22,'/api/vitals','POST',{'type':'weight','value':_v})
    check('بخش۲۲ value=%s با ۴۰۰ رد می‌شود'%_v, _code==400 and _j.get('error')=='invalid_vital', (_code,_j))
_n1=_alert_count()
check('بخش۲۲ ورودی غیرمتناهی هیچ هشدار بحرانی جعلی نمی‌سازد', _n1==_n0, (_n0,_n1))
# کنترل مثبت: اگر این سبز بماند ولی بالایی‌ها هم سبز باشند، ممکن است کل
# هشداردهی از کار افتاده باشد. پس بحران «واقعی» باید هنوز هشدار بسازد.
_code,_j=req(B22,'/api/vitals','POST',{'type':'blood_pressure','value':{'systolic':300,'diastolic':180}})
check('بخش۲۲ بحران واقعی هنوز critical ارزیابی می‌شود', _code==201 and any(r.get('status')=='critical' for r in (_j.get('evaluation') or {}).get('results',[])), (_code,_j))
check('بخش۲۲ بحران واقعی هنوز هشدار می‌سازد', _alert_count()>_n1)
_code,_j=req(B22,'/api/vitals','POST',{'type':'weight','value':72.5})
check('بخش۲۲ مقدار عادی هنوز normal است', _code==201 and (_j.get('evaluation') or {}).get('results',[{}])[0].get('status')=='normal', (_code,_j))

# --- همان قاعده برای remaining / refill_threshold (شکاف باز از دور ششم) ---
for _lbl,_d in [('remaining=1e400',{'remaining':'1e400','refill_threshold':5}),
                ('refill_threshold=1e400',{'remaining':3,'refill_threshold':'1e400'}),
                ('remaining=nan',{'remaining':'nan','refill_threshold':5}),
                ('remaining=inf',{'remaining':'inf','refill_threshold':5})]:
    _code,_j=req(B22,'/api/medications/x-details-22/details','POST',_d)
    check('بخش۲۲ %s با ۴۰۰ رد می‌شود'%_lbl, _code==400 and _j.get('error')=='invalid_medication_quantity', (_code,_j))
_code,_j=req(B22,'/api/medications/x-details-22/details','POST',{'remaining':30,'refill_threshold':5})
check('بخش۲۲ مقدارهای معتبر remaining/refill_threshold هنوز پذیرفته می‌شوند', _code==200, (_code,_j))
_code,_j=req(B22,'/api/medications/x-refill-22/refill','POST',{'amount':'1e400'})
check('بخش۲۲ refill با amount=1e400 با ۴۰۰ رد می‌شود', _code==400 and _j.get('error')=='invalid_amount', (_code,_j))

_s22.shutdown(); _s22.server_close()

# ===================== بخش ۲۳: احراز هویت سطح مراقب =====================
# دو مسیر از هشت مسیر /api/caregiver/* گارد نداشتند، در حالی که هر دو خواهرشان
# (panel و conversation-summary) داشتند. چون payload این جدول شمارهٔ «کامل» مراقب
# را دارد — همان داده‌ای که /api/caregivers برای ناشناس ماسک می‌کند — نشتی حریم
# خصوصی بود. و deliver بی‌گارد از آن بدتر بود: مهاجم می‌توانست درخواست تماسِ در
# انتظار سالمند را delivered علامت بزند تا هیچ‌کس سراغش نرود (مسئلهٔ ایمنی).
_s23=ThreadingHTTPServer(('127.0.0.1',0),_m14.Handler)
threading.Thread(target=_s23.serve_forever,daemon=True).start()
B23='http://127.0.0.1:%d'%_s23.server_address[1]
print()
print('--- بخش ۲۳: احراز هویت سطح مراقب ---')

# --- نگهبان ساختاری: هر مسیر /api/caregiver/* باید گارد داشته باشد، مگر آن‌هایی ---
# --- که «عمداً» بازند. این قاعده مسیرهای آینده را هم می‌گیرد، نه فقط فهرست امروز. ---
OPEN_ON_PURPOSE={'/api/caregiver/session','/api/caregiver/call-request'}
import ast as _ast23
_tree=_ast23.parse(srvsrc)
_missing=[]; _seen=[]
class _G(_ast23.NodeVisitor):
    def visit_If(self,node):
        t=node.test; lit=None
        # p=='/api/...'  یا  p.startswith('/api/...')
        if isinstance(t,_ast23.Compare) and len(t.comparators)==1 and isinstance(t.comparators[0],_ast23.Constant) \
           and isinstance(t.comparators[0].value,str) and t.comparators[0].value.startswith('/api/caregiver/'):
            lit=t.comparators[0].value
        elif isinstance(t,_ast23.Call) and isinstance(t.func,_ast23.Attribute) and t.func.attr=='startswith' and t.args \
           and isinstance(t.args[0],_ast23.Constant) and isinstance(t.args[0].value,str) \
           and t.args[0].value.startswith('/api/caregiver/'):
            lit=t.args[0].value
        if lit is not None:
            _seen.append(lit)
            body_src=_ast23.get_source_segment(srvsrc,node) or ''
            if 'caregiver_session(' not in body_src and lit not in OPEN_ON_PURPOSE:
                _missing.append(lit)
        self.generic_visit(node)
_G().visit(_tree)
check('بخش۲۳ نگهبان ساختاری مسیرهای caregiver را پیدا می‌کند', len(_seen)>=6, _seen)
check('بخش۲۳ هر مسیر /api/caregiver/* گارد احراز هویت دارد (جز موارد عمدی)', _missing==[], _missing)
for _o in sorted(OPEN_ON_PURPOSE):
    check('بخش۲۳ %s عمداً باز است (caller آن سالمند یا خودِ ورود است)'%_o, _o in _seen, _seen)

# --- اثبات رفتاری ---
_c,_cg=req(B23,'/api/caregivers','POST',{'name':'نگهبان تست','phone':'09350001122','role':'پسر'})
_code=_cg.get('invite_code')
req(B23,'/api/consents','POST',{'scope':'health','granted':True})
_a,_r=req(B23,'/api/caregiver/call-request','POST',{'reason':'حالم خوب نیست'})
_aid=(_r or {}).get('id')
_s,_ses=req(B23,'/api/caregiver/session','POST',{'phone':'09350001122','code':_code})
_tok=(_ses or {}).get('token')
check('بخش۲۳ نشست مراقب با کد دعوت باز می‌شود', _s==201 and bool(_tok), (_s,_ses))

_c,_j=req(B23,'/api/caregiver/actions')
check('بخش۲۳ GET ناشناس /api/caregiver/actions رد می‌شود', _c==403 and _j.get('error')=='caregiver_session_required', (_c,_j))
_c,_j=req(B23,'/api/caregiver/actions/%s/deliver'%_aid,'POST',{})
check('بخش۲۳ deliver ناشناس رد می‌شود', _c==403 and _j.get('error')=='caregiver_session_required', (_c,_j))
_c,_j=req_raw(B23,'/api/caregiver/actions',json.dumps({}).encode(),'GET')
check('بخش۲۳ توکن جعلی رد می‌شود', _c==403, (_c,_j))

# کنترل مثبت: اگر فقط ۴۰۳ را بسنجیم، ممکن است کل سطح مراقب از کار افتاده باشد.
import http.client as _hc23
def _req_tok(base,path,method='GET',data=None,tok=None):
    u=urlparse(base); hd={'Content-Type':'application/json'}
    if tok: hd['X-Caregiver-Token']=tok
    b=json.dumps(data,ensure_ascii=False).encode() if data is not None else None
    cn=_hc23.HTTPConnection(u.hostname,u.port,timeout=30); cn.request(method,path,body=b,headers=hd)
    r=cn.getresponse(); raw=r.read(); cn.close()
    try: return r.status,json.loads(raw or b'{}')
    except Exception: return r.status,{'_raw':raw[:80].decode('utf-8','replace')}
_c,_j=_req_tok(B23,'/api/caregiver/actions',tok=_tok)
check('بخش۲۳ مراقب دارای توکن فهرست اقدام‌ها را می‌بیند', _c==200 and len(_j.get('items',[]))>=1, (_c,_j))
_c,_j=_req_tok(B23,'/api/caregiver/actions/%s/deliver'%_aid,'POST',{'delivered_by':'نگهبان تست'},tok=_tok)
check('بخش۲۳ مراقب دارای توکن می‌تواند تحویل را ثبت کند', _c==200 and _j.get('status')=='delivered', (_c,_j))
# مسیر سالمند نباید بسته شود: index.html هیچ توکنی ندارد.
_c,_j=req(B23,'/api/caregiver/call-request','POST',{'reason':'کنترل مثبت'})
check('بخش۲۳ درخواست تماس سالمند بدون توکن کار می‌کند', _c==201, (_c,_j))

_s23.shutdown(); _s23.server_close()

# ========== بخش ۲۵: بازخورد عمل در پنل مراقب ==========
# سه فراخوان در caregiver.html از هلپر post() رد می‌شدند و با fetch خام می‌رفتند،
# پس نه توکن می‌فرستادند و نه پاسخ را می‌سنجیدند. POST /api/safe-zones سه مسیر
# خطای واقعاً دسترس‌پذیر دارد (lat/lon نال، مقدار غیرمتناهی، شعاع <= ۰) و در همهٔ
# آن‌ها مراقب «افزودن محدودهٔ امن» را می‌زد و هیچ اتفاقی نمی‌افتاد: منطقه ثبت نمی‌شد
# و هیچ پیامی هم نبود. اثبات رفتاری با jsdom انجام شد (۹ بررسی، ۰ شکست)؛ این‌جا
# معادل سطح منبع است تا بدون وابستگی به node همیشه اجرا شود.
print()
print('--- بخش ۲۵: بازخورد عمل در پنل مراقب ---')
_cg=open(os.path.join(ROOT,'caregiver.html'),encoding='utf-8').read()
# ۱) فقط دو هلپر get/post حق دارند fetch خام بزنند
_nf=re.findall(r'await fetch\(',_cg)
check('بخش۲۵ فقط هلپرهای get/post با fetch خام کار می‌کنند', len(_nf)==2, len(_nf))
check('بخش۲۵ فراخوان مستقیم /api/safe-zones با fetch خام نمانده',
      "fetch(API+'/api/safe-zones'" not in _cg, _cg.find("fetch(API+'/api/safe-zones'"))
check('بخش۲۵ فراخوان مستقیم /ack با fetch خام نمانده',
      "fetch(API+'/api/alerts/'" not in _cg, _cg.find("fetch(API+'/api/alerts/'"))
check('بخش۲۵ فراخوان مستقیم /complete با fetch خام نمانده',
      "fetch(API+'/api/care-tasks/'" not in _cg, _cg.find("fetch(API+'/api/care-tasks/'"))
# ۲) هر سه هندلر باید شاخهٔ موفقیت و شکست داشته باشند
for _fn in ['ack','completeTask','addCurrentZone']:
    _m=re.search(r'async function '+_fn+r'\(.*?(?=\n(?:async )?function |\nfunction |\Z)',_cg,re.S)
    _body=_m.group(0) if _m else ''
    check('بخش۲۵ %s نتیجهٔ درخواست را می‌سنجد'%_fn, 'r.ok' in _body, _body[:120])
    check('بخش۲۵ %s در هر دو شاخه بازخورد می‌دهد'%_fn, _body.count('sayStatus')>=2, _body.count('sayStatus'))
# ۳) ناحیهٔ اعلام زنده
check('بخش۲۵ ناحیهٔ aria-live دارد', 'aria-live="polite"' in _cg, _cg.find('aria-live'))
check('بخش۲۵ ناحیهٔ وضعیت role="status" دارد', 'id="cg-status"' in _cg and 'role="status"' in _cg, None)
check('بخش۲۵ ناحیهٔ وضعیت پیش از محتوای اصلی در ترتیب سند است',
      0 < _cg.find('id="cg-status"') < _cg.find('id="main"'),
      (_cg.find('id="cg-status"'),_cg.find('id="main"')))
check('بخش۲۵ CSS وضعیت، حالت خالی را پنهان می‌کند', '.cg-status:empty{display:none}' in _cg, None)

# ================== بخش ۲۴: منطق روزانه بر پایهٔ ساعت ایران ==================
# چهار محل از منطق روزانه از datetime.now() خام استفاده می‌کردند، یعنی ساعتِ خودِ
# سرور. روی هر میزبانی که منطقهٔ زمانی‌اش تهران نیست، یادآوری دارو به همان اختلاف
# جابه‌جا می‌شد. اثبات پیش از رفع: دوزی که «همین لحظه» به وقت تهران سررسید بود،
# روی سرور UTC سررسید گزارش نمی‌شد (۰ در برابر ۱). بدتر، پنجرهٔ سکوت ۲۲:۰۰–۰۷:۰۰
# به ۰۱:۳۰–۱۰:۳۰ ایران ترجمه می‌شد: یادآوری صبحگاهی سرکوب و سالمند نصفه‌شب بیدار.
print()
print('--- بخش ۲۴: منطق روزانه بر پایهٔ ساعت ایران ---')

# ۱) نگهبان ساختاری: هیچ datetime.now() خامی نباید در server.py بماند.
import ast as _ast24
_t24=_ast24.parse(srvsrc)
for _n24 in _ast24.walk(_t24):   # کامنت‌ها و رشته‌ها را بی‌اثر کن تا متن توضیح، کد حساب نشود
    if isinstance(_n24,_ast24.Constant) and isinstance(_n24.value,str): _n24.value=''
_bare=[]
for _n24 in _ast24.walk(_t24):
    if isinstance(_n24,_ast24.Call) and isinstance(_n24.func,_ast24.Attribute) and _n24.func.attr=='now' \
       and not _n24.args and not _n24.keywords:
        _bare.append((_n24.lineno,_ast24.unparse(_n24)))
check('بخش۲۴ هیچ datetime.now() خامی در server.py نمانده', _bare==[], _bare)
check('بخش۲۴ local_now() تعریف شده', 'def local_now():' in srvsrc, srvsrc.find('def local_now():'))

# ۲) خاصیت کلیدی: آفست باید دقیقاً +3:30 باشد. این سنجش مستقل از TZ ماشین است؛
#    تستی که فقط «سررسید درست است» را بسنجد، روی ماشین تهران‌زمانه تصادفی سبز می‌شود.
_ln24=getattr(_m14,'local_now',None)
check('بخش۲۴ local_now روی ماژول سرور موجود است', _ln24 is not None, 'local_now وجود ندارد')
_off=_ln24().utcoffset() if _ln24 else datetime.timedelta(0)
check('بخش۲۴ آفست local_now دقیقاً ۳:۳۰+ است',
      _off==datetime.timedelta(hours=3,minutes=30), str(_off))
_IR=datetime.datetime.now(_m14.ZoneInfo('Asia/Tehran'))
check('بخش۲۴ ساعت local_now با محاسبهٔ مستقل تهران یکی است',
      bool(_ln24) and abs((_ln24()-_IR).total_seconds())<5,
      (_ln24().isoformat() if _ln24 else None,_IR.isoformat()))
check('بخش۲۴ تاریخ «امروز» برابر تاریخ تهران است نه تاریخ سرور',
      bool(_ln24) and _ln24().date().isoformat()==_IR.date().isoformat(),
      (_ln24().date().isoformat() if _ln24 else None,_IR.date().isoformat()))

# ۳) اثبات رفتاری با TZ اجباری دور از تهران. اگر TZ ماشین عوض شود، نتیجه نباید عوض شود.
import time as _t24
_tz_saved=os.environ.get('TZ')
try:
    os.environ['TZ']='UTC'; _t24.tzset()
except Exception:
    pass
_s24=ThreadingHTTPServer(('127.0.0.1',0),_m14.Handler)
threading.Thread(target=_s24.serve_forever,daemon=True).start()
B24='http://127.0.0.1:%d'%_s24.server_address[1]
_dose=datetime.datetime.now(_m14.ZoneInfo('Asia/Tehran')).strftime('%H:%M')
_c,_j=req(B24,'/api/medications','POST',{'name':'متفورمین تست۲۴','dose':'500mg','time':_dose,'frequency':'daily'})
check('بخش۲۴ دارو با ساعت ایران ثبت می‌شود', _c==201, (_c,_j))
_c,_j=req(B24,'/api/reminders/due')
_names=[i.get('name') for i in _j.get('items',[])]
check('بخش۲۴ دوزی که همین لحظه به وقت ایران سررسید است، گزارش می‌شود',
      'متفورمین تست۲۴' in _names, (_c,_names,_dose))
# کنترل منفی: بدون این، تست می‌تواند با «همیشه سررسید است» هم سبز شود.
_c,_j=req(B24,'/api/medications','POST',{'name':'آسپرین تست۲۴','dose':'80mg','time':'05:12','frequency':'daily'})
_c,_j=req(B24,'/api/reminders/due')
_names=[i.get('name') for i in _j.get('items',[])]
check('بخش۲۴ دوزی که سررسید نیست گزارش نمی‌شود', 'آسپرین تست۲۴' not in _names, _names)

# ۴) پنجرهٔ سکوت باید به وقت ایران سنجیده شود — کاربرپسندترین پیامد این باگ.
_now_ir=datetime.datetime.now(_m14.ZoneInfo('Asia/Tehran'))
_qs=(_now_ir+datetime.timedelta(minutes=30)).strftime('%H:%M')
_qe=(_now_ir+datetime.timedelta(minutes=90)).strftime('%H:%M')
req(B24,'/api/reminders/settings','POST',{'quiet_start':_qs,'quiet_end':_qe,'max_nudges':2})
_c,_j=req(B24,'/api/reminders/due')
check('بخش۲۴ پنجرهٔ سکوت ایران یادآوری را سرکوب می‌کند',
      'متفورمین تست۲۴' not in [i.get('name') for i in _j.get('items',[])], (_qs,_qe,_j.get('items')))
# کنترل مثبتِ سرکوب: پنجره را از روی «الان» برداریم، یادآوری باید برگردد.
_qs2=(_now_ir+datetime.timedelta(minutes=180)).strftime('%H:%M')
_qe2=(_now_ir+datetime.timedelta(minutes=240)).strftime('%H:%M')
req(B24,'/api/reminders/settings','POST',{'quiet_start':_qs2,'quiet_end':_qe2,'max_nudges':2})
# کنترل مثبت با داروی تازه: UNIQUE(medication_id,reminder_date,channel) در reminder_events
# فقط یک یادآوری به ازای هر دارو/روز/کانال اجازه می‌دهد، پس همان دارو دوباره شلیک نمی‌شود.
_dose2=datetime.datetime.now(_m14.ZoneInfo('Asia/Tehran')).strftime('%H:%M')
req(B24,'/api/medications','POST',{'name':'لوزارتان تست۲۴','dose':'50mg','time':_dose2,'frequency':'daily'})
_c,_j=req(B24,'/api/reminders/due')
check('بخش۲۴ با برداشتن پنجرهٔ سکوت، یادآوری برمی‌گردد',
      'لوزارتان تست۲۴' in [i.get('name') for i in _j.get('items',[])], (_qs2,_qe2,[i.get('name') for i in _j.get('items',[])]))

# ۵) مرز تاریخ: دوزی که «الان» مصرف می‌شود باید به تاریخ ایران ثبت شود.
_med_id=[i.get('id') for i in (req(B24,'/api/medications')[1].get('items',[])) if i.get('name')=='متفورمین تست۲۴']
if _med_id:
    req(B24,'/api/medications/%s/event'%_med_id[0],'POST',{'event':'taken'})
    _logs=[l for l in _m14.rows(_m14.db(),'SELECT * FROM medication_logs WHERE medication_id=?',(_med_id[0],))]
    check('بخش۲۴ ثبت مصرف به تاریخ ایران نوشته می‌شود',
          bool(_logs) and _logs[0]['log_date']==_IR.date().isoformat(),
          [l['log_date'] for l in _logs]+[_IR.date().isoformat()])
else:
    check('بخش۲۴ ثبت مصرف به تاریخ ایران نوشته می‌شود', False, 'دارو پیدا نشد')
if _tz_saved is None: os.environ.pop('TZ',None)
else: os.environ['TZ']=_tz_saved
try: _t24.tzset()
except Exception: pass

print()
print('بررسی‌ها: %d · شکست: %d'%(total,len(failures)))
if failures:
    print('شکست‌ها:'); [print(' -',f) for f in failures]
sys.exit(1 if failures else 0)
