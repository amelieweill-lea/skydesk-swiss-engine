from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import swisseph as swe
import datetime as dt
from typing import Dict, List, Any, Optional, Literal

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

ZodiacMode = Literal["tropical", "sidereal"]
SidMode = Literal["fagan_bradley"]  # extensible plus tard


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
    # On peut ajouter d’autres modes ici plus tard
    if mode == "fagan_bradley":
        return swe.SIDM_FAGAN_BRADLEY
    return swe.SIDM_FAGAN_BRADLEY


def calc_body(
    jd: float,
    body_id: int,
    zodiac: ZodiacMode = "tropical",
    sid_mode: SidMode = "fagan_bradley",
) -> Dict[str, Any]:
    """
    Calcule une position à jd (UT), en tropical ou sidéral.

    Important:
    - Tropical: flags = 0 (défaut).
    - Sidéral: on met le mode sidéral + le flag SEFLG_SIDEREAL.
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
    bodies["south_node"] = {
        **sign_from_lon((nn + 180.0) % 360.0),
        "longitude": (nn + 180.0) % 360.0,
        "derivedFrom": "true_node+180",
    }


@app.get("/api/health")
def health(
    zodiac: ZodiacMode = Query("tropical", description="tropical | sidereal"),
    sid_mode: SidMode = Query("fagan_bradley", description="sidereal mode (if zodiac
