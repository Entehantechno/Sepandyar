"""سپندیار — handler"""
import json, sqlite3, os, uuid, datetime, hashlib, re, difflib, time, secrets, hmac, threading, html, math, urllib.request as ureq, urllib.error as uerr
from zoneinfo import ZoneInfo
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, quote, unquote, parse_qs

from .caregiver import caregiver_session,consent_granted,enqueue_caregiver_action,mask_phone,new_invite_code,open_alert,primary_caregiver
from .clock import local_now,now
from .config import MAX_BODY_BYTES,ROOT
from .database import db
from .domain import as_hhmm,distance_m,in_quiet_window,share_payload
from .language import DEFAULT_PATIENCE_MS,assess_risk,fetch_images,find_alias,get_voice_profile,is_smalltalk,learn_alias,match_candidates,normalize_dialect
from .live import LIVE_MODEL,LIVE_TOKENS_LIMIT,LIVE_VOICE,LIVE_WS_BASE,fetch_live_token,live_system_prompt,live_token_payload,live_vad_config
from .memory import MEMORY_TURNS,call_llm,conversation_summary,recall,remember
from .primitives import as_float,as_int,as_text,body,idem_key,rows,send
from .proactive import collect_due_prompts,escalate_stale_prompts
from .report import report_html
from .security import SECURITY_HEADERS,STATIC_ALLOW
from .transactions import insert_transaction
from .vitals import baseline_report,detect_deviation_alerts,evaluate_vital

