#!/usr/bin/env python3
"""Stage-3 test — کنترل اپ‌های اندروید: کاتالوگ تأییدشده، قرارداد لایه‌ها و ثبت سوابق."""
import json, os, re, sys, urllib.request, urllib.error
BASE='http://127.0.0.1:4174'
ROOT=os.path.dirname(os.path.abspath(__file__))
KT=os.path.join(ROOT,'android','app','src','main','java','ai','arena','sepandyar')
# ریشهٔ پروژهٔ اندروید. §۱۳ و §۱۴ هر دو به آن نیاز دارند (manifest،
# res/xml، build.gradle.kts و دارایی assets) و تعریف نشده بود — همان
# چیزی که باعث کرش خاموش و گزارش نادرست «۱۲۰۱ · ۰» شد.
AND=os.path.join(ROOT,'android')
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
# com.snappfood در مرحلهٔ ۲۴ اصلاح شد: آن شناسه هرگز متعلق به اسنپ‌فود نبود
# و آن رسپی بی‌صدا شکست می‌خورد. شناسهٔ رسمی گوگل‌پلی com.zoodfood.android.play است.
check('اسنپ‌فود و اسنپ و کروم و همراه‌من و آپ در فهرست‌اند',
      {'com.zoodfood.android.play','cab.snapp.passenger','com.android.chrome',
       'ir.mci.ecareapp','com.sibche.aspardproject.app'}<=pkgs,pkgs)
bad=[x['package'] for x in items if not ((x.get('plan') or {}).get('steps'))]
check('همه اپ‌ها برنامه گام دارند',not bad,bad)
STEP_TYPES={'launch','wait','tap_text','tap_id','input_text','ime_enter','submit',
            'long_click','tap_xy','swipe','back','home','recents','notifications',
            'quick_settings','power_dialog','lock_screen','screenshot','scroll',
            'focus','a11y_focus','next_node','prev_node','select_text','select_all',
            'copy','cut','paste','clear_text','append_text','expand','collapse',
            'set_progress','double_tap','pinch','drag','dismiss_notifications',
            'split_screen','headset_hook','a11y_all_apps','a11y_home','a11y_back','a11y_recents','confirm'}
# دو واژگانِ جدا. افزودن goto/set_css به STEP_TYPES غلط است: آن‌وقت یک
# رسپی «بومی» می‌تواند از آن‌ها استفاده کند و performStep بی‌صدا false
# برگرداند. هر دسته فقط در واژگان خودش مجاز است.
WEB_STEP_TYPES={'goto','wait_ms','wait_css','click_css','set_css','read_css','probe','confirm'}
def _mode_of(x): return (x['plan'] or {}).get('mode') or 'native'
native_items=[x for x in items if _mode_of(x)=='native']
web_items=[x for x in items if _mode_of(x)=='web']
check('سنجش تهی نیست: هم رسپی بومی هست هم وب', bool(native_items) and bool(web_items),
      (len(native_items), len(web_items)))
unknown=[(x['package'],st.get('type')) for x in native_items for st in (x['plan'] or {}).get('steps',[]) if st.get('type') not in STEP_TYPES]
check('همه نوع گام‌ها معتبرند',not unknown,unknown)
unknown_web=[(x['package'],st.get('type')) for x in web_items for st in (x['plan'] or {}).get('steps',[]) if st.get('type') not in WEB_STEP_TYPES]
check('گام‌های رسپی وب در واژگان وب معتبرند',not unknown_web,unknown_web)
_cross=[(x['package'],st.get('type')) for x in web_items for st in (x['plan'] or {}).get('steps',[])
        if st.get('type') in STEP_TYPES and st.get('type') not in WEB_STEP_TYPES]
check('گام بومی به رسپی وب نشت نکرده (وگرنه هیچ‌کس اجرایش نمی‌کند)',not _cross,_cross)
_wt=open(os.path.join(KT,'WebTaskRunner.kt'),encoding='utf-8').read()
_unimpl=[t for t in sorted({st.get('type') for x in web_items for st in (x['plan'] or {}).get('steps',[])})
         if '"%s"'%t not in _wt]
check('هر گام وب در WebTaskRunner پیاده شده (بی‌صدا حذف نمی‌شود)',not _unimpl,_unimpl)
check('WebTaskRunner گام ناشناخته را true نمی‌دهد (else -> false)',
      'else -> "false"' in _wt, '')
check('گام‌های لمس/ورودی متن دارای payload هستند',all(st.get('payload') for x in items for st in (x['plan'] or {}).get('steps',[]) if st['type'] in ('tap_text','input_text')),'')

print('--- 2) قرارداد لایه‌ها: سرور ↔ Kotlin ↔ وب ---')
svc=open(os.path.join(KT,'ScreenControlService.kt'),encoding='utf-8').read()
block=svc[svc.find('fun performStep'):]
block=block[:block.find('\n    }\n')+5] if '\n    }\n' in block else block
kotlin_types=set(re.findall(r'"([a-z_]+)"',block))
# فقط رسپی‌های بومی: گام‌های وب هرگز به performStep نمی‌رسند،
# بلکه در WebTaskRunner اجرا می‌شوند.
server_types={st['type'] for x in items if ((x['plan'] or {}).get('mode') or 'native')=='native'
              for st in (x['plan'] or {}).get('steps',[])}
# گام‌هایی که «عمداً» در performStep نیستند: یک لایه بالاتر، در
# ScreenTaskRunner، اجرا می‌شوند. confirm هیچ کنش دسترس‌پذیری ندارد — کارش
# متوقف کردن اجرا تا تأیید صریح سالمند است، و ورودش به performStep یعنی
# ساختن یک کنش جعلی که همیشه false می‌دهد.
# اما استثنا گذاشتن خطر دارد: اگر گامی نه در performStep باشد نه در
# اجراکننده، بی‌صدا حذف می‌شود. پس سنجش دوم همین را می‌بندد.
RUNNER_LEVEL_STEPS={'confirm'}
_rn2=open(os.path.join(KT,'ScreenTaskRunner.kt'),encoding='utf-8').read()
missing=server_types-kotlin_types-RUNNER_LEVEL_STEPS
check('هر نوع گام سرور در performStep پیاده شده',not missing,(missing,kotlin_types))
_dropped=[t for t in (server_types & RUNNER_LEVEL_STEPS) if '"%s"'%t not in _rn2]
check('گام‌های سطح اجراکننده واقعاً مدیریت می‌شوند (بی‌صدا حذف نمی‌شوند)',
      not _dropped, _dropped)
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
 'Throwable','Exception','NumberFormatException','IllegalArgumentException','IllegalStateException',
 # java.lang.* در Kotlin پیش‌فرض import می‌شود؛ نبودِ System در این فهرست
 # باعث شد System.currentTimeMillis() خطای کامپایل گزارش شود.
 'System','Math','Integer','StringBuilder','Thread','Runnable'}
# نوع‌های تودرتویی که از کلاس پایه به ارث می‌رسند و import نمی‌خواهند.
# TakeScreenshotCallback و ScreenshotResult داخل AccessibilityService تعریف
# شده‌اند؛ چون ScreenControlService از آن ارث می‌برد، بی‌قیدِ نام در دسترس‌اند.
_KT_INHERITED_NESTED={'TakeScreenshotCallback','ScreenshotResult','GestureDescription','StrokeDescription'}
_pkg_syms=set()
_kt_files=sorted(fn for fn in os.listdir(KT) if fn.endswith('.kt'))
for fn in _kt_files:
    _src=open(os.path.join(KT,fn),encoding='utf-8').read()
    # val/var سطح-فایل هم اضافه شد: ApprovedApps یک private val است و
    # بدون این، هم‌فایل بودنش دیده نمی‌شد و «بدون import» گزارش می‌شد.
    _pkg_syms|=set(re.findall(r'\b(?:class|object|interface|enum class|data class|sealed class|fun|val|var)\s+(\w+)',_src))
_unresolved=[]
for fn in _kt_files:
    _c=open(os.path.join(KT,fn),encoding='utf-8').read()
    # ترتیب مهم است: اول رشتهٔ خام ("""...""")، بعد رشتهٔ معمولی، بعد
    # کامنت. اگر کامنت اول بیاید، "https://" بقیهٔ خط را می‌خورد؛ اگر
    # رشتهٔ خام پوشش نداشته باشد، جاوااسکریپتِ داخلش کد Kotlin دیده می‌شود.
    _c=re.sub(r'""".*?"""','""',_c,flags=re.S)
    _c=re.sub(r'"(?:\\.|[^"\\])*"','""',_c)
    _c=re.sub(r'/\*.*?\*/','',_c,flags=re.S); _c=re.sub(r'//.*','',_c)
    _imp={i.split('.').pop().strip() for i in re.findall(r'^import\s+([\w.]+)',_c,re.M)}
    # (?<![\w.]) تا نمادِ وسطِ یک مسیرِ کاملاً واجد (مثل android.graphics.Typeface)
    # به اشتباه گزارش نشود — بدون آن سه مثبت کاذب داشتیم.
    for _m in re.finditer(r'(?<![\w.])([A-Z]\w+)\s*\.\s*[A-Za-z_]',_c):
        _s=_m.group(1)
        if _s in _KT_BUILTIN or _s in _imp or _s in _pkg_syms or _s in _KT_INHERITED_NESTED or _s.isupper(): continue
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
            'callCaregiver','saveVoiceProfile','setAssistantName','cancelScreenTask','bringAppToFront',
            'setNotificationsAllowed','setScreenVisionAllowed','captureScreenForVision',
            'dismissAllNotifications','dismissNotification','openNotification']
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
# تصمیم اخلاقی، «به‌روزشده» در مرحلهٔ ۲۴.
# در مرحلهٔ ۲۳ این سنجش می‌گفت takeScreenshot اصلاً استفاده نشود، چون روی
# API 30 هیچ اعلان/نمایشگری ندارد. در مرحلهٔ ۲۴ بینایی روی تصویر افزوده شد
# چون بدون آن اپ‌های فلاتر و canvas هیچ کمکی نمی‌گرفتند و readScreenText
# رشتهٔ خالی می‌داد. پس گارد از «حذف مطلق» به «قرارداد حریم» تبدیل شد:
# takeScreenshot مجاز است، اما فقط یک بار، فقط داخل captureForVision، و
# announceCapture باید «پیش از» آن بیاید. حذف این گارد یعنی بازگشت به
# تصویر گرفتن بی‌صدا از گوشی سالمند.
_ts9=[m.start() for m in re.finditer(r'takeScreenshot\(',_svc_code)]
_cvi9=_svc_code.find('fun captureForVision'); _cve9=_svc_code.find('fun announceCapture')
check('بخش۹ takeScreenshot تنها یک بار و داخل captureForVision است',
      len(_ts9)==1 and 0 < _cvi9 < _ts9[0] < _cve9, (_ts9,_cvi9,_cve9))
check('بخش۹ گرفتن تصویر بی‌صدا نیست: نشانگر «پیش از» takeScreenshot می‌آید',
      0 < _svc_code.find('announceCapture()',_cvi9) < _ts9[0], _svc_code.find('announceCapture()',_cvi9))
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

print('--- 10) پوشش کامل کنترل (مرحلهٔ ۲۳) ---')
# گام‌های کنش گره
NODE_STEPS=['focus','a11y_focus','next_node','prev_node','select_text','select_all',
            'copy','cut','paste','clear_text','append_text','expand','collapse',
            'set_progress','double_tap','pinch','drag']
_missing=[t for t in NODE_STEPS if '"%s"'%t not in svc]
check('بخش۱۰ همهٔ کنش‌های گره پیاده شده‌اند', not _missing, _missing)
for _act in ['ACTION_FOCUS','ACTION_ACCESSIBILITY_FOCUS','ACTION_NEXT_AT_MOVEMENT',
             'ACTION_PREVIOUS_AT_MOVEMENT','ACTION_SET_SELECTION','ACTION_COPY',
             'ACTION_CUT','ACTION_PASTE','ACTION_EXPAND','ACTION_COLLAPSE','ACTION_SET_PROGRESS']:
    check('بخش۱۰ %s استفاده می‌شود'%_act, _act in svc, '')
check('بخش۱۰ پارامترهای انتخاب متن درست ساخته می‌شوند',
      'ACTION_ARGUMENT_SELECTION_START_INT' in svc and 'ACTION_ARGUMENT_SELECTION_END_INT' in svc, '')
