"""
Mapping of Sydney suburb names and postcodes → store slugs.

Woolworths and Coles are available across all Sydney.
Aldi has stores nationwide with uniform pricing — included everywhere.
Harris Farm has four Sydney stores — each suburb maps to its nearest one:
  harris_farm_broadway   — Broadway Shopping Centre, 1 Bay St (Inner West / CBD)
  harris_farm_cammeray   — 397 Miller St, Cammeray (Lower North Shore)
  harris_farm_mosman     — 765 Military Rd, Mosman (Mosman / Northern Beaches)
  harris_farm_lane_cove  — 65 Burns Bay Rd, Lane Cove (Lane Cove / Upper North Shore)
IGA variants are included only for the North Sydney / Lower North Shore / Newtown areas.
"""

_W   = "woolworths"
_C   = "coles"
_A   = "aldi"
_HFB = "harris_farm_broadway"    # Broadway Shopping Centre
_HFC = "harris_farm_cammeray"    # 397 Miller St, Cammeray
_HFM = "harris_farm_mosman"      # 765 Military Rd, Mosman
_HFL = "harris_farm_lane_cove"   # 65 Burns Bay Rd, Lane Cove
_IN  = "iga_north_sydney"
_IM  = "iga_milsons_point"
_IC  = "iga_crows_nest"
_INW = "iga_newtown"             # Lloyds IGA Newtown, 259 King St
_IKS = "iga_king_st"             # IGA Local Grocer King Street, 40 King St

