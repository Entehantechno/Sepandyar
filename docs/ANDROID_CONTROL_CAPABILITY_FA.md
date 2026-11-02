# بررسی توانایی کنترل کامل گوشی و صفحات اندرویدی — سپندیار

**تاریخ:** ۱۴۰۵/۰۸/۱۱ · **کامیت مبنای بررسی:** `5071d53`
**روش:** خواندن کامل ۱۰۰۶ خط کد Kotlin (۸ فایل) + مانیفست + پیکربندی سرویس + پژوهش وب

---

## حکم نهایی

> **به‌روزرسانی مرحلهٔ ۲۲:** شش شکاف پیاده‌سازیِ فهرست‌شده در بخش ۲ **رفع
> شدند** (کامیت `8e78eaa` → مرحلهٔ ۲۲). حالا ۱۹ نوع گام پشتیبانی می‌شود.
> محدودیت‌های بخش ۳ **همچنان پابرجا** هستند — آن‌ها محدودیت پلتفرم و
> سیاست‌اند، نه کمبود کد.

**کنترل «عملیِ کامل» روی اپ‌های با درخت دسترس‌پذیری سالم: بله.**
«کنترل مطلق» روی هر صفحه‌ای: **خیر** — به دلایل بخش ۳.

سپندیار می‌تواند روی اپ‌هایی که درخت دسترس‌پذیری سالم دارند، جریان‌های
خطیِ «باز کن ← بزن ← تایپ کن ← اسکرول کن» را اجرا کند. اما شش دسته
عملیات پایه را **اصلاً پیاده نکرده‌ایم** و یک دسته محدودیت هم سخت‌افزاری/
سیاستی است که با هیچ کدی حل نمی‌شود.

---

## ۱. آنچه می‌توانیم (همه در کد تأیید شد)

| توانایی | سازوکار | محل |
|---|---|---|
| پیدا کردن عنصر با متن/توضیح/hint/شناسه، با نرمال‌سازی فارسی و امتیازدهی فازی | `SmartSelector` (levenshtein، اشتراک توکن، آستانهٔ ۳۵) | `SmartSelector.kt` |
| کلیک روی عنصر | `ACTION_CLICK` ← کلیک والد ← ضربهٔ مختصاتی با `dispatchGesture` | `tapOnce` |
| تایپ در فیلد | `ACTION_SET_TEXT` روی فیلدِ فوکوس‌دارِ ورودی | `smartInput` |
| ضربه در مختصات | `dispatchGesture` | `tap` |
| بازگشت / خانه / برنامه‌های اخیر | `performGlobalAction` | `performStep` |
| اسکرول | `ACTION_SCROLL_FORWARD/BACKWARD` روی گره `isScrollable` | `scrollNode` |
| خواندن متن صفحه | `AccessibilityNodeInfo` (text, contentDescription, hintText, viewIdResourceName) | `containsText`, `walk` |
| تأیید انجام گام | `isTextVisible` + مکانیزم `expect` با deadline و تلاش مجدد ۶۵۰ms | `ScreenTaskRunner.attempt` |
| اجرای اپ از فهرست مجاز | `launchApprovedPackage` (allowlist) | `MainActivity` |
| فرمان‌های تلویزیون | کلیدهای رسانه‌ای | `TvCommandRouter` |
| دیدن کنترل‌های `importantForAccessibility="no"` | `flagIncludeNotImportantViews` | config.xml |
| درخت چندپنجره‌ای | `flagRetrieveInteractiveWindows` | config.xml |

---

## ۲. آنچه نمی‌توانیم (شمارش grep، همه صفر)

| نبوده | شمارش | پیامد عملی |
|---|---|---|
| `ACTION_IME_ENTER` | **۰** | **نمی‌توانیم فرم/جست‌وجو را ارسال کنیم** — بزرگ‌ترین شکاف |
| `takeScreenshot` (API 30) | **۰** | روی بازی canvas، فلاتر با semantics ضعیف و بعضی WebView **کاملاً نابیناییم** |
| `ACTION_LONG_CLICK` | **۰** | منوهای زمینه‌ای (long-press) دست‌نیافتنی |
| ژست پیوسته (`willContinue`) | **۰** | کشیدن، اسلایدر، جابه‌جایی با drag، الگوی قفل — هیچ‌کدام ممکن نیست |
| `StrokeDescription` | **۱** | فقط یک ضربهٔ تک‌نقطه‌ای ۸۰ms؛ هیچ swipe ای وجود ندارد |
| `NotificationListenerService` | **۰** | خواندن/کنش روی اعلان‌ها ممکن نیست |