check('بخش۱۰ پارامتر لغزنده درست ساخته می‌شود',
      'ACTION_ARGUMENT_PROGRESS_VALUE_FLOAT' in svc, '')
check('بخش۱۰ نیشگون ژست «دو‌انگشتی» می‌سازد (دو StrokeDescription)',
      svc.count('addStroke(GestureDescription.StrokeDescription(p')>=2, svc.count('addStroke'))

# کنش‌های سراسری با نگهبان نسخه
GLOBAL_STEPS=['dismiss_notifications','split_screen','headset_hook','a11y_all_apps',
              'a11y_home','a11y_back','a11y_recents']
_missing=[t for t in GLOBAL_STEPS if '"%s"'%t not in svc]
check('بخش۱۰ کنش‌های سراسری تازه پیاده شده‌اند', not _missing, _missing)
check('بخش۱۰ split_screen/headset_hook/all_apps پشت نگهبان نسخه‌اند',
      'SDK_INT >= 24' in svc and 'SDK_INT >= 26' in svc and 'SDK_INT >= 31' in svc, '')

# خواندن صفحه
check('بخش۱۰ readScreenText پیاده شده', 'fun readScreenText()' in svc, '')
check('بخش۱۰ فقط گره‌های نمایان خوانده می‌شوند',
      'isVisibleToUser' in svc and 'collectText' in svc, '')
check('بخش۱۰ تکرارهای پیاپی حذف می‌شوند (وگرنه جمله دوبار خوانده می‌شد)',
      'dedupeConsecutive' in svc, '')
check('بخش۱۰ طول متن خوانده‌شده کران دارد', 'SCREEN_TEXT_MAX = 4000' in svc, '')
check('بخش۱۰ readScreenText از پل جاوااسکریپت در دسترس است',
      'fun readScreenText(): String' in main, '')

# سرویس اعلان‌ها
notif=open(os.path.join(KT,'NotificationService.kt'),encoding='utf-8').read()
check('بخش۱۰ NotificationService وجود دارد', 'class NotificationService : NotificationListenerService()' in notif, '')
check('بخش۱۰ در مانیفست با مجوز درست ثبت شده',
      'BIND_NOTIFICATION_LISTENER_SERVICE' in open(os.path.join(ROOT,'android','app','src','main','AndroidManifest.xml'),encoding='utf-8').read(), '')
check('بخش۱۰ دسترسی اعلان «پیش‌فرض خاموش» است',
      'getBoolean(PREF_KEY, false)' in notif, '')
# هر سه متد عمومی باید کلید را در زمان فراخوانی بسنجند، نه فقط onNotificationPosted
_nogate=[]
for _fn in ['fun snapshot()','fun dismiss(','fun open(','fun dismissAll()']:
    _i=notif.find(_fn)
    if _i<0: _nogate.append((_fn,'NOT FOUND')); continue
    if 'allowed(this)' not in notif[_i:_i+160]: _nogate.append((_fn,'no gate'))
check('بخش۱۰ هر چهار متد عمومی، رضایت را در زمان فراخوانی می‌سنجند', not _nogate, _nogate)
check('بخش۱۰ خطا فهرست «خالی» می‌دهد نه استثنا (از نخ پل صدا زده می‌شود)',
      notif.count('catch (e: Exception)')>=4, notif.count('catch (e: Exception)'))
check('بخش۱۰ متدهای اعلان روی پل گارد مبدأ دارند',
      main.count('if (!bridgeTrusted) return false')>=5 and 'fun getNotifications()' in main, '')

# برچسب overlay برای هر گام تازه
_nolabel=[t for t in NODE_STEPS+GLOBAL_STEPS if '"%s"'%t not in runner]
check('بخش۱۰ همهٔ گام‌های تازه برچسب فارسی overlay دارند', not _nolabel, _nolabel)

print('--- 11) یکسان‌سازی فارسی، رسپی‌های واقعی و بینایی صفحه (مرحلهٔ ۲۴) ---')
import unicodedata as _ud11
sel=open(os.path.join(KT,'SmartSelector.kt'),encoding='utf-8').read()
main=open(os.path.join(KT,'MainActivity.kt'),encoding='utf-8').read()
hnd=open(os.path.join(ROOT,'app','handler.py'),encoding='utf-8').read()
mem=open(os.path.join(ROOT,'app','memory.py'),encoding='utf-8').read()
web=open(os.path.join(ROOT,'index.html'),encoding='utf-8').read()

# ۱۱٫۱) پنج باگ یکسان‌سازی که واقعاً تطبیق را می‌شکستند
for _cp,_name in [('\u200C','نیم‌فاصله'),('\u0640','تطویل'),('\u0660','رقم عربی'),
                  ('\u06F0','رقم فارسی'),('\u0623','الف همزه‌دار'),('\u0624','واو همزه‌دار'),
                  ('\u06C0','نشانگر اضافه')]:
    check('بخش۱۱ normalize به %s (U+%04X) می‌رسد'%(_name,ord(_cp)),
          ('\\u%04X'%ord(_cp)) in sel, '\\u%04X'%ord(_cp))

# ۱۱٫۲) منطق normalize — پورت وفادار. این اجرای Kotlin نیست (JVM نداریم)؛
#        فقط منطق را می‌سنجد و باید کنار ./gradlew خوانده شود.
def _norm11(v):
    if not v: return ""
    out=[]
    for ch in v.lower():
        if ch in '\u200c\u200d\u0640\u06c0': continue
        elif ch=='\u064a': out.append('\u06cc')
        elif ch=='\u0643': out.append('\u06a9')
        elif ch=='\u0629': out.append('\u0647')
        elif ch in '\u0623\u0625': out.append('\u0627')
        elif ch=='\u0624': out.append('\u0648')
        elif '\u0660'<=ch<='\u0669': out.append(chr(ord('0')+(ord(ch)-0x0660)))
        elif '\u06f0'<=ch<='\u06f9': out.append(chr(ord('0')+(ord(ch)-0x06f0)))
        else: out.append(ch)
    t=re.sub('[\u064b-\u065f\u0670\u06d6-\u06ed]','',''.join(out))
    t=''.join(c if (_ud11.category(c)[0] in 'LN' or c==' ') else ' ' for c in t)
    return re.sub(r'\s+',' ',t).strip()
_POS11=[('می‌رود','میرود'),('تأیید','تاييد'),('۱۲۳۴','١٢٣٤'),('۱۲۳۴','1234'),
        ('تأیــید','تأیید'),('پیگیری','پيگيري'),('شركت','شرکت'),('شؤون','شوون'),
        ('حملهٔ','حملهۀ'),('حملهٔ','حمله'),('مدرسة','مدرسه'),('خانهٔ من','خانه من')]
_NEG11=[('آب','اب'),('مسئله','مسيله'),('شیر','شور')]
_badpos=[(a,b) for a,b in _POS11 if _norm11(a)!=_norm11(b)]
_badneg=[(a,b) for a,b in _NEG11 if _norm11(a)==_norm11(b)]
check('بخش۱۱ ۱۲ جفت هم‌معنی یکسان می‌شوند', not _badpos, _badpos)
check('بخش۱۱ آ و ئ مستقل می‌مانند (تطبیق کاذب ساخته نمی‌شود)', not _badneg, _badneg)

# ۱۱٫۳) باگ نام بسته: اسنپ‌فود با شناسهٔ جعلی هرگز باز نمی‌شد
check('بخش۱۱ شناسهٔ جعلی com.snappfood حذف شد', "'com.snappfood'" not in _dbsrc, 'com.snappfood')
# این‌ها شناسهٔ رسمی گوگل‌پلی‌اند (جست‌وجوی وب، ۲۰۲۶). هر نام بیرون از این
# فهرست یعنی حدس زده شده است.
REAL11={'com.zoodfood.android.play':'اسنپ‌فود','cab.snapp.passenger':'اسنپ',
        'com.android.chrome':'کروم','ir.mci.ecareapp':'همراه من',
        'com.sibche.aspardproject.app':'آپ'}
# شناسهٔ گوگل‌پلی فقط برای رسپی‌های «بومی» معنا دارد: مسیر وب هیچ بسته‌ای
# launch نمی‌کند، پس شناسهٔ web.* عمداً در REAL11 نیست.
_pkgs11=[x['package'] for x in items if ((x['plan'] or {}).get('mode') or 'native')=='native']
_webpkgs11=[x['package'] for x in items if (x['plan'] or {}).get('mode')=='web']
check('بخش۱۱ همهٔ بسته‌های رسپی شناسهٔ واقعی گوگل‌پلی دارند',
      all(pk in REAL11 for pk in _pkgs11), [pk for pk in _pkgs11 if pk not in REAL11])
# در عوض، رسپی وب باید سه چیز داشته باشد وگرنه موتور نمی‌تواند اجرایش کند.
_badweb=[x['package'] for x in items if (x['plan'] or {}).get('mode')=='web'
         and not str((x['plan'] or {}).get('url') or '').startswith('https://')]
check('بخش۱۱ هر رسپی وب نشانی https دارد', not _badweb, _badweb)
_nosel=[x['package'] for x in items if (x['plan'] or {}).get('mode')=='web'
        and 'selectors_verified' not in (x['plan'] or {})]
check('بخش۱۱ هر رسپی وب پرچم selectors_verified دارد', not _nosel, _nosel)
_premature=[x['package'] for x in items if (x['plan'] or {}).get('mode')=='web'
            and (x['plan'] or {}).get('selectors_verified')
            and any(not st.get('payload') for st in (x['plan'] or {}).get('steps',[])
                    if st['type'] in ('wait_css','click_css','set_css'))]
check('بخش۱۱ رسپی وب با سلکتور خالی نمی‌تواند verified باشد', not _premature, _premature)
check('بخش۱۱ همراه من و آپ افزوده شدند',
      {'ir.mci.ecareapp','com.sibche.aspardproject.app'} <= set(_pkgs11), _pkgs11)
check('بخش۱۱ هر رسپی نشانگر verified دارد',
      all('verified' in (x.get('plan') or {}) for x in items),
      [x['package'] for x in items if 'verified' not in (x.get('plan') or {})])

# ۱۱٫۴) قاعدهٔ ایمنی: هیچ رسپی‌ای نباید پرداخت را «انجام» دهد.
# تأیید مبلغ کار سالمند است، نه اتوماسیون. این هم با سیاست Google Play
# سازگار است (agent مختار ممنوع) هم با اصل محصول.
PAY11=['پرداخت','تأیید پرداخت','خرید نهایی','ثبت سفارش','تأیید و پرداخت','pay now','confirm payment']
_pay=[(x['package'],st.get('payload')) for x in items
      for st in (x['plan'] or {}).get('steps',[])
      if str(st.get('payload') or '').strip() in PAY11]
check('بخش۱۱ هیچ رسپی‌ای گام پرداخت ندارد', not _pay, _pay)

# ۱۱٫۵) بینایی صفحه: سه قید حریم
_cv=svc[svc.find('fun captureForVision'):]
_cv=_cv[:_cv.find('\n    }\n')+5] if '\n    }\n' in _cv else _cv
check('بخش۱۱ captureForVision پیاده شده', 'fun captureForVision(): String' in svc, '')
check('بخش۱۱ رضایت اولین سطر است (پیش از هر کاری سنجیده می‌شود)',
      _cv.strip().splitlines()[1].strip().startswith('if (!visionAllowed'), _cv.strip().splitlines()[1:3])
check('بخش۱۱ کلید بینایی پیش‌فرض خاموش است',
      'getBoolean(PREF_VISION, false)' in svc, 'getBoolean(PREF_VISION')
# takeScreenshot روی API 30 بی‌صداست؛ اگر خودمان نشانگر نگذاریم سالمند هرگز
# نمی‌فهمد از صفحه‌اش تصویر گرفته شده.
_ann=svc.find('private fun announceCapture')
_cap=svc.find('fun captureForVision')
check('بخش۱۱ پیش از گرفتن تصویر نشانگر بصری نمایش داده می‌شود',
      0 < _ann < svc.find('announceCapture()', _cap) or svc.find('announceCapture()', _cap) < svc.find('takeScreenshot(', _cap),
      (_cap,_ann))
check('بخش۱۱ نشانگر از OverlayController می‌آید نه toast گذرا',
      'OverlayController.show' in svc[_ann:_ann+400], '')
