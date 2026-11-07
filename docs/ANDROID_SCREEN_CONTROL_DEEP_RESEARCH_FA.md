# کنترل صفحهٔ اندروید — تحقیق گسترده و پیاده‌سازی

> پاسخ به این درخواست: «مجدداً برای کنترل گوشی اندروید با صفحه نمایش آن،
> تحقیقات گسترده در منابع معتبر برنامه‌نویسی، گیت‌هاب و کل اینترنت انجام بده؛
> اپ ما لازم است که **حتماً** صفحه را کنترل کند.»
>
> تفاوت این دور با دور پیش: سؤال از «آیا کنترل صفحه درست است؟» به «چطور
> مطمئن‌ترین کنترل صفحه را بسازیم؟» تغییر کرد. پس معیار، **قابلیت اجرا** است
> نه مقایسه.

---

## ۱) یافتهٔ حقوقی که همه‌چیز را محدود می‌کند

از **Play Console Help** (منبع رسمی):

> *«Any use of the Accessibility API that enables an app to autonomously
> initiate, plan, and execute actions or decisions is strictly prohibited.
> This does not prohibit deterministic, rule-based automation, where behavior
> follows a static, human-defined script.»*

و بند استثنا:

> *«Verified accessibility tools, identified by the `isAccessibilityTool="true"`
> flag, are exempt from this prohibition and may use the Accessibility API for
> autonomous functionality, provided this functionality is for the app's core
> purpose of assisting people with disabilities.»*

### آیا ما می‌توانیم `isAccessibilityTool="true"` بگذاریم؟ **خیر.**

وسوسه‌انگیز است — چون سپندیار برای سالمندان است. ولی همان منابع صریح‌اند:

> *«Antivirus software, automation tools, **assistants**, monitoring apps,
> cleaners, password managers, and launchers do not fall under this category.»*

و:

> *«A general voice assistant that happens to help some users with motor
> impairments would not qualify.»*

سپندیار یک دستیار صوتی است. گذاشتن این پرچم **سوءاستفاده از پرچم** است و خودِ
سیاست می‌گوید *«Don't misuse the isAccessibilityTool flag.»*

**پیامد طراحی:** ما در دستهٔ «automation» می‌مانیم، یعنی فقط
**deterministic, rule-based automation** مجاز است — «اگر X دیدی، Y را بزن» با
اسکریپتِ از پیش نوشتهٔ انسان. این دقیقاً همان چیزی است که رسپی‌های ما هستند.
پس معماری موجود درست است و عاملِ LLMِ خودمختار **نباید** ساخته شود.

### Android 17 / Advanced Protection

از Android 17 (پایدار از ۱۶ ژوئن ۲۰۲۶)، وقتی **Advanced Protection روشن** باشد،
دسترسی AccessibilityService فقط به ابزارهای تأییدشده داده می‌شود و دسترسی
بقیه **لغو** می‌شود. سه شرط لازم است: اندروید ۱۷ + روشن بودن Advanced
Protection + تأییدشده نبودنِ اپ.

این یک حالت opt-in است و آمار پذیرشش منتشر نشده. برای کاربر سالمندِ ما
عملاً خاموش است، ولی باید بدانیم که روی آن دستگاه‌ها کنترل صفحه کار نخواهد کرد
— و پیامِ «دسترسی را روشن کنید» آن‌جا بی‌فایده است.

---

## ۲) یافتهٔ فنیِ منفی: OCR روی‌دستگاهی برای فارسی وجود ندارد

ML Kit Text Recognition v2 کاملاً روی‌دستگاهی و آفلاین است — ولی
**فقط** این خط‌ها را پشتیبانی می‌کند: Latin، چینی، دواناگری، ژاپنی، کره‌ای.

> *«there are currently 4 text recognition models available … Arabic is
> currently not available»*

خط فارسی/عربی در فهرست نیست. (ML Kit Language Identification فارسی را
**می‌شناسد**، ولی آن تشخیصِ زبان است نه خواندنِ تصویر — این دو را اشتباه
نگیرید.)

**پیامد:** مسیر «اسکرین‌شات → OCR روی دستگاه → متن» برای ما بسته است. تنها
راه، فرستادن تصویر به یک مدل بینایی است — همان کاری که
`/api/screen/vision` می‌کند. پس کران‌های حریمِ موجود (رضایت + سقف اندازه +
محدودیت نرخ) بارِ اصلی را حمل می‌کنند و قابل حذف نیستند.

---

## ۳) مکان‌یابی بصری یک حوزهٔ بالغ است

مسئلهٔ «عبارت → مختصات پیکسل» نام دارد: **GUI visual grounding**.

