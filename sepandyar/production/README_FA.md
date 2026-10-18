# مسیر تولید بر اساس پروپوزال

این پوشه قرارداد استقرار تولیدی پیشنهادی پروپوزال را نگه می‌دارد: Django REST، PostgreSQL، Redis و Celery.

نسخه‌ی اجرایی و تست‌شده‌ی فعلی در ریشه پروژه با `server.py` است. Docker Compose این پوشه برای مرحله انتقال به محیط production آماده شده و قبل از اجرا باید پروژه Django، migrationهای PostgreSQL، احراز هویت و secretهای واقعی اضافه شوند.

هرگز مقادیر `.env.example` را در production استفاده نکنید. ابتدا آن را به `.env` تبدیل کنید، secret تصادفی بسازید، TLS و backup رمزنگاری‌شده تنظیم کنید و سرویس را پشت reverse proxy قرار دهید.