# روی متن بی‌کامنت: KDoc همین تابع توضیح می‌دهد چرا به MediaProjection
# «نمی‌افتیم»، و آن توضیح بدون حذف کامنت به‌شکل استفاده خوانده می‌شد.
check('بخش۱۱ زیر API 30 بی‌صدا خالی می‌دهد (MediaProjection جایگزین نمی‌شود)',
      'Build.VERSION.SDK_INT < 30' in _cv and 'MediaProjection' not in _svc_code, 'MediaProjection')
check('بخش۱۱ هیچ تصویری روی دیسک نوشته نمی‌شود',
      not re.search(r'FileOutputStream|openFileOutput|MediaStore', svc), 'FileOutputStream')
check('بخش۱۱ خطا استثنا نمی‌دهد بلکه رشتهٔ خالی می‌دهد (نخ پل جاوااسکریپت)',
      _cv.count('return ""') >= 3, _cv.count('return ""'))

# ۱۱٫۶) پل: سه متد تازه، همه پشت bridgeTrusted
for _m in ('screenVisionAllowed','setScreenVisionAllowed','captureScreenForVision'):
    _i=main.find('fun '+_m)
    _b=main[_i:_i+260]
    check('بخش۱۱ پل %s پشت bridgeTrusted است'%_m,
          _i>0 and ('bridgeTrusted' in _b or _m=='screenVisionAllowed'), _b[:80])
# readScreenText هم خواندنی است؛ اجازهٔ «خواندن» نباید خودِ «نوشتن» پرچم باشد.
check('بخش۱۱ خواندن پرچم bridgeTrusted نمی‌خواهد ولی نوشتنش می‌خواهد',
      'fun setScreenVisionAllowed(on: Boolean) {\n            if (!bridgeTrusted) return' in main, '')

# ۱۱٫۷) سمت سرور: سه قید مستقل
check('بخش۱۱ endpoint /api/screen/vision وجود دارد', "p=='/api/screen/vision'" in hnd, '')
_ep=hnd[hnd.find("p=='/api/screen/vision'"):]
_ep=_ep[:_ep.find("p=='/api/screen-tasks'")]
check('بخش۱۱ رضایت screen_vision سمت سرور سنجیده می‌شود', "consent_granted(c,'screen_vision')" in _ep, '')
check('بخش۱۱ اندازهٔ تصویر کران جدا از MAX_BODY_BYTES دارد', 'VISION_MAX_B64' in _ep and 'VISION_MAX_B64 = ' in hnd, '')
check('بخش۱۱ محدودیت نرخ دارد', 'vision_rate_ok' in _ep, '')
check('بخش۱۱ رویداد ثبت‌شده «بی‌محتوا» است (خودِ تصویر ذخیره نمی‌شود)',
      "'screen_vision_read'" in _ep and 'img' not in _ep.split("'screen_vision_read'")[1].split(')')[0], '')
check('بخش۱۱ حافظهٔ مکالمه به درخواست بینایی تزریق نمی‌شود',
      'memory_block' not in mem[mem.find('def call_llm_vision'):], 'memory_block')

# ۱۱٫۸) رابط کاربری: درخت گره «اول»، بینایی فقط وقتی خالی بود
check('بخش۱۱ دکمهٔ «صفحه را برایم بخوان» روی پنل خانه هست',
      'onclick="readScreenAloud()"' in web, '')
_rs=web[web.find('async function readScreenAloud'):]
_rs=_rs[:_rs.find('\n}\n')+3]
check('بخش۱۱ ابتدا درخت گره خوانده می‌شود', _rs.find('readScreenText()') < _rs.find('captureScreenForVision()'), '')
check('بخش۱۱ بینایی فقط در شاخهٔ «درخت خالی بود» است',
      'if(!text){' in _rs and _rs.find('if(!text){') < _rs.find('captureScreenForVision()'), '')
check('بخش۱۱ بینایی پشت رضایت صریح است', "localStorage.getItem('screenVision')!=='1'" in _rs, '')
# پنجرهٔ ثابت ۱۶۰۰ نویسه‌ای تا داخل applySettings می‌رفت که خودش innerHTML
# دارد؛ مثبت کاذب. بدنهٔ تابع با اولین «\nfunction » بعدی بسته می‌شود.
_ni=web.find('function readNotificationsAloud'); _ne=web.find('\nfunction ',_ni+10)
_rn=web[_ni:_ne if _ne>0 else _ni+2000]
# سنجش ساختاری «نبودِ» یک نماد باید روی متن بی‌کامنت اجرا شود. کامنتِ همین
# تابع توضیح می‌دهد چرا innerHTML استفاده «نمی‌شود» — دقیقاً همان دامی که در
# مرحلهٔ ۲۳ با takeScreenshot خوردیم. خطوطی که با // شروع می‌شوند حذف
# می‌شوند؛ نه همهٔ // ها، چون '//' داخل رشتهٔ نشانی وب معنای دیگری دارد.
_rnc='\n'.join(l for l in _rn.split('\n') if not l.strip().startswith('//'))
check('بخش۱۱ متن اعلان با textContent نوشته می‌شود نه innerHTML (XSS)',
      'tr.textContent=' in _rnc and 'innerHTML' not in _rnc, _rnc[-160:])
check('بخش۱۱ تابع خواندن اعلان واقعاً بسته شده (پنجره خالی نیست)',
      len(_rnc)>400, len(_rnc))

# ۱۱٫۹) نامتغیر بین‌لایه‌ای: هر بسته‌ای که سمت سرور seed می‌شود باید در
# فهرست مجاز Kotlin هم باشد. این دقیقاً باگی است که در مرحلهٔ ۲۴ پیدا شد:
# شناسهٔ اسنپ‌فود در database.py اصلاح شد ولی ApprovedApps در MainActivity.kt
# همان شناسهٔ غلط را داشت؛ پس رسپی ثبت می‌شد و launchApprovedPackage همیشه
# false می‌داد. اصلاحی که فقط یک لایه را بگیرد، اصلاح نیست.
# تا «) در ابتدای خط». نسخهٔ نخست (.*?)\) بود و در اولین ) داخل «کامنت»
# همان فهرست می‌ایستاد — کامنتم «(۲۰۲۶)» داشت — پس مجموعه خالی درآمد و هر
# پنج بسته بی‌دلیل «غیرمجاز» گزارش شدند. کامنت نباید بتواند یک سنجش را
# بشکند؛ این همان دامی است که با takeScreenshot و innerHTML هم خوردیم.
_allow=re.search(r'private val ApprovedApps = setOf\(([\s\S]*?)\n\)', main)
check('بخش۱۱ فهرست مجاز ApprovedApps پیدا می‌شود', bool(_allow), '')
_allowset=set(re.findall(r'"([\w.]+)"', _allow.group(1))) if _allow else set()
# سنجش تهی: اگر استخراج مجموعه خالی بدهد، سنجش بعدی همه را «غیرمجاز» می‌گوید
# و باگ واقعی پنهان می‌شود. پس خالی بودن خودش یک شکست جداست.
check('بخش۱۱ فهرست مجاز خالی استخراج نشد (سنجش تهی نیست)', len(_allowset)>=5, sorted(_allowset))
check('بخش۱۱ شناسهٔ جعلی com.snappfood از فهرست مجاز Kotlin هم رفته',
      'com.snappfood' not in _allowset, _allowset)
_notallow=[x['package'] for x in items if ((x['plan'] or {}).get('mode') or 'native')=='native'
           and x['package'] not in _allowset]
check('بخش۱۱ هر بستهٔ سرور در فهرست مجاز Kotlin هم هست (وگرنه رسپی هرگز اجرا نمی‌شود)',
      not _notallow, _notallow)
# سنجش مثبت: شناسهٔ وب هرگز نباید وارد ApprovedApps شود. اگر روزی شد،
# یعنی کسی فرض کرده مسیر وب هم بسته launch می‌کند — و آن فرض غلط است.
_leaked=[pk for pk in _webpkgs11 if pk in _allowset]
check('بخش۱۱ شناسهٔ وب به فهرست مجاز Kotlin نشت نکرده', not _leaked, _leaked)

# ۱۱٫۱۰) توازن کروشه/پرانتز روی همهٔ فایل‌ها با strip_kotlin.
# نکته: پاره‌کنندهٔ سادهٔ «اول کامنت، بعد رشته» روی MainActivity مثبت کاذب
# ۱۳/۱۰ می‌داد، چون رشتهٔ "https://" را کامنت می‌دید و بقیهٔ خط — از جمله
# یک «{» — را می‌خورد. strip_kotlin توکنایزر است و این دام را ندارد.
_unbal=[]
for _fn in sorted(f for f in os.listdir(KT) if f.endswith('.kt')):
    _k=strip_kotlin(open(os.path.join(KT,_fn),encoding='utf-8').read())
    if _k.count('{')!=_k.count('}') or _k.count('(')!=_k.count(')'):
        _unbal.append((_fn,_k.count('{'),_k.count('}'),_k.count('('),_k.count(')')))
check('بخش۱۱ کروشه و پرانتز همهٔ فایل‌های Kotlin متوازن است', not _unbal, _unbal)

print('--- 12) هیچ تعهدی بدون تأیید صریح سالمند ثبت نمی‌شود ---')
# باگ امنیتی واقعی که در امکان‌سنجی مرحلهٔ ۲۴ پیدا شد: رسپی اسنپ روی
# «درخواست خودرو» بدون expect و بدون تأیید ضربه می‌زد و یک سفر «واقعی»
# ثبت می‌شد. گام confirm اضافه شد و این بخش نامتغیر آن را پاس می‌دارد.

# برچسب‌هایی که یک تعهد واقعی/مالی ثبت می‌کنند. اگر رسپی روی یکی از این‌ها
# ضربه بزند، باید پیش از آن یک گام confirm آمده باشد.
COMMIT12=['درخواست خودرو','ثبت سفارش','پرداخت','تأیید نهایی','ارسال سفارش',
          'خرید','ثبت و پرداخت','place order','confirm order','pay now','checkout']
_types12=[]
for _x in items:
    _seq=[st for st in (_x['plan'] or {}).get('steps',[])]
    _seen_confirm=False
    for _st in _seq:
        if _st['type']=='confirm': _seen_confirm=True; continue
        if _st['type']=='tap_text' and str(_st.get('payload') or '').strip() in COMMIT12:
            if not _seen_confirm: _types12.append((_x['package'],_st['payload']))
check('بخش۱۲ هیچ ضربهٔ تعهدآوری بدون confirm پیشین نیست', not _types12, _types12)
check('بخش۱۲ گام confirm در رسپی‌های تعهدآور وجود دارد',
      any(st['type']=='confirm' for x in items for st in (x['plan'] or {}).get('steps',[])), '')

# confirm باید در اجراکننده پیاده شده باشد، وگرنه بی‌صدا رد می‌شود و
# «تأیید» هیچ اثری ندارد — همان باگی که در مرحلهٔ ۲۲ برای ime_enter داشتیم.
_rn12=open(os.path.join(KT,'ScreenTaskRunner.kt'),encoding='utf-8').read()
check('بخش۱۲ confirm در اجراکننده پیاده شده',
      'step.type == "confirm"' in _rn12 and 'fun askConfirm' in _rn12, '')
# گام confirm نباید از attempt() رد شود: performStep برای آن کاری ندارد و
# ورود به حلقهٔ تلاش فقط تایم‌اوت بی‌مصرف می‌سازد.
_rs12=_rn12[_rn12.find('private fun runStep'):_rn12.find('private fun attempt')]
check('بخش۱۲ confirm پیش از attempt() برمی‌گردد (حلقهٔ تلاش بی‌مصرف نمی‌سازد)',
      0 < _rs12.find('"confirm"') < _rs12.find('attempt(step'), (_rs12.find('"confirm"'), _rs12.find('attempt(step')))
check('بخش۱۲ برچسب فارسی overlay برای confirm هست', '"confirm" ->' in _rn12, '')

# کارت تأیید: سه قید حریم/ایمنی
_oc12=open(os.path.join(KT,'OverlayController.kt'),encoding='utf-8').read()
_sc12=_oc12[_oc12.find('fun showConfirm'):]
check('بخش۱۲ کارت تأیید دو دکمه دارد (نه فقط «باشه»)',
      _sc12.count('setOnClickListener')==2, _sc12.count('setOnClickListener'))
# پیش‌فرض باید «نه» باشد: تایم‌اوت، نبودِ اجازهٔ overlay و هر استثنا ⇒ false.
check('بخش۱۲ پیش‌فرض «نه» است (تایم‌اوت و استثنا ⇒ رد)',
      _sc12.count('onDone(false)')>=3 and 'onDone(true)' in _sc12,
      (_sc12.count('onDone(false)'), _sc12.count('onDone(true)')))
