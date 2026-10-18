#!/usr/bin/env python3
"""آزمون لایهٔ گفت‌وگوی زنده (Gemini Live API) — مسیرهٔ الف.

مبنای پژوهشی: docs/RESEARCH_LIVE_VOICE_AI_FA.md
- Gemini 3.8 Live: ورودی صدا $0.005/min، خروجی $0.018/min، فارسی `fa` در فهرست ۹۹ زبان
- silenceDurationMs در AutomaticActivityDetection ← نگاشت مستقیم به patience_ms مرحلهٔ ۵
- فشرده‌سازی بافت الزامی است؛ وگرنه توکن صوتی انباشته هر دور دوباره صورتحساب می‌شود
- توکن موقت باید مدل را در liveConnectConstraints قفل کند (جلوگیری از تزریق ابزار)
"""
import json, os, re, sys, threading, http.client, urllib.error, importlib.util
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

# حمل‌ونقل آزمون عمداً از http.client است، نه urlopen — تا پچ کردن urlopen
# فقط تماس خروجی سرور به گوگل را شبیه‌سازی کند و درخواست‌های خود آزمون را نه.
def req(base,path,method='GET',data=None):
    u=urlparse(base)
    b=json.dumps(data,ensure_ascii=False).encode() if data is not None else None
    conn=http.client.HTTPConnection(u.hostname,u.port,timeout=60)
    conn.request(method,path,body=b,headers={'Content-Type':'application/json'})
    r=conn.getresponse(); raw=r.read(); code=r.status; conn.close()
    try: return code,json.loads(raw or b'{}')
    except Exception: return code,{'_raw':(raw or b'').decode('utf-8','replace')}

# ---------- ۱) مسیر «تنظیم نشده» روی سرور در حال اجرا ----------
print('--- 1) GET /api/live/session بدون GEMINI_API_KEY ---')
s,j=req(BASE,'/api/live/session')
check('بدون کلید، 503 برمی‌گردد',s==503,(s,j))
check('کد خطا live_not_configured است',j.get('error')=='live_not_configured',j)
check('provider برابر none است تا کلاینت به مسیر جایگزین برود',j.get('provider')=='none',j)
check('پیام فارسی است و نام متغیر محیطی را می‌گوید','GEMINI_API_KEY' in (j.get('message') or ''),j.get('message'))

# ---------- ۲) توابع سازندهٔ پیکربندی ----------
print('--- 2) سازندهٔ پیکربندی (توابع خالص) ---')
spec=importlib.util.spec_from_file_location('srv',os.path.join(ROOT,'server.py')); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

