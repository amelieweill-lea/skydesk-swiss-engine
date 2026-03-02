from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import swisseph as swe
import datetime as dt
from typing import Dict, List, Any, Literal

app = FastAPI()

# -----------------------------
# CORS
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://starry-path-2026.lovable.app",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_origin_regex=r"https://.*\.lovable\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    ("mean_apog", swe.MEAN_APOG),
]

SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

ZodiacMode = Literal["tropical", "sidereal"]
SidMode = Literal["lahiri", "fagan_bradley"]


def sign_from_lon(lon: float) -> Dict[str, Any]:
    lon = lon % 360.0
    sign_index = int(lon // 30)
    deg_in_sign = lon - 30 * sign_index
    return {"sign": SIGNS[sign_index], "signIndex": sign_index, "degreeInSign": deg_in_sign}


def parse_date_yyyy_mm_dd(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def jd_at_00utc(d: dt.date) -> float:
    return swe.julday(d.year, d.month, d.day, 0.0)


def sid_mode_to_swe(mode: SidMode) -> int:
    if mode == "lahiri":
        return swe.SIDM_LAHIRI
    if mode == "fagan_bradley":
        return swe.SIDM_FAGAN_BRADLEY
    return swe.SIDM_LAHIRI


def calc_body(jd: float, body_id: int, zodiac: ZodiacMode, sid_mode: SidMode) -> Dict[str, Any]:
    flags = 0
    if zodiac == "sidereal":
        swe.set_sid_mode(sid_mode_to_swe(sid_mode), 0, 0)
        flags |= swe.FLG_SIDEREAL

    xx, _ = swe.calc_ut(jd, body_id, flags)
    lon, lat, dist, speed_lon, speed_lat, speed_dist = xx

    out = {
        "longitude": lon % 360.0,
        "latitude": lat,
        "distance": dist,
        "longitudeSpeed": speed_lon,
        "isRetrograde": speed_lon < 0,
    }
    out.update(sign_from_lon(lon))
    return out


def add_south_node(bodies: Dict[str, Any]) -> None:
    nn = bodies["true_node"]["longitude"]
    south_lon = (nn + 180.0) % 360.0
    bodies["south_node"] = {
        **sign_from_lon(south_lon),
        "longitude": south_lon,
        "derivedFrom": "true_node+180",
    }


def bodies_to_positions_list(bodies: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Liste itérable avec la clé "key" (sun, moon, etc.)
    out: List[Dict[str, Any]] = []
    for key, val in bodies.items():
        item = {"key": key}
        item.update(val)
        out.append(item)
    return out


@app.get("/api/health")
def health(
    zodiac: ZodiacMode = Query("tropical"),
    sid_mode: SidMode = Query("lahiri"),
):
    try:
        d = dt.date(2026, 1, 1)
        jd = jd_at_00utc(d)
        sun = calc_body(jd, swe.SUN, zodiac, sid_mode)
        return {
            "status": "ok",
            "engine": "swisseph-python",
            "zodiac": zodiac,
            "siderealMode": sid_mode if zodiac == "sidereal" else None,
            "sample": {"sun": {"longitude": sun["longitude"], "sign": sun["sign"]}},
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/api/positions")
def positions(
    date: str = Query(...),
    zodiac: ZodiacMode = Query("tropical"),
    sid_mode: SidMode = Query("lahiri"),
):
    d = parse_date_yyyy_mm_dd(date)
    jd = jd_at_00utc(d)

    bodies: Dict[str, Any] = {}
    for name, body_id in PLANETS:
        bodies[name] = calc_body(jd, body_id, zodiac, sid_mode)
    add_south_node(bodies)

    positions_list = bodies_to_positions_list(bodies)

    return {
        "status": "ok",
        "date": d.isoformat(),
        "jd": jd,
        "zodiac": zodiac,
        "siderealMode": sid_mode if zodiac == "sidereal" else None,
        "bodies": bodies,
        "positions": bodies,                 # accès direct positions.sun ✅
        "positionsList": positions_list,     # itérable ✅
    }


@app.get("/api/positions/range")
def positions_range(
    start: str = Query(...),
    end: str = Query(...),
    zodiac: ZodiacMode = Query("tropical"),
    sid_mode: SidMode = Query("lahiri"),
):
    d0 = parse_date_yyyy_mm_dd(start)
    d1 = parse_date_yyyy_mm_dd(end)
    if d1 < d0:
        return {"status": "error", "detail": "end must be >= start"}

    days_count = (d1 - d0).days + 1
    days: List[Dict[str, Any]] = []

    for i in range(days_count):
        d = d0 + dt.timedelta(days=i)
        jd = jd_at_00utc(d)

        bodies: Dict[str, Any] = {}
        for name, body_id in PLANETS:
            bodies[name] = calc_body(jd, body_id, zodiac, sid_mode)
        add_south_node(bodies)

        positions_list = bodies_to_positions_list(bodies)

        days.append({
            "date": d.isoformat(),
            "jd": jd,
            "bodies": bodies,
            "positions": bodies,               # accès direct ✅
            "positionsList": positions_list,   # itérable ✅
        })

    return {
        "status": "ok",
        "start": d0.isoformat(),
        "end": d1.isoformat(),
        "count": len(days),
        "days": days,
    }


# -----------------------------
# Compat endpoints for Lovable frontend
# -----------------------------
@app.get("/api/events")
def events(
    start: str = Query(None, description="YYYY-MM-DD (optional)"),
    end: str = Query(None, description="YYYY-MM-DD (optional)"),
):
    return {
        "status": "ok",
        "start": start,
        "end": end,
        "count": 0,
        "events": [],
    }


@app.get("/api/events/range")
def events_range(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
):
    return {
        "status": "ok",
        "start": start,
        "end": end,
        "count": 0,
        "events": [],
        "days": [],
    }