# تایم‌اوت و لمس مسابقه می‌دهند؛ بدون محافظ، گام اجراکننده دو بار ادامه می‌داد.
# نسخهٔ نخست فقط «رشته وجود دارد» را می‌سنجید و پروب تهی‌نبودن لو داد که
# ضعیف است: دو تا از سه occurrences محافظ را عوض کردم و سنجش همچنان سبز
# ماند. حالا «شمارش» می‌کنیم. سه مسیر با هم مسابقه می‌دهند: تایم‌اوت،
# لمس «بله»، و استثنا. پس هر سه باید compareAndSet داشته باشند.
# (فراخوانی چهارم onDone در مسیر «اجازهٔ overlay نیست» عمداً بی‌محافظ است:
#  پیش از ثبت هر شنونده‌ای برمی‌گردد، پس چیزی برای مسابقه وجود ندارد.)
_n12=_sc12.count('compareAndSet(false, true)')
check('بخش۱۲ هر سه مسیرِ رقیب با compareAndSet محافظت شده‌اند',
      _n12>=3, _n12)
check('بخش۱۲ محافظ از AtomicBoolean است نه Boolean معمولی (مسابقهٔ نخ)',
      'AtomicBoolean' in _sc12, '')
check('بخش۱۲ دکمه‌های تأیید از کف ۴۸dp پروژه بزرگ‌ترند',
      'dp(56)' in _sc12, '')
check('بخش۱۲ hide() کارت تأیید را هم می‌بندد (کارت یتیم نمی‌ماند)',
      'dismissConfirm()' in _oc12[:_oc12.find('fun showConfirm')] or
      _oc12.count('dismissConfirm()')>=3, _oc12.count('dismissConfirm()'))

# قالب‌بندی پارامتر
_st12=open(os.path.join(KT,'ScreenTask.kt'),encoding='utf-8').read()
check('بخش۱۲ قالب {{نام}} در payload جای‌گذاری می‌شود',
      'PARAM_RE' in _st12 and 'payload = fill(' in _st12, '')
check('بخش۱۲ expect هم قالب‌گذاری می‌شود (نه فقط payload)', 'expect = fill(' in _st12, '')
check('بخش۱۲ پارامتر گم‌شده کار را رد می‌کند نه اینکه قالب خام اجرا شود',
      'missing.isNotEmpty()) null' in _st12, '')
check('بخش۱۲ requiredParams برای پرسیدن از سالمند در دسترس است',
      'fun requiredParams(' in _st12, '')
check('بخش۱۲ رسپی اسنپ مقصد ثابت ندارد',
      'خیابان ولیعصر' not in _dbsrc and '{{destination}}' in _dbsrc, '')
check('بخش۱۲ رسپی اسنپ‌فود کالای ثابت ندارد',
      'شیر کم‌چرب' not in _dbsrc and '{{item}}' in _dbsrc, '')

print('--- 13) مسیر وب: نسخهٔ وب سرویس‌ها داخل WebView ---')
_wt=open(os.path.join(KT,'WebTaskRunner.kt'),encoding='utf-8').read()

# ۱۳٫۱) پایهٔ حقوقی کل این مسیر: هیچ استفاده‌ای از AccessibilityService.
# اگر روزی این API وارد WebTaskRunner شود، بهانهٔ «مشمول سیاست Play
# نیستیم» از بین می‌رود و کل مسیر بیهوده می‌شود.
_A11Y13=['AccessibilityService','AccessibilityNodeInfo','dispatchGesture',
         'GestureDescription','performGlobalAction','takeScreenshot']
_used13=[k for k in _A11Y13 if k in _wt]
check('بخش۱۳ WebTaskRunner هیچ API دسترس‌پذیری استفاده نمی‌کند', not _used13, _used13)
check('بخش۱۳ فقط evaluateJavascript است نه loadUrl("javascript:")',
      'evaluateJavascript' in _wt and 'javascript:' not in _wt, '')

# ۱۳٫۲) هر نوع گام وب باید هم اسکریپت داشته باشد هم برچسب فارسی.
# گام بی‌اسکریپت یعنی else -> "false" ⇒ تا timeout تلاش و بعد شکست.
_script13=_wt[_wt.find('private fun scriptFor'):]
_script13=_script13[:_script13.find('\n    }\n')+6]
_label13=_wt[_wt.find('private fun labelFor'):]
_label13=_label13[:_label13.find('\n    }\n')+6]
# confirm و wait_ms و goto عمداً بیرون از scriptFor هستند: هیچ‌کدام با
# evaluateJavascript انجام نمی‌شوند و در runStep مدیریت می‌شوند. اما این
# استثنا باید «سنجیده» شود، وگرنه یک گامِ فراموش‌شده بی‌صدا تا timeout
# شکست می‌خورد — دقیقاً همان باگی که برای goto داشتیم.
_rs13=_wt[_wt.find('private fun runStep'):_wt.find('private fun attempt')]
_handled13={'confirm','wait_ms','goto'}
_nohandled=[t for t in sorted(_handled13) if 'step.type == "%s"'%t not in _rs13]
check('بخش۱۳ گام‌های بی‌اسکریپت در runStep مدیریت می‌شوند', not _nohandled, _nohandled)
# حلقهٔ بی‌پایان: onPageFinished خودش runStep را صدا می‌زند، پس goto باید
# index را «پیش از» loadUrl جلو ببرد.
# بلوک کامل goto، نه تا اولین return: اولین return داخل گارد «نشانی خالی»
# است و «پیش از» loadUrl می‌آید، پس برش روی آن، loadUrl را از پنجره بیرون
# می‌انداخت و سنجش (22, -1) می‌داد. کرانهٔ درست، فراخوانی attempt است که
# بعد از بلوک goto می‌آید.
_gotoseg=_rs13[_rs13.find('"goto"'):]
_end13=_gotoseg.find('attempt(wv, step')
_gotoseg=_gotoseg[:_end13] if _end13 > 0 else _gotoseg
check('بخش۱۳ پنجرهٔ بلوک goto تهی استخراج نشد (سنجش تهی نیست)',
      'loadUrl' in _gotoseg and 'index += 1' in _gotoseg, len(_gotoseg))
check('بخش۱۳ goto پیش از loadUrl جلو می‌رود (حلقهٔ بی‌پایان نمی‌سازد)',
      0 <= _gotoseg.find('index += 1') < _gotoseg.find('loadUrl'),
      (_gotoseg.find('index += 1'), _gotoseg.find('loadUrl')))
check('بخش۱۳ goto با نشانی خالی شکست صریح می‌دهد نه loadUrl("")',
      'target.isBlank()' in _gotoseg, '')
_noscript=[t for t in sorted(WEB_STEP_TYPES-_handled13) if '"%s"'%t not in _script13]
check('بخش۱۳ هر گام وب اسکریپت دارد', not _noscript, _noscript)
_nolabel=[t for t in sorted(WEB_STEP_TYPES) if '"%s"'%t not in _label13]
check('بخش۱۳ هر گام وب برچسب فارسی overlay دارد', not _nolabel, _nolabel)

# ۱۳٫۳) تزریق: سلکتور و مقدار از رسپی می‌آیند. یک ' ساده باید اسکریپت را
# بشکند؛ JSONObject.quote هر دو را یک‌جا می‌بندد.
check('بخش۱۳ سلکتور/مقدار با JSONObject.quote نقل‌قول می‌شوند',
      'JSONObject.quote' in _wt and _script13.count('${q(')>=3, _script13.count('${q('))

# ۱۳٫۴) دام React: انتساب مستقیم e.value فرم را به‌روز نمی‌کند. باید setter
# بومی prototype صدا زده شود و رویداد input با bubbles:true برود.
check('بخش۱۳ setter بومی prototype برای ورودی React استفاده می‌شود',
      'getOwnPropertyDescriptor(proto' in _wt and 'd.set.call(e,v)' in _wt, '')
check('بخش۱۳ رویداد input با bubbles فرستاده می‌شود',
      "dispatchEvent(new Event('input',{bubbles:true}))" in _wt, '')

# ۱۳٫۵) دروازهٔ صداقت: بدون نگاشت سلکتور، اصلاً اجرا نمی‌شود.
check('بخش۱۳ بدون selectors_verified اجرا نمی‌کند',
      'if (!parsed.selectorsVerified)' in _wt and '"not_mapped"' in _wt, '')
check('بخش۱۳ گام probe برای نگاشت سلکتور روی دستگاه هست',
      '"probe"' in _wt and 'SEPANDYAR_PROBE' in _wt, '')

# ۱۳٫۶) تأیید صریح در مسیر وب هم الزامی است (همان قاعدهٔ بخش۱۲).
check('بخش۱۳ مسیر وب هم از کارت تأیید استفاده می‌کند',
      'OverlayController.showConfirm' in _wt, '')
check('بخش۱۳ لغو، اجرای در جریان را متوقف می‌کند',
      'fun cancel()' in _wt and 'cancelled = true' in _wt, '')
check('بخش۱۳ پس از پایان، سالمند روی صفحهٔ سرویس رها نمی‌شود',
      'HOME_URL' in _wt and 'loadUrl(HOME_URL)' in _wt, '')
check('بخش۱۳ هلپر DOM پس از هر ناوبری دوباره تزریق می‌شود',
      'onPageFinished' in _wt and 'evaluateJavascript(HELPERS' in _wt, '')

# ۱۳٫۷) متدهای پل باید گارد مبدأ داشته باشند: addJavascriptInterface با هر
# ناوبری باقی می‌ماند و صفحهٔ اسنپ هم می‌تواند SepandyarNative را صدا بزند.
for _m13 in ('runWebTask','cancelWebTask'):
    _i13=main.find('@JavascriptInterface fun %s'%_m13)
    _seg13=main[_i13:_i13+240] if _i13>=0 else ''
    check('بخش۱۳ %s گارد bridgeTrusted دارد'%_m13, 'bridgeTrusted' in _seg13, _seg13[:90])
check('بخش۱۳ runWebTask بدون WebView مقداردهی‌نشده اجرا نمی‌شود',
      '::web.isInitialized' in main[main.find('fun runWebTask'):main.find('fun runWebTask')+300], '')

# ۱۳٫۸) رابط وب: مسیریابی، لغو، و پیام «آماده نیست»
check('بخش۱۳ رابط بر اساس mode رسپی مسیر را انتخاب می‌کند',
      "_mode==='web'" in web and 'runWebTask' in web, '')
check('بخش۱۳ دکمهٔ لغو به cancelWebTask می‌رود وقتی کار وب است',
      'cancelWebTask' in web and 'screenRunState.web' in web, '')
check('بخش۱۳ وضعیت not_mapped پیام riêng دارد (نه «شکست» مبهم)',
      "res.status==='not_mapped'" in web, '')
check('بخش۱۳ resپی وب url و selectors_verified را به موتور می‌فرستد',
      'plan.url=' in web and 'plan.selectors_verified=' in web, '')
check('بخش۱۳ دارایی اندروید با رابط وب همگام است',
      open(os.path.join(AND,'app/src/main/assets/index.html'),encoding='utf-8').read()==web, '')

print('--- 14) لایهٔ ۳: App Actions / built-in intents ---')
import xml.etree.ElementTree as ET
_sc14p=os.path.join(AND,'app/src/main/res/xml/shortcuts.xml')
check('بخش۱۴ shortcuts.xml وجود دارد', os.path.exists(_sc14p), _sc14p)
_sc14=ET.parse(_sc14p).getroot()
_A='{http://schemas.android.com/apk/res/android}'
_caps14=[e.get(_A+'name') for e in _sc14.findall('capability')]
_sh14=[e.get(_A+'shortcutId') for e in _sc14.findall('shortcut')]

# ۱۴٫۱) نام BII باید از فهرست راستی‌آزمایی‌شده باشد.
# ساختن نامِ جعلی دقیقاً همان باگی است که در رسپی اسنپ خوردیم: build سبز
# می‌ماند، Assistant هیچ‌وقت تطبیق نمی‌دهد، و قابلیت بی‌صدا مرده است.
BII14={'actions.intent.OPEN_APP_FEATURE','actions.intent.GET_THING',
       'actions.intent.GET_HEALTH_STATS','actions.intent.RECORD_HEALTH_OBSERVATION',
       'actions.intent.CREATE_TAXI_RESERVATION','actions.intent.ORDER_MENU_ITEM',
       'actions.intent.CREATE_CALL','actions.intent.GET_FOOD_OBSERVATION'}