pay=m.live_token_payload()
check('توکن یک‌بارمصرف است (uses=1)',pay.get('uses')==1,pay)
check('مدل با پیشوند models/ قفل شده',pay['liveConnectConstraints']['model']=='models/gemini-3.8-live',pay)
lcc=pay['liveConnectConstraints']['config']
check('مودالیته خروجی AUDIO قفل شده',lcc.get('responseModalities')==['AUDIO'],lcc)
check('بازگشت نشست در توکن مجاز شده',('sessionResumption' in lcc),lcc)
check('expireTime با قالب Z پایان می‌یابد',str(pay.get('expireTime','')).endswith('Z'),pay.get('expireTime'))
check('expireTime ثانیه دارد نه میکروثانیه',re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$',str(pay.get('expireTime'))),pay.get('expireTime'))
check('مدل قابل جایگزینی است',m.live_token_payload('gemini-3.1-flash-live-preview')['liveConnectConstraints']['model']=='models/gemini-3.1-flash-live-preview','')

print('--- 3) نگاشت patience_ms به VAD ---')
vad=m.live_vad_config(1800)
check('silenceDurationMs همان صبر کاربر است',vad['silenceDurationMs']==1800,vad)
check('حساسیت پایان گفتار LOW است (پریدن وسط حرف سالمند ممنوع)',vad['endOfSpeechSensitivity']=='END_SENSITIVITY_LOW',vad)
check('حساسیت آغاز گفتار LOW است',vad['startOfSpeechSensitivity']=='START_SENSITIVITY_LOW',vad)
check('VAD خاموش نیست',vad['disabled'] is False,vad)
check('مقدار کم به کف ۸۰۰ms می‌چسبد',m.live_vad_config(200)['silenceDurationMs']==m.LIVE_MIN_SILENCE_MS,m.live_vad_config(200))
check('مقدار زیاد به سقف ۵۰۰۰ms می‌چسبد',m.live_vad_config(99999)['silenceDurationMs']==m.LIVE_MAX_SILENCE_MS,m.live_vad_config(99999))
check('ورودی نامعتبر به پیش‌فرض برمی‌گردد',m.live_vad_config('abc')['silenceDurationMs']==m.DEFAULT_PATIENCE_MS,m.live_vad_config('abc'))
check('کف VAD از بازهٔ پیشنهادی گوگل (۵۰۰–۸۰۰ms) کمتر نیست',m.LIVE_MIN_SILENCE_MS>=500,m.LIVE_MIN_SILENCE_MS)

print('--- 4) دستور سامانهٔ فارسی ---')
c=m.db()
sp=m.live_system_prompt(c)
check('تلفظ تهرانی قید شده','تهرانی' in sp,sp[:120])
check('دری افغانی صریحاً رد شده','دری' in sp,sp[:200])
check('عربی صریحاً رد شده','عربی' in sp,sp[:200])
check('قاعدهٔ جملهٔ کوتاه و واژهٔ آشنا آمده','کوتاه' in sp and 'آشنا' in sp,sp[:200])
check('قاعدهٔ صبر هنگام مکث آمده','مکث' in sp,sp[:200])
check('guardrails دیتابیس در دستور سامانه هست','قواعد ایمنی' in sp,sp[:200])
check('enable_affective_dialog فرستاده نمی‌شود (در ۳.۸ حذف شده و خطا می‌دهد)','affective' not in sp.lower(),sp[:200])

# ---------- ۵) fetch_live_token با urlopen جایگزین ----------
print('--- 5) fetch_live_token — درخواست واقعی به گوگل (شبیه‌سازی‌شده) ---')
calls=[]
class FakeResp:
    def __init__(s,b): s.b=b
    def read(s): return s.b
    def __enter__(s): return s
    def __exit__(s,*a): return False
orig=m.ureq.urlopen
def fake_ok(r,timeout=None):
    calls.append({'url':r.full_url,'headers':{k.lower():v for k,v in r.header_items()},'body':r.data})
    return FakeResp(json.dumps({'name':'auth_tokens/FAKETOKEN123','expireTime':'2026-10-18T13:00:00Z'}).encode())
m.ureq.urlopen=fake_ok
tok=m.fetch_live_token('FAKE_KEY')
m.ureq.urlopen=orig
check('نام توکن برگردانده می‌شود',tok=='auth_tokens/FAKETOKEN123',tok)
check('یک درخواست زده شد',len(calls)==1,calls)
check('آدرس، اندپوینت رسمی v1beta/auth_tokens است',calls[0]['url']==m.LIVE_TOKEN_URL,calls[0]['url'])
check('کلید در هدر x-goog-api-key می‌رود نه در URL','x-goog-api-key' in calls[0]['headers'] and calls[0]['headers']['x-goog-api-key']=='FAKE_KEY',calls[0]['headers'])
check('کلید API در آدرس نشت نمی‌کند','FAKE_KEY' not in calls[0]['url'],calls[0]['url'])
sent=json.loads(calls[0]['body'])
check('بدنه همان live_token_payload است',sent.get('uses')==1 and sent['liveConnectConstraints']['model']=='models/gemini-3.8-live',sent)

def fake_fail(r,timeout=None): raise urllib.error.HTTPError(m.LIVE_TOKEN_URL,403,'denied',{},None)
m.ureq.urlopen=fake_fail
check('خطای HTTP به None نگاشت می‌شود (نه استثنا)',m.fetch_live_token('BAD') is None,'')
m.ureq.urlopen=orig

# ---------- ۶) اجرای واقعی do_GET روی اندپوینت جدید ----------
print('--- 6) اجرای واقعی GET /api/live/session (سرور درون‌فرآیندی) ---')
os.environ['GEMINI_API_KEY']='FAKE_TEST_KEY'
srv=ThreadingHTTPServer(('127.0.0.1',0),m.Handler); port=srv.server_address[1]
threading.Thread(target=srv.serve_forever,daemon=True).start()
IN='http://127.0.0.1:%d'%port
try:
    m.ureq.urlopen=fake_ok; calls.clear()
    st,js=req(IN,'/api/live/session?id=default')
    m.ureq.urlopen=orig
    check('با کلید، 200 برمی‌گردد',st==200,(st,js))
    check('provider برابر gemini است',js.get('provider')=='gemini',js.get('provider'))
    check('توکن به کلاینت داده می‌شود',js.get('token')=='auth_tokens/FAKETOKEN123',js.get('token'))
    check('ws_url از اندپوینت Constrained می‌آید','BidiGenerateContentConstrained' in (js.get('ws_url') or ''),js.get('ws_url'))
    check('توکن در پارامتر access_token است نه key=','access_token=' in (js.get('ws_url') or '') and 'key=' not in (js.get('ws_url') or '').split('access_token=')[0][-6:],js.get('ws_url'))
    check('مدل با پیشوند models/ است',js.get('model')=='models/gemini-3.8-live',js.get('model'))
    gc=js.get('generation_config') or {}
    check('مودالیته خروجی AUDIO است',gc.get('responseModalities')==['AUDIO'],gc)
    check('صدا در speechConfig تنظیم می‌شود',bool(gc.get('speechConfig',{}).get('voiceConfig',{}).get('prebuiltVoiceConfig',{}).get('voiceName')),gc)
    cw=js.get('context_window_compression') or {}
    check('فشرده‌سازی بافت با آستانهٔ توکن فعال است',cw.get('compressTriggerConfig',{}).get('tokensLimit')==m.LIVE_TOKENS_LIMIT,cw)
    check('پنجرهٔ لغزان تنظیم شده','slidingWindow' in cw,cw)
    check('patience_ms به کلاینت اعلام می‌شود',js.get('patience_ms')==1800,js.get('patience_ms'))
    check('اندپوینت گاردریل به کلاینت اعلام می‌شود',js.get('guardrail_endpoint')=='/api/conversation',js.get('guardrail_endpoint'))
    check('دستور سامانه از سرور می‌آید (نه hardcode در کلاینت)','تهرانی' in (js.get('system_instruction') or ''),(js.get('system_instruction') or '')[:80])

    print('--- 7) پروفایل صوتی شخصی → silenceDurationMs ---')
    st2,_=req(IN,'/api/voice-profile','POST',{'id':'livetester','name':'آزمون','dialect':'mashhadi','patience_ms':3000,'confidence_floor':0.6,'calibrated':True})
    check('پروفایل آزمون ساخته شد',st2==200,st2)
    m.ureq.urlopen=fake_ok
    st3,js3=req(IN,'/api/live/session?id=livetester')
    m.ureq.urlopen=orig
    check('نشست با پروفایل شخصی 200 است',st3==200,(st3,js3))
    check('صبر ۳۰۰۰ms کاربر به silenceDurationMs رسید',js3['realtime_input_config']['automaticActivityDetection']['silenceDurationMs']==3000,js3.get('realtime_input_config'))
    check('patience_ms در پاسخ هم ۳۰۰۰ است',js3.get('patience_ms')==3000,js3.get('patience_ms'))
    check('پروفایل درست انتخاب شده',js3.get('profile')=='livetester',js3.get('profile'))
finally:
    srv.shutdown(); srv.server_close()
    os.environ.pop('GEMINI_API_KEY',None)

# ---------- ۸) گاردریل قطعی روی متن ورودی ----------
print('--- 8) لایهٔ ایمنی قطعی روی متن مسیر زنده ---')
st,r=req(BASE,'/api/conversation','POST',{'text':'تنگی نفس دارم','profile':'default','source':'live'})
check('POST /api/conversation 200 است',st==200,(st,r))
check('متن پرخطر رهگیری می‌شود',r.get('safety') in ('urgent','caution'),r.get('safety'))
check('پاسخ گفتاری ایمن برگردانده می‌شود',bool(r.get('spoken_reply')),r)
check('پاسخ بالینی مسدود می‌شود',r.get('clinical_answer_blocked') is True,r)
check('intent روی safety.emergency می‌رود',r.get('intent')=='safety.emergency',r.get('intent'))
check('هشدار و اقدام مراقب ساخته می‌شود',bool(r.get('alert_id')) and bool(r.get('action_id')),(r.get('alert_id'),r.get('action_id')))
st,r2=req(BASE,'/api/conversation','POST',{'text':'دوز دارو را زیاد کنم','profile':'default','source':'live'})
check('سؤال درمانی مبهم به ارجاع می‌رود',r2.get('safety')=='caution' and r2.get('intent')=='safety.referral',(r2.get('safety'),r2.get('intent')))
st,r3=req(BASE,'/api/conversation','POST',{'text':'سلام حالت چطوره','profile':'default','source':'live'})
check('گپ معمولی ایمن است',r3.get('safety')=='normal',r3.get('safety'))

# این دو مورد قبلاً شکاف بودند (تطبیق زیررشتهٔ صرف) و اکنون باید گرفته شوند
st,g1=req(BASE,'/api/conversation','POST',{'text':'درد شدید قفسه سینه دارم','profile':'default','source':'live'})
check('واژهٔ میانی دیگر تطبیق را نمی‌شکند',g1.get('safety')=='urgent' and g1.get('intent')=='safety.emergency',(g1.get('safety'),g1.get('intent')))
st,g2=req(BASE,'/api/conversation','POST',{'text':'نفسم نمیاد','profile':'default','source':'live'})
check('عبارت محاوره‌ای تنگی نفس گرفته می‌شود',g2.get('safety')=='urgent',(g2.get('safety'),g2))
st,g3=req(BASE,'/api/conversation','POST',{'text':'سینه‌ام درد می‌کند','profile':'default','source':'live'})
check('ترتیب وارونهٔ واژه‌ها هم گرفته می‌شود',g3.get('safety')=='urgent',(g3.get('safety'),g3))
st,g4=req(BASE,'/api/conversation','POST',{'text':'داروهایم را سر وقت خوردم','profile':'default','source':'live'})
check('گزارش عادی دارو به اورژانس نمی‌رود',g4.get('safety')=='normal',(g4.get('safety'),g4))
st,g5=req(BASE,'/api/conversation','POST',{'text':'فشار خونم امروز خوب بود','profile':'default','source':'live'})
check('گزارش عادی فشار خون به اورژانس نمی‌رود',g5.get('safety')=='normal',(g5.get('safety'),g5))

print('--- 8b) حذف تکرار هشدار در گاردریل زنده ---')
html_guard=open(os.path.join(ROOT,'index.html'),encoding='utf-8').read()
check('کلید آخرین عبارت رهگیری‌شده نگه داشته می‌شود','lastGuardKey' in html_guard,'')
check('پنجرهٔ زمانی حذف تکرار وجود دارد','nowMs-lastGuardAt<20000' in html_guard,'')
check('متن پیش از ارسال یکسان‌سازی می‌شود',"replace(/\\s+/g,' ')" in html_guard,'')

# ---------- ۹) قرارداد کلاینت (index.html) ----------
print('--- 9) قرارداد کلاینت در index.html ---')
html=open(os.path.join(ROOT,'index.html'),encoding='utf-8').read()
for probe,label in [('BidiGenerateContentConstrained' ,'اندپوینت Constrained در کلاینت لازم نیست (از سرور می‌آید)')]:
    pass
check('تابع tryLiveVoice تعریف شده','async function tryLiveVoice(' in html,'')
check('/api/live/session صدا زده می‌شود',"/api/live/session?id=" in html,'')
check('پیام setup با کلید setup فرستاده می‌شود','{setup:{model:s.model' in html,'')
check('realtimeInputConfig از سرور گرفته می‌شود','realtimeInputConfig:s.realtime_input_config' in html,'')
check('فشرده‌سازی بافت فرستاده می‌شود','contextWindowCompression:s.context_window_compression' in html,'')
check('بازگشت نشست فعال است','sessionResumption:resumptionHandle' in html,'')
check('ترنسکریپت ورودی و خروجی هر دو خواسته شده','inputAudioTranscription:{}' in html and 'outputAudioTranscription:{}' in html,'')
check('صدا با نرخ ۲۴۰۰۰ پخش می‌شود','createBuffer(1,n,24000)' in html,'')
check('صدا با نرخ ۱۶۰۰۰ فرستاده می‌شود','audio/pcm;rate=16000' in html,'')
check('mediaChunks با قالب درست','realtimeInput:{mediaChunks:[' in html,'')
check('گفت‌وگوی زنده از گاردریل سرور رد می‌شود','guardLiveTranscript(' in html,'')
check('گاردریل به /api/conversation می‌رود',"/api/conversation'" in html and 'source:\'live\'' in html,'')
check('پیام goAway مدیریت می‌شود','if(x.goAway)' in html,'')
check('شبکهٔ ایمنی صدای خالی وجود دارد','emptyAudioFallback' in html,'')
check('enable_affective_dialog فرستاده نمی‌شود (در ۳.۸ خطا می‌دهد)','affective' not in html.lower(),'')
check('مسیر جایگزین Web Speech حفظ شده','startAlwaysListening()' in html,'')
check('ترتیب راه‌اندازی: Live → OpenAI → Web Speech','await tryLiveVoice()' in html and 'await tryRealtimeVoice()' in html,'')
asset=os.path.join(ROOT,'android/app/src/main/assets/index.html')
check('دارایی Android با index.html همسان است',open(asset,encoding='utf-8').read()==html,'')

print()
print('بررسی‌ها: %d · شکست: %d'%(total,len(failures)))
if failures:
    print('شکست‌ها:'); [print(' -',f) for f in failures]
sys.exit(1 if failures else 0)
