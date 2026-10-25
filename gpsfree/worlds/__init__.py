# World catalogue. Adding a world = one entry here + `gpsfree fetch <id>`.
# Local frame for everything downstream: ENU meters, x = east, y = north, z = up,
# origin at (lat, lon) with z = 0 at ground level there.
#
# kind      "terrain": elevation tiles (+ optional OpenStreetMap layers); "city": 3DBAG buildings (NL only)
# layers    Overture layers baked into the TRUE world: "buildings", "forest" (pinned release, worlds/overture.py)
# trees     how forest cover becomes tree meshes: forest canopy cover, extra scattered trees per hectare,
#           height and crown radius ranges (m)
# sea_level clamp terrain to >= 0 m so the sea is a flat surface instead of the seabed
TERRAIN = "Elevation: AWS Terrain Tiles (Mapzen, SRTM, GEBCO et al.) · Imagery: Esri, Maxar, Earthstar Geographics"
OSM = " · Buildings: Overture Maps / © OpenStreetMap contributors (ODbL) · Forest: ESA WorldCover via Overture (CC BY 4.0)"
BOREAL = {"forest_cover": 0.6, "scatter_per_ha": 0.5, "height_m": [12, 26], "crown_r_m": [1.8, 3.2]}

WORLDS = {
    "yosemite": {"kind": "terrain", "name": "Yosemite Valley, US", "lat": 37.742, "lon": -119.585, "radius": 3000,
                 "attribution": TERRAIN},
    "rotterdam": {"kind": "city", "name": "Rotterdam, NL", "lat": 51.918, "lon": 4.48, "radius": 2500,
                  "attribution": "Buildings: 3DBAG by TU Delft & 3DGI (CC BY 4.0)"},
    "pallas": {"kind": "terrain", "name": "Pallas fells, Lapland FI", "lat": 68.045, "lon": 24.07, "radius": 3000,
               "layers": ["buildings", "forest"], "attribution": TERRAIN + OSM,
               "trees": {"forest_cover": 0.35, "scatter_per_ha": 1.0, "height_m": [4, 12], "crown_r_m": [1.2, 2.5]}},
    "repovesi": {"kind": "terrain", "name": "Repovesi forest hills, Kouvola FI", "lat": 61.19, "lon": 26.88, "radius": 2500,
                 "layers": ["buildings", "forest"], "attribution": TERRAIN + OSM, "trees": BOREAL},
    "kotka": {"kind": "terrain", "name": "Kotka archipelago, Gulf of Finland FI", "lat": 60.40, "lon": 26.97, "radius": 3000,
              "layers": ["buildings", "forest"], "attribution": TERRAIN + OSM, "trees": BOREAL, "sea_level": True},
    "tampere": {"kind": "terrain", "name": "Tampere city, FI", "lat": 61.4978, "lon": 23.761, "radius": 2500,
                "layers": ["buildings", "forest"], "attribution": TERRAIN + OSM,
                "trees": {"forest_cover": 0.5, "scatter_per_ha": 2.0, "height_m": [8, 22], "crown_r_m": [2, 4]}},
    "imatra": {"kind": "terrain", "name": "Imatra border town, FI", "lat": 61.193, "lon": 28.775, "radius": 2500,
               "layers": ["buildings", "forest"], "attribution": TERRAIN + OSM, "trees": BOREAL},
    "kyiv": {"kind": "terrain", "name": "Kyiv city centre, UA", "lat": 50.4501, "lon": 30.5234, "radius": 2500,
             "layers": ["buildings", "forest"], "attribution": TERRAIN + OSM,
             "trees": {"forest_cover": 0.5, "scatter_per_ha": 3.0, "height_m": [10, 25], "crown_r_m": [2.5, 5]}},
    "steppe": {"kind": "terrain", "name": "Steppe fields, Poltava region UA", "lat": 49.45, "lon": 35.13, "radius": 3000,
               "layers": ["buildings", "forest"], "attribution": TERRAIN + OSM,
               "trees": {"forest_cover": 0.5, "scatter_per_ha": 0.2, "height_m": [10, 22], "crown_r_m": [2.5, 4.5]}},
    "vinnytsia": {"kind": "terrain", "name": "Farmland and villages, Vinnytsia region UA", "lat": 49.02, "lon": 28.40, "radius": 3000,
                  "layers": ["buildings", "forest"], "attribution": TERRAIN + OSM,
                  "trees": {"forest_cover": 0.5, "scatter_per_ha": 0.5, "height_m": [10, 24], "crown_r_m": [2.5, 4.5]}},
    "carpathians": {"kind": "terrain", "name": "Forested Carpathians near Vorokhta, UA", "lat": 48.30, "lon": 24.45, "radius": 3000,
                    "layers": ["buildings", "forest"], "attribution": TERRAIN + OSM,
                    "trees": {"forest_cover": 0.65, "scatter_per_ha": 0.5, "height_m": [15, 32], "crown_r_m": [1.8, 3.2]}},
    "namib": {"kind": "terrain", "name": "Namib dunes near Sossusvlei, NA", "lat": -24.75, "lon": 15.35, "radius": 3000,
              "attribution": TERRAIN},
}