_badbii=[c for c in _caps14 if c not in BII14]
check('بخش۱۴ همهٔ capabilityها BII راستی‌آزمایی‌شده‌اند', not _badbii, _badbii)
check('بخش۱۴ سنجش تهی نیست: حداقل ۵ capability اعلام شد', len(_caps14)>=5, _caps14)
check('بخش۱۴ GET_THING هست (برای اپ دارای جست‌وجو الزامی است)',
      'actions.intent.GET_THING' in _caps14, _caps14)

# ۱۴٫۲) نام پارامترِ برگ هم باید راستی‌آزمایی‌شده باشد.
# این مهم‌ترین گارد این بخش است: CREATE_TAXI_RESERVATION عمداً «بدون»
# <parameter> اعلام شده چون نام برگش را از bii-index تأیید نکردم. اگر روزی
# کسی نامی حدس بزند، این سنجش می‌گیردش.
PARAM14={'feature','thing.name','menuItem.name'}
_params14=[pr.get(_A+'name') for c in _sc14.findall('capability')
           for i in c.findall('intent') for pr in i.findall('parameter')]
_badpar=[x for x in _params14 if x not in PARAM14]
check('بخش۱۴ هیچ نام پارامتر حدس‌زده‌ای اعلام نشده', not _badpar, _badpar)
check('بخش۱۴ سنجش تهی نیست: دست‌کم یک پارامتر راستی‌آزمایی‌شده هست',
      len(_params14)>=1, _params14)

# ۱۴٫۳) سند رسمی: هر capability باید یک fallback بدون پارامتر لازم داشته
# باشد، وگرنه پرسش‌های مبهم شکست می‌خورند. برای سالمند حیاتی است.
_nofb=[c.get(_A+'name') for c in _sc14.findall('capability')
       if not any(not i.findall('parameter') for i in c.findall('intent'))]
check('بخش۱۴ هر capability یک intent بدون پارامتر لازم دارد', not _nofb, _nofb)

# ۱۴٫۴) registration: بدون meta-data، Assistant فایل را هرگز نمی‌بیند.
_mf14=open(os.path.join(AND,'app/src/main/AndroidManifest.xml'),encoding='utf-8').read()
check('بخش۱۴ shortcuts.xml در manifest ثبت شده',
      'android.app.shortcuts' in _mf14 and '@xml/shortcuts' in _mf14, '')
# singleTop لازم است وگرنه onNewIntent هرگز نمی‌آید و قابلیت فقط وقتی اپ
# بسته است کار می‌کند.
check('بخش۱۴ MainActivity singleTop است (تا onNewIntent برسد)',
      'android:launchMode="singleTop"' in _mf14, '')
check('بخش۱۴ وابستگی androidx.core هست (پیش‌نیاز رسمی shortcuts.xml)',
      'androidx.core:core:' in open(os.path.join(AND,'app/build.gradle.kts'),encoding='utf-8').read(), '')

# ۱۴٫۵) قرارداد کلید Extra باید در هر دو سمت یکی باشد. این همان باگی است
# که در مرحلهٔ ۲۵ برای بسته‌ها داشتیم: یک لایه درست، لایهٔ دیگر کهنه.
_keys14=sorted({e.get(_A+'name') for c in _sc14.iter() for e in c.findall('extra') if e.get(_A+'name')})
_pkeys14=sorted({pr.get(_A+'key') for c in _sc14.iter() for pr in c.findall('parameter') if pr.get(_A+'key')})
_all14=set(_keys14)|set(_pkeys14)
_missing14=[k for k in _all14 if '"%s"'%k not in main]
check('بخش۱۴ هر کلید Extra در MainActivity هم خوانده می‌شود', not _missing14, _missing14)
check('بخش۱۴ سنجش تهی نیست: دست‌کم ۲ کلید Extra استخراج شد', len(_all14)>=2, sorted(_all14))

# ۱۴٫۶) capability-binding باید به capability اعلام‌شده اشاره کند
_badbind=[b.get(_A+'key') for sc in _sc14.findall('shortcut')
          for b in sc.findall('capability-binding') if b.get(_A+'key') not in _caps14]
check('بخش۱۴ هر capability-binding به capability موجود اشاره می‌کند', not _badbind, _badbind)
# parameter-binding باید پارامتری باشد که آن capability واقعاً اعلام کرده
_cap_par14={c.get(_A+'name'):{pr.get(_A+'name') for i in c.findall('intent')
            for pr in i.findall('parameter')} for c in _sc14.findall('capability')}
_badpb=[(sc.get(_A+'shortcutId'),b.get(_A+'key'),pb.get(_A+'key'))
        for sc in _sc14.findall('shortcut') for b in sc.findall('capability-binding')
        for pb in sc.findall('parameter-binding')
        if pb.get(_A+'key') not in _cap_par14.get(b.get(_A+'key'),set())]
check('بخش۱۴ هر parameter-binding پارامترِ واقعیِ همان capability است', not _badpb, _badpb)
_labels14=[sc.get(_A+'shortcutShortLabel') for sc in _sc14.findall('shortcut')]
check('بخش۱۴ برچسب میان‌برها منبع رشته‌اند نه متن خام',
      all(l and l.startswith('@string/') for l in _labels14), _labels14)
_str14=open(os.path.join(AND,'app/src/main/res/values/strings.xml'),encoding='utf-8').read()
_missingstr=[l.split('/')[-1] for l in _labels14 if ('name="%s"'%l.split('/')[-1]) not in _str14]
check('بخش۱۴ همهٔ رشته‌های برچسب تعریف شده‌اند', not _missingstr, _missingstr)

# ۱۴٫۷) سمت رابط وب
check('بخش۱۴ onAppAction در رابط وب هست', 'window.onAppAction' in web, '')
check('بخش۱۴ onAppAction ناشناخته را بی‌صدا نمی‌بلعد',
      'پیدا نکردم' in web[web.find('window.onAppAction'):web.find('window.onAppAction')+1800], '')
check('بخش۱۴ MainActivity intent را به onAppAction می‌فرستد',
      'window.onAppAction' in main and 'fun consumeAppAction' in main, '')
check('بخش۱۴ onNewIntent پیاده شده', 'override fun onNewIntent' in main, '')
check('بخش۱۴ هیچ خراشیدن UI در مسیر App Actions نیست',
      'AccessibilityService' not in main[main.find('fun consumeAppAction'):main.find('fun consumeAppAction')+1200], '')
check('بخش۱۴ دارایی اندروید با onAppAction همگام است',
      open(os.path.join(AND,'app/src/main/assets/index.html'),encoding='utf-8').read()==web, '')

print('--- 15) لایهٔ ۱: AppFunctions ---')
_af15p=os.path.join(KT,'appfunctions','SepandyarAppFunctions.kt')
check('بخش۱۵ فایل AppFunctions وجود دارد', os.path.exists(_af15p), _af15p)
_af15=open(_af15p,encoding='utf-8').read()
# سنجش‌های ساختاری روی نسخهٔ «بی‌کامنت و بی‌رشته». شش سنجش نخست این بخش
# با شمارش خام نوشته شده بودند و KDocهای توضیحیِ خودم آن‌ها را واژگون کرد
# (مثلاً عبارت «@AppFunctionDeclaration» داخل توضیحات، تعداد annotationها را
# ۹ به ۱۱ رساند). همان دمی که در §۱۱٫۹ و §۹ هم خورده بودیم.
_af15c=strip_kotlin(_af15)
def _fnbody15(name, src):
    i=src.find('suspend fun %s('%name)
    if i<0: return ''
    j=src.find('{',i); d=0
    for k in range(j,len(src)):
        if src[k]=='{': d+=1
        elif src[k]=='}':
            d-=1
            if d==0: return src[i:k+1]
    return src[i:]

# ۱۵٫۱) دام alpha13: @AppFunction قدیمی «کامپایل می‌شود» ولی KSP بی‌صدا
# XML خالی می‌سازد. بدترین نوع شکست — build سبز، صفر تابع.
check('بخش۱۵ از @AppFunctionDeclaration استفاده می‌شود نه @AppFunction قدیمی',
      '@AppFunctionDeclaration' in _af15 and '@AppFunction(' not in _af15, '')
# ۱۵٫۲) دام beta01: isDescribedByKDoc مقدار پیش‌فرض ندارد.
_nd15=_af15c.count('@AppFunctionDeclaration')+_af15c.count('@AppFunctionSerializable')
_kdoc15=len(re.findall(r'isDescribedByKDoc\s*=\s*true',_af15c))
check('بخش۱۵ هر declaration و serializable صریحاً isDescribedByKDoc=true دارد',
      _kdoc15==_nd15 and _nd15>=5, (_kdoc15,_nd15))
# ۱۵٫۳) دام alpha10: توابع باید «داخل» کلاسِ entry-point باشند.
_ep15=re.search(r'@AppFunctionServiceEntryPoint\(([^)]*)\)',_af15,re.S)
check('بخش۱۵ @AppFunctionServiceEntryPoint هست', bool(_ep15), '')
check('بخش۱۵ کلاس entry-point از AppFunctionService ارث می‌برد',
      ': AppFunctionService()' in _af15, '')
_ep_end15=_af15.find('@AppFunctionServiceEntryPoint')
_first_fn15=_af15.find('suspend fun')
check('بخش۱۵ توابع «بعد از» entry-point تعریف شده‌اند (داخل همان کلاس)',
      0 <= _ep_end15 < _first_fn15, (_ep_end15,_first_fn15))
check('بخش۱۵ پارامتر AppFunctionContext حذف شده (در beta01 وجود ندارد)',
      'AppFunctionContext' not in _af15, '')
# ۱۵٫۴) دام alpha09: appfunctions-service دیگر منتشر نمی‌شود.
_gb15=open(os.path.join(AND,'app/build.gradle.kts'),encoding='utf-8').read()
_gb15c=strip_kotlin(_gb15)
check('بخش۱۵ وابستگی منسوخ appfunctions-service افزوده نشده',
      'appfunctions-service' not in _gb15c, '')
check('بخش۱۵ نسخهٔ beta01 پین شده', 'appfunctions:1.0.0-beta01' in _gb15 and
      'appfunctions-compiler:1.0.0-beta01' in _gb15, '')
check('بخش۱۵ پلاگین KSP اعمال شده', 'com.google.devtools.ksp' in _gb15 and
      'com.google.devtools.ksp' in open(os.path.join(AND,'build.gradle.kts'),encoding='utf-8').read(), '')
check('بخش۱۵ compileSdk >= 37 و targetSdk >= 36 (پیش‌نیاز Android 16)',
      'compileSdk = 37' in _gb15 and 'targetSdk = 36' in _gb15, '')

# ۱۵٫۵) مهم‌ترین سنجش: هم‌خوانی نام‌ها بین annotation و manifest.
# اگر این دو جدا بیفتند، system_server سرویس را bind می‌کند ولی فهرست
# توابع خالی است و build هم سبز می‌ماند.
_svcname15=re.search(r'serviceName\s*=\s*"([^"]+)"',_af15)
_xmlname15=re.search(r'appFunctionXmlFileName\s*=\s*"([^"]+)"',_af15)
check('بخش۱۵ serviceName و appFunctionXmlFileName در annotation هستند',
      bool(_svcname15) and bool(_xmlname15), '')
_mf15b=open(os.path.join(AND,'app/src/main/AndroidManifest.xml'),encoding='utf-8').read()
_regname15=re.search(r'android:name="([^"]*%s)"'%re.escape(_svcname15.group(1)),_mf15b)
check('بخش۱۵ سرویس تولیدشده در manifest ثبت شده', bool(_regname15), _svcname15.group(1))
_prop15=re.search(r'android\.app\.appfunctions"\s*\n?\s*android:value="([^"]+)"',_mf15b)
check('بخش۱۵ property متادیتا با appFunctionXmlFileName یکی است',
      bool(_prop15) and _prop15.group(1)==_xmlname15.group(1)+'.xml',
      (_prop15.group(1) if _prop15 else None, _xmlname15.group(1)))
check('بخش۱۵ سرویس با BIND_APP_FUNCTION_SERVICE محافظت می‌شود',
      'BIND_APP_FUNCTION_SERVICE' in _mf15b, '')
check('بخش۱۵ action سرویس درست است',
      'android.app.appfunctions.AppFunctionService' in _mf15b, '')
