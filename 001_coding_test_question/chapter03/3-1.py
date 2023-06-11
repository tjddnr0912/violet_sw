n = int(input("Write how much you need : "))
count = 0

coin_type = [500, 100, 50, 10]

for coin in coin_type:
    count += n // coin
    n %= coin

print("Number of Returns coin number : ", count)