import os
import time
import asyncio
import requests
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ── ENV ───────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = int(os.environ.get("CHAT_ID"))
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
CLOB_API_KEY = os.environ.get("CLOB_API_KEY")
CLOB_SECRET = os.environ.get("CLOB_SECRET")
CLOB_PASSPHRASE = os.environ.get("CLOB_PASSPHRASE")

CLOB_HOST = "https://clob.polymarket.com"

# ── TAKİP EDİLEN MARKETLER ────────────────────────────────
watched_markets = {}

# ── FİYAT ÇEK ────────────────────────────────────────────
def get_price(token_id):
    try:
        url = f"{CLOB_HOST}/book?token_id={token_id}"
        r = requests.get(url, timeout=10)
        data = r.json()
        asks = data.get("asks", [])
        if asks:
            return float(asks[0]["price"])
        return None
    except:
        return None

# ── HEADER OLUŞTUR ────────────────────────────────────────
def get_headers(method, path, body=""):
    import hmac
    import hashlib
    import base64
    from datetime import datetime, timezone

    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    message = timestamp + method.upper() + path + (body or "")
    
    secret_bytes = base64.b64decode(CLOB_SECRET)
    signature = hmac.new(secret_bytes, message.encode(), hashlib.sha256).digest()
    sig_b64 = base64.b64encode(signature).decode()

    return {
        "POLY_ADDRESS": CLOB_API_KEY,
        "POLY_SIGNATURE": sig_b64,
        "POLY_TIMESTAMP": timestamp,
        "POLY_PASSPHRASE": CLOB_PASSPHRASE,
        "Content-Type": "application/json"
    }

# ── GERÇEK ALIM ───────────────────────────────────────────
def buy_token(token_id, amount_usd, price):
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import OrderArgs, OrderType

        client = ClobClient(
            host=CLOB_HOST,
            chain_id=137,
            key=PRIVATE_KEY,
            creds={
                "apiKey": CLOB_API_KEY,
                "secret": CLOB_SECRET,
                "passphrase": CLOB_PASSPHRASE,
            }
        )
        size = round(amount_usd / price, 4)
        order = client.create_order(OrderArgs(
            token_id=token_id,
            price=price,
            size=size,
            side="BUY",
        ))
        resp = client.post_order(order, OrderType.FOK)
        return str(resp)
    except Exception as e:
        return f"HATA: {e}"

# ── GERÇEK SATIM ──────────────────────────────────────────
def sell_token(token_id, size, price):
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import OrderArgs, OrderType

        client = ClobClient(
            host=CLOB_HOST,
            chain_id=137,
            key=PRIVATE_KEY,
            creds={
                "apiKey": CLOB_API_KEY,
                "secret": CLOB_SECRET,
                "passphrase": CLOB_PASSPHRASE,
            }
        )
        order = client.create_order(OrderArgs(
            token_id=token_id,
            price=price,
            size=round(size, 4),
            side="SELL",
        ))
        resp = client.post_order(order, OrderType.FOK)
        return str(resp)
    except Exception as e:
        return f"HATA: {e}"

# ── TELEGRAM MESAJ ────────────────────────────────────────
async def send_msg(app, msg):
    await app.bot.send_message(chat_id=CHAT_ID, text=msg)

# ── TELEGRAM KOMUTLAR ─────────────────────────────────────
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
            await update.message.reply_text(
                f"✅ Eklendi!\nToken: {token_id[:30]}\nTakip başlıyor...")
        else:
            await update.message.reply_text("Bu market zaten takipte.")

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
        await update.message.reply_text("🗑️ Tüm marketler temizlendi.")

    elif text == "/durum":
        await update.message.reply_text(
            f"🤖 Bot aktif\n📊 Takipteki market: {len(watched_markets)}")

# ── STRATEJİ ─────────────────────────────────────────────
async def check_markets(app):
    for token_id, state in list(watched_markets.items()):
        price = get_price(token_id)
        if price is None:
            continue

        elapsed = (datetime.now(timezone.utc) - state["start_time"]).seconds // 60
        first_half = elapsed <= 45
        position = state["position"]
        sold_half = state["sold_half"]
        spent = state["spent"]

        # ALIM 1
        if first_half and price < 0.10 and position == 0:
            resp = buy_token(token_id, 25, price)
            state["position"] += 25 / price
            state["spent"] += 25
            state["sold_half"] = False
            await send_msg(app,
                f"✅ ALIM 1\nFiyat: {price}\nMiktar: $25\n{resp}")

        # ALIM 2
        elif first_half and price < 0.05 and position > 0 and spent < 50:
            resp = buy_token(token_id, 25, price)
            state["position"] += 25 / price
            state["spent"] += 25
            await send_msg(app,
                f"✅ ALIM 2\nFiyat: {price}\nMiktar: $25\n{resp}")

        # %50 SAT
        if position > 0 and price >= 0.50 and not sold_half:
            sell_size = state["position"] * 0.5
            resp = sell_token(token_id, sell_size, price)
            state["position"] -= sell_size
            state["sold_half"] = True
            kazanc = sell_size * price
            await send_msg(app,
                f"💰 %50 SAT\nFiyat: {price}\nKazanç: ${round(kazanc,2)}\n{resp}")

# ── SABAH 9 ───────────────────────────────────────────────
async def morning_ask(app):
    await send_msg(app,
        "🌅 Günaydın! Bugün hangi maçları takip edeyim?\n\n"
        "token:BURAYA_TOKEN_ID şeklinde gönder\n\n"
        "/liste — takipteki marketler\n"
        "/temizle — temizle\n"
        "/durum — bot durumu")

# ── ANA DÖNGÜ ─────────────────────────────────────────────
async def main_loop(app):
    last_morning = None
    while True:
        now = datetime.now(timezone.utc)
        if now.hour == 6 and now.minute == 0:
            if last_morning != now.date():
                await morning_ask(app)
                last_morning = now.date()
        await check_markets(app)
        await asyncio.sleep(30)

async def post_init(app):
    asyncio.create_task(main_loop(app))

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    app.run_polling()

if _name_ == "_main_":
    main()
