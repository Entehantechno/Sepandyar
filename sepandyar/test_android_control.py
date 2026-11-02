#!/usr/bin/env python3
"""Stage-3 test — کنترل اپ‌های اندروید: کاتالوگ تأییدشده، قرارداد لایه‌ها و ثبت سوابق."""
import json, os, re, sys, urllib.request, urllib.error
BASE='http://127.0.0.1:4174'
ROOT=os.path.dirname(os.path.abspath(__file__))
KT=os.path.join(ROOT,'android','app','src','main','java','ai','arena','sepandyar')
def req(path,method='GET',data=None,headers=None):
 b=json.dumps(data,ensure_ascii=False).encode() if data is not None else None
 r=urllib.request.Request(BASE+path,method=method,data=b,headers={'Content-Type':'application/json',**(headers or {})})
 try:
  with urllib.request.urlopen(r,timeout=5) as x: return x.status,json.loads(x.read())
 except urllib.error.HTTPError as e: return e.code,json.loads(e.read() or b'{}')
failures=[]; total=0
def check(name,cond,detail=''):
 global total
 total+=1
 print(('✅' if cond else '❌'),name,('' if cond else '-> '+str(detail)))
 if not cond: failures.append(name)

print('--- 1) کاتالوگ اپ‌های تأییدشده ---')
s,j=req('/api/apps/approved'); check('GET /api/apps/approved 200',s==200,(s,j))
items=j.get('items',[]); check('دست‌کم ۳ اپ تأییدشده',len(items)>=3,len(items))
pkgs={x['package'] for x in items}
check('اسنپ‌فود و اسنپ و کروم در فهرست‌اند',{'com.snappfood','cab.snapp.passenger','com.android.chrome'}<=pkgs,pkgs)
bad=[x['package'] for x in items if not ((x.get('plan') or {}).get('steps'))]
check('همه اپ‌ها برنامه گام دارند',not bad,bad)
STEP_TYPES={'launch','wait','tap_text','tap_id','input_text','ime_enter','submit',
            'long_click','tap_xy','swipe','back','home','recents','notifications',
            'quick_settings','power_dialog','lock_screen','screenshot','scroll'}
unknown=[(x['package'],st.get('type')) for x in items for st in (x['plan'] or {}).get('steps',[]) if st.get('type') not in STEP_TYPES]
check('همه نوع گام‌ها معتبرند',not unknown,unknown)
check('گام‌های لمس/ورودی متن دارای payload هستند',all(st.get('payload') for x in items for st in (x['plan'] or {}).get('steps',[]) if st['type'] in ('tap_text','input_text')),'')

print('--- 2) قرارداد لایه‌ها: سرور ↔ Kotlin ↔ وب ---')
svc=open(os.path.join(KT,'ScreenControlService.kt'),encoding='utf-8').read()
block=svc[svc.find('fun performStep'):]
block=block[:block.find('\n    }\n')+5] if '\n    }\n' in block else block
kotlin_types=set(re.findall(r'"([a-z_]+)"',block))
server_types={st['type'] for x in items for st in (x['plan'] or {}).get('steps',[])}
missing=server_types-kotlin_types
check('هر نوع گام سرور در performStep پیاده شده',not missing,(missing,kotlin_types))
main=open(os.path.join(KT,'MainActivity.kt'),encoding='utf-8').read()
bridge=set(re.findall(r'@JavascriptInterface fun (\w+)',main))
web=open(os.path.join(ROOT,'index.html'),encoding='utf-8').read()
used=set(re.findall(r'SepandyarNative\.(\w+)',web))
missing_bridge=used-bridge
check('هر متد پل که وب صدا می‌زند در MainActivity وجود دارد',not missing_bridge,(missing_bridge,sorted(bridge)))
check('پل runScreenTask و cancelScreenTask ثبت شده‌اند',{'runScreenTask','cancelScreenTask','hasOverlayPermission','openOverlaySettings'}<=bridge,sorted(bridge))
check('بازگشت نتیجه به وب تعریف شده','window.onScreenTaskResult' in web and 'onScreenTaskResult' in main,'')
check('اجازه SYSTEM_ALERT_WINDOW در مانیفست','SYSTEM_ALERT_WINDOW' in open(os.path.join(ROOT,'android','app','src','main','AndroidManifest.xml'),encoding='utf-8').read(),'')

