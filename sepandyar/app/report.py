"""سپندیار — report

ساخت HTML گزارشِ سمت سرور.

این تنها خروجی HTML سمت سرور است (/share/<token>) و در باگ‌یابی دور دوازدهم
هشت درون‌گذاری خام در آن پیدا شد که XSS ذخیره‌شده می‌ساخت. اکنون هر مقدار
پیش از درون‌گذاری از _e() می‌گذرد و یک پیمایش AST نبودِ درون‌گذاری خام را
قطعی می‌سنجد.
"""
import json, sqlite3, os, uuid, datetime, hashlib, re, difflib, time, secrets, hmac, threading, html, math, urllib.request as ureq, urllib.error as uerr
from zoneinfo import ZoneInfo
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, quote, unquote, parse_qs


# ==================== بخش ۸: گزارش HTML (تنها صفحهٔ سمت‌سرور) ====================
# این تنها جایی است که سرور HTML تولید می‌کند؛ پس تنها جایی است که
# فرار HTML باید دستی انجام شود. _e() هر درون‌گذاری را می‌پوشاند.
def _e(v):
 # هر مقداری که درون HTML درون‌ریزی می‌شود باید escape شود. این گزارش با
 # f-string ساخته می‌شود و هیچ موتور قالبی در کار نیست، پس autoescape
 # معنایی ندارد و فراموش‌شدن یک فیلد یعنی XSS.
 # quote=True (پیش‌فرض) «'» و «"» را هم می‌گیرد، پس هم در متن و هم در مقدارِ
 # درون نقل‌قول امن است. None هم به رشتهٔ خالی تبدیل می‌شود چون ستون‌ها NULL‌پذیرند.
 #
 # اندازه‌گیری شد: «POST /api/profile» با name برابر
 # «<script>document.title="pwned"</script>» ذخیره می‌شد و «/share/<token>»
 # آن را خام برمی‌گرداند؛ در jsdom عنوان صفحه واقعاً «pwned» شد. قربانی
 # آن کسی است که لینک اشتراک را باز می‌کند، یعنی خانوادهٔ سالمند.
 return html.escape('' if v is None else str(v))

def report_html(data):
 p=data.get('profile') or {}; items=data.get('vitals') or []
 tr=''.join(f"<tr><td>{_e(x.get('type'))}</td><td>{_e(x.get('value'))}</td><td>{_e(x.get('source'))}</td><td>{_e(x.get('measured_at'))}</td></tr>" for x in items)
 return f'''<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8"><title>گزارش سلامت — سپندیار</title><style>body{{font-family:Tahoma,Arial;max-width:900px;margin:30px auto;padding:0 18px;color:#18312f}}h1{{color:#347d6d}}table{{width:100%;border-collapse:collapse}}td,th{{padding:12px;border-bottom:1px solid #dfe9e4;text-align:right}}.note{{background:#eef8f3;padding:14px;border-radius:12px}}</style><h1>گزارش علائم حیاتی</h1><div class="note">این لینک تا {_e(data['expires_at'])} معتبر است. اطلاعات با اجازه سالمند به اشتراک گذاشته شده است.</div><h2>{_e(p.get('name','سالمند'))}</h2><p>سن: {_e(p.get('age','ثبت نشده'))} — شرایط ثبت‌شده: {_e(p.get('needs','ثبت نشده'))}</p><table><tr><th>نوع</th><th>مقدار</th><th>منبع</th><th>زمان</th></tr>{tr}</table><p style="color:#71807c">این گزارش جایگزین تشخیص پزشک نیست.</p></html>'''
