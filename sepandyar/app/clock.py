"""سپندیار — clock"""
import json, sqlite3, os, uuid, datetime, hashlib, re, difflib, time, secrets, hmac, threading, html, math, urllib.request as ureq, urllib.error as uerr
from zoneinfo import ZoneInfo
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, quote, unquote, parse_qs


def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()

# «الان» به ساعت دیواری کاربر. پیش از این چهار محل منطق روزانه از
# datetime.now() خام استفاده می‌کردند، یعنی ساعتِ «خودِ سرور». روی هر سروری که
# منطقهٔ زمانی‌اش تهران نیست، یادآوری دارو به همان اختلاف جابه‌جا می‌شد: روی
# سرور UTC، پنجرهٔ سکوت ۲۲:۰۰–۰۷:۰۰ به ۰۱:۳۰–۱۰:۳۰ ایران ترجمه می‌شد — یعنی
# یادآوری صبحگاهی سرکوب می‌شد و سالمند نصفه‌شب بیدار می‌شد. تاریخ «امروز» هم بین
# ۰۰:۰۰ و ۰۳:۳۰ ایران، روز قبل محسوب می‌شد و دوز به روز اشتباه ثبت می‌گشت.
# زمانِ خودِ دارو از قبل درست ذخیره می‌شود (HH:MM دیواری = نیت کاربر)؛ تنها
# خطا در مقایسه بود، پس فقط ساعت مرجع اصلاح می‌شود.
def _tehran_tz():
 # ZoneInfo درست‌ترین راه است. اما اگر پایگاه‌دادهٔ tz موجود نباشد (مثلاً
 # ویندوز بدون بستهٔ tzdata) نباید کل یادآور از کار بیفتد. ایران از ۲۱ سپتامبر
 # ۲۰۲۲ ساعت تابستانی را لغو کرده و UTC+3:30 ثابت است، پس این جایگزین دقیق است.
 try: return ZoneInfo('Asia/Tehran')
 except Exception: return datetime.timezone(datetime.timedelta(hours=3,minutes=30))

LOCAL_TZ=_tehran_tz()

def local_now(): return datetime.datetime.now(LOCAL_TZ)