print('--- 3) ساختار فایل‌های Kotlin (بررسی ساختاری، نه کامپایل) ---')
def strip_kotlin(src):
    """کامنت‌ها و رشته‌ها را حذف می‌کند تا شمارش کروشه فقط کد واقعی را ببیند."""
    out=[]; i=0; n=len(src)
    while i<n:
        ch=src[i]
        if src.startswith('"""',i):
            j=src.find('"""',i+3); i=(j+3) if j>=0 else n; continue
        if ch=='"':
            j=i+1
            while j<n:
                if src[j]=='\\': j+=2; continue
                if src[j]=='"': break
                j+=1
            i=j+1; continue
        if ch=="'":
            j=i+1
            while j<n:
                if src[j]=='\\': j+=2; continue
                if src[j]=="'": break
                j+=1
            i=j+1; continue
        if src.startswith('//',i):
            j=src.find('\n',i); i=j if j>=0 else n; continue
        if src.startswith('/*',i):
            j=src.find('*/',i+2); i=(j+2) if j>=0 else n; continue
        out.append(ch); i+=1
    return ''.join(out)
for fn in sorted(os.listdir(KT)):
    if not fn.endswith('.kt'): continue
    code=strip_kotlin(open(os.path.join(KT,fn),encoding='utf-8').read())
    ok=code.count('{')==code.count('}') and code.count('(')==code.count(')')
    check('کروشه/پرانتز متوازن: '+fn,ok,(code.count('{'),code.count('}'),code.count('('),code.count(')')))

print('--- 4) ثبت سابقه اجرای کار ---')
s,j=req('/api/screen-tasks','POST',{'package':'com.snappfood','title':'اسنپ‌فود','status':'done','steps_total':5,'steps_done':5,'error':''}); check('ثبت اجرای موفق',s==201 and j.get('ok'),(s,j))
s,j=req('/api/screen-tasks','POST',{'package':'cab.snapp.passenger','title':'اسنپ','status':'failed','steps_total':4,'steps_done':2,'error':'«درخواست خودرو» روی صفحه پیدا نشد'}); check('ثبت اجرای ناموفق',s==201,(s,j))
s,j=req('/api/screen-tasks'); runs=j.get('items',[]); check('سوابق خوانده می‌شوند',s==200 and len(runs)>=2,(s,len(runs)))
check('خطای گام در سابقه ثبت شده',any('پیدا نشد' in (r.get('error') or '') for r in runs),[r.get('error') for r in runs][:2])

print('--- 5) دید مراقب بر سوابق کنترل صفحه، فقط با رضایت ---')
req('/api/consents','POST',{'scope':'health','granted':True,'confirmed_by_voice':True})
req('/api/consents','POST',{'scope':'screen_control','granted':False,'confirmed_by_voice':False})
import time as _t
_PH3='095%08d'%(_t.time_ns()%100000000)
s,j=req('/api/caregivers','POST',{'name':'مراقب کنترل صفحه','phone':_PH3,'role':'family','permissions':['health','screen_control']}); invite=j.get('invite_code')
check('کد دعوت برای مراقب کنترل صفحه صادر شد',bool(invite),(s,invite))
s,j=req('/api/caregiver/session','POST',{'phone':_PH3}); check('شماره بدون کد دعوت = 403',s==403 and j.get('error')=='invalid_credentials',(s,j))
s,j=req('/api/caregiver/session','POST',{'phone':_PH3,'code':invite}); tok=j.get('token'); check('نشست مراقب ساخته شد',s==201 and tok,(s,j))
H={'X-Caregiver-Token':tok or ''}
s,j=req('/api/caregiver/panel',headers=H)
check('بدون رضایت screen_control، سوابق کنترل صفحه دیده نمی‌شود',s==200 and j.get('screen_tasks') is None and j.get('screen_control_shared') is False,(s,j.get('screen_control_shared')))
req('/api/consents','POST',{'scope':'screen_control','granted':True,'confirmed_by_voice':True})
s,j=req('/api/caregiver/panel',headers=H)
check('با رضایت، سوابق کنترل صفحه به مراقب نشان داده می‌شود',s==200 and isinstance(j.get('screen_tasks'),list) and len(j.get('screen_tasks'))>=2 and j.get('screen_control_shared') is True,(s,type(j.get('screen_tasks'))))
req('/api/caregiver/session/revoke','POST',headers=H)