SUBURB_STORES: dict[str, list[str]] = {

    # ── City / CBD (2000) — nearest HF: Broadway ──────────────────────
    "sydney":               [_W, _C, _A, _HFB],
    "sydney cbd":           [_W, _C, _A, _HFB],
    "haymarket":            [_W, _C, _A, _HFB],
    "the rocks":            [_W, _C, _A],
    "barangaroo":           [_W, _C, _A],
    "2000":                 [_W, _C, _A, _HFB],

    # ── Pyrmont / Ultimo (2007–2009) — nearest HF: Broadway ──────────
    "pyrmont":              [_W, _C, _A, _HFB],
    "ultimo":               [_W, _C, _A, _HFB],
    "2007":                 [_W, _C, _A, _HFB],
    "2009":                 [_W, _C, _A, _HFB],

    # ── Inner East (2010–2021) — nearest HF: Broadway ─────────────────
    "surry hills":          [_W, _C, _A, _HFB],
    "darlinghurst":         [_W, _C, _A, _HFB],
    "east sydney":          [_W, _C, _A, _HFB],
    "woolloomooloo":        [_W, _C, _A, _HFB],
    "potts point":          [_W, _C, _A, _HFB],
    "elizabeth bay":        [_W, _C, _A, _HFB],
    "2010":                 [_W, _C, _A, _HFB],
    "redfern":              [_W, _C, _A, _HFB],
    "waterloo":             [_W, _C, _A, _HFB],
    "zetland":              [_W, _C, _A, _HFB],
    "2016":                 [_W, _C, _A, _HFB],
    "2017":                 [_W, _C, _A, _HFB],
    "paddington":           [_W, _C, _A, _HFB],
    "woollahra":            [_W, _C, _A, _HFB],
    "edgecliff":            [_W, _C, _A, _HFB],
    "2021":                 [_W, _C, _A, _HFB],

    # ── Eastern Suburbs (2022–2036) — nearest HF: Broadway ────────────
    "double bay":           [_W, _C, _A, _HFB],
    "point piper":          [_W, _C, _A],
    "rose bay":             [_W, _C, _A, _HFB],
    "bellevue hill":        [_W, _C, _A, _HFB],
    "2022":                 [_W, _C, _A, _HFB],
    "bondi junction":       [_W, _C, _A, _HFB],
    "bondi":                [_W, _C, _A, _HFB],
    "bondi beach":          [_W, _C, _A, _HFB],
    "tamarama":             [_W, _C, _A],
    "bronte":               [_W, _C, _A, _HFB],
    "2026":                 [_W, _C, _A, _HFB],
    "waverley":             [_W, _C, _A, _HFB],
    "dover heights":        [_W, _C, _A],
    "2024":                 [_W, _C, _A, _HFB],
    "clovelly":             [_W, _C, _A],
    "coogee":               [_W, _C, _A, _HFB],
    "randwick":             [_W, _C, _A, _HFB],
    "2031":                 [_W, _C, _A, _HFB],
    "kingsford":            [_W, _C, _A],
    "kensington":           [_W, _C, _A, _HFB],
    "2032":                 [_W, _C, _A, _HFB],
    "matraville":           [_W, _C, _A],
    "malabar":              [_W, _C, _A],
    "maroubra":             [_W, _C, _A, _HFB],
    "2035":                 [_W, _C, _A, _HFB],
    "la perouse":           [_W, _C, _A],
    "phillip bay":          [_W, _C, _A],
    "2036":                 [_W, _C, _A],

    # ── Inner West (2037–2050) — nearest HF: Broadway ─────────────────
    "glebe":                [_W, _C, _A, _HFB],
    "forest lodge":         [_W, _C, _A, _HFB],
    "2037":                 [_W, _C, _A, _HFB],
    "rozelle":              [_W, _C, _A, _HFB],
    "lilyfield":            [_W, _C, _A, _HFB],
    "2039":                 [_W, _C, _A, _HFB],
    "balmain":              [_W, _C, _A, _HFB],
    "balmain east":         [_W, _C, _A, _HFB],
    "birchgrove":           [_W, _C, _A, _HFB],
    "2041":                 [_W, _C, _A, _HFB],
    "newtown":              [_W, _C, _A, _HFB, _INW, _IKS],
    "erskineville":         [_W, _C, _A, _HFB, _INW, _IKS],
    "2042":                 [_W, _C, _A, _HFB, _INW, _IKS],
    "enmore":               [_W, _C, _A, _HFB, _INW, _IKS],
    "st peters":            [_W, _C, _A, _HFB, _INW],
    "sydenham":             [_W, _C, _A, _INW],
    "tempe":                [_W, _C, _A],
    "2044":                 [_W, _C, _A, _HFB, _INW],
    "leichhardt":           [_W, _C, _A, _HFB, _INW],
    "annandale":            [_W, _C, _A, _HFB, _INW],
    "2040":                 [_W, _C, _A, _HFB, _INW],
    "petersham":            [_W, _C, _A, _HFB, _INW],
    "lewisham":             [_W, _C, _A, _INW],
    "stanmore":             [_W, _C, _A, _HFB, _INW, _IKS],
    "2048":                 [_W, _C, _A, _HFB, _INW, _IKS],
    "marrickville":         [_W, _C, _A, _HFB, _INW],
    "dulwich hill":         [_W, _C, _A, _HFB],
    "2204":                 [_W, _C, _A, _HFB],
    "ashfield":             [_W, _C, _A, _HFB],
    "summer hill":          [_W, _C, _A, _HFB],
    "2131":                 [_W, _C, _A, _HFB],

    # ── Alexandria / Green Square / Zetland — nearest HF: Broadway ───
    "alexandria":           [_W, _C, _A, _HFB],
    "beaconsfield":         [_W, _C, _A],
    "rosebery":             [_W, _C, _A, _HFB],
    "green square":         [_W, _C, _A, _HFB],
    "2015":                 [_W, _C, _A, _HFB],
    "mascot":               [_W, _C, _A],
    "eastlakes":            [_W, _C, _A],
    "2018":                 [_W, _C, _A],
    "botany":               [_W, _C, _A],
    "2019":                 [_W, _C, _A],

    # ── Lower North Shore (2060–2090) ─────────────────────────────────
    # North Sydney / Cammeray area — nearest HF: Cammeray
    "north sydney":         [_W, _C, _A, _IN,  _HFC],
    "lavender bay":         [_W, _C, _A, _IN,  _HFC],
    "mcmahons point":       [_W, _C, _A, _IN,  _HFC],
    "waverton":             [_W, _C, _A, _IN,  _HFC],
    "berry island":         [_W, _C, _A, _IN,  _HFC],
    "2060":                 [_W, _C, _A, _IN,  _HFC],
    "milsons point":        [_W, _C, _A, _IM,  _HFC],
    "kirribilli":           [_W, _C, _A, _IM,  _HFC],
    "2061":                 [_W, _C, _A, _IM,  _HFC],
    "cammeray":             [_W, _A,  _IN,  _HFC],   # no Coles in Cammeray
    "2062":                 [_W, _A,  _IN,  _HFC],
    # Cremorne — nearest HF: Mosman (Military Rd runs through both)
    "cremorne":             [_W, _C, _A, _HFM],
    "cremorne point":       [_W, _C, _A, _HFM],
    "2063":                 [_W, _C, _A, _HFM],
    # Artarmon / St Leonards / Crows Nest — nearest HF: Cammeray
    "artarmon":             [_W, _C, _A, _IC,  _HFC],
    "st leonards":          [_W, _C, _A, _IC,  _HFC],
    "2064":                 [_W, _C, _A, _IC,  _HFC],
    "crows nest":           [_W, _C, _A, _IC,  _HFC],
    "wollstonecraft":       [_W, _C, _A, _IC,  _HFC],
    "naremburn":            [_W, _C, _A, _IC,  _HFC],
    "2065":                 [_W, _C, _A, _IC,  _HFC],
    # Lane Cove — nearest HF: Lane Cove
    "lane cove":            [_W, _C, _A, _HFL],
    "longueville":          [_W, _C, _A, _HFL],
    "2067":                 [_W, _C, _A, _HFL],
    # Mosman — nearest HF: Mosman
    "mosman":               [_W, _C, _A, _HFM],
    "2088":                 [_W, _C, _A, _HFM],
    # Neutral Bay / Kurraba — halfway between Cammeray & Mosman; use Cammeray
    "neutral bay":          [_W, _C, _A, _IM,  _HFC],
    "kurraba point":        [_W, _C, _A, _IM,  _HFC],
    "2090":                 [_W, _C, _A, _IM,  _HFC],

    # ── Upper North Shore ─────────────────────────────────────────────
    # Chatswood / Roseville — nearest HF: Lane Cove
    "chatswood":            [_W, _C, _A, _HFL],
    "willoughby":           [_W, _C, _A],
    "castle cove":          [_W, _C, _A],
    "2068":                 [_W, _C, _A, _HFL],
    "roseville":            [_W, _C, _A, _HFL],
    "lindfield":            [_W, _C, _A, _HFL],
    "2069":                 [_W, _C, _A, _HFL],
    "killara":              [_W, _C, _A],
    "gordon":               [_W, _C, _A],
    "pymble":               [_W, _C, _A],
    "2071":                 [_W, _C, _A],
    "turramurra":           [_W, _C, _A],
    "warrawee":             [_W, _C, _A],
    "2074":                 [_W, _C, _A],
    "wahroonga":            [_W, _C, _A],
    "2076":                 [_W, _C, _A],
    "hornsby":              [_W, _C, _A],
    "waitara":              [_W, _C, _A],
    "2077":                 [_W, _C, _A],
    "st ives":              [_W, _C, _A],
    "2075":                 [_W, _C, _A],

    # ── Northern Beaches — nearest HF: Mosman ─────────────────────────
    "manly":                [_W, _C, _A, _HFM],
    "fairlight":            [_W, _C, _A, _HFM],
    "2095":                 [_W, _C, _A, _HFM],
    "freshwater":           [_W, _C, _A, _HFM],
    "curl curl":            [_W, _C, _A],
    "2096":                 [_W, _C, _A, _HFM],
    "dee why":              [_W, _C, _A, _HFM],
    "2099":                 [_W, _C, _A, _HFM],
    "narraweena":           [_W, _C, _A],
    "brookvale":            [_W, _C, _A, _HFM],
    "2100":                 [_W, _C, _A, _HFM],
    "narrabeen":            [_W, _C, _A],
    "collaroy":             [_W, _C, _A],
    "2101":                 [_W, _C, _A],
    "avalon beach":         [_W, _C, _A],
    "avalon":               [_W, _C, _A],
    "bilgola":              [_W, _C, _A],
    "2107":                 [_W, _C, _A],
    "mona vale":            [_W, _C, _A],
    "2103":                 [_W, _C, _A],
    "frenchs forest":       [_W, _C, _A, _HFM],
    "2086":                 [_W, _C, _A, _HFM],

    # ── North West / Hills District ───────────────────────────────────
    "ryde":                 [_W, _C, _A],
    "west ryde":            [_W, _C, _A],
    "meadowbank":           [_W, _C, _A],
    "2112":                 [_W, _C, _A],
    "epping":               [_W, _C, _A],
    "2121":                 [_W, _C, _A],
    "carlingford":          [_W, _C, _A],
    "2118":                 [_W, _C, _A],
    "castle hill":          [_W, _C, _A],
    "2154":                 [_W, _C, _A],
    "baulkham hills":       [_W, _C, _A],
    "2153":                 [_W, _C, _A],
    "kellyville":           [_W, _C, _A],
    "2155":                 [_W, _C, _A],
    "norwest":              [_W, _C, _A],
    "bella vista":          [_W, _C, _A],

    # ── Parramatta / West ─────────────────────────────────────────────
    "parramatta":           [_W, _C, _A],
    "2150":                 [_W, _C, _A],
    "westmead":             [_W, _C, _A],
    "2145":                 [_W, _C, _A],
    "pendle hill":          [_W, _C, _A],
    "granville":            [_W, _C, _A],
    "2142":                 [_W, _C, _A],
    "auburn":               [_W, _C, _A],
    "2144":                 [_W, _C, _A],
    "merrylands":           [_W, _C, _A],
    "2160":                 [_W, _C, _A],
    "liverpool":            [_W, _C, _A],
    "2170":                 [_W, _C, _A],
    "campbelltown":         [_W, _C, _A],
    "2560":                 [_W, _C, _A],

    # ── Strathfield / Burwood / Inner West ────────────────────────────
    "strathfield":          [_W, _C, _A],
    "2135":                 [_W, _C, _A],
    "burwood":              [_W, _C, _A],
    "2134":                 [_W, _C, _A],
    "concord":              [_W, _C, _A],
    "2137":                 [_W, _C, _A],
    "homebush":             [_W, _C, _A],
    "homebush bay":         [_W, _C, _A],
    "2140":                 [_W, _C, _A],
    # Five Dock / Drummoyne — nearest HF: Broadway (Anzac Bridge)
    "five dock":            [_W, _C, _A, _HFB],
    "canada bay":           [_W, _C, _A],
    "2046":                 [_W, _C, _A, _HFB],
    "drummoyne":            [_W, _C, _A, _HFB],
    "2047":                 [_W, _C, _A, _HFB],

    # ── St George / Sutherland ────────────────────────────────────────
    "kogarah":              [_W, _C, _A],
    "2217":                 [_W, _C, _A],
    "hurstville":           [_W, _C, _A],
    "2220":                 [_W, _C, _A],
    "rockdale":             [_W, _C, _A],
    "2216":                 [_W, _C, _A],
    "brighton-le-sands":    [_W, _C, _A],
    "ramsgate":             [_W, _C, _A],
    "miranda":              [_W, _C, _A],
    "2228":                 [_W, _C, _A],
    "cronulla":             [_W, _C, _A],
    "2230":                 [_W, _C, _A],
    "sutherland":           [_W, _C, _A],
    "2232":                 [_W, _C, _A],

    # ── Chifley / South East ──────────────────────────────────────────
    "little bay":           [_W, _C, _A],
    "chifley":              [_W, _C, _A],
    "port botany":          [_W, _C, _A],

    # ── Newtown / Enmore adjacent — nearest HF: Broadway ─────────────
    "camperdown":           [_W, _C, _A, _HFB],
    "2050":                 [_W, _C, _A, _HFB],

}

