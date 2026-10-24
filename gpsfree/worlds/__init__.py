# World catalogue. Adding a world = one entry here + `gpsfree fetch <id>`.
# Local frame for everything downstream: ENU meters, x = east, y = north, z = up,
# origin at (lat, lon) with z = 0 at ground level there.
WORLDS = {
    "yosemite": {
        "kind": "terrain",
        "name": "Yosemite Valley (terrain)",
        "lat": 37.742, "lon": -119.585, "radius": 5000,
        "attribution": "Elevation: AWS Terrain Tiles (Mapzen, USGS et al.) · Imagery: Esri, Maxar, Earthstar Geographics",
    },
    "amsterdam": {
        "kind": "city",
        "name": "Amsterdam (city)",
        "lat": 52.3731, "lon": 4.8926, "radius": 2500,
        "attribution": "Buildings: 3DBAG by TU Delft & 3DGI (CC BY 4.0)",
    },
    "rotterdam": {
        "kind": "city",
        "name": "Rotterdam (city)",
        "lat": 51.918, "lon": 4.48, "radius": 2500,
        "attribution": "Buildings: 3DBAG by TU Delft & 3DGI (CC BY 4.0)",
    },
}