print('--- 6) کنترل دستگاه: قرارداد نوع پل + پیکربندی سرویس دسترس‌پذیری ---')
# این بخش دقیقاً همان شکافی را می‌بندد که باعث شد یک خطای کامپایل از
# تست‌ها رد شود: بررسی بخش ۲ فقط «نام» متدها را تطبیق می‌داد، نه امضای
# نوعشان. ScreenTaskRunner.start پارامتر «launch: (String) -> Boolean»
# می‌گیرد، ولی launchApprovedPackage نوع بازگشت نداشت (یعنی Unit) و
# کاتلین Unit را به Boolean تبدیل نمی‌کند؛ پس کل MainActivity کامپایل
# نمی‌شد و قابلیت کنترل دستگاه هرگز ساخته نمی‌شد.
runner=open(os.path.join(KT,'ScreenTaskRunner.kt'),encoding='utf-8').read()

_m=re.search(r'fun start\([^)]*launch:\s*\(String\)\s*->\s*(\w+)',runner)
check('بخش۶ نوع پارامتر launch در ScreenTaskRunner.start تشخیص داده شد',bool(_m),runner[:120])
LAUNCH_RET=(_m.group(1) if _m else None)
check('بخش۶ ScreenTaskRunner.start انتظار (String) -> Boolean دارد',LAUNCH_RET=='Boolean',LAUNCH_RET)

_mb=re.search(r'@JavascriptInterface fun launchApprovedPackage\([^)]*\)\s*:\s*(\w+)',main)
check('بخش۶ launchApprovedPackage نوع بازگشت صریح دارد',bool(_mb),'امضای بدون نوع بازگشت = Unit')
BRIDGE_RET=(_mb.group(1) if _mb else None)
check('بخش۶ نوع بازگشت launchApprovedPackage با انتظار runner می‌خواند',
      BRIDGE_RET==LAUNCH_RET,(BRIDGE_RET,LAUNCH_RET))
check('بخش۶ لامبدای پاس‌داده‌شده به start همان متد Boolean است',
      re.search(r'ScreenTaskRunner\.start\([^)]*\)\s*\{\s*pkg\s*->\s*launchApprovedPackage\(pkg\)\s*\}',main) is not None,'')

# نتیجهٔ performStep باید واقعاً استفاده شود، نه دور ریخته
_att=runner[runner.find('private fun attempt'):]
_att=_att[:_att.find('\n    }\n')+5] if '\n    }\n' in _att else _att
check('بخش۶ نتیجهٔ performStep در attempt استفاده می‌شود',
      re.search(r'=\s*svc\.performStep\(step\)',_att) is not None,'نتیجه دور ریخته می‌شد')
check('بخش۶ موفقیت گام دیگر فقط به دیده‌شدن متن پی‌لود وابسته نیست',
      'acted' in _att and 'svc.isTextVisible(step.expect)' in _att,'')

# پیکربندی سرویس دسترس‌پذیری
_cfg=open(os.path.join(ROOT,'android','app','src','main','res','xml',
                       'accessibility_service_config.xml'),encoding='utf-8').read()
check('بخش۶ isAccessibilityTool="true" اعلام شده',
      'android:isAccessibilityTool="true"' in _cfg,
      'بدون آن، حالت Advanced Protection در اندروید ۱۷ مجوز را لغو می‌کند')
check('بخش۶ canPerformGestures برای dispatchGesture فعال است',
      'android:canPerformGestures="true"' in _cfg,'')
check('بخش۶ canRetrieveWindowContent برای خواندن درخت فعال است',
      'android:canRetrieveWindowContent="true"' in _cfg,'')
check('بخش۶ flagIncludeNotImportantViews فعال است',
      'flagIncludeNotImportantViews' in _cfg,
      'بدون آن کنترل‌های many-apps دیده نمی‌شوند')

# fallback ضربه با dispatchGesture
check('بخش۶ tapOnce در صورت شکست ACTION_CLICK به dispatchGesture می‌افتد',
      re.search(r'private fun tapOnce',svc) is not None and 'return tap(' in svc,'')
# انتخاب فیلد ورودی با فوکوس
check('بخش۶ smartInput اول فیلد دارای فوکوس ورودی را برمی‌دارد',
      'FOCUS_INPUT' in svc,'بدون آن متن در فیلد اشتباه تایپ می‌شد')

