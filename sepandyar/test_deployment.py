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
print('بررسی‌ها: %d · شکست: %d'%(total,len(failures)))
if failures:
    print('شکست‌ها:'); [print(' -',f) for f in failures]
sys.exit(1 if failures else 0)
