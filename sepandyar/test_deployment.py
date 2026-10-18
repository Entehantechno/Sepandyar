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
    td=calls[0]['body']['session']['audio']['input']['turn_detection']
    check('دیگر semantic_vad نیست',td.get('type')!='semantic_vad',td)
    check('server_vad استفاده می‌شود',td.get('type')=='server_vad',td)
    check('silence_duration_ms برابر patience است',td.get('silence_duration_ms')==1800,td)
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
print('بررسی‌ها: %d · شکست: %d'%(total,len(failures)))
if failures:
    print('شکست‌ها:'); [print(' -',f) for f in failures]
sys.exit(1 if failures else 0)
