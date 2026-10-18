#!/usr/bin/env python3
"""Stage-4 test — رفع ابهام گفتار نامفهوم سالمند با پاپ‌آپ دو تصویری."""
import io, json, os, re, sys, urllib.request, urllib.error
BASE='http://127.0.0.1:4174'
ROOT=os.path.dirname(os.path.abspath(__file__))
def req(path,method='GET',data=None,headers=None):
 b=json.dumps(data,ensure_ascii=False).encode() if data is not None else None
 r=urllib.request.Request(BASE+path,method=method,data=b,headers={'Content-Type':'application/json',**(headers or {})})
 try:
  with urllib.request.urlopen(r,timeout=60) as x: return x.status,json.loads(x.read())
 except urllib.error.HTTPError as e: return e.code,json.loads(e.read() or b'{}')
failures=[]; total=0
def check(name,cond,detail=''):
 global total
 total+=1
 print(('✅' if cond else '❌'),name,('' if cond else '-> '+str(detail)))
 if not cond: failures.append(name)

print('--- 1) واژه‌نامه نیت‌ها ---')
s,j=req('/api/intents'); items=j.get('items',[]); check('GET /api/intents 200',s==200,(s,j))
check('دست‌کم ۱۰ نیت با پرس‌وجوی تصویر',len(items)>=10 and all(x.get('image_query') for x in items),len(items))

print('--- 2) تشخیص گفتار نامفهوم ---')
s,j=req('/api/conversation','POST',{'text':'بگو ببینم اون یکی','confidence':0.31})
check('اطمینان پایین → نیاز به رفع ابهام',s==200 and j.get('needs_clarification') is True,(s,j.get('needs_clarification')))
s,j=req('/api/conversation','POST',{'text':'داروهای امروز من','confidence':0.93})
check('گفتار روشن → بدون رفع ابهام',j.get('needs_clarification') is False,j.get('intent'))
s,j=req('/api/conversation','POST',{'text':'سلام خوبی'})
check('احوال‌پرسی → مزاحم کاربر نمی‌شود',j.get('needs_clarification') is False,j.get('needs_clarification'))
s,j=req('/api/conversation','POST',{'text':'درد قفسه سینه دارم'})
check('گارد ایمنی همچنان بر رفع ابهام مقدم است',j.get('clinical_answer_blocked') is True and 'needs_clarification' not in j,j.get('intent'))

print('--- 3) پاپ‌آپ دو تصویری ---')
s,j=req('/api/disambiguate','POST',{'text':'بگو ببینم اون یکی','confidence':0.31})
check('POST /api/disambiguate 200',s==200,(s,j))
opts=j.get('options',[])
check('دقیقاً دو گزینه نشان داده می‌شود',len(opts)==2,len(opts))
check('هر گزینه برچسب و اقدام دارد',all(o.get('label') and o.get('action') for o in opts),opts)
check('هر گزینه تصویر (یا جایگزین آفلاین) دارد',all(isinstance(o.get('image'),dict) and 'source' in o['image'] for o in opts),[type(o.get('image')) for o in opts])
check('منبع تصویر اعلام می‌شود',all((o['image'].get('source') in ('openverse','commons','offline')) for o in opts),[o['image'].get('source') for o in opts])
check('پرسش کوتاه و تأییدی است (بدون نام فنی)',len(j.get('question',''))<=30,j.get('question'))
check('جمله گفتاری هر دو گزینه را نام می‌برد',all(o['label'] in j.get('spoken','') for o in opts),j.get('spoken'))
sid=j.get('id'); check('شناسه نشست ساخته می‌شود',bool(sid),sid)

print('--- 4) ثبت انتخاب کاربر ---')
s,j=req('/api/disambiguate/resolve','POST',{'id':sid,'chosen':opts[0]['id']})
check('ثبت انتخاب 200',s==200 and j.get('ok'),(s,j))
check('اقدام مقصد برگردانده می‌شود',j.get('action')==opts[0]['action'],(j.get('action'),opts[0]['action']))
s,j=req('/api/disambiguate/resolve','POST',{'id':'not-a-real-id','chosen':'meds'}); check('شناسه نامعتبر 404',s==404,(s,j))
s,j=req('/api/disambiguation/history'); hist=j.get('items',[])
check('تاریخچه ثبت می‌شود',s==200 and any(h['id']==sid for h in hist),(s,len(hist)))
check('انتخاب کاربر در تاریخچه مانده',any(h['id']==sid and h.get('chosen')==opts[0]['id'] and h.get('resolved')==1 for h in hist),[h.get('chosen') for h in hist if h['id']==sid])

print('--- 5) جست‌وجوی تصویر ---')
s,j=req('/api/images/search?q=medicine%20pills&count=2'); check('GET /api/images/search 200',s==200,(s,j))
check('دو تصویر برمی‌گردد',len(j.get('items',[]))==2,len(j.get('items',[])))
s,j=req('/api/images/search?q='); check('پرس‌وجوی خالی 400',s==400,(s,j))
s,a=req('/api/images/search?q=home%20blood%20pressure%20monitor&count=1')
s,b=req('/api/images/search?q=home%20blood%20pressure%20monitor&count=1')
check('کش محلی نتیجه یکسان می‌دهد',a.get('items')==b.get('items'),'')
check('در حالت آفلاین هم پاسخ خالی نیست',all(isinstance(i,dict) and 'source' in i for i in b.get('items',[])),b.get('items'))

print('--- 6) قرارداد لایه‌ها: اقدام‌های سرور ↔ دیسپچر وب ---')
web=io.open(os.path.join(ROOT,'index.html'),encoding='utf-8').read()
m=re.search(r'function dispatchClarified\(action\)\{(.*?)\n?\}\n',web,re.S) or re.search(r'function dispatchClarified\(action\)\{(.*)',web)
block=web[web.find('function dispatchClarified'):]
block=block[:block.find('function SmartNormalize')]
handled=set(re.findall(r"case '([a-z_]+)'",block))
server_actions={x['action'] for x in items}
missing=server_actions-handled
check('هر اقدام سرور در رابط وب پیاده شده',not missing,(missing,sorted(handled)))
for fn in ['showChoicePopup','chooseClarification','dismissClarification','requestClarification','closeClarifyPopup']:
    check('تابع '+fn+' در رابط هست',('function '+fn) in web or ('async function '+fn) in web,'')
check('پاپ‌آپ با z-index بالای اپ اصلی می‌نشیند','z-index:10000' in web,'')
check('اهداف لمسی بزرگ (دست‌کم ۱۹۰px)','min-height:198px' in web,'')
check('راه خروج بن‌بست‌نبودن («هیچ‌کدام» و «بعداً»)',('هیچ‌کدام' in web and 'بعداً' in web),'')
check('پاپ‌آپ پس از انتخاب بسته می‌شود','closeClarifyPopup()' in web,'')
check('مهلت خودکار برای رها نشدن گفت‌وگو','dismissClarification(\'timeout\')' in web,'')
check('اعتبارنامه تصویر نمایش داده می‌شود','تصاویر: ' in web,'')
check('پاسخ صوتی «اولی/دومی» پشتیبانی می‌شود','chooseClarification(0)' in web and 'chooseClarification(1)' in web,'')
asset=io.open(os.path.join(ROOT,'android','app','src','main','assets','index.html'),encoding='utf-8').read()
check('کپی اندروید با نسخه وب یکسان است',asset==web,'')

print(f'STAGE-4 TEST: {total} checks; failures={len(failures)}')
if failures: print('FAILED:',', '.join(failures)); sys.exit(1)
print('Stage-4 disambiguation test passed')
