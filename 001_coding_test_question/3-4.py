n, k = map(int, input().split())

count = 0

while True:
    if n % k == 0:
        n //= k
        count += 1
    else :
        count += (n % k)
        n -= (n % k)

    if n == 0:
        count -= 1
        n = 1
        break

print(count)