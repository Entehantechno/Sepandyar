"""سپندیار — transactions

درج تراکنش کیف پول با کلید تکرارناپذیری.

insert_transaction() به جای «SELECT سپس INSERT» اول INSERT می‌کند و نقض
قید UNIQUE را نشانهٔ درخواست تکراری می‌گیرد؛ سپس rollback می‌کند (چون
UPDATE کیف پول در همان تراکنشِ commit‌نشده است، بازنده پول را جابه‌جا
نمی‌کند)، برنده را دوباره می‌خواند و آن را با replayed=True برمی‌گرداند.

نقضِ بدون کلیدِ مطابق دوباره raise می‌شود تا پنهان نماند. پیش از این،
بازندهٔ رقابت IntegrityError می‌گرفت و کارخواه ۵۰۰ می‌دید، هرچند پول
هرگز دوبار خرج نمی‌شد.
"""
import json, sqlite3, os, uuid, datetime, hashlib, re, difflib, time, secrets, hmac, threading, html, math, urllib.request as ureq, urllib.error as uerr
from zoneinfo import ZoneInfo
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, quote, unquote, parse_qs

from .clock import now

def insert_transaction(c,tid,kind,amount,description,key):
 """درج تراکنش با کلید تکرارناپذیری؛ برندهٔ واقعی را پایگاه‌داده تعیین می‌کند.

 دو درخواست همزمان با یک کلید، هر دو SELECT را «خالی» می‌بینند و هر دو درج
 می‌کنند. تا پیش از این، استثنا‌ی نقض UNIQUE تا هندلر سراسری بالا می‌رفت و
 کلاینت ۵۰۰ می‌گرفت — برای مسیر پرداخت بدترین سیگنال ممکن، چون پرداخت در
 واقع «موفق» بوده و کلاینت با دیدن ۵۰۰ یا دوباره تلاش می‌کند یا به کاربر
 خطا نشان می‌دهد. پول هیچ‌وقت دوبار خرج نمی‌شد (UNIQUE جلوی درج دوم را
 می‌گرفت)، ولی پاسخ غلط بود.

 حالا نقض UNIQUE یعنی «درخواست همزمان دیگری برده است» و پاسخِ همان برنده
 بازپخش می‌شود. UPDATE کیف پول در همان تراکنشِ commit‌نشده است، پس rollback
 آن را هم برمی‌گرداند و بازنده پولی جابه‌جا نمی‌کند.

 بازگشت: (True, tid) اگر این درخواست برنده شد، وگرنه (False, id برنده).
 """
 try:
  c.execute('INSERT INTO transactions(id,kind,amount,description,created_at,idempotency_key) VALUES(?,?,?,?,?,?)',
            (tid,kind,amount,description,now(),key))
  return True,tid
 except sqlite3.IntegrityError:
  c.rollback()
  row=c.execute('SELECT id FROM transactions WHERE idempotency_key=?',(key,)).fetchone()
  # اگر ردیفی با این کلید نیست، نقض UNIQUE از جای دیگری آمده (مثلاً id تکراری)
  # و نباید بی‌صدا به بازپخش تبدیل شود.
  if row is None: raise
  return False,row['id']
