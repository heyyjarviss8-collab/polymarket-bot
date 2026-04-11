import os
import time
import asyncio
import requests
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = int(os.environ.get("CHAT_ID"))

watched_markets = {}

def get_price(token_id):
    try:
        url = f"https://clob.polymarket.com/book?token_id={token_id}"
        r = requests.get(url, timeout=10)
        data = r.json()
        asks = data.get("asks", [])
        if asks:
            return float(asks[0]["price"])
        return None
    except:
        return None

async def send_msg(bot, msg):
    await bot.send_message(chat_id=CHAT_ID, text=msg)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text.startswith("token:"):
        token_id = text.replace("token:", "").strip()
        if token_id not in watched_markets:
            watched_markets[token_id] = {
                "position": 0,
                "sold_half": False,
                "spent": 0,
                "start_time": datetime.now(timezone.utc)
            }
            await update.message.reply_text(f"✅ Eklendi! Takip başlıyor...")
        else:
            await update.message.reply_text("Zaten takipte.")

    elif text == "/liste":
        if watched_markets:
            msg = "📋 Takipteki marketler:\n"
            for t, s in watched_markets.items():
                msg += f"• {t[:20]}... | Poz: {round(s['position'],2)} | Harcanan: ${s['spent']}\n"
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text("Takipte market yok.")

    elif text == "/temizle":
        watched_markets.clear()
        await update.message.reply_text("🗑️ Temizlendi.")

async def check_markets(bot):
    for token_id, state in list(watched_markets.items()):
        price = get_price(token_id)
        if price is None:
            continue

        elapsed = (datetime.now(timezone.utc) - state["start_time"]).seconds // 60
        first_half = elapsed <= 45
        position = state["position"]
        sold_half = state["sold_half"]
        spent = state["spent"]

        if first_half and price < 0.10 and position == 0:
            state["position"] += 25 / price
            state["spent"] += 25
            state["sold_half"] = False
            await send_msg(bot, f"✅ ALIM 1\nFiyat: {price} | $25")

        elif first_half and price < 0.05 and position > 0 and spent < 50:
            state["position"] += 25 / price
            state["spent"] += 25
            await send_msg(bot, f"✅ ALIM 2\nFiyat: {price} | $25")

        if position > 0 and price >= 0.50 and not sold_half:
            sell_amount = state["position"] * 0.5
            state["position"] -= sell_amount
            state["sold_half"] = True
            kazanc = sell_amount * price
            await send_msg(bot, f"💰 %50 SAT\nFiyat: {price} | Kazanç: ${round(kazanc,2)}")

async def main_loop(bot):
    last_morning = None
    while True:
        now = datetime.now(timezone.utc)
        if now.hour == 6 and now.minute == 0:
            if last_morning != now.date():
                await send_msg(bot,
                    "🌅 Günaydın! Bugün hangi maçları takip edeyim?\n"
                    "token:TOKEN_ID şeklinde gönder.")
                last_morning = now.date()
        await check_markets(bot)
        await asyncio.sleep(30)

async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    
    async with app:
        await app.start()
        await app.updater.start_polling()
        await main_loop(app.bot)
        await app.updater.stop()
        await app.stop()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
