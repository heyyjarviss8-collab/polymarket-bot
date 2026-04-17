import os
import time
import asyncio
import logging
import json
import requests
from datetime import datetime
from telegram import Bot, Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

PRIVATE_KEY = os.environ["PRIVATE_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = int(os.environ["CHAT_ID"])

HOST = "https://clob.polymarket.com"
CHAIN = 137

markets = {}
waiting_for_urls = False

client = ClobClient(HOST, key=PRIVATE_KEY, chain_id=CHAIN)
client.set_api_creds(client.create_or_derive_api_creds())

def get_price(token_id):
    try:
        url = HOST + "/price?token_id=" + token_id + "&side=buy"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return float(r.json()["price"])
    except Exception as e:
        log.error("Fiyat hatasi: " + str(e))
        return None

def get_token_id_from_url(url):
    try:
        if "polymarket.com" in url:
            slug = url.rstrip("/").split("/event/")[-1].split("?")[0]
            api_url = "https://gamma-api.polymarket.com/events?slug=" + slug
            r = requests.get(api_url, timeout=10)
            r.raise_for_status()
            data = r.json()
            if data and len(data) > 0:
                markets_data = data[0].get("markets", [])
                if markets_data:
                    token_ids = markets_data[0].get("clobTokenIds", "[]")
                    ids = json.loads(token_ids)
                    if ids:
                        return ids[0]
        return url.strip()
    except Exception as e:
        log.error("Token ID hatasi: " + str(e))
        return None

def place_order(token_id, side, amount_usdc, price):
    try:
        size = round(amount_usdc / price, 4)
        order_args = OrderArgs(
            token_id=token_id,
            price=price,
            size=size,
            side=BUY if side == "BUY" else SELL,
        )
        signed = client.create_order(order_args)
        resp = client.post_order(signed, OrderType.GTC)
        log.info("Emir gonderildi: " + side + " " + str(size) + " @ " + str(price))
        return True
    except Exception as e:
        log.error("Emir hatasi: " + str(e))
        return False

async def send_telegram(bot, text):
    await bot.send_message(chat_id=CHAT_ID, text=text)

async def strategy_loop(bot):
    while True:
        await asyncio.sleep(30)
        if not markets:
            continue
        for token_id, state in list(markets.items()):
            price = get_price(token_id)
            if price is None:
                continue

            short_id = token_id[:8] + "..."
            position = state["position"]
            sold_half = state["sold_half"]
            bought2 = state["bought2"]

            log.info("[" + short_id + "] Fiyat: " + str(price) + " Poz: " + str(round(position, 2)))

            if price < 0.10 and position == 0 and not sold_half:
                if place_order(token_id, "BUY", 25.0, price):
                    state["position"] = 25.0 / price
                    state["sold_half"] = False
                    await send_telegram(bot, "ALIM 1 - " + short_id + "\nFiyat: " + str(price) + "\nTutar: $25")

            elif price < 0.05 and position > 0 and not bought2:
                if place_order(token_id, "BUY", 25.0, price):
                    state["position"] += 25.0 / price
                    state["bought2"] = True
                    await send_telegram(bot, "ALIM 2 - " + short_id + "\nFiyat: " + str(price) + "\nTutar: $25")

            if position > 0 and price >= 0.50 and not sold_half:
                sell_size = position * 0.5
                if place_order(token_id, "SELL", sell_size * price * 0.5, price):
                    gain = sell_size * price
                    state["position"] = position - sell_size
                    state["sold_half"] = True
                    await send_telegram(bot, "SATIS %50 - " + short_id + "\nFiyat: " + str(price) + "\nKazanc: $" + str(round(gain, 2)))

async def morning_scheduler(bot):
    global waiting_for_urls
    while True:
        now = datetime.now()
        target = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now >= target:
            from datetime import timedelta
            target = target + timedelta(days=1)
        wait_secs = (target - now).total_seconds()
        log.info("Sabah mesajina " + str(round(wait_secs / 3600, 1)) + " saat var.")
        await asyncio.sleep(wait_secs)

        waiting_for_urls = True
        markets.clear()
        await send_telegram(bot, "Gunaydin! Bugun hangi maclari takip edeyim?\nPolymarket URL'lerini gonder.\nBitince 'tamam' yaz.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global waiting_for_urls

    if update.effective_chat.id != CHAT_ID:
        return

    text = update.message.text.strip()

    if not waiting_for_urls:
        await update.message.reply_text("Su an URL beklemiyorum. Sabah 09:00'da sorarim!")
        return

    if text.lower() in ("tamam", "ok", "bitti"):
        waiting_for_urls = False
        if markets:
            await update.message.reply_text(str(len(markets)) + " mac eklendi, takip basliyor!")
        else:
            await update.message.reply_text("Hic gecerli URL eklenmedi.")
        return

    raw_urls = [u.strip() for u in text.replace(",", " ").split() if u.strip()]
    added = 0
    for url in raw_urls:
        token_id = get_token_id_from_url(url)
        if token_id:
            markets[token_id] = {"position": 0.0, "sold_half": False, "bought2": False}
            added += 1
        else:
            await update.message.reply_text("URL'den token cikarilmadi: " + url)

    if added > 0:
        await update.message.reply_text(str(added) + " mac eklendi. Daha fazla URL gonder ya da 'tamam' yaz.")

async def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    bot = app.bot
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.gather(
        morning_scheduler(bot),
        strategy_loop(bot),
    )

if __name__ == "__main__":
    asyncio.run(main())
