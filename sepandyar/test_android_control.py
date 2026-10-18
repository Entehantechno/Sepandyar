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

print(f'STAGE-3 TEST: {total} checks; failures={len(failures)}')
if failures: print('FAILED:',', '.join(failures)); sys.exit(1)
print('Stage-3 Android control test passed')
