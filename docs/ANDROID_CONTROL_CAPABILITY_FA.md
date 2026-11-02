# بررسی توانایی کنترل کامل گوشی و صفحات اندرویدی — سپندیار

**تاریخ:** ۱۴۰۵/۰۸/۱۱ · **کامیت مبنای بررسی:** `5071d53`
**روش:** خواندن کامل ۱۰۰۶ خط کد Kotlin (۸ فایل) + مانیفست + پیکربندی سرویس + پژوهش وب

---

## حکم نهایی

**خیر — «کنترل کامل» نداریم.** کنترل ما **قابل‌توجه ولی کران‌دار** است.

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
