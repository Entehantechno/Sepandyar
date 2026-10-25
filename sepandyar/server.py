#!/usr/bin/env python3
"""سپندیار — نقطهٔ ورود سرور.

کد برنامه در بستهٔ «app» زندگی می‌کند؛ این فایل تنها نقطهٔ ورود و
بازصادرات نام‌های عمومی است تا اسکریپت‌ها و آزمون‌ها همان‌طور که پیش‌تر
«import server» می‌کردند کار کنند. فهرست بخش‌ها در app/ و در هر ماژول
با سرفصل مشخص است.

ترتیب وابستگی ماژول‌ها (هر کدام فقط از بالایی‌ها استفاده می‌کند):
  config → clock → database → primitives → transactions →
  vitals / memory / domain / report → proactive → language → live →
  caregiver → security → handler
"""
import os as _os, sys as _sys

# آزمون‌ها این فایل را با spec_from_file_location بار می‌کنند که پوشهٔ فایل را
# به sys.path اضافه «نمی‌کند»؛ بدون این دو خط، «from app...» پیدا نمی‌شود.
_HERE=_os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path: _sys.path.insert(0,_HERE)

from app.caregiver import enqueue_caregiver_action,open_alert,open_alert_once,consent_granted,mask_phone,new_invite_code,caregiver_session,primary_caregiver
from app.clock import now,LOCAL_TZ,local_now
from app.clock import _tehran_tz
from app.config import ROOT,DB,ROOT,DB,MAX_BODY_BYTES
from app.database import db
from app.domain import as_hhmm,in_quiet_window,distance_m,share_payload
from app.handler import Handler
from app.language import normalize_fa,norm_fa,SMALLTALK,is_smalltalk,IMAGE_UA,OPENVERSE_URL,COMMONS_URL,DEFAULT_PATIENCE_MS,OBJ_SUFFIXES,get_voice_profile,normalize_dialect,strip_obj_suffix,find_alias,learn_alias,match_candidates,net_json,images_from_openverse,images_from_commons,IMAGE_NET,fetch_images,FA_CLITICS,assess_risk
from app.language import _stem,_pattern_hits
from app.live import LIVE_TOKEN_URL,LIVE_WS_BASE,LIVE_MODEL,LIVE_VOICE,LIVE_MIN_SILENCE_MS,LIVE_MAX_SILENCE_MS,LIVE_TOKENS_LIMIT,live_vad_config,live_token_payload,fetch_live_token,live_system_prompt
from app.memory import MEMORY_TURNS,MEMORY_MAX_CHARS,remember,recall,memory_block,conversation_summary,call_llm
from app.primitives import desurrogate,body,send,rows,num,as_int,as_float,as_text,idem_key
from app.primitives import _SURR
from app.proactive import PROACTIVE_PROMPTS,PROACTIVE_ESCALATE_MIN,collect_due_prompts,escalate_stale_prompts,scheduler_loop
from app.report import report_html
from app.report import _e
from app.security import STATIC_ALLOW,CSP,SECURITY_HEADERS
from app.transactions import insert_transaction
from app.vitals import evaluate_vital,vital_numbers,baseline_report,detect_deviation_alerts

# نام‌هایی که اسکریپت‌های بیرونی و آزمون‌ها مستقیم استفاده می‌کنند.
# ureq و ZoneInfo هم بازصادرات می‌شوند چون آزمون‌ها به آن‌ها دست می‌برند:
# test_deployment «m.ureq.urlopen» را وصله می‌کند و «_m14.ZoneInfo» را می‌خواند.
import urllib.request as ureq
from zoneinfo import ZoneInfo
from app.config import ROOT, DB
from app.handler import Handler
from app.proactive import scheduler_loop

__all__=[n for n in dir() if not n.startswith("__")]

if __name__=='__main__':
 import threading
 from http.server import ThreadingHTTPServer
 threading.Thread(target=scheduler_loop,daemon=True).start()
 print('Sepandyar API listening on 0.0.0.0:4174')
 ThreadingHTTPServer(('0.0.0.0',4174),Handler).serve_forever()