check('بخش۱۵ سرویس exported است (بدون آن system_server نمی‌تواند bind کند)',
      re.search(r'SepandyarAppFunctionService"[\s\S]{0,220}?android:exported="true"',_mf15b) is not None, '')

# ۱۵٫۶) قاعدهٔ ایمنی: هیچ تابعی کار بازگشت‌ناپذیر «انجام» نمی‌دهد.
# فقط توابعِ واقعاً AppFunction. نسخهٔ نخست هر `suspend fun` را می‌گرفت و
# دو هلپر خصوصی HTTP را هم جزو توابع می‌شمرد، پس سنجش KDoc و withContext
# روی آن‌ها بی‌معنا شکست می‌خورد.
_fns15=re.findall(r'@AppFunctionDeclaration\(isDescribedByKDoc = true\)\s*suspend fun (\w+)\(',_af15c)
check('بخش۱۵ همهٔ توابع suspend هستند', len(_fns15)>=5, _fns15)
check('بخش۱۵ سنجش تهی نیست: دست‌کم ۵ تابع اعلام شد', len(_fns15)>=5, len(_fns15))
_mut15=[f for f in _fns15 if f.startswith(('request','create','book','pay','send','delete'))]
_badmut=[f for f in _mut15 if 'EnqueuedAction' not in _af15[_af15.find('suspend fun %s('%f):_af15.find('suspend fun %s('%f)+300]]
check('بخش۱۵ هر تابعِ تغییردهنده فقط «صف» می‌کند نه اجرا', not _badmut, _badmut)
check('بخش۱۵ صف تأیید صریح است (needsConfirmation)',
      'needsConfirmation' in _af15 and 'needsConfirmation = true' in _af15, '')
check('بخش۱۵ راه لغو به عامل برگردانده می‌شود', 'cancelHint' in _af15, '')
check('بخش۱۵ تابع کیف پول فقط خواندنی است',
      'WalletBalance(' in _af15 and 'postJson("/api/wallet"' not in _af15, '')
_taxi15=_fnbody15('requestTaxiRide',_af15c)
check('بخش۱۵ بدنهٔ تابع تاکسی تهی استخراج نشد (سنجش تهی نیست)',
      len(_taxi15)>80 and 'EnqueuedAction' in _taxi15, len(_taxi15))
check('بخش۱۵ تابع تاکسی سفر را «ثبت» نمی‌کند',
      'api/taxi' not in _taxi15 and 'postJson' not in _taxi15 and 'getJson' not in _taxi15, '')

# ۱۵٫۷) KDoc یعنی prompt؛ بی‌KDoc یعنی ابزارِ بی‌توصیف.
_nodoc=[f for f in _fns15 if not re.search(r'/\*\*[\s\S]{0,600}?\*/\s*@AppFunctionDeclaration\(isDescribedByKDoc = true\)\s*suspend fun %s\('%f,_af15)]
check('بخش۱۵ هر تابع KDoc دارد (همان چیزی که مدل می‌خواند)', not _nodoc, _nodoc)
check('بخش۱۵ فراخوانی شبکه از نخ UI خارج می‌شود (وگرنه ANR)',
      _af15.count('withContext(Dispatchers.IO)')==len(_fns15), (_af15.count('withContext(Dispatchers.IO)'),len(_fns15)))
check('بخش۱۵ timeout شبکه دارد', 'connectTimeout' in _af15 and 'readTimeout' in _af15, '')
check('بخش۱۵ هیچ API دسترس‌پذیری در این فایل نیست',
      not any(k in _af15c for k in ('AccessibilityService','AccessibilityNodeInfo','dispatchGesture')), '')


# ════════════════════════════════════════════════════════════════════════
# بخش ۱۶ — fallback بینایی وقتی درخت دسترس‌پذیری خالی است
#
# ریشه در بررسی گیت‌هاب: droidrun/mobilerun صریحاً --vision-only دارد و
# دلیلش را خودش می‌گوید: «useful for the apps that do not have a11y tree
# information». ما captureForVision را داشتیم ولی opt-in، سمت وب، و
# بی‌ارتباط با حلقهٔ گام‌ها. نتیجه: در یک اپ فلاتر شش تلاش بی‌فایده و
# سپس ««X» پیدا نشد» — پیامی که دروغ است، چون دکمه هست و ما نمی‌بینیمش.
# ════════════════════════════════════════════════════════════════════════
_rn16 = open(os.path.join(KT, 'ScreenTaskRunner.kt'), encoding='utf-8').read()
_sc16 = open(os.path.join(KT, 'ScreenControlService.kt'), encoding='utf-8').read()
_rn16c = strip_kotlin(_rn16)
_sc16c = strip_kotlin(_sc16)

def _body16(name, src):
    """بدنهٔ یک fun با تطبیق کروشه.

    پنجرهٔ ثابت اینجا غلط می‌داد: attempt() کوتاه است و یک پنجرهٔ ۹۰۰
    کاراکتری به unreadableScreen() سرریز می‌کرد و سنجش‌ها را «قبول» می‌کرد.
    """
    m = re.search(r'\bfun %s\(' % re.escape(name), src)
    if not m: return ''
    j = src.find('{', m.end())
    if j < 0: return ''
    d = 0
    for k in range(j, len(src)):
        if src[k] == '{': d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0: return src[m.start():k + 1]
    return ''

# ── ۱۶٫۱) مجموعهٔ گام‌های وابسته به درخت: تهی نیست و ساختگی نیست ──────
# از منبع «خام»، نه strip‌شده: strip_kotlin رشته‌ها را حذف می‌کند و
# اعضای NEEDS_TREE همه رشته‌اند. نسخهٔ نخست از _rn16c می‌خواند و مجموعهٔ
# «خالی» می‌گرفت — یعنی سنجش تهی بود و خودش هم تهی بودن را گزارش داد.
_m16 = re.search(r'NEEDS_TREE\s*=\s*setOf\(([^)]*)\)', _rn16, re.S)
check('بخش۱۶ NEEDS_TREE استخراج شد (سنجش تهی نیست)', _m16 is not None, '')
_nt16 = set(re.findall(r'"([^"]+)"', _m16.group(1))) if _m16 else set()
check('بخش۱۶ NEEDS_TREE تهی نیست', len(_nt16) >= 10, len(_nt16))
_bogus16 = sorted(_nt16 - STEP_TYPES)
check('بخش۱۶ هیچ نوع گامِ ساختگی در NEEDS_TREE نیست', not _bogus16, _bogus16)

# ── ۱۶٫۲) گام‌های سراسری عمداً بیرون‌اند ─────────────────────────────
# این تفکیک بارِ اصلیِ طراحی است. اگر home/back داخل بودند، یک «بازگشت»
# ساده روی اپی با درخت نازک به‌اشتباه «نمی‌بینم» می‌گرفت و کار می‌خوابید.
_glob16 = {'home', 'back', 'recents', 'scroll', 'swipe', 'tap_xy', 'wait',
           'launch', 'confirm', 'lock_screen', 'notifications', 'screenshot',
           'a11y_back', 'a11y_home', 'dismiss_notifications', 'pinch', 'drag',
           'quick_settings', 'power_dialog', 'split_screen', 'headset_hook',
           'a11y_all_apps', 'a11y_recents'}
_leak16 = sorted(_glob16 & _nt16)
check('بخش۱۶ گام‌های سراسری (بدون نیاز به درخت) بیرون مانده‌اند', not _leak16, _leak16)
# پارتیشن کامل: هیچ نوع گامی نباید بی‌تکلیف بماند.
check('بخش۱۶ NEEDS_TREE ⊂ STEP_TYPES و پارتیشن کامل است',
      _nt16 | _glob16 == STEP_TYPES, sorted(STEP_TYPES - (_nt16 | _glob16)))

# ── ۱۶٫۳) دروازهٔ خوانایی «داخل attempt» و «پیش از» حلقهٔ تلاش ──────
_att16 = _body16('attempt', _rn16c)
check('بخش۱۶ بدنهٔ attempt تهی استخراج نشد (سنجش تهی نیست)',
      len(_att16) > 300 and 'performStep' in _att16, len(_att16))
check('بخش۱۶ دروازهٔ خوانایی داخل attempt است', 'NEEDS_TREE' in _att16, '')
check('بخش۱۶ دروازه خوانایی درخت را می‌سنجد', 'readScreenText().isBlank()' in _att16, '')
_g16 = _att16.find('NEEDS_TREE')
_r16 = _att16.find('tries < 6')
check('بخش۱۶ دروازه «پیش از» حلقهٔ تلاش است (وگرنه فایده‌ای ندارد)',
      0 <= _g16 < _r16, (_g16, _r16))

# ── ۱۶٫۴) بینایی روی نخ پس‌زمینه است، نه نخ اصلی (ANR) ──────────────
# captureForVision با CountDownLatch منتظر می‌ماند و درخواست شبکه blocking
# است. attempt() روی Handler(mainLooper) اجرا می‌شود.
check('بخش۱۶ executor جدا برای بینایی تعریف شده', 'Executors.newSingleThreadExecutor' in _rn16c, '')
check('بخش۱۶ executor تک‌نخی است (دو تصویر هم‌زمان گرفته نمی‌شود)',
      'newSingleThreadExecutor' in _rn16c and 'newFixedThreadPool' not in _rn16c, '')
check('بخش۱۶ readScreenViaVision مستقیم از attempt صدا زده نمی‌شود',
      'readScreenViaVision' not in _att16, '')
_un16 = _body16('unreadableScreen', _rn16c)
check('بخش۱۶ بدنهٔ unreadableScreen تهی استخراج نشد (سنجش تهی نیست)',
      len(_un16) > 300, len(_un16))
check('بخش۱۶ خواندن بینایی داخل worker.execute است',
      'worker.execute' in _un16 and 'readScreenViaVision' in _un16, '')
_wi16 = _un16.find('worker.execute'); _rv16 = _un16.find('readScreenViaVision')
check('بخش۱۶ فراخوانی بینایی «بعد از» ورود به worker است', 0 <= _wi16 < _rv16, (_wi16, _rv16))

# ── ۱۶٫۵) کران فراخوانی: هر تصویر، پیامک و موجودی بانکی دارد ───────
check('بخش۱۶ کران MAX_VISION_READS تعریف شده', 'MAX_VISION_READS' in _rn16c, '')
_mx16 = re.search(r'MAX_VISION_READS\s*=\s*(\d+)', _rn16c)
check('بخش۱۶ کران عددِ کوچک است (سرور ۶ بار در ۶۰ ثانیه اجازه می‌دهد)',
      _mx16 is not None and 1 <= int(_mx16.group(1)) <= 3, _mx16 and _mx16.group(1))
check('بخش۱۶ شمارشگر «پیش از» فراخوانی زیاد می‌شود',
      'visionReads += 1' in _un16 and _un16.find('visionReads += 1') < _un16.find('worker.execute'), '')
# محدود به بدنهٔ start(). نسخهٔ نخست فقط می‌پرسید «این رشته در فایل هست؟»
# و خودِ تعریفِ «private var visionReads = 0» همان رشته را داشت — پس پروبِ
# حذفِ بازنشانی گرفته نشد. سومین باری که یک سنجشِ «حضورِ رشته» تهی از آب
# درآمد.
_st16 = _body16('start', _rn16c)
check('بخش۱۶ بدنهٔ start تهی استخراج نشد (سنجش تهی نیست)',
      len(_st16) > 300 and 'running = true' in _st16, len(_st16))
check('بخش۱۶ شمارشگر در start() صفر می‌شود (کران بین کارها نشت نمی‌کند)',
      'visionReads = 0' in _st16, '')
check('بخش۱۶ بازنشانی «پیش از» شروع گام‌هاست',
      0 <= _st16.find('visionReads = 0') < _st16.find('runStep'),
      (_st16.find('visionReads = 0'), _st16.find('runStep')))

# ── ۱۶٫۶) رضایت پیش از تصویر؛ هیچ مسیرِ دورزدنی نیست ────────────────
check('بخش۱۶ رضایت بینایی پیش از هر تصویر سنجیده می‌شود',
      'visionAllowed' in _un16 and _un16.find('visionAllowed') < _un16.find('worker.execute'), '')
_rvv16 = _body16('readScreenViaVision', _sc16c)
check('بخش۱۶ بدنهٔ readScreenViaVision تهی استخراج نشد (سنجش تهی نیست)',
      len(_rvv16) > 200, len(_rvv16))
