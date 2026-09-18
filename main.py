import os
import threading
from datetime import datetime
from flask import Flask
import telebot
from groq import Groq

# ۱. وب‌سرور برای زنده نگه داشتن سرویس در رندر
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is active and running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()

# ۲. دریافت امن متغیرها از رندر
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# ۳. دستورات پایه، هویت برند و مشخصات کامل سرویس‌ها
SYSTEM_PROMPT = """
تو پشتیبان رسمی و هوشمند مجموعه «سنجاب VPN» هستی.

قوانین کلی و هویت:
۱. فقط به فارسی سلیس و محاوره‌ای محترمانه پاسخ بده.
۲. هرگز نامی از OpenAI، ChatGPT یا مدل‌های متفرقه نبر؛ اگر درباره هویتت پرسیدند، بگو: «من پشتیبان هوشمند سنجاب VPN هستم».
۳. پاسخ‌ها حتماً کوتاه، شفاف و حداکثر در ۲ الی ۳ جمله باشند تا کاربر معطل نشود.
۴. قیمت‌ها کاملاً مقطوع هستند؛ تحت هیچ شرایطی تخفیف نده.
۵. برای خرید نهایی، کاربر را به دکمه‌های شیشه‌ای منوی ربات راهنمایی کن.

مشخصات سرویس پایه و اقتصادی (اشتراک‌های یکماهه)[span_0](start_span)[span_0](end_span):
- سرورهای مستقیم و بهینه با کیفیت مناسب وب‌گردی، پیام‌رسان‌ها و اینستاگرام[span_1](start_span)[span_1](end_span).
- دسترسی به لوکیشن‌های منتخب (محدودتر از VIP)[span_2](start_span)[span_2](end_span).
- سازگار با تمامی اپراتورها، اینترنت خانگی و تمام دستگاه‌ها (اندروید، iOS، ویندوز و مک)[span_3](start_span)[span_3](end_span).
- تعرفه‌ها:
  * ۱۰ گیگ: ۵۹,۰۰۰ تومان[span_4](start_span)[span_4](end_span)
  * ۲۰ گیگ: ۱۰۹,۰۰۰ تومان[span_5](start_span)[span_5](end_span)
  * ۳۰ گیگ: ۱۴۹,۰۰۰ تومان[span_6](start_span)[span_6](end_span)
  * ۴۰ گیگ: ۱۸۹,۰۰۰ تومان[span_7](start_span)[span_7](end_span)
  * ۵۰ گیگ (پیشنهادی): ۲۲۹,۰۰۰ تومان[span_8](start_span)[span_8](end_span)
  * ۷۵ گیگ: ۳۲۹,۰۰۰ تومان[span_9](start_span)[span_9](end_span)
  * ۱۰۰ گیگ: ۳۹۹,۰۰۰ تومان[span_10](start_span)[span_10](end_span)

مشخصات سرویس اختصاصی VIP (اشتراک‌های یکماهه)[span_11](start_span)[span_11](end_span):
- سرورهای تانل‌شده اختصاصی با پایداری بسیار بالا و بدون نوسان[span_12](start_span)[span_12](end_span).
- مناسب اینستاگرام، یوتیوب، وب‌گردی و گیمینگ[span_13](start_span)[span_13](end_span).
- دارای قابلیت استفاده هم‌زمان برای اعضای خانواده[span_14](start_span)[span_14](end_span).
- دسترسی به متنوع‌ترین لوکیشن‌های اختصاصی و پشتیبانی ۲۴ ساعته[span_15](start_span)[span_15](end_span).
- قابل اتصال روی تمامی دستگاه‌ها[span_16](start_span)[span_16](end_span).
- تعرفه‌ها:
  * ۱۰ گیگ: ۱۰۹,۰۰۰ تومان[span_17](start_span)[span_17](end_span)
  * ۲۰ گیگ: ۱۹۹,۰۰۰ تومان[span_18](start_span)[span_18](end_span)
  * ۳۰ گیگ: ۲۷۹,۰۰۰ تومان[span_19](start_span)[span_19](end_span)
  * ۴۰ گیگ (پیشنهادی): ۳۵۹,۰۰۰ تومان[span_20](start_span)[span_20](end_span)
  * ۵۰ گیگ: ۴۲۹,۰۰۰ تومان[span_21](start_span)[span_21](end_span)
  * ۷۵ گیگ: ۵۹۹,۰۰۰ تومان[span_22](start_span)[span_22](end_span)
  * ۱۰۰ گیگ (خانوادگی): ۷۴۹,۰۰۰ تومان[span_23](start_span)[span_23](end_span)

تفاوت دو پلن: سرویس VIP به دلیل سرورهای تانل‌شده برای یوتیوب و بازی مناسب‌تر بوده و اجازه اتصال هم‌زمان چند کاربر را می‌دهد[span_24](start_span)[span_24](end_span)، در حالی که سرویس اقتصادی قیمت ارزان‌تری دارد و برای استفاده روزمره مناسب است[span_25](start_span)[span_25](end_span).
"""

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "سلام! به پشتیبانی سنجاب VPN خوش آمدید. چطور می‌توانم کمکتان کنم؟")

@bot.message_handler(func=lambda message: True)
def handle_chat(message):
    try:
        bot.send_chat_action(message.chat.id, 'typing')

        # تزریق زنده زمان سرور به حافظه لحظه‌ای مدل
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        full_system_context = f"{SYSTEM_PROMPT}\nاطلاعات سیستمی: زمان و تاریخ کنونی سرور: {current_time}"

        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": full_system_context},
                {"role": "user", "content": message.text}
            ],
            temperature=0.3,
            max_tokens=350
        )

        reply_text = response.choices[0].message.content

        # جلوگیری از خطای متن خالی تلگرام (Error 400)
        if reply_text and reply_text.strip():
            bot.reply_to(message, reply_text.strip())
        else:
            bot.reply_to(message, "متاسفانه پاسخی دریافت نشد، لطفاً سوال خود را مجدداً بنویسید.")

    except Exception as e:
        print(f"Error: {e}")
        bot.reply_to(message, "سیستم موقتاً در دسترس نیست؛ لطفاً دقایقی دیگر پیام دهید.")

print("ربات در حال اجراست...")
bot.infinity_polling()
