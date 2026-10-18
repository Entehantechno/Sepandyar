# Android TV / Smart TV Research و پیاده‌سازی همراه من

## یافته‌های رسمی

Android TV با touch-first فرق دارد؛ ورودی اصلی remote و D-pad است و مسیر focus باید برای Up/Down/Left/Right و Select قابل پیش‌بینی باشد. عناصر custom باید درخت AccessibilityNodeInfo را درست ارائه کنند تا TalkBack و D-pad بتوانند حرکت کنند. [1](https://developer.android.com/training/tv/accessibility/custom-views)

برای TV باید از 10-foot UI استفاده کرد: متن بزرگ، فاصله کافی، density پایین، safe zone داخلی و focus کاملاً مشخص. [2](https://stuff.mit.edu/afs/sipb/project/android/docs/training/tv/optimizing-layouts-tv.html) [3](https://developer.amazon.com/docs/fire-tv/design-and-user-experience-guidelines.html)

Android TV/Fire TV کنترل‌های D-pad را از طریق KeyEvent دریافت می‌کنند و MediaSession برای کنترل پخش مناسب‌تر از کلیک کور UI است. [4](https://developer.android.com/media/media3/ui/androidtv)

AccessibilityService فقط با اقدام صریح کاربر فعال می‌شود و باید package/eventهای مجاز محدود شود؛ استفاده از آن برای خواندن یا کنترل نامحدود همه اپ‌ها ریسک حریم خصوصی و policy دارد. [5](https://developer.android.com/reference/android/accessibilityservice/AccessibilityService) [6](https://support.google.com/googleplay/android-developer/answer/10964491?hl=en)

## تصمیم‌های پیاده‌سازی

### حالت Landscape

- app روی نمایشگرهای عریض تا 1280px گسترش می‌یابد.
- کارت دستیار در مرکز، بزرگ و کم‌تراکم است.
- تب‌ها و iconها بزرگ‌تر می‌شوند.
- کنترل‌ها از لبه‌های صفحه فاصله دارند.
- متن و focus برای فاصله دور قابل مشاهده است.

### Remote Router

`TvCommandRouter.kt` فرمان‌های امن زیر را مدیریت می‌کند:

- بازکردن YouTube
- بازکردن Netflix
- بازکردن Chrome
- افزایش و کاهش صدا
- mute
- play/pause
- next/previous media

### کنترل صفحه

`ScreenControlService` و `SmartSelector` برای اپ‌های allowlist استفاده می‌شوند. سیستم برای هر app باید سناریوی مشخص داشته باشد و رمز، OTP، کارت، browser history و داده‌های غیرمرتبط را نخواند.

### ارتباط و پیام‌رسان

- در صورت وجود Intent یا Deep Link رسمی، همان مسیر اولویت دارد.
- برای پیام‌رسانی، intent share یا API رسمی استفاده می‌شود.
- Accessibility فقط برای UI قابل مشاهده و با رضایت کاربر است.
- پیام نهایی قبل از ارسال با صدای بلند خوانده و تأیید می‌شود.

## تست TV که باید روی دستگاه واقعی انجام شود

- Android TV 10 تا 14
- Google TV
- تلویزیون 32، 43، 55 و 65 اینچ
- 720p، 1080p و 4K
- remote با D-pad و voice remote
- TalkBack فعال و خاموش
- RTL و فونت فارسی بزرگ
- focus از هر عنصر به عنصر بعدی
- Back و Home
- قطع اینترنت هنگام اجرای فرمان
- app مقصد بدون Accessibility
- app مقصد با UI سفارشی Canvas/OpenGL

## ریسک‌ها

- همه تلویزیون‌ها Accessibility Service را ارائه یا allow نمی‌کنند.
- Power/Home و کلیدهای سیستمی معمولاً قابل intercept نیستند.
- package name و Intent اپ‌ها نسخه‌به‌نسخه تغییر می‌کند.
- پیام‌رسان نصب‌شده ممکن است API یا Deep Link نداشته باشد.
- کنترل کور UI نباید برای پرداخت یا پیام حساس استفاده شود.