`performStep` فقط این ۹ نوع را می‌شناسد و هر چیز دیگر `false` می‌دهد:
`launch, wait, tap_text, input_text, tap_xy, back, home, recents, scroll`

### باگ کارکردی که در همین بررسی پیدا شد

سه رسپیِ پیش‌فرض در `app/database.py` **هیچ گام ارسال (submit) ندارند**:

| اپ | رسپی | مشکل |
|---|---|---|
| کروم | `wait → tap(omnibox) → input("نوبت پزشک")` → **پایان** | **قطعاً خراب**: تایپ می‌کند و هرگز جست‌وجو نمی‌کند |
| اسنپ‌فود | `… → input("شیر کم‌چرب") → tap("افزودن به سبد")` | فقط اگر UI نتیجهٔ زنده نشان دهد کار می‌کند؛ وگرنه گام بعد تا timeout (۱۲s) تلاش و سپس شکست |
| اسنپ | `… → input("خیابان ولیعصر") → tap("درخواست خودرو")` | نیازمند انتخاب پیشنهاد از فهرست است که رسپی ندارد |

علت ریشه‌ای: `ACTION_IME_ENTER` پیاده نشده، پس حتی اگر رسپی گام `enter`
می‌خواست، `performStep` آن را `false` برمی‌گرداند.

---

## ۳. محدودیت‌های سخت (با کد حل نمی‌شوند)

