#!/usr/bin/env python3
"""Stage-5 test — لایه گویش/لهجه، پروفایل صوتی تطبیقی و صبر گفتاری.

مبنای پژوهشی:
- PSRB (arXiv:2505.21230): بدترین دقت ASR فارسی روی لهجه مشهدی (SW-WER ۵۳٫۳) و یزدی
- asr-age-gap: دقت ASR با سن افت معنادار ندارد ولی نوبت‌گیری ۵٫۴ برابر بدتر می‌شود
- CHI'26 (10.1145/3772318.3791581): کالیبراسیون کوتاه شخصی هنگام راه‌اندازی توصیه شده
"""
import io, json, os, re, sys, urllib.request, urllib.error
BASE='http://127.0.0.1:4174'
ROOT=os.path.dirname(os.path.abspath(__file__))
def req(path,method='GET',data=None):
 b=json.dumps(data,ensure_ascii=False).encode() if data is not None else None
 r=urllib.request.Request(BASE+path,method=method,data=b,headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(r,timeout=60) as x: return x.status,json.loads(x.read())
 except urllib.error.HTTPError as e: return e.code,json.loads(e.read() or b'{}')
failures=[]; total=0
def check(name,cond,detail=''):
 global total
 total+=1
 print(('✅' if cond else '❌'),name,('' if cond else '-> '+str(detail)))
 if not cond: failures.append(name)

print('--- 1) واژه‌نامه گویشی ---')
s,j=req('/api/dialects'); items=j.get('items',[])
check('GET /api/dialects 200',s==200,(s,j))
accs={i['accent'] for i in items}
for need in ['colloquial','mashhadi','shirazi','azeri','kurdish','lori','dari','shomali','jonubi','baluchi','yazdi','isfahani','kermani']:
    check('لهجه '+need+' پوشش داده شده',need in accs,sorted(accs))
check('منبع پژوهشی اعلام می‌شود','PSRB' in (j.get('source') or ''),j.get('source'))
check('عدد دقت PSRB برای مشهدی ثبت شده',any(i['accent']=='mashhadi' and i.get('psrb_sw_wer') for i in items),[i for i in items if i['accent']=='mashhadi'])

print('--- 2) نرمال‌سازی گویش → معیار ---')
import importlib.util
spec=importlib.util.spec_from_file_location('srv',os.path.join(ROOT,'server.py')); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
c=m.db()
cases=[('mashhadi','مو دوامو خوام','دارو'),('shirazi','مه ره دوا بده','دارو'),
       ('azeri','جفتن که حالم خوب نیست','که'),('standard','نفسم میگیره','تنگی نفس'),
       ('standard','جون ندارم بی حالم','ضعف'),('colloquial','مریض خونه رفتم','بیمارستان')]
for dial,txt,expect in cases:
    canon,rules=m.normalize_dialect(c,txt,dial)
    check(f'[{dial}] «{txt}» شامل «{expect}» شود',expect in canon,canon)
check('تکرار پیاپی حذف می‌شود',m.normalize_dialect(c,'جون ندارم بی حالم','standard')[0]=='ضعف',m.normalize_dialect(c,'جون ندارم بی حالم','standard')[0])
check('قواعد لهجه فقط با اعلام پروفایل اعمال می‌شود',m.normalize_dialect(c,'مو خوام','standard')[1]==[],m.normalize_dialect(c,'مو خوام','standard')[1])
check('همان جمله با پروفایل مشهدی نگاشت می‌شود',len(m.normalize_dialect(c,'مو خوام','mashhadi')[1])>0,'')
check('جمله معیار دست‌نخورده می‌ماند',m.normalize_dialect(c,'داروهای امروز من','standard')[0]=='داروهای امروز من',m.normalize_dialect(c,'داروهای امروز من','standard')[0])
check('حرف ربط خراب نمی‌شود (بدون تاشوی نویسه‌ای)','کک' not in m.normalize_dialect(c,'جفتن که حالم خوب نیست','azeri')[0],'')

print('--- 3) پروفایل صوتی و کالیبراسیون ---')
s,j=req('/api/voice-profile?id=testdialect')
check('پروفایل پیش‌فرض ساخته می‌شود',s==200 and j.get('patience_ms',0)>=1800,(s,j))
s,j=req('/api/voice-profile','POST',{'id':'testdialect','name':'بی‌بی','dialect':'mashhadi','patience_ms':2400})
check('ذخیره لهجه و صبر',j.get('dialect')=='mashhadi' and j.get('patience_ms')==2400,(s,j))
check('صبر خارج از بازه محدود می‌شود',req('/api/voice-profile','POST',{'id':'clamp','patience_ms':99999})[1].get('patience_ms')==5000,'')
s,j=req('/api/calibration','POST',{'id':'testdialect','samples':[{'phrase':'a','confidence':0.31},{'phrase':'b','confidence':0.44},{'phrase':'c','confidence':0.38}]})
check('کالیبراسیون 200',s==200 and j.get('ok'),(s,j))
check('اطمینان پایین → صبر بیشتر',j.get('patience_ms',0)>1800,j.get('patience_ms'))
check('آستانه اطمینان محافظه‌کارانه می‌شود',j.get('confidence_floor',1)<=0.50,j.get('confidence_floor'))
check('کالیبراسیون بدون نمونه = 400',req('/api/calibration','POST',{'id':'x','samples':[]})[0]==400,'')
check('کالیبراسیون بدون عدد = 400',req('/api/calibration','POST',{'id':'x','samples':[{'phrase':'a'}]})[0]==400,'')

print('--- 4) گفتار لهجه‌دار از مسیر واقعی HTTP ---')
s,j=req('/api/conversation','POST',{'text':'مو دوامو خوام','confidence':0.41,'profile':'testdialect'})
check('لهجه مشهدی → نیت دارو',j.get('intent')=='medication.list_today',(j.get('intent'),j.get('normalized')))
check('متن نگاشت‌شده برمی‌گردد','دارو' in (j.get('normalized') or ''),j.get('normalized'))
check('قواعد اعمال‌شده گزارش می‌شود',len(j.get('dialect_rules_applied') or [])>0,j.get('dialect_rules_applied'))
check('صبر پروفایل به کلاینت می‌رسد',j.get('patience_ms')==2400 or j.get('patience_ms',0)>=1800,j.get('patience_ms'))
s,j=req('/api/conversation','POST',{'text':'سلام خوبی','profile':'testdialect'})
check('احوال‌پرسی همچنان مزاحم نمی‌شود',j.get('needs_clarification') is False,j.get('needs_clarification'))

print('--- 5) یادگیری از اصلاح کاربر ---')
s,j=req('/api/disambiguate','POST',{'text':'همون چیزه همیشگی','confidence':0.22,'profile':'testdialect'})
sid=j.get('id'); opts=j.get('options',[])
check('پاپ‌آپ دو گزینه‌ای ساخته می‌شود',s==200 and len(opts)==2,(s,len(opts)))
pick=opts[0]['id']
s,j=req('/api/disambiguate/resolve','POST',{'id':sid,'chosen':pick,'profile':'testdialect'})
check('انتخاب ثبت می‌شود',s==200 and j.get('ok'),(s,j))
check('عبارت به عنوان میان‌بر شخصی یاد گرفته شد',j.get('learned') is True,j.get('learned'))
s,j=req('/api/conversation','POST',{'text':'همون چیزه همیشگی','confidence':0.99,'profile':'testdialect'})
check('دفعه بعد مستقیم شناخته می‌شود',j.get('alias_used')==pick,(j.get('alias_used'),pick))
check('بدون پاپ‌آپ اضافه پاسخ می‌دهد',j.get('needs_clarification') is False,j.get('needs_clarification'))
s,j=req('/api/aliases'); check('میان‌برها خوانده می‌شوند',s==200 and len(j.get('items',[]))>=1,(s,j))
s,j=req('/api/disambiguate/resolve','POST',{'id':sid,'chosen':'__none','profile':'testdialect'})
before=len((req('/api/aliases')[1]).get('items',[]))
check('«هیچ‌کدام» میان‌بر جعلی نمی‌سازد',all(not i['intent_id'].startswith('__') for i in (req('/api/aliases')[1]).get('items',[])),before)

print('--- 6) صبر گفتاری در رابط کاربری ---')
web=io.open(os.path.join(ROOT,'index.html'),encoding='utf-8').read()
for fn in ['onSpeechResult','loadVoiceProfile','startPatienceWatchdog','looksIncomplete','openVoiceSettings','saveVoiceSettings','runCalibration','finishCalibration']:
    check('تابع '+fn+' وجود دارد',('function '+fn) in web or ('async function '+fn) in web,'')
check('دیگر روی isFinal بلافاصله فرمان اجرا نمی‌شود','setTimeout(()=>handleVoiceCommand(text,conf),350)' not in web,'')
check('فرمان از مسیر موتور صبر می‌گذرد','onSpeechResult(text,conf' in web,'')
check('جمله ناتمام زمان بیشتری می‌گیرد','speechState.patience*1.6' in web,'')
check('پیش‌فرض صبر ۱۸۰۰ms است','patience:1800' in web,'')
check('سکوت طولانی با پیام پر می‌شود (بن‌بست ندارد)','وسط حرفتان نمی‌پرم' in web,'')
check('پروفایل صوتی هنگام بارگذاری خوانده می‌شود','loadVoiceProfile()' in web,'')
check('شناسه پروفایل به سرور فرستاده می‌شود','profile:pid' in web,'')
check('کالیبراسیون سه جمله‌ای پیاده شده','داروهای امروز من' in web and 'فشار خونم را اندازه بگیر' in web,'')
check('انتخاب لهجه در تنظیمات هست','vs-dialect' in web,'')
check('ورودی تنظیم گفتار در فهرست امکانات هست','openVoiceSettings()' in web,'')
asset=io.open(os.path.join(ROOT,'android','app','src','main','assets','index.html'),encoding='utf-8').read()
check('کپی اندروید با نسخه وب یکسان است',asset==web,'')

print(f'STAGE-5 TEST: {total} checks; failures={len(failures)}')
if failures: print('FAILED:',', '.join(failures)); sys.exit(1)
print('Stage-5 dialect & speech-patience test passed')
