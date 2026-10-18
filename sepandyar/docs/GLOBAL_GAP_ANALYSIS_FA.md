# تحلیل شکاف محصول همراه من در برابر رقبا و شواهد

## رقبایی که مزیت مهم دارند

### Birdie

مزیت‌های Birdie نسبت به نسخه فعلی همراه من:

- eMAR حرفه‌ای
- PRN protocol
- visit check-in/out
- GPS/QR verification
- offline-first carer app
- care plan و observation
- body map
- roster و scheduling
- finance و invoicing
- training record
- secure messaging
- alert inbox سازمانی

منبع: [Birdie Carer App](https://www.birdie.care/product-features/carer-app)، [Birdie Platform](https://www.applytosupply.digitalmarketplace.service.gov.uk/g-cloud/services/126012328431224)

### CarePredict

مزیت‌ها:

- baseline فعالیت و ADL
- تشخیص تغییر الگو قبل از بحران
- fall detection تخصصی
- wander management
- indoor room-level location
- two-way voice روی wearable
- family activity insights
- ترکیب wearable و sensor

منبع: [CarePredict](https://www.carepredict.com/at-home-3/)

### ElliQ

مزیت‌ها:

- proactive companionship
- شروع گفت‌وگو بدون درخواست سالمند
- پیگیری خواب و حال
- goals و wellness activities
- پیام، عکس و video call خانواده
- memories و مناسبت‌ها
- check-in قابل شخصی‌سازی
- تجربه بسیار polished برای سالمند

منبع: [ElliQ How it Works](https://elliq.com/pages/how-it-works)، [NYSOFA](https://aging.ny.gov/news/nysofa-brings-elliq-proactive-care-companion-technology-older-adults-reducing-social-isolation)

### Medisafe

مزیت‌ها:

- drug interaction checker
- refill reminder
- appointment manager
- complex dose schedule
- PRN medication
- health measurements متعدد
- report پزشک
- Medfriend

منبع: [Medisafe Google Play](https://play.google.com/store/apps/details?id=com.medisafe.android.client&hl=en_US)

### Food/Nutrition products

محصولات nutrition مدرن ویژگی‌هایی مثل barcode، pantry، meal plan، recipe، food image، food database و health restrictions دارند. ElCombo از Food Knowledge Graph با dish، ingredients، nutrients و disease constraints استفاده کرده است. [ElCombo](https://formative.jmir.org/2024/1/e52170)

## شکاف‌های اصلی همراه من

### P0

1. medication dictionary و source معتبر
2. drug interaction و food interaction با disclaimer
3. refill inventory و پایان دارو
4. appointment و calendar
5. PRN medication protocol
6. eMAR حرفه‌ای برای مراقب
7. offline-first واقعی با sync queue
8. پیام و تماس خانواده
9. memory book و مناسبت‌ها
10. goal و wellness activities
11. alert inbox با priority، SLA و escalation
12. onboarding/training مراقب
13. گزارش structured پزشک
14. قابلیت تنظیم proactive schedule توسط مراقب

### P1

1. indoor location و sensor integration
2. wearable fall detection
3. baseline رفتار و ADL
4. تحلیل روند خواب/غذا/حمام/تحرک
5. care agency roster و visit check-in
6. body map و گزارش زخم
7. telehealth و video call
8. nutrition database فرهنگی فارسی
9. rewards و habit loops غیرکودکانه
10. multilingual Persian dialect support

### P2

1. smart home
2. radar/thermal privacy-first sensing
3. clinician portal و referral
4. enterprise billing
5. federated learning
6. clinical validation
7. reimbursement و partnership

## معیار پیاده‌سازی هر قابلیت

هر feature بدون این موارد کامل محسوب نمی‌شود:

- workflow سالمند
- workflow مراقب
- API
- مدل داده
- offline behavior
- error handling
- consent
- audit event
- test
- accessibility
- metric
- fallback انسانی

## KPIهای رقابتی

- medication adherence window
- missed-dose response time
- alert precision و false alert rate
- caregiver acknowledge time
- % task completion بدون کمک
- proactive prompt response rate
- 30/90-day retention
- caregiver burden pre/post
- voice WER به تفکیک لهجه
- food recognition confidence
- share report open/revoke rate
- offline sync success

## تصمیم

همراه من نباید صرفاً همه قابلیت‌ها را کنار هم بچیند. مزیت رقابتی باید این باشد:

```text
Voice-first فارسی
+ proactive care
+ ICOPE
+ caregiver action center
+ privacy-first safety
+ offline reliability
+ human escalation
+ culturally appropriate nutrition
```

این ترکیب، شکاف میان ElliQ، Birdie، CarePredict، Medisafe و محصولات nutrition را هدف می‌گیرد، بدون ادعای جایگزینی پزشک یا مراقب.
