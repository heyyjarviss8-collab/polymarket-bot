import os
import time
import asyncio
import logging
from datetime import datetime, timezone
import requests
from telegram import Bot, Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType, Side
from py_clob_client.order_builder.constants import BUY, SELL

logging.basicConfig(level=logging.INFO, format=”%(asctime)s %(message)s”)
log = logging.getLogger(**name**)

# ── ENV ──────────────────────────────────────────────────────────────────────

PRIVATE_KEY    = os.environ[“PRIVATE_KEY”]
TELEGRAM_TOKEN = os.environ[“TELEGRAM_TOKEN”]
CHAT_ID        = int(os.environ[“CHAT_ID”])

HOST  = “https://clob.polymarket.com”
CHAIN = 137  # Polygon

# ── STATE ────────────────────────────────────────────────────────────────────

# { token_id: { “position”: float, “sold_half”: bool, “bought2”: bool } }

markets: dict[str, dict] = {}
waiting_for_urls = False

# ── CLOB CLIENT ──────────────────────────────────────────────────────────────

client = ClobClient(HOST, key=PRIVATE_KEY, chain_id=CHAIN)
client.set_api_creds(client.create_or_derive_api_creds())

# ── HELPERS ──────────────────────────────────────────────────────────────────

def get_price(token_id: str) -> float | None:
“”“Polymarket CLOB’dan en iyi bid fiyatını çek.”””
try:
url = f”{HOST}/price?token_id={token_id}&side=buy”
r = requests.get(url, timeout=10)
r.raise_for_status()
return float(r.json()[“price”])
except Exception as e:
log.error(f”Fiyat çekme hatası ({token_id[:8]}…): {e}”)
return None

def get_token_id_from_url(url: str) -> str | None:
“””
Polymarket URL’inden token ID çıkar.
Örnek: https://polymarket.com/event/xxx?tid=TOKEN_ID
ya da doğrudan token ID string olarak verilebilir.
“””
try:
if “polymarket.com” in url:
# URL’deki event slug’dan market bilgisini çek
slug = url.rstrip(”/”).split(”/event/”)[-1].split(”?”)[0]
api_url = f”https://gamma-api.polymarket.com/events?slug={slug}”
r = requests.get(api_url, timeout=10)
r.raise_for_status()
data = r.json()
if data and len(data) > 0:
markets_data = data[0].get(“markets”, [])
if markets_data:
# İlk market’in clobTokenIds’inden al
token_ids = markets_data[0].get(“clobTokenIds”, “[]”)
import json
ids = json.loads(token_ids)
if ids:
return ids[0]  # underdog token (ilk yarı geride kalan)
# Doğrudan token ID verilmişse
return url.strip()
except Exception as e:
log.error(f”Token ID çıkarma hatası: {e}”)
return None

def is_first_half() -> bool:
“””
Polymarket maç saatini API’den çekmek ideal ama
şimdilik zaman bazlı yaklaşım: maçın başlama saatini bilmiyoruz,
bu yüzden botu her zaman aktif tutuyoruz ve
ikinci yarı koruması strateji içinde yönetiliyor.
NOT: İleride maç dakikası API entegrasyonu eklenebilir.
“””
return True  # Strateji kontrolü buy/sell logic’te yapılıyor

def place_order(token_id: str, side: str, amount_usdc: float, price: float) -> bool:
“”“Polymarket’e emir gönder.”””
try:
size = round(amount_usdc / price, 4)
order_args = OrderArgs(
token_id=token_id,
price=price,
size=size,
side=BUY if side == “BUY” else SELL,
)
signed = client.create_order(order_args)
resp = client.post_order(signed, OrderType.GTC)
log.info(f”Emir gönderildi: {side} {size} @ {price} → {resp}”)
return True
except Exception as e:
log.error(f”Emir hatası: {e}”)
return False

async def send_telegram(bot: Bot, text: str):
await bot.send_message(chat_id=CHAT_ID, text=text)

# ── ANA STRATEJİ DÖNGÜSÜ ────────────────────────────────────────────────────

async def strategy_loop(bot: Bot):
“”“Her 30 saniyede bir tüm aktif marketleri kontrol et.”””
while True:
await asyncio.sleep(30)

