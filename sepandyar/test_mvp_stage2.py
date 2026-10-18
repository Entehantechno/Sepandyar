#!/usr/bin/env python3
"""Stage-2 MVP test — آموزش تأییدشده، گارد ایمنی، خوداظهاری علائم، رضایت مراقب و صف پیام/تماس."""
import json, sys, urllib.request, urllib.error
BASE='http://127.0.0.1:4174'
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

print('--- 1) محتوای آموزشی از پیش تأییدشده (بند ۴ MVP) ---')
s,j=req('/api/education/topics'); check('GET /api/education/topics 200',s==200,(s,j))
check('دست‌کم ۸ موضوع تأییدشده',len(j.get('items',[]))>=8,len(j.get('items',[])))
s,j=req('/api/education/next'); check('GET /api/education/next محتوا دارد',s==200 and bool(j.get('item')),j)
tid=j['item']['id'] if j.get('item') else ''
s,j=req('/api/education/'+tid); check('GET /api/education/{id} 200',s==200 and j.get('body'),(s,j))
s,j=req('/api/education/does-not-exist'); check('محتوای ناموجود 404',s==404,(s,j))
s,j=req('/api/education','POST',{'topic':'تست','category':'تست','body':'متن آزمایشی'}); check('ثبت محتوای جدید = pending',s==201 and j.get('status')=='pending',(s,j)); nid=j.get('id')
s,j=req('/api/education/'+nid); check('محتوای تأییدنشده به سالمند نشان داده نمی‌شود',s==404,(s,j))
s,j=req('/api/education/'+nid+'/approve','POST',{}); check('تأیید بدون نام تأییدکننده رد می‌شود',s==400,(s,j))
s,j=req('/api/education/'+nid+'/approve','POST',{'approved_by':'دکتر تست'}); check('تأیید با نام پزشک',s==200 and j.get('status')=='approved',(s,j))
s,j=req('/api/education/'+nid); check('پس از تأیید قابل نمایش است',s==200,(s,j))

print('--- 2) خوداظهاری علائم منتخب (بند ۲ MVP) ---')
s,j=req('/api/symptoms/catalog'); check('GET /api/symptoms/catalog 200',s==200,len(j.get('items',[])))
check('کاتالوگ دست‌کم ۱۰ علامت دارد',len(j.get('items',[]))>=10,len(j.get('items',[])))
s,j=req('/api/symptoms','POST',{'symptom':'سرگیجه','severity':'متوسط'}); check('علامت عادی ثبت می‌شود بدون ارتقا',s==201 and j.get('escalated') is False,(s,j))
s,j=req('/api/symptoms','POST',{'symptom':'تنگی نفس','severity':'متوسط'}); check('علامت پرخطر هشدار + صف مراقب می‌سازد',s==201 and j.get('escalated') and j.get('alert_id') and j.get('action_id'),(s,j))
s,j=req('/api/symptoms','POST',{'symptom':'سردرد','severity':'شدید'}); check('شدت «شدید» هم ارتقا می‌دهد',s==201 and j.get('escalated') is True,(s,j))
s,j=req('/api/symptoms','POST',{}); check('علامت خالی 400',s==400,(s,j))
s,j=req('/api/symptoms'); check('گزارش‌ها خوانده می‌شوند',s==200 and len(j.get('items',[]))>=3,(s,j))

print('--- 3) گارد ایمنی کد-محور (بند ایمنی پروپوزال) ---')
s,j=req('/api/safety/rules'); check('GET /api/safety/rules 200',s==200,len(j.get('items',[])))
check('دست‌کم ۲۵ قاعده ایمنی',len(j.get('items',[]))>=25,len(j.get('items',[])))
s,j=req('/api/ai/chat','POST',{'text':'امروز درد قفسه سینه دارم'})
check('عبارت پرخطر: پاسخ بالینی مسدود شد',s==200 and j.get('provider')=='safety_guardrail' and j.get('clinical_answer_blocked') is True,(s,j))
check('عبارت پرخطر: نیاز به ارجاع فوری + هشدار',j.get('requires_escalation') is True and j.get('alert_id'),j)
s,j=req('/api/conversation','POST',{'text':'تنگی نفس دارم'})
check('/api/conversation هم رهگیری می‌شود',s==200 and j.get('intent')=='safety.emergency' and j.get('clinical_answer_blocked') is True,(s,j))
s,j=req('/api/ai/chat','POST',{'text':'می‌شود دوز دارو را خودم زیاد کنم؟'})
check('پرسش مبهم: ارجاع به پزشک بدون تشخیص',s==200 and j.get('provider')=='safety_guardrail' and j.get('requires_escalation') is False and j.get('matched')=='دوز دارو',(s,j))
s,j=req('/api/ai/chat','POST',{'text':'سلام'})
check('مسیر عادی دست‌نخورده (بدون کلید AI = 503)',s in (200,503) and j.get('provider','configured')!='safety_guardrail',(s,j))

