"""سپندیار — primitives"""
import json, sqlite3, os, uuid, datetime, hashlib, re, difflib, time, secrets, hmac, threading, html, math, urllib.request as ureq, urllib.error as uerr
from zoneinfo import ZoneInfo
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, quote, unquote, parse_qs

from .config import MAX_BODY_BYTES

# ============ بخش ۳: لایهٔ HTTP — بدنهٔ درخواست، پاسخ، و پاک‌سازی ورودی ============
# هر تجزیه و اعتبارسنجی ورودی در همین بخش انجام می‌شود («تجزیه در مرز»)،
# تا کسب‌وکار پایین‌تر هرگز مقدار خام یا نامعتبر نبیند.
_SURR=re.compile(r'[\ud800-\udfff]')

def desurrogate(v):
 """سورگیت جفت‌نشده را با U+FFFD جایگزین می‌کند.

 json.loads یک \ud800 تنها را می‌پذیرد (JSON اجازهٔ escape نیم‌جفت را می‌دهد)،
 ولی پایگاه‌داده نمی‌تواند آن را UTF-8 کند؛ نتیجه UnicodeEncodeError و ۵۰۰ بود.
 اینجا گلوگاه مشترک همهٔ اندپوینت‌هاست، پس یک بار و برای همه بسته می‌شود.
 """
 if isinstance(v,str): return _SURR.sub('\ufffd',v)
 if isinstance(v,dict): return {(desurrogate(k) if isinstance(k,str) else k):desurrogate(x) for k,x in v.items()}
 if isinstance(v,list): return [desurrogate(x) for x in v]
 return v

def body(h):
 """بدنهٔ JSON را می‌خواند. خطای تجزیه را روی خود نمونهٔ handler علامت می‌زند
(نه یک متغیر سراسری) تا در سرور نخی بین درخواست‌ها نشت نکند."""
 h._body_error=False
 h._body_too_large=False
 try:
  n=int(h.headers.get('Content-Length','0'))
  # سقف اندازهٔ بدنه، پیش از خواندن حتی یک بایت. خواندن هدر تقریباً رایگان
  # است ولی read(n) با n بزرگ همان حجم را در حافظه نگه می‌دارد و سپس در
  # پایگاه‌داده نوشته می‌شود؛ اندازه‌گیری شد: یک بدنهٔ ۲۰۰MB پایگاه‌داده را
  # برای همیشه به ۲۲۱MB رساند (۲۲۰MB صفحهٔ مرده که بدون VACUUM برنمی‌گردد).
  if n<0:
   h._body_error=True
   return {}
  if n>MAX_BODY_BYTES:
   h._body_too_large=True
   return {}
  # n اکنون در بازهٔ [۰, MAX] است، پس خودِ خواندن هم کران‌دار است.
  raw=h.rfile.read(n)
  if not raw or not raw.strip(): return {}
  v=json.loads(raw)
  if not isinstance(v,dict):
   # [] و null و "x" هم JSON معتبرند، ولی بدنهٔ این API باید شیء باشد؛
   # وگرنه d.get() روی آن‌ها AttributeError می‌دهد
   h._body_error=True
   return {}
  return desurrogate(v)
 except Exception:
  h._body_error=True
  return {}

def send(h,code,obj):
 raw=json.dumps(obj,ensure_ascii=False).encode()
 h.send_response(code)
 h.send_header('Content-Type','application/json; charset=utf-8')
 h.send_header('Content-Length',str(len(raw)))
 h.send_header('Access-Control-Allow-Origin','*')
 h.end_headers()
 h.wfile.write(raw)

def rows(c,sql,args=()): return [dict(x) for x in c.execute(sql,args).fetchall()]

def num(v):
 try: x=float(v)
 except (TypeError,ValueError): return None
 # json.loads طبق اجازهٔ پایتون لیترال‌های غیرمتناهی را می‌پذیرد: «1e400» به inf
 # تبدیل می‌شود. با inf هر مقایسهٔ آستانه‌ای True می‌شود (inf>cmax یا -inf<cmin)،
 # پس یک ورودی زباله «هشدار بحرانی سلامت» جعلی می‌ساخت و صف مراقب را پر می‌کرد.
 # اندازه‌گیری شد: سه POST با 1e400 → سه هشدار vital_critical.
 return x if math.isfinite(x) else None

def as_int(v,default=0):
 # ورودی نامعتبر باید ۴۰۰ بدهد نه ۵۰۰؛ None و رشتهٔ غیرعددی هم شامل می‌شود
 try: return int(float(v))
 except Exception: return None

def as_float(v):
 # فیلد غایب یا غیرعددی باید 400 بدهد؛ float(None) پیش‌تر 500 می‌داد
 try: x=float(v)
 except Exception: return None
 # inf/NaN هم «غیرمعتبر» است: remaining=inf شمارش دارو را برای همیشه بی‌معنا می‌کرد
 # و refill_threshold=inf هر دارویی را در وضعیت «نیازمند تمدید» نشان می‌داد.
 return x if math.isfinite(x) else None

def as_text(v,default=''):
 # مقدار ساخت‌یافته هرگز نباید به sqlite برود: «type 'dict' is not supported»
 # پیش‌تر ۵۰۰ می‌داد. مثل as_int/as_float، ورودی نامعتبر None می‌دهد تا فراخوان ۴۰۰ برگرداند.
 if v is None: return default
 if isinstance(v,(dict,list)): return None
 return str(v)

def idem_key(h,d,op=''):
 # کلید تکرارناپذیری فقط وقتی معنا دارد که کلاینت آن را بفرستد.
 # کلید مشتق از بدنه، دو تراکنش یکسانِ ولی جدا را یکی می‌کرد و شارژ دوم را بی‌صدا می‌بلعید.
 #
 # کلید باید به عملیات هم مقید باشد، نه سراسری. پیش‌تر جست‌وجو فقط با خودِ
 # کلید بود و دو مسیر یک فضای نام مشترک داشتند؛ در عمل: شارژ ۵۰۰۰ با کلید K
 # موفق می‌شد و بعد «پرداخت ۳۰۰۰ با همان K» پاسخ ۲۰۰ «succeeded» می‌گرفت،
 # در حالی که هیچ پرداختی انجام نشده بود و موجودی دست‌نخورده می‌ماند.
 # پیشوند، فضای نام هر عملیات را جدا می‌کند و چون مقدارِ ذخیره‌شده همچنان
 # یکتا می‌ماند، همان UNIQUE INDEX قبلی مرز همزمانی باقی می‌ماند.
 k=h.headers.get('Idempotency-Key') or d.get('idempotency_key')
 if not k: return 'auto-'+str(uuid.uuid4())
 return (op+'::' if op else '')+str(k)
