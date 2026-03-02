from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import swisseph as swe
import datetime

app = FastAPI()

# ⚠️ Autorise ton frontend Lovable
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://starry-path-2026.lovable.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health():
    try:
        # 1er janvier 2026 à 00:00 UTC
        dt = datetime.datetime(2026, 1, 1, 0, 0)
        jd = swe.julday(dt.year, dt.month, dt.day, 0.0)

        lon, lat, dist, speed_lon, speed_lat, speed_dist = swe.calc_ut(jd, swe.SUN)[0]

        return {
            "status": "ok",
            "engine": "swisseph-python",
            "sun_longitude": lon,
            "sun_speed": speed_lon
        }

    except Exception as e:
        return {"status": "error", "detail": str(e)}

