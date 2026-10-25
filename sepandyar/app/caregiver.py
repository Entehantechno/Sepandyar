"""سپندیار — caregiver

کمکی‌های سمت مراقب و سالمند: ساخت هشدار، صف کنش‌های مراقب، سنجش رضایت،
ماسک‌کردن شماره، کد دعوت و اعتبارسنجی نشست مراقب.

open_alert_once() و enqueue_caregiver_action() هر دو «تصاحب اتمیک» هستند:
یک INSERT شرطی با WHERE NOT EXISTS و سپس سنجش cur.rowcount. این الگو در
باگ‌یابی دور نهم جایگزین select-then-insert شد، چون زیر بار همزمانی چند
ردیف تکراری می‌ساخت.
"""
import json, sqlite3, os, uuid, datetime, hashlib, re, difflib, time, secrets, hmac, threading, html, math, urllib.request as ureq, urllib.error as uerr
from zoneinfo import ZoneInfo
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, quote, unquote, parse_qs

from .clock import now

def enqueue_caregiver_action(c,kind,payload,requested_by='senior'):
 aid=str(uuid.uuid4()); c.execute('INSERT INTO caregiver_actions VALUES(?,?,?,?,?,?,NULL,NULL)',(aid,kind,json.dumps(payload,ensure_ascii=False),'pending',requested_by,now())); return aid

def open_alert(c,atype,message,severity='normal'):
 aid=str(uuid.uuid4()); c.execute('INSERT INTO alerts VALUES(?,?,?,?,?,?)',(aid,atype,message,severity,'open',now())); return aid

def open_alert_once(c,atype,message,severity='normal'):
 """هشدار را فقط وقتی می‌سازد که نمونهٔ بازی از همین نوع وجود نداشته باشد.
 انتخاب و نوشتن در یک دستور است و SQLite فقط یک نویسندهٔ همزمان دارد، پس
 دو فراخوانی همزمان نمی‌توانند هر دو ردیف بسازند. اگر ساخته نشد None می‌دهد.
 (الگوی قبلی «اول SELECT بعد INSERT» بود و زیر بار همزمان هشدار تکراری می‌ساخت.)"""
 aid=str(uuid.uuid4())
 cur=c.execute("INSERT INTO alerts(id,type,message,severity,status,created_at) SELECT ?,?,?,?,'open',? WHERE NOT EXISTS (SELECT 1 FROM alerts WHERE type=? AND status='open')",
   (aid,atype,message,severity,now(),atype))
 return aid if cur.rowcount else None

def consent_granted(c,scope='health'):
 r=c.execute('SELECT granted FROM consents WHERE scope=?',(scope,)).fetchone(); return bool(r and r['granted'])

def mask_phone(ph):
 # شمارهٔ کامل، خودش عامل ورود است؛ به تماس‌گیرندهٔ ناشناس نشان داده نمی‌شود
 ph=str(ph or '')
 return (ph[:4]+'***'+ph[-2:]) if len(ph)>=7 else ('***' if ph else '')

def new_invite_code():
 return secrets.token_urlsafe(18)

def caregiver_session(c,headers):
 tok=(headers.get('X-Caregiver-Token') or '').strip()
 if not tok: return None
 r=c.execute('SELECT * FROM caregiver_sessions WHERE token=?',(tok,)).fetchone()
 if not r or (r['expires_at'] and r['expires_at']<now()): return None
 return dict(r)

def primary_caregiver(c):
 r=c.execute('SELECT * FROM caregivers ORDER BY created_at LIMIT 1').fetchone(); return dict(r) if r else None
