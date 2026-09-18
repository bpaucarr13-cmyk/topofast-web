import rasterio
from pyproj import Geod

NODATA_VALUE = -9999.0
_GEOD = Geod(ellps="WGS84")


def utm_epsg_for_point(lon, lat):
    zone = int((lon + 180) // 6) + 1
    zone = min(max(zone, 1), 60)
    return (32600 if lat >= 0 else 32700) + zone


def raster_min_max_mean(path):
    with rasterio.open(path) as ds:
        band = ds.read(1, masked=True)
    return float(band.min()), float(band.max()), float(band.mean())


def raster_mean(path):
    with rasterio.open(path) as ds:
        band = ds.read(1, masked=True)
    return float(band.mean())


def polygon_area_m2(ring_lonlat):
    # ring_lonlat: lista de (lon, lat) del anillo exterior (rectángulo o
    # polígono dibujado). Geod.polygon_area_perimeter da el área geodésica
    # real sobre el elipsoide WGS84 — mismo resultado que QgsDistanceArea
    # con setEllipsoid("WGS84") en el plugin, sin depender de QGIS.
    lons = [p[0] for p in ring_lonlat]
    lats = [p[1] for p in ring_lonlat]
    area, _perimeter = _GEOD.polygon_area_perimeter(lons, lats)
    return abs(area)


def build_report(dem_path, slope_path, ring_lonlat, demtype, interval):
    vmin, vmax, vmean = raster_min_max_mean(dem_path)
    slope_mean = raster_mean(slope_path) if slope_path else None
    area_m2 = polygon_area_m2(ring_lonlat)

    centroid_lon = sum(p[0] for p in ring_lonlat) / len(ring_lonlat)
    centroid_lat = sum(p[1] for p in ring_lonlat) / len(ring_lonlat)
    epsg = utm_epsg_for_point(centroid_lon, centroid_lat)
    zone_number = epsg % 100
    hemisphere = "N" if epsg // 100 == 326 else "S"

    return {
        "elevation_min": round(vmin),
        "elevation_max": round(vmax),
        "elevation_mean": round(vmean),
        "slope_mean_deg": round(slope_mean, 1) if slope_mean is not None else None,
        "area_ha": round(area_m2 / 10000.0, 2),
        "area_km2": round(area_m2 / 1_000_000.0, 4),
        "utm_zone": f"{zone_number}{hemisphere}",
        "epsg": epsg,
        "demtype": demtype,
        "interval": interval,
    }