check('بخش۱۶ readScreenViaVision از captureForVision می‌گذرد (دور نمی‌زند)',
      'captureForVision()' in _rvv16 and 'takeScreenshot' not in _rvv16, '')
check('بخش۱۶ captureForVision همچنان با رضایت و API 30+ دروازه شده',
      'visionAllowed(this)' in _sc16c and 'SDK_INT < 30' in _sc16c, '')

# ── ۱۶٫۷) پیامِ صادقانه، نه «پیدا نشد» ───────────────────────────────
_hint16 = re.search(r'UNREADABLE_HINT\s*=\s*\n?\s*"([^"]+)"', _rn16)
check('بخش۱۶ پیامِ درختِ‌ناخوانا تعریف شده', _hint16 is not None, '')
if _hint16:
    _h16 = _hint16.group(1)
    check('بخش۱۶ پیام با «پیدا نشد» فرق دارد (وگرنه همان دروغ قبلی است)',
          'پیدا نشد' not in _h16, _h16)
    check('بخش۱۶ پیام راه‌حل را می‌گوید، نه فقط بن‌بست را',
          'دیدن صفحه' in _h16, _h16)
check('بخش۱۶ مسیر شکستِ ناخوانا واقعاً به UNREADABLE_HINT می‌رسد',
      'UNREADABLE_HINT' in _un16, '')

# ── ۱۶٫۸) مقایسه با همان نرمال‌سازیِ گره‌ها ─────────────────────────
# مدل بینایی متن را از پیکسل می‌خواند: «ی» عربی، رقم عربی، نیم‌فاصلهٔ
# از دست رفته. اگر گره‌ها نرمال می‌شدند ولی این مقایسه نه، صفحهٔ درست
# «پیدا نشد» می‌گرفت.
_th16 = _body16('textHas', _rn16c)
check('بخش۱۶ textHas هر دو طرف را نرمال می‌کند',
      _th16.count('SmartSelector.normalize') == 2, _th16.count('SmartSelector.normalize'))
check('بخش۱۶ مقایسهٔ بینایی با contains خام نیست',
      'h.contains(n)' in _th16 and 'seen.contains(step.expect)' not in _rn16c, '')

# ── ۱۶٫۹) لغو در فاصلهٔ انتظارِ شبکه ─────────────────────────────────
check('بخش۱۶ بازگشت از worker، لغو را می‌سنجد',
      'if (cancelled || !running) return@post' in _rn16c, '')

# ── ۱۶٫۱۰) دروازهٔ confirm دست‌نخورده ───────────────────────────────
# بینایی فقط «می‌خواند». هرگز جای تأیید سالمند را نمی‌گیرد.
check('بخش۱۶ confirm در NEEDS_TREE نیست (هرگز از مسیر بینایی نمی‌گذرد)',
      'confirm' not in _nt16, '')
# ساختاری و بی‌رشته: در منبع strip‌شده «confirm» وجود ندارد، پس سنجشِ
# رشته‌ای اینجا همیشه شکست می‌خورد. در عوض «ترتیب» را می‌سنجیم.
_rs16 = _body16('runStep', _rn16c)
check('بخش۱۶ بدنهٔ runStep تهی استخراج نشد (سنجش تهی نیست)',
      len(_rs16) > 200 and 'askConfirm' in _rs16, len(_rs16))
check('بخش۱۶ confirm همچنان پیش از attempt جدا می‌شود',
      0 <= _rs16.find('askConfirm') < _rs16.find('attempt(step'),
      (_rs16.find('askConfirm'), _rs16.find('attempt(step')))
check('بخش۱۶ مسیر بینایی هیچ کنشِ تغییری ندارد (فقط می‌خواند)',
      not any(k in _un16 for k in ('performStep', 'dispatchGesture', 'performAction')), '')

# ── ۱۶٫۱۱) شبکه: timeout و شکستِ بی‌صدا ──────────────────────────────
check('بخش۱۶ readScreenViaVision timeout اتصال و خواندن دارد',
      'connectTimeout' in _rvv16 and 'readTimeout' in _rvv16, '')
check('بخش۱۶ خطای شبکه استثنا پرتاب نمی‌کند (کار نصفه رها نمی‌شود)',
      'catch (e: Exception)' in _rvv16 and 'finally' in _rvv16, '')
check('بخش۱۶ پاسخِ غیر 2xx رشتهٔ خالی می‌دهد نه متنِ خطای سرور',
      'responseCode !in 200..299' in _rvv16, '')

# ── ۱۶٫۱۲) هیچ API دسترس‌پذیریِ تازه‌ای اضافه نشد ────────────────────
# لایهٔ بینایی عمداً «خواندن» است؛ اگر dispatchGesture از دلِ متنِ
# خوانده‌شده ساخته می‌شد، همان چیزی می‌شد که سیاست پلی ممنوع کرده.
check('بخش۱۶ مسیر بینایی API دسترس‌پذیری تازه‌ای ندارد',
      not any(k in _rvv16 for k in ('AccessibilityNodeInfo', 'dispatchGesture', 'performGlobalAction')), '')


# ════════════════════════════════════════════════════════════════════════
# بخش ۱۷ — ضربهٔ بینایی: بستنِ حلقهٔ «دیدن → عمل کردن»
#
# پیش از این، fallback بینایی فقط «متن» می‌داد. یعنی می‌توانستیم به سالمند
# بگوییم روی صفحه چیست، ولی در همان اپ‌هایی که بیشترین نیاز را دارند
# (فلاتر، canvas، WebView) نمی‌توانستیم هیچ دکمه‌ای را بزنیم. کنترل صفحه
# ناقص بود.
#
# الگو از بررسی منابع: crew-helper#114 (VisualTapLease + فهرست ممنوعهٔ
# کنش‌های تعهدآور) و UGround/OS-Atlas (مکان‌یابی بصری به مختصات).
# ════════════════════════════════════════════════════════════════════════
_hnd17 = open(os.path.join(ROOT, 'app', 'handler.py'), encoding='utf-8').read()
_mem17 = open(os.path.join(ROOT, 'app', 'memory.py'), encoding='utf-8').read()
_rn17 = open(os.path.join(KT, 'ScreenTaskRunner.kt'), encoding='utf-8').read()
_sc17 = open(os.path.join(KT, 'ScreenControlService.kt'), encoding='utf-8').read()
_rn17c = strip_kotlin(_rn17)
_sc17c = strip_kotlin(_sc17)

# ── ۱۷٫۱) endpoint وجود دارد و دروازه‌هایش به ترتیب درست‌اند ──────────
_ep17 = _hnd17[_hnd17.find("p=='/api/screen/vision/tap'"):]
check('بخش۱۷ endpoint /api/screen/vision/tap وجود دارد', _ep17.startswith("p=='"), '')
_ep17 = _ep17[:_ep17.find("if p=='/api/screen-tasks'")] if "if p=='/api/screen-tasks'" in _ep17 else _ep17[:3000]
_o17 = [k for k in ("consent_granted(c,'screen_vision')", 'image_required', 'target_required',
                    'vision_tap_denied', 'image_too_large', 'rate_limited', 'call_llm_vision_ground')
        if k in _ep17]
check('بخش۱۷ هر هفت دروازه در مسیر هست', len(_o17) == 7, _o17)
_i17 = {k: _ep17.find(k) for k in _o17}
check('بخش۱۷ رضایت «پیش از» هر چیز دیگری سنجیده می‌شود',
      _i17["consent_granted(c,'screen_vision')"] == min(_i17.values()), _i17)
check('بخش۱۷ فهرست ممنوعه «پیش از» محدودیت نرخ است (درخواستِ ردشده بودجه نمی‌سوزاند)',
      _i17['vision_tap_denied'] < _i17['rate_limited'], (_i17['vision_tap_denied'], _i17['rate_limited']))
check('بخش۱۷ هیچ تصویری در رویداد ثبت نمی‌شود',
      "'screen_vision_tap'" in _ep17 and 'img' not in _ep17.split("'screen_vision_tap'")[1].split(')')[0], '')

# ── ۱۷٫۲) زنده: ترتیب دروازه‌ها در عمل ──────────────────────────────
req('/api/consents', 'POST', {'scope': 'screen_vision', 'granted': False, 'confirmed_by_voice': False})
_st17, _bd17 = req('/api/screen/vision/tap', 'POST', {'image': 'x' * 50, 'target': 'منو'})
check('بخش۱۷ زنده: بی‌رضایت ۴۰۳', _st17 == 403 and _bd17.get('error') == 'senior_consent_not_granted', (_st17, _bd17))
req('/api/consents', 'POST', {'scope': 'screen_vision', 'granted': True, 'confirmed_by_voice': True})
_st17, _bd17 = req('/api/screen/vision/tap', 'POST', {'target': 'منو'})
check('بخش۱۷ زنده: بی‌تصویر ۴۰۰', _st17 == 400 and _bd17.get('error') == 'image_required', (_st17, _bd17))
_st17, _bd17 = req('/api/screen/vision/tap', 'POST', {'image': 'x' * 50})
check('بخش۱۷ زنده: بی‌هدف ۴۰۰', _st17 == 400 and _bd17.get('error') == 'target_required', (_st17, _bd17))
for _t17 in ('پرداخت', 'ثبت سفارش', 'Pay Now', 'CHECKOUT', 'ورود به حساب', 'حذف', 'password'):
    _st17, _bd17 = req('/api/screen/vision/tap', 'POST', {'image': 'x' * 50, 'target': _t17})
    check('بخش۱۷ زنده: «%s» با بینایی رد می‌شود' % _t17,
          _st17 == 403 and _bd17.get('error') == 'visual_tap_denied', (_st17, _bd17))
# تصویرِ بیش‌ازحد بزرگ عمداً انتخاب شد، نه تصویرِ کوچک.
#
# چرا؟ کران اندازه «پیش از» محدودیت نرخ سنجیده می‌شود. پس ۴۱۳ ثابت می‌کند
# درخواست از دروازهٔ رضایت، تصویر، هدف و «فهرست ممنوعه» گذشته — بدون آنکه
# حتی یک توکن از بودجهٔ نرخ را بسوزاند. نسخهٔ نخست اینجا تصویر کوچک
# می‌فرستاد و ۵۰۲ می‌گرفت؛ یعنی دو توکن مصرف می‌کرد و §۲۷ در
# test_deployment («دقیقاً ۶ درخواست در پنجره») را می‌شکست. بودجهٔ نرخ
# stateِ داخل «فرایند سرور» است و از فرایند آزمون قابل بازنشانی نیست.
_BIG17 = 'x' * 400_001
_st17, _bd17 = req('/api/screen/vision/tap', 'POST', {'image': _BIG17, 'target': 'دسته‌بندی غذا'})
check('بخش۱۷ زنده: هدفِ ناوبری از فهرست ممنوعه می‌گذرد (۴۱۳ نه ۴۰۳)',
      _st17 == 413 and _bd17.get('error') == 'image_too_large', (_st17, _bd17))

# ── ۱۷٫۳) زنده: درخواستِ ردشده بودجهٔ نرخ را نمی‌سوزاند ──────────────
# هفت بار هدفِ ممنوع می‌فرستیم؛ اگر دروازهٔ رد «بعد از» محدودیت نرخ بود،
# بودجه تمام می‌شد و درخواست مشروع بعدی ۴۲۹ می‌گرفت.
for _ in range(7):
    _s, _ = req('/api/screen/vision/tap', 'POST', {'image': 'x' * 50, 'target': 'پرداخت'})
    check('بخش۱۷ زنده: درخواستِ ردشده هرگز ۴۲۹ نمی‌شود', _s == 403, _s)
_st17, _bd17 = req('/api/screen/vision/tap', 'POST', {'image': _BIG17, 'target': 'دسته‌بندی غذا'})
check('بخش۱۷ زنده: پس از ۸ درخواستِ ردشده، هدفِ مشروع هنوز به کران نرخ نرسیده',
      _st17 == 413 and _st17 != 429, (_st17, _bd17))

# ── ۱۷٫۳٫۱) پاک‌سازی: رضایت را همان‌طور که بود برگردان ──────────────
# بدون این، §۲۷ در test_deployment («بی‌رضایت باید ۴۰۳ بدهد») روی رضایتِ
# روشنِ باقی‌مانده از این بخش اجرا می‌شد و ۵۰۲ می‌گرفت. آلودگیِ state بین
# دو سوئیت — و چون هر دو سبز/قرمز بودنشان به ترتیب اجرا بند بود، فقط در
# اجرای «کامل» هارنس دیده می‌شد، نه در اجرای تکی.
req('/api/consents', 'POST', {'scope': 'screen_vision', 'granted': False, 'confirmed_by_voice': False})

