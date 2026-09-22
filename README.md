# 🎬 زیرنویسا (Zirnevisa)

<div align="center">

![Django](https://img.shields.io/badge/Django-5.0+-092E20?style=for-the-badge&logo=django&logoColor=white)
![Google Gemini](https://img.shields.io/badge/Google%20Gemini-64K%20Output-4285F4?style=for-the-badge&logo=google&logoColor=white)
![Mistral AI](https://img.shields.io/badge/Mistral%20AI-16K%20Output-FF7000?style=for-the-badge&logo=mistralai&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white)
![HTMX](https://img.shields.io/badge/HTMX-Live%20Polling-3D72D7?style=for-the-badge)

**سامانه هوشمند و فوق‌سریع ترجمه زیرنویس فیلم و سریال با هوش مصنوعی به زبان فارسی محاوره‌ای و روان**

</div>

---

## ✨ ویژگی‌های کلیدی

- 🗣️ **ترجمه طبیعی و محاوره‌ای:** گفتاری و روان (مشابه زیرنویس‌های برتر انسانی)، با حفظ ۱۰۰٪ تگ‌های استایل (`<i>...</i>`)، تراز (`{\an8}`) و تایم‌کدهای دقیق.
- 🎯 **قانون قطعی یک فایل = یک مدل:** هر فایل زیرنویس از ابتدا تا انتها منحصراً با یک مدل واحد ترجمه می‌شود تا لحن فیلم کاملاً یکدست بماند.
- ⚡ **چانک‌بندی هوشمند بر اساس توان مدل:**
  - **Google Gemini:** سقف ۳۸,۰۰۰ کاراکتر (ترجمه یک فیلم ۲.۵ ساعته فقط در ۲ چانک).
  - **Mistral AI:** سقف ۱۸,۰۰۰ کاراکتر با سیستم خرد کردن خودکار زیرچانک‌ها.
- 💎 **طراحی شیشه‌ای مدرن (Glassmorphism):** همراه با Dark/Light Mode، آپلود Drag & Drop و نوار پیشرفت زنده با HTMX بدون رفرش صفحه.
- ⏳ **سهمیه‌بندی و پاکسازی خودکار:**
  - مهمان: ۳ فایل در روز (حذف خودکار فایل‌ها بعد از ۵ دقیقه).
  - ویژه (VIP): ۱۰ فایل در روز (ذخیره دائمی در داشبورد).
- 🛠️ **پنل مدیریت و ابزار کشف مدل‌ها:** پنل تحت وب برای مدیریت ارائه‌دهندگان + اسکریپت CLI برای تست تاخیر (Latency) و ثبت خودکار مدل‌ها.

---

## 🚀 نصب و راه‌اندازی سریع

```bash
# ۱. کلون پروژه و ورود به مسیر
git clone https://github.com/TheHadrix/Zirnevisa.git
cd Zirnevisa

# ۲. فعال‌سازی محیط مجازی و نصب کتابخانه‌ها
python -m venv .venv
.venv\Scripts\activate      # در لینوکس: source .venv/bin/activate
pip install -r requirements.txt

# ۳. اعمال مایگریشن‌ها و ساخت کاربر ادمین
python manage.py migrate
python manage.py createsuperuser

# ۴. اجرای سرور
python manage.py runserver
```

🌐 **آدرس سایت:** `http://127.0.0.1:8000`  
🔑 **پنل مدیریت:** `http://127.0.0.1:8000/admin-panel/`

---

## ⚙️ تنظیمات مهم (`core/settings.py`)

| متغیر | مقدار پیش‌فرض | توضیحات |
| :--- | :---: | :--- |
| `GEMINI_CHUNK_MAX_CHARS` | `38000` | سقف کاراکتر هر چانک برای مدل‌های Gemini |
| `MISTRAL_CHUNK_MAX_CHARS` | `18000` | سقف کاراکتر هر چانک برای مدل‌های Mistral |
| `CHAR_LIMIT` | `38000` | سقف مجاز کاراکترهای فایل برای مهمانان |
| `GUEST_DAILY_LIMIT` | `3` | سهمیه روزانه کاربر مهمان |
| `VIP_DAILY_LIMIT` | `10` | سهمیه روزانه کاربر VIP |
| `GUEST_CLEANUP_DELAY_SECONDS` | `300` | زمان حذف خودکار فایل‌های مهمان (۵ دقیقه) |
