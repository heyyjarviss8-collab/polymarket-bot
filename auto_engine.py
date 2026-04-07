import time

position = 0
sold_half = False

while True:
    try:
        price = float(input("Fiyat: "))
        minute = int(input("Dakika: "))
        diff = int(input("Geride mi (1 evet): "))

        first_half = minute <= 45

        # AL
        if first_half and diff == 1 and price < 0.10 and position == 0:
            print("AL 10$")
            position += 1
            sold_half = False

        # 2. AL
        elif first_half and diff == 1 and price < 0.05 and position > 0:
            print("AL 10$ (2)")
            position += 1

        # RE-ENTRY
        elif diff == 1 and price < 0.10 and sold_half:
            print("RE-ENTRY AL")
            position += 1
            sold_half = False

        # SAT
        if position > 0 and price >= 0.50 and not sold_half:
            print("%50 SAT")
            sold_half = True

        print("------")
        time.sleep(1)

    except:
        pass
