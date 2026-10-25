"""سپندیار — database"""
import json, sqlite3, os, uuid, datetime, hashlib, re, difflib, time, secrets, hmac, threading, html, math, urllib.request as ureq, urllib.error as uerr
from zoneinfo import ZoneInfo
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, quote, unquote, parse_qs

from .clock import now
from .config import DB

# ================= بخش ۲: پایگاه‌داده — اتصال، PRAGMAها و طرحواره =================
def db(h=None):
 # اتصال روی هندلر ثبت می‌شود تا در پایان درخواست بسته شود؛
 # وگرنه خطای وسط تراکنش، قفل نوشتن را رها می‌کند و کل پایگاه‌داده قفل می‌شود
 c=sqlite3.connect(DB,timeout=15); c.row_factory=sqlite3.Row
 # پایانهٔ PRAGMA عملکردی. ترتیب مهم است: نخست journal_mode، بعد دوام، بعد حافظهٔ نهان.
 # journal_mode در سرآیند «فایل» پایگاه‌داده نوشته می‌شود و پایاست؛ بقیه اتصال‌محورند و
 # در هر اتصال نو به مقدار پیش‌فرض برمی‌گردند، پس باید هر بار تنظیم شوند.
 # cache_size عمداً کوچک‌تر از توصیهٔ رایج ۶۴MB است: آن عدد برای pool اتصال نوشته شده،
 # ولی این سرور به‌ازای «هر درخواست» یک اتصال می‌گشاید و سقف حافظه در همزمانی ضرب می‌شود.
 c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA synchronous=NORMAL')
 c.execute('PRAGMA busy_timeout=15000'); c.execute('PRAGMA cache_size=-8000')
 c.execute('PRAGMA temp_store=MEMORY')
 if h is not None: h._db=c
 c.executescript('''CREATE TABLE IF NOT EXISTS profile(id INTEGER PRIMARY KEY CHECK(id=1),name TEXT,age INTEGER,needs TEXT,assistant_name TEXT,updated_at TEXT);
 CREATE TABLE IF NOT EXISTS caregivers(id TEXT PRIMARY KEY,name TEXT,phone TEXT,role TEXT,permissions TEXT,created_at TEXT);
 CREATE TABLE IF NOT EXISTS wallet(id INTEGER PRIMARY KEY CHECK(id=1),balance INTEGER NOT NULL DEFAULT 0,currency TEXT NOT NULL DEFAULT 'IRR');
 CREATE TABLE IF NOT EXISTS transactions(id TEXT PRIMARY KEY,kind TEXT,amount INTEGER,description TEXT,idempotency_key TEXT UNIQUE,created_at TEXT);
 CREATE TABLE IF NOT EXISTS medications(id TEXT PRIMARY KEY,name TEXT,time TEXT,instructions TEXT,status TEXT DEFAULT 'pending');
 CREATE TABLE IF NOT EXISTS medication_details(medication_id TEXT PRIMARY KEY,purpose TEXT,remaining REAL,refill_threshold REAL DEFAULT 5,unit TEXT DEFAULT 'عدد',warnings TEXT,updated_at TEXT);
 CREATE TABLE IF NOT EXISTS medication_logs(id TEXT PRIMARY KEY,medication_id TEXT,log_date TEXT,event TEXT,created_at TEXT,UNIQUE(medication_id,log_date));
 CREATE TABLE IF NOT EXISTS reminder_events(id TEXT PRIMARY KEY,medication_id TEXT,reminder_date TEXT,channel TEXT,created_at TEXT,UNIQUE(medication_id,reminder_date,channel));
 CREATE TABLE IF NOT EXISTS reminder_settings(id INTEGER PRIMARY KEY CHECK(id=1),quiet_start TEXT DEFAULT '22:00',quiet_end TEXT DEFAULT '07:00',max_nudges INTEGER DEFAULT 2,preferred_channel TEXT DEFAULT 'voice',updated_at TEXT);
 CREATE TABLE IF NOT EXISTS proactive_events(id TEXT PRIMARY KEY,kind TEXT,prompt_date TEXT,delivered_at TEXT,response TEXT,responded_at TEXT);
 CREATE TABLE IF NOT EXISTS vitals(id TEXT PRIMARY KEY,type TEXT,value TEXT,source TEXT,measured_at TEXT,created_at TEXT);
 CREATE TABLE IF NOT EXISTS alerts(id TEXT PRIMARY KEY,type TEXT,message TEXT,severity TEXT,status TEXT DEFAULT 'open',created_at TEXT);
 CREATE TABLE IF NOT EXISTS shares(token TEXT PRIMARY KEY,scope TEXT,expires_at TEXT,revoked INTEGER DEFAULT 0,created_at TEXT);
 CREATE TABLE IF NOT EXISTS consents(scope TEXT PRIMARY KEY,granted INTEGER DEFAULT 0,confirmed_by_voice INTEGER DEFAULT 0,updated_at TEXT,updated_by TEXT);
 CREATE TABLE IF NOT EXISTS care_tasks(id TEXT PRIMARY KEY,title TEXT,kind TEXT,assigned_to TEXT,due_at TEXT,status TEXT DEFAULT 'pending',created_at TEXT);
 CREATE TABLE IF NOT EXISTS checkins(id TEXT PRIMARY KEY,mood TEXT,pain TEXT,sleep TEXT,note TEXT,created_at TEXT);
 CREATE TABLE IF NOT EXISTS icope_assessments(id TEXT PRIMARY KEY,domain TEXT,score REAL,status TEXT,notes TEXT,assessed_by TEXT,assessed_at TEXT);
 CREATE TABLE IF NOT EXISTS food_items(id TEXT PRIMARY KEY,name TEXT,quantity TEXT,source TEXT,created_at TEXT);
 CREATE TABLE IF NOT EXISTS contacts(id TEXT PRIMARY KEY,name TEXT,phone TEXT,relationship TEXT,created_at TEXT);
 CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,contact_id TEXT,body TEXT,kind TEXT,created_at TEXT,status TEXT DEFAULT 'queued');
 CREATE TABLE IF NOT EXISTS appointments(id TEXT PRIMARY KEY,title TEXT,provider TEXT,location TEXT,starts_at TEXT,reminder_minutes INTEGER DEFAULT 60,status TEXT DEFAULT 'scheduled',created_at TEXT);
 CREATE TABLE IF NOT EXISTS doctors(id TEXT PRIMARY KEY,name TEXT,specialty TEXT,phone TEXT,address TEXT,clinic TEXT,preferred INTEGER DEFAULT 0,created_at TEXT);
 CREATE TABLE IF NOT EXISTS emergency_card(id INTEGER PRIMARY KEY CHECK(id=1),full_name TEXT,birth_date TEXT,blood_type TEXT,allergies TEXT,conditions TEXT,critical_meds TEXT,primary_doctor TEXT,emergency_contact TEXT,updated_at TEXT);
 CREATE TABLE IF NOT EXISTS locations(id TEXT PRIMARY KEY,lat REAL,lon REAL,accuracy REAL,source TEXT,created_at TEXT);
 CREATE TABLE IF NOT EXISTS safe_zones(id TEXT PRIMARY KEY,name TEXT,lat REAL,lon REAL,radius_m REAL,enabled INTEGER DEFAULT 1,created_at TEXT);
 CREATE TABLE IF NOT EXISTS ai_config(id INTEGER PRIMARY KEY CHECK(id=1),provider TEXT,base_url TEXT,model TEXT,stt_provider TEXT,tts_provider TEXT,system_prompt TEXT,guardrails TEXT,voice_id TEXT,tone TEXT,temperature REAL,updated_at TEXT);
 CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,type TEXT,payload TEXT,created_at TEXT);
 CREATE TABLE IF NOT EXISTS vital_thresholds(type TEXT PRIMARY KEY,normal_min TEXT,normal_max TEXT,critical_min TEXT,critical_max TEXT,updated_by TEXT,updated_at TEXT);
 CREATE TABLE IF NOT EXISTS education_content(id TEXT PRIMARY KEY,topic TEXT,category TEXT,body TEXT,status TEXT DEFAULT 'pending',approved_by TEXT,approved_at TEXT,updated_at TEXT);
 CREATE TABLE IF NOT EXISTS symptom_catalog(name TEXT PRIMARY KEY,escalate INTEGER DEFAULT 0,sort_order INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS symptom_reports(id TEXT PRIMARY KEY,symptom TEXT,severity TEXT,note TEXT,source TEXT DEFAULT 'self_report',escalated INTEGER DEFAULT 0,created_at TEXT);
 CREATE TABLE IF NOT EXISTS caregiver_actions(id TEXT PRIMARY KEY,kind TEXT,payload TEXT,status TEXT DEFAULT 'pending',requested_by TEXT,requested_at TEXT,delivered_at TEXT,delivered_by TEXT);
 CREATE TABLE IF NOT EXISTS caregiver_sessions(token TEXT PRIMARY KEY,phone TEXT,created_at TEXT,expires_at TEXT);
 CREATE TABLE IF NOT EXISTS safety_rules(id TEXT PRIMARY KEY,level TEXT,pattern TEXT,action TEXT,reply TEXT,updated_at TEXT);
 CREATE TABLE IF NOT EXISTS approved_apps(package TEXT PRIMARY KEY,label TEXT,category TEXT,icon TEXT,plan TEXT,enabled INTEGER DEFAULT 1,updated_at TEXT);
 CREATE TABLE IF NOT EXISTS screen_task_runs(id TEXT PRIMARY KEY,app_package TEXT,title TEXT,status TEXT,steps_total INTEGER,steps_done INTEGER,error TEXT,started_at TEXT,finished_at TEXT);
 CREATE TABLE IF NOT EXISTS intent_lexicon(id TEXT PRIMARY KEY,label TEXT,action TEXT,keywords TEXT,image_query TEXT,priority INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS image_cache(query TEXT PRIMARY KEY,items TEXT,source TEXT,fetched_at TEXT);
 CREATE TABLE IF NOT EXISTS disambiguation_events(id TEXT PRIMARY KEY,transcript TEXT,confidence REAL,options TEXT,chosen TEXT,resolved INTEGER DEFAULT 0,created_at TEXT);
 CREATE TABLE IF NOT EXISTS dialect_lexicon(id TEXT PRIMARY KEY,accent TEXT,variant TEXT,canonical TEXT,note TEXT);
 CREATE TABLE IF NOT EXISTS voice_profiles(id TEXT PRIMARY KEY,name TEXT,dialect TEXT,secondary_dialect TEXT,patience_ms INTEGER,confidence_floor REAL,calibrated INTEGER DEFAULT 0,updated_at TEXT);
 CREATE TABLE IF NOT EXISTS utterance_aliases(id TEXT PRIMARY KEY,transcript TEXT,intent_id TEXT,source TEXT,weight INTEGER DEFAULT 1,created_at TEXT);
 CREATE TABLE IF NOT EXISTS conversation_turns(id TEXT PRIMARY KEY,profile_id TEXT,role TEXT,content TEXT,intent TEXT,flagged INTEGER DEFAULT 0,created_at TEXT);
 CREATE INDEX IF NOT EXISTS ix_turns_profile ON conversation_turns(profile_id,created_at);
 CREATE TABLE IF NOT EXISTS prescriptions(id TEXT PRIMARY KEY,image_ref TEXT,source TEXT,status TEXT,notes TEXT,created_at TEXT,UNIQUE(image_ref));
 CREATE TABLE IF NOT EXISTS prescription_items(id TEXT PRIMARY KEY,prescription_id TEXT,name TEXT,dose TEXT,schedule TEXT,confirmed INTEGER DEFAULT 0,medication_id TEXT,created_at TEXT);
 -- ایندکس‌ها فقط روی مسیرهای داغی که واقعاً در این فایل پرس‌وجو می‌شوند.
 -- سهم token در shares و caregiver_sessions «عمداً» ایندکس نگرفت: هر دو PRIMARY KEY
 -- هستند و ایندکس دوم روی آن‌ها فقط نوشتن را کندتر و فایل را بزرگ‌تر می‌کرد.
 -- reminder_date و log_date لازم‌اند چون ایندکس UNIQUE موجود با medication_id شروع
 -- می‌شود و پرس‌وجوی «فقط بر پایهٔ تاریخ» نمی‌تواند از آن استفاده کند.
 CREATE INDEX IF NOT EXISTS ix_vitals_measured ON vitals(measured_at);
 CREATE INDEX IF NOT EXISTS ix_alerts_status_created ON alerts(status,created_at);
 CREATE INDEX IF NOT EXISTS ix_actions_requested ON caregiver_actions(requested_at);
 CREATE INDEX IF NOT EXISTS ix_transactions_created ON transactions(created_at);
 CREATE INDEX IF NOT EXISTS ix_messages_created ON messages(created_at);
 CREATE INDEX IF NOT EXISTS ix_locations_created ON locations(created_at);
 CREATE INDEX IF NOT EXISTS ix_reminder_events_date ON reminder_events(reminder_date);
 CREATE INDEX IF NOT EXISTS ix_medication_logs_date ON medication_logs(log_date);;''')
 defaults=[('systolic','90','140','80','180'),('diastolic','60','90','50','120'),('glucose','70','180','54','300'),('weight','0','1000','0','1000')]
 for t,nmin,nmax,cmin,cmax in defaults: c.execute('INSERT OR IGNORE INTO vital_thresholds(type,normal_min,normal_max,critical_min,critical_max,updated_by,updated_at) VALUES(?,?,?,?,?,?,?)',(t,nmin,nmax,cmin,cmax,'system',now()))
 pecols=[x[1] for x in c.execute('PRAGMA table_info(proactive_events)').fetchall()]
 if 'escalated_at' not in pecols: c.execute('ALTER TABLE proactive_events ADD COLUMN escalated_at TEXT')
 cgcols=[x[1] for x in c.execute('PRAGMA table_info(caregivers)').fetchall()]
 for _col,_ddl in (('invite_code','TEXT'),('failed_attempts','INTEGER DEFAULT 0'),('locked_until','TEXT')):
  if _col not in cgcols: c.execute('ALTER TABLE caregivers ADD COLUMN %s %s'%(_col,_ddl))
 # شمارهٔ تکراری باعث می‌شد کد دعوتِ نشان‌داده‌شده به ردیف دیگری تعلق داشته باشد
 # تا ردیفی که هنگام ورود بررسی می‌شود؛ پس اول تکراری‌ها پاک و سپس قید یکتا ساخته می‌شود.
 # توجه: MIN(rowid) باید با GROUP BY phone باشد؛ کوئری همبسته با «phone IS caregivers.phone»
 # به همان حوزهٔ داخلی وصل می‌شد و همهٔ ردیف‌ها جز نخستین را پاک می‌کرد.
 if c.execute('SELECT 1 FROM caregivers GROUP BY phone HAVING COUNT(*)>1 LIMIT 1').fetchone():
  c.execute('DELETE FROM caregivers WHERE rowid NOT IN (SELECT MIN(rowid) FROM caregivers GROUP BY phone)'); c.commit()
 # ردیف‌های بی‌شماره پیش از افزودن این اعتبارسنجی ساخته شده بودند؛ چنین مراقبی
 # هرگز نمی‌تواند وارد شود (شماره برای ورود الزامی است) پس دادهٔ مرده است
 c.execute("DELETE FROM caregivers WHERE phone IS NULL OR TRIM(phone)=''")
 c.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_caregivers_phone ON caregivers(phone)')
 cols=[x[1] for x in c.execute('PRAGMA table_info(transactions)').fetchall()]
 if 'idempotency_key' not in cols:
  c.execute('ALTER TABLE transactions ADD COLUMN idempotency_key TEXT')
  c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_idempotency ON transactions(idempotency_key)')
 c.execute('INSERT OR IGNORE INTO wallet(id,balance,currency) VALUES(1,1250000,"IRR")')
 c.execute('INSERT OR IGNORE INTO ai_config(id,provider,base_url,model,stt_provider,tts_provider,system_prompt,guardrails,voice_id,tone,temperature,updated_at) VALUES(1,?,?,?,?,?,?,?,?,?,?,?)',
   ('openrouter','https://openrouter.ai/api/v1','openai/gpt-4o-mini','whisper','native-tts','تو یک دستیار فارسی محترم، کوتاه‌گو و شفاف برای سالمندان هستی.','هرگز تشخیص قطعی، تغییر دوز دارو، پرداخت یا تماس اضطراری را بدون تأیید انجام نده. در ابهام سؤال روشن‌کننده بپرس.','friendly_fa','گرم، آرام، کوتاه و غیرکودکانه',0.2,now()))
 c.execute('INSERT OR IGNORE INTO reminder_settings(id,quiet_start,quiet_end,max_nudges,preferred_channel,updated_at) VALUES(1,?,?,?,?,?)',('22:00','07:00',2,'voice',now()))
 edu=[('medication_adherence','دارو','پایبندی دارویی','داروها را سر همان ساعت و با همان مقدار که پزشک نوشته مصرف کنید. اگر یک نوبت را فراموش کردید، مقدار را دو برابر نکنید؛ فقط به من بگویید تا ثبت کنم و به مراقب شما اطلاع دهم.','نمونه اولیه — نیازمند تأیید پزشک'),
      ('blood_pressure',
        'فشار خون',
        'اندازه‌گیری در خانه',
        'فشار خون را در حالت نشسته و پس از پنج دقیقه استراحت اندازه بگیرید و بازو هم‌سطح قلب باشد. مقدار را با صدا به من بگویید تا در پرونده ثبت شود.',
        'نمونه اولیه — نیازمند تأیید پزشک'),
      ('salt_diet','تغذیه','نمک کمتر','مصرف نمکدان را سر سفره کنار بگذارید و به‌جای آن از سبزی معطر، لیمو و ادویه استفاده کنید. غذاهای کنسروی و شور را کمتر کنید.','نمونه اولیه — نیازمند تأیید پزشک'),
      ('walking','فعالیت بدنی','حرکت روزانه','روزی چند بار کوتاه راه رفتن در خانه یا حیاط، به‌همراه کسی یا با تکیه‌گاه مطمئن، بهتر از یک پیاده‌روی طولانی و خسته‌کننده است.','نمونه اولیه — نیازمند تأیید پزشک'),
      ('hydration','آب','نوشیدن آب','در طول روز جرعه‌جرعه آب بنوشید، حتی وقتی تشنه نیستید. اگر پزشک برای شما محدودیت مایعات تعیین کرده، همان مقدار را رعایت کنید.','نمونه اولیه — نیازمند تأیید پزشک'),
      ('fall_prevention','ایمنی','پیشگیری از زمین خوردن','مسیر رفت‌وآمد خانه را خلوت نگه دارید، فرش‌های لیز را جمع کنید و شب‌ها چراغ راهرو را روشن بگذارید. کفش پاشنه‌دار یا دمپایی لق نپوشید.','نمونه اولیه — نیازمند تأیید پزشک'),
      ('sleep','خواب','خواب بهتر','ساعت خواب و بیداری را ثابت نگه دارید و چرت روز را کوتاه کنید. اگر شب‌ها بی‌خواب هستید، آن را در گزارش روزانه به من بگویید.','نمونه اولیه — نیازمند تأیید پزشک'),
      ('loneliness','ارتباط','تنهایی کمتر','هر روز یک تماس کوتاه با خانواده یا یک دوست داشته باشید. اگر دوست دارید، من می‌توانم درخواست تماس را برای مراقب شما بفرستم.','نمونه اولیه — نیازمند تأیید پزشک')]
 for tid,topic,cat,txt,appr in edu: c.execute('INSERT OR IGNORE INTO education_content(id,topic,category,body,status,approved_by,approved_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(tid,topic,cat,txt,'approved',appr,now(),now()))
 symp=[('تنگی نفس',1,1),('درد قفسه سینه',1,2),('تپش قلب',1,3),('سرگیجه',0,4),('سردرد',0,5),('تهوع',0,6),('استفراغ',0,7),('درد شکم',0,8),('تورم پاها',0,9),('بی‌حالی',0,10),('تب',0,11),('بی‌خوابی',0,12),('اضطراب',0,13),('درد مفاصل',0,14)]
 for nm,esc,so in symp: c.execute('INSERT OR IGNORE INTO symptom_catalog(name,escalate,sort_order) VALUES(?,?,?)',(nm,esc,so))
 crit_reply='این وضعیت را نمی‌توانم از راه دور تشخیص دهم و اجازه اظهار نظر بالینی ندارم. لطفاً همین حالا با مراقب خود یا اورژانس ۱۱۵ تماس بگیرید. اگر اجازه بدهید، درخواست تماس را برای مراقب اصلی شما می‌فرستم.'
 refer_reply='این پرسش نیازمند نظر پزشک یا داروساز است؛ من اجازه تشخیص یا تغییر دارو ندارم. می‌توانم همین پرسش را برای مراقب شما بفرستم تا با پزشک مطرح شود.'
 rules=[('critical','emergency',crit_reply,['درد قفسه سینه','درد سینه','سنگینی سینه','تنگی نفس','نفس نمی‌کشم','نمی‌توانم نفس بکشم','از حال رفتم','غش کردم','بیهوش شدم','تشنج','سکته','بی‌حسی صورت','کج شدن صورت','خونریزی شدید','زمین خوردم','خودکشی','می‌خواهم بمیرم',
         # گونه‌های محاوره‌ای همان دو اورژانس (قفسه سینه و تنگی نفس)؛ سالمند کتابی حرف نمی‌زند
         'درد قلب','قلبم درد','سینه درد','نفسم نمیاد','نفس نمیاد','نمیتونم نفس','نمیتوانم نفس','خفتم','خفه میشم']),
        ('ambiguous','refer_professional',refer_reply,['دوز دارو','مقدار دارو','دارو را قطع','قرص را قطع','چه بیماری دارم','چه‌ام هست','تداخل دارویی','جایگزین دارو','نسخه بنویس','تجویز کن'])]
 for lvl,act,reply,pats in rules:
  for pat in pats: c.execute('INSERT OR IGNORE INTO safety_rules(id,level,pattern,action,reply,updated_at) VALUES(?,?,?,?,?,?)',(lvl+'::'+pat,lvl,pat,act,reply,now()))
 apps=[('com.snappfood','اسنپ‌فود','خرید','🛍️',[{'type':'wait','timeout_ms':3000},{'type':'tap_text','payload':'جست‌وجو','timeout_ms':9000},{'type':'input_text','payload':'شیر کم‌چرب','timeout_ms':6000},{'type':'tap_text','payload':'افزودن به سبد','timeout_ms':12000},{'type':'tap_text','payload':'سبد خرید','timeout_ms':9000}]),
       ('cab.snapp.passenger',
         'اسنپ',
         'تاکسی',
         '🚕',
         [{'type':'wait','timeout_ms':3000},{'type':'tap_text','payload':'کجا می‌روید','timeout_ms':9000},{'type':'input_text','payload':'خیابان ولیعصر','timeout_ms':6000},{'type':'tap_text','payload':'درخواست خودرو','timeout_ms':12000}]),
       ('com.android.chrome','کروم','مرورگر','🌐',[{'type':'wait','timeout_ms':2500},{'type':'tap_text','payload':'جست‌وجو یا وارد کردن نشانی','timeout_ms':9000},{'type':'input_text','payload':'نوبت پزشک','timeout_ms':6000}])]
 for pkg,label,cat,icon,steps in apps: c.execute('INSERT OR IGNORE INTO approved_apps VALUES(?,?,?,?,?,?,?)',(pkg,label,cat,icon,json.dumps({'steps':steps},ensure_ascii=False),1,now()))
 lex=[('meds','داروهای من','meds',['دارو','قرص','داروها','داروی من','داروهایم'],'medicine pills blister pack on table',90),
      ('vitals','فشار خون و قند','vitals',['فشار','قند','فشار خون','قند خون','علائم حیاتی','وزن'],'home blood pressure monitor device',85),
      ('symptom','اعلام علامت و ناراحتی','symptom',['علامت','درد','سرگیجه','حالم بد','خوب نیستم','تهوع','تنگی نفس','ناراحت'],'elderly patient talking with nurse at home',80),
      ('caregiver_call','تماس با مراقب','caregiver_call',['مراقب','تماس','زنگ','خانواده','پسرم','دخترم','کمکم'],'elderly person talking on phone with family',88),
      ('food_order','سفارش خرید خانه','food_order',['خرید','سفارش','نان','شیر','سوپر','فروشگاه'],'grocery shopping bags with bread and milk',70),
      ('taxi','گرفتن تاکسی','taxi',['تاکسی','اسنپ','بروم','برسان','سفر','بیرون'],'taxi car waiting on city street',68),
      ('education','نکته بهداشتی','education',['نکته','آموزش','بهداشتی','یاد بده','توصیه'],'health education pamphlet for seniors',60),
      ('wallet','کیف پول و موجودی','wallet',['کیف پول','موجودی','پول','شارژ','پرداخت'],'leather wallet with money and cards',55),
      ('appointment','نوبت پزشک','appointment',['نوبت','پزشک','دکتر','ویزیت','کلینیک','بیمارستان'],'doctor appointment at clinic reception',75),
      ('screen_control','کنترل اپ‌ها','screen_control',['اپ','اپلیکیشن','تلویزیون','کنترل','گوشی'],'smartphone screen with large app icons',50),
      ('chat','گفت‌وگو و هم‌صحبتی','chat',['حرف','صحبت','گپ','تنها','تنهایی','حوصله','دلم گرفته','بشنو','خاطره'],'two elderly friends having a friendly conversation',45)]
 for lid,label,action,kws,iq,prio in lex: c.execute('INSERT OR IGNORE INTO intent_lexicon VALUES(?,?,?,?,?,?)',(lid,label,action,json.dumps(kws,ensure_ascii=False),iq,prio))
 # واژه‌نامه گویشی — بر پایه فهرست ۱۲ لهجه بنچمارک PSRB؛ این فهرست اولیه است و باید با گویشوران بومی اعتبارسنجی شود
 dia=[
  ('colloquial','دوا','دارو','محاوره عمومی'),('colloquial','دوام','دارویم','محاوره عمومی'),('colloquial','دواها','داروها','محاوره عمومی'),
  ('colloquial','مریض خونه','بیمارستان','محاوره عمومی'),('colloquial','مریضخانه','بیمارستان','محاوره عمومی'),
  ('colloquial','دکتر','پزشک','محاوره عمومی'),('colloquial','طبیب','پزشک','محاوره عمومی'),('colloquial','حکیم','پزشک','محاوره عمومی'),
  ('colloquial','خونه','خانه','محاوره عمومی'),('colloquial','چایی','چای','محاوره عمومی'),('colloquial','نهار','ناهار','محاوره عمومی'),
  ('colloquial','سرم گیج میره','سرگیجه','محاوره عمومی'),('colloquial','دور سرم میچرخه','سرگیجه','محاوره عمومی'),('colloquial','گیجی','سرگیجه','محاوره عمومی'),
  ('colloquial','نفسم میگیره','تنگی نفس','محاوره عمومی'),('colloquial','دلم هوا میخواد','تنگی نفس','محاوره عمومی'),
  ('colloquial','جون ندارم','ضعف','محاوره عمومی'),('colloquial','رمق ندارم','ضعف','محاوره عمومی'),('colloquial','بی حالم','ضعف','محاوره عمومی'),
  ('colloquial','دلم بهم میخوره','حالت تهوع','محاوره عمومی'),('colloquial','تهوع دارم','حالت تهوع','محاوره عمومی'),
  ('colloquial','فشارم','فشار خون','محاوره عمومی'),('colloquial','قندم','قند خون','محاوره عمومی'),
  ('colloquial','میخوام','می‌خواهم','محاوره عمومی'),('colloquial','نمیخوام','نمی‌خواهم','محاوره عمومی'),
  ('colloquial','میخواد','می‌خواهد','محاوره عمومی'),('colloquial','بده','بده','محاوره عمومی'),
  ('colloquial','حالم','حالم','محاوره عمومی'),('colloquial','درد','درد','محاوره عمومی'),
  ('colloquial','زنگ بزن','تماس بگیر','محاوره عمومی'),('colloquial','تلفن کن','تماس بگیر','محاوره عمومی'),
  ('mashhadi','مو','من','ضمیر — لهجه مشهدی/خراسانی'),('mashhadi','مه','مال من','لهجه مشهدی'),('mashhadi','امه','آمده','لهجه مشهدی'),
  ('mashhadi','رفه','رفته','لهجه مشهدی'),('mashhadi','نخوام','نمی‌خواهم','لهجه مشهدی'),('mashhadi','خوام','می‌خواهم','لهجه مشهدی'),
  ('dari','مو','من','ضمیر — دری/افغانستان'),('dari','شفاخانه','بیمارستان','دری'),('dari','دواخانۀ','داروخانه','دری'),
  ('shirazi','مه ره','مرا','لهجه شیرازی'),('shirazi','میرم','می‌روم','لهجه شیرازی'),('shirazi','نمیرم','نمی‌روم','لهجه شیرازی'),
  ('isfahani','سی','برای','لهجه اصفهانی'),('isfahani','میرم','می‌روم','لهجه اصفهانی'),
  ('yazdi','سی','برای','لهجه یزدی'),('yazdi','اِش','او','لهجه یزدی'),
  ('azeri','جفتن','گفتن','گ → ج در لهجه ترکی'),('azeri','هردم','کردم','ک → ه در لهجه ترکی'),
  ('azeri','یاش','سن','واژه ترکی'),('azeri','اوشاق','بچه','واژه ترکی'),('azeri','جوراب','جوراب','بدون تغییر'),
  ('kurdish','چۆنی','چطوری','کردی'),('kurdish','خۆش','خوب','کردی'),('kurdish','ناخۆش','بیمار','کردی'),
  ('lori','مه','من','ضمیر — لری'),('lori','ته','تو','ضمیر — لری'),('lori','دردمه','درد دارم','لری'),
  ('shomali','تی','تو','ضمیر — گیلکی/مازندرانی'),('shomali','مه','من','ضمیر — شمالی'),
  ('jonubi','مه','من','ضمیر — جنوبی/بندری'),('jonubi','بازار','خرید','جنوبی'),
  ('baluchi','منی','من','ضمیر — بلوچی'),('baluchi','درد','درد','بدون تغییر'),
  ('kermani','سی','برای','لهجه کرمانی'),('kermani','میرم','می‌روم','لهجه کرمانی')]
 for i,(acc,var,can,note) in enumerate(dia): c.execute('INSERT OR IGNORE INTO dialect_lexicon VALUES(?,?,?,?,?)',('dl%d'%i,acc,var,can,note))
 c.commit(); return c
