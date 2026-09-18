import json
import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

import dem as dem_mod
import processing
import styling
import report as report_mod
import landxml as landxml_mod
import jobs
import ratelimit

app = FastAPI(title="TopoFast Web")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


class GenerateRequest(BaseModel):
    mode: str  # "rect" | "polygon"
    bounds: Optional[dict] = None  # {min_lon, min_lat, max_lon, max_lat}
    polygon: Optional[list] = None  # [[lon, lat], ...] anillo exterior
    api_key: str
    demtype: str
    interval: float
    intermediate_contours: bool = False
    intermediate_interval: float = 2.0
    fill_voids: bool = True


class ExportDxfRequest(BaseModel):
    dxf_mode: str = "3D"  # "2D" | "3D"


def _manifest_path(job_dir):
    return os.path.join(job_dir, "manifest.json")


def _load_manifest(job_id):
    job_dir = jobs.job_dir_for(job_id)
    path = _manifest_path(job_dir)
    if not os.path.exists(path):
        raise HTTPException(404, "Job no encontrado o expirado.")
    with open(path, "r", encoding="utf-8") as f:
        return job_dir, json.load(f)


def _ring_from_request(req: GenerateRequest):
    if req.mode == "polygon":
        if not req.polygon or len(req.polygon) < 3:
            raise HTTPException(400, "Falta el polígono de selección.")
        return req.polygon
    if not req.bounds:
        raise HTTPException(400, "Falta el rectángulo de selección.")
    b = req.bounds
    return [
        (b["min_lon"], b["min_lat"]),
        (b["max_lon"], b["min_lat"]),
        (b["max_lon"], b["max_lat"]),
        (b["min_lon"], b["max_lat"]),
        (b["min_lon"], b["min_lat"]),
    ]


def _run_generate(req: GenerateRequest):
    ring = _ring_from_request(req)
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    jobs.check_area_size(min_lon, min_lat, max_lon, max_lat)

    jobs.cleanup_old_jobs()
    job_id, job_dir = jobs.new_job_dir()

    dem_raw = os.path.join(job_dir, "dem_raw.tif")
    dem_mod.download_dem(min_lon, min_lat, max_lon, max_lat, req.demtype, req.api_key, dem_raw)

    dem_tagged = os.path.join(job_dir, "dem_tagged.tif")
    processing.tag_nodata(dem_raw, dem_tagged)
    os.remove(dem_raw)
    current_dem = dem_tagged

    void_warning = None
    frac = styling.void_fraction(current_dem)
    if frac > 0.1:
        void_warning = (
            f"El {frac * 100:.0f}% del área no tiene datos de elevación (vacíos del "
            "DEM, típico en glaciares/nieve). Si necesitás cobertura completa probá "
            "con el modelo Copernicus GLO-30 (COP30)."
        )

    if req.fill_voids:
        dem_filled = os.path.join(job_dir, "dem_filled.tif")
        processing.fill_nodata(current_dem, dem_filled)
        os.remove(current_dem)
        current_dem = dem_filled

    dem_for_slope = current_dem

    if req.mode == "polygon":
        polygon_geojson = os.path.join(job_dir, "selection_mask.geojson")
        with open(polygon_geojson, "w", encoding="utf-8") as f:
            json.dump({
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature", "properties": {},
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                }],
            }, f)
        dem_clipped = os.path.join(job_dir, "dem_clipped.tif")
        processing.clip_to_polygon(current_dem, dem_clipped, polygon_geojson)
        current_dem = dem_clipped

    final_dem_path = os.path.join(job_dir, "dem.tif")
    if current_dem != final_dem_path:
        os.replace(current_dem, final_dem_path)

    generation_interval = req.intermediate_interval if req.intermediate_contours else req.interval
    contours_path = os.path.join(job_dir, "contours.geojson")
    processing.generate_contours_geojson(final_dem_path, contours_path, generation_interval)

    if req.intermediate_contours:
        contours_data = styling.classify_master_contours(contours_path, req.interval)
    else:
        with open(contours_path, "r", encoding="utf-8") as f:
            contours_data = json.load(f)

    dem_png_path = os.path.join(job_dir, "dem.png")
    dem_bounds = styling.render_dem_png(final_dem_path, dem_png_path)

    slope_path = os.path.join(job_dir, "slope.tif")
    try:
        processing.slope(dem_for_slope, slope_path)
    except processing.GdalError:
        slope_path = None

    report_data = report_mod.build_report(
        final_dem_path, slope_path, ring, req.demtype, req.interval
    )
    if slope_path and os.path.exists(slope_path):
        os.remove(slope_path)

    manifest = {
        "dem_path": final_dem_path,
        "contour_geojson_path": contours_path,
        "epsg": report_data["epsg"],
    }
    with open(_manifest_path(job_dir), "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    return {
        "job_id": job_id,
        "contours": contours_data,
        "intermediate_contours": req.intermediate_contours,
        "dem_png_url": f"/api/jobs/{job_id}/dem.png",
        "dem_tif_url": f"/api/jobs/{job_id}/dem.tif",
        "contours_url": f"/api/jobs/{job_id}/contours.geojson",
        "dem_bounds": dem_bounds,
        "report": report_data,
        "void_warning": void_warning,
    }


@app.post("/api/generate", dependencies=[Depends(ratelimit.enforce)])
async def generate(req: GenerateRequest):
    try:
        return await run_in_threadpool(_run_generate, req)
    except (dem_mod.DemDownloadError, processing.GdalError, ValueError) as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/jobs/{job_id}/dem.png")
def get_dem_png(job_id: str):
    job_dir, _ = _load_manifest(job_id)
    return FileResponse(os.path.join(job_dir, "dem.png"), media_type="image/png")


@app.get("/api/jobs/{job_id}/dem.tif")
def get_dem_tif(job_id: str):
    job_dir, manifest = _load_manifest(job_id)
    return FileResponse(manifest["dem_path"], filename="topofast_dem.tif")


@app.get("/api/jobs/{job_id}/contours.geojson")
def get_contours(job_id: str):
    job_dir, manifest = _load_manifest(job_id)
    return FileResponse(manifest["contour_geojson_path"], filename="topofast_curvas.geojson")


@app.post("/api/jobs/{job_id}/export/dxf")
async def export_dxf(job_id: str, req: ExportDxfRequest):
    job_dir, manifest = _load_manifest(job_id)

    def _do():
        dxf_path = os.path.join(job_dir, "curvas_nivel.dxf")
        processing.contours_to_dxf(
            manifest["contour_geojson_path"], dxf_path, manifest["epsg"], req.dxf_mode == "3D"
        )
        return dxf_path

    try:
        dxf_path = await run_in_threadpool(_do)
    except processing.GdalError as exc:
        raise HTTPException(400, str(exc))
    return FileResponse(dxf_path, filename="topofast_curvas.dxf")


@app.post("/api/jobs/{job_id}/export/landxml")
async def export_landxml(job_id: str):
    job_dir, manifest = _load_manifest(job_id)

    def _do():
        utm_dem_path = os.path.join(job_dir, "dem_utm.tif")
        processing.warp_to_epsg(manifest["dem_path"], utm_dem_path, manifest["epsg"])
        xml_path = os.path.join(job_dir, "superficie.xml")
        landxml_mod.build_landxml(utm_dem_path, xml_path)
        os.remove(utm_dem_path)
        return xml_path

    try:
        xml_path = await run_in_threadpool(_do)
    except (processing.GdalError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    return FileResponse(xml_path, filename="topofast_superficie.xml")


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
