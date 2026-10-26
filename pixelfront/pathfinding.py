"""8-directional A* over the tile grid."""
import heapq

_D = 1.41421356
_NEIGHBOURS = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
               (1, 1, _D), (1, -1, _D), (-1, 1, _D), (-1, -1, _D))


def find_path(world, start, goal_rect, adjacent=False, max_nodes=5000):
    """Path of tiles from start (exclusive) into goal_rect (inclusive tile rect).

    With adjacent=True, any tile touching the rect counts as arriving (used for
    structures and other blocked targets). If the goal can't be reached, returns a
    path to the closest tile found instead.
    """
    w, h, blocked = world.w, world.h, world.blocked
    sx, sy = start
    x0, y0, x1, y1 = goal_rect
    reach = 1 if adjacent else 0

    def heur(x, y):
        dx = max(x0 - x, 0, x - x1)
        dy = max(y0 - y, 0, y - y1)
        return dx + dy + (_D - 2) * min(dx, dy)

    def arrived(x, y):
        return max(x0 - x, 0, x - x1) <= reach and max(y0 - y, 0, y - y1) <= reach

    if arrived(sx, sy):
        return []
    start_i = sy * w + sx
    g = {start_i: 0.0}
    came = {}
    closed = set()
    h0 = heur(sx, sy)
    open_heap = [(h0, h0, sx, sy)]
    best_h, best_i = h0, start_i
    expanded = 0
    while open_heap and expanded < max_nodes:
        _, hc, x, y = heapq.heappop(open_heap)
        i = y * w + x
        if i in closed:
            continue
        closed.add(i)
        expanded += 1
        if i != start_i and arrived(x, y):
            return _rebuild(came, i, start_i, w)
        if hc < best_h:
            best_h, best_i = hc, i
        gc = g[i]
        for dx, dy, cost in _NEIGHBOURS:
            nx, ny = x + dx, y + dy
            if nx < 0 or ny < 0 or nx >= w or ny >= h:
                continue
            ni = ny * w + nx
            if blocked[ni] or ni in closed:
                continue
            if dx and dy and (blocked[y * w + nx] or blocked[ny * w + x]):
                continue  # no cutting corners
            ng = gc + cost
            if ng < g.get(ni, 1e18):
                g[ni] = ng
                came[ni] = i
                nh = heur(nx, ny)
                heapq.heappush(open_heap, (ng + nh, nh, nx, ny))
    return _rebuild(came, best_i, start_i, w)


def _rebuild(came, i, start_i, w):
    path = []
    while i != start_i:
        path.append((i % w, i // w))
        i = came[i]
    path.reverse()
    return path
