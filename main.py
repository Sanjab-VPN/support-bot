import os
import threading
from datetime import datetime
from flask import Flask
import telebot
from telebot.apihelper import ApiTelegramException
from groq import Groq

# ۱. فعال نگه‌داشتن وب‌سرویس روی سرور رندر
app = Flask(__name__)

@app.route('/')
def home():
    return "Personal Fast AI Assistant is Online!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()

# ۲. فراخوانی امن توکن‌ها
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# ۳. دستور سیستمی برای دستیار همه‌کاره و سریع
SYSTEM_PROMPT = """
تو یک دستیار هوش مصنوعی شخصی، فوق‌العاده سریع، هوشمند و مسلط به تمامی زمینه‌ها هستی.
خروجی تو مستقیماً در تلگرام نمایش داده می‌شود؛ بنابراین این قواعد را رعایت کن:

اصول پاسخ‌دهی و قالب‌بندی:
۱. در تمام زمینه‌ها (کدنویسی، تولید محتوا، ترجمه، تحلیل و ایده‌پردازی) دقیق و کاربردی پاسخ بده.
۲. زبان پیش‌فرض فارسی روان و سلیس است؛ اگر کاربر فینگلیش یا انگلیسی نوشت، متناسب با زبان او پاسخ بده.
۳. از تعارفات و مقدمه‌چینی پرهیز کن و مستقیماً پاسخ بده.
۴. برای بولد کردن کلمات از دو ستاره (**متن**) و برای کدهای چندخطی از سه بک‌تیک (```) استفاده کن و همیشه علائم را کامل ببند.
۵. به هیچ وجه از فرمت LaTeX و علامت دلار ($) استفاده نکن؛ تمام محاسبات ریاضی را با متن و نمادهای ساده بنویس (مثال: ۱۵ × ۴۲ = ۶۳۰).
"""

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "سلام! دستیار پرسرعت شخصی شما آماده پاسخگویی است.")

@bot.message_handler(func=lambda message: True)
def handle_chat(message):
    try:
        bot.send_chat_action(message.chat.id, 'typing')

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        full_system = f"{SYSTEM_PROMPT}\nزمان فعلی سرور: {current_time}"

        response = client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {"role": "system", "content": full_system},
                {"role": "user", "content": message.text}
            ],
            temperature=0.6,
            max_tokens=800
        )

        reply_text = response.choices[0].message.content

        if reply_text and reply_text.strip():
            clean_text = reply_text.strip()
            # تلاش اول: ارسال با استایل تلگرام (بولد، باکس کد و ...)
            try:
                bot.reply_to(message, clean_text, parse_mode='Markdown')
            except ApiTelegramException:
                # سوپاپ اطمینان: در صورت خطای نگارشی هوش مصنوعی، ارسال متن ساده تا پیام نسوزد
                bot.reply_to(message, clean_text)
        else:
            bot.reply_to(message, "پاسخی دریافت نشد؛ لطفاً دوباره تلاش کنید.")

    except Exception as e:
        print(f"Error: {e}")
        bot.reply_to(message, f"خطا در پردازش:\n{e}")

print("ربات پرسرعت آماده به کار است...")
bot.infinity_polling()