```
    if not markets:
        continue

    for token_id, state in list(markets.items()):
        price = get_price(token_id)
        if price is None:
            continue

        short_id = token_id[:8] + "..."
        log.info(f"[{short_id}] Fiyat: {price:.4f} | Poz: {state['position']:.2f} | SoldHalf: {state['sold_half']}")

        position  = state["position"]
        sold_half = state["sold_half"]
        bought2   = state["bought2"]

        # ── ALIM 1: fiyat < 0.10, pozisyon yok ──
        if price < 0.10 and position == 0 and not sold_half:
            success = place_order(token_id, "BUY", 25.0, price)
            if success:
                state["position"] = 25.0 / price
                state["sold_half"] = False
                msg = f"🟢 ALIM 1 — {short_id}\nFiyat: {price:.4f}\nTutar: $25"
                await send_telegram(bot, msg)
                log.info(msg)

        # ── ALIM 2: fiyat < 0.05, pozisyon var, ikinci alım yapılmadı ──
        elif price < 0.05 and position > 0 and not bought2:
            success = place_order(token_id, "BUY", 25.0, price)
            if success:
                state["position"] += 25.0 / price
                state["bought2"] = True
                msg = f"🟡 ALIM 2 (ekleme) — {short_id}\nFiyat: {price:.4f}\nTutar: $25"
                await send_telegram(bot, msg)
                log.info(msg)

        # ── %50 SATIŞ: fiyat >= 0.50, pozisyon var, henüz satılmadı ──
        if position > 0 and price >= 0.50 and not sold_half:
            sell_size = position * 0.5
            success = place_order(token_id, "SELL", sell_size * price * 0.5, price)
            if success:
                gain = sell_size * price
                state["position"] = position - sell_size
                state["sold_half"] = True
                msg = (f"🔴 %50 SATIŞ — {short_id}\n"
                       f"Fiyat: {price:.4f}\n"
                       f"Tahmini kazanç: ${gain:.2f}\n"
                       f"Kalan pozisyon: {state['position']:.2f}")
                await send_telegram(bot, msg)
                log.info(msg)
```

# ── SABAH 09:00 SORUSU ──────────────────────────────────────────────────────

async def morning_scheduler(bot: Bot):
“”“Her gün 09:00’da Telegram’dan maç URL’si iste.”””
global waiting_for_urls
while True:
now = datetime.now()
# Bugün 09:00’ı hesapla
target = now.replace(hour=9, minute=0, second=0, microsecond=0)
if now >= target:
# Yarın 09:00
target = target.replace(day=target.day + 1)
wait_secs = (target - now).total_seconds()
log.info(f”Sabah mesajına {wait_secs/3600:.1f} saat var.”)
await asyncio.sleep(wait_secs)

```
    waiting_for_urls = True
    markets.clear()  # Eski maçları temizle
    await send_telegram(bot,
        "🌅 Günaydın! Bugün hangi maçları takip edeyim?\n"
        "Polymarket URL'lerini gönder (her biri ayrı mesaj veya virgülle ayır).\n"
        "Bitince 'tamam' yaz."
    )
```

# ── TELEGRAM MESAJ HANDLER ──────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
global waiting_for_urls

```
if update.effective_chat.id != CHAT_ID:
    return

text = update.message.text.strip()

if not waiting_for_urls:
    await update.message.reply_text("Şu an URL beklemiyor. Sabah 09:00'da sorarım! ⏰")
    return

if text.lower() in ("tamam", "ok", "bitti"):
    waiting_for_urls = False
    if markets:
        await update.message.reply_text(
            f"✅ {len(markets)} maç eklendi, takip başlıyor!\n" +
            "\n".join(f"• {tid[:12]}..." for tid in markets)
        )
    else:
        await update.message.reply_text("⚠️ Hiç geçerli URL eklenmedi.")
    return

# URL'leri işle (virgülle veya boşlukla ayrılmış olabilir)
raw_urls = [u.strip() for u in text.replace(",", " ").split() if u.strip()]
added = 0
for url in raw_urls:
    token_id = get_token_id_from_url(url)
    if token_id:
        markets[token_id] = {"position": 0.0, "sold_half": False, "bought2": False}
        added += 1
        log.info(f"Market eklendi: {token_id[:12]}...")
    else:
        await update.message.reply_text(f"❌ Bu URL'den token çıkarılamadı:\n{url}")

if added > 0:
    await update.message.reply_text(f"✅ {added} maç eklendi. Daha fazla URL gönder ya da 'tamam' yaz.")
```

# ── MAIN ─────────────────────────────────────────────────────────────────────

async def main():
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
bot = app.bot

```
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

await app.initialize()
await app.start()
await app.updater.start_polling()

# Paralel görevler
await asyncio.gather(
    morning_scheduler(bot),
    strategy_loop(bot),
)
```

if __name__ == “__main__”:
asyncio.run(main())
