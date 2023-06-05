n, m, k = map(int, input().split())
data = list(map(int, input().split()))

while len(data) != n:
    print("Data length is not correct, Please input right number : ", n)
    data = list(map(int, input().split()))

data.sort()

first = data[n-1]
second = data[n-2]

acc_sum = 0

if 0:
    max_count = 0
    for i in range(m):
        if max_count < k :
            max_count += 1
            acc_sum += first
        else :
            max_count = 0
            acc_sum += second
else :
    count = int(m / (k+1)) * k
    count += m % (k+1)

    acc_sum = count * first
    acc_sum += (m - count) * second

print("Acc_sum value = ", acc_sum)