**۱. کاربر باید دستی فعال کند.** هیچ API ای برای روشن کردن سرویس
دسترس‌پذیری وجود ندارد. در اندروید ۱۳+ اپ‌های sideload یک دروازهٔ اضافهٔ
«restricted settings» هم دارند
([esper.io](https://www.esper.io/blog/android-13-sideloading-restriction-harder-malware-abuse-accessibility-apis)).

**۲. اندروید ۱۷ API را قفل کرده است.** با فعال بودن Advanced Protection،
فقط اپ‌های دارای `isAccessibilityTool=true` دسترسی را نگه می‌دارند و بقیه
**به‌صورت خودکار لغو** می‌شوند
([thehackernews، ۲۰۲۶/۱۰](https://thehackernews.com/2026/10/android-17-advanced-protection-locks.html)،
[androidauthority](https://www.androidauthority.com/android-17-beta-2-advanced-protection-mode-accessibility-apps-3648860/)).
دسته‌های مجاز: screen reader، **voice control**، switch input، بریل.
اندروید ۱۷ از ۲۶ خرداد ۱۴۰۵ پایدار شده
([androidpolice](https://www.androidpolice.com/advanced-protection-mode-week-test/)).

> **وضع ما:** `isAccessibilityTool="true"` داریم و صادقانه واجد شرایطیم
> (ورودی صوتی برای سالمند با محدودیت حرکتی/شناختی). این تصمیم مرحلهٔ ۱۸
> درست بوده — بدون آن، روی اندروید ۱۷ + Advanced Protection قابلیت کنترل
> دستگاه **بی‌صدا از کار می‌افتاد**.

**۳. Advanced Protection نصب sideload را هم می‌بندد.** «you cannot install an
APK from outside verified stores». یعنی برای آن دسته کاربران، **توزیع از
Play الزامی است** و APK دستی جواب نمی‌دهد.

**۴. سیاست Play: عامل خودمختار ممنوع.**
«The Accessibility API is prohibited from being used to … **power autonomous
decision-making agents**» و «Don't use the API to **autonomously initiate,
plan, and execute actions or decisions**»
([Play Console Help](https://support.google.com/googleplay/android-developer/answer/16558241)).

> **وضع ما: منطبق است — و این را تأیید کردم، نه فرض.**
> `call_llm` در کل بک‌اند فقط در **دو** جا صدا زده می‌شود:
> `handler.py:429` (پیشنهاد غذا) و `handler.py:820` (پاسخ گفت‌وگو).
> **هیچ‌کدام گام کنترل صفحه تولید نمی‌کند.** گام‌ها فقط از رسپی‌های قطعیِ
> جدول `approved_apps` می‌آیند. `POST /api/screen-tasks` هم فقط **گزارش
> نتیجه** را ذخیره می‌کند، نه گام‌ها.

**۵. `accessibilityDataSensitive` (API 34).** اپ‌ها می‌توانند نماهای حساس را
از سرویس‌های غیرابزارِ دسترس‌پذیری پنهان کنند
([developer.android.com](https://developer.android.com/blog/posts/enhancing-android-security-stop-malware-from-snooping-on-your-app-data)).
چون ما `isAccessibilityTool=true` اعلام کرده‌ایم، آن نماها را **می‌بینیم** —
این یک **مسئولیت** است نه توانایی، و Play Protect صداقت این ادعا را
راستی‌آزمایی می‌کند.

**۶. اپ‌های با semantics ضعیف ذاتاً نابینا‌کننده‌اند.** «Apps with poor
Compose semantics, Flutter, canvas games and some WebViews produce a thin or
empty tree»
([cross-app-agent](https://github.com/ioscastaway/cross-app-agent)).
راه‌حلش `takeScreenshot` است که ما نداریم.

**۷. بیومتریک و Credential Manager.** ورودی مصنوعی را نادیده می‌گیرند.
این **محدودیت خوب** است و نباید دور زده شود.

---

## ۴. جمع‌بندی صادقانه

| پرسش | پاسخ |
|---|---|
| کنترل کامل گوشی؟ | **خیر** |
| کنترل کافی برای سناریوهای MVP (سفارش غذا، تاکسی، جست‌وجو)؟ | **تقریباً** — به‌شرط رفع شکاف `IME_ENTER` |
| از نظر سیاست Play منطبق است؟ | **بله** — قطعی/قاعده‌محور، تأییدشده |
| روی اندروید ۱۷ + Advanced Protection کار می‌کند؟ | **بله** — به‌شرط اعلام درست در Play Console + ویدئوی معرفی |
| با APK دستی (sideload) قابل توزیع است؟ | **برای کاربران Advanced Protection: خیر** |

### برای رسیدن به «کنترل کاملِ عملی» به این شش مورد نیاز است

1. `ime_enter` در `performStep` + اصلاح سه رسپی *(کوچک، بیشترین اثر)*
2. `long_click` *(کوچک)*
3. ژست swipe/drag با `StrokeDescription` چندنقطه‌ای *(متوسط)*
4. `takeScreenshot` با نگهبان نسخه (minSdk=26 ولی API نیازمند ۳۰) *(متوسط؛ راه‌حل نابینایی روی فلاتر/canvas)*
5. بقیهٔ `performGlobalAction` ها: notifications، quick_settings، power_dialog *(کوچک)*
6. `NotificationListenerService` اگر خواندن اعلان لازم است *(متوسط؛ مجوز جدید)*

**هشدار:** هیچ‌کدام از این‌ها در این محیط **کامپایل نمی‌شوند** (نه JVM، نه
gradle، نه Android SDK). پیش از انتشار `./gradlew assembleDebug` الزامی است.

---

## ۵. افزوده‌های مرحلهٔ ۲۲ — آنچه پیاده شد

پیش از این `performStep` **۹** نوع گام می‌شناخت؛ حالا **۱۹** نوع:

| گام تازه | سازوکار | چرا لازم بود |
|---|---|---|
| `ime_enter` / `submit` | `ACTION_IME_ENTER` + مسیر جایگزین هیوریستیک | **بزرگ‌ترین شکاف**: هیچ رسپی‌ای نمی‌توانست جست‌وجو را ارسال کند |
| `long_click` | `ACTION_LONG_CLICK` + ضربهٔ ۶۰۰ms | منوهای زمینه‌ای |
| `swipe` | `StrokeDescription` دونقطه‌ای (`up`/`down`/`left`/`right` یا `x1,y1,x2,y2[,ms]`) | `scrollRoot` فقط روی گره `isScrollable` کار می‌کرد؛ فهرست Compose، اسلایدر، کاروسل و drag دست‌نیافتنی بودند |
| `tap_id` | تطبیق **دقیق** `viewIdResourceName` | `SmartSelector` شناسه را فقط با وزن ۳۰ می‌دید؛ در متن‌های تکراری عنصر اشتباه برنده می‌شد |
| `notifications` / `quick_settings` / `power_dialog` | `performGlobalAction` | دسترسی به سطوح سیستمی |
| `lock_screen` | `GLOBAL_ACTION_LOCK_SCREEN` با نگهبان API 28 | |
| `screenshot` | `GLOBAL_ACTION_TAKE_SCREENSHOT` با نگهبان API 28 | تصویر صفحه برای راهنمایی مراقب |

### دو تصمیم طراحی که عمداً گرفته شد

**۱. از `takeScreenshot()` (API 30) استفاده نکردیم.** آن API کاملاً بی‌صداست
— نه اعلان، نه toast، نه هیچ نشانه‌ای. این دقیقاً همان الگویی است که
بدافزارهای جاسوس استفاده می‌کنند. روی گوشی یک سالمند، تصویر گرفتنِ بی‌صدا
با نیت خوب هم قابل توجیه نیست. `GLOBAL_ACTION_TAKE_SCREENSHOT` مسیر
استاندارد سیستم است: کاربر پیش‌نمایش را می‌بیند و تصویر در گالری می‌نشیند.
یک سنجش در `test_android_control.py` بخش ۹ جلوی بازگشت ناخواستهٔ آن را
می‌گیرد (و روی متنِ **بی‌کامنت** اجرا می‌شود، چون کامنتِ توضیحیِ خودمان
هم همان واژه را دارد).

**۲. مسیر جایگزین `ime_enter` صادقانه هیوریستیک است.** `ACTION_IME_ENTER`
از API 30 است و `minSdk` ما ۲۶ — یعنی اندروید ۸ تا ۱۰ که **دقیقاً گوشی‌های
رایجِ سالمندان** هستند. برای آن‌ها گره کلیک‌پذیری با برچسب «ارسال/جست‌وجو/
submit/…» پیدا و لمس می‌شود. این روی هر صفحه‌کلیدی جواب نمی‌دهد و در
کامنت هم به‌عنوان هیوریستیک علامت‌گذاری شده؛ رسپی‌ها باید در اولویت از
`tap_text` با برچسب دقیق همان دکمه استفاده کنند.

### رسپی‌های اصلاح‌شده

هر سه رسپی پیش‌فرض گام `ime_enter` گرفتند. پیش از این کروم متن را تایپ
می‌کرد و **هرگز جست‌وجو نمی‌کرد**.

یک سنجش رگرسیون هم اضافه شد که اجازه نمی‌دهد هیچ رسپی‌ای `input_text` را
بی‌واسطه به `tap_text` برساند.

### نتایج آزمون

`۱۰۱۳ → ۱۰۲۸ بررسی · ۰ شکست`. تهی‌نبودن بخش ۹ اثبات شد: با حذف
`ime_enter`/`long_click`/`swipe` دقیقاً **۴ ❌** — و یک سنجش موجودِ
بین‌لایه‌ای هم مستقل آن را گرفت.

### آنچه همچنان باقی است

- **`NotificationListenerService`** برای خواندن اعلان‌ها — نیازمند مجوز
  جدید و یک سرویس جدا؛ عمداً این مرحله اضافه نشد.
- **بینایی ماشین روی پیکسل‌ها.** ما درخت گره‌ها را می‌خوانیم، نه پیکسل.
  برای اپ‌های فلاتر/canvas با semantics ضعیف هنوز نابیناییم. راه‌حلش
  `takeScreenshot()` است که به دلیل حریم سالمند استفاده نکردیم؛ اگر لازم
  شد باید با رضایت صریح و نمایشگر قابل‌دیدن پیاده شود.
- **هیچ‌کدام از این کدها کامپایل نشده‌اند.** در این محیط نه JVM هست، نه
  gradle، نه Android SDK. دو گارد جایگزین داریم (اسکنر نمادهای بی‌import و
  توازن کروشه) ولی **`./gradlew assembleDebug` پیش از انتشار الزامی است.**

---

## ۶. مرحلهٔ ۲۳ — پوشش کامل

`performStep` از ۱۹ به **۴۳** نوع گام رسید.

### کنش‌های گره (کامل)
`focus` · `a11y_focus` · `next_node` · `prev_node` · `select_text` ·
`select_all` · `copy` · `cut` · `paste` · `clear_text` · `append_text` ·
`expand` · `collapse` · `set_progress` · `double_tap`

### ژست‌ها
`tap` · `long_click` · `double_tap` · `swipe` (جهت‌دار/مختصاتی) ·
`drag` (کشیدن آرام) · `pinch` (**دو‌انگشتی** — دو `StrokeDescription`)

### کنش‌های سراسری (کامل)
`back` · `home` · `recents` · `notifications` · `quick_settings` ·
`power_dialog` · `lock_screen`(۲۸+) · `screenshot`(۲۸+) ·
`dismiss_notifications` · `split_screen`(۲۴+) · `headset_hook`(۲۶+) ·
`a11y_all_apps`/`a11y_home`/`a11y_back`/`a11y_recents`(۳۱+)

### خواندن صفحه — مهم‌ترین قابلیت برای سالمند
`readScreenText()` متن صفحه را به ترتیب خواندن بیرون می‌کشد تا با صدا خوانده
شود. سه نکتهٔ کیفی عمداً رعایت شده:
- فقط `isVisibleToUser` — وگرنه متن پنهان هم خوانده می‌شد
- `text` بر `contentDescription` اولویت دارد، ولی اگر خالی بود desc جای آن
  را می‌گیرد (بسیاری از دکمه‌های تصویری فقط desc دارند)
- **تکرارهای پیاپی حذف می‌شوند** — درخت اندروید پر از والد/فرزندی است که
  همان متن را دوبار حمل می‌کنند و بدون این، هر جمله دوبار خوانده می‌شد
- طول خروجی کران دارد (`SCREEN_TEXT_MAX = 4000`) تا صفحهٔ شلوغ صف گفتار را
  منفجر نکند

### سرویس اعلان‌ها
`NotificationService.kt` تازه. محتوای پیامک و پیام خصوصی را می‌تواند ببیند،
پس **سه لایه** دارد:
1. کاربر باید در تنظیمات اندروید دسترسی Notification بدهد
2. کلید `readNotifications` باید صریحاً روشن شود — **پیش‌فرض خاموش**
3. **هر چهار متد عمومی** کلید را **در زمان فراخوانی** می‌سنجند، نه فقط
   `onNotificationPosted`. یعنی با خاموش کردن کلید، خواندن فوراً متوقف
   می‌شود حتی اگر دسترسی سیستمی باقی باشد.

هیچ اعلانی به سرور فرستاده نمی‌شود. همهٔ متدها در صورت خطا **خالی/`false`**
برمی‌گردانند نه استثنا، چون از نخ پل جاوااسکریپت صدا زده می‌شوند و یک
استثنای نگرفته WebView را در وضعیت نامشخص رها می‌کند.

### آنچه عمداً انجام نشد
- **`takeScreenshot()` بی‌صدا** — به دلیل حریم سالمند (بخش ۵)
- **بینایی روی پیکسل‌ها** — ما درخت گره‌ها را می‌خوانیم. برای فلاتر/canvas با
  semantics ضعیف هنوز نابیناییم.
- **عبور از بیومتریک/Credential Manager** — غیرممکن و **نباید** ممکن باشد.

### آزمون
`۱۰۲۸ → ۱۰۵۸ بررسی · ۰ شکست`. `test_android_control.py` از ۸۳ به ۱۱۳
رسید (بخش۱۰ با ۱۹ سنجش). تهی‌نبودن اثبات شد: حذف `NotificationService` +
سه کنش گره + `readScreenText` → **دقیقاً ۶ ❌**.

دو گارد جایگزین کامپایلر: اسکنر نمادهای بی‌import روی هر ۹ فایل → **۰
نماد**؛ توازن کروشه/پرانتز → همه OK. **`./gradlew assembleDebug` پیش از
انتشار همچنان الزامی است.**
