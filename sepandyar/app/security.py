"""سپندیار — security

allowlist سرو پروندهٔ ایستا، سیاست امنیت محتوا و سرصفحه‌های امنیتی.

CSP برای اسکریپت 'unsafe-inline' را نگه می‌دارد چون ۱۱۷ هندلر درون‌خطی
onclick در index.html وجود دارد و nonce یا hash نمی‌تواند جای آن را بگیرد.
HSTS عمداً نیست: سرور روی HTTP محلی اجرا می‌شود و HSTS تنها بر بستر HTTPS
معنا دارد.
"""
import json, sqlite3, os, uuid, datetime, hashlib, re, difflib, time, secrets, hmac, threading, html, math, urllib.request as ureq, urllib.error as uerr
from zoneinfo import ZoneInfo
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, quote, unquote, parse_qs


# تنها پرونده‌هایی که از وب سرو می‌شوند. تا پیش از این super().do_GET() هر
# پروندهٔ زیر ROOT را می‌داد — از جمله sepandyar.db (کل پایگاه‌دادهٔ سلامت
# سالمند، ۴۱۷ کیلوبایت)، server.py، مجموعهٔ آزمون، و فهرست پوشه‌های
# docs/ و uploads/ و production/.
# ریسرچ نشان داد blocklist با percent-encoding دور زده می‌شود چون
# SimpleHTTPRequestHandler مسیر را پیش از نگاشت به دیسک decode می‌کند
# (آزمودم: «/..%2fserver.py» → ۲۰۰ با کل کد منبع). پس allowlist روی مسیر
# decode‌شده سنجیده می‌شود و هر چیز دیگر ۴۰۴ می‌گیرد؛ فهرست پوشه هم
# خودبه‌خود بسته می‌شود چون هیچ مسیری به آن ختم نمی‌شود.
# ====================== بخش ۱۲: امنیت — مسیرهای ایستا، CSP و سرآیندها ======================
# سرآیندها در یک گلوگاه واحد (end_headers) تزریق می‌شوند تا هیچ مسیری
# بی‌سرآیند نماند، از جمله ۴۰۴.
STATIC_ALLOW=frozenset({'/','/index.html','/caregiver.html','/admin.html',
                        '/investor.html','/sw.js','/manifest.webmanifest'})

# --- سرآیندهای امنیتی: روی «هر» پاسخ ---
# اندازه‌گیری پیش از این تغییر: از هفت سرآیند توصیه‌شده، صفر مورد ارسال می‌شد.
# CSP: اسکریپت درون‌خطی عمداً مجاز مانده چون این UI هیچ فریم‌ورکی ندارد و ۱۱۷ هندلر
# onclick در index.html و ۱۲ مورد در caregiver.html دارد؛ nonce و hash هندلر درون‌خطی
# رویداد را پوشش نمی‌دهند، پس script-src سخت کل اپ را از کار می‌انداخت. آنچه این سیاست
# همچنان می‌بندد: هر مبدأ اسکریپت بیرونی، object/embed، ربودن <base>، قاب‌گیری
# (clickjacking) و برون‌بری داده به مبدأ نامعلوم.
CSP=("default-src 'self'; "
 "script-src 'self' 'unsafe-inline'; "
 "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
 "font-src 'self' https://fonts.gstatic.com data:; "
 "img-src 'self' data: blob: https:; "
 # میزبان wss باید «صریح» بیاید: طبق CSP3 فقط http→https و ws→wss ارتقا می‌یابند،
 # پس https:// هیچ‌وقت wss:// را نمی‌پوشاند. بدون این، مسیر Gemini Live (بند ۵)
 # در مرورگر پیش از رسیدن به سرور بسته می‌شد. آدرس از LIVE_WS_BASE گرفته شده.
 "connect-src 'self' https://api.openai.com wss://generativelanguage.googleapis.com; "
 "media-src 'self' blob:; "
 "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")

SECURITY_HEADERS=(('Content-Security-Policy',CSP),
 ('X-Content-Type-Options','nosniff'),
 ('X-Frame-Options','DENY'),
 ('Referrer-Policy','strict-origin-when-cross-origin'),
 # microphone و geolocation عمداً بسته «نشده»اند: getUserMedia در index.html و
 # getCurrentPosition در caregiver.html استفاده می‌شوند. قاعدهٔ پژوهش هم همان است:
 # فقط قابلیتی را ببند که استفاده نمی‌کنی.
 ('Permissions-Policy','camera=(), payment=(), usb=(), magnetometer=(), bluetooth=(), display-capture=(), interest-cohort=()'))
