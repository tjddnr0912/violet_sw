n = int(input("Squar size : "))
vector = list(input("Travel vector :").split())

travel_pos = [1, 1]

#for i in range(int(len(vector))) :
for i in range(len(vector)) :
    if vector[i] == "R" :
        if travel_pos[0] != n :
            travel_pos[0] += 1
    elif vector[i] == "L" :
        if travel_pos[0] != 1 :
            travel_pos[0] -= 1
    elif vector[i] == "U" :
        if travel_pos[1] != 1 :
            travel_pos[1] -= 1
    else : # vector[i] == "D" :
        if travel_pos[1] != n :
            travel_pos[1] += 1
    #print(travel_pos)

print("Final destination : ", travel_pos[0], travel_pos[1])