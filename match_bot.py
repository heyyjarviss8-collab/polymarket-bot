import time
import random

balance = 200
position = 0
sold_half = False

home = "Argentina"
away = "France"

home_score = 0
away_score = 0
minute = 1

while True:
    minute += 1
    if minute > 90:
        print("MAÇ BİTTİ")
        break

    if random.random() < 0.08:
        if random.random() < 0.5:
            home_score += 1
        else:
            away_score += 1

    first_half = minute <= 45

    # fiyat skora bağlı
    if home_score == away_score:
        price = round(random.uniform(0.3, 0.6), 2)
    elif home_score > away_score:
        price = round(random.uniform(0.7, 0.95), 2)
    else:
        price = round(random.uniform(0.05, 0.15), 2)

    print("MAÇ:", home, "vs", away, "| DK:", minute,
          "| SKOR:", home_score, "-", away_score,
          "| FİYAT:", price)

    if abs(home_score - away_score) == 1:

        if home_score < away_score:
            losing_team = home
        else:
            losing_team = away

        print("GERİDE:", losing_team)

        # ALIM 1
        if first_half and price < 0.10 and position == 0 and balance >= 10:
            amount = 10 / price
            position += amount
            balance -= 10
            sold_half = False
            print("ALIM 1 → 10$ @", price)

        # ALIM 2
        elif first_half and price < 0.05 and position > 0 and balance >= 10:
            amount = 10 / price
            position += amount
            balance -= 10
            print("ALIM 2 → 10$ @", price)

        # RE-ENTRY
        elif price < 0.10 and sold_half and balance >= 10:
            amount = 10 / price
            position += amount
            balance -= 10
            sold_half = False
            print("RE-ENTRY → 10$ @", price)

    # %50 SAT (1 KEZ)
    if position > 0 and price >= 0.50 and not sold_half:
        sell = position * 0.5
        gain = sell * price
        balance += gain
        position -= sell
        sold_half = True
        print("%50 SAT →", price, "|", round(gain,2), "$")

    print("BAKIYE:", round(balance,2), "| POZ:", round(position,2))
    print("------")

    time.sleep(2)
