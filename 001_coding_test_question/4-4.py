n, m = map(int, input().split())
x_pos, y_pos, vector = map(int, input().split())
game_map = []
adventure_map = []
for i in range(n) :
    game_map.append(list(map(int, input().split())))
    adventure_map.append(game_map[i])

#debug input value
#n = 4
#m = 4
#x_pos = 1
#y_pos = 1
#vector = 0
#game_map = [[1, 1, 1, 1], [1, 0, 0, 1], [1,1,0,1],[1,1,1,1]]
#adventure_map = [[1, 1, 1, 1], [1, 0, 0, 1], [1,1,0,1],[1,1,1,1]]

if vector == 1 :
    vector = 3
elif vector == 3 :
    vector = 1
else :
    vector = vector

dx = [ 0, -1,  0, +1]
dy = [-1,  0, +1,  0]

done_flag = 0
move_done = 0
count = 1

adventure_map[y_pos][x_pos] = 1

while done_flag != 1:
    #print ("done_flag = ", done_flag)
    for i in range(4) :

        #print(i, move_done, vector)

        if move_done == 1 :
            continue
        else:
            if vector != 3 :
                vector += 1
            else :
                vector = 0

            x_tmp = x_pos + dx[vector]
            y_tmp = y_pos + dy[vector]

            if 0 <= x_tmp and x_tmp < m and 0 <= y_tmp and y_tmp < n :
                #print("pos info : ", x_tmp, y_tmp, adventure_map[y_tmp][x_tmp])
                if adventure_map[y_tmp][x_tmp] == 0 :
                    x_pos = x_tmp
                    y_pos = y_tmp
                    adventure_map[y_pos][x_pos] = 1
                    count += 1
                    move_done = 1
                    #print(x_pos, y_pos, count)
                else :
                    continue
            else :
                continue

    vector_tmp = 0

    if move_done == 1 :
        move_done = 0
        #print("move_done : ", move_done)
    else :
        move_done = 0

        if (vector + 2) <= 3 :
            vector_tmp += 2
        else :
            vector_tmp -= 2

        x_tmp = x_pos + dx[vector_tmp]
        y_tmp = y_pos + dy[vector_tmp]
            
        if 0 <= x_tmp and x_tmp < m and 0 <= y_tmp and y_tmp < n :
            if game_map[y_tmp][x_tmp] == 0 :
                x_pos = x_tmp
                y_pos = y_tmp
                #count += 1
            else :
                done_flag = 1
        else :
            done_flag = 1

print(count)







#debug print
#print (n, m)
#print (x_pos, y_pos, vector)
#for i in range(n) :
#    print(game_map[i])
