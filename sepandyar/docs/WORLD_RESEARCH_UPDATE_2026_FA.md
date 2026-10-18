# به‌روزرسانی پژوهش جهانی همراه من — ۲۰۲۶

## حوزه‌های جدید بررسی‌شده

### ۱. پروفایل جامع سالمند

استاندارد FHIR در Patient برای نام، تماس، telecom، آدرس، پزشک عمومی، ارتباطات و contact party ساختار مشخص دارد. این ساختار برای پروفایل همراه من مرجع بهتری از چند فیلد آزاد است. [1](https://hl7.org/fhir/R4B/patient.html)

**قابلیت‌های لازم:**

- اطلاعات هویتی
- نام ترجیحی
- آدرس خانه و آدرس تحویل
- تلفن
- زبان و لهجه
- آلرژی‌ها
- شرایط مزمن
- blood type در صورت تأیید
- پزشک عمومی و متخصص‌ها
- داروها
- مراقب اصلی و پشتیبان
- بیمارستان ترجیحی
- داروخانه
- بیمه
- نیازهای ارتباطی
- نیازهای حرکتی/شنوایی/بینایی
- اطلاعات emergency

### ۲. اطلاعات اضطراری

Medical IDهای موجود بر دسترسی سریع به نام، تاریخ تولد، آلرژی، دارو، بیماری، گروه خونی و تماس اضطراری تأکید دارند. اطلاعات ضروری باید کوتاه، به‌روز و جدا از تاریخچه کامل نگهداری شود. [2](https://www.grayingwithgrace.com/phone-emergency-features-setup/)

**قابلیت لازم:** emergency card قابل چاپ، QR موقت، نمایش محدود روی lock screen با consent و بدون اطلاعات مالی.

### ۳. کلاهبرداری و حفاظت مالی

پژوهش‌ها و گزارش‌های جدید، voice cloning، grandparent scam، سرمایه‌گذاری جعلی و phishing صوتی را برای سالمندان خطر جدی می‌دانند. [3](https://www.kxii.com/2026/07/24/ai-voice-calls-fixed-incomes-put-older-adults-risk-financial-scams-researchers-say/)

**قابلیت لازم:**

- تشخیص درخواست مالی غیرعادی
- توقف پرداخت به مخاطب جدید
- تأیید دومرحله‌ای با مراقب
- سقف روزانه
- عبارت هشدار ساده
- عدم اعتماد به صدای تماس‌گیرنده
- نمایش «این تماس ممکن است جعلی باشد»

### ۴. حمل‌ونقل و دسترسی به پزشک

پژوهش‌های دسترسی سلامت نشان می‌دهند حمل‌ونقل، ارتباط و دسترسی دیجیتال در هم تنیده‌اند و جایگزینی کامل ویزیت حضوری با telehealth برای سالمندان همیشه مناسب نیست. [4](https://www.sciencedirect.com/science/article/abs/pii/S2214140524001865)

**قابلیت لازم:**

- پیشنهاد تماس تصویری یا ویزیت حضوری
- درخواست تاکسی یا راننده مورد اعتماد
- یادآوری زمان خروج
- ذخیره آدرس پزشک
- زمان لازم برای مسیر
- اطلاع مراقب از رسیدن و برگشت

### ۵. ارتباط اجتماعی

مرورهای ICT نشان می‌دهند ارتباط دیجیتال می‌تواند connectedness را بهبود دهد، اما اثرها کوتاه‌مدت و وابسته به آموزش، خانواده و تعامل واقعی هستند؛ فناوری نباید جایگزین رابطه انسانی شود. [5](https://pmc.ncbi.nlm.nih.gov/articles/PMC8024169/) [6](https://onlinelibrary.wiley.com/doi/10.1002/cl2.1369)

**قابلیت لازم:**

- تماس‌های تکرارشونده خانواده
- یادآوری تولد و مناسبت
- خاطرات و عکس‌ها
- پیشنهاد تماس با فردی که مدتی خبری از او نیست
- گروه کوچک family circle
- اتصال به فعالیت‌های اجتماعی محلی

### ۶. ادمین و سرمایه‌گذاری

تحقیق deckهای سلامت دیجیتال نشان می‌دهد سرمایه‌گذار می‌خواهد problem، workflow، buyer، evidence، regulatory path، business model و ask را در یک روایت منسجم ببیند؛ فهرست طولانی feature کافی نیست. [7](https://www.anygen.io/showcase/healthcare-startup-pitch-deck/index.html)

**قابلیت لازم:**

- Admin evidence dashboard
- cohort و retention
- activation و task completion
- alert precision
- medication adherence
- caregiver burden
- pilot evidence
- regulatory status
- unit economics
- investor demo mode

## نتیجه نهایی پژوهش

همراه من برای تبدیل‌شدن به محصول جهانی باید از «اپ سلامت سالمند» به این پلتفرم تبدیل شود:

```text
Voice Companion
+ Proactive Care
+ Personal Health Record
+ Medication Safety
+ Emergency Medical ID
+ Financial Scam Protection
+ Caregiver Coordination
+ Safe Mobility
+ Nutrition
+ Social Connection
+ TV/Smart Home
+ Clinician Sharing
+ Admin Evidence
```

## قابلیت‌هایی که نباید بدون اعتبارسنجی ادعا شوند

- تشخیص پزشکی
- تشخیص قطعی سقوط
- پیش‌بینی افسردگی یا UTI
- توصیه دارویی
- nutrition therapy
- تماس خودکار اورژانس
- تشخیص کلاهبرداری قطعی

همه این موارد باید با confidence، توضیح، human review، consent و پایلوت معتبر همراه باشند.
