from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import swisseph as swe
import datetime as dt
from typing import Dict, List, Any, Literal

app = FastAPI()

# --- CORS ---
# Lovable peut servir depuis différents sous-domaines (preview, etc.)
# + support local dev
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

# --- Conventions: géocentrique, UT ---
# Tropical = par défaut dans Swiss Ephemeris.
# Pas de set_topo => géocentrique.
# UT via calc_ut

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

SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

ZodiacMode = Literal["tropical", "sidereal"]
SidMode = Literal["lahiri", "fagan_bradley"]


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
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def jd_at_00utc(d: dt.date) -> float:
    # 00:00 UTC
    return swe.julday(d.year, d.month, d.day, 0.0)


def sid_mode_to_swe(mode: SidMode) -> int:
    if mode == "lahiri":
        return swe.SIDM_LAHIRI
    if mode == "fagan_bradley":
        return swe.SIDM_FAGAN_BRADLEY
    # fallback safe
    return swe.SIDM_LAHIRI


def calc_body(
    jd: float,
    body_id: int,
    zodiac: ZodiacMode = "tropical",
    sid_mode: SidMode = "lahiri",
) -> Dict[str, Any]:
    """
    Calcule une position à jd (UT), en tropical ou sidéral.

    - Tropical: flags = 0 (défaut).
    - Sidéral: on set le mode sidéral + FLG_SIDEREAL.
    """
    flags = 0

    if zodiac == "sidereal":
        swe.set_sid_mode(sid_mode_to_swe(sid_mode), 0, 0)
        flags |= swe.FLG_SIDEREAL

    xx, _ = swe.calc_ut(jd, body_id, flags)
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


def add_south_node(bodies: Dict[str, Any]) -> None:
    # Nœud Sud = Nœud Nord + 180°
    nn = bodies["true_node"]["longitude"]
    south_lon = (nn + 180.0) % 360.0
    bodies["south_node"] = {
        **sign_from_lon(south_lon),
        "longitude": south_lon,
        "derivedFrom": "true_node+180",
    }


@app.get("/api/health")
def health(
    zodiac: ZodiacMode = Query("tropical", description="tropical | sidereal"),
    sid_mode: SidMode = Query("lahiri", description="sidereal mode (lahiri | fagan_bradley)"),
):
    try:
        d = dt.date(2026, 1, 1)
        jd = jd_at_00utc(d)
        sun = calc_body(jd, swe.SUN, zodiac=zodiac, sid_mode=sid_mode)

        return {
            "status": "ok",
            "engine": "swisseph-python",
            "zodiac": zodiac,
            "siderealMode": sid_mode if zodiac == "sidereal" else None,
            "testDateUTC": "2026-01-01T00:00:00Z",
            "sample": {
                "sun": {"lon": sun["longitude"], "speed": sun["longitudeSpeed"], "sign": sun["sign"]}
            },
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/api/positions")
def positions(
    date: str = Query(..., description="YYYY-MM-DD (UTC, 00:00)"),
    zodiac: ZodiacMode = Query("tropical", description="tropical | sidereal"),
    sid_mode: SidMode = Query("lahiri", description="sidereal mode (lahiri | fagan_bradley)"),
):
    d = parse_date_yyyy_mm_dd(date)
    jd = jd_at_00utc(d)

    out = {
        "status": "ok",
        "date": d.isoformat(),
        "jd": jd,
        "zodiac": zodiac,
        "siderealMode": sid_mode if zodiac == "sidereal" else None,
        "bodies": {},
    }

    for name, body_id in PLANETS:
        out["bodies"][name] = calc_body(jd, body_id, zodiac=zodiac, sid_mode=sid_mode)

    add_south_node(out["bodies"])
    return out


@app.get("/api/positions/range")
def positions_range(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    zodiac: ZodiacMode = Query("tropical", description="tropical | sidereal"),
    sid_mode: SidMode = Query("lahiri", description="sidereal mode (lahiri | fagan_bradley)"),
):
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
            row["bodies"][name] = calc_body(jd, body_id, zodiac=zodiac, sid_mode=sid_mode)

        add_south_node(row["bodies"])
        data.append(row)

    return {
        "status": "ok",
        "start": d0.isoformat(),
        "end": d1.isoformat(),
        "step": "1d@00:00Z",
        "count": len(data),
        "zodiac": zodiac,
        "siderealMode": sid_mode if zodiac == "sidereal" else None,
        "data": data,
    }
