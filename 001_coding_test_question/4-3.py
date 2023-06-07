loc = input()
x = "abcdefgh".find(loc[0]) + 1
y = int(loc[1])
count = 0

nx = [-2, -2, -1, +1, +2, +2, -1, +1]
ny = [-1, +1, +2, +2, -1, +1, -2, -2]

for i in range(8):
    dx = x + nx[i]
    dy = y + ny[i]

    if (dx < 1) or (dx > 8) or (dy < 1) or (dy > 8) :
        continue
    else :
        count += 1

print(count)


#print(loc[0], loc[1])
#print(x, y)