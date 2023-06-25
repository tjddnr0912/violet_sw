from collections import deque

def search_bfs(graph, visited, n, m):
    #print("Function Start")
    num_iceCream = 0
    queue = deque()

    dx = [ 0, 1, 0, -1]
    dy = [-1, 0, 1,  0]

    for y in range(n):
        for x in range(m):
            if visited[y*m + x] == False:
                num_iceCream += 1
                visited[y*m + x] = True
                for i in range(4):
                    if 0 <= x+dx[i] and x+dx[i] < m and 0 <= y+dy[i] and y+dy[i] < n:
                        if visited[(y+dy[i])*m + (x+dx[i])] == False:
                            queue.append([(x+dx[i]), (y+dy[i])])
                            visited[(y+dy[i])*m + (x+dx[i])] = True
                
                print("x: ", x, "y: ", y, "queue: ", list(queue))
                print("visited value")
                for ty in range(n):
                    for tx in range(m):
                        print(visited[ty*m + tx], end=' ')
                    print("")

                while queue:
                    #print("Debug Loop")
                    print("")
                    print("**** Main pos: ", x, y, list(queue))
                    v = queue.popleft()
                    print("******** Current pos: ", v[0], v[1])
                    for i in range(4):
                        if 0 <= v[0]+dx[i] and v[0]+dx[i] < m and 0 <= v[1]+dy[i] and v[1]+dy[i] < n:
                            if visited[(v[1]+dy[i])*m + (v[0]+dx[i])] == False:
                                queue.append([(v[0]+dx[i]), (v[1]+dy[i])])
                                visited[(v[1]+dy[i])*m + (v[0]+dx[i])] = True

                            #print(v[0]+dx[i], v[1]+dy[i], visited[(v[1]+dy[i])*m + (v[0]+dx[i])])
                #print(list(visited))

    return num_iceCream

n, m = map(int, input().split())
graph = []
visited = [False] * (n * m)
for i in range(n):
    graph.append(input())
    for y in range(m):
        #print(i, y, i*m+y)
        if graph[i][y] == '1':
            visited[i*m + y] = True

    #print(list(graph[i]))
#print(graph[0][3])
#print(list(graph))
#print(list(visited))

print(search_bfs(graph, visited, n, m))
