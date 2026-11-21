"""Polynomial graph helpers for bundle/rack reconciliation.

Everything here works in O(V * E log V) or better; no permutation of bundles or
racks is ever enumerated.
"""
from collections import deque
import heapq


def hopcroft_karp(size, adjacency):
    """Maximum bipartite matching.

    ``adjacency`` maps a left vertex to a list of right vertices.  Returns
    ``(match_left, match_right)`` with ``-1`` for unmatched vertices.
    """
    match_left = [-1] * size
    match_right = {}
    distance = [0] * size
    infinity = size + 1

    def bfs():
        queue = deque()
        found = False
        for left in range(size):
            if match_left[left] == -1:
                distance[left] = 0
                queue.append(left)
            else:
                distance[left] = infinity
        while queue:
            left = queue.popleft()
            for right in adjacency.get(left, ()):
                other = match_right.get(right, -1)
                if other == -1:
                    found = True
                elif distance[other] == infinity:
                    distance[other] = distance[left] + 1
                    queue.append(other)
        return found

    def dfs(left):
        for right in adjacency.get(left, ()):
            other = match_right.get(right, -1)
            if other == -1 or (distance[other] == distance[left] + 1 and dfs(other)):
                match_left[left] = right
                match_right[right] = left
                return True
        distance[left] = infinity
        return False

    while bfs():
        for left in range(size):
            if match_left[left] == -1:
                dfs(left)
    return match_left, match_right


def hall_deficiency(adjacency, match_left, match_right, active):
    """Find a Hall-deficient bundle set and its rack neighbourhood.

    ``active`` are the left vertices that still have at least one edge.  The
    alternating search is seeded from exactly the active vertices the maximum
    matching left unmatched, so the reached left set is deficient: it has more
    members than reached racks.  Used to explain "each edge is individually
    usable, but together they compete for racks".
    """
    reached_left = {left for left in active if match_left[left] == -1}
    reached_right = set()
    queue = deque(reached_left)
    while queue:
        left = queue.popleft()
        for right in adjacency[left]:
            if right in reached_right:
                continue
            reached_right.add(right)
            other = match_right.get(right, -1)
            if other != -1 and other not in reached_left:
                reached_left.add(other)
                queue.append(other)
    return sorted(reached_left), sorted(reached_right)


def allowed_edges(size, adjacency, match_left, match_right):
    """Edges that occur in at least one maximum matching of the given size.

    The caller must pass a *perfect* matching (all left vertices matched and as
    many right vertices as left ones).  An edge is usable iff it is in that
    matching or lies on an alternating cycle, i.e. both endpoints share a
    strongly connected component of the alternating digraph.
    """
    nodes = 2 * size
    graph = [[] for _ in range(nodes)]
    for left in range(size):
        matched = match_left[left]
        for right in adjacency.get(left, ()):
            if right == matched:
                graph[size + right].append(left)
            else:
                graph[left].append(size + right)
    component = strongly_connected(nodes, graph)
    allowed = set()
    for left in range(size):
        matched = match_left[left]
        for right in adjacency.get(left, ()):
            if right == matched or component[left] == component[size + right]:
                allowed.add((left, right))
    return allowed


def strongly_connected(nodes, graph):
    """Iterative Kosaraju returning a component id per node."""
    order = []
    seen = [False] * nodes
    for start in range(nodes):
        if seen[start]:
            continue
        stack = [(start, 0)]
        seen[start] = True
        while stack:
            vertex, index = stack[-1]
            if index < len(graph[vertex]):
                nxt = graph[vertex][index]
                stack[-1] = (vertex, index + 1)
                if not seen[nxt]:
                    seen[nxt] = True
                    stack.append((nxt, 0))
            else:
                order.append(vertex)
                stack.pop()
    reverse = [[] for _ in range(nodes)]
    for vertex in range(nodes):
        for nxt in graph[vertex]:
            reverse[nxt].append(vertex)
    component = [-1] * nodes
    label = 0
    for start in reversed(order):
        if component[start] != -1:
            continue
        component[start] = label
        stack = [start]
        while stack:
            vertex = stack.pop()
            for nxt in reverse[vertex]:
                if component[nxt] == -1:
                    component[nxt] = label
                    stack.append(nxt)
        label += 1
    return component


def min_cost_matching(size, edges):
    """Minimum-cost perfect matching of a bipartite graph with ``size`` each.

    ``edges`` is an iterable of ``(left, right, cost)`` with non-negative
    integer costs.  Returns a list ``right_of_left`` or ``None`` when no
    perfect matching exists.  Successive shortest paths with potentials keeps
    this polynomial even for the maximum supported input.
    """
    source = 2 * size
    sink = source + 1
    nodes = sink + 1
    graph = [[] for _ in range(nodes)]

    def add_edge(start, end, capacity, cost):
        graph[start].append([end, len(graph[end]), capacity, cost])
        graph[end].append([start, len(graph[start]) - 1, 0, -cost])

    for left in range(size):
        add_edge(source, left, 1, 0)
    for right in range(size):
        add_edge(size + right, sink, 1, 0)
    references = []
    for left, right, cost in edges:
        index = len(graph[left])
        add_edge(left, size + right, 1, cost)
        references.append((left, right, index))

    potential = [0] * nodes
    infinity = float('inf')
    flow = 0
    while flow < size:
        distance = [infinity] * nodes
        previous_node = [-1] * nodes
        previous_edge = [-1] * nodes
        distance[source] = 0
        queue = [(0, source)]
        while queue:
            current, vertex = heapq.heappop(queue)
            if current > distance[vertex]:
                continue
            for index, edge in enumerate(graph[vertex]):
                target, _, capacity, cost = edge
                if capacity <= 0:
                    continue
                candidate = current + cost + potential[vertex] - potential[target]
                if candidate < distance[target]:
                    distance[target] = candidate
                    previous_node[target] = vertex
                    previous_edge[target] = index
                    heapq.heappush(queue, (candidate, target))
        if distance[sink] == infinity:
            return None
        for vertex in range(nodes):
            if distance[vertex] < infinity:
                potential[vertex] += distance[vertex]
        vertex = sink
        while vertex != source:
            node = previous_node[vertex]
            edge = graph[node][previous_edge[vertex]]
            edge[2] -= 1
            graph[vertex][edge[1]][2] += 1
            vertex = node
        flow += 1

    right_of_left = [-1] * size
    for left, right, index in references:
        if right_of_left[left] == -1 and graph[left][index][2] == 0:
            right_of_left[left] = right
    return right_of_left