print('--- 4) رضایت سالمند برای داشبورد مراقب ---')
s,j=req('/api/caregiver/panel'); check('پنل بدون نشست مراقب = 403',s==403 and j.get('error')=='caregiver_session_required',(s,j))
s,j=req('/api/caregiver/session','POST',{'phone':'09129999999'}); check('شماره‌ی دعوت‌نشده = 403',s==403 and j.get('error')=='caregiver_not_invited',(s,j))
s,j=req('/api/caregiver/session','POST',{}); check('شماره خالی = 400',s==400,(s,j))
s,j=req('/api/caregivers','POST',{'name':'مراقب مرحله دو','phone':'09128888888','role':'family','permissions':['health']}); check('ثبت مراقب',s==201,(s,j))
s,j=req('/api/consents','POST',{'scope':'health','granted':False,'confirmed_by_voice':False,'updated_by':'test'}); check('رضایت سلامت برای این تست لغو شد',s==200,(s,j))
s,j=req('/api/caregiver/session','POST',{'phone':'09128888888'}); check('بدون رضایت سالمند = 403',s==403 and j.get('error')=='senior_consent_not_granted',(s,j))
s,j=req('/api/consents','POST',{'scope':'health','granted':True,'confirmed_by_voice':True,'updated_by':'senior'}); check('رضایت صوتی سلامت ثبت شد',s==200,(s,j))
s,j=req('/api/caregiver/session','POST',{'phone':'09128888888'}); check('با رضایت = توکن نشست',s==201 and bool(j.get('token')),(s,j)); tok=j.get('token')
H={'X-Caregiver-Token':tok or ''}
s,j=req('/api/caregiver/panel',headers=H); check('پنل با توکن = 200',s==200,(s,j))
check('پنل شامل دارو/هشدار/علائم/صف است',all(k in j for k in ('medications','open_alerts','symptoms','pending_actions')),(s,list(j)))
s,j=req('/api/caregiver/panel',headers={'X-Caregiver-Token':'bad-token'}); check('توکن نامعتبر = 403',s==403,(s,j))

print('--- 5) پیام و درخواست تماس برای مراقب (بند ۳ MVP) ---')
s,j=req('/api/contacts','POST',{'name':'مراقب مرحله دو','phone':'09128888888','relationship':'family'}); cid=j.get('id')
s,j=req('/api/messages','POST',{'contact_id':cid,'body':'حالت چطور است؟','kind':'text'}); check('پیام صف می‌شود + action_id',s==201 and j.get('status')=='queued' and j.get('action_id'),(s,j)); aid=j.get('action_id'); mid=j.get('id')
s,j=req('/api/caregiver/actions'); pend=[a for a in j.get('items',[]) if a['status']=='pending']
check('اقدام در انتظار در صف مراقب دیده می‌شود',any(a['id']==aid for a in pend),(s,len(pend)))
s,j=req('/api/caregiver/actions/'+str(aid)+'/deliver','POST',{'delivered_by':'مراقب مرحله دو'}); check('تحویل اقدام',s==200 and j.get('status')=='delivered',(s,j))
s,j=req('/api/messages'); row=[m for m in j.get('items',[]) if m['id']==mid]
check('وضعیت پیام از queued به delivered رفت',bool(row) and row[0]['status']=='delivered',(s,row))
s,j=req('/api/caregiver/call-request','POST',{'reason':'احساس تنگی نفس'}); check('درخواست تماس در صف می‌نشیند',s==201 and j.get('status')=='pending' and j.get('reply'),(s,j))
s,j=req('/api/caregiver/panel',headers=H); check('درخواست تماس در پنل مراقب هست',any(a['kind']=='call_request' for a in j.get('pending_actions',[])),(s,j))
s,j=req('/api/caregiver/session/revoke','POST',headers=H); check('لغو نشست مراقب',s==200,(s,j))
s,j=req('/api/caregiver/panel',headers=H); check('پس از لغو، پنل بسته می‌شود',s==403,(s,j))

print(f'STAGE-2 TEST: {total} checks; failures={len(failures)}')
if failures: print('FAILED:',', '.join(failures)); sys.exit(1)
print('Stage-2 MVP test passed')
