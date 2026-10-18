import json, time, urllib.request, urllib.error, sys
BASE='http://127.0.0.1:4174'
def req(path,method='GET',data=None,headers=None):
 body=json.dumps(data,ensure_ascii=False).encode() if data is not None else None
 r=urllib.request.Request(BASE+path,method=method,data=body,headers={'Content-Type':'application/json',**(headers or {})})
 t=time.perf_counter()
 try:
  with urllib.request.urlopen(r,timeout=5) as x:return x.status,json.loads(x.read()),(time.perf_counter()-t)*1000
 except urllib.error.HTTPError as e:return e.code,json.loads(e.read() or b'{}'),(time.perf_counter()-t)*1000

def check(name,cond,ms=None):
 global total
 total+=1
 label=f'✅ {name}' if cond else f'❌ {name}'
 if ms is not None: label+=f' ({ms:.1f}ms)'
 print(label)
 if not cond: failures.append(name)
failures=[];total=0
checks=[('/api/health','GET',None,200),('/api/profile','GET',None,200),('/api/caregivers','GET',None,200),('/api/medications','GET',None,200),('/api/vitals','GET',None,200),('/api/vitals/thresholds','GET',None,200),('/api/reminder-settings','GET',None,200),('/api/reminders/due','GET',None,200),('/api/proactive/due','GET',None,200),('/api/icope/summary','GET',None,200),('/api/pantry','GET',None,200),('/api/doctors','GET',None,200),('/api/appointments','GET',None,200),('/api/contacts','GET',None,200),('/api/messages','GET',None,200),('/api/emergency-card','GET',None,200),('/api/safe-zones','GET',None,200),('/api/care-circle/summary','GET',None,200)]
for p,m,d,w in checks:
 s,j,ms=req(p,m,d);check(p,s==w,ms)
s,j,ms=req('/api/profile','POST',{'name':'تست سرعت','age':70,'needs':'فشار خون','assistant_name':'همراه'});check('profile write',s==200,ms)
# شمارهٔ یکتا در هر اجرا: شمارهٔ تکراری حالا 409 می‌دهد (قید یکتا روی phone)
_phone='093%08d'%(time.time_ns()%100000000)
s,j,ms=req('/api/caregivers','POST',{'name':'مراقب تست','phone':_phone,'permissions':['health']});check('caregiver create',s==201,ms)
s,jj,ms2=req('/api/caregivers','POST',{'name':'مراقب تست','phone':_phone,'permissions':['health']});check('شمارهٔ تکراری = 409',s==409 and jj.get('error')=='caregiver_exists',ms2)
invite=j.get('invite_code');check('invite code issued',bool(invite) and len(invite)>=16,ms)
s,j,ms=req('/api/consents','POST',{'scope':'health','granted':True});check('senior consent',s==200,ms)
s,j,ms=req('/api/caregiver/session','POST',{'phone':_phone,'code':invite});check('caregiver session',s==201 and bool(j.get('token')),ms)
AH={'X-Caregiver-Token':j.get('token') or ''}
for ap in ['/api/admin/overview','/api/admin/activity','/api/admin/ai-config']:
 s2,j2,ms2=req(ap);check(ap+' بدون نشست مراقب = 403',s2==403 and j2.get('error')=='caregiver_session_required',ms2)
 s3,j3,ms3=req(ap,'GET',None,AH);check(ap+' با نشست مراقب = 200',s3==200,ms3)
