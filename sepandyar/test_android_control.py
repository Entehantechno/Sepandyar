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
STEP_TYPES={'launch','wait','tap_text','input_text','tap_xy','back','home','recents','scroll'}
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

print(f'STAGE-3 TEST: {total} checks; failures={len(failures)}')
if failures: print('FAILED:',', '.join(failures)); sys.exit(1)
print('Stage-3 Android control test passed')
