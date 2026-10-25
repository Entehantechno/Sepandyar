"""سپندیار — proactive

پرامپت‌های پیش‌دستانه، پله‌بادی و زمان‌بند پس‌زمینه.

collect_due_prompts() سررسیدها را با INSERT شرطی اتمیک ثبت می‌کند
(تصاحب با WHERE NOT EXISTS + سنجش cur.rowcount) تا فراخوانی‌های همزمان
یک سررسید، چند پرامپت نسازند. scheduler_loop() در یک رشتهٔ درون‌فرایندی
با فاصلهٔ ۶۰ ثانیه اجرا می‌شود و اتصال خودش را در finally می‌بندد.

محدودیت شناخته‌شده: این cron یا systemd نیست؛ اجرای از دست رفته پس از
راه‌اندازی مجدد جبران نمی‌شود.
"""
import json, sqlite3, os, uuid, datetime, hashlib, re, difflib, time, secrets, hmac, threading, html, math, urllib.request as ureq, urllib.error as uerr
from zoneinfo import ZoneInfo
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, quote, unquote, parse_qs

from .caregiver import enqueue_caregiver_action,open_alert,primary_caregiver
from .clock import local_now,now
from .config import DB
from .primitives import rows

# ============== بخش ۶: پیش‌دستی — پرامپت‌های زمان‌دار و زمان‌بند پس‌زمینه ==============
PROACTIVE_PROMPTS=[('morning_checkin','09:00','صبح بخیر. حال روحی و انرژی امروزتان چطور است؟'),
                   ('blood_pressure','09:30','اگر آماده‌اید، لطفاً فشار خونتان را بگیرید و عددش را به من بگویید.'),
                   ('evening_checkin','20:00','امروز حالتان چطور گذشت؟ درد یا ناراحتی جدیدی دارید؟')]

PROACTIVE_ESCALATE_MIN=45   # دقیقه بی‌پاسخی پیش از خبر دادن مراقب

def collect_due_prompts(c,at_local=None):
 """یادآورهای پیش‌دستانه‌ای که الان سررسیدشان است. هم endpoint و هم زمان‌بند صدایش می‌زنند."""
 nl=at_local or local_now()
 hhmm=nl.strftime('%H:%M'); day=nl.date().isoformat(); out=[]
 for kind,at,text in PROACTIVE_PROMPTS:
  delta=abs((datetime.datetime.strptime(hhmm,'%H:%M')-datetime.datetime.strptime(at,'%H:%M')).total_seconds())
  if delta<=300:
   # تصاحب اتمیک در یک دستور: پیش از این endpoint و زمان‌بند هر دو SELECT را
   # «خالی» می‌دیدند و برای یک سررسید چند پرامپت تکراری ساخته می‌شد.
   eid=str(uuid.uuid4())
   cur=c.execute("INSERT INTO proactive_events(id,kind,prompt_date,delivered_at,response,responded_at,escalated_at) SELECT ?,?,?,?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM proactive_events WHERE kind=? AND prompt_date=?)",(eid,kind,day,now(),None,None,None,kind,day))
   if cur.rowcount: out.append({'id':eid,'kind':kind,'text':text,'prompt_date':day})
 c.commit(); return out

def escalate_stale_prompts(c):
 """پیش‌دستی واقعی یعنی همین: اگر سالمند جواب نداد، خانواده باخبر شود.
 MediSafe حدود یک ساعت صبر می‌کند و بازه‌اش قابل تغییر نیست؛ این‌جا قابل تنظیم است."""
 escalated=[]
 for r in rows(c,"SELECT * FROM proactive_events WHERE responded_at IS NULL AND delivered_at IS NOT NULL AND escalated_at IS NULL"):
  try: age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(r['delivered_at'])).total_seconds()/60
  except Exception: continue
  if age<PROACTIVE_ESCALATE_MIN: continue
  prompt=next((t for k,_a,t in PROACTIVE_PROMPTS if k==r['kind']),r['kind'])
  # تصاحب اتمیک: شرط «escalated_at IS NULL» درون خود UPDATE است و rowcount نتیجه را
  # می‌گوید. پیش از این انتخاب و نوشتن دو مرحله بود و scheduler با درخواست همزمان
  # هر دو رد می‌شدند — برای یک رویداد بی‌پاسخ، ۶ هشدار و ۶ کنش تکراری ساخته می‌شد.
  cur=c.execute('UPDATE proactive_events SET escalated_at=? WHERE id=? AND escalated_at IS NULL',(now(),r['id']))
  if not cur.rowcount: continue   # دیگری زودتر تصاحب کرد
  cg=primary_caregiver(c) or {}
  enqueue_caregiver_action(c,'call_request',{'phone':cg.get('phone',''),'caregiver':cg.get('name',''),'reason':'سالمند به یادآوری «'+prompt+'» پاسخ نداد.'})
  open_alert(c,'proactive_no_response','یادآوری «'+prompt+'» بی‌پاسخ ماند.','warning'); escalated.append(r['id'])
 c.commit(); return escalated

def scheduler_loop(interval=60):
 """محرک پس‌زمینه. تا پیش از این پیش‌دستی فقط on-demand بود: اگر کسی نمی‌پرسید،
 هیچ‌گاه رخ نمی‌داد. ElliQ برعکس عمل می‌کند — خودش شروع می‌کند."""
 while True:
  try:
   c=sqlite3.connect(DB,timeout=15); c.row_factory=sqlite3.Row
   try: collect_due_prompts(c); escalate_stale_prompts(c)
   finally: c.close()
  except Exception: pass
  time.sleep(interval)