# Sorted list of suburb names only (no postcodes), for reference
ALL_SUBURBS = sorted(
    {k for k in SUBURB_STORES if not k.isdigit()},
    key=str.lower,
)

# Mapping of postcode → primary suburb name(s) for display
POSTCODE_NAMES: dict[str, str] = {
    "2000": "Sydney CBD",
    "2007": "Pyrmont / Ultimo",
    "2009": "Pyrmont",
    "2010": "Surry Hills / Darlinghurst",
    "2015": "Alexandria / Green Square",
    "2016": "Redfern / Waterloo",
    "2017": "Waterloo / Zetland",
    "2018": "Mascot / Eastlakes",
    "2019": "Botany",
    "2021": "Paddington / Woollahra",
    "2022": "Bondi / Double Bay",
    "2024": "Waverley / Dover Heights",
    "2026": "Bondi Beach / Bronte",
    "2031": "Coogee / Randwick",
    "2032": "Kingsford / Kensington",
    "2035": "Maroubra",
    "2036": "La Perouse / Chifley",
    "2037": "Glebe / Forest Lodge",
    "2039": "Rozelle / Lilyfield",
    "2040": "Leichhardt / Annandale",
    "2041": "Balmain",
    "2042": "Newtown / Erskineville",
    "2044": "Enmore / St Peters",
    "2046": "Drummoyne",
    "2047": "Drummoyne",
    "2048": "Petersham / Stanmore",
    "2050": "Camperdown / Newtown",
    "2060": "North Sydney",
    "2061": "Milsons Point / Kirribilli",
    "2062": "Cammeray",
    "2063": "Cremorne",
    "2064": "Artarmon / St Leonards",
    "2065": "Crows Nest / Wollstonecraft",
    "2067": "Chatswood",
    "2068": "Lane Cove / Longueville",
    "2069": "Ryde / Meadowbank",
    "2071": "Killara / Gordon",
    "2074": "Pymble / Turramurra",
    "2075": "St Ives",
    "2076": "Hornsby / Waitara",
    "2077": "Asquith / Berowra",
    "2086": "Frenchs Forest / Forestville",
    "2088": "Mosman",
    "2090": "Neutral Bay / Cremorne",
    "2095": "Manly",
    "2096": "Dee Why / Brookvale",
    "2099": "Narrabeen / Collaroy",
    "2100": "Allambie Heights / Beacon Hill",
    "2101": "Mona Vale / Bayview",
    "2103": "Church Point / Scotland Island",
    "2107": "Palm Beach / Avalon",
    "2112": "Rhodes / Concord",
    "2118": "Cherrybrook / Pennant Hills",
    "2121": "Epping / Carlingford",
    "2131": "Ashfield / Summer Hill",
    "2134": "Burwood",
    "2135": "Strathfield",
    "2137": "Concord / Rhodes",
    "2140": "Homebush / Strathfield",
    "2142": "Auburn / Granville",
    "2144": "Auburn",
    "2145": "Westmead / Parramatta",
    "2150": "Parramatta",
    "2153": "Baulkham Hills",
    "2154": "Castle Hill / Kellyville",
    "2155": "Kellyville / Rouse Hill",
    "2160": "Merrylands / Granville",
    "2170": "Liverpool",
    "2204": "Marrickville / Dulwich Hill",
    "2216": "Rockdale / Arncliffe",
    "2217": "Kogarah / Carlton",
    "2220": "Hurstville",
    "2228": "Miranda / Caringbah",
    "2230": "Cronulla / Caringbah South",
    "2232": "Sutherland / Engadine",
    "2560": "Campbelltown",
}