# مانیفست + پیکربندی شبکه
_mf=open(os.path.join(ROOT,'android','app','src','main','AndroidManifest.xml'),encoding='utf-8').read()
check('بخش۶ networkSecurityConfig به مانیفست وصل شده',
      'android:networkSecurityConfig="@xml/network_security_config"' in _mf,
      'بدون آن اپ به سرور http محلی نمی‌رسد و هیچ وظیفهٔ کنترلی ممکن نیست')
_nsc=os.path.join(ROOT,'android','app','src','main','res','xml','network_security_config.xml')
check('بخش۶ فایل network_security_config.xml وجود دارد',os.path.exists(_nsc),'')
if os.path.exists(_nsc):
    _n=open(_nsc,encoding='utf-8').read()
    check('بخش۶ فقط حلقهٔ محلی cleartext است، نه همه‌جا',
          'cleartextTrafficPermitted="true"' in _n and '<domain includeSubdomains="false">localhost</domain>' in _n
          and '0.0.0.0/0' not in _n and '*.' not in _n,_n[:200])
check('بخش۶ usesCleartextTraffic="false" دست‌نخورده باقی مانده',
      'android:usesCleartextTraffic="false"' in _mf,'سیاست https-only عمدی است')
check('بخش۶ POST_NOTIFICATIONS در زمان اجرا درخواست می‌شود',
      'Manifest.permission.POST_NOTIFICATIONS' in main,'')
# روی متنِ بدون کامنت بررسی می‌شود: کامنت توضیحیِ خودِ اصلاح، عبارت قدیمی
# را نقل می‌کند و بررسیِ متن خام را به اشتباه قرمز می‌کرد.
_main_code=strip_kotlin(main)
check('بخش۶ نتیجهٔ مجوز با نام مجوز سنجیده می‌شود نه جایگاهش',
      'permissions.indexOf(Manifest.permission.RECORD_AUDIO)' in _main_code
      and 'grantResults.firstOrNull()' not in _main_code,'')

print('--- 7) اتصال به سرور: رفع بن‌بست http بدون شکستن سیاست https ---')
# دو باگ اینجا قفل می‌شوند:
#  ۱) saveServerUrl هر http را رد می‌کرد و به‌علاوه host.contains('.')
#     الزامی بود که خودِ «localhost» را هم رد می‌کرد. سرور MVP روی
#     http:4174 است، پس اپِ نصب‌شده هرگز نمی‌توانست به آن وصل شود و
#     /api/apps/approved خالی می‌ماند => هیچ وظیفهٔ کنترلی ممکن نبود.
#  ۲) setServerUrl در لایهٔ وب بدون توجه به نتیجهٔ native پیام «ذخیره شد»
#     می‌داد؛ یعنی یک شکست بی‌صدا که کاربر نمی‌توانست عیب‌یابی کند.
# نکته: strip_kotlin رشته‌ها را هم پاک می‌کند، پس برای سنجشِ «محتوای
# رشته» باید از متن خام استفاده کرد؛ نسخهٔ بدون رشته باعث می‌شد جست‌وجوی
# «http» هرگز匹配 نکند و چند بررسی به اشتباه قرمز شوند.
_i0=main.find('fun saveServerUrl')
assert _i0>0, 'saveServerUrl not found'
_sv=main[_i0:_i0+1800]

check('بخش۷ saveServerUrl مقدار Boolean برمی‌گرداند (تا وب بتواند رد شدن را بفهمد)',
      re.search(r'@JavascriptInterface fun saveServerUrl\([^)]*\)\s*:\s*Boolean', main) is not None,
      'بدون آن، لایهٔ وب نمی‌تواند شکست را به کاربر نشان دهد')
check('بخش۷ http برای میزبان خصوصی/حلقهٔ محلی پذیرفته می‌شود',
      'scheme == "http" && privateHost' in _sv, _sv[:200])
check('بخش۷ localhost به‌صراحت مجاز است (بدون نیاز به نقطه در هاست)',
      'host.equals("localhost"' in _sv, 'الزام host.contains(".") خودِ localhost را رد می‌کرد')
check('بخش۷ الزام سراسری host.contains(".") برداشته شده',
      'host.contains(\'.\')' not in _sv, '')
