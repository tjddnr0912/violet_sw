from collections import deque
def bfs(graph, start, visited):
    queue = deque([start])
    #print(list(queue))
    visited[start] = True
    while queue:
        #print(list(queue))
        v = queue.popleft()
        print(v, end=' ')
        for i in graph[v]:
            #print(i, " ", visited[i])
            if not visited[i]:
                queue.append(i)
                visited[i] = True
                #print(list(queue))

graph = [
    [],
    [2,3,8],
    [1,7],
    [1,4,5],
    [3,5],
    [3,4],
    [7],
    [2,6,8],
    [1,7]
]

visited = [False] * 9
bfs(graph, 1, visited)