# ================= بخش ۱۳: هندلر HTTP و همهٔ مسیرهای API =================
# هر مسیر یک «if p==...» است. مسیرهای /api/caregiver/* باید caregiver_session()
# را صدا بزنند؛ آزمون بخش ۲۳ این قاعده را به‌طور ساختاری پاس می‌دارد.
class Handler(SimpleHTTPRequestHandler):
 # تایم‌اوت سوکت، وگرنه هر اتصال نیمه‌باز یک رشته را برای همیشه نگه می‌دارد.
 # timeout در زنجیرهٔ ارث None است و StreamRequestHandler.setup() فقط وقتی آن
 # را settimeout می‌کند که None نباشد؛ در نتیجه read(n) تا ابد مسدود می‌ماند.
 # اندازه‌گیری شد: ۲۰ اتصال نیمه‌باز → ۲۰ رشتهٔ بلوکه که پس از ۲۵ ثانیه هم
 # آزاد نشدند (سبک slowloris). سقف اندازهٔ بدنه جلوی این را نمی‌گیرد، چون
 # حمله زمان است نه حجم: نگه‌داشتن سوکت برای کلاینت هیچ هزینه‌ای ندارد.
 # BaseHTTPRequestHandler.handle_one_request تایم‌اوت سوکت را پایان درخواست
 # می‌گیرد و اتصال را می‌بندد، پس چیز دیگری لازم نیست تغییر کند.
 # ۳۰ ثانیه با فاصلهٔ امن بالای کُندترین مسیر مشروع است (پروکسی Gemini
 # تایم‌اوت ۱۵ ثانیه دارد).
 timeout=30
 # تنها نقطهٔ گلوگاهی مشترک «همهٔ» پاسخ‌ها: send() برای JSON، send_error() برای خطاها،
 # و send_head() ارثی برای فایل‌های ایستا همگی از end_headers می‌گذرند؛ پس هیچ مسیری
 # جا نمی‌ماند. (همان درسی که در دور یازدهم از do_HEAD گرفتیم: گلوگاه را پایین بگیر.)
 #
 # Strict-Transport-Security (HSTS) عمداً «نیامده»: RFC 6797 می‌گوید این سرآیند فقط باید روی HTTPS فرستاده شود و
 # این سرور HTTP ساده است. پشت پروکسی TLS باید همان‌جا اضافه شود، نه اینجا.
 def end_headers(self):
  for k,v in SECURITY_HEADERS: self.send_header(k,v)
  # دادهٔ سلامت هرگز نباید در حافظهٔ نهان بنشیند؛ پوستهٔ اپ و service worker باید
  # بازاعتبارسنجی شوند تا پس از انتشار، نسخهٔ کهنه روی دستگاه سالمند نماند.
  # self.path در مسیرهای خطای parse_request ممکن است هنوز تنظیم نشده باشد.
  p=(getattr(self,'path','') or '').split('?',1)[0]
  if p.startswith('/api/') or p.startswith('/share/'): self.send_header('Cache-Control','no-store')
  elif p in ('/','/index.html','/caregiver.html','/admin.html','/investor.html','/sw.js','/manifest.webmanifest'): self.send_header('Cache-Control','no-cache')
  super().end_headers()
 def __init__(self,*a,**kw):
  self._db=None
  try: super().__init__(*a,directory=ROOT,**kw)
  finally:
   c=self._db
   if c is not None:
    try: c.rollback()
    except Exception: pass
    try: c.close()
    except Exception: pass
 def do_OPTIONS(self): self.send_response(204); self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Access-Control-Allow-Headers','Content-Type,Idempotency-Key,X-Caregiver-Token'); self.send_header('Access-Control-Allow-Methods','GET,POST,PUT,OPTIONS'); self.end_headers()
 def do_GET(self):
  try: return self._get()
  except ConnectionError:
   return None
  except Exception:
   try: return send(self,500,{'error':'server_error'})
   except Exception: return None
 def send_head(self):
  # آخرین لایهٔ دفاع. do_HEAD در SimpleHTTPRequestHandler مستقیم send_head()
  # را صدا می‌زند و اصلاً از do_GET نمی‌گذرد، پس دروازهٔ allowlist در _get
  # برای HEAD بی‌اثر بود: «HEAD /sepandyar.db» با ۲۰۰ و Content-Length کامل
  # پاسخ می‌گرفت. allowlist باید در پایین‌ترین لایه باشد تا هیچ متد دیگری
  # هم نتواند دورش بزند.
  p=urlparse(self.path).path
  if unquote(p,errors='surrogateescape') not in STATIC_ALLOW:
   self.send_error(404,'Not Found')
   return None
  return super().send_head()
 def _get(self):
  p=urlparse(self.path).path; c=db(self)
  # سطح ادمین: پیش‌تر بدون هیچ احراز هویتی خوانده و نوشته می‌شد، از جمله بازنویسی
  # دستور سیستمی هوش مصنوعی. بدون نشست معتبر مراقب هیچ دسترسی مجاز نیست.
  if p.startswith('/api/admin/') or p=='/api/safety/rules':
   if not caregiver_session(c,self.headers): return send(self,403,{'error':'caregiver_session_required','message':'برای این بخش ابتدا با شماره و کد دعوت مراقب وارد شوید.'})
  if p.startswith('/share/'):
   token=p.split('/')[-1]; data=share_payload(c,token)
   if not data: self.send_error(404,'share_not_found'); return
   raw=report_html(data).encode()
   self.send_response(200)
   self.send_header('Content-Type','text/html; charset=utf-8')
   self.send_header('Content-Length',str(len(raw)))
   self.end_headers()
   self.wfile.write(raw)
   return
  if p=='/api/vitals/shares': return send(self,200,{'items':rows(c,'SELECT token,scope,expires_at,revoked,created_at FROM shares ORDER BY created_at DESC')})
  if p.startswith('/api/vitals/share/'):
   data=share_payload(c,p.split('/')[-1]); return send(self,200,data) if data else send(self,404,{'error':'share_not_found'})
  if p=='/api/health': return send(self,200,{'ok':True,'service':'sepandyar','time':now(),'version':'0.2'})
  if p=='/api/consents': return send(self,200,{'items':rows(c,'SELECT * FROM consents ORDER BY scope')})
  if p=='/api/profile':
   r=c.execute('SELECT * FROM profile WHERE id=1').fetchone(); return send(self,200,dict(r) if r else {})
  if p=='/api/caregivers':
   # شمارهٔ کامل، خودش عامل ورود مراقب است؛ برای تماس‌گیرندهٔ ناشناس ماسک می‌شود
   authed=bool(caregiver_session(c,self.headers))
   items=[]
   for r in rows(c,'SELECT id,name,phone,role,permissions,created_at FROM caregivers ORDER BY created_at'):
    it=dict(r); it['phone_masked']=mask_phone(it.get('phone'))
    if not authed: it['phone']=it['phone_masked']
    items.append(it)
   return send(self,200,{'items':items})
  if p=='/api/wallet':
   w=dict(c.execute('SELECT * FROM wallet WHERE id=1').fetchone())
   w['transactions']=rows(c,'SELECT id,kind,amount,description,created_at FROM transactions ORDER BY created_at DESC LIMIT 50')
   return send(self,200,w)
  if p=='/api/medications': return send(self,200,{'items':rows(c,'SELECT * FROM medications ORDER BY time')})
  if p.startswith('/api/medications/') and p.endswith('/details'):
   mid=p.split('/')[3]; r=c.execute('SELECT * FROM medication_details WHERE medication_id=?',(mid,)).fetchone(); return send(self,200,dict(r) if r else {})
  if p=='/api/vitals': return send(self,200,{'items':rows(c,'SELECT * FROM vitals ORDER BY measured_at DESC LIMIT 100')})
  if p=='/api/vitals/thresholds': return send(self,200,{'items':rows(c,'SELECT * FROM vital_thresholds ORDER BY type')})
  if p=='/api/reminder-settings':
   r=c.execute('SELECT * FROM reminder_settings WHERE id=1').fetchone(); return send(self,200,dict(r) if r else {})
  if p=='/api/proactive/due':
   return send(self,200,{'items':collect_due_prompts(c),'escalated':escalate_stale_prompts(c),'checked_at':now()})
  if p=='/api/reminders/due':
   current=local_now().strftime('%H:%M')
   today=local_now().date().isoformat()
   due=[]
   settings=c.execute('SELECT * FROM reminder_settings WHERE id=1').fetchone()
   quiet=in_quiet_window(current,settings['quiet_start'],settings['quiet_end']) if settings else False
   if not quiet:
    for m in c.execute("SELECT * FROM medications WHERE id NOT IN (SELECT medication_id FROM medication_logs WHERE log_date=? AND event='taken')",(today,)).fetchall():
     try:
      mt=datetime.datetime.strptime(m['time'],'%H:%M'); ct=datetime.datetime.strptime(current,'%H:%M'); delta=abs((ct-mt).total_seconds())
      if delta<=900:
       channel=(settings['preferred_channel'] if settings else 'voice') or 'voice'
       # max_nudges پیش از این ذخیره و اعتبارسنجی می‌شد ولی هیچ‌جا خوانده
       # نمی‌شد؛ یعنی تنظیم سقف یادآوری کاملاً بی‌اثر بود. حالا خوانده می‌شود
       # و دست‌کم max_nudges=0 واقعاً یادآوری را خاموش می‌کند.
       # توجه: تکرار واقعی بیش از یک بار در روز نیاز به مهاجرت schema دارد،
       # چون UNIQUE(medication_id,reminder_date,channel) در جدول reminder_events
       # فقط یک ردیف به ازای هر دارو/روز/کانال اجازه می‌دهد.
       try: maxn=int(settings['max_nudges']) if settings and settings['max_nudges'] is not None else 2
       except (TypeError,ValueError): maxn=2
       maxn=max(0,min(maxn,10))
       sent=c.execute('SELECT COUNT(*) FROM reminder_events WHERE medication_id=? AND reminder_date=? AND channel=?',(m['id'],today,channel)).fetchone()[0]
       if sent<maxn:
        c.execute('INSERT INTO reminder_events VALUES(?,?,?,?,?)',(str(uuid.uuid4()),m['id'],today,channel,now())); due.append(dict(m))
     except: pass
    c.commit()
   return send(self,200,{'items':due,'checked_at':now(),'quiet_hours':quiet})
  if p=='/api/care-circle/summary':
   prof=c.execute('SELECT name,age,needs FROM profile WHERE id=1').fetchone()
   today=local_now().date().isoformat()
   meds=rows(c,"SELECT m.id,m.name,m.time,COALESCE(l.event,'pending') AS status FROM medications m LEFT JOIN medication_logs l ON l.medication_id=m.id AND l.log_date=? ORDER BY m.time",(today,))
   alerts=rows(c,"SELECT id,type,message,severity,status,created_at FROM alerts WHERE status='open' ORDER BY created_at DESC LIMIT 20")
   vit=c.execute("SELECT type,value,measured_at FROM vitals ORDER BY measured_at DESC LIMIT 1").fetchone()
   return send(self,200,{'profile':dict(prof) if prof else {},'medications':meds,'open_alerts':alerts,'last_vital':dict(vit) if vit else None,'caregivers':rows(c,'SELECT name,phone,role FROM caregivers'),'tasks':rows(c,"SELECT * FROM care_tasks WHERE status!='done' ORDER BY due_at"),'last_checkin':dict(c.execute('SELECT * FROM checkins ORDER BY created_at DESC LIMIT 1').fetchone()) if c.execute('SELECT COUNT(*) FROM checkins').fetchone()[0] else None})
  if p=='/api/care-tasks': return send(self,200,{'items':rows(c,'SELECT * FROM care_tasks ORDER BY due_at')})
  if p=='/api/checkins': return send(self,200,{'items':rows(c,'SELECT * FROM checkins ORDER BY created_at DESC LIMIT 30')})
  if p=='/api/icope': return send(self,200,{'items':rows(c,'SELECT * FROM icope_assessments ORDER BY assessed_at DESC')})
  if p=='/api/icope/summary':
   domains=['locomotion','vitality','vision','hearing','cognition','psychology']; latest={}
   for d in domains:
    r=c.execute('SELECT * FROM icope_assessments WHERE domain=? ORDER BY assessed_at DESC LIMIT 1',(d,)).fetchone()
    latest[d]=dict(r) if r else None
   return send(self,200,{'domains':latest,'assessed_at':now()})
  if p=='/api/pantry': return send(self,200,{'items':rows(c,'SELECT * FROM food_items ORDER BY created_at DESC')})
  if p=='/api/contacts': return send(self,200,{'items':rows(c,'SELECT * FROM contacts ORDER BY name')})
  if p=='/api/messages': return send(self,200,{'items':rows(c,'SELECT * FROM messages ORDER BY created_at DESC LIMIT 50')})
  if p=='/api/appointments': return send(self,200,{'items':rows(c,'SELECT * FROM appointments WHERE status=\'scheduled\' ORDER BY starts_at')})
  if p=='/api/doctors': return send(self,200,{'items':rows(c,'SELECT * FROM doctors ORDER BY preferred DESC,specialty')})
  if p=='/api/emergency-card':
   r=c.execute('SELECT * FROM emergency_card WHERE id=1').fetchone(); return send(self,200,dict(r) if r else {})
  if p=='/api/location/latest':
   r=c.execute('SELECT * FROM locations ORDER BY created_at DESC LIMIT 1').fetchone(); return send(self,200,dict(r) if r else {})
  if p=='/api/safe-zones': return send(self,200,{'items':rows(c,'SELECT * FROM safe_zones WHERE enabled=1 ORDER BY name')})
  if p=='/api/admin/overview':
   w=c.execute('SELECT balance FROM wallet WHERE id=1').fetchone()
   return send(self,200,{'users':1,'caregivers':c.execute('SELECT COUNT(*) FROM caregivers').fetchone()[0],'medications':c.execute('SELECT COUNT(*) FROM medications').fetchone()[0],'vitals':c.execute('SELECT COUNT(*) FROM vitals').fetchone()[0],'open_alerts':c.execute("SELECT COUNT(*) FROM alerts WHERE status='open'").fetchone()[0],'transactions':c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],'wallet_balance':w['balance'] if w else 0,'health_checks':{'api':'ok','database':'ok','reminders':'ok'}})
  if p=='/api/admin/activity': return send(self,200,{'items':rows(c,'SELECT type,payload,created_at FROM events ORDER BY created_at DESC LIMIT 100')})
  if p=='/api/admin/ai-config':
   r=c.execute('SELECT provider,base_url,model,stt_provider,tts_provider,system_prompt,guardrails,voice_id,tone,temperature,updated_at FROM ai_config WHERE id=1').fetchone()
   return send(self,200,dict(r) if r else {})
  if p=='/api/admin/ai-test': return send(self,200,{'ok':True,'provider':'configured','message':'تنظیمات AI آماده استفاده هستند.'})
  if p=='/api/realtime/session':
   key=os.getenv('OPENAI_API_KEY','')
   if not key: return send(self,503,{'error':'realtime_not_configured','message':'OPENAI_API_KEY در محیط سرور ثبت نشده است.'})
   cfg=c.execute('SELECT * FROM ai_config WHERE id=1').fetchone()
   model=(cfg['model'] if cfg and cfg['model'] else 'gpt-realtime-2.1')
   tone=(cfg['tone'] if cfg else 'گرم و کوتاه')
   prompt=(cfg['system_prompt'] if cfg else 'دستیار فارسی سالمندان هستی.')+'\nلحن: '+tone+'\nGuardrails: '+(cfg['guardrails'] if cfg else '')+'\nهمیشه به فارسی معیار ایران با تلفظ تهرانی صحبت کن، نه دری افغانی.'
   # صبر گفتاری کاربر باید به خودِ مدل برسد. semantic_vad پارامترهای زمانی را نمی‌پذیرد،
   # پس server_vad با silence_duration_ms برابر patience_ms پروفایل کاربر.
   rpid=parse_qs(urlparse(self.path).query).get('id',['default'])[0]
   pat=live_vad_config(get_voice_profile(c,rpid)['patience_ms'])['silenceDurationMs']
   payload={'session':{'type':'realtime','model':model,'output_modalities':['audio'],'audio':{'input':{'turn_detection':{'type':'server_vad','silence_duration_ms':pat,'prefix_padding_ms':120,'create_response':True,'interrupt_response':True}},'output':{'voice':(cfg['voice_id'] if cfg and cfg['voice_id'] else 'marin')}},'instructions':prompt}}
   try:
    r=ureq.Request('https://api.openai.com/v1/realtime/client_secrets',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','OpenAI-Safety-Identifier':hashlib.sha256(b'sepandyar-local-user').hexdigest()},method='POST')
    with ureq.urlopen(r,timeout=15) as resp: return send(self,200,json.loads(resp.read()))
   except Exception as e: return send(self,502,{'error':'realtime_provider_error','message':'اتصال realtime برقرار نشد.'})
  if p=='/api/live/session':
   key=os.getenv('GEMINI_API_KEY','')
   if not key: return send(self,503,{'error':'live_not_configured','provider':'none','message':'GEMINI_API_KEY در محیط سرور ثبت نشده است.'})
   pid=parse_qs(urlparse(self.path).query).get('id',['default'])[0]
   prof=get_voice_profile(c,pid)
   cfg=c.execute('SELECT * FROM ai_config WHERE id=1').fetchone()
   voice=(cfg['voice_id'] if cfg and cfg['voice_id'] else LIVE_VOICE)
   name=fetch_live_token(key,LIVE_MODEL)
   if not name: return send(self,502,{'error':'live_provider_error','provider':'none','message':'دریافت توکن گفت‌وگوی زنده ناموفق بود.'})
   vad=live_vad_config(prof['patience_ms'])
   return send(self,200,{'provider':'gemini','token':name,'ws_url':LIVE_WS_BASE+'?access_token='+quote(name,safe=''),'model':'models/'+LIVE_MODEL,
    'generation_config':{'responseModalities':['AUDIO'],'speechConfig':{'voiceConfig':{'prebuiltVoiceConfig':{'voiceName':voice}}}},
    'realtime_input_config':{'automaticActivityDetection':vad},
    'context_window_compression':{'slidingWindow':{},'compressTriggerConfig':{'tokensLimit':LIVE_TOKENS_LIMIT}},
    'system_instruction':live_system_prompt(c),'voice':voice,'patience_ms':vad['silenceDurationMs'],'profile':pid,
    'guardrail_endpoint':'/api/conversation','expires_at':live_token_payload(LIVE_MODEL)['expireTime']})
  if p=='/api/education/topics': return send(self,200,{'items':rows(c,"SELECT id,topic,category,approved_by FROM education_content WHERE status='approved' ORDER BY category,topic")})
  if p=='/api/education/next':
   it=rows(c,"SELECT id,topic,category,body,approved_by FROM education_content WHERE status='approved' ORDER BY RANDOM() LIMIT 1"); return send(self,200,{'item':it[0] if it else None})
  if p=='/api/education': return send(self,200,{'items':rows(c,'SELECT * FROM education_content ORDER BY category,topic')})
  if p.startswith('/api/education/'):
   r=c.execute("SELECT * FROM education_content WHERE id=? AND status='approved'",(p.split('/')[3],)).fetchone()
   return send(self,200,dict(r)) if r else send(self,404,{'error':'content_not_found_or_not_approved'})
  if p=='/api/symptoms/catalog': return send(self,200,{'items':rows(c,'SELECT name,escalate FROM symptom_catalog ORDER BY sort_order')})
  if p=='/api/symptoms': return send(self,200,{'items':rows(c,'SELECT * FROM symptom_reports ORDER BY created_at DESC LIMIT 50')})
  if p=='/api/safety/rules': return send(self,200,{'items':rows(c,'SELECT level,pattern,action,reply FROM safety_rules ORDER BY level,pattern')})
  if p=='/api/dialects':
   acc=rows(c,"SELECT accent,COUNT(*) AS entries FROM dialect_lexicon GROUP BY accent ORDER BY entries DESC")
   known={'mashhadi':'مشهدی/خراسانی',
     'yazdi':'یزدی',
     'shirazi':'شیرازی',
     'isfahani':'اصفهانی',
     'azeri':'ترکی/آذری',
     'kurdish':'کردی',
     'lori':'لری',
     'shomali':'شمالی (گیلکی/مازندرانی)',
     'jonubi':'جنوبی/بندری',
     'baluchi':'بلوچی',
     'dari':'دری',
     'kermani':'کرمانی',
     'colloquial':'محاوره عمومی',
     'standard':'فارسی معیار'}
   # دقت نسبی از بنچمارک PSRB (SW-WER میانگین ده سامانه؛ عدد کمتر بهتر)
   psrb={'kurdish':36.7,'mashhadi':53.3,'shirazi':43.8,'shomali':41.8,'standard':None}
   return send(self,200,{'items':[{'accent':a['accent'],'label':known.get(a['accent'],a['accent']),'entries':a['entries'],'psrb_sw_wer':psrb.get(a['accent']),'patience_ms':get_voice_profile(c)['patience_ms']} for a in acc],'source':'PSRB (arXiv:2505.21230) + PDID (arXiv:2510.09528)'})
  if p=='/api/voice-profile': return send(self,200,get_voice_profile(c,parse_qs(urlparse(self.path).query).get('id',['default'])[0]))
  if p=='/api/aliases': return send(self,200,{'items':rows(c,'SELECT transcript,intent_id,weight,source,created_at FROM utterance_aliases ORDER BY weight DESC, created_at DESC LIMIT 100')})
  if p=='/api/intents': return send(self,200,{'items':rows(c,'SELECT id,label,action,image_query,priority FROM intent_lexicon ORDER BY priority DESC')})
  if p=='/api/images/search':
   qs=parse_qs(urlparse(self.path).query); q=(qs.get('q') or [''])[0]; cnt=min(int((qs.get('count') or ['2'])[0] or 2),6)
   if not q.strip(): return send(self,400,{'error':'q_required'})
   return send(self,200,{'items':fetch_images(c,q,cnt),'query':q})
  if p=='/api/prescriptions':
   items=[]
   for x in rows(c,'SELECT * FROM prescriptions ORDER BY created_at DESC LIMIT 50'):
    x['items']=rows(c,'SELECT * FROM prescription_items WHERE prescription_id=? ORDER BY created_at',(x['id'],)); items.append(x)
   return send(self,200,{'items':items})
  if p=='/api/baselines':
   rep=baseline_report(c); return send(self,200,{'baselines':rep,'alerts_created':detect_deviation_alerts(c,rep)})
  if p=='/api/conversation/history':
   pid=parse_qs(urlparse(self.path).query).get('profile',['default'])[0]
   return send(self,200,{'items':recall(c,pid,MEMORY_TURNS*3),'profile':pid})
  if p=='/api/caregiver/conversation-summary':
   # حریم «خلاصه + موارد پرخطر»: خانواده موضوع و حجم گفتگو را می‌بیند، نه متن خام.
   # استثنا فقط نوبت‌هایی است که گارد ایمنی پرچم زده — چون ایمنی بر حریم مقدم است.
   s=caregiver_session(c,self.headers)
   if not s: return send(self,403,{'error':'caregiver_session_required','message':'برای دیدن این صفحه، ابتدا با شماره همراه مراقب وارد شوید.'})
   if not consent_granted(c,'health'): return send(self,403,{'error':'senior_consent_not_granted','message':'سالمند هنوز رضایت خود را برای اشتراک‌گذاری اطلاعات سلامت ثبت نکرده است.'})
   pid=parse_qs(urlparse(self.path).query).get('profile',['default'])[0]
   return send(self,200,conversation_summary(c,pid))
  if p=='/api/disambiguation/history': return send(self,200,{'items':rows(c,'SELECT * FROM disambiguation_events ORDER BY created_at DESC LIMIT 50')})
  if p=='/api/apps/approved':
   items=[]
   for x in rows(c,'SELECT * FROM approved_apps WHERE enabled=1 ORDER BY category,label'):
    try: x['plan']=json.loads(x['plan'] or '{}')
    except Exception: x['plan']={'steps':[]}
    items.append(x)
   return send(self,200,{'items':items})
  if p=='/api/screen-tasks': return send(self,200,{'items':rows(c,'SELECT * FROM screen_task_runs ORDER BY started_at DESC LIMIT 50')})
  if p=='/api/caregiver/actions':
   # ستون payload این جدول شمارهٔ «کامل» مراقب و دلیل درخواست سالمند را نگه می‌دارد —
   # همان داده‌ای که /api/caregivers برای تماس‌گیرندهٔ ناشناس ماسک می‌کند. اینجا بی‌گارد
   # بود؛ اندازه‌گیری شد: GET ناشناس → {"phone": "09121234567", ...}.
   # تنها caller مشروع caregiver.html است که X-Caregiver-Token می‌فرستد.
   if not caregiver_session(c,self.headers): return send(self,403,{'error':'caregiver_session_required','message':'برای دیدن این صفحه، ابتدا با شماره همراه مراقب وارد شوید.'})
   return send(self,200,{'items':rows(c,'SELECT * FROM caregiver_actions ORDER BY requested_at DESC LIMIT 50')})
  if p=='/api/caregiver/panel':
   s=caregiver_session(c,self.headers)
   if not s: return send(self,403,{'error':'caregiver_session_required','message':'برای دیدن این صفحه، ابتدا با شماره همراه مراقب وارد شوید.'})
   if not consent_granted(c,'health'): return send(self,403,{'error':'senior_consent_not_granted','message':'سالمند هنوز رضایت خود را برای اشتراک‌گذاری اطلاعات سلامت ثبت نکرده است.'})
   prof=c.execute('SELECT name,age,needs FROM profile WHERE id=1').fetchone(); today=local_now().date().isoformat()
   meds=rows(c,"SELECT m.id,m.name,m.time,COALESCE(l.event,'pending') AS status FROM medications m LEFT JOIN medication_logs l ON l.medication_id=m.id AND l.log_date=? ORDER BY m.time",(today,))
   alerts=rows(c,"SELECT id,type,message,severity,status,created_at FROM alerts WHERE status='open' ORDER BY created_at DESC LIMIT 20")
   vit=c.execute('SELECT type,value,measured_at FROM vitals ORDER BY measured_at DESC LIMIT 1').fetchone()
   screen=rows(c,'SELECT app_package,title,status,steps_done,steps_total,error,started_at FROM screen_task_runs ORDER BY started_at DESC LIMIT 8') if consent_granted(c,'screen_control') else None
   return send(self,200,{'profile':dict(prof) if prof else {},'medications':meds,'open_alerts':alerts,'last_vital':dict(vit) if vit else None,'tasks':rows(c,"SELECT * FROM care_tasks WHERE status!='done' ORDER BY due_at"),'symptoms':rows(c,'SELECT * FROM symptom_reports ORDER BY created_at DESC LIMIT 10'),'pending_actions':[a for a in rows(c,'SELECT * FROM caregiver_actions ORDER BY requested_at DESC LIMIT 50') if a['status']=='pending'],'screen_tasks':screen,'screen_control_shared':screen is not None,'checked_at':now()})
  if p=='/api/alerts': return send(self,200,{'items':rows(c,'SELECT * FROM alerts ORDER BY created_at DESC LIMIT 50')})
  if p=='/api/events': return send(self,200,{'items':rows(c,'SELECT * FROM events ORDER BY created_at DESC LIMIT 100')})
  if unquote(p,errors='surrogateescape') not in STATIC_ALLOW:
   return send(self,404,{'error':'not_found'})
  return super().do_GET()
 def do_POST(self):
  # پوشش کامل: بخشی از زنجیرهٔ مسیرها بیرون از try داخلی است و هر خطای نوع/تبدیل
  # در آن‌جا پیش‌تر اتصال را بی‌پاسخ می‌بست (RemoteDisconnected)
  try: return self._post()
  except sqlite3.ProgrammingError as e:
   # «Error binding parameter N: type 'dict' is not supported» یعنی کلاینت مقدار
   # ساخت‌یافته فرستاده جایی که مقدار ساده لازم است؛ این خطای ۴۰۰ است نه ۵۰۰.
   # فقط خطای اتصال نوع نگاشت می‌شود تا باگ واقعی (مثل تعداد غلط پارامتر) پنهان نماند.
   if 'Error binding parameter' in str(e):
    try: return send(self,400,{'error':'invalid_field_type','message':'مقدار این فیلد باید ساده باشد (رشته/عدد)، نه شیء یا آرایه.'})
    except Exception: return None
   try: return send(self,500,{'error':'server_error'})
   except Exception: return None
  except ConnectionError:
   # کلاینت پیش از گرفتن پاسخ رفته است (RST یا بستن ناگهانی). خودِ send() هم
   # روی سوکت مرده شکست می‌خورد، و تلاش برای فرستادن ۵۰۰ یک ورودی ۵۰۰ جعلی
   # در لاگ می‌نشاند. بازتولید شد: هر درخواست RST‌شده «۴۰۰ و سپس ۵۰۰» ثبت
   # می‌کرد، در حالی که سرور هیچ خطایی نداشت. این کار پایش خطا را آلوده می‌کند
   # و ۵۰۰ واقعی را پنهان می‌سازد.
   return None
  except Exception:
   try: return send(self,500,{'error':'server_error'})
   except Exception: return None
 def _post(self):
  p=urlparse(self.path).path; d=body(self)
  # بدنهٔ ناقص/خراب هرگز نباید به‌صورت «درخواست خالی معتبر» تفسیر شود،
  # وگرنه مثلاً پروفایل کالیبره‌شدهٔ کاربر بی‌صدا بازنویسی می‌شود.
  if getattr(self,'_body_too_large',False): return send(self,413,{'error':'payload_too_large','message':'بدنهٔ درخواست بزرگ‌تر از حد مجاز است؛ هیچ تغییری اعمال نشد.','max_bytes':MAX_BODY_BYTES})
  if getattr(self,'_body_error',False): return send(self,400,{'error':'invalid_json','message':'بدنهٔ درخواست JSON معتبر نیست؛ هیچ تغییری اعمال نشد.'})
  c=db(self)
  # سطح ادمین: پیش‌تر بدون هیچ احراز هویتی خوانده و نوشته می‌شد، از جمله بازنویسی
  # دستور سیستمی هوش مصنوعی. بدون نشست معتبر مراقب هیچ دسترسی مجاز نیست.
  if p.startswith('/api/admin/') or p=='/api/safety/rules':
   if not caregiver_session(c,self.headers): return send(self,403,{'error':'caregiver_session_required','message':'برای این بخش ابتدا با شماره و کد دعوت مراقب وارد شوید.'})
  if p=='/api/consents':
   scope=d.get('scope','');
   if scope not in ('health','wallet','screen_control','voice_profile','emergency_call'): return send(self,400,{'error':'invalid_scope'})
   c.execute('INSERT INTO consents(scope,granted,confirmed_by_voice,updated_at,updated_by) VALUES(?,?,?,?,?) ON CONFLICT(scope) DO UPDATE SET granted=excluded.granted,confirmed_by_voice=excluded.confirmed_by_voice,updated_at=excluded.updated_at,updated_by=excluded.updated_by',(scope,int(bool(d.get('granted'))),int(bool(d.get('confirmed_by_voice'))),now(),d.get('updated_by','senior')))
   c.commit()
   return send(self,200,{'ok':True})
  if p=='/api/care-tasks':
   tid=str(uuid.uuid4())
   c.execute('INSERT INTO care_tasks VALUES(?,?,?,?,?,?,?)',(tid,d.get('title',''),d.get('kind','routine'),d.get('assigned_to','senior'),d.get('due_at',''), 'pending',now()))
   c.commit()
   return send(self,201,{'id':tid,'ok':True})
  if p.startswith('/api/care-tasks/') and p.endswith('/complete'):
   tid=p.split('/')[3]; c.execute("UPDATE care_tasks SET status='done' WHERE id=?",(tid,)); c.commit(); return send(self,200,{'ok':True})
  if p=='/api/checkins':
   cid=str(uuid.uuid4())
   c.execute('INSERT INTO checkins VALUES(?,?,?,?,?,?)',(cid,d.get('mood',''),d.get('pain',''),d.get('sleep',''),d.get('note',''),now()))
   c.commit()
   return send(self,201,{'id':cid,'ok':True})
  if p=='/api/prescriptions':
   # ورود نسخه با تصویر. دارویاد این را دارد و ۴۱ هزار نصب گرفته؛ ورود دستی دارو
   # بزرگ‌ترین اصطکاک اولیه است و اگر ثبت دارو سخت باشد کاربر از روز اول می‌رود.
   # as_text برای dict/list عمداً None می‌دهد تا فراخوان ۴۰۰ برگرداند؛
   # صدا زدن .strip() روی None باعث AttributeError و پاسخ ۵۰۰ می‌شد.
   ref=(as_text(d.get('image_ref','')) or '').strip()
   if not ref: return send(self,400,{'error':'image_ref_required','message':'لینک یا ارجاع تصویر نسخه لازم است.'})
   if c.execute('SELECT id FROM prescriptions WHERE image_ref=?',(ref,)).fetchone():
    return send(self,409,{'error':'duplicate_prescription','message':'این نسخه پیش‌تر ثبت شده است.'})
   pid=str(uuid.uuid4()); c.execute('INSERT INTO prescriptions VALUES(?,?,?,?,?,?)',(pid,ref,as_text(d.get('source','upload')),'pending',as_text(d.get('notes','')),now()))
   items=[]
   raw=d.get('items')
   if not isinstance(raw,list): raw=[]
   for it in raw[:40]:
    if not isinstance(it,dict): continue
    name=(as_text(it.get('name','')) or '').strip()
    if not name: continue
    iid=str(uuid.uuid4())
    c.execute('INSERT INTO prescription_items VALUES(?,?,?,?,?,?,?,?)',(iid,pid,name[:160],as_text(it.get('dose','')),as_text(it.get('schedule','')),0,None,now()))
    items.append({'id':iid,'name':name})
   c.commit(); return send(self,201,{'id':pid,'status':'pending','items':items})
  if p.startswith('/api/prescriptions/') and p.endswith('/confirm'):
   # تأیید قلم نسخه ← ساخت داروی واقعی. هیچ‌گاه بی‌تأیید خودکار دارو ساخته نمی‌شود.
   pid=p.split('/')[3]
   pr=c.execute('SELECT * FROM prescriptions WHERE id=?',(pid,)).fetchone()
   if not pr: return send(self,404,{'error':'prescription_not_found'})
   it=c.execute('SELECT * FROM prescription_items WHERE id=?',(as_text(d.get('item_id','')),)).fetchone()
   if not it or it['prescription_id']!=pid: return send(self,404,{'error':'item_not_found'})
   if it['confirmed']: return send(self,200,{'ok':True,'already_confirmed':True,'medication_id':it['medication_id']})
   mid=str(uuid.uuid4()); c.execute('INSERT INTO medications VALUES(?,?,?,?,?)',(mid,it['name'],as_text(d.get('time','08:00')),as_text(d.get('instructions','')) or it['schedule'],'active'))
   c.execute('UPDATE prescription_items SET confirmed=1,medication_id=? WHERE id=?',(mid,it['id']))
   c.execute("UPDATE prescriptions SET status='confirmed' WHERE id=?",(pid,)); c.commit()
   return send(self,201,{'ok':True,'medication_id':mid,'name':it['name']})
  if p=='/api/proactive/respond':
   eid=d.get('id'); c.execute('UPDATE proactive_events SET response=?,responded_at=? WHERE id=?',(d.get('response',''),now(),eid)); c.commit(); return send(self,200,{'ok':True})
  if p=='/api/reminder-settings':
   nudges=as_int(d.get('max_nudges',2))
   if nudges is None or not 0<=nudges<=10: return send(self,400,{'error':'invalid_max_nudges','message':'max_nudges باید عددی بین ۰ و ۱۰ باشد.'})
   qs=as_hhmm(d.get('quiet_start','22:00')); qe=as_hhmm(d.get('quiet_end','07:00'))
   if qs is None or qe is None:
    return send(self,400,{'error':'invalid_quiet_hours','message':'quiet_start و quiet_end باید به قالب HH:MM باشند.'})
   c.execute('INSERT INTO reminder_settings(id,quiet_start,quiet_end,max_nudges,preferred_channel,updated_at) VALUES(1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET quiet_start=excluded.quiet_start,quiet_end=excluded.quiet_end,max_nudges=excluded.max_nudges,preferred_channel=excluded.preferred_channel,updated_at=excluded.updated_at',
     (qs,qe,nudges,d.get('preferred_channel','voice'),now()))
   c.commit()
   return send(self,200,{'ok':True,'quiet_start':qs,'quiet_end':qe,'max_nudges':nudges})
  if p=='/api/icope':
   domain=d.get('domain',''); score=as_float(d.get('score',0))
   # as_float روی ورودی غیرعددی None می‌دهد؛ 0<=None پیش‌تر TypeError و ۵۰۰ می‌داد
   if score is None or domain not in ('locomotion','vitality','vision','hearing','cognition','psychology') or not 0<=score<=10: return send(self,400,{'error':'invalid_icope_assessment'})
   status='good' if score>=7 else ('watch' if score>=4 else 'needs_support')
   iid=str(uuid.uuid4())
   c.execute('INSERT INTO icope_assessments VALUES(?,?,?,?,?,?,?)',(iid,domain,score,status,d.get('notes',''),d.get('assessed_by','senior'),now()))
   if status=='needs_support': c.execute('INSERT INTO alerts VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),'icope_'+domain,'در حوزه '+domain+' نیاز به حمایت بیشتر ثبت شد.','warning','open',now()))
   c.commit(); return send(self,201,{'id':iid,'status':status,'ok':True})
  if p=='/api/pantry':
   for item in d.get('items',[]): c.execute('INSERT INTO food_items VALUES(?,?,?,?,?)',(str(uuid.uuid4()),item.get('name',''),item.get('quantity',''),d.get('source','voice'),now()))
   c.commit(); return send(self,201,{'ok':True,'items':rows(c,'SELECT * FROM food_items ORDER BY created_at DESC')})
  if p=='/api/recipes/suggest':
   items=[str(x) for x in d.get('items',[])]; ai=call_llm(c,'با این مواد برای یک سالمند فارسی‌زبان دو غذای ساده، کم‌نمک و ایمن پیشنهاد بده: '+', '.join(items));
   if ai: return send(self,200,{'recipes':[],'spoken_suggestion':ai,'provider':'configured'})
   return send(self,200,{'recipes':[{'name':'املت سبزیجات کم‌نمک','time_min':20,'ingredients':items[:5],'steps':['مواد را خرد کنید','با حرارت ملایم بپزید','نمک را حذف یا بسیار کم کنید'],'note':'مقدار نمک و روغن با شرایط پزشکی سالمند تطبیق داده شود.'},{'name':'سوپ ساده و مقوی','time_min':35,'ingredients':items[:5],'steps':['مواد را بشویید','با آب کافی بپزید','در پایان بافت و دما را بررسی کنید'],'note':'برای دیابت، مقدار نان و کربوهیدرات را با نظر متخصص تنظیم کنید.'}]})
  if p=='/api/contacts':
   cid=str(uuid.uuid4())
   c.execute('INSERT INTO contacts VALUES(?,?,?,?,?)',(cid,d.get('name',''),d.get('phone',''),d.get('relationship','family'),now()))
   c.commit()
   return send(self,201,{'id':cid,'ok':True})
  if p=='/api/messages':
   mid=str(uuid.uuid4()); c.execute('INSERT INTO messages VALUES(?,?,?,?,?,?)',(mid,d.get('contact_id',''),d.get('body',''),d.get('kind','voice'),now(),'queued'))
   aid=enqueue_caregiver_action(c,'message',{'message_id':mid,'contact_id':d.get('contact_id',''),'body':d.get('body',''),'kind':d.get('kind','voice')})
   c.commit(); return send(self,201,{'id':mid,'ok':True,'status':'queued','action_id':aid})
  if p=='/api/appointments':
   # location باید بیرون از if مقدار اولیه بگیرد؛ وگرنه وقتی doctor_id نیست
   # (که شکل درخواستِ خودِ کلاینت است) INSERT با NameError می‌ترکد و ۵۰۰ می‌دهد
   aid=str(uuid.uuid4()); provider=d.get('provider',''); location=d.get('location',''); doctor_id=d.get('doctor_id');
   if doctor_id:
    doc=c.execute('SELECT * FROM doctors WHERE id=?',(doctor_id,)).fetchone()
    provider=doc['name'] if doc else provider
    location=(doc['clinic']+' — '+doc['address']) if doc and doc['clinic'] else d.get('location','')
   rmin=as_int(d.get('reminder_minutes',60))
   if rmin is None: return send(self,400,{'error':'invalid_reminder_minutes','message':'reminder_minutes باید عدد باشد.'})
   c.execute('INSERT INTO appointments VALUES(?,?,?,?,?,?,?,?)',(aid,d.get('title','وقت پزشک'),provider,location,d.get('starts_at',''),rmin, 'scheduled',now()))
   c.commit()
   return send(self,201,{'id':aid,'ok':True,'provider':provider,'location':location})
  if p=='/api/doctors':
   did=str(uuid.uuid4())
   c.execute('INSERT INTO doctors VALUES(?,?,?,?,?,?,?,?)',(did,d.get('name',''),d.get('specialty',''),d.get('phone',''),d.get('address',''),d.get('clinic',''),int(bool(d.get('preferred'))),now()))
   c.commit()
   return send(self,201,{'id':did,'ok':True})
  if p=='/api/emergency-card':
   fields=[d.get(k,'') for k in ('full_name','birth_date','blood_type','allergies','conditions','critical_meds','primary_doctor','emergency_contact')]
   c.execute('INSERT INTO emergency_card(id,full_name,birth_date,blood_type,allergies,conditions,critical_meds,primary_doctor,emergency_contact,updated_at) VALUES(1,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET full_name=excluded.full_name,birth_date=excluded.birth_date,blood_type=excluded.blood_type,allergies=excluded.allergies,conditions=excluded.conditions,critical_meds=excluded.critical_meds,primary_doctor=excluded.primary_doctor,emergency_contact=excluded.emergency_contact,updated_at=excluded.updated_at',
     (*fields,now()))
   c.commit()
   return send(self,200,{'ok':True})
  if p=='/api/location':
   lat=as_float(d.get('lat')); lon=as_float(d.get('lon'))
   if lat is None or lon is None: return send(self,400,{'error':'coordinates_required','message':'مقدار lat و lon باید عدد باشد.'})
   acc=as_float(d.get('accuracy',0)); acc=0.0 if acc is None else acc
   lid=str(uuid.uuid4()); c.execute('INSERT INTO locations VALUES(?,?,?,?,?,?)',(lid,lat,lon,acc,d.get('source','phone'),now())); outside=[]
   for z in c.execute('SELECT * FROM safe_zones WHERE enabled=1').fetchall():
    dist=distance_m(lat,lon,z['lat'],z['lon']);
    if dist>z['radius_m']: outside.append({'zone':z['name'],'distance_m':round(dist)})
   if outside: c.execute('INSERT INTO alerts VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),'safe_zone_exit','سالمند از محدوده امن خارج شده است.','warning','open',now()))
   c.commit(); return send(self,201,{'ok':True,'outside_zones':outside})
  if p=='/api/safe-zones':
   zlat=as_float(d.get('lat')); zlon=as_float(d.get('lon')); zrad=as_float(d.get('radius_m',200))
   if zlat is None or zlon is None: return send(self,400,{'error':'coordinates_required','message':'مقدار lat و lon باید عدد باشد.'})
   if zrad is None or zrad<=0: return send(self,400,{'error':'invalid_radius','message':'شعاع محدوده باید عددی بزرگ‌تر از صفر باشد.'})
   zid=str(uuid.uuid4()); c.execute('INSERT INTO safe_zones VALUES(?,?,?,?,?,?,?)',(zid,d.get('name','خانه'),zlat,zlon,zrad,1,now())); c.commit(); return send(self,201,{'id':zid,'ok':True})
  if p=='/api/admin/ai-config':
   allowed=['provider','base_url','model','stt_provider','tts_provider','system_prompt','guardrails','voice_id','tone','temperature']
   current=c.execute('SELECT * FROM ai_config WHERE id=1').fetchone(); values={k:d.get(k,current[k] if current else '') for k in allowed}
   c.execute('UPDATE ai_config SET provider=?,base_url=?,model=?,stt_provider=?,tts_provider=?,system_prompt=?,guardrails=?,voice_id=?,tone=?,temperature=?,updated_at=? WHERE id=1',
     (values['provider'],values['base_url'],values['model'],values['stt_provider'],values['tts_provider'],values['system_prompt'],values['guardrails'],values['voice_id'],values['tone'],float(values['temperature']),now()))
   c.execute('INSERT INTO events VALUES(?,?,?,?)',
     (str(uuid.uuid4()),'ai_config_updated',json.dumps({'provider':values['provider'],'model':values['model'],'tone':values['tone']},ensure_ascii=False),now()))
   c.commit()
   return send(self,200,{'ok':True})
  if p=='/api/admin/ai-test':
   return send(self,200,{'ok':True,'provider':'configured','message':'تنظیمات API معتبر است؛ اتصال واقعی پس از ثبت کلید در محیط امن انجام می‌شود.'})
  if p=='/api/profile':
   c.execute('INSERT INTO profile(id,name,age,needs,assistant_name,updated_at) VALUES(1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,age=excluded.age,needs=excluded.needs,assistant_name=excluded.assistant_name,updated_at=excluded.updated_at',
     (d.get('name',''),d.get('age'),d.get('needs',''),d.get('assistant_name','سپندیار'),now()))
   c.commit()
   return send(self,200,{'ok':True})
  if p=='/api/caregivers':
   _ph=str(d.get('phone','')).strip()
   # شماره هم شناسهٔ مراقب است هم عامل ورود؛ مراقب بی‌شماره هرگز نمی‌تواند وارد شود
   # و با قید یکتا، ساخت دومین مراقب بی‌شماره به IntegrityError و ۵۰۰ می‌انجامید
   if not _ph: return send(self,400,{'error':'phone_required','message':'شمارهٔ همراه مراقب الزامی است.'})
   if c.execute('SELECT id FROM caregivers WHERE phone=?',(_ph,)).fetchone():
    return send(self,409,{'error':'caregiver_exists','message':'این شماره پیش‌تر به عنوان مراقب ثبت شده است.'})
   cid=str(uuid.uuid4()); code=new_invite_code()
   c.execute('INSERT INTO caregivers(id,name,phone,role,permissions,created_at,invite_code,failed_attempts,locked_until) VALUES(?,?,?,?,?,?,?,?,NULL)',
     (cid,d.get('name',''),d.get('phone',''),d.get('role','family'),json.dumps(d.get('permissions',[]),ensure_ascii=False),now(),code,0))
   c.commit()
   c.execute('INSERT INTO events VALUES(?,?,?,?)',(str(uuid.uuid4()),'caregiver_invited',json.dumps({'name':d.get('name','')},ensure_ascii=False),now())); c.commit()
   # کد دعوت فقط یک بار، در پاسخ ساخت، برگردانده می‌شود
   return send(self,201,{'id':cid,'ok':True,'invite_code':code,'message':'این کد را به مراقب بدهید؛ فقط یک بار نشان داده می‌شود.'})
  if p=='/api/medications':
   mid=str(uuid.uuid4())
   c.execute('INSERT INTO medications VALUES(?,?,?,?,?)',(mid,d.get('name',''),d.get('time',''),d.get('instructions',''),'pending'))
   c.commit()
   return send(self,201,{'id':mid,'ok':True})
  if p.startswith('/api/medications/') and p.endswith('/details'):
   rem=as_float(d.get('remaining',0)); thr=as_float(d.get('refill_threshold',5))
   if rem is None or thr is None: return send(self,400,{'error':'invalid_medication_quantity','message':'remaining و refill_threshold باید عدد باشند.'})
   mid=p.split('/')[3]
   c.execute('INSERT INTO medication_details(medication_id,purpose,remaining,refill_threshold,unit,warnings,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(medication_id) DO UPDATE SET purpose=excluded.purpose,remaining=excluded.remaining,refill_threshold=excluded.refill_threshold,unit=excluded.unit,warnings=excluded.warnings,updated_at=excluded.updated_at',
     (mid,d.get('purpose',''),rem,thr,d.get('unit','عدد'),d.get('warnings',''),now()))
   c.commit()
   return send(self,200,{'ok':True})
  if p.startswith('/api/medications/') and p.endswith('/refill'):
   amount=as_float(d.get('amount',0))
   if amount is None: return send(self,400,{'error':'invalid_amount','message':'amount باید عدد باشد.'})
   mid=p.split('/')[3]; c.execute('UPDATE medication_details SET remaining=remaining+?,updated_at=? WHERE medication_id=?',(amount,now(),mid)); c.commit(); return send(self,200,{'ok':True})
  if p.startswith('/api/medications/') and p.endswith('/event'):
   mid=p.split('/')[3]
   status=d.get('event','pending')
   today=local_now().date().isoformat()
   c.execute('UPDATE medications SET status=? WHERE id=?',(status,mid))
   c.execute('INSERT OR REPLACE INTO medication_logs(id,medication_id,log_date,event,created_at) VALUES(?,?,?,?,?)',(str(uuid.uuid4()),mid,today,status,now()))
   c.execute('INSERT INTO events VALUES(?,?,?,?)',(str(uuid.uuid4()),'medication_'+status,json.dumps({'medication_id':mid,'log_date':today},ensure_ascii=False),now()))
   c.commit()
   return send(self,200,{'ok':True,'status':status,'log_date':today})
  if p=='/api/vitals/share/revoke':
   token=d.get('token','')
   c.execute('UPDATE shares SET revoked=1 WHERE token=?',(token,))
   c.execute('INSERT INTO events VALUES(?,?,?,?)',(str(uuid.uuid4()),'vitals_share_revoked',json.dumps({'token':token},ensure_ascii=False),now()))
   c.commit()
   return send(self,200,{'ok':True})
  if p=='/api/vitals/share':
   edays=as_int(d.get('expires_days',7))
   if edays is None: return send(self,400,{'error':'invalid_expires_days','message':'expires_days باید عدد باشد.'})
   days=max(1,min(edays,30))
   token=uuid.uuid4().hex
   expires=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=days)).isoformat()
   c.execute('INSERT INTO shares VALUES(?,?,?,?,?)',(token,d.get('scope','vitals'),expires,0,now()))
   c.execute('INSERT INTO events VALUES(?,?,?,?)',(str(uuid.uuid4()),'vitals_share_created',json.dumps({'expires_at':expires},ensure_ascii=False),now()))
   c.commit()
   return send(self,201,{'token':token,'url':f'/share/{token}','expires_at':expires})
  if p=='/api/vitals/thresholds':
   items_in=d.get('items',[])
   if not isinstance(items_in,list): return send(self,400,{'error':'invalid_thresholds','message':'items باید فهرست باشد.'})
   # str(None) رشتهٔ 'None' ذخیره می‌کرد و float('None') بعداً ثبت علامت را
   # برای همیشه ۵۰۰ می‌کرد. عدد بودن را همین‌جا در مرز تضمین می‌کنیم.
   parsed=[]
   for item in items_in:
    if not isinstance(item,dict): return send(self,400,{'error':'invalid_threshold','message':'هر قلم آستانه باید شیء باشد.'})
    t=as_text(item.get('type',''))
    if not t: return send(self,400,{'error':'invalid_threshold','message':'type لازم است.'})
    nums=[]
    for k in ('normal_min','normal_max','critical_min','critical_max'):
     n=as_float(item.get(k))
     if n is None: return send(self,400,{'error':'invalid_threshold','message':'مقادیر آستانهٔ '+t+' باید عدد باشند.'})
     nums.append(n)
    if nums[0]>nums[1] or nums[2]>nums[3]:
     return send(self,400,{'error':'inverted_threshold','message':'حد پایین آستانهٔ '+t+' نمی‌تواند از حد بالا بزرگ‌تر باشد.'})
    parsed.append((t,nums))
   for t,(nmin,nmax,cmin,cmax) in parsed:
    c.execute('INSERT INTO vital_thresholds(type,normal_min,normal_max,critical_min,critical_max,updated_by,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(type) DO UPDATE SET normal_min=excluded.normal_min,normal_max=excluded.normal_max,critical_min=excluded.critical_min,critical_max=excluded.critical_max,updated_by=excluded.updated_by,updated_at=excluded.updated_at',
      (t,str(nmin),str(nmax),str(cmin),str(cmax),d.get('updated_by','caregiver'),now()))
   c.commit(); return send(self,200,{'ok':True,'items':rows(c,'SELECT * FROM vital_thresholds ORDER BY type')})
  if p=='/api/vitals':
   kind=d.get('type','unknown'); value=d.get('value'); evaluation=evaluate_vital(c,kind,value)
   if kind not in ('blood_pressure','glucose','weight','heart_rate') or not evaluation['results']: return send(self,400,{'error':'invalid_vital','message':'مقدار علائم حیاتی معتبر نیست'})
   vid=str(uuid.uuid4())
   c.execute('INSERT INTO vitals VALUES(?,?,?,?,?,?)',(vid,kind,json.dumps(value,ensure_ascii=False),d.get('source','manual'),d.get('measured_at',now()),now()))
   c.commit()
   return send(self,201,{'id':vid,'ok':True,'evaluation':evaluation})
  if p.startswith('/api/alerts/') and p.endswith('/ack'):
   aid=p.split('/')[3]
   c.execute("UPDATE alerts SET status='acknowledged' WHERE id=?",(aid,))
   c.execute('INSERT INTO events VALUES(?,?,?,?)',(str(uuid.uuid4()),'alert_acknowledged',json.dumps({'alert_id':aid},ensure_ascii=False),now()))
   c.commit()
   return send(self,200,{'ok':True})
  if p=='/api/alerts':
   aid=str(uuid.uuid4())
   c.execute('INSERT INTO alerts VALUES(?,?,?,?,?,?)',(aid,d.get('type','general'),d.get('message',''),d.get('severity','normal'),'open',now()))
   c.commit()
   return send(self,201,{'id':aid,'ok':True})
  if p=='/api/wallet/topups':
   amount=as_int(d.get('amount',0)); key=idem_key(self,d,'topup')
   if amount is None: return send(self,400,{'error':'invalid_amount','message':'مبلغ باید عدد باشد.'})
   old=c.execute('SELECT * FROM transactions WHERE idempotency_key=?',(key,)).fetchone()
   if old:
    # اثرانگشت درخواست: همان کلید با عملیات یا مبلغ متفاوت، تکرارِ همان
    # درخواست نیست و نباید پاسخِ درخواست قبلی را بی‌صدا برگرداند.
    if old['kind']!='topup' or old['amount']!=amount: return send(self,409,{'error':'idempotency_key_conflict','message':'این کلید تکرارناپذیری پیش‌تر برای درخواست دیگری به کار رفته است.'})
    return send(self,200,{'status':'succeeded','balance':c.execute('SELECT balance FROM wallet WHERE id=1').fetchone()['balance'],'transaction_id':old['id'],'replayed':True})
   if amount<=0 or amount>100000000: return send(self,400,{'error':'invalid_amount'})
   tid=str(uuid.uuid4()); c.execute('UPDATE wallet SET balance=balance+? WHERE id=1',(amount,))
   won,wid=insert_transaction(c,tid,'topup',amount,d.get('description','شارژ کیف پول'),key)
   if won:
    c.commit(); return send(self,200,{'status':'succeeded','balance':c.execute('SELECT balance FROM wallet WHERE id=1').fetchone()['balance'],'transaction_id':tid})
   return send(self,200,{'status':'succeeded','balance':c.execute('SELECT balance FROM wallet WHERE id=1').fetchone()['balance'],'transaction_id':wid,'replayed':True})
  if p=='/api/wallet/payment':
   amount=as_int(d.get('amount',0)); key=idem_key(self,d,'payment')
   if amount is None: return send(self,400,{'error':'invalid_amount','message':'مبلغ باید عدد باشد.'})
   old=c.execute('SELECT * FROM transactions WHERE idempotency_key=?',(key,)).fetchone()
   if old:
    # در جدول، مبلغ پرداخت به‌صورت منفی ذخیره می‌شود.
    if old['kind']!='payment' or old['amount']!=-amount: return send(self,409,{'error':'idempotency_key_conflict','message':'این کلید تکرارناپذیری پیش‌تر برای درخواست دیگری به کار رفته است.'})
    return send(self,200,{'status':'succeeded','balance':c.execute('SELECT balance FROM wallet WHERE id=1').fetchone()['balance'],'transaction_id':old['id'],'replayed':True})
   w=c.execute('SELECT balance FROM wallet WHERE id=1').fetchone()['balance']
   if amount<=0 or amount>w: return send(self,409,{'status':'insufficient_funds','balance':w})
   tid=str(uuid.uuid4()); c.execute('UPDATE wallet SET balance=balance-? WHERE id=1',(amount,))
   won,wid=insert_transaction(c,tid,'payment',-amount,d.get('description','پرداخت'),key)
   if won:
    c.commit(); return send(self,200,{'status':'succeeded','transaction_id':tid,'balance':w-amount})
   return send(self,200,{'status':'succeeded','transaction_id':wid,'balance':c.execute('SELECT balance FROM wallet WHERE id=1').fetchone()['balance'],'replayed':True})
  if p=='/api/events':
   eid=str(uuid.uuid4())
   c.execute('INSERT INTO events VALUES(?,?,?,?)',(eid,d.get('type','unknown'),json.dumps(d.get('payload',{}),ensure_ascii=False),now()))
   c.commit()
   return send(self,201,{'ok':True,'id':eid})
  if p=='/api/education':
   eid=str(uuid.uuid4()); topic=str(d.get('topic','')).strip(); bodytext=str(d.get('body','')).strip()
   if not topic or not bodytext: return send(self,400,{'error':'topic_and_body_required'})
   c.execute('INSERT INTO education_content VALUES(?,?,?,?,?,?,?,?)',(eid,topic,str(d.get('category','عمومی')),bodytext,'pending','',None,now()))
   c.execute('INSERT INTO events VALUES(?,?,?,?)',(str(uuid.uuid4()),'education_submitted',json.dumps({'id':eid,'topic':topic},ensure_ascii=False),now()))
   c.commit()
   return send(self,201,{'id':eid,'status':'pending'})
  if p.startswith('/api/education/') and p.endswith('/approve'):
   eid=p.split('/')[3]; approved_by=str(d.get('approved_by','')).strip()
   if not approved_by: return send(self,400,{'error':'approved_by_required'})
   if not c.execute('SELECT id FROM education_content WHERE id=?',(eid,)).fetchone(): return send(self,404,{'error':'content_not_found'})
   c.execute("UPDATE education_content SET status='approved',approved_by=?,approved_at=?,updated_at=? WHERE id=?",(approved_by,now(),now(),eid))
   c.commit()
   return send(self,200,{'id':eid,'status':'approved'})
  if p=='/api/symptoms':
   sym=str(d.get('symptom','')).strip(); sev=str(d.get('severity','متوسط')).strip()
   if not sym: return send(self,400,{'error':'symptom_required'})
   cat=c.execute('SELECT * FROM symptom_catalog WHERE name=?',(sym,)).fetchone()
   escalate=1 if (cat and cat['escalate']) or sev=='شدید' else 0
   sid=str(uuid.uuid4()); c.execute('INSERT INTO symptom_reports VALUES(?,?,?,?,?,?,?)',(sid,sym,sev,str(d.get('note','')),str(d.get('source','self_report')),escalate,now()))
   resp={'id':sid,'ok':True,'escalated':bool(escalate)}
   if escalate:
    aid=open_alert(c,'symptom_escalation','گزارش خوداظهاری نیازمند بررسی: '+sym+' ('+sev+')','high')
    act=enqueue_caregiver_action(c,'symptom_alert',{'symptom':sym,'severity':sev,'note':str(d.get('note','')),'report_id':sid})
    resp.update({'alert_id':aid,'action_id':act,'reply':'این علامت را ثبت کردم و فوراً به مراقب شما اطلاع دادم. لطفاً منتظر تماس او باشید.'})
   else: resp['reply']='علامت «'+sym+'» را ثبت کردم و در گزارش مراقب شما قرار دادم.'
   c.commit(); return send(self,201,resp)
  if p=='/api/voice-profile':
   pid=str(d.get('id') or 'default')
   old=get_voice_profile(c,pid)
   pat=d.get('patience_ms'); floor=d.get('confidence_floor')
   # به‌روزرسانی جزئی نباید کالیبراسیون یا لهجهٔ اعلام‌شدهٔ کاربر را پاک کند
   try: pat=max(400,min(int(pat),5000)) if pat is not None else old['patience_ms']
   except Exception: pat=old['patience_ms']
   try: floor=max(0.05,min(float(floor),0.95)) if floor is not None else old['confidence_floor']
   except Exception: floor=old['confidence_floor']
   try: pat=max(400,min(int(pat),5000))
   except Exception: pat=DEFAULT_PATIENCE_MS
   try: floor=max(0.05,min(float(floor),0.95))
   except Exception: floor=0.55
   name=str(d.get('name') or old['name'] or 'کاربر')
   dial=str(d.get('dialect') or old['dialect'] or 'standard')
   sec=str(d.get('secondary_dialect') if d.get('secondary_dialect') is not None else (old['secondary_dialect'] or ''))
   cal=1 if (d['calibrated'] if 'calibrated' in d else old['calibrated']) else 0
   c.execute('INSERT OR REPLACE INTO voice_profiles VALUES(?,?,?,?,?,?,?,?)',(pid,name,dial,sec,pat,floor,cal,now()))
   c.execute('INSERT INTO events VALUES(?,?,?,?)',(str(uuid.uuid4()),'voice_profile_set',json.dumps({'dialect':dial,'patience_ms':pat},ensure_ascii=False),now())); c.commit()
   return send(self,200,get_voice_profile(c,pid))
  if p=='/api/calibration':
   """کالیبراسیون کوتاه هنگام راه‌اندازی: کاربر چند عبارت کوتاه می‌خواند؛ اطمینان‌ها سنجیده و صبر و آستانه تنظیم می‌شود."""
   pid=str(d.get('id') or 'default'); samples=d.get('samples') or []
   if not isinstance(samples,list) or not samples: return send(self,400,{'error':'samples_required'})
   confs=[]
   for s in samples:
    try: v=float(s.get('confidence'))
    except Exception: v=None
    if v is not None: confs.append(max(0.0,min(v,1.0)))
   if not confs: return send(self,400,{'error':'no_numeric_confidence'})
   avg=sum(confs)/len(confs); worst=min(confs)
   # پژوهش CHI'26: کالیبراسیون شخصی + آستانه محافظه‌کارانه برای گفتار سالمند
   patience=int(round(DEFAULT_PATIENCE_MS*(1.0+(0.55-avg)) )) if avg<0.55 else DEFAULT_PATIENCE_MS
   patience=max(900,min(patience,4000))
   floor=0.40 if avg<0.5 else (0.50 if avg<0.7 else 0.60)
   c.execute('INSERT OR REPLACE INTO voice_profiles VALUES(?,?,?,?,?,?,?,?)',
     (pid,str(d.get('name') or 'کاربر'),str(d.get('dialect') or (c.execute('SELECT dialect FROM voice_profiles WHERE id=?',(pid,)).fetchone() or {'dialect':'standard'})['dialect']),str(d.get('secondary_dialect') or ''),patience,floor,1,now()))
   c.execute('INSERT INTO events VALUES(?,?,?,?)',
     (str(uuid.uuid4()),'voice_calibration',json.dumps({'samples':len(confs),'avg':round(avg,3),'worst':round(worst,3),'patience_ms':patience,'confidence_floor':floor},ensure_ascii=False),now()))
   c.commit()
   return send(self,200,{'ok':True,'samples':len(confs),'avg_confidence':round(avg,3),'worst_confidence':round(worst,3),'patience_ms':patience,'confidence_floor':floor,'advice':'آرام و شمرده بخوانید؛ دستگاه وسط جمله شما را قطع نمی‌کند.'})
  if p=='/api/disambiguate':
   text=str(d.get('text','')); conf=d.get('confidence')
   try: conf=float(conf) if conf is not None else None
   except Exception: conf=None
   _lim=as_int(d.get('limit') or 2)
   if _lim is None: return send(self,400,{'error':'invalid_limit','message':'limit باید عدد باشد.'})
   limit=min(max(_lim,2),3)
   prof=get_voice_profile(c,str(d.get('profile') or 'default'))
   cands=match_candidates(c,text,limit,prof['dialect'],prof['secondary_dialect'],str(d.get('profile') or 'default'))
   if len(cands)<2:
    for r in rows(c,'SELECT * FROM intent_lexicon ORDER BY priority DESC LIMIT 5'):
     if r['id'] not in [x['id'] for x in cands]: cands.append({'id':r['id'],'label':r['label'],'action':r['action'],'image_query':r['image_query'],'score':0})
     if len(cands)>=2: break
   if len(cands)<2: return send(self,200,{'needs_clarification':False,'reason':'not_enough_candidates','repeat_prompt':'متوجه نشدم؛ لطفاً آرام‌تر و کوتاه‌تر بگویید.'})
   opts=[]
   for x in cands[:2]:
    imgs=fetch_images(c,x['image_query'],1)
    opts.append({'id':x['id'],'label':x['label'],'action':x['action'],'image':(imgs[0] if imgs else None),'score':x['score']})
   eid=str(uuid.uuid4())
   c.execute('INSERT INTO disambiguation_events VALUES(?,?,?,?,?,?,?)',(eid,text[:300],conf,json.dumps([o['id'] for o in opts],ensure_ascii=False),'',0,now()))
   c.execute('INSERT INTO events VALUES(?,?,?,?)',(str(uuid.uuid4()),'disambiguation_asked',json.dumps({'confidence':conf},ensure_ascii=False),now())); c.commit()
   return send(self,200,{'id':eid,'needs_clarification':True,'question':'منظورتان کدام یک است؟','spoken':'منظورتان کدام است؟ اولی، '+opts[0]['label']+'؟ یا دومی، '+opts[1]['label']+'؟','options':opts,'transcript':text,'confidence':conf})
  if p=='/api/disambiguate/resolve':
   eid=str(d.get('id','')); chosen=str(d.get('chosen',''))
   row=c.execute('SELECT * FROM disambiguation_events WHERE id=?',(eid,)).fetchone()
   if not row: return send(self,404,{'error':'session_not_found'})
   c.execute('UPDATE disambiguation_events SET chosen=?,resolved=1 WHERE id=?',(chosen,eid))
   lex=c.execute('SELECT * FROM intent_lexicon WHERE id=?',(chosen,)).fetchone()
   # یادگیری: همان عبارت لهجه‌دار دفعه بعد مستقیم شناخته می‌شود (پژوهش: ترمیم توسط کاربر ~۶۰٪ موفق)
   learned=False
   if lex and not chosen.startswith('__') and row['transcript']:
    learned=learn_alias(c,row['transcript'],chosen,'disambiguation',str(d.get('profile') or 'default'))
   c.execute('INSERT INTO events VALUES(?,?,?,?)',(str(uuid.uuid4()),'disambiguation_resolved',json.dumps({'chosen':chosen,'transcript':row['transcript']},ensure_ascii=False),now())); c.commit()
   return send(self,200,{'ok':True,'action':lex['action'] if lex else None,'label':lex['label'] if lex else chosen,'learned':learned,'aliases':c.execute('SELECT COUNT(*) FROM utterance_aliases').fetchone()[0]})
  if p=='/api/screen-tasks':
   rid=str(uuid.uuid4())
   st_tot=as_int(d.get('steps_total') or 0); st_done=as_int(d.get('steps_done') or 0)
   if st_tot is None or st_done is None: return send(self,400,{'error':'invalid_steps','message':'steps_total و steps_done باید عدد باشند.'})
   # as_text نه str(): str({'a':1}) بی‌صدا «{'a': 1}» را به‌عنوان متن ذخیره می‌کرد
   _flds=[as_text(d.get(k,'')) for k in ('package','title','status','error')]
   if any(f is None for f in _flds): return send(self,400,{'error':'invalid_field_type','message':'مقدار این فیلد باید ساده باشد (رشته/عدد)، نه شیء یا آرایه.'})
   c.execute('INSERT INTO screen_task_runs VALUES(?,?,?,?,?,?,?,?,?)',(rid,_flds[0],_flds[1],_flds[2],st_tot,st_done,_flds[3],str(d.get('started_at') or now()),now()))
   c.execute('INSERT INTO events VALUES(?,?,?,?)',(str(uuid.uuid4()),'screen_task_finished',json.dumps({'package':d.get('package'),'status':d.get('status')},ensure_ascii=False),now())); c.commit()
   return send(self,201,{'id':rid,'ok':True})
  if p=='/api/caregiver/session':
   phone=str(d.get('phone','')).strip()
   if not phone: return send(self,400,{'error':'phone_required'})
   cg=c.execute('SELECT * FROM caregivers WHERE phone=?',(phone,)).fetchone()
   # پاسخ یکسان برای «شماره نیست» و «کد غلط است» تا وجود مراقب لو نرود.
   # توجه: send() اثر جانبی دارد و فوراً پاسخ را می‌نویسد، پس نباید
   # نتیجه‌اش را در متغیر ذخیره کرد؛ وگرنه پیش از اعتبارسنجی ۴۰۳ فرستاده می‌شود.
   if not cg: return send(self,403,{'error':'invalid_credentials','message':'شماره یا کد دعوت نادرست است.'})
   # قفل باید پیش از اعتبارسنجی بررسی شود؛ وگرنه مهاجمی که بالاخره کد درست را
   # حدس بزند هرگز به آن نمی‌رسد و محدودسازی نرخ بی‌اثر می‌ماند.
   if cg['locked_until'] and cg['locked_until']>now():
    return send(self,429,{'error':'too_many_attempts','message':'به دلیل تلاش‌های ناموفق، ورود موقتاً مسدود است.'})
   # شماره به‌تنهایی شناسه است نه راز؛ بدون کد دعوت هیچ جلسه‌ای باز نمی‌شود
   code=str(d.get('code') or d.get('invite_code') or '').strip()
   stored=str(cg['invite_code'] or '')
   # compare_digest روی str غیر-ASCII استثنا می‌دهد؛ چون رابط کاربری فارسی است،
   # تایپ اشتباه متن فارسی در فیلد کد نباید ۵۰۰ بدهد -> هر دو به بایت
   if not stored or not code or not hmac.compare_digest(code.encode('utf-8'),stored.encode('utf-8')):
    fa=int(cg['failed_attempts'] or 0)+1
    lock=None
    if fa>=5:
     lock=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=15)).isoformat(); fa=0
    c.execute('UPDATE caregivers SET failed_attempts=?,locked_until=? WHERE id=?',(fa,lock,cg['id']))
    c.execute('INSERT INTO events VALUES(?,?,?,?)',(str(uuid.uuid4()),'caregiver_login_failed',json.dumps({'phone':mask_phone(phone)},ensure_ascii=False),now())); c.commit()
    return send(self,403,{'error':'invalid_credentials','message':'شماره یا کد دعوت نادرست است.'+((' به دلیل تلاش‌های ناموفق، ۱۵ دقیقه مسدود است.') if lock else '')})
   if not consent_granted(c,'health'): return send(self,403,{'error':'senior_consent_not_granted','message':'سالمند هنوز رضایت خود را برای اشتراک‌گذاری اطلاعات سلامت ثبت نکرده است.'})
   c.execute('UPDATE caregivers SET failed_attempts=0,locked_until=NULL WHERE id=?',(cg['id'],))
   tok=secrets.token_urlsafe(32); exp=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=7)).isoformat()
   c.execute('INSERT INTO caregiver_sessions VALUES(?,?,?,?)',(tok,phone,now(),exp))
   c.execute('INSERT INTO events VALUES(?,?,?,?)',(str(uuid.uuid4()),'caregiver_session_opened',json.dumps({'phone':phone},ensure_ascii=False),now()))
   c.commit()
   return send(self,201,{'token':tok,'expires_at':exp,'caregiver':{'name':cg['name'],'role':cg['role']}})
  if p=='/api/caregiver/session/revoke':
   s=caregiver_session(c,self.headers)
   if not s: return send(self,403,{'error':'caregiver_session_required'})
   c.execute('DELETE FROM caregiver_sessions WHERE token=?',(s['token'],)); c.commit(); return send(self,200,{'ok':True})
  if p=='/api/caregiver/call-request':
   cg=primary_caregiver(c)
   if not cg: return send(self,409,{'error':'no_caregiver','message':'هنوز مراقبی ثبت نشده است.'})
   aid=enqueue_caregiver_action(c,'call_request',{'phone':cg['phone'],'caregiver':cg['name'],'reason':str(d.get('reason','درخواست تماس سالمند'))})
   c.execute('INSERT INTO events VALUES(?,?,?,?)',(str(uuid.uuid4()),'call_requested',json.dumps({'caregiver':cg['name']},ensure_ascii=False),now()))
   c.commit()
   return send(self,201,{'id':aid,'ok':True,'status':'pending','caregiver':cg['name'],'phone':cg['phone'],'reply':'درخواست تماس را برای '+cg['name']+' فرستادم.'})
  if p.startswith('/api/caregiver/actions/') and p.endswith('/deliver'):
   # بی‌گارد بودن این مسیر فقط حریم خصوصی نیست، «ایمنی» است: مهاجم می‌توانست
   # درخواست تماسِ در انتظار سالمند را delivered علامت بزند و از صف مراقب ناپدیدش
   # کند، پس هیچ‌کس سراغ سالمند نمی‌رفت. اندازه‌گیری شد: POST ناشناس → 200 delivered.
   if not caregiver_session(c,self.headers): return send(self,403,{'error':'caregiver_session_required','message':'برای دیدن این صفحه، ابتدا با شماره همراه مراقب وارد شوید.'})
   aid=p.split('/')[4]; row=c.execute('SELECT * FROM caregiver_actions WHERE id=?',(aid,)).fetchone()
   if not row: return send(self,404,{'error':'action_not_found'})
   c.execute("UPDATE caregiver_actions SET status='delivered',delivered_at=?,delivered_by=? WHERE id=?",(now(),str(d.get('delivered_by','caregiver')),aid))
   if row['kind']=='message':
    try: mid=json.loads(row['payload'] or '{}').get('message_id')
    except Exception: mid=None
    if mid: c.execute("UPDATE messages SET status='delivered' WHERE id=? AND status='queued'",(mid,))
   c.execute('INSERT INTO events VALUES(?,?,?,?)',(str(uuid.uuid4()),'caregiver_action_delivered',json.dumps({'id':aid,'kind':row['kind']},ensure_ascii=False),now()))
   c.commit()
   return send(self,200,{'id':aid,'status':'delivered'})
  if p=='/api/ai/chat':
   text=str(d.get('text','')); risk=assess_risk(c,text)
   if risk['level']!='normal':
    extra={}
    if risk['action']=='emergency':
     cg=primary_caregiver(c) or {}
     extra={'alert_id':open_alert(c,'clinical_risk','گفت‌وگوی نیازمند بررسی فوری: '+str(risk['matched']),'critical'),
       'action_id':enqueue_caregiver_action(c,'call_request',{'phone':cg.get('phone',''),'caregiver':cg.get('name',''),'reason':'گزارش پرخطر در گفت‌وگو: '+str(risk['matched'])}),
       'matched':risk['matched']}
    else: extra={'action_id':enqueue_caregiver_action(c,'professional_referral',{'text':text[:300],'matched':risk['matched']}),'matched':risk['matched']}
    c.execute('INSERT INTO events VALUES(?,?,?,?)',(str(uuid.uuid4()),'safety_intercept',json.dumps({'level':risk['level'],'matched':risk['matched']},ensure_ascii=False),now())); c.commit()
    remember(c,str(d.get('profile') or 'default'),'user',text,'safety_intercept',1)
    remember(c,str(d.get('profile') or 'default'),'assistant',risk['reply'],'safety_intercept',1); c.commit()
    out={'ok':True,
      'text':risk['reply'],
      'provider':'safety_guardrail',
      'safety':'urgent' if risk['level']=='critical' else 'caution',
      'clinical_answer_blocked':True,
      'requires_escalation':risk['action']=='emergency'}
    out.update(extra)
    return send(self,200,out)
   pid=str(d.get('profile') or 'default')
   remember(c,pid,'user',text,'chat')
   answer=call_llm(c,text,d.get('context'),pid)
   if answer: remember(c,pid,'assistant',answer,'chat')
   c.commit()
   return send(self,200,{'ok':True,'text':answer,'provider':'configured'}) if answer else send(self,503,{'ok':False,'error':'ai_not_configured_or_unavailable'})
  if p=='/api/conversation':
   risk=assess_risk(c,d.get('text',''))
   if risk['level']!='normal':
    extra={}
    if risk['action']=='emergency':
     cg=primary_caregiver(c) or {}
     extra={'alert_id':open_alert(c,'clinical_risk','گفت‌وگوی نیازمند بررسی فوری: '+str(risk['matched']),'critical'),
       'action_id':enqueue_caregiver_action(c,'call_request',{'phone':cg.get('phone',''),'caregiver':cg.get('name',''),'reason':'گزارش پرخطر در گفت‌وگو: '+str(risk['matched'])})}
    else: extra={'action_id':enqueue_caregiver_action(c,'professional_referral',{'text':str(d.get('text',''))[:300],'matched':risk['matched']})}
    c.execute('INSERT INTO events VALUES(?,?,?,?)',(str(uuid.uuid4()),'safety_intercept',json.dumps({'level':risk['level'],'matched':risk['matched']},ensure_ascii=False),now())); c.commit()
    out={'intent':'safety.emergency' if risk['action']=='emergency' else 'safety.referral',
      'spoken_reply':risk['reply'],
      'requires_confirmation':True,
      'safety':'urgent' if risk['level']=='critical' else 'caution',
      'clinical_answer_blocked':True}
    out.update(extra)
    return send(self,200,out)
   raw=str(d.get('text','')); pid=str(d.get('profile') or 'default'); prof=get_voice_profile(c,pid)
   alias,ascore=find_alias(c,raw,pid)
   text,rules=normalize_dialect(c,raw,prof['dialect'],prof['secondary_dialect'])
   text=text.replace('ي','ی').replace('ك','ک'); intent='conversation.general'; reply='درخواست شما را شنیدم و آماده کمک هستم.'
   if alias:
    intent=alias['intent_id']; alab=(c.execute('SELECT label FROM intent_lexicon WHERE id=?',(intent,)).fetchone() or {'label':intent})['label']
    reply='بله، '+alab+' — از بار قبل یادم مانده.'
   elif 'کیف پول' in text or 'موجودی' in text: intent='wallet.balance'; reply='موجودی کیف پول شما آماده بررسی است.'
   elif 'دارو' in text: intent='medication.list_today'; reply='داروهای امروز شما را آماده کردم.'
   elif 'کمک' in text or 'اورژانس' in text: intent='emergency.request_help'; reply='درخواست کمک فوری نیازمند تأیید صوتی شماست.'
   conf=d.get('confidence')
   try: conf=float(conf) if conf is not None else None
   except Exception: conf=None
   floor=prof['confidence_floor'] if prof['confidence_floor'] else 0.55
   stuck=(intent=='conversation.general' and not is_smalltalk(text)) or (conf is not None and conf<floor)
   return send(self,200,{'intent':intent,'spoken_reply':reply,'requires_confirmation':intent.startswith(('wallet','emergency')),'safety':'caution' if intent.startswith(('wallet','emergency')) else 'normal','needs_clarification':bool(stuck),'candidates':match_candidates(c,text,2,prof['dialect'],prof['secondary_dialect'],pid) if stuck else [],'confidence':conf,'normalized':text,'dialect_rules_applied':rules,'alias_used':alias['intent_id'] if alias else None,'patience_ms':prof['patience_ms'],'confidence_floor':floor})
  return send(self,404,{'error':'not_found'})