check('بخش۷ https برای هر میزبان دیگری همچنان الزامی است (سیاست امنیتی حفظ شد)',
      'scheme == "https"' in _sv, '')
check('بخش۷ بازهٔ خصوصی ۱۷۲.۱۶ تا ۱۷۲.۳۱ درست محدود شده',
      r'172\\.(1[6-9]|2[0-9]|3[01])' in _sv,
      '۱۷۲.x.x همه خصوصی نیستند؛ فقط ۱۶ تا ۳۱')
check('بخش۷ نشانی خالی، مقدار ذخیره‌شده را پاک می‌کند',
      'remove("server_url")' in _sv, 'پیش‌تر نشانی بد برای همیشه می‌ماند')

# پیکربندی شبکه
_nsc2=os.path.join(ROOT,'android','app','src','main','res','xml','network_security_config.xml')
_n2=open(_nsc2,encoding='utf-8').read()
check('بخش۷ نام مستعار میزبانِ شبیه‌ساز (۱۰.۰.۲.۲) در پیکربندی شبکه هست',
      '>10.0.2.2<' in _n2, 'بدون آن، شبیه‌ساز اندروید به سرور میزبان نمی‌رسد')
check('بخش۷ پیکربندی شبکه wildcard یا بازهٔ broad ندارد',
      '*.' not in _n2 and '0.0.0.0/0' not in _n2, '')
check('بخش۷ شبکه به مانیفست وصل است',
      'android:networkSecurityConfig="@xml/network_security_config"' in _mf, '')

# لایهٔ وب باید رد شدن را نشان دهد
check('بخش۷ لایهٔ وب نتیجهٔ saveServerUrl را می‌سنجد',
      'const ok=window.SepandyarNative.saveServerUrl(v)' in web
      and 'ok===false' in web, 'پیش‌تر شکست بی‌صدا بود')
check('بخش۷ در صورت رد شدن، API_BASE ذخیره نمی‌شود',
      web.find('ok===false') < web.find('localStorage.setItem(\'sepandyarServer\',v)'),
      'ترتیب اشتباه = نشانی بد در localStorage می‌ماند')
# متن جدید همان زیررشتهٔ قدیمی را دارد («برای اینترنت، آدرس باید با
# https باشد؛») پس «نبودنِ» آن substring معیار درستی نیست؛ باید حضورِ
# توضیح تازه سنجیده شود.
check('بخش۷ راهنمای کاربر می‌گوید http برای نشانی محلی/خصوصی مجاز است',
      'http با نشانی محلی' in web and 'localhost' in web,
      'پیش‌تر فقط گفته می‌شد «آدرس باید با https باشد» که دیگر درست نبود')

print('--- 8) گارد مبدأ پل + نمادهای بدون import (جایگزین کامپایلر) ---')
# چون در این محیط نه JVM هست نه Android SDK، هیچ‌کدام از فایل‌های Kotlin
# کامپایل نمی‌شوند. این دو گارد جبران می‌کنند:
#  ۱) هر نماد Foo.BAR باید import داشته باشد یا در همان پکیج باشد. این
#     دقیقاً همان کلاسی از خطاست که پیش‌تر رخ داد (launchApprovedPackage
#     با نوع بازگشت Unit) و چون فقط «نام» متدها تطبیق داده می‌شد، از
#     تست‌ها رد می‌شد. یک نمونهٔ واقعی هم در مرحلهٔ ۲۰ رخ داد:
#     WebSettings استفاده شد ولی import نداشت.
#  ۲) پل بومی باید در «زمان فراخوانی» مبدأ را بسنجد.
_KT_BUILTIN={'Int','String','Boolean','Long','Float','Double','Any','Unit','List','Map','Set',
 'MutableList','MutableMap','MutableSet','Array','IntArray','Pair','Triple','Result','CharSequence',
 'Throwable','Exception','NumberFormatException','IllegalArgumentException','IllegalStateException'}
_pkg_syms=set()
_kt_files=sorted(fn for fn in os.listdir(KT) if fn.endswith('.kt'))
for fn in _kt_files:
    _src=open(os.path.join(KT,fn),encoding='utf-8').read()
    _pkg_syms|=set(re.findall(r'\b(?:class|object|interface|enum class|data class|sealed class|fun)\s+(\w+)',_src))