| کار | نکته |
|---|---|
| **UGround** (ICLR'25 Oral) | ۱۰ میلیون عنصر از ۱٫۳ میلیون اسکرین‌شات؛ چارچوب SeeAct-V که **کاملاً بصری** است و عملیات سطح پیکسل می‌زند |
| **OS-Atlas** | بزرگ‌ترین پیکرهٔ بازِ مکان‌یابی، ۱۳ میلیون عنصر، چندسکویی |
| **ShowUI** | خروجی به شکل `{'action':…, 'position':[x,y]}` با مختصات ۰ تا ۱ |
| **GUI-Actor** | مکان‌یابی بدون مختصات، با attention head |
| **AgentCPM-GUI** | ۸B، روی‌دستگاهی؛ عمل `POINT` با مختصات نرمال‌شده در `[0,1000]` |

**نکتهٔ مشترک همه:** مختصات **نرمال‌شده** رد و بدل می‌شود، نه پیکسل مطلق.

و الگوی اجماعی، از یک منبع مهندسی:

> *«The reliable pattern is hybrid. Use the accessibility tree when it exists,
> and fall back to Set-of-Mark on canvas apps, games, or remote desktops where
> the tree is empty.»*
>
> *«Before sending a screenshot to a model, check whether an accessibility tree
> or DOM can give you element coordinates for free.»*

یعنی: **اول درخت، بعد بینایی.** دقیقاً همان ترتیبی که پیاده کردیم.

---

## ۴) درخت چرا خالی می‌شود — و این یک باگِ بالادستی است

- خودِ Flutter باگ‌های ثبت‌شده دارد که کل درخت را تا ری‌استارت پاک می‌کند
  (`flutter/flutter#194541`، `#194596`): *«the whole accessibility tree is gone
  until the app is restarted»*
- یک توسعه‌دهندهٔ عاملِ اندرویدی: *«webviews and flutter apps break everything.
  the accessibility tree just comes back empty.»*
- در اپ‌های فلاتر متن اغلب در `content-desc` است نه `text` — ما این را از
  قبل رعایت کرده‌ایم (`readScreenText` اول `text`، بعد `contentDescription`)

و دو دامِ زمانی که یک منبع امنیتی مستند کرده:

> *«Tree population delay: … On some devices this takes 200-500ms per dialog.»*
>
> *«Settings transition animations: … The tree nodes exist but their bounds
> aren't final until the animation completes. **Tapping during the animation
> hits the wrong coordinates.**»*

---

## ۵) بهترین الگوی موجود: اجارهٔ ضربهٔ بینایی

نزدیک‌ترین prior art به مسئلهٔ ما `crew-helper#114` است
(*«Add bounded visual tap fallback for node-poor UIs»*). قیدهایش:

- Accessibility-first → vision fallback
- فقط وقتی **package + fingerprint بین دو گرفتنِ تصویر ثابت بماند**، یک
  `VisualTapLease` یک‌بارمصرف صادر می‌شود
- مختصات بصری **فقط پس از** هدف‌گیری معنایی/عنصری
- *«SEND, payment, purchase, deletion, account, credential and other
  high-risk/commit targets **can never** use visual coordinates»*
- *«PhoneRuntimeExecutor **refuses** unvalidated visual coordinates»*
- اثرِ ضربه همچنان راستی‌آزمایی می‌شود
- مختصات بصری **هرگز** در رسپی ذخیره/بازیابی نمی‌شود

و از یک عاملِ بازمتن دیگر، الگوی بازیابی از گیرکردن:

> *«if the screen doesn't change for 3 steps, it tries to recover on its own.
> goes back, tries home, re-launches the app.»*

---

## ۶) چه پیاده شد

### ۶٫۱ حلقه بسته شد: «دیدن → عمل کردن»

پیش از این دور، fallback بینایی (مرحلهٔ ۲۸) فقط **متن** می‌داد. یعنی
می‌توانستیم بگوییم روی صفحه چیست، ولی در همان اپ‌هایی که بیشترین نیاز را
دارند نمی‌توانستیم هیچ دکمه‌ای را بزنیم. **کنترل صفحه ناقص بود.**

حالا:

| لایه | فایل | کار |
|---|---|---|
| سرور | `app/memory.py` | `call_llm_vision_ground` + `parse_ground` — عبارت → مختصات نرمال‌شده |
| سرور | `app/handler.py` | `POST /api/screen/vision/tap` + `vision_tap_denied` |
| دستگاه | `ScreenControlService.kt` | `locateViaVision`، `screenFingerprint`، `visualTap` |
| دستگاه | `ScreenTaskRunner.kt` | `tryVisualTap` با اجارهٔ یک‌بارمصرف |

ترتیب اجرا در `tryVisualTap`:

```
اثرانگشت صفحه (پیش)  →  مختصات از سرور  →  اثرانگشت صفحه (پس)
      ↓                                          ↓
   ضربه «فقط» اگر دو اثرانگشت یکسان باشند  →  گام دوباره سنجیده می‌شود
```

### ۶٫۲ چهار قید ایمنی

**۱. کنش تعهدآور هرگز با مختصات مدل زده نمی‌شود.** یک فهرست ۴۵ عضوی
(فارسی و انگلیسی) در **دو** لایه: `COMMIT_LABELS` سمت دستگاه و
`VISION_TAP_DENY` سمت سرور. چرا دو لایه؟ چون ضربهٔ بینایی
برگشت‌ناپذیر است و دفاعِ فقط-کلاینت با یک درخواست دست‌ساز دور زده می‌شود.
§۱۷ **یکسان بودن** این دو فهرست را می‌سنجد — اگر جدا بیفتند، رانش بی‌صداست
و build سبز می‌ماند.

**۲. مختصات نرمال‌شده (۰ تا ۱)، نه پیکسل.** تصویر سمت ما به عرض ۷۲۰ کوچک
می‌شود ولی صفحهٔ واقعی ۱۰۸۰ یا ۱۴۴۰ است. `visualTap` با `displayMetrics`
تبدیل می‌کند. اگر پیکسلِ تصویر مستقیم استفاده می‌شد، روی هر دستگاهی با وضوح
متفاوت به نقطهٔ غلط می‌زد.

**۳. اجارهٔ یک‌بارمصرف.** مختصات مربوط به همان لحظهٔ گرفتن تصویر است. اگر تا
لحظهٔ ضربه صفحه عوض شده باشد — اعلان آمده، انیمیشن تمام شده — به نقطهٔ
غلط می‌خورد. این همان باگی است که در منابع به «tapping during the animation
hits the wrong coordinates» معروف است.

**۴. راستی‌آزمایی اثر.** پس از ضربه، گام **دوباره** با همان `attempt`
سنجیده می‌شود؛ موفقیت فرض نمی‌شود. و `tries + 1` از حلقهٔ بی‌پایان
جلوگیری می‌کند.

به‌علاوه: کران `MAX_VISION_READS = 2` در هر کار، رضایت `screen_vision`،
و دروازهٔ `confirm` که دست‌نخورده ماند.

---

## ۷) چه چیزی عمداً ساخته نشد

| مورد | چرا نه |
|---|---|
| `isAccessibilityTool="true"` | سیاست صریحاً «assistants» را رد کرده؛ سوءاستفاده از پرچم است |
| عامل LLM خودمختار روی درخت | فقط «deterministic, rule-based automation» مجاز است |
| OCR روی‌دستگاهی | ML Kit خط فارسی/عربی ندارد |
| MediaProjection | دیالوگ مجوز جدا می‌خواهد؛ `takeScreenshot` بی‌صدا و بدون دیالوگ است |
| Shizuku / روت / ADB | sideloading یا کامپیوتر می‌خواهد |
| ذخیرهٔ مختصات بصری در رسپی | مختصات به همان صفحه در همان لحظه بند است؛ رسپیِ قابلِ بازیابی باید نمادین بماند |
| App cards | دانشِ خواناییِ درختِ هر اپ را نداریم و ساختنش دادهٔ ساختگی بود |
| بازیابی از گیرکردن | **کار بعدی، نه ردشده.** الگو: اگر صفحه ۳ گام پیاپی عوض نشد، `back` → `home` → اجرای دوبارهٔ اپ. منبعش یک عامل بازمتن است که می‌گوید *«if the screen doesn't change for 3 steps, it tries to recover on its own.»* پیاده نشد چون تشخیصِ «عوض نشدن» به اثرانگشتِ پایدارِ بین‌گامی نیاز دارد و در این دور اثرانگشت فقط درون یک تلاش استفاده می‌شود؛ افزودنش بدون سنجشِ زنده روی دستگاه، حدس بود |

---

## ۸) جمع‌بندی

«بهترین روشِ کنترل صفحه» یک فناوری نیست، یک **ترتیبِ سخت‌گیرانه** است:

۱. قابلیتِ اعلام‌شده (AppFunctions / App Actions) — هیچ کنترلی لازم نیست
۲. درخت دسترس‌پذیری + انتخابگر هوشمند — مسیر اصلی
۳. درخت خالی است؟ → بینایی برای **خواندن**
۴. باز هم نشد؟ → بینایی برای **مکان‌یابی** + ضربهٔ دارای اجاره
۵. کنش تعهدآور؟ → **هرگز** با بینایی؛ فقط درخت + دروازهٔ تأیید سالمند

و در همهٔ این‌ها یک قاعده ثابت است: **هرگز روی صفحه‌ای که ندیده‌ایم حدس
نزن، و هر حدسی را راستی‌آزمایی کن.**
