import os
import time
import requests
from datetime import datetime, timezone
from eth_account import Account
from eth_account.messages import encode_defunct

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN").strip()
CHAT_ID = str(os.environ.get("CHAT_ID")).strip()
PRIVATE_KEY = os.environ.get("PRIVATE_KEY").strip()

watched_markets = {}

def send_msg(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=10)
    except:
        pass

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 10}
    if offset:
        params["offset"] = offset
    try:
        r = requests.get(url, params=params, timeout=15)
        return r.json().get("result", [])
    except:
        return []

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

def get_auth_headers():
    account = Account.from_key(PRIVATE_KEY)
    timestamp = str(int(time.time()))
    message = encode_defunct(text=timestamp)
    signed = account.sign_message(message)
    return {
        "POLY_ADDRESS": account.address,
        "POLY_SIGNATURE": signed.signature.hex(),
        "POLY_TIMESTAMP": timestamp,
        "POLY_NONCE": timestamp,
        "Content-Type": "application/json"
    }

def buy_token(token_id, price, amount_usd):
    try:
        size = round(amount_usd / price, 4)
        headers = get_auth_headers()
        order = {
            "tokenID": token_id,
            "price": price,
            "size": size,
            "side": "BUY",
            "orderType": "GTC",
            "feeRateBps": "0",
            "nonce": "0",
            "expiration": "0"
        }
        r = requests.post(
            "https://clob.polymarket.com/order",
            json=order,
            headers=headers,
            timeout=10
        )
        return r.json()
    except Exception as e:
        send_msg(f"⚠️ Alım hatası: {str(e)}")
        return None

def sell_token(token_id, price, size):
    try:
        headers = get_auth_headers()
        order = {
            "tokenID": token_id,
            "price": price,
            "size": size,
            "side": "SELL",
            "orderType": "GTC",
            "feeRateBps": "0",
            "nonce": "0",
            "expiration": "0"
        }
        r = requests.post(
            "https://clob.polymarket.com/order",
            json=order,
            headers=headers,
            timeout=10
        )
        return r.json()
    except Exception as e:
        send_msg(f"⚠️ Satış hatası: {str(e)}")
        return None

def handle_message(text):
    text = text.strip()
    
    if "polymarket.com" in text:
        slug = text.split("/")[-1]
        try:
            r = requests.get(f'https://gamma-api.polymarket.com/events?slug={slug}')
            data = r.json()
            markets = data[0]['markets']
            msg = "📋 Bulunan marketler:\n"
            for i, m in enumerate(markets):
                cid = m.get('conditionId', '')
                msg += f"{i+1}. {m['question']}\nID: {cid}\n\n"
            msg += "Takibe eklemek için:\ntoken:ID_BURAYA"
            send_msg(msg)
        except:
            send_msg("❌ Market bulunamadı.")
    
    elif text.startswith("token:"):
        token_id = text.replace("token:", "").strip()
        if token_id not in watched_markets:
            watched_markets[token_id] = {
                "position": 0,
                "sold_half": False,
                "spent": 0,
                "start_time": datetime.now(timezone.utc)
            }
            send_msg(f"✅ Eklendi! Takip başlıyor...\n{token_id[:30]}")
        else:
            send_msg("Zaten takipte.")
    
    elif text == "/liste":
        if watched_markets:
            msg = "📋 Takipteki marketler:\n"
            for t, s in watched_markets.items():
                msg += f"• {t[:20]}... | Poz: {round(s['position'],2)} | Harcanan: ${s['spent']}\n"
            send_msg(msg)
        else:
            send_msg("Takipte market yok.")
    
    elif text == "/temizle":
        watched_markets.clear()
        send_msg("🗑️ Temizlendi.")

def check_markets():
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
            resp = buy_token(token_id, price, 25)
            if resp:
                state["position"] += 25 / price
                state["spent"] += 25
                state["sold_half"] = False
                send_msg(f"✅ ALIM 1\nFiyat: {price} | $25")

        elif first_half and price < 0.05 and position > 0 and spent < 50:
            resp = buy_token(token_id, price, 25)
            if resp:
                state["position"] += 25 / price
                state["spent"] += 25
                send_msg(f"✅ ALIM 2\nFiyat: {price} | $25")

        if position > 0 and price >= 0.50 and not sold_half:
            sell_size = round(state["position"] * 0.5, 4)
            resp = sell_token(token_id, price, sell_size)
            if resp:
                state["position"] -= sell_size
                state["sold_half"] = True
                kazanc = sell_size * price
                send_msg(f"💰 %50 SAT\nFiyat: {price} | Kazanç: ${round(kazanc,2)}")

def main():
    send_msg("🤖 Bot başladı! Gerçek işlem modu aktif.")
    last_update_id = None
    last_morning = None

    while True:
        now = datetime.now(timezone.utc)
        if now.hour == 6 and now.minute == 0:
            if last_morning != now.date():
                send_msg("🌅 Günaydın! Bugün hangi maçları takip edeyim?\ntoken:TOKEN_ID şeklinde gönder.")
                last_morning = now.date()

        updates = get_updates(last_update_id)
        for update in updates:
            last_update_id = update["update_id"] + 1
            if "message" in update and "text" in update["message"]:
                handle_message(update["message"]["text"])

        check_markets()
        time.sleep(30)

if __name__ == "__main__":
    main()