# Flat lowlands for the path-planning study: 15 x 15 km, 7.5 m grid from zoom-15 tiles, no imagery.
LOWLAND = {"forest_cover": 0.5, "scatter_per_ha": 0.5, "height_m": [10, 24], "crown_r_m": [2.5, 4.5]}
FLAT = [  # id, name, lat, lon, trees, sea_level
    ("kherson_plain", "Kherson plain, UA", 46.75, 32.90, LOWLAND, False),
    ("mykolaiv_fields", "Mykolaiv fields, UA", 47.05, 31.80, LOWLAND, False),
    ("odesa_steppe", "Odesa steppe, UA", 46.80, 30.60, LOWLAND, False),
    ("zaporizhzhia_fields", "Zaporizhzhia fields, UA", 47.60, 35.50, LOWLAND, False),
    ("dnipro_fields", "Dnipro fields, UA", 48.30, 35.20, LOWLAND, False),
    ("kryvyi_rih_steppe", "Kryvyi Rih steppe, UA", 47.80, 33.60, LOWLAND, False),
    ("kharkiv_plain", "Kharkiv plain, UA", 49.80, 36.60, LOWLAND, False),
    ("poltava_fields", "Poltava fields, UA", 49.70, 34.40, LOWLAND, False),
    ("sumy_fields", "Sumy fields, UA", 50.80, 34.60, LOWLAND, False),
    ("chernihiv_plain", "Chernihiv plain, UA", 51.40, 31.50, LOWLAND, False),
    ("kyiv_polissia", "Kyiv Polissia, UA", 50.70, 30.10, LOWLAND, False),
    ("zhytomyr_fields", "Zhytomyr fields, UA", 50.20, 28.90, LOWLAND, False),
    ("cherkasy_fields", "Cherkasy fields, UA", 49.30, 31.60, LOWLAND, False),
    ("kropyvnytskyi_steppe", "Kropyvnytskyi steppe, UA", 48.40, 32.40, LOWLAND, False),
    ("uman_fields", "Uman fields, UA", 48.80, 30.30, LOWLAND, False),
    ("khmelnytskyi_fields", "Khmelnytskyi fields, UA", 49.50, 26.80, LOWLAND, False),
    ("rivne_plain", "Rivne plain, UA", 50.70, 26.30, LOWLAND, False),
    ("volyn_plain", "Volyn plain, UA", 50.90, 25.00, LOWLAND, False),
    ("melitopol_steppe", "Melitopol steppe, UA", 46.95, 35.20, LOWLAND, False),
    ("kremenchuk_fields", "Kremenchuk fields, UA", 49.10, 33.60, LOWLAND, False),
    ("seinajoki_fields", "Seinajoki fields, FI", 62.85, 22.70, BOREAL, False),
    ("vaasa_coast", "Vaasa coast, FI", 63.05, 21.80, BOREAL, True),
    ("kokkola_plain", "Kokkola plain, FI", 63.75, 23.30, BOREAL, True),
    ("oulu_plain", "Oulu plain, FI", 64.85, 25.60, BOREAL, True),
    ("pori_fields", "Pori fields, FI", 61.45, 21.90, BOREAL, True),
    ("turku_archipelago", "Turku archipelago, FI", 60.25, 21.80, BOREAL, True),
    ("aland", "Aland islands, FI", 60.15, 19.95, BOREAL, True),
    ("hanko_coast", "Hanko coast, FI", 59.85, 23.20, BOREAL, True),
    ("porvoo_coast", "Porvoo coast, FI", 60.35, 25.80, BOREAL, True),
    ("loimaa_fields", "Loimaa fields, FI", 60.85, 23.10, BOREAL, False),
    ("lapua_fields", "Lapua fields, FI", 63.00, 23.10, BOREAL, False),
    ("ilmajoki_fields", "Ilmajoki fields, FI", 62.73, 22.55, BOREAL, False),
    ("parnu_lowland", "Parnu lowland, EE", 58.45, 24.60, BOREAL, True),
    ("tartu_plain", "Tartu plain, EE", 58.35, 26.90, BOREAL, False),
    ("saaremaa", "Saaremaa, EE", 58.35, 22.60, BOREAL, True),
    ("jelgava_plain", "Jelgava plain, LV", 56.60, 23.70, LOWLAND, False),
    ("siauliai_plain", "Siauliai plain, LT", 55.85, 23.20, LOWLAND, False),
    ("panevezys_plain", "Panevezys plain, LT", 55.70, 24.40, LOWLAND, False),
    ("mazovia_plain", "Mazovia plain, PL", 52.50, 20.60, LOWLAND, False),
    ("kujawy_fields", "Kujawy fields, PL", 52.70, 18.40, LOWLAND, False),
    ("wielkopolska_fields", "Wielkopolska fields, PL", 52.20, 17.00, LOWLAND, False),
    ("lodz_fields", "Lodz fields, PL", 51.60, 19.30, LOWLAND, False),
    ("lublin_fields", "Lublin fields, PL", 51.20, 22.90, LOWLAND, False),
    ("flevoland", "Flevoland polders, NL", 52.50, 5.60, LOWLAND, False),
    ("friesland", "Friesland, NL", 53.10, 5.80, LOWLAND, False),
    ("lolland", "Lolland, DK", 54.80, 11.40, LOWLAND, True),
    ("alfold", "Great Hungarian Plain, HU", 46.90, 20.30, LOWLAND, False),
    ("baragan", "Baragan plain, RO", 44.60, 27.00, LOWLAND, False),
    ("skane_plain", "Skane plain, SE", 55.65, 13.40, LOWLAND, False),
    ("nordfriesland", "Nordfriesland marsh, DE", 54.60, 8.95, LOWLAND, True),
]
for _id, _name, _lat, _lon, _trees, _sea in FLAT:
    WORLDS[_id] = {"kind": "terrain", "name": _name, "lat": _lat, "lon": _lon, "radius": 7500, "elev_zoom": 15,
                   "step_m": 7.5, "imagery": False, "despike_m": 30, "layers": ["buildings", "forest"], "trees": _trees,
                   "attribution": TERRAIN + OSM, **({"sea_level": True} if _sea else {})}
FLAT_IDS = [f[0] for f in FLAT]
