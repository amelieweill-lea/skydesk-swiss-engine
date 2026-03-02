from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import swisseph as swe
import datetime as dt
from typing import Dict, List, Any

app = FastAPI()

# CORS: autorise ton front publié
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://starry-path-2026.lovable.app"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Conventions: tropical, géocentrique, UT ---
# Swiss Ephemeris est tropical par défaut; on force quand même le mode au démarrage.
swe.set_sid_mode(swe.SIDM_FAGAN_BRADLEY, 0, 0)  # sans effet en tropical; safe
# Pas de set_topo -> géocentrique

PLANETS = [
    ("sun", swe.SUN),
    ("moon", swe.MOON),
    ("mercury", swe.MERCURY),
    ("venus", swe.VENUS),
    ("mars", swe.MARS),
    ("jupiter", swe.JUPITER),
    ("saturn", swe.SATURN),
    ("uranus", swe.URANUS),
    ("neptune", swe.NEPTUNE),
    ("pluto", swe.PLUTO),
    ("true_node", swe.TRUE_NODE),
    ("mean_apog", swe.MEAN_APOG),  # Lilith “moyenne”
]

SIGNS = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]

def sign_from_lon(lon: float) -> Dict[str, Any]:
    lon = lon % 360.0
    sign_index = int(lon // 30)
    deg_in_sign = lon - 30 * sign_index
    return {
        "sign": SIGNS[sign_index],
        "signIndex": sign_index,
        "degreeInSign": deg_in_sign,
    }

def parse_date_yyyy_mm_dd(s: str) -> dt.date:
    # attend "YYYY-MM-DD"
    return dt.datetime.strptime(s, "%Y-%m-%d").date()

def jd_at_00utc(d: dt.date) -> float:
    # 00:00 UTC
    return swe.julday(d.year, d.month, d.day, 0.0)

def calc_body(jd: float, body_id: int) -> Dict[str, Any]:
    # calc_ut renvoie (xx, retflag) où xx = [lon, lat, dist, speed_lon, speed_lat, speed_dist]
    xx, _ = swe.calc_ut(jd, body_id)
    lon, lat, dist, speed_lon, speed_lat, speed_dist = xx
    s = sign_from_lon(lon)
    return {
        "longitude": lon % 360.0,
        "latitude": lat,
        "distance": dist,
        "longitudeSpeed": speed_lon,
        "isRetrograde": speed_lon < 0,
        **s,
    }

@app.get("/api/health")
def health():
    try:
        d = dt.date(2026, 1, 1)
        jd = jd_at_00utc(d)
        sun = calc_body(jd, swe.SUN)
        moon = calc_body(jd, swe.MOON)
        merc = calc_body(jd, swe.MERCURY)
        return {
            "status": "ok",
            "engine": "swisseph-python",
            "testDateUTC": "2026-01-01T00:00:00Z",
            "sample": {
                "sun": {"lon": sun["longitude"], "speed": sun["longitudeSpeed"], "sign": sun["sign"]},
                "moon": {"lon": moon["longitude"], "speed": moon["longitudeSpeed"], "sign": moon["sign"]},
                "mercury": {"lon": merc["longitude"], "speed": merc["longitudeSpeed"], "sign": merc["sign"]},
            }
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.get("/api/positions")
def positions(date: str = Query(..., description="YYYY-MM-DD (UTC, 00:00)")):
    """
    Positions à 00:00 UTC pour une date donnée.
    """
    d = parse_date_yyyy_mm_dd(date)
    jd = jd_at_00utc(d)

    out = {"date": d.isoformat(), "jd": jd, "bodies": {}}
    for name, body_id in PLANETS:
        out["bodies"][name] = calc_body(jd, body_id)

    # Nœud Sud = Nœud Nord + 180°
    nn = out["bodies"]["true_node"]["longitude"]
    out["bodies"]["south_node"] = {
        **sign_from_lon((nn + 180.0) % 360.0),
        "longitude": (nn + 180.0) % 360.0,
        "derivedFrom": "true_node+180",
    }
    return out

@app.get("/api/positions/range")
def positions_range(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
):
    """
    Positions quotidiennes à 00:00 UTC, start..end inclus.
    Aucune interpolation.
    """
    d0 = parse_date_yyyy_mm_dd(start)
    d1 = parse_date_yyyy_mm_dd(end)
    if d1 < d0:
        return {"status": "error", "detail": "end must be >= start"}

    days = (d1 - d0).days + 1
    data: List[Dict[str, Any]] = []

    for i in range(days):
        d = d0 + dt.timedelta(days=i)
        jd = jd_at_00utc(d)
        row = {"date": d.isoformat(), "jd": jd, "bodies": {}}
        for name, body_id in PLANETS:
            row["bodies"][name] = calc_body(jd, body_id)

        nn = row["bodies"]["true_node"]["longitude"]
        row["bodies"]["south_node"] = {
            **sign_from_lon((nn + 180.0) % 360.0),
            "longitude": (nn + 180.0) % 360.0,
            "derivedFrom": "true_node+180",
        }
        data.append(row)

    return {
        "status": "ok",
        "start": d0.isoformat(),
        "end": d1.isoformat(),
        "step": "1d@00:00Z",
        "count": len(data),
        "data": data,
    }
