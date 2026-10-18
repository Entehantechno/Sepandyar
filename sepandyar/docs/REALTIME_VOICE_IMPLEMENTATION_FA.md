# معماری گفت‌وگوی صوتی هم‌زمان

## نتیجه تحقیق

برای مرورگر و موبایل، WebRTC برای ارسال و دریافت مستقیم صدا مناسب‌تر از WebSocket است؛ WebSocket برای pipeline سروری و دریافت/ارسال chunkهای Base64 مناسب است. مستندات رسمی OpenAI برای voice-agent همین تفکیک را توصیه می‌کند. [1](https://developers.openai.com/api/docs/guides/realtime) [2](https://developers.openai.com/api/docs/guides/realtime-webrtc)

توکن اصلی نباید در مرورگر قرار بگیرد. سرور باید با کلید اصلی یک client secret کوتاه‌عمر بسازد و فقط همان را به کلاینت بدهد. [2](https://developers.openai.com/api/docs/guides/realtime-webrtc)

برای تعامل طبیعی، semantic VAD، قطع پاسخ هنگام صحبت سالمند و flush کردن صدای پخش‌شده لازم است. قطع صدا و مدیریت barge-in باید در لایه transport انجام شود تا پاسخ قبلی ادامه پیدا نکند. [3](https://developers.openai.com/api/docs/guides/realtime-conversations)

## آنچه در پروژه اضافه شد

### Backend

```text
GET /api/realtime/session
```

این endpoint:

- تنظیمات AI Studio را از دیتابیس می‌خواند.
- provider، مدل، voice، tone، prompt و guardrails را به session می‌دهد.
- کلید اصلی را در سرور نگه می‌دارد.
- با `OPENAI_API_KEY` یک client secret کوتاه‌عمر می‌سازد.
- بدون کلید، به‌جای شکست خاموش، خطای مشخص `realtime_not_configured` می‌دهد.
- Safety Identifier را به درخواست session اضافه می‌کند.

### Frontend

- WebRTC peer connection
- microphone با echo cancellation، noise suppression و auto gain
- remote audio playback
- data channel برای eventها
- semantic VAD
- fallback خودکار به SpeechRecognition مرورگر
- نمایش transcript و وضعیت شنیدن
- بدون ذخیره کلید اصلی در browser

### fallback

اگر یکی از این موارد برقرار نباشد:

- API key تنظیم نشده باشد
- مرورگر WebRTC نداشته باشد
- مجوز میکروفون رد شده باشد
- provider خطا بدهد

اپ به‌صورت خودکار به SpeechRecognition و TTS محلی بازمی‌گردد.

## guardrailهای realtime

Realtime فقط برای مکالمه نیست؛ ابزارها باید پشت Policy Engine باشند:

```text
model output
   ↓
structured event validation
   ↓
risk classification
   ↓
consent check
   ↓
confirmation check
   ↓
tool execution
   ↓
audit event
```

مدل نباید مستقیماً پرداخت، تغییر دارو، تماس اضطراری، share سلامت یا Accessibility را اجرا کند. این با ریسک‌های OWASP مانند prompt injection، excessive agency، improper output handling و sensitive information disclosure هم‌راستاست. [4](https://www.wiz.io/academy/ai-security/owasp-llm-top-10)

## راه‌اندازی

روی سرور:

```bash
export OPENAI_API_KEY="..."
python3 server.py
```

سپس صفحه را از پورت 4174 باز کنید. اگر کلید وجود نداشته باشد، MVP از fallback صوتی استفاده می‌کند.

## نکته Android

در Android 14، سرویس microphone باید نوع foreground service و مجوزهای مربوط را اعلام کند و شروع سرویس از background محدود است. برای تجربه wake word پایدار، VoiceInteractionService یا شروع foreground service هنگام حضور کاربر لازم است؛ ادعای «شنیدن مخفیانه و نامحدود بعد از force-stop» با محدودیت‌های Android سازگار نیست. [5](https://developer.android.com/about/versions/14/changes/fgs-types-required) [6](https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start)
