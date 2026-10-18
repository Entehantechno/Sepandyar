import json, urllib.request, urllib.error, sys
BASE='http://127.0.0.1:4174'
def req(path,method='GET',data=None,headers=None):
 r=urllib.request.Request(BASE+path,method=method,headers={'Content-Type':'application/json',**(headers or {})},data=json.dumps(data,ensure_ascii=False).encode() if data is not None else None)
 try:
  with urllib.request.urlopen(r,timeout=5) as x:return x.status,json.loads(x.read())
 except urllib.error.HTTPError as e:
  try: return e.code,json.loads(e.read() or b'{}')
  except Exception: return e.code,{}
def ok(name,cond):
 print(('✅' if cond else '❌'),name)
 if not cond: raise SystemExit(1)
status,h=req('/api/health');ok('health',status==200 and h['ok'])
status,_=req('/api/profile','POST',{'name':'مریم تست','age':72,'needs':'فشار خون','assistant_name':'نازنین'});ok('profile write',status==200)
status,p=req('/api/profile');ok('profile read',p.get('name')=='مریم تست')
import time as _t
_PH='096%08d'%(_t.time_ns()%100000000)
status,c=req('/api/caregivers','POST',{'name':'علی تست','phone':_PH,'permissions':['wallet','health']});ok('caregiver write',status==201)
status,m=req('/api/medications','POST',{'name':'داروی تست','time':'09:00','instructions':'بعد صبحانه'});ok('medication write',status==201); mid=m['id']
status,e=req('/api/medications/'+mid+'/event','POST',{'event':'taken'});ok('medication event',status==200 and e['status']=='taken')
status,v=req('/api/vitals','POST',{'type':'blood_pressure','value':{'systolic':120,'diastolic':80},'source':'test'});ok('normal vital',status==201 and v['evaluation']['status']=='normal')
status,v=req('/api/vitals','POST',{'type':'blood_pressure','value':{'systolic':190,'diastolic':130},'source':'test'});ok('critical vital',status==201 and v['evaluation']['request_emergency_call'])
key='qa-wallet-unique-1';status,a=req('/api/wallet/topups','POST',{'amount':100,'description':'QA'}, {'Idempotency-Key':key});status,b=req('/api/wallet/topups','POST',{'amount':100,'description':'QA'}, {'Idempotency-Key':key});ok('wallet idempotency',a['transaction_id']==b['transaction_id'])
status,s=req('/api/vitals/share','POST',{'expires_days':1});ok('share create',status==201 and s.get('token'))
status,_=req('/api/vitals/share/revoke','POST',{'token':s['token']});ok('share revoke',status==200)
# req دیگر HTTPError پرتاب نمی‌کند (وگرنه سوئیت نصفه‌کاره می‌مرد)؛ پس کد بازگشتی بررسی می‌شود
status,_=req('/share/'+s['token']);ok('revoked share blocked',status==404)
print('MVP smoke test passed')
