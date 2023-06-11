n, m = map(int, input().split())
max_value = 0
if 0:
    data = []
    for i in range(n):
        data.append(list(map(int, input().split())))
        data[i].sort()
        if i == 0:
            max_value = data[i][0]
        else :
            max_value = data[i][0] if data[i][0] > max_value else max_value
else :
    for i in range(n):
        data = list(map(int, input().split()))
        min_value = min(data)
        max_value = max(max_value, min_value)

print("max_value number is : ", max_value)
