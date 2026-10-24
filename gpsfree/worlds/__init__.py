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
