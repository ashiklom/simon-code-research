"""Exact GeoJSON-geometry / bbox intersection in pure Python (stands in for PostGIS ST_Intersects)."""


def _coords(g):
    t = g["type"]
    c = g.get("coordinates")
    if t == "Point":
        return [c]
    if t in ("MultiPoint", "LineString"):
        return c
    if t in ("MultiLineString", "Polygon"):
        return [p for ring in c for p in ring]
    if t == "MultiPolygon":
        return [p for poly in c for ring in poly for p in ring]
    if t == "GeometryCollection":
        return [p for sub in g["geometries"] for p in _coords(sub)]
    return []


def bounds(g):
    pts = _coords(g)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys)) if pts else None


def _lines(g):
    t = g["type"]
    c = g["coordinates"] if t != "GeometryCollection" else None
    if t == "LineString":
        return [c]
    if t in ("MultiLineString", "Polygon"):
        return c
    if t == "MultiPolygon":
        return [ring for poly in c for ring in poly]
    if t == "GeometryCollection":
        return [ln for sub in g["geometries"] for ln in _lines(sub)]
    return []


def _polygons(g):
    t = g["type"]
    if t == "Polygon":
        return [g["coordinates"]]
    if t == "MultiPolygon":
        return g["coordinates"]
    if t == "GeometryCollection":
        return [p for sub in g["geometries"] for p in _polygons(sub)]
    return []


def _in_ring(x, y, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _in_polygon(x, y, poly):
    return _in_ring(x, y, poly[0]) and not any(_in_ring(x, y, h) for h in poly[1:])


def _ccw(a, b, c):
    return (c[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (c[0] - a[0])


def _seg_intersect(p1, p2, p3, p4):
    d1, d2 = _ccw(p3, p4, p1), _ccw(p3, p4, p2)
    d3, d4 = _ccw(p1, p2, p3), _ccw(p1, p2, p4)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True

    def on(a, b, c):
        return min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= c[1] <= max(a[1], b[1])
    return ((d1 == 0 and on(p3, p4, p1)) or (d2 == 0 and on(p3, p4, p2))
            or (d3 == 0 and on(p1, p2, p3)) or (d4 == 0 and on(p1, p2, p4)))


def intersects(g, bbox):
    """True if geometry g (GeoJSON dict, lon/lat) intersects bbox (minx, miny, maxx, maxy)."""
    x0, y0, x1, y1 = bbox
    b = bounds(g)
    if b is None or b[2] < x0 or b[0] > x1 or b[3] < y0 or b[1] > y1:
        return False
    for p in _coords(g):
        if x0 <= p[0] <= x1 and y0 <= p[1] <= y1:
            return True
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    edges = list(zip(corners, corners[1:] + corners[:1]))
    for line in _lines(g):
        for a, c in zip(line, line[1:]):
            for e0, e1 in edges:
                if _seg_intersect(a, c, e0, e1):
                    return True
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return any(_in_polygon(cx, cy, poly) for poly in _polygons(g))