_unresolved=[]
for fn in _kt_files:
    _c=open(os.path.join(KT,fn),encoding='utf-8').read()
    _c=re.sub(r'/\*.*?\*/','',_c,flags=re.S); _c=re.sub(r'//.*','',_c)
    _c=re.sub(r'"(?:\\.|[^"\\])*"','""',_c)
    _imp={i.split('.').pop().strip() for i in re.findall(r'^import\s+([\w.]+)',_c,re.M)}
    # (?<![\w.]) تا نمادِ وسطِ یک مسیرِ کاملاً واجد (مثل android.graphics.Typeface)
    # به اشتباه گزارش نشود — بدون آن سه مثبت کاذب داشتیم.
    for _m in re.finditer(r'(?<![\w.])([A-Z]\w+)\s*\.\s*[A-Za-z_]',_c):
        _s=_m.group(1)
        if _s in _KT_BUILTIN or _s in _imp or _s in _pkg_syms or _s.isupper(): continue
        if (fn,_s) not in [(a,b) for a,b,_ in _unresolved]: _unresolved.append((fn,_s,_m.group(0)[:40]))
check('بخش۸ هیچ نماد Kotlin بدون import استفاده نشده (خطای کامپایل)',
      not _unresolved, _unresolved[:6])
check('بخش۸ WebSettings برای mixedContentMode import شده',
      'import android.webkit.WebSettings' in main, '')

# گارد مبدأ در زمان فراخوانی
check('بخش۸ پرچم @Volatile برای اعتماد مبدأ تعریف شده',
      '@Volatile private var bridgeTrusted' in main, '')
check('بخش۸ پرچم روی نخ UI از onPageStarted به‌روز می‌شود',
      'override fun onPageStarted' in main and 'updateBridgeTrust(url)' in main, '')
check('بخش۸ پرچم در doUpdateVisitedHistory هم به‌روز می‌شود (تغییر مسیر/بازگشت)',
      'override fun doUpdateVisitedHistory' in main, '')
_SENSITIVE=['saveServerUrl','runScreenTask','tvCommand','launchApprovedPackage',
            'callCaregiver','saveVoiceProfile','setAssistantName','cancelScreenTask','bringAppToFront']
_noguard=[]
for _fn in _SENSITIVE:
    _i=main.find('fun %s('%_fn)
    if _i<0: _noguard.append((_fn,'NOT FOUND')); continue
    _body=main[_i:_i+400]
    if 'bridgeTrusted' not in _body: _noguard.append((_fn,'no guard'))
check('بخش۸ همهٔ متدهای حساس پل در زمان فراخوانی مبدأ را می‌سنجند',
      not _noguard, _noguard)
check('بخش۸ web.url مستقیماً از نخ پل خوانده نمی‌شود (باید روی نخ UI باشد)',
      'web.url' not in main or 'runOnUiThread' in main, '')
check('بخش۸ mixedContentMode صریحاً NEVER_ALLOW است',
      'mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW' in main,
      'صفحه https است؛ http غیر-loopback به‌عنوان محتوای مختلط مسدود می‌شود')

print('--- 9) مجموعهٔ کامل گام‌های کنترل صفحه (مرحلهٔ ۲۲) ---')
# پیش از این performStep فقط ۹ نوع گام می‌شناخت و شش عملیات پایه را اصلاً
# نداشت. مهم‌ترینشان ACTION_IME_ENTER بود: بدون آن هیچ رسپی‌ای نمی‌توانست
# یک جست‌وجو را «ارسال» کند و رسپی کروم قطعاً خراب بود.
NEW_STEPS=['tap_id','ime_enter','submit','long_click','swipe','notifications',
           'quick_settings','power_dialog','lock_screen','screenshot']
_missing=[t for t in NEW_STEPS if '"%s"'%t not in svc]
check('بخش۹ همهٔ گام‌های تازه در performStep هستند', not _missing, _missing)
check('بخش۹ ACTION_IME_ENTER استفاده می‌شود', 'ACTION_IME_ENTER' in svc, '')
check('بخش۹ ACTION_LONG_CLICK استفاده می‌شود', 'ACTION_LONG_CLICK' in svc, '')
check('بخش۹ ژست کشیدن مسیر دونقطه‌ای می‌سازد (moveTo + lineTo)',
      'moveTo(x1, y1); lineTo(x2, y2)' in svc, '')
