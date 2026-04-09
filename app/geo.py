"""
Geo utilities: suburb coordinates (lat/lng) and haversine distance.
Used for 5km-radius store discovery on the landing page.
"""
import math

# Approximate lat/lng for Sydney suburbs (lowercase suburb name → (lat, lng))
SUBURB_COORDS: dict[str, tuple[float, float]] = {
    # City / CBD
    "sydney":               (-33.8688, 151.2093),
    "sydney cbd":           (-33.8688, 151.2093),
    "haymarket":            (-33.8798, 151.2017),
    "the rocks":            (-33.8593, 151.2090),
    "barangaroo":           (-33.8652, 151.2019),
    "pyrmont":              (-33.8721, 151.1944),
    "ultimo":               (-33.8812, 151.1992),
    # Inner East
    "surry hills":          (-33.8857, 151.2104),
    "darlinghurst":         (-33.8781, 151.2168),
    "east sydney":          (-33.8730, 151.2180),
    "woolloomooloo":        (-33.8680, 151.2196),
    "potts point":          (-33.8678, 151.2247),
    "elizabeth bay":        (-33.8726, 151.2285),
    "redfern":              (-33.8929, 151.2043),
    "waterloo":             (-33.8988, 151.2066),
    "zetland":              (-33.9047, 151.2035),
    "paddington":           (-33.8843, 151.2275),
    "woollahra":            (-33.8876, 151.2382),
    "edgecliff":            (-33.8782, 151.2389),
    # Eastern Suburbs
    "double bay":           (-33.8775, 151.2439),
    "point piper":          (-33.8662, 151.2465),
    "rose bay":             (-33.8726, 151.2653),
    "bellevue hill":        (-33.8840, 151.2570),
    "bondi junction":       (-33.8927, 151.2543),
    "bondi":                (-33.8915, 151.2741),
    "bondi beach":          (-33.8956, 151.2743),
    "tamarama":             (-33.9028, 151.2741),
    "bronte":               (-33.9050, 151.2654),
    "waverley":             (-33.9011, 151.2502),
    "dover heights":        (-33.8705, 151.2752),
    "clovelly":             (-33.9133, 151.2645),
    "coogee":               (-33.9207, 151.2574),
    "randwick":             (-33.9148, 151.2424),
    "kingsford":            (-33.9230, 151.2260),
    "kensington":           (-33.9059, 151.2228),
    "matraville":           (-33.9474, 151.2270),
    "malabar":              (-33.9476, 151.2525),
    "maroubra":             (-33.9495, 151.2416),
    "la perouse":           (-33.9974, 151.2280),
    "phillip bay":          (-33.9977, 151.2351),
    # Inner West
    "glebe":                (-33.8803, 151.1866),
    "forest lodge":         (-33.8835, 151.1826),
    "rozelle":              (-33.8621, 151.1703),
    "lilyfield":            (-33.8712, 151.1643),
    "balmain":              (-33.8589, 151.1800),
    "balmain east":         (-33.8558, 151.1887),
    "birchgrove":           (-33.8513, 151.1793),
    "newtown":              (-33.8977, 151.1787),
    "erskineville":         (-33.9022, 151.1843),
    "enmore":               (-33.9034, 151.1752),
    "st peters":            (-33.9093, 151.1834),
    "sydenham":             (-33.9159, 151.1812),
    "tempe":                (-33.9215, 151.1724),
    "leichhardt":           (-33.8833, 151.1529),
    "annandale":            (-33.8875, 151.1663),
    "petersham":            (-33.9022, 151.1568),
    "lewisham":             (-33.9037, 151.1481),
    "stanmore":             (-33.9014, 151.1617),
    "marrickville":         (-33.9090, 151.1573),
    "dulwich hill":         (-33.9130, 151.1440),
    "ashfield":             (-33.8889, 151.1222),
    "summer hill":          (-33.8893, 151.1287),
    # Alexandria / Green Square
    "alexandria":           (-33.9076, 151.1967),
    "beaconsfield":         (-33.9110, 151.1952),
    "rosebery":             (-33.9176, 151.1977),
    "green square":         (-33.9090, 151.2017),
    "mascot":               (-33.9285, 151.1944),
    "eastlakes":            (-33.9305, 151.2193),
    "botany":               (-33.9495, 151.2020),
    # Lower North Shore (IGA area)
    "north sydney":         (-33.8388, 151.2092),
    "lavender bay":         (-33.8449, 151.2058),
    "mcmahons point":       (-33.8474, 151.1987),
    "waverton":             (-33.8352, 151.2013),
    "berry island":         (-33.8280, 151.2013),
    "milsons point":        (-33.8474, 151.2107),
    "kirribilli":           (-33.8498, 151.2119),
    "cammeray":             (-33.8219, 151.2238),
    "cremorne":             (-33.8362, 151.2275),
    "cremorne point":       (-33.8374, 151.2316),
    "artarmon":             (-33.8148, 151.1857),
    "st leonards":          (-33.8234, 151.1944),
    "crows nest":           (-33.8274, 151.2072),
    "wollstonecraft":       (-33.8277, 151.2010),
    "naremburn":            (-33.8190, 151.2015),
    "lane cove":            (-33.8074, 151.1767),
    "longueville":          (-33.8231, 151.1600),
    "mosman":               (-33.8268, 151.2418),
    "neutral bay":          (-33.8387, 151.2183),
    "kurraba point":        (-33.8375, 151.2236),
    # Upper North Shore
    "chatswood":            (-33.7982, 151.1817),
    "willoughby":           (-33.8002, 151.1982),
    "castle cove":          (-33.7954, 151.2089),
    "roseville":            (-33.7863, 151.1773),
    "lindfield":            (-33.7773, 151.1697),
    "killara":              (-33.7641, 151.1622),
    "gordon":               (-33.7557, 151.1539),
    "pymble":               (-33.7435, 151.1404),
    "turramurra":           (-33.7359, 151.1275),
    "warrawee":             (-33.7267, 151.1226),
    "wahroonga":            (-33.7175, 151.1165),
    "hornsby":              (-33.7025, 151.0996),
    "waitara":              (-33.7095, 151.1026),
    "st ives":              (-33.7362, 151.1644),
    # Northern Beaches
    "manly":                (-33.7973, 151.2836),
    "fairlight":            (-33.7950, 151.2737),
    "freshwater":           (-33.7873, 151.2829),
    "curl curl":            (-33.7737, 151.2844),
    "dee why":              (-33.7534, 151.2853),
    "narraweena":           (-33.7556, 151.2701),
    "brookvale":            (-33.7673, 151.2603),
    "narrabeen":            (-33.7244, 151.2990),
    "collaroy":             (-33.7346, 151.2990),
    "avalon beach":         (-33.6322, 151.3297),
    "avalon":               (-33.6322, 151.3297),
    "bilgola":              (-33.6427, 151.3253),
    "mona vale":            (-33.6769, 151.3032),
    "frenchs forest":       (-33.7535, 151.2196),
    # North West / Hills
    "ryde":                 (-33.8163, 151.0978),
    "west ryde":            (-33.8115, 151.0822),
    "meadowbank":           (-33.8238, 151.0892),
    "epping":               (-33.7715, 151.0819),
    "carlingford":          (-33.7815, 151.0480),
    "castle hill":          (-33.7314, 151.0033),
    "baulkham hills":       (-33.7632, 150.9848),
    "kellyville":           (-33.7081, 150.9710),
    "norwest":              (-33.7318, 150.9749),
    "bella vista":          (-33.7266, 150.9715),
    # Parramatta / West
    "parramatta":           (-33.8150, 151.0011),
    "westmead":             (-33.8073, 150.9881),
    "pendle hill":          (-33.7861, 150.9605),
    "granville":            (-33.8341, 151.0133),
    "auburn":               (-33.8495, 151.0325),
    "merrylands":           (-33.8341, 150.9897),
    "liverpool":            (-33.9200, 150.9239),
    "campbelltown":         (-34.0688, 150.8128),
    # Strathfield / Burwood / Inner West
    "strathfield":          (-33.8746, 151.0833),
    "burwood":              (-33.8779, 151.1031),
    "concord":              (-33.8615, 151.0919),
    "homebush":             (-33.8658, 151.0715),
    "homebush bay":         (-33.8523, 151.0716),
    "five dock":            (-33.8624, 151.1269),
    "canada bay":           (-33.8735, 151.1122),
    "drummoyne":            (-33.8498, 151.1248),
    # St George / Sutherland
    "kogarah":              (-33.9660, 151.1344),
    "hurstville":           (-33.9677, 151.1033),
    "rockdale":             (-33.9524, 151.1431),
    "brighton-le-sands":    (-33.9605, 151.1566),
    "ramsgate":             (-33.9777, 151.1527),
    "miranda":              (-34.0355, 151.1027),
    "cronulla":             (-34.0568, 151.1545),
    "sutherland":           (-34.0310, 151.0575),
    # South East
    "little bay":           (-33.9736, 151.2517),
    "chifley":              (-33.9810, 151.2449),
    "port botany":          (-33.9578, 151.2165),
    # Inner West adjacent
    "camperdown":           (-33.8877, 151.1849),
}


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in km between two (lat, lng) points using the Haversine formula."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nearby_suburbs(suburb_name: str, km: float = 5.0) -> list[str]:
    """
    Return all suburb names (lowercase keys) within `km` kilometres of
    `suburb_name`.  Returns empty list if suburb has no coordinates.
    """
    key = suburb_name.strip().lower()
    if key not in SUBURB_COORDS:
        return []
    lat1, lon1 = SUBURB_COORDS[key]
    return [
        s for s, (lat2, lon2) in SUBURB_COORDS.items()
        if haversine(lat1, lon1, lat2, lon2) <= km
    ]
