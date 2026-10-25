"""سپندیار — live

مسیر صوتی زندهٔ Gemini.

ثابت‌های اتصال (LIVE_WS_BASE، LIVE_MODEL، LIVE_VOICE) و ساخت پیکربندی VAD،
پیکربندی توکن و پرامپت سیستم.

live_vad_config() صبر گفتاری کاربر را به silenceDurationMs نگاشت می‌کند.
دقت شود که wss:// با https:// یکی نیست: در CSP، connect-src باید میزبان
wss را جداگانه فهرست کند و https: به wss: ارتقا نمی‌یابد.
"""
import json, sqlite3, os, uuid, datetime, hashlib, re, difflib, time, secrets, hmac, threading, html, math, urllib.request as ureq, urllib.error as uerr
from zoneinfo import ZoneInfo
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, quote, unquote, parse_qs

from .language import DEFAULT_PATIENCE_MS

# ==================== بخش ۱۰: موتور گفت‌وگوی زنده (Gemini Live) ====================
# ---- موتور گفت‌وگوی زنده (Live) — برگزیده از پژوهش docs/RESEARCH_LIVE_VOICE_AI_FA.md ----
LIVE_TOKEN_URL='https://generativelanguage.googleapis.com/v1beta/auth_tokens'

LIVE_WS_BASE='wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained'

LIVE_MODEL='gemini-3.8-live'

LIVE_VOICE='Kore'

LIVE_MIN_SILENCE_MS=800    # گوگل: کمتر از ۵۰۰–۸۰۰ms جمله را وسط مکث طبیعی می‌شکند

LIVE_MAX_SILENCE_MS=5000   # هم‌سقف با patience_ms مرحلهٔ ۵

LIVE_TOKENS_LIMIT=25000    # آستانهٔ فشرده‌سازی بافت؛ بدون آن توکن صوتی انباشته هر دور دوباره صورتحساب می‌شود

def live_vad_config(patience_ms):
 """صبر گفتاری کاربر (patience_ms) را به تنظیم VAD لایه Live نگاشت می‌کند."""
 try: pat=int(patience_ms)
 except Exception: pat=DEFAULT_PATIENCE_MS
 pat=max(LIVE_MIN_SILENCE_MS,min(LIVE_MAX_SILENCE_MS,pat))
 return {'disabled':False,'startOfSpeechSensitivity':'START_SENSITIVITY_LOW','endOfSpeechSensitivity':'END_SENSITIVITY_LOW','prefixPaddingMs':120,'silenceDurationMs':pat}

def live_token_payload(model=LIVE_MODEL):
 """بدنهٔ درخواست توکن موقت گوگل؛ مدل و مودالیته را در خود توکن قفل می‌کند."""
 exp=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=30)).replace(microsecond=0).isoformat().replace('+00:00','Z')
 return {'uses':1,'expireTime':exp,'liveConnectConstraints':{'model':'models/'+str(model),'config':{'sessionResumption':{},'responseModalities':['AUDIO']}}}

def fetch_live_token(key,model=LIVE_MODEL):
 """توکن موقت را از گوگل می‌گیرد؛ نام توکن را برمی‌گرداند و در صورت خطا None."""
 try:
  r=ureq.Request(LIVE_TOKEN_URL,data=json.dumps(live_token_payload(model),ensure_ascii=False).encode(),headers={'x-goog-api-key':str(key),'Content-Type':'application/json'},method='POST')
  with ureq.urlopen(r,timeout=15) as resp: return str((json.loads(resp.read()) or {}).get('name') or '') or None
 except Exception: return None

def live_system_prompt(c):
 """دستور سامانهٔ فارسی: قید آواشناسی تهرانی + رد صریح دری/عربی + جملهٔ کوتاه."""
 cfg=c.execute('SELECT system_prompt,tone,guardrails FROM ai_config WHERE id=1').fetchone()
 base=(cfg['system_prompt'] if cfg and cfg['system_prompt'] else 'تو دستیار فارسی سالمندان هستی.')
 tone=(cfg['tone'] if cfg and cfg['tone'] else 'گرم، آرام، کوتاه و غیرکودکانه')
 guard=(cfg['guardrails'] if cfg and cfg['guardrails'] else '')
 phon='همیشه به فارسی معیار ایران و با تلفظ تهرانی صحبت کن: ح را «ه» بگو، ق و غ را «غ» فارسی، ط را «ت»، ص و ث را «س»، ض و ظ و ذ را «ز». هرگز با لهجهٔ دری افغانی یا عربی صحبت نکن.'
 style='جمله‌ها کوتاه و با واژه‌های آشنا باشند. از واژهٔ تخصصی و پیچیده پرهیز کن. شمرده و آرام حرف بزن. اگر کاربر وسط جمله مکث کرد، صبر کن و حرفش را قطع نکن.'
 return '\n'.join(x for x in (base,'لحن: '+tone,phon,style,('قواعد ایمنی: '+guard) if guard else '') if x)