check('بخش۹ ضربهٔ طولانی مدت بلندتری از ضربهٔ معمولی دارد',
      'LONG_PRESS_MS = 600L' in svc and 'StrokeDescription(path, 0, 80)' in svc, '')

# نگهبان نسخه: minSdk=26 است ولی ACTION_IME_ENTER از API 30 و
# GLOBAL_ACTION_LOCK_SCREEN / TAKE_SCREENSHOT از API 28 هستند.
# بدون این نگهبان‌ها روی اندروید ۸ تا ۱۰ خطای زمان اجرا می‌داد.
check('بخش۹ IME_ENTER پشت نگهبان API 30 است',
      'Build.VERSION.SDK_INT >= 30' in svc, '')
check('بخش۹ lock_screen پشت نگهبان API 28 است',
      'GLOBAL_ACTION_LOCK_SCREEN) else false' in svc and 'SDK_INT >= 28' in svc, '')
check('بخش۹ screenshot پشت نگهبان API 28 است',
      'GLOBAL_ACTION_TAKE_SCREENSHOT) else false' in svc, '')
check('بخش۹ Build برای نگهبان‌ها import شده',
      'import android.os.Build' in svc, '')

# تصمیم اخلاقی: تصویر گرفتن «بی‌صدا» روی گوشی سالمند پذیرفتنی نیست.
# AccessibilityService.takeScreenshot (API 30) هیچ اعلان/نمایشگری ندارد؛
# عمداً استفاده نمی‌شود و این سنجش جلوی بازگشت ناخواسته‌اش را می‌گیرد.
# توجه: این سنجش باید روی متنِ «بی‌کامنت» اجرا شود. در ScreenControlService
# یک کامنت هست که توضیح می‌دهد چرا از takeScreenshot استفاده «نمی‌کنیم»؛
# بدون حذف کامنت، همان توضیح به‌شکل استفاده از آن خوانده می‌شد.
_svc_code=strip_kotlin(svc)
check('بخش۹ takeScreenshot بی‌صدا عمداً استفاده نشده (حریم سالمند)',
      'takeScreenshot(' not in _svc_code, 'takeScreenshot در کد پیدا شد')
check('بخش۹ مسیر جایگزین imeEnter برچسب‌های ارسال دارد',
      'SUBMIT_LABELS' in svc and 'جست‌وجو' in svc, '')

# هر گام تازه باید برچسب فارسی روی overlay داشته باشد، وگرنه سالمند
# «در حال اجرا» می‌بیند و نمی‌فهمد چه اتفاقی دارد می‌افتد.
_nolabel=[t for t in ['tap_id','ime_enter','long_click','swipe','notifications',
                      'quick_settings','power_dialog','lock_screen','screenshot']
          if '"%s"'%t not in runner]
check('بخش۹ همهٔ گام‌های تازه برچسب فارسی overlay دارند', not _nolabel, _nolabel)

# رگرسیونِ خودِ باگ: هیچ رسپی‌ای نباید input_text را بی‌واسطه به tap_text
# برساند، چون در هر UI ای که نیازمند ارسال صریح است، گام بعد هرگز پیدا
# نمی‌شود و تا timeout تلاش و سپس شکست می‌خورد.
import json as _json22, re as _re22
_dbsrc=open(os.path.join(ROOT,'app','database.py'),encoding='utf-8').read()
_recipes=_re22.findall(r"\[\{'type':'wait'.*?\}\]", _dbsrc)
check('بخش۹ رسپی‌های پیش‌فرض پیدا شدند', len(_recipes)>=3, len(_recipes))
_badseq=[]
for _r in _recipes:
    _types=_re22.findall(r"'type':'(\w+)'", _r)
    for _i in range(len(_types)-1):
        if _types[_i]=='input_text' and _types[_i+1]=='tap_text':
            _badseq.append(_types)
check('بخش۹ هیچ رسپی‌ای input_text را بی‌واسطه به tap_text نمی‌رساند',
      not _badseq, _badseq)
check('بخش۹ هر سه رسپی گام ارسال (ime_enter) دارند',
      sum(1 for _r in _recipes if "'ime_enter'" in _r)>=3,
      sum(1 for _r in _recipes if "'ime_enter'" in _r))

print(f'STAGE-3 TEST: {total} checks; failures={len(failures)}')
if failures: print('FAILED:',', '.join(failures)); sys.exit(1)
print('Stage-3 Android control test passed')
