# برنامه تست مبتنی بر شواهد همراه من

## روش

این برنامه بر اساس چهار گروه مرجع ساخته شده است:

1. طراحی سالمندان و دسترس‌پذیری
2. مکالمه صوتی و proactive care
3. دارو، علائم حیاتی و مراقبت یکپارچه
4. امنیت، حریم خصوصی و کنترل ابزارهای AI

تست‌ها دو لایه دارند:

- **Automated:** API، دیتابیس، validation، latency، idempotency و مسیرهای workflow
- **Human/device:** سالمند واقعی، مراقب، Android، Android TV، TalkBack، WebRTC، دوربین و دستگاه سلامت

## رفرنس‌های مبنا

- طراحی اپ سالمندان: مرور نظام‌مند ۱۳۲ مطالعه، سادگی، متن و touch target بزرگ، voice و error tolerance. [1](https://pubmed.ncbi.nlm.nih.gov/40804492/)
- Voice-first aging in place و اهمیت display مکمل، privacy و تفاوت افراد. [2](https://dl.acm.org/doi/fullHtml/10.1145/3563657.3596104)
- Voice assistant سلامت و شخصی‌سازی، context، autonomy و reminder. [3](https://dl.acm.org/doi/10.1145/3706598.3713839)
- ICOPE، شش حوزه ظرفیت ذاتی و care pathway. [4](https://www.who.int/teams/maternal-newborn-child-adolescent-health-and-ageing/ageing-and-health/integrated-care-for-older-people)
- context-aware medication reminder و پنجره مصرف. [5](https://pmc.ncbi.nlm.nih.gov/articles/PMC2998278/)
- دارو و alert fatigue، reminder زمینه‌محور، social support و dictionary. [6](https://www.mcpdigitalhealth.org/article/S2949-7612(23)00091-3/fulltext)
- Fall detection و trade-off wearable/ambient/hybrid. [7](https://www.mdpi.com/1424-8220/25/21/6540)
- AI nutrition، تصویر غذا، privacy، bias و human oversight. [8](https://www.mdpi.com/2072-6643/17/20/3223)
- FHIR Patient، contact، address، telecom و general practitioner. [9](https://hl7.org/fhir/R4B/patient.html)
- WebRTC Realtime، ephemeral client secret، VAD و interruption. [10](https://developers.openai.com/api/docs/guides/realtime)
- OWASP LLM، prompt injection، sensitive disclosure، excessive agency و output handling. [11](https://www.wiz.io/academy/ai-security/owasp-llm-top-10)
- Android TV، D-pad، focus، AccessibilityNodeInfo و 10-foot UI. [12](https://developer.android.com/training/tv/accessibility/custom-views)
- Android window size classes و adaptive layout برای phone/tablet/fold/desktop/TV. [13](https://developer.android.com/develop/adaptive-apps/guides/use-window-size-classes?hl=en)
- WCAG animation/reduced motion. [14](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html)

## تست‌های Automated

### API و داده

- health endpoint
- profile CRUD
- doctor/contact/caregiver CRUD
- medication create و daily log
- PRN و refill
- appointment create
- check-in
- ICOPE score و invalid score
- vital normal/out_of_range/critical
- threshold update
- alert create/ack
- safe zone/location
- pantry/recipe fallback
- emergency card
- consent scope
- share/create/revoke/expiry
- wallet topup/payment/idempotency
- reminder quiet hours/dedup
- proactive prompt/respond
- admin overview/activity/AI config
- AI no-key safe fallback
- invalid payload و error code

### Safety

- پرداخت بدون تأیید نباید رخ دهد.
- تغییر دارو توسط LLM ممنوع.
- share بعد از revoke باید 404 شود.
- score خارج از ۰ تا ۱۰ باید 400 شود.
- vital ناقص باید 400 شود.
- wallet amount منفی/بیش از سقف باید رد شود.
- API key در frontend نباید وجود داشته باشد.
- contact جدید قبل از ارسال پیام نیازمند تأیید است.
- critical vital باید alert و request_emergency_call flag بسازد.
- quiet hours نباید reminder interruptive تولید کند.

### Performance

- p50، p95 و p99 endpointهای سبک
- همزمانی حداقل ۲۰ درخواست health
- ۲۰ درخواست summary
- زمان پاسخ recipe fallback
- محدودیت اندازه تصویر و payload
- عدم رشد بی‌نهایت event log در endpoint عمومی

## تست‌های Human/Device

### سالمند

- انجام check-in فقط با پاسخ صوتی
- تشخیص پاسخ کوتاه و مکث‌دار
- اصلاح «نه، منظورم...»
- شنیدن و تکرار پاسخ
- خرید با تأیید صوتی
- لغو خرید
- ثبت دارو با جمله طبیعی
- گرفتن vital با اعداد فارسی و عربی
- درخواست recipe از عکس
- افزودن پزشک و انتخاب «پزشک همیشگی»
- ارسال پیام صوتی
- فهم وضعیت privacy

### Accessibility

- TalkBack/VoiceOver
- فونت ۲۰۰٪
- کنتراست بالا
- Reduce Motion
- screen reader reading order
- focus-visible
- بدون swipe اجباری
- کنترل تمام مسیرها با voice
- دکمه‌های حداقل ۴۴–۴۸dp/pt

### TV

- D-pad up/down/left/right/select/back
- focus قابل مشاهده
- 720p/1080p/4K
- تلویزیون ۳۲ تا ۶۵ اینچ
- فاصله ۳ متر
- landscape و safe zone
- YouTube/Netflix/Chrome در allowlist
- media play/pause/next/previous/volume
- AccessibilityNodeInfo در app مقصد

### صوت و realtime

- ephemeral token بدون افشای API key
- WebRTC offer/answer
- VAD start/stop
- barge-in و توقف صدای مدل
- قطع اینترنت و reconnect
- microphone permission denied
- echo cancellation
- noise و تلویزیون در پس‌زمینه
- fallback SpeechRecognition

## معیار Release Candidate

- 100% automated safety tests
- صفر crash در smoke flowها
- p95 API زیر ۵۰۰ms برای endpointهای ساده
- task completion سالمند حداقل ۸۵٪ در core flows
- ۰ پرداخت بدون تأیید
- ۰ تغییر دارو توسط مدل
- false alert و missed alert در pilot گزارش‌شده
- تمام داده‌های shareable قابل revoke
- تست حداقل ۱۰ سالمند و ۵ مراقب
- تست حداقل ۳ گوشی Android و ۲ Android TV
- بررسی پزشک/داروساز برای medication و nutrition claims