# ── ۱۷٫۴) parse_ground: تنها جایی که رشتهٔ مدل به عدد تبدیل می‌شود ──
sys.path.insert(0, ROOT)
from app.memory import parse_ground as _pg17
_cases17 = [
    ('{"found": true, "x": 0.52, "y": 0.83}', {'found': True, 'x': 0.52, 'y': 0.83}),
    ('```json\n{"found": true, "x": 0.5, "y": 0.5}\n```', {'found': True, 'x': 0.5, 'y': 0.5}),
    ('بفرما: {"found": true, "x": 0.1, "y": 0.9} موفق باشی', {'found': True, 'x': 0.1, 'y': 0.9}),
    ('{"found": false}', None),
    ('{"found": true, "x": 540, "y": 1200}', None),   # پیکسل داده، نه نرمال
    ('{"found": true, "x": -0.1, "y": 0.5}', None),
    ('{"found": true, "x": 1.2, "y": 0.5}', None),
    ('{"found": true, "y": 0.5}', None),
    ('{"found": true, "x": "abc", "y": 0.5}', None),
    ('{"found": "true", "x": 0.1, "y": 0.9}', None),
    ('پیدا نکردم', None), ('', None), (None, None), (42, None),
]
_bad17 = [(r, _pg17(r), e) for r, e in _cases17 if _pg17(r) != e]
check('بخش۱۷ parse_ground هر ۱۴ حالت را درست تجزیه می‌کند', not _bad17, _bad17)
check('بخش۱۷ سنجش تهی نیست: دست‌کم ۳ حالت باید قبول شود',
      sum(1 for _, e in _cases17 if e is not None) >= 3, '')

# ── ۱۷٫۵) هم‌خوانی دو فهرستِ ممنوعه (بار اصلیِ این بخش) ──────────────
# اگر فهرست دستگاه و فهرست سرور جدا بیفتند، یکی چیزی را مجاز می‌داند که
# آن یکی رد می‌کند — و چون هر دو لایه «ایمنی»‌اند، رانش بی‌صدا است و build
# هم سبز می‌ماند. همان شکلِ دامی که در §۱۵ (annotation↔manifest) بود.
_m17s = re.search(r'VISION_TAP_DENY\s*=\s*\(([^)]*)\)', _hnd17, re.S)
_m17k = re.search(r'COMMIT_LABELS\s*=\s*setOf\(([^)]*)\)', _rn17, re.S)
check('بخش۱۷ هر دو فهرست استخراج شدند (سنجش تهی نیست)',
      _m17s is not None and _m17k is not None, (_m17s is not None, _m17k is not None))
_srv17 = set(re.findall(r"'([^']+)'", _m17s.group(1))) if _m17s else set()
_cli17 = set(re.findall(r'"([^"]+)"', _m17k.group(1))) if _m17k else set()
check('بخش۱۷ فهرست سرور تهی نیست', len(_srv17) >= 20, len(_srv17))
check('بخش۱۷ فهرست دستگاه تهی نیست', len(_cli17) >= 20, len(_cli17))
check('بخش۱۷ دو فهرست «یکسان»‌اند (رانش = ضربهٔ بینایی به کنش تعهدآور)',
      _srv17 == _cli17, sorted(_srv17 ^ _cli17))

# ── ۱۷٫۶) ضربهٔ بینایی فقط برای ناوبری، و فقط با سه قید ──────────────
_un17 = _body16('unreadableScreen', _rn17c)
# از منبع «خام»: strip_kotlin رشته‌ها را پاک می‌کند، پس «tap_text» در
# _rn17c وجود ندارد و سنجش همیشه شکست می‌خورد (همان دامِ §۱۶).
check('بخش۱۷ ضربهٔ بینایی فقط برای tap_text است',
      'step.type == "tap_text"' in _rn17, '')
_tvt17 = _body16('tryVisualTap', _rn17c)
check('بخش۱۷ بدنهٔ tryVisualTap تهی استخراج نشد (سنجش تهی نیست)',
      len(_tvt17) > 300, len(_tvt17))
check('بخش۱۷ ضربهٔ بینایی روی نخ پس‌زمینه است',
      'worker.execute' in _tvt17 and _tvt17.find('worker.execute') < _tvt17.find('locateViaVision'), '')
_f1 = _tvt17.find('screenFingerprint'); _l1 = _tvt17.find('locateViaVision')
_f2 = _tvt17.rfind('screenFingerprint')
check('بخش۱۷ اثرانگشت «پیش از» مکان‌یابی گرفته می‌شود', 0 <= _f1 < _l1, (_f1, _l1))
check('بخش۱۷ اثرانگشت «پس از» مکان‌یابی هم گرفته می‌شود (اجاره)',
      _f2 > _l1 and _tvt17.count('screenFingerprint') >= 2, _tvt17.count('screenFingerprint'))
check('بخش۱۷ ضربه «فقط» پس از یکسان بودن دو اثرانگشت است',
      'before != after' in _tvt17 and _tvt17.find('before != after') < _tvt17.find('visualTap'), '')
check('بخش۱۷ دروازهٔ برچسب تعهدآور پیش از ورود به مسیر ضربه است',
      'commitLabel(step.payload) == null' in _rn17c, '')
check('بخش۱۷ اثرِ ضربه راستی‌آزمایی می‌شود (گام دوباره سنجیده می‌شود، نه فرضِ موفقیت)',
      'attempt(step, svc, deadline, tries + 1)' in _tvt17, '')
check('بخش۱۷ tries+1 از حلقهٔ بی‌پایان جلوگیری می‌کند',
      'tries + 1' in _tvt17 and 'tries)' not in _tvt17.replace('tries + 1', ''), '')
check('بخش۱۷ بازگشت از worker لغو را می‌سنجد', 'if (cancelled || !running) return@post' in _tvt17, '')
# باز هم منبع خام: خودِ «""» یک رشته است و strip_kotlin حذفش می‌کند.
_cl17 = _body16('commitLabel', _rn17)
check('بخش۱۷ بدنهٔ commitLabel تهی استخراج نشد (سنجش تهی نیست)',
      len(_cl17) > 100 and 'COMMIT_LABELS' in _cl17, len(_cl17))
check('بخش۱۷ برچسب «خالی» تعهدآور شمرده می‌شود (ضربهٔ بی‌هدف ممنوع)',
      'if (t.isEmpty()) return ""' in _cl17, _cl17[:150])

# ── ۱۷٫۷) مختصات نرمال‌شده، نه پیکسل ─────────────────────────────────
_vt17 = _body16('visualTap', _sc17c)
check('بخش۱۷ visualTap بازهٔ ۰ تا ۱ را اعتبارسنجی می‌کند',
      'nx < 0f || nx > 1f || ny < 0f || ny > 1f' in _vt17, '')
check('بخش۱۷ ضربه با displayMetrics به پیکسلِ «صفحه» تبدیل می‌شود نه پیکسلِ تصویر',
      'displayMetrics' in _vt17 and 'widthPixels' in _vt17 and 'heightPixels' in _vt17, '')
_lv17 = _body16('locateViaVision', _sc17c)
check('بخش۱۷ locateViaVision هم بازه را سمت دستگاه چک می‌کند (دفاع دوم)',
      'x < 0.0 || x > 1.0 || y < 0.0 || y > 1.0' in _lv17, '')
check('بخش۱۷ locateViaVision از captureForVision می‌گذرد (رضایت دور زده نمی‌شود)',
      'captureForVision()' in _lv17 and 'takeScreenshot' not in _lv17, '')
check('بخش۱۷ locateViaVision timeout شبکه دارد',
      'connectTimeout' in _lv17 and 'readTimeout' in _lv17, '')
check('بخش۱۷ effect انگشت صفحه تهی استخراج نشد (سنجش تهی نیست)',
      len(_body16('screenFingerprint', _sc17c)) > 120, len(_body16('screenFingerprint', _sc17c)))
check('بخش۱۷ هیچ API دسترس‌پذیری تازه‌ای در مسیر بینایی نیست',
      not any(k in _lv17 for k in ('AccessibilityNodeInfo', 'performGlobalAction')), '')


# ════════════════════════════════════════════════════════════════════════
# بخش ۱۸ — «ضربه پذیرفته شد» ≠ «کار انجام شد»
#
# ریشه: ۳۴ گام از ۳۵ گامِ رسپی‌های موجود expect ندارند. بدون expect تنها
# معیارِ موفقیت، مقدار برگشتی performStep بود — و آن برای tap یعنی
# «dispatchGesture پذیرفته شد»، نه «دکمهٔ درست زده شد». اگر برچسبِ حدسیِ ما
# با برچسبِ واقعی اپ نمی‌خواند، ضربه به هیچ می‌خورد و ما به سالمند
# می‌گفتیم «کار انجام شد».
# ════════════════════════════════════════════════════════════════════════
_rn18 = open(os.path.join(KT, 'ScreenTaskRunner.kt'), encoding='utf-8').read()
_rn18c = strip_kotlin(_rn18)
_att18 = _body16('attempt', _rn18c)

# ── ۱۸٫۱) داده: چقدر از رسپی‌ها بی‌expect اند؟ ───────────────────────
_j18 = req('/api/apps/approved')[1]
_steps18 = [st for it in _j18.get('items', []) for st in ((it.get('plan') or {}).get('steps') or [])]
_noexp18 = [st for st in _steps18 if not (st.get('expect') or '').strip()]
check('بخش۱۸ سنجش تهی نیست: دست‌کم ۲۰ گام در رسپی‌ها هست', len(_steps18) >= 20, len(_steps18))
check('بخش۱۸ بیشتر گام‌ها expect ندارند (پس معیارِ جایگزین لازم است)',
      len(_noexp18) > len(_steps18) // 2, (len(_noexp18), len(_steps18)))

# ── ۱۸٫۲) معیارِ جایگزین: صفحه باید عوض شده باشد ────────────────────
check('بخش۱۸ اثرانگشت «پیش از» performStep گرفته می‌شود',
      0 <= _att18.find('preFp') < _att18.find('performStep'), (_att18.find('preFp'), _att18.find('performStep')))
check('بخش۱۸ صفحهٔ دست‌نخورده ⇒ گام راضی‌کننده «نیست»',
      'svc.screenFingerprint() == preFp) false' in _att18.replace('\n', ' ').replace('  ', ' ')
      or ('screenFingerprint() == preFp' in _att18 and ') false' in _att18), '')
check('بخش۱۸ نتیجه به حلقهٔ تلاش برمی‌گردد، نه شکستِ فوری (صفحهٔ کُند تنبیه نمی‌شود)',
      'finish("failed"' not in _att18.split('screenFingerprint() == preFp')[1][:120]
      if 'screenFingerprint() == preFp' in _att18 else False, '')

# ── ۱۸٫۳) دامنهٔ نگهبان: عمداً باریک ────────────────────────────────
_nve18 = _body16('needsVisibleEffect', _rn18)
check('بخش۱۸ بدنهٔ needsVisibleEffect تهی استخراج نشد (سنجش تهی نیست)',
      len(_nve18) > 40 and 'tap_text' in _nve18, len(_nve18))
check('بخش۱۸ نگهبان فقط وقتی expect خالی است فعال می‌شود (معیارِ expect دست‌نخورده)',
      'step.expect.isBlank()' in _nve18, '')
_nve_types18 = set(re.findall(r'step\.type == "([a-z_]+)"', _nve18))
check('بخش۱۸ نگهبان فقط برای tap_text و tap_id است',
      _nve_types18 == {'tap_text', 'tap_id'}, sorted(_nve_types18))
check('بخش۱۸ گام‌های ذاتاً بی‌اثرِ بصری بیرون مانده‌اند (وگرنه کپی «شکست» می‌گرفت)',
      not _nve_types18 & {'copy', 'cut', 'select_text', 'select_all', 'set_progress', 'scroll'},
      sorted(_nve_types18))
check('بخش۱۸ conforM/wait/launch در دامنهٔ نگهبان نیستند',
      not _nve_types18 & {'confirm', 'wait', 'launch'}, sorted(_nve_types18))

print(f'STAGE-3 TEST: {total} checks; failures={len(failures)}')
if failures: print('FAILED:',', '.join(failures)); sys.exit(1)
print('Stage-3 Android control test passed')
