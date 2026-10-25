"""سپندیار — domain"""
import json, sqlite3, os, uuid, datetime, hashlib, re, difflib, time, secrets, hmac, threading, html, math, urllib.request as ureq, urllib.error as uerr
from zoneinfo import ZoneInfo
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, quote, unquote, parse_qs

from .clock import now
from .primitives import rows

# ================= بخش ۷: ابزار دامنه — ساعت، سکوت، فاصله، اشتراک =================
def as_hhmm(v):
 """مرز ورودی: HH:MM را تجزیه می‌کند و اگر معتبر نبود None می‌دهد.
 پیش از این مقدار خام در پایگاه‌داده ذخیره می‌شد و خواننده‌اش با
 strptime می‌شکست — یعنی یک نوشتن بد، اندپوینت را برای همیشه از کار می‌انداخت."""
 if not isinstance(v,str): return None
 try: datetime.datetime.strptime(v,'%H:%M')
 except Exception: return None
 return v

def in_quiet_window(current,start,end):
 from datetime import datetime
 # دادهٔ کهنهٔ ناسالم نباید هستهٔ یادآور را از کار بیندازد؛ در آن حالت
 # «ساعت سکوت نداریم» امن‌ترین پیش‌فرض است چون یادآوری را سرکوب نمی‌کند.
 try:
  c=datetime.strptime(current,'%H:%M').time(); s=datetime.strptime(start,'%H:%M').time(); e=datetime.strptime(end,'%H:%M').time()
 except Exception: return False
 return (s<=c<e) if s<e else (c>=s or c<e)

def distance_m(lat1,lon1,lat2,lon2):
 import math
 r=6371000; p=math.pi/180; a=0.5-math.cos((lat2-lat1)*p)/2+math.cos(lat1*p)*math.cos(lat2*p)*(1-math.cos((lon2-lon1)*p))/2
 return 2*r*math.asin(math.sqrt(a))

def share_payload(c,token):
 s=c.execute('SELECT * FROM shares WHERE token=? AND revoked=0',(token,)).fetchone()
 if not s or s['expires_at']<now(): return None
 profile=c.execute('SELECT name,age,needs FROM profile WHERE id=1').fetchone()
 return {'share_token':token,'expires_at':s['expires_at'],'profile':dict(profile) if profile else {},'vitals':rows(c,'SELECT type,value,source,measured_at FROM vitals ORDER BY measured_at DESC LIMIT 100'),'medications':[]}
