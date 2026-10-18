# ماتریس تحقیق و فعال‌سازی تک‌تک قابلیت‌های همراه من

## روش تحقیق

برای هر قابلیت چهار سؤال بررسی می‌شود:

1. آیا سالمند واقعاً به آن نیاز دارد؟
2. شواهد اثربخشی چیست؟
3. ریسک خطا و حریم خصوصی چیست؟
4. معیار پذیرش فنی و انسانی چیست؟

قابلیت فقط زمانی «فعال و کاربردی» محسوب می‌شود که رابط سالمند، پنل مراقب، Backend، offline behavior، permission، audit، تست و fallback انسانی داشته باشد.

## ۱. همدم و گفت‌وگوی صوتی

### شواهد

مرورهای voice assistant برای سالمندان، مزیت‌هایی مانند استقلال، همراهی و مدیریت سلامت را نشان می‌دهند، اما privacy، speech recognition، discoverability و اعتماد را ریسک اصلی می‌دانند. [1](https://dl.acm.org/doi/fullHtml/10.1145/3563657.3596104) [2](https://arxiv.org/html/2503.23153v1)

### پیاده‌سازی لازم

- Realtime WebRTC
- fallback STT/TTS
- VAD و barge-in
- transcript قابل مشاهده
- نام و voice profile
- confidence پایین → سؤال روشن‌کننده
- «لغو»، «دوباره بگو»، «صبر کن»
- ذخیره نکردن صدای خام بدون consent

### معیار پذیرش

- سالمند با سه نوع لهجه فرمان را می‌دهد.
- سیستم در خطا پاسخ قابل اصلاح می‌دهد.
- هیچ ابزار حساس بدون policy اجرا نمی‌شود.
- کاربر می‌داند چه زمانی میکروفون فعال است.

### وضعیت فعلی

Realtime endpoint، WebRTC، fallback، prompt، tone و guardrail در MVP پیاده شده‌اند؛ provider واقعی با API key باید روی staging تست شود.

## ۲. proactive check-in

### شواهد

مطالعه MATCHA با استقرار ۲۰ هفته‌ای، check-in زمان‌بندی‌شده و contextual را برای مدیریت دارو و سلامت بررسی کرده است. Check-in مکالمه‌ای در طول روز برای سالمندان و مراقبان از alarm ساده مناسب‌تر گزارش شد. [3](https://arxiv.org/html/2510.06690v1)

### پیاده‌سازی لازم

- برنامه صبح، ظهر، عصر و شب
- quiet hours
- پاسخ صوتی
- retry با فاصله
- escalation پس از بی‌پاسخی
- جلوگیری از prompt تکراری
- تنظیم توسط مراقب با consent

### معیار پذیرش

- سالمند لازم نیست خودش درخواست check-in بدهد.
- prompt در زمان درست پخش می‌شود.
- پاسخ ثبت می‌شود.
- عدم پاسخ به مراقب منتقل می‌شود.
- alert fatigue اندازه‌گیری می‌شود.

### وضعیت فعلی

Prompt روزانه صبح، فشار خون و شب در Backend پیاده شده است؛ scheduler تولیدی و Push چندکاناله باید تکمیل شود.

## ۳. دارو و eMAR

### شواهد

Medisafe reminder، missed-dose، refill، interaction، report و Medfriend دارد. Birdie eMAR، PRN، care plan، offline و concern raising را در workflow مراقب قرار داده است. [4](https://play.google.com/store/apps/details?id=com.medisafe.android.client&hl=en_US) [5](https://www.birdie.care/product-features/carer-app)

### پیاده‌سازی لازم

- medication list
- دوز و واحد
- PRN protocol
- refill inventory
- drug dictionary
- interaction از منبع معتبر
- administration log
- missed-dose escalation
- offline queue
- گزارش پزشک

### معیار پذیرش

- هر نوبت فقط یک log روزانه دارد.
- مصرف دیروز روی امروز اثر نمی‌گذارد.
- دوز بدون پزشک قابل تغییر نیست.
- PRN بدون سقف و فاصله زمانی ثبت نمی‌شود.

### وضعیت فعلی

دارو، log روزانه، reminder، quiet hours، refill metadata و event در MVP وجود دارد؛ interaction و eMAR حرفه‌ای باید با دیتابیس دارویی معتبر و review داروساز تکمیل شود.

## ۴. علائم حیاتی

### شواهد

پایش remote زمانی مفید است که منبع، زمان، خطا و زمینه داده مشخص باشد و alertها شخصی‌سازی شوند. ICOPE بر پایش طولی و care plan شخصی تأکید دارد. [6](https://www.thelancet.com/journals/lanhl/article/PIIS2666-7568(22)00097-6/fulltext)

### پیاده‌سازی لازم

- فشار، قند، وزن، نبض، دما، SpO2
- ورود صوتی، دستی، OCR و device
- آستانه عادی و بحرانی شخصی
- trend و baseline
- alert tier
- physician share
- data source و confidence

### معیار پذیرش

- داده نامعتبر رد می‌شود.
- threshold قابل تغییر با role و consent است.
- critical alert به سالمند و مراقب می‌رسد.
- اورژانس فقط با پروتکل و رضایت فعال می‌شود.

### وضعیت فعلی

Blood pressure، glucose، weight، threshold، evaluation، critical alert و لینک پزشک پیاده شده‌اند؛ device integration و clinical validation باقی است.

## ۵. ICOPE و ظرفیت ذاتی

### شواهد

WHO ICOPE شش حوزه حرکت، vitality، بینایی، شنوایی، شناخت و روان را در پنج مرحله غربالگری، ارزیابی، care plan، referral/monitoring و مشارکت مراقب دنبال می‌کند. [7](https://www.who.int/teams/maternal-newborn-child-adolescent-health-and-ageing/ageing-and-health/integrated-care-for-older-people)

### پیاده‌سازی لازم

- screening دوره‌ای
- score و trend
- سؤال ساده صوتی
- ارجاع به ارزیابی عمیق
- care goal
- monitor plan
- alert به مراقب

### وضعیت فعلی

Assessment، score، status، alert و summary در MVP فعال است؛ دوره‌بندی ۴ تا ۶ ماهه و ارجاع متخصص باید در scheduler تولیدی اضافه شود.

## ۶. تغذیه و آشپزی

### شواهد

AI در تشخیص غذا، پیشنهاد وعده و nutrition support امیدوارکننده است، اما portion estimation، تنوع فرهنگی، privacy، bias و human oversight ریسک‌های اصلی‌اند. ElCombo از Food Knowledge Graph استفاده می‌کند. [8](https://formative.jmir.org/2024/1/e52170) [9](https://www.mdpi.com/2072-6643/17/20/3223)

### پیاده‌سازی لازم

- photo meal analysis
- pantry inventory
- recipe from available ingredients
- allergy و restriction
- diabetes/low-salt/renal rules
- texture و dysphagia flags
- nutrition confidence
- dietitian review

### وضعیت فعلی

Photo flow، pantry و recipe fallback/API آماده است؛ computer vision واقعی، food database معتبر و review متخصص تغذیه باید اضافه شود.

## ۷. کیف پول و اشتراک

### ریسک

کیف پول به ledger، idempotency، احراز هویت، سقف هزینه و payment provider نیاز دارد.

### پیاده‌سازی لازم

- ledger سرور
- top-up سالمند و مراقب
- payment intent
- voice confirmation
- refund
- سقف روزانه
- 2FA برای مراقب
- audit

### وضعیت فعلی

Wallet، transaction، idempotency و account plan در MVP وجود دارد؛ درگاه، KYC، refund و production auth باقی است.

## ۸. Safe Zone و Fall Safety

### شواهد

پژوهش‌ها نشان می‌دهند wearable، ambient و hybrid trade-off دارند و هیچ روش واحدی برای همه محیط‌ها بهترین نیست. [10](https://www.mdpi.com/1424-8220/25/21/6540)

### پیاده‌سازی لازم

- location consent
- safe zone
- geofence
- wandering alert
- wearable integration
- sensor integration
- false alert workflow
- emergency escalation

### وضعیت فعلی

Safe Zone، location و خروج از محدوده پیاده شده‌اند؛ fall detection واقعی باید با device معتبر و pilot محیطی انجام شود.

## ۹. ارتباط خانواده

### شواهد

ElliQ و ابزارهای voice-first، پیام، عکس، تماس، خاطرات و proactive social engagement را برای کاهش تنهایی و اتصال خانواده استفاده می‌کنند. [11](https://elliq.com/pages/how-it-works)

### پیاده‌سازی لازم

- contacts
- voice message
- photo share
- video call
- memories
- birthday/occasion
- consent
- delivery status

### وضعیت فعلی

Contacts و queued messages در MVP وجود دارند؛ اتصال واقعی SMS، پیام‌رسان و video provider باید اضافه شود.

## ۱۰. Care Plan و مراقب

### شواهد

Caregiver technology می‌تواند burden را در کوتاه‌مدت کاهش دهد، اما اثر به support انسانی و context وابسته است. [12](https://www.frontiersin.org/journals/digital-health/articles/10.3389/fdgth.2025.1636084/full)

### پیاده‌سازی لازم

- care goals
- tasks
- assignment
- reminder
- acknowledge
- escalation
- workload view
- caregiver training
- offline

### وضعیت فعلی

Care tasks، check-in، caregiver dashboard، alert acknowledge، summary و Safe Zone فعال‌اند.

## ۱۱. Admin و AI Studio

### پیاده‌سازی لازم

- user/role management
- provider/model config
- prompt versioning
- guardrail versioning
- audit
- cost/latency
- model fallback
- incident log
- rollout و rollback

### وضعیت فعلی

Admin Dashboard، AI config، prompt، guardrail، tone، model و realtime session آماده‌اند؛ prompt versioning، usage cost و rollout کنترل‌شده باید اضافه شوند.

## ۱۲. Adaptive UI و TV

### شواهد

Android Window Size Classes و Material Adaptive برای compact، medium، expanded، large و extra-large پیشنهاد می‌شوند؛ Layout نباید بر اساس نام دستگاه قفل شود. [13](https://developer.android.com/develop/adaptive-apps/guides/use-window-size-classes?hl=en) [14](https://m3.material.io/foundations/layout/breakpoints/overview)

### وضعیت فعلی

- موبایل
- تبلت
- landscape
- TV
- D-pad
- safe zone
- horizontal tab scroll
- resizeable activity
- TV command router

پیاده‌سازی شده‌اند.

## ترتیب نهایی فعال‌سازی

1. تکمیل production auth و role-based access
2. تکمیل eMAR و drug dictionary با داروساز
3. تکمیل Push/SMS/Voice escalation
4. اتصال realtime provider واقعی
5. اتصال Health Connect و wearable
6. اتصال nutrition knowledge base و dietitian review
7. pilot با سالمند، مراقب و پزشک
8. اندازه‌گیری KPI و اصلاح بر اساس داده واقعی

## اصل عدم ادعای کاذب

قابلیت‌هایی مانند fall detection، nutrition diagnosis، emergency calling، drug interaction و medical recommendation تا قبل از provider معتبر، validation و review متخصص نباید به‌عنوان «بالینی، قطعی یا بی‌خطا» معرفی شوند.
