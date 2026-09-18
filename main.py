import os
import threading
from datetime import datetime
from flask import Flask
import telebot
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
اصول پاسخ‌دهی:
۱. در تمام زمینه‌ها (کدنویسی، تولید محتوا، ترجمه، پاسخ به سوالات عمومی و ایده‌پردازی) دقیق و کاربردی کمک کن.
۲. زبان پیش‌فرض فارسی روان و سلیس است؛ اگر کاربر فینگلیش یا انگلیسی پیام داد، با همان ساختار پاسخ بده.
۳. از تعارفات طولانی پرهیز کن و مستقیماً و با ساختار تمیز پاسخ سوال را بده.
۴. «از قالب‌بندی استاندارد Markdown مثل دو ستاره برای بولد کردن و بک‌تیک برای کدها استفاده کن و همیشه علائم را کامل ببند.
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
            bot.reply_to(message, reply_text.strip(), parse_mode='Markdown')
        else:
            bot.reply_to(message, "پاسخی دریافت نشد؛ لطفاً دوباره تلاش کنید.")

    except Exception as e:
        print(f"Error: {e}")
        bot.reply_to(message, f"خطا در پردازش:\n{e}")

print("ربات پرسرعت آماده به کار است...")
bot.infinity_polling()
