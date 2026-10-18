# ماژول Android و کنترل صفحه

این پوشه یک اسکلت واقعی Android برای MVP است و دیگر صرفاً پروتوتایپ مرورگری نیست.

## ساخت و اجرا

1. پروژه `android` را با Android Studio باز کنید.
2. Gradle Sync را انجام دهید.
3. روی گوشی Android 8 یا بالاتر اجرا کنید.
4. مجوز میکروفون را تأیید کنید.
5. از Settings → Accessibility → Installed apps، سرویس «سپندیار» را فعال کنید.
6. فقط اپ‌های مورد تأیید را به فهرست سفید اضافه کنید.

## کنترل صفحه چگونه انجام می‌شود؟

- `MainActivity` رابط MVP را در WebView محلی اجرا می‌کند.
- `AppBridge` بین رابط و Android Native ارتباط برقرار می‌کند.
- `ScreenControlService` از Android Accessibility Service استفاده می‌کند.
- `ListeningService` با اعلان دائمی (Foreground Service) حالت گوش‌به‌زنگ را هنگام خروج از صفحه حفظ می‌کند.
- نام دستیار در تنظیمات ذخیره می‌شود و از طریق `SharedPreferences` در اختیار سرویس Native قرار می‌گیرد.
- فرآیند آموزش صوتی، نام را سه بار با Speech Recognition فارسی دریافت می‌کند و نمونه‌های تشخیص‌شده را به‌صورت پروفایل محلی ذخیره می‌کند.
- این پروفایل برای wake-word شخصی‌سازی‌شده آماده است؛ برای دقت واقعی فارغ از لهجه باید در نسخه انتشار، یک مدل on-device keyword spotting / speaker embedding به `ListeningService` متصل شود. SpeechRecognizer عمومی به‌تنهایی مدل گوینده را شخصی‌سازی نمی‌کند.
- Packageهای اولیه در فهرست سفید: Snapp، SnappFood و Chrome؛ نام Package واقعی هر نصب باید روی دستگاه بررسی شود.
- سرویس می‌تواند در اپ مجاز، متن قابل مشاهده را پیدا کند، روی عنصر متنی کلیک کند، متن را در فیلد وارد کند و به خانه یا عقب برگردد.
- اجرای خرید، پرداخت، OTP و اطلاعات کارت عمداً خودکار نشده است؛ بعد از نمایش مبلغ باید تأیید جداگانه سالمند گرفته شود.

## نکته عملی

Accessibility Service فقط با اجازه صریح کاربر فعال می‌شود. اندروید اجازه کنترل نامحدود و مخفیانه صفحه را نمی‌دهد. `SmartSelector` بدون نیاز به selector دستی، متن فارسی، contentDescription، hint، شناسه resource، قابل‌کلیک‌بودن و شباهت واژه‌ای را امتیازدهی می‌کند و بهترین عنصر را پیدا می‌کند. اگر صفحه هنوز کامل نشده باشد، سرویس چند بار با فاصله کوتاه تلاش می‌کند؛ بنابراین کاربر نهایی نیازی به یافتن selector ندارد. وقتی API یا Deep Link رسمی وجود دارد، استفاده از آن از کنترل UI پایدارتر و امن‌تر است.

## پشتیبانی از همه نمایشگرها

- طراحی وب از breakpointهای بر اساس فضای واقعی پنجره استفاده می‌کند، نه نام دستگاه.
- compact: گوشی، medium: تبلت/فولد، expanded: تبلت landscape، large/extra-large: دسکتاپ و نمایشگر خارجی.
- Android Window Size Classes برای تصمیم layout توصیه شده‌اند؛ همان دستگاه می‌تواند با split-screen یا fold/unfold کلاسش را عوض کند. [Android adaptive layouts](https://developer.android.com/develop/adaptive-apps/guides/use-window-size-classes?hl=en)
- نسخه Android `resizeableActivity=true` دارد.
- Web UI در portrait، landscape، tablet، desktop و TV reflow می‌شود.
- تب‌ها در عرض کم horizontal scroll دارند و در صفحه بزرگ فاصله/اندازه بیشتری می‌گیرند.
- safe-area برای notch و نمایشگرهای edge-to-edge در meta/CSS لحاظ شده است.

## Android TV و تلویزیون هوشمند

- Manifest اکنون `LEANBACK_LAUNCHER` و صفحه عریض را پشتیبانی می‌کند.
- CSS در حالت landscape و نمایشگر بزرگ به 10-foot layout تغییر می‌کند.
- تب‌ها بزرگ‌تر می‌شوند و focus/remote باید با D-pad تست شود.
- Android TV با D-pad، focus واضح و grid قابل پیش‌بینی کار می‌کند؛ کنترل‌های custom باید AccessibilityNodeInfo را درخت UI ارائه کنند. [Android TV accessibility](https://developer.android.com/training/tv/accessibility/custom-views) [D-pad navigation](https://stuff.mit.edu/afs/sipb/project/android/docs/training/tv/optimizing-navigation-tv.html)
- safe zone حدود ۹۰٪ داخلی صفحه، فونت بزرگ، فاصله زیاد و عدم قرارگیری کنترل در لبه‌ها رعایت می‌شود.
- `ScreenControlService` برای تلویزیون فقط در دستگاهی کار می‌کند که Accessibility Service را پشتیبانی و کاربر آن را صریحاً فعال کرده باشد.
- برای کنترل media از MediaSession/Media3 و برای بازکردن شبکه یا اپ از Intent/Deep Link رسمی استفاده می‌کنیم؛ کنترل Home، Power و بعضی کلیدهای ریموت توسط سیستم یا سازنده غیرقابل intercept هستند.

## گام بعدی اتصال واقعی

- اضافه‌کردن packageهای تأییدشده به allowlist
- تعریف state machine برای مراحل جست‌وجو، سبد، آدرس، مبلغ و تأیید
- افزودن واژه‌های هم‌معنی فارسی برای هر مرحله و تست SmartSelector روی نسخه‌های مختلف اپ
- ذخیره screenshot یا OTP ممنوع؛ فقط برای تشخیص شکست UI از eventهای بی‌خطر استفاده شود
- اضافه‌کردن backend و دریافت action plan امضاشده از سرور
- تست روی چند گوشی و چند نسخه اپ مقصد