s,j,ms=req('/api/medications','POST',{'name':'داروی تست','time':'09:00','instructions':'بعد صبحانه'});check('medication create',s==201,ms);mid=j.get('id')
s,j,ms=req('/api/medications/'+str(mid)+'/event','POST',{'event':'taken'});check('medication event',s==200 and j.get('status')=='taken',ms)
s,j,ms=req('/api/vitals','POST',{'type':'blood_pressure','value':{'systolic':120,'diastolic':80},'source':'test'});check('normal vital',s==201 and j['evaluation']['status']=='normal',ms)
s,j,ms=req('/api/vitals','POST',{'type':'blood_pressure','value':{'systolic':190,'diastolic':130},'source':'test'});check('critical vital + alert',s==201 and j['evaluation']['request_emergency_call'],ms)
s,j,ms=req('/api/icope','POST',{'domain':'locomotion','score':8,'notes':'خوب','assessed_by':'senior'});check('icope create',s==201 and j['status']=='good',ms)
s,j,ms=req('/api/checkins','POST',{'mood':'خوب','pain':'ندارم','sleep':'خوب'});check('checkin create',s==201,ms)
s,j,ms=req('/api/care-tasks','POST',{'title':'آب خوردن','kind':'routine','assigned_to':'senior','due_at':'12:00'});check('care task create',s==201,ms)
s,j,ms=req('/api/safe-zones','POST',{'name':'خانه تست','lat':32.78,'lon':-96.8,'radius_m':200});check('safe zone create',s==201,ms)
s,j,ms=req('/api/location','POST',{'lat':32.79,'lon':-96.8,'accuracy':10});check('location + geofence',s==201 and isinstance(j.get('outside_zones'),list),ms)
s,j,ms=req('/api/doctors','POST',{'name':'دکتر تست','specialty':'cardiology','phone':'02100000000','clinic':'کلینیک تست','address':'خیابان تست','preferred':True});check('doctor create',s==201,ms); doctor_id=j.get('id')
s,j,ms=req('/api/appointments','POST',{'title':'ویزیت قلب','doctor_id':doctor_id,'starts_at':'2026-08-20T10:00:00+03:30','reminder_minutes':60});check('appointment create',s==201,ms)
s,j,ms=req('/api/contacts','POST',{'name':'مخاطب تست','phone':'09120000000','relationship':'family'});check('contact create',s==201,ms); contact_id=j.get('id')
s,j,ms=req('/api/messages','POST',{'contact_id':contact_id,'body':'پیام تست','kind':'voice'});check('message queue',s==201 and j.get('status')=='queued',ms)
s,j,ms=req('/api/emergency-card','POST',{'full_name':'مریم تست','allergies':'پنی‌سیلین','conditions':'فشار خون'});check('emergency card write',s==200,ms)
s,j,ms=req('/api/reminder-settings','POST',{'quiet_start':'22:00','quiet_end':'07:00','max_nudges':2,'preferred_channel':'voice'});check('reminder settings write',s==200,ms)
s,j,ms=req('/api/pantry','POST',{'items':[{'name':'تخم مرغ','quantity':'۲ عدد'},{'name':'گوجه','quantity':'۳ عدد'}]});check('pantry create',s==201,ms)
s,j,ms=req('/api/recipes/suggest','POST',{'items':['تخم مرغ','گوجه']});check('recipe suggestion',s==200 and (j.get('recipes') or j.get('spoken_suggestion')),ms)
s,j,ms=req('/api/vitals/share','POST',{'expires_days':1});token=j.get('token');check('doctor share create',s==201 and bool(token),ms)
s,j,ms=req('/api/vitals/share/revoke','POST',{'token':token});check('doctor share revoke',s==200,ms)
s,j,ms=req('/api/ai/chat','POST',{'text':'سلام'});check('AI safe unavailable response',s in (200,503),ms)
# performance: 20 lightweight health requests
samples=[]
for _ in range(20): samples.append(req('/api/health')[2])
avg=sum(samples)/len(samples); p95=sorted(samples)[int(.95*len(samples))-1]
check('health average latency < 250ms',avg<250,avg);check('health p95 latency < 500ms',p95<500,p95)
print(f'FULL PLATFORM TEST: {total} checks; failures={len(failures)}; avg={avg:.1f}ms; p95={p95:.1f}ms')
if failures: print('FAILED:',', '.join(failures));sys.exit(1)
