# تطبیق پیاده‌سازی با پروپوزال «دستیار صوتی هوشمند همراه سالمند»

این سند بر اساس پروپوزال ۲۷ صفحه‌ای پیوست تنظیم شده است.

## اصولی که از پروپوزال وارد محصول شد

- Voice-first: مسیر اصلی سالمند فقط گفت‌وگو است.
- رابط جداگانه سالمند و مراقب.
- STT فارسی، LLM، TTS و Function Calling.
- لایه Workflow برای کارهای چندمرحله‌ای.
- ثبت فعالیت و گزارش روزانه.
- یادآوری دارو و تماس خانواده.
- پایش علائم حیاتی و محدوده شخصی.
- ارتباط پزشک با لینک موقت گزارش.
- Privacy by Design، رضایت پویا و Audit Log.
- مدل درآمدی B2C اشتراکی و B2B برای مراکز مراقبتی.
- تفکیک قابلیت wellness از تصمیم پزشکی.

## معماری نهایی پیشنهادی مطابق پروپوزال

```text
Android Native / Web caregiver
          |
      API Gateway
          |
      Django REST API
          |
  Conversation Orchestrator
    |       |        |
 Whisper  OpenRouter  TTS
    |       |        |
 Intent / Policy / Tool Permission
          |
       Workflow Engine
          |
 PostgreSQL + Redis + Object Storage
```

n8n فقط برای workflowهای غیرحساس و قابل ممیزی استفاده می‌شود. اقدامات حساس مانند پرداخت، تغییر دارو و تماس اضطراری باید در Policy Engine داخلی انجام شوند؛ نه مستقیماً در n8n یا توسط مدل.

## قابلیت‌ها و معیار پذیرش

### 1. مکالمه

- سالمند با نام دستیار، گفت‌وگو را شروع می‌کند.
- STT متن فارسی را با confidence برمی‌گرداند.
- اگر confidence کم باشد، دستیار حدس نمی‌زند و سؤال روشن‌کننده می‌پرسد.
- هر فرمان Intent، risk level، tool و confirmation policy دارد.
- «لغو کن»، «صبر کن»، «دوباره بگو» در همه workflowها کار می‌کنند.
- پاسخ کوتاه و صوتی است و متن جایگزین دارد.

### 2. دارو

- دارو، دوز، زمان، دستور، نسخه و تصویر بسته نگهداری می‌شود.
- مصرف، رد، تعویق و خطای ثبت‌شده event دارند.
- زمان موعد از timezone کاربر محاسبه می‌شود.
- یادآوری تکراری در یک نوبت ممنوع است.
- پس از عدم پاسخ، escalation به مراقب انجام می‌شود.
- مدل حق تغییر دوز یا قطع دارو ندارد.

### 3. علائم حیاتی

- محدوده عادی و بحرانی برای هر فرد جداست.
- تغییر محدوده فقط با نقش و رضایت مجاز انجام می‌شود.
- داده شامل مقدار، واحد، منبع، دستگاه، زمان و confidence است.
- normal، out_of_range و critical جدا می‌شوند.
- critical به سالمند و مراقب هشدار می‌دهد.
- تماس اضطراری فقط با رضایت قبلی و پروتکل قابل لغو فعال می‌شود.

### 4. پروفایل و مراقبان

- سالمند مالک داده است.
- مراقب نقش و permission مشخص دارد.
- رضایت‌های health، wallet، screen_control، voice_profile و emergency_call جدا هستند.
- هر دسترسی و تغییر در Audit Log ذخیره می‌شود.
- حذف مراقب، لغو لینک و حذف داده وجود دارد.

### 5. کیف پول و اکانت

- ledger غیرقابل‌تغییر برای هر تراکنش لازم است.
- idempotency برای جلوگیری از پرداخت تکراری فعال است.
- خرید، شارژ، برگشت وجه و سقف هزینه باید در Backend باشد.
- پرداخت همیشه با خلاصه صوتی و تأیید سالمند انجام می‌شود.
- مراقب فقط با permission wallet می‌تواند شارژ کند.

### 6. لینک پزشک

- scope محدود به vitals است.
- لینک expire و revoke دارد.
- داده اضافی مثل کیف پول و شماره مراقب هرگز نمایش داده نمی‌شود.
- پزشک گزارش قابل چاپ و قابل مشاهده در وب دریافت می‌کند.

### 7. کنترل صفحه

- allowlist اپ‌ها.
- Semantic selector، contentDescription، view id، text fuzzy و OCR fallback.
- توقف در صفحه ناشناخته یا ریسک بالا.
- رمز، OTP و اطلاعات کارت هرگز توسط Accessibility خوانده نمی‌شود.
- برای پرداخت، تأیید صوتی جدا و audit event الزامی است.

## مواردی که در MVP فعلی عملیاتی شده‌اند

- رابط سالمند و پنل مراقب
- API محلی و SQLite
- پروفایل، مراقب، دارو، vital، alert، wallet و share
- آستانه‌های شخصی و ارزیابی critical
- idempotency تراکنش
- revoke لینک پزشک
- reminder endpoint
- acknowledge هشدار مراقب
- SmartSelector اندروید
- تست smoke خودکار

## مسیر تبدیل MVP فعلی به نسخه تولیدی

### هفته ۱ تا ۲: زیرساخت

- ایجاد Django REST API
- PostgreSQL و Redis
- مهاجرت داده SQLite
- JWT، refresh token، نقش و permission
- secrets و محیط‌های dev/staging/prod

### هفته ۳ تا ۴: صدا و مدل

- Whisper فارسی یا سرویس STT با confidence
- OpenRouter adapter با مدل قابل تعویض
- TTS فارسی
- Policy Engine و Tool Registry
- ذخیره session و conversation event

### هفته ۵ تا ۶: workflow

- دارو و escalation
- vital evaluation
- کیف پول ledger
- link sharing
- مراقب و consent
- n8n برای اعلان‌های غیرحساس

### هفته ۷ تا ۸: Android تولیدی

- Foreground Service
- VAD و wake-word on-device
- Accessibility allowlist
- Health Connect
- notification channel
- crash reporting و offline queue

### هفته ۹ تا ۱۰: اعتبارسنجی

- تست با حداقل ۲۰ سالمند
- تست با مراقب و پزشک
- تست لهجه و صدای محیط
- تست accessibility و TalkBack
- threat modeling و penetration test
- پایلوت ۳۰ خانواده

## گیت انتشار

نسخه تولیدی تا زمانی منتشر نمی‌شود که:

- پرداخت بدون تأیید: صفر
- تغییر دارو توسط مدل: صفر
- لینک منقضی‌شده قابل مشاهده: صفر
- ثبت vital نامعتبر: صفر
- دسترسی بدون consent: صفر
- همه workflowهای حساس audit event داشته باشند
- سالمند بتواند کارهای اصلی را بدون لمس انجام دهد
- مراقب بتواند هشدار را acknowledge کند
- crash-free session و latency با cohort واقعی اندازه‌گیری شده باشد
