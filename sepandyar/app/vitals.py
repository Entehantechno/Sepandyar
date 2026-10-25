"""سپندیار — vitals

ارزیابی علائم حیاتی و تشخیص هشدار.

evaluate_vital() هر نوع را با آستانهٔ خودش می‌سنجد (systolic، diastolic،
glucose، weight، heart_rate) و وزنِ خارج از بازه را critical می‌دهد —
پیش از آن weight=۱ «normal» شمرده می‌شد. detect_deviation_alerts() انحراف
از خط پایهٔ خودِ کاربر را محاسبه می‌کند، نه فقط عبور از آستانهٔ مطلق.
"""
import json, sqlite3, os, uuid, datetime, hashlib, re, difflib, time, secrets, hmac, threading, html, math, urllib.request as ureq, urllib.error as uerr
from zoneinfo import ZoneInfo
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, quote, unquote, parse_qs

from .caregiver import enqueue_caregiver_action,open_alert_once,primary_caregiver
from .clock import now
from .primitives import num,rows

# ================ بخش ۴: علائم حیاتی — آستانه‌ها، خط پایه و انحراف ================
def evaluate_vital(c,kind,value):
 vals=[]
 if kind=='blood_pressure' and isinstance(value,dict): vals=[('systolic',num(value.get('systolic'))),('diastolic',num(value.get('diastolic')))]
 elif kind in ('glucose','weight','heart_rate'): vals=[(kind,num(value.get('value') if isinstance(value,dict) else value))]
 results=[]; critical=False; abnormal=False
 for t,v in vals:
  if v is None: continue
  r=c.execute('SELECT * FROM vital_thresholds WHERE type=?',(t,)).fetchone()
  if not r: continue
  # آستانه‌ها در ستون TEXT نگه داشته می‌شوند؛ اگر مقدارشان عدد نباشد
  # float() با ValueError کل ثبت علامت حیاتی را ۵۰۰ می‌کرد.
  try: nmin=float(r['normal_min']); nmax=float(r['normal_max']); cmin=float(r['critical_min']); cmax=float(r['critical_max'])
  except (TypeError,ValueError): continue
  normal=nmin<=v<=nmax; severe=v<cmin or v>cmax
  results.append({'type':t,'value':v,'status':'normal' if normal else ('critical' if severe else 'out_of_range'),'normal_min':r['normal_min'],'normal_max':r['normal_max']})
  abnormal|=not normal; critical|=severe
 if abnormal:
  severity='critical' if critical else 'warning'; message='علائم حیاتی خارج از محدوده شخصی‌سازی‌شده ثبت شد.'
  aid=str(uuid.uuid4()); c.execute('INSERT INTO alerts VALUES(?,?,?,?,?,?)',(aid,'vital_'+severity,message,severity,'open',now()))
  c.execute('INSERT INTO events VALUES(?,?,?,?)',(str(uuid.uuid4()),'vital_alert',json.dumps({'alert_id':aid,'results':results},ensure_ascii=False),now()))
  c.commit()
 return {'status':'critical' if critical else ('out_of_range' if abnormal else 'normal'),'results':results,'notify_senior':abnormal,'notify_caregivers':abnormal,'request_emergency_call':critical}

def vital_numbers(c,limit=200):
 """تاریخچهٔ عددی علائم حیاتی. value به‌صورت JSON ذخیره می‌شود، پس باز کردنش لازم است."""
 out={}
 for r in rows(c,'SELECT type,value,measured_at FROM vitals ORDER BY measured_at DESC LIMIT ?',(limit,)):
  try: v=json.loads(r['value'])
  except Exception: v=None
  pairs=[('systolic',num(v.get('systolic'))),('diastolic',num(v.get('diastolic')))] if (r['type']=='blood_pressure' and isinstance(v,dict)) \
        else [(r['type'],num(v.get('value') if isinstance(v,dict) else v))]
  for t,val in pairs:
   if val is None: continue
   out.setdefault(t,[]).append((val,r['measured_at']))
 return out

def baseline_report(c):
 """انحراف از خط پایهٔ شخصی، نه فقط آستانهٔ مطلق.
 آستانهٔ ثابت یک عدد را برای همه یکی می‌داند؛ ولی افتِ ناگهانیِ فشارِ کسی که همیشه
 ۱۵۰ بوده، همان‌قدر مهم است که عبورِ فردِ دیگری از ۱۴۰. هوشیارینو روی همین ساخته شده."""
 import statistics as st
 out=[]
 for t,vals in sorted(vital_numbers(c).items()):
  nums=[v for v,_a in vals]
  if len(nums)<3: continue
  mean=st.mean(nums); sd=st.pstdev(nums) or 0.0
  latest=vals[0][0]
  z=((latest-mean)/sd) if sd>0 else 0.0
  drift='stable' if abs(z)<1.5 else ('rising' if z>0 else 'falling')
  out.append({'type':t,'sample_count':len(nums),'mean':round(mean,2),'stddev':round(sd,2),
              'latest':latest,'latest_at':vals[0][1],'z_score':round(z,2),'trend':drift,
              'deviation':abs(z)>=2.0})
 return out

def detect_deviation_alerts(c,report=None):
 """انحراف معنادار را به هشدار تبدیل می‌کند؛ تکراری نمی‌سازد."""
 made=[]
 for b in (report or baseline_report(c)):
  if not b['deviation']: continue
  sig='baseline_deviation:'+b['type']
  aid=open_alert_once(c,sig,'انحراف معنادار در '+b['type']+': آخرین مقدار '+str(b['latest'])+' در برابر میانگین '+str(b['mean'])+' (z='+str(b['z_score'])+')','warning')
  if not aid: continue   # دیگری زودتر ساخت؛ کنش مراقب هم تکرار نشود
  cg=primary_caregiver(c) or {}
  if cg: enqueue_caregiver_action(c,'call_request',{'phone':cg.get('phone',''),'caregiver':cg.get('name',''),'reason':'انحراف در '+b['type']+' مشاهده شد.'})
  made.append(aid)
 c.commit(); return made
