# سیستم Motion و Micro-interaction همراه من

## نتیجه پژوهش

Motion باید در خدمت فهم تغییر وضعیت باشد، نه تزئین دائمی. WCAG 2.3.3 می‌گوید motion ناشی از interaction باید قابل کاهش یا حذف باشد مگر برای عملکرد ضروری. [1](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html)

Apple پیشنهاد می‌کند برای Reduce Motion، حرکت‌های بزرگ، zoom، scale، spin و parallax حذف یا به fade و تغییر رنگ تبدیل شوند؛ اما animation ضروریِ نشان‌دهنده وضعیت نباید حذف شود و باید جایگزین static داشته باشد. [2](https://developer.apple.com/help/app-store-connect/manage-app-accessibility/reduced-motion-evaluation-criteria/) [3](https://developer.apple.com/design/human-interface-guidelines/foundations/accessibility)

Material Design برای target بزرگ ۴۸dp، feedback روشن، و جلوگیری از blinking و حرکت خودکار طولانی توصیه دارد. [4](https://m1.material.io/usability/accessibility.html)

پژوهش‌های microinteraction نشان می‌دهند animation عملکردی می‌تواند feedback و خطای کاربر را بهتر کند، اما motion زیاد، تکراری یا تزئینی cognitive load و ناراحتی ایجاد می‌کند. [5](https://www.irjmets.com/upload_newfiles/irjmets70400336048/paper_file/irjmets70400336048.pdf)

## اصول اعمال‌شده

### وضعیت شنیدن

- pulse آرام برای فعال‌بودن microphone
- waveform به‌عنوان داده واقعی، نه تزئین صرف
- متن هم‌زمان «فعال» برای کسانی که motion یا رنگ را نمی‌بینند
- توقف waveform در Reduce Motion

### وضعیت موفقیت

- pop کوچک روی check دارو
- success flash برای تغییر موفق
- پیام صوتی و متن جایگزین
- بدون confetti، bounce یا flash سریع

### وضعیت خطا

- رنگ، متن و توضیح هم‌زمان
- بدون shake شدید فرم
- پیام قابل اصلاح
- امکان retry و لغو

### انتقال صفحه

- fade کوتاه به‌جای slide طولانی
- modal بدون zoom یا parallax در Reduce Motion
- کاربر در طول transition مجبور به صبر نیست

## زمان‌بندی پیشنهادی

- feedback ساده: ۱۵۰ تا ۲۰۰ms
- transition محتوا: ۲۰۰ تا ۳۰۰ms
- modal: fade کوتاه
- alert بحرانی: تغییر رنگ پایدار، نه blinking
- waveform: فقط هنگام صحبت یا گوش‌دادن فعال

## تست اجباری

- سیستم با `prefers-reduced-motion: reduce`
- setting داخلی reduce motion
- TalkBack و VoiceOver
- صفحه کوچک و فونت بزرگ
- نور کم و کنتراست بالا
- سالمند با لرزش دست
- سالمند با حساسیت vestibular

## خروجی فعلی

در `index.html` موارد زیر اضافه/اصلاح شده‌اند:

- transitionهای کوتاه و purposeful
- press feedback برای کنترل‌ها
- check pop برای مصرف دارو
- success flash برای وضعیت موفق
- حذف animation در reduced motion
- حفظ متن و وضعیت static در کنار motion
