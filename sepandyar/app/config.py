"""سپندیار — config

مسیرهای پایه و سقف‌های سراسری. این ماژول به هیچ ماژول دیگری وابسته نیست،
پس پایین‌ترین لایهٔ بسته است.
"""
import os

# ROOT پوشهٔ «خودِ برنامه» است، نه پوشهٔ این ماژول. از وقتی کد به بستهٔ app/
# رفت، __file__ به .../sepandyar/app/config.py اشاره می‌کند؛ اگر همان dirname
# را برمی‌داشتیم، ROOT به .../sepandyar/app تبدیل می‌شد و هم سروِ فایل‌های
# ایستا (index.html و بقیه) و هم مسیر پایگاه‌داده به جای اشتباه می‌رفتند.
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB=os.path.join(ROOT,'sepandyar.db')

# سقف بدنهٔ درخواست: ۱MB. بزرگ‌ترین بدنهٔ مشروع این API چند کیلوبایت است؛
# nginx هم به‌طور پیش‌فرض client_max_body_size را ۱MB می‌گیرد.
MAX_BODY_BYTES=1024*1024
