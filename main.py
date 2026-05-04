"""
Generador de webs por anfitrión — versión agnóstica de ciudad.

Flujo:
  Tally → Google Sheet → main.py:
    1. Lee última fila (un anfitrión, N propiedades)
    2. Para cada propiedad:
       a. Geocoding de la dirección → ciudad, barrio, lat/lng, región
       b. Places nearby por categoría (atracciones, restaurantes,
          cafés, cervecerías, supermercados, salir nocturno)
       c. Parser de las recomendaciones que cargó el anfitrión
       d. Convierte links de YouTube/Drive/Photos a embebibles
    3. Gemini: marca, welcome multi-idioma, tips locales, descripción
       de cada lugar en ES/EN/PT
    4. Render template_maestro.html con Jinja2 → sites/<slug-anfitrion>/index.html
    5. Email al anfitrión con el link

Pedro Volpacchio · Bariloche Experiencias
"""

from __future__ import annotations

import json
import os
import re
import smtplib
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse

import google.generativeai as genai
import googlemaps
import gspread
from jinja2 import Environment, FileSystemLoader
from oauth2client.service_account import ServiceAccountCredentials
from slugify import slugify

# ============================================================
# CONFIG
# ============================================================
# Nota: aceptamos múltiples nombres de variable para compatibilidad
# con secrets ya existentes en GitHub.
SHEET_ID = os.environ.get("SPREADSHEET_ID") or os.environ["SHEET_ID"]
GMAPS_API_KEY = os.environ["GOOGLE_MAPS_API_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASS = os.environ["EMAIL_PASS"]
WORKSHEET_NAME = os.environ.get("WORKSHEET_NAME", "Sheet1")
GITHUB_PAGES_BASE = (
    os.environ.get("SITE_BASE_URL")
    or os.environ.get("GITHUB_PAGES_BASE")
    or "https://USUARIO.github.io/bariloche-experiencias"
).rstrip("/")

CREDENTIALS_PATH = Path("credentials.json")
TEMPLATE_BARILOCHE = "template_bariloche.html"
TEMPLATE_GENERICO = "template_generico.html"
OUTPUT_DIR = Path("sites")
MAX_PROPIEDADES = 10

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


# ============================================================
# 1. CREDENCIALES (en runtime desde Secret)
# ============================================================
def build_credentials() -> None:
    """Reconstruye credentials.json desde el secret. Acepta dos formatos:
    - GOOGLE_CREDENTIALS_JSON: el JSON completo en plain text
    - GOOGLE_CREDENTIALS_JSON_B64: el JSON codificado en base64 (más seguro)
    """
    if CREDENTIALS_PATH.exists():
        return
    # Probar primero el formato base64 (el que tiene Pedro)
    b64 = os.environ.get("GOOGLE_CREDENTIALS_JSON_B64", "").strip()
    if b64:
        import base64
        try:
            decoded = base64.b64decode(b64).decode("utf-8")
            CREDENTIALS_PATH.write_text(decoded, encoding="utf-8")
            return
        except Exception as e:
            print(f"⚠️  Error decodificando GOOGLE_CREDENTIALS_JSON_B64: {e}")
    # Fallback al formato plain text
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip()
    if raw:
        CREDENTIALS_PATH.write_text(raw, encoding="utf-8")


# ============================================================
# 2. GOOGLE SHEETS
# ============================================================
def conectar_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(str(CREDENTIALS_PATH), scope)
    return gspread.authorize(creds).open_by_key(SHEET_ID).worksheet(WORKSHEET_NAME)


def leer_ultima_fila(sheet) -> dict[str, Any]:
    rows = sheet.get_all_records()
    if not rows:
        raise ValueError("Hoja vacía.")
    return rows[-1]


def get_field(row: dict, *names: str, default: str = "") -> str:
    """Devuelve el primer campo que matchee (acepta variantes de naming)."""
    for n in names:
        v = row.get(n)
        if v not in (None, ""):
            return str(v).strip()
    return default


# ============================================================
# 3. CONVERSIÓN DE LINKS DE VIDEO
# ============================================================
def normalize_video(url: str) -> dict:
    """Devuelve {kind, embed_url, raw_url, message}.

    kind ∈ { 'youtube', 'drive', 'photos', 'iframe', 'none' }
    
    Notas importantes:
    - YouTube: embebe perfecto (recomendado: subir como "No listado" para privacidad)
    - Drive: embebe perfecto si está compartido como "Cualquiera con el link"
    - Google Photos: NO se puede embeber (Google lo bloquea con X-Frame-Options).
      Solo se puede abrir en pestaña aparte. Se le avisa al anfitrión.
    """
    if not url:
        return {"kind": "none", "embed_url": "", "raw_url": "", "message": ""}
    raw = url.strip()

    # YouTube / Shorts (cualquier formato: youtu.be/X, youtube.com/watch?v=X, /shorts/X, /embed/X)
    if "youtube.com" in raw or "youtu.be" in raw:
        vid = ""
        if "v=" in raw:
            vid = parse_qs(urlparse(raw).query).get("v", [""])[0]
        elif "/shorts/" in raw:
            vid = raw.split("/shorts/")[-1].split("?")[0].split("/")[0]
        elif "/embed/" in raw:
            vid = raw.split("/embed/")[-1].split("?")[0].split("/")[0]
        else:
            vid = raw.rstrip("/").split("/")[-1].split("?")[0]
        if vid:
            return {
                "kind": "youtube",
                "embed_url": f"https://www.youtube.com/embed/{vid}",
                "raw_url": raw,
                "message": "",
            }

    # Google Drive (formatos: /file/d/ID/view, /open?id=ID, /uc?id=ID)
    m = re.search(r"/file/d/([^/?#]+)", raw) or re.search(r"[?&]id=([^&]+)", raw)
    if m and "drive.google.com" in raw:
        return {
            "kind": "drive",
            "embed_url": f"https://drive.google.com/file/d/{m.group(1)}/preview",
            "raw_url": raw,
            "message": "",
        }

    # Google Photos — múltiples formatos posibles. Google bloquea embed.
    if (
        "photos.app.goo.gl" in raw
        or "photos.google.com" in raw
        or "goo.gl/photos" in raw
    ):
        return {
            "kind": "photos",
            "embed_url": "",  # vacío a propósito: Google no permite iframe
            "raw_url": raw,
            "message": "Google Photos no permite embed; el video se abre en pestaña aparte. Para mejor experiencia, subir a YouTube como 'No listado'.",
        }

    # Vimeo
    if "vimeo.com" in raw:
        m = re.search(r"vimeo\.com/(\d+)", raw)
        if m:
            return {
                "kind": "iframe",
                "embed_url": f"https://player.vimeo.com/video/{m.group(1)}",
                "raw_url": raw,
                "message": "",
            }

    # Asumimos otro embed válido (caso raro)
    return {"kind": "iframe", "embed_url": raw, "raw_url": raw, "message": ""}


# ============================================================
# 4. PARSER DE RECOMENDACIONES DEL ANFITRIÓN
# ============================================================
URL_RE = re.compile(r"https?://[^\s,]+")

def parse_recomendaciones(texto: str) -> list[dict]:
    """De un textarea de Tally con líneas tipo:
       'La Pasiva https://maps.google.com/?cid=...'
       'Cervecería Berlina - https://goo.gl/maps/...'
       Devuelve [{nombre, url}].
    """
    if not texto:
        return []
    out = []
    for linea in texto.splitlines():
        linea = linea.strip(" \t-•·,;")
        if not linea:
            continue
        m = URL_RE.search(linea)
        url = m.group(0) if m else ""
        nombre = (linea.replace(url, "").strip(" -·:,;") if url else linea).strip()
        if nombre:
            out.append({"nombre": nombre, "url": url})
    return out


# ============================================================
# 5. GOOGLE MAPS — geocoding + lugares por categoría
# ============================================================
def gmaps_client():
    return googlemaps.Client(key=GMAPS_API_KEY)


def extract_coords_from_maps_url(url: str) -> tuple[float, float] | None:
    """Extrae (lat, lng) de un link de Google Maps, expandiendo links cortos si es necesario."""
    import re, urllib.request
    if not url:
        return None

    def _parse(u):
        m = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', u)
        if m:
            return float(m.group(1)), float(m.group(2))
        m = re.search(r'[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)', u)
        if m:
            return float(m.group(1)), float(m.group(2))
        return None

    result = _parse(url)
    if result:
        return result

    # Link corto (goo.gl, maps.app.goo.gl) — expandir siguiendo redirects
    if 'goo.gl' in url or 'maps.app' in url:
        try:
            import requests as req_lib
            resp = req_lib.get(url, allow_redirects=True, timeout=8,
                               headers={'User-Agent': 'Mozilla/5.0'})
            expanded = resp.url
            print(f"  → Maps URL expandida: {expanded[:120]}")
            result = _parse(expanded)
            if result:
                return result
            # Extraer nombre del lugar del path /maps/place/NOMBRE/data=...
            m = re.search(r'/maps/place/([^/@]+)', expanded)
            if m:
                from urllib.parse import unquote_plus
                place_name = unquote_plus(m.group(1).replace('+', ' '))
                print(f"  → Geocodeando por nombre: {place_name[:80]}")
                geo = geocode(place_name)
                if geo:
                    return geo["lat"], geo["lng"]
        except Exception as e:
            print(f"⚠️  No se pudo expandir Maps URL: {e}")

    return None


def reverse_geocode(lat: float, lng: float) -> dict | None:
    """Reverse geocode de coordenadas a {ciudad, barrio, ...}."""
    if not GMAPS_API_KEY:
        return None
    try:
        r = gmaps_client().reverse_geocode((lat, lng))
        if not r:
            return None
        comps = {c["types"][0]: c["long_name"] for c in r[0]["address_components"] if c["types"]}
        ciudad = (
            comps.get("locality")
            or comps.get("administrative_area_level_2")
            or comps.get("sublocality_level_1")
            or comps.get("administrative_area_level_1")
            or ""
        )
        barrio = (
            comps.get("sublocality_level_1")
            or comps.get("neighborhood")
            or comps.get("sublocality")
            or ""
        )
        return {
            "lat": lat,
            "lng": lng,
            "ciudad": ciudad,
            "barrio": barrio,
            "region": comps.get("administrative_area_level_1", ""),
            "country": comps.get("country", ""),
            "formatted": r[0]["formatted_address"],
        }
    except Exception as e:
        print(f"⚠️  reverse_geocode error: {e}")
        return None


def geocode(direccion: str) -> dict | None:
    """Devuelve {lat, lng, ciudad, barrio, region, formatted, country}."""
    if not direccion or not GMAPS_API_KEY:
        return None
    try:
        r = gmaps_client().geocode(direccion)
        if not r:
            return None
        loc = r[0]["geometry"]["location"]
        comps = {c["types"][0]: c["long_name"] for c in r[0]["address_components"] if c["types"]}

        # Resolver ciudad: prioridad locality > admin level 2 > sublocality
        ciudad = (
            comps.get("locality")
            or comps.get("administrative_area_level_2")
            or comps.get("sublocality_level_1")
            or comps.get("administrative_area_level_1")
            or ""
        )
        barrio = (
            comps.get("sublocality_level_1")
            or comps.get("neighborhood")
            or comps.get("sublocality")
            or ""
        )
        region = comps.get("administrative_area_level_1", "")
        country = comps.get("country", "")
        return {
            "lat": loc["lat"],
            "lng": loc["lng"],
            "ciudad": ciudad,
            "barrio": barrio,
            "region": region,
            "country": country,
            "formatted": r[0]["formatted_address"],
        }
    except Exception as e:
        print(f"⚠️  geocode error: {e}")
        return None


# Categorías que se renderizan como tabs en la web
CATEGORIAS = [
    # (clave, etiqueta_es, etiqueta_en, etiqueta_pt, [(places_type, keyword), ...])
    # Múltiples búsquedas por categoría: el mejor que matche queda.
    ("atracciones",   "Atracciones",   "Attractions",   "Atrações",
     [("tourist_attraction", None), ("museum", None), ("park", None)]),
    ("restaurantes",  "Restaurantes",  "Restaurants",   "Restaurantes",
     [("restaurant", None)]),
    ("cafes",         "Cafés",         "Cafés",         "Cafés",
     [("cafe", None), ("bakery", "café")]),
    ("cervecerias",   "Cervecerías",   "Breweries",     "Cervejarias",
     [("bar", "cerveceria"), ("bar", "craft beer"), ("bar", "cerveza artesanal")]),
    ("salir",         "Salir",         "Nightlife",     "Vida noturna",
     [("night_club", None), ("bar", "cocktail"), ("bar", "pub")]),
    ("supermercados", "Supermercados", "Supermarkets",  "Supermercados",
     [("supermarket", None)]),
    ("panaderias",    "Panaderías",    "Bakeries",      "Padarias",
     [("bakery", None)]),
]

# Categorías "esenciales": solo se busca el MÁS CERCANO de cada uno.
ESENCIALES = [
    ("farmacia",   "Farmacia",  "Pharmacy",    "Farmácia",     "pharmacy",    "💊"),
    ("cajero",     "Cajero",    "ATM",         "Caixa eletrônico", "atm",     "💳"),
    ("hospital",   "Hospital",  "Hospital",    "Hospital",     "hospital",    "🏥"),
    ("nafta",      "Estación de servicio", "Gas station", "Posto de gasolina", "gas_station", "⛽"),
]

# Detector de ciudades donde Pedro tiene promos personales
CIUDADES_PEDRO = {"bariloche", "san carlos de bariloche"}


def _places_search(gm, location, radius, places_type, keyword=None):
    """Una llamada a places_nearby, devuelve lista de results crudos."""
    kwargs = {"location": location, "radius": radius, "type": places_type}
    if keyword:
        kwargs["keyword"] = keyword
    try:
        return gm.places_nearby(**kwargs).get("results", [])
    except Exception as e:
        print(f"⚠️  places error ({places_type}/{keyword}): {e}")
        return []


def _normalize_place(p):
    return {
        "nombre": p.get("name", ""),
        "rating": p.get("rating"),
        "reviews": p.get("user_ratings_total"),
        "direccion": p.get("vicinity", ""),
        "lat": p["geometry"]["location"]["lat"],
        "lng": p["geometry"]["location"]["lng"],
        "place_id": p.get("place_id", ""),
        "maps_url": f"https://www.google.com/maps/place/?q=place_id:{p.get('place_id','')}",
    }


def lugares_por_categoria(lat: float, lng: float, radius: int = 4000) -> dict[str, list[dict]]:
    """Para cada categoría, hace múltiples búsquedas, deduplica por place_id,
    ordena por rating × log(reseñas) y devuelve hasta 5.
    
    Si una categoría sale vacía, reintenta con radio expandido (8km).
    """
    if not GMAPS_API_KEY:
        return {k: [] for k, *_ in CATEGORIAS}

    gm = gmaps_client()
    out: dict[str, list[dict]] = {}

    for key, _es, _en, _pt, queries in CATEGORIAS:
        all_results = []
        seen_ids = set()

        # Intento 1: radio normal con todas las queries
        for places_type, keyword in queries:
            for p in _places_search(gm, (lat, lng), radius, places_type, keyword):
                pid = p.get("place_id", "")
                if pid and pid not in seen_ids and p.get("business_status") != "CLOSED_PERMANENTLY":
                    seen_ids.add(pid)
                    all_results.append(p)

        # Intento 2: si sigue vacío, expandir radio a 8km
        if not all_results:
            print(f"  ⚠️  {key} vacío con radio {radius}m, reintentando con 8000m")
            for places_type, keyword in queries:
                for p in _places_search(gm, (lat, lng), 8000, places_type, keyword):
                    pid = p.get("place_id", "")
                    if pid and pid not in seen_ids and p.get("business_status") != "CLOSED_PERMANENTLY":
                        seen_ids.add(pid)
                        all_results.append(p)

        # Ordenar por rating × log(reseñas)
        all_results.sort(
            key=lambda p: (p.get("rating", 0) * (1 + (p.get("user_ratings_total", 0) ** 0.5))),
            reverse=True,
        )
        out[key] = [_normalize_place(p) for p in all_results[:5]]
        print(f"  ✓ {key}: {len(out[key])} lugares")

    return out


# ============================================================
# 6. GEMINI — marca, welcome, tips, descripciones
# ============================================================
def _gemini():
    return genai.GenerativeModel("gemini-2.5-flash") if GEMINI_API_KEY else None


def _gemini_json(prompt: str, fallback: Any) -> Any:
    """Pide a Gemini que devuelva JSON estricto. Tolerante a errores."""
    model = _gemini()
    if not model:
        return fallback
    try:
        resp = model.generate_content(
            prompt + "\n\nDevolvé SOLO JSON válido. Sin markdown, sin ``` y sin texto extra."
        )
        txt = resp.text.strip()
        # quitar fences si vienen
        txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt, flags=re.MULTILINE).strip()
        return json.loads(txt)
    except Exception as e:
        print(f"⚠️  gemini json error: {e}")
        return fallback


def generar_marca(ciudad: str, country: str) -> dict:
    """Devuelve {nombre_corto, hero_titulo_html, hero_badge, region_label, theme}.

    theme ∈ { 'montana', 'ciudad', 'playa', 'rio', 'desierto', 'vinedo', 'selva' }
    Define el gradiente y mood visual del hero/header.
    """
    fallback = {
        "nombre_corto": f"{ciudad} Experiencias" if ciudad else "Experiencias",
        "hero_titulo_html": f"{ciudad}<br>Experiencias" if ciudad else "Tu<br>Experiencia",
        "hero_badge": f"📍 {ciudad}" if ciudad else "📍 Bienvenido",
        "region_label": ciudad,
        "theme": "ciudad",
    }
    if not ciudad:
        return fallback
    return _gemini_json(
        f"""
Para una ciudad llamada "{ciudad}" en "{country}", devolveme un JSON con:
- nombre_corto: "{ciudad} Experiencias" (literal)
- hero_titulo_html: el nombre cortado en dos líneas con <br>, ej "{ciudad}<br>Experiencias"
- hero_badge: emoji que represente la zona + región turística + ciudad. Ejemplos:
    "🏔️ Patagonia · {ciudad}" para zonas montañosas/cordillera,
    "🏖️ Costa Atlántica · {ciudad}" para playa/mar,
    "🌆 Zona Norte · {ciudad}" para urbano/suburbano,
    "🏜️ Cuyo · {ciudad}" para desierto/viñedos,
    "🌳 Litoral · {ciudad}" para río/selva subtropical.
- region_label: nombre corto de la región turística. Ej "Patagonia", "Zona Norte", "Costa Atlántica", "Cuyo", "Litoral", "NOA".
- theme: el AMBIENTE PREDOMINANTE de la ciudad. UNA de estas opciones EXACTAS:
    "montana"  -> ciudades de cordillera/sierra (Bariloche, Mendoza alta, El Chaltén, Esquel)
    "ciudad"   -> urbano/suburbano (CABA, San Isidro, Rosario, Córdoba ciudad)
    "playa"    -> costa marítima (Mar del Plata, Pinamar, Cariló, Punta del Este)
    "rio"      -> ribera/delta (Tigre, Rosario costa, Paraná)
    "desierto" -> seco/árido (San Juan, La Rioja, parte de Salta)
    "vinedo"   -> zonas vitivinícolas (Mendoza, Cafayate, Valle de Uco)
    "selva"    -> selva/yungas/litoral húmedo (Iguazú, Misiones, Tucumán)

Devolvé SOLO el JSON. Sin markdown, sin texto extra.
""",
        fallback,
    )


def generar_welcome(
    ciudad: str,
    barrio: str,
    direccion: str,
    nombre_propiedad: str,
    lugares_cercanos: list[dict] | None = None,
) -> dict:
    """Devuelve {es: {title, sub}, en: {...}, pt: {...}}.
    Si recibe lugares_cercanos (de Places API), Gemini menciona uno concreto.
    """
    base = barrio or ciudad
    fallback = {
        "es": {"title": f"Bienvenidos al {nombre_propiedad}", "sub": f"En el corazón de {base}"},
        "en": {"title": f"Welcome to {nombre_propiedad}", "sub": f"In the heart of {base}"},
        "pt": {"title": f"Bem-vindos ao {nombre_propiedad}", "sub": f"No coração de {base}"},
    }
    if not (barrio or ciudad):
        return fallback

    # Pasarle a Gemini los nombres de lugares reales cercanos para que use UNO concreto
    contexto_lugares = ""
    if lugares_cercanos:
        nombres = [l["nombre"] for l in lugares_cercanos[:8] if l.get("nombre")]
        if nombres:
            contexto_lugares = "\nLugares notables que están cerca (elegí UNO para mencionar): " + ", ".join(nombres)

    return _gemini_json(
        f"""
Generá el welcome message para una propiedad de alquiler temporario.
Propiedad: "{nombre_propiedad}"
Barrio: "{barrio}"
Ciudad: "{ciudad}"
Dirección: "{direccion}"
{contexto_lugares}

JSON con tres idiomas (es, en, pt). Cada uno con:
- title: "Bienvenidos a {nombre_propiedad}" o variación corta. Una sola línea, max 40 chars.
- sub: una línea corta y CONCRETA mencionando algo específico cerca. SI te di lugares
  notables arriba, mencioná UNO de ellos con distancia aproximada inventada-pero-creíble
  (ej. "El Museo Pueyrredón a la vuelta", "Catedral de San Isidro a 200 metros").
  Si NO hay lugares, mencioná un dato concreto del barrio. Sin clichés ("vibrante",
  "increíble", "único"). Max 80 chars.

Tono: cálido, local, evocador. Sin emojis. Sin signos de exclamación.
""",
        fallback,
    )


def generar_tip_local(ciudad: str, barrio: str, region: str) -> dict:
    """Tips para la sección de info útil."""
    fallback = {"es": "", "en": "", "pt": ""}
    if not ciudad:
        return fallback
    return _gemini_json(
        f"""
Para huéspedes de Airbnb llegando a {ciudad} ({region}, barrio {barrio or ciudad}),
escribí UN tip local concreto y útil (máx 90 chars) en 3 idiomas.

JSON: {{"es": "...", "en": "...", "pt": "..."}}.

Sin emojis. Sin clichés ("vibra única"). Algo que un local le diría a un visitante:
ej. "El centro tiene galerías para refugiarse de la lluvia",
ej. "En verano la playa de mañana es de locales, de tarde se llena".
""",
        fallback,
    )


def generar_tips_locales(ciudad: str, region: str, country: str) -> list[dict]:
    """Devuelve [{es, en, pt, emoji}, …] con 4 tips concretos sobre la ciudad."""
    if not ciudad:
        return []
    fallback = []
    return _gemini_json(
        f"""
Para huéspedes de Airbnb llegando a {ciudad} ({region}, {country}),
generá EXACTAMENTE 4 tips locales concretos y útiles. Cada uno en 3 idiomas.

JSON: array de 4 objetos con esta forma:
{{
  "emoji": "💡",
  "title": {{"es": "...", "en": "...", "pt": "..."}},
  "text": {{"es": "...", "en": "...", "pt": "..."}}
}}

Reglas:
- title: máx 35 chars, en mayúsculas estilo card. Ej: "Domingos en {ciudad}", "Subte hasta cuándo", "Lluvia en {ciudad}".
- text: máx 110 chars. Tip CONCRETO que un local le diría a alguien recién llegado.
- emoji: UN emoji que represente el tip. Variá los emojis entre los 4.
- Sin clichés. Sin "increíble", "vibrante", "único". Sin signos de exclamación.
- Los 4 tips deben ser de TEMAS DIFERENTES: ej clima, transporte, costumbres, gastronomía,
  horarios, seguridad, qué evitar, qué buscar, etc.
- Adaptados a {ciudad} específicamente (NO genéricos).
""",
        fallback,
    )


def generar_outfit_actividades(ciudad: str, region: str, lat: float, lng: float) -> list[dict]:
    """Devuelve actividades típicas de la zona, cada una con outfit por clima."""
    if not ciudad:
        return []
    return _gemini_json(
        f"""
Para huéspedes de Airbnb en {ciudad} ({region}, lat {lat}, lng {lng}),
generá 4 ACTIVIDADES TÍPICAS QUE SE PUEDEN HACER en esa zona específica.
Por ejemplo, en Bariloche: trekking en cerro, kayak en lago, ski, recorrer cervecerías.
En San Isidro: pasear por la costa, ir al hipódromo, paseo por el casco histórico.
En Mar del Plata: playa, puerto, surf, salir de noche.

JSON: array de 4 objetos con esta forma:
{{
  "key": "slug_corto_sin_espacios",
  "emoji": "🚶",
  "label": {{"es": "...", "en": "...", "pt": "..."}},
  "outfit_frio":  {{"es": ["item1", "item2", "item3", "item4"], "en": [...], "pt": [...]}},
  "outfit_templado": {{"es": [...], "en": [...], "pt": [...]}},
  "outfit_calido": {{"es": [...], "en": [...], "pt": [...]}},
  "tip": {{"es": "...", "en": "...", "pt": "..."}}
}}

Reglas:
- label: máx 18 chars. ej "Trekking", "Playa", "Centro histórico".
- Cada outfit_X debe tener 4-5 items con emoji al inicio. Ej: "🧥 Campera impermeable".
- tip: máx 100 chars. Algo concreto sobre HACER esa actividad en {ciudad}.
- Las 4 actividades deben ser GENUINAMENTE TÍPICAS de {ciudad} — NO genéricas.
- Sin signos de exclamación. Sin clichés.
""",
        [],
    )


def generar_info_completa(ciudad: str, region: str, country: str) -> dict:
    """De UNA sola llamada a Gemini, todas las secciones contextuales:
    instrucciones, autos, colectivos, temporadas, hikes, excursiones, emergencias.

    NOTA: los nombres de ALQUILERES DE AUTO se llenan con Places API por separado
    (ver obtener_alquileres_auto). Gemini solo da el "consejo general" sobre autos.
    """
    fallback = {
        "instrucciones": [],
        "autos": {},
        "colectivos": {},
        "temporadas": [],
        "hikes": [],
        "excursiones": [],
        "emergencias": {"emergencia_general": "911"},
    }
    if not ciudad:
        return fallback
    return _gemini_json(
        f"""
Sos un anfitrión local de {ciudad} ({region}, {country}) ayudando a un huésped que recién llega.
Generá un JSON con info CONCRETA y VERIFICABLE de {ciudad}. Si no estás seguro de algún dato,
OMITILO en lugar de inventar.

JSON estructura exacta:
{{
  "instrucciones": [
    /* EXACTAMENTE 4 items críticos para huéspedes de {ciudad}.
       Ejemplos por ciudad:
       - Bariloche: aire seco / agua potable / vientos fuertes / nieve resbaladiza
       - Mar del Plata: bruma matinal / agua del mar fría / cuidado con sudestada / médanos
       - San Isidro: humedad alta verano / SUBE obligatoria / domingos centro cerrado
       - Mendoza: zonda (viento cálido seco) / altura provoca cansancio / agua escasa

       NO digas cosas obvias ("disfruten su estadía"). SÍ cosas que un local sabe.

       Cada item: {{"emoji":"...","title":{{"es","en","pt"}},"text":{{"es","en","pt"}}}}
    */
  ],
  "autos": {{
    "title": {{"es":"Alquiler de auto","en":"Car rental","pt":"Aluguel de carro"}},
    "necesario": "si"|"opcional"|"no",
    "desc": {{"es":"...","en":"...","pt":"..."}},
    /* desc: ¿es necesario tener auto en {ciudad}? Razones concretas.
       Ej Bariloche: "Sí, para hacer Circuito Chico y excursiones. En centro caminás bien."
       Ej Mar del Plata: "No es necesario, hay buen transporte y todo cerca de la costa."
       Ej San Isidro: "Opcional. Si vas a recorrer zona norte sí, sino tren y subte funcionan." */
    "tips": [
      /* 2-3 tips operativos REALES sobre manejar en {ciudad}: peajes, estacionamiento,
         calles complicadas, dónde NO ir en hora pico. */
      {{"es":"...","en":"...","pt":"..."}}
    ]
  }},
  "colectivos": {{
    "title": {{"es":"Transporte público","en":"Public transport","pt":"Transporte público"}},
    "desc": {{"es":"...","en":"...","pt":"..."}},
    /* desc: cómo funciona el transporte. Tarjeta SUBE? Otro sistema? Apps? Frecuencia general? */
    "lineas_principales": [
      /* 3-4 LÍNEAS REALES con destino REAL. Si no las conocés con seguridad, dejá array vacío.
         Ej Mar del Plata línea 522 va al Aquarium. Ej Bariloche línea 20 va al Cerro Catedral.
         Ej CABA "subte línea D" llega a Recoleta. */
      {{"linea":"NUMERO_O_NOMBRE_REAL","desc":{{"es":"hacia DESTINO REAL · frecuencia","en":"...","pt":"..."}}}}
    ]
  }},
  "temporadas": [
    /* EXACTAMENTE 4 entries. Cada una con TEMP. PROMEDIO REAL y un consejo específico.
       Ej Mar del Plata: "Verano (Dic-Mar)" → "25-30°C, playa llena en enero, mejor febrero"
       Ej Bariloche: "Invierno (Jun-Sep)" → "0-8°C, ski en Catedral, días cortos"
    */
    {{"emoji":"☀️|🍂|❄️|🌸","title":{{"es","en","pt"}},"meses":{{"es":"Mes-Mes","en","pt"}},
      "desc":{{"es":"TEMP°C + dato concreto","en":"...","pt":"..."}}}}
  ],
  "hikes": [
    /* 3-4 caminatas/paseos al aire libre REALES de {ciudad}.
       Ej Mar del Plata: Reserva del Puerto, Laguna de los Padres, Faro Punta Mogotes.
       Ej Bariloche: Cerro Llao Llao, Cerro Campanario, Mirador Cipreses.
       Si {ciudad} es muy urbana sin senderos: parques emblemáticos o paseos peatonales.

       Si NO conocés hikes específicos de {ciudad} con NOMBRE EXACTO, dejá array vacío.
    */
    {{"nombre":"NOMBRE EXACTO","tipo":{{"es","en","pt"}},"dificultad":{{"es","en","pt"}},
      "desc":{{"es","en","pt"}},"maps_query":"nombre+lugar+ciudad"}}
  ],
  "excursiones": [
    /* 3-4 excursiones de día completo SALIENDO de {ciudad}, con NOMBRE REAL del destino.
       Ej Bariloche: "Circuito Chico", "Cerro Tronador", "El Bolsón".
       Ej Mar del Plata: "Mar Chiquita", "Sierra de los Padres", "Miramar".
       Ej San Isidro: "Tigre y Delta", "Luján", "Capital Federal".
    */
    {{"nombre":"NOMBRE REAL","duracion":{{"es":"Día completo|Medio día","en","pt"}},
      "desc":{{"es":"qué se hace + cómo llegar","en","pt"}},"maps_query":"..."}}
  ],
  "emergencias": {{
    /* Para Argentina: policía 911, ambulancia 107, bomberos 100. Otros países, ajustar. */
    "policia":"911","ambulancia":"107","bomberos":"100","emergencia_general":"911"
  }}
}}

REGLAS NO NEGOCIABLES:
1. Cada texto en cada idioma debe ser DISTINTO y bien traducido (no copiar el español).
2. Datos REALES y verificables. Si dudás, OMITILO (array vacío). Inventar nombres es peor que faltar.
3. Cada texto máx 120 chars.
4. NO uses clichés ("vibrante", "único", "increíble", "imperdible").
5. NO emojis dentro de los textos (van en el campo "emoji").
6. Tono: hablale al huésped en segunda persona ("vas a ver", "te conviene").
7. Devolvé SOLO el JSON, sin markdown ni ``` ni texto extra.
""",
        fallback,
    )


def obtener_alquileres_auto(lat: float, lng: float) -> list[dict]:
    """Busca alquileres de auto reales cerca usando Places API.
    Devuelve hasta 3 con nombre, dirección, teléfono si disponible.
    """
    if not GMAPS_API_KEY:
        return []
    gm = gmaps_client()
    try:
        resp = gm.places_nearby(
            location=(lat, lng), radius=5000, keyword="alquiler de autos rent a car"
        )
        results = resp.get("results", [])
        results.sort(
            key=lambda p: (p.get("rating", 0) * (1 + (p.get("user_ratings_total", 0) ** 0.5))),
            reverse=True,
        )
        out = []
        for p in results[:3]:
            if p.get("business_status") == "CLOSED_PERMANENTLY":
                continue
            place_id = p.get("place_id", "")
            # Buscar teléfono via Place Details
            phone = ""
            try:
                details = gm.place(place_id, fields=["formatted_phone_number"])
                phone = details.get("result", {}).get("formatted_phone_number", "")
            except Exception:
                pass
            out.append({
                "nombre": p.get("name", ""),
                "direccion": p.get("vicinity", ""),
                "rating": p.get("rating"),
                "telefono": phone,
                "maps_url": f"https://www.google.com/maps/place/?q=place_id:{place_id}",
            })
        return out
    except Exception as e:
        print(f"⚠️  alquileres error: {e}")
        return []


def obtener_esenciales(lat: float, lng: float) -> dict[str, dict | None]:
    """Devuelve {key: {nombre, direccion, maps_url, distancia_aprox} | None}.
    Busca el más cercano de cada categoría esencial.
    """
    if not GMAPS_API_KEY:
        return {key: None for key, *_ in ESENCIALES}

    gm = gmaps_client()
    out = {}
    for key, _es, _en, _pt, places_type, emoji in ESENCIALES:
        try:
            resp = gm.places_nearby(location=(lat, lng), rank_by="distance", type=places_type)
            results = [
                p for p in resp.get("results", [])
                if p.get("business_status") != "CLOSED_PERMANENTLY"
            ]
            if not results:
                out[key] = None
                continue
            p = results[0]
            out[key] = {
                "nombre": p.get("name", ""),
                "direccion": p.get("vicinity", ""),
                "rating": p.get("rating"),
                "place_id": p.get("place_id", ""),
                "lat": p["geometry"]["location"]["lat"],
                "lng": p["geometry"]["location"]["lng"],
                "maps_url": f"https://www.google.com/maps/place/?q=place_id:{p.get('place_id','')}",
                "emoji": emoji,
                "labels": {"es": _es, "en": _en, "pt": _pt},
            }
        except Exception as e:
            print(f"⚠️  esenciales error ({key}): {e}")
            out[key] = None
    return out


def describir_lugares(lugares_por_cat: dict[str, list[dict]], ciudad: str) -> dict:
    """Para cada lugar, agrega 'desc' con {es, en, pt} de máx 90 chars."""
    if not _gemini() or not lugares_por_cat:
        return lugares_por_cat

    # Aplanar para enviar uno solo a Gemini
    flat = []
    for cat, items in lugares_por_cat.items():
        for i, item in enumerate(items):
            flat.append({"cat": cat, "idx": i, "nombre": item["nombre"]})
    if not flat:
        return lugares_por_cat

    nombres_listado = "\n".join(f"{i}. {x['nombre']} ({x['cat']})" for i, x in enumerate(flat))
    prompt = f"""
Para cada uno de estos lugares en {ciudad}, escribí una descripción breve (max 90 chars) en 3 idiomas. Sin clichés. Sin emojis. Si no conocés el lugar específico, describí el TIPO de lugar (cafetería de especialidad, parrilla clásica, bar de cervezas artesanales, etc.).

Lugares:
{nombres_listado}

Devolvé un JSON: array con {len(flat)} objetos, cada uno {{"es": "...", "en": "...", "pt": "..."}} en el MISMO ORDEN.
"""
    descs = _gemini_json(prompt, [{"es": "", "en": "", "pt": ""} for _ in flat])
    if not isinstance(descs, list) or len(descs) != len(flat):
        return lugares_por_cat

    for x, d in zip(flat, descs):
        if isinstance(d, dict):
            lugares_por_cat[x["cat"]][x["idx"]]["desc"] = d
    return lugares_por_cat


# ============================================================
# 7. ARMAR DATA POR PROPIEDAD
# ============================================================
@dataclass
class Propiedad:
    idx: int
    nombre: str
    direccion: str
    lat: float | None
    lng: float | None
    barrio: str
    ciudad: str
    formatted: str
    maps_link: str
    instagram: str
    video_es: dict
    video_en: dict
    wifi_ssid: str
    wifi_pass: str
    welcome: dict
    recomendaciones: list[dict]
    lugares: dict[str, list[dict]] = field(default_factory=dict)


def procesar_propiedad(row: dict, idx: int) -> Propiedad | None:
    suf = f"_d{idx}"
    nombre = get_field(row, f"nombre_propiedad{suf}", f"nombre{suf}")
    if not nombre:
        return None
    direccion = get_field(row, f"direccion{suf}", f"ubicacion{suf}", "direccion")
    maps_url = get_field(row, f"maps{suf}", f"maps_link{suf}", f"google_maps{suf}")
    print(f"  → [{idx}] '{nombre}' | {direccion or maps_url or '(sin dirección)'}")

    geo = None
    if direccion:
        geo = geocode(direccion)
    if not geo and maps_url:
        coords = extract_coords_from_maps_url(maps_url)
        if coords:
            geo = reverse_geocode(coords[0], coords[1])
            print(f"  → Geocodeado desde Maps link: {geo and geo.get('ciudad')}")

    lat = geo["lat"] if geo else None
    lng = geo["lng"] if geo else None
    ciudad = geo["ciudad"] if geo else (get_field(row, "ciudad") or "")
    barrio = geo["barrio"] if geo else ""
    formatted = geo["formatted"] if geo else (direccion or "")

    welcome = generar_welcome(ciudad, barrio, formatted, nombre)
    recos = parse_recomendaciones(get_field(row, f"recomendaciones{suf}", f"recomendados{suf}"))

    return Propiedad(
        idx=idx,
        nombre=nombre,
        direccion=formatted,
        lat=lat,
        lng=lng,
        barrio=barrio,
        ciudad=ciudad,
        formatted=formatted,
        maps_link=(
            maps_url
            or get_field(row, f"maps_link{suf}")
            or (
                f"https://www.google.com/maps/search/?api=1&query={quote_plus(formatted)}"
                if formatted
                else ""
            )
        ),
        instagram=get_field(row, f"instagram{suf}", f"usuario_instagram{suf}").lstrip("@"),
        video_es=normalize_video(get_field(row, f"video_checkin{suf}", f"video{suf}")),
        video_en=normalize_video(get_field(row, f"video_checkin_en{suf}")),
        wifi_ssid=get_field(row, f"wifi_ssid{suf}", f"wifi_nombre{suf}"),
        wifi_pass=get_field(row, f"wifi_pass{suf}", f"wifi_password{suf}"),
        welcome=welcome,
        recomendaciones=recos,
    )


# ============================================================
# 8. RENDER + GUARDAR
# ============================================================
def render(ctx: dict, slug: str, template_name: str) -> Path:
    env = Environment(loader=FileSystemLoader("."), autoescape=True)
    env.filters["tojson"] = lambda v: json.dumps(v, ensure_ascii=False)
    tpl = env.get_template(template_name)
    html = tpl.render(**ctx)
    carpeta = OUTPUT_DIR / slug
    carpeta.mkdir(parents=True, exist_ok=True)
    out = carpeta / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"✓ Generado: {out} (con {template_name})")
    return out


# ============================================================
# 9. EMAIL
# ============================================================
def enviar_email(
    destinatario: str,
    link: str,
    anfitrion: str,
    ciudad: str,
    propiedades: list | None = None,
) -> None:
    """Email al anfitrión con: link de la web + WhatsApp de Pedro +
    instrucciones detalladas para grabar el video de check-in.
    """
    # WhatsApp de Pedro (configurable via env, fallback al actual)
    PEDRO_WHATSAPP = os.environ.get("PEDRO_WHATSAPP", "+5491131952798")
    pedro_wa_link = "https://wa.me/" + PEDRO_WHATSAPP.replace("+", "").replace(" ", "").replace("-", "")
    pedro_wa_display = PEDRO_WHATSAPP

    # Listado de propiedades para que el anfitrión sepa qué deptos tiene cargados
    propiedades = propiedades or []
    nombres_propiedades = [p.get("nombre", "") if isinstance(p, dict) else getattr(p, "nombre", "")
                           for p in propiedades]
    nombres_propiedades = [n for n in nombres_propiedades if n]

    if len(nombres_propiedades) > 1:
        listado_props_txt = "\n".join(f"  • {n}" for n in nombres_propiedades)
        listado_props_html = "<ul>" + "".join(f"<li><strong>{n}</strong></li>" for n in nombres_propiedades) + "</ul>"
        propiedades_intro_txt = f"\nTenés cargadas estas {len(nombres_propiedades)} propiedades:\n{listado_props_txt}\n\n"
        propiedades_intro_html = f"<p>Tenés cargadas estas <strong>{len(nombres_propiedades)} propiedades</strong>:</p>{listado_props_html}"
        instr_video_extra_txt = "Importante: cuando me mandes los videos, decime de cuál propiedad es cada uno (usá los nombres de arriba)."
        instr_video_extra_html = "<p><strong>Importante:</strong> cuando me mandes los videos, decime de cuál propiedad es cada uno (usá los nombres de arriba).</p>"
    elif len(nombres_propiedades) == 1:
        propiedades_intro_txt = f"\nPropiedad cargada: {nombres_propiedades[0]}\n\n"
        propiedades_intro_html = f"<p>Propiedad cargada: <strong>{nombres_propiedades[0]}</strong></p>"
        instr_video_extra_txt = ""
        instr_video_extra_html = ""
    else:
        propiedades_intro_txt = ""
        propiedades_intro_html = ""
        instr_video_extra_txt = ""
        instr_video_extra_html = ""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "✅ Tu web está lista — solo falta el video"
    msg["From"] = EMAIL_USER
    msg["To"] = destinatario

    texto = f"""Hola {anfitrion}!

¡Bienvenido/a! Tu guía digital para huéspedes en {ciudad} ya está publicada:

{link}
{propiedades_intro_txt}
🎯 SIGUIENTE PASO — VIDEO DE CHECK-IN

Para que tu web esté 100% lista, falta solo una cosa: el video de cómo entrar a tu propiedad. Lo cargo yo, vos solo lo grabás con el celu y me lo mandás.

CÓMO GRABAR EL VIDEO (tipo Airbnb, 1-2 minutos)

📱 Filmá con el celu en horizontal (acostado), buena luz, sin viento.

Mostrá estos 5 puntos en orden, hablando como si fueras un anfitrión amigo:

1. ESTACIONAMIENTO
   Mostrá dónde tiene que estacionar el huésped. Si hay calle, garage,
   o lugar específico, indicalo claramente.

2. CÓMO LLEGAR A LA PUERTA
   Caminá desde donde estaciona hasta la puerta de entrada. Si hay
   pasillo, escalera, ascensor, o algo confuso, mostralo.

3. DÓNDE ESTÁN LAS LLAVES
   Mostrá EXACTAMENTE dónde se retiran. Si hay caja con código,
   recepción, llavero escondido, lo que sea.
   Decí en voz alta el código si aplica (después lo edito si querés).

4. CÓMO ABRIR LA PUERTA
   Mostrá la cerradura y cómo se gira la llave. A veces parece obvio
   pero los huéspedes nuevos se traban.

5. PRIMER VISTAZO ADENTRO
   Una vez adentro, una pasada general por las áreas principales:
   "Acá está la cocina, allá el dormitorio, el baño es ese".

CONSEJOS

✓ Hablá tranquilo y claro, en español neutro
✓ Evitá ruidos de fondo (TV, música, gente hablando)
✓ Si te equivocás, no importa — re-grabá la parte
✓ El video puede ser vertical o horizontal
✓ Tamaño máximo: 5 minutos. Ideal: 1-2 minutos.
{instr_video_extra_txt}
🟢 MANDAME EL VIDEO POR WHATSAPP

Mi WhatsApp: {pedro_wa_display}
Link directo: {pedro_wa_link}

Mandame el video por ahí. Yo lo subo a YouTube y lo agrego a tu web (5 minutos de mi parte). Cuando esté cargado, te aviso.

LO QUE TIENE TU WEB

• Bienvenida personalizada al barrio
• WiFi con código QR (los huéspedes lo escanean y se conectan)
• Cómo llegar (link directo a Google Maps)
• Recomendaciones de restaurantes, cervecerías, cafés cerca
• Clima en tiempo real
• Tips locales de la zona
• Lugares esenciales: farmacia, cajero, hospital
• Multi-idioma: español, inglés y portugués

Cualquier ajuste o duda, respondeme este mail o escribime al WhatsApp.

¡Saludos!

— Pedro Volpacchio
Bariloche Experiencias
"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.6;color:#1f2937;max-width:600px;margin:0 auto;padding:20px;background:#f9fafb">

  <div style="background:linear-gradient(135deg,#10b981,#059669);color:#fff;padding:24px;border-radius:14px;text-align:center;margin-bottom:24px">
    <div style="font-size:32px;margin-bottom:8px">✅</div>
    <h1 style="margin:0;font-size:22px;font-weight:800">¡Tu web ya está lista!</h1>
    <p style="margin:8px 0 0 0;opacity:0.95;font-size:14px">Solo falta el video de check-in</p>
  </div>

  <p>Hola <strong>{anfitrion}</strong>!</p>
  <p>Tu guía digital para huéspedes en <strong>{ciudad}</strong> ya está publicada:</p>

  <p style="text-align:center;margin:24px 0">
    <a href="{link}" style="display:inline-block;background:#2563eb;color:#fff;padding:14px 28px;border-radius:10px;text-decoration:none;font-weight:700;font-size:15px">🌐 Ver mi web</a>
  </p>

  {propiedades_intro_html}

  <div style="background:#fef3c7;border:2px solid #fbbf24;border-radius:14px;padding:20px;margin:28px 0">
    <h2 style="margin:0 0 12px 0;font-size:18px;color:#92400e">🎯 Siguiente paso — Video de check-in</h2>
    <p style="margin:0;color:#78350f">Para que tu web esté 100% lista, falta solo una cosa: el video de cómo entrar a tu propiedad. <strong>Lo cargo yo</strong>, vos solo lo grabás con el celu y me lo mandás por WhatsApp.</p>
  </div>

  <h3 style="color:#1f2937;border-bottom:2px solid #e5e7eb;padding-bottom:8px">📹 Cómo grabar el video (tipo Airbnb, 1-2 min)</h3>

  <p>Filmá con el celu en <strong>buena luz, sin viento</strong>. Mostrá estos 5 puntos en orden, hablando como si fueras un anfitrión amigo:</p>

  <div style="background:#f0f9ff;border-left:4px solid #3b82f6;padding:14px 18px;margin:12px 0;border-radius:0 8px 8px 0">
    <strong style="color:#1e40af">1. 🚗 Estacionamiento</strong>
    <p style="margin:4px 0 0 0;font-size:14px;color:#374151">Mostrá dónde tiene que estacionar. Si hay calle, garage o lugar específico, indicalo claramente.</p>
  </div>

  <div style="background:#f0f9ff;border-left:4px solid #3b82f6;padding:14px 18px;margin:12px 0;border-radius:0 8px 8px 0">
    <strong style="color:#1e40af">2. 🚶 Cómo llegar a la puerta</strong>
    <p style="margin:4px 0 0 0;font-size:14px;color:#374151">Caminá desde donde estaciona hasta la puerta. Si hay pasillo, escalera, ascensor o algo confuso, mostralo.</p>
  </div>

  <div style="background:#f0f9ff;border-left:4px solid #3b82f6;padding:14px 18px;margin:12px 0;border-radius:0 8px 8px 0">
    <strong style="color:#1e40af">3. 🔑 Dónde están las llaves</strong>
    <p style="margin:4px 0 0 0;font-size:14px;color:#374151">Mostrá <strong>exactamente</strong> dónde se retiran. Si hay caja con código, recepción, llavero escondido — lo que sea. Decí el código en voz alta (después lo edito si preferís).</p>
  </div>

  <div style="background:#f0f9ff;border-left:4px solid #3b82f6;padding:14px 18px;margin:12px 0;border-radius:0 8px 8px 0">
    <strong style="color:#1e40af">4. 🚪 Cómo abrir la puerta</strong>
    <p style="margin:4px 0 0 0;font-size:14px;color:#374151">Mostrá la cerradura y cómo se gira la llave. A veces parece obvio pero los huéspedes nuevos se traban.</p>
  </div>

  <div style="background:#f0f9ff;border-left:4px solid #3b82f6;padding:14px 18px;margin:12px 0;border-radius:0 8px 8px 0">
    <strong style="color:#1e40af">5. 🏠 Primer vistazo adentro</strong>
    <p style="margin:4px 0 0 0;font-size:14px;color:#374151">Una vez adentro, una pasada general: "acá está la cocina, allá el dormitorio, el baño es ese".</p>
  </div>

  <div style="background:#f0fdf4;border-radius:10px;padding:14px 18px;margin:20px 0;font-size:13px;color:#166534">
    <strong>Consejos rápidos:</strong>
    <ul style="margin:8px 0 0 0;padding-left:20px">
      <li>Hablá tranquilo, en español neutro</li>
      <li>Evitá ruidos de fondo (TV, música, gente)</li>
      <li>Si te equivocás, re-grabá la parte. No importa la perfección.</li>
      <li>Vertical u horizontal, los dos andan</li>
      <li>Ideal: 1-2 minutos. Máximo: 5 minutos.</li>
    </ul>
  </div>

  {instr_video_extra_html}

  <div style="background:linear-gradient(135deg,#25d366,#128c7e);color:#fff;border-radius:14px;padding:22px;text-align:center;margin:28px 0">
    <div style="font-size:36px;margin-bottom:8px">📱</div>
    <h2 style="margin:0 0 8px 0;font-size:18px">Mandame el video por WhatsApp</h2>
    <p style="margin:0 0 16px 0;font-size:14px;opacity:0.95">Yo lo subo a YouTube y lo agrego a tu web (5 min). Cuando esté listo, te aviso.</p>
    <a href="{pedro_wa_link}" style="display:inline-block;background:#fff;color:#128c7e;padding:14px 28px;border-radius:10px;text-decoration:none;font-weight:800;font-size:15px">💬 Escribirme — {pedro_wa_display}</a>
  </div>

  <h3 style="color:#1f2937;border-bottom:2px solid #e5e7eb;padding-bottom:8px;margin-top:32px">✨ Lo que tiene tu web</h3>
  <ul style="color:#374151;font-size:14px">
    <li>Bienvenida personalizada al barrio</li>
    <li>WiFi con código QR (huéspedes escanean y se conectan)</li>
    <li>Cómo llegar (link directo a Google Maps)</li>
    <li>Recomendaciones de restaurantes, cervecerías, cafés cerca</li>
    <li>Clima en tiempo real</li>
    <li>Tips locales de la zona (transporte, costumbres, qué evitar)</li>
    <li>Esenciales: farmacia, cajero, hospital más cercano</li>
    <li>Multi-idioma: español, inglés, portugués</li>
  </ul>

  <p style="font-size:13px;color:#6b7280;margin-top:24px">Cualquier ajuste o duda, respondeme este mail o escribime al WhatsApp ☝️</p>

  <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0">

  <p style="font-size:13px;color:#6b7280;text-align:center">
    <strong style="color:#374151">Pedro Volpacchio</strong><br>
    Bariloche Experiencias
  </p>

</body>
</html>"""

    msg.attach(MIMEText(texto, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(EMAIL_USER, EMAIL_PASS)
        s.send_message(msg)
    print(f"✓ Email enviado a {destinatario}")


# ============================================================
# MAIN
# ============================================================
def main():
    build_credentials()

    print("→ Conectando al Sheet…")
    sheet = conectar_sheet()
    row = leer_ultima_fila(sheet)

    anfitrion = get_field(row, "nombre_anfitrion", "anfitrion", "nombre", default="anfitrion")
    email_dueno = get_field(row, "email_dueno", "email_anfitrion", "email")
    telefono_host = get_field(row, "telefono_host", "whatsapp", "whatsapp_contacto")
    print(f"→ Anfitrión: {anfitrion} ({email_dueno or 'sin email'})")

    try:
        cantidad = int(get_field(row, "cantidad_propiedades", default="1") or "1")
    except ValueError:
        cantidad = 1
    cantidad = max(1, min(cantidad, MAX_PROPIEDADES))
    print(f"→ Procesando {cantidad} propiedad(es)…")

    propiedades: list[Propiedad] = []
    for i in range(1, cantidad + 1):
        p = procesar_propiedad(row, i)
        if p:
            propiedades.append(p)
    if not propiedades:
        print("✗ Sin propiedades válidas. Abortando.")
        return

    # Detectar ciudad principal para decidir el modo
    geo_principal = next((p for p in propiedades if p.lat and p.lng), None)
    ciudad = (geo_principal.ciudad if geo_principal else "Bariloche") or "Bariloche"
    es_bariloche = ciudad.lower().strip() in CIUDADES_PEDRO

    horario_checkin = get_field(row, "checkin", "horario_checkin", default="15:00")
    horario_checkout = get_field(row, "checkout", "horario_checkout", default="11:00")

    if es_bariloche:
        # ====================================================
        # MODO BARILOCHE: web original con todo el contenido
        # de Bariloche hardcoded (Catedral, cervecerías, hikes, etc.).
        # Se parametrizan las variables del anfitrión Y el welcome
        # se genera con Gemini en función de SU dirección específica
        # (qué hay cerca de SU depto en Bariloche).
        # ====================================================
        print(f"→ Modo BARILOCHE detectado ({ciudad})")
        # Buscar lugares cercanos REALES a la dirección del anfitrión
        # para que el welcome diga algo concreto sobre SU zona en Bari.
        if geo_principal:
            print(f"→ Buscando qué hay cerca de {geo_principal.direccion} para el welcome…")
            lugares_cerca = lugares_por_categoria(geo_principal.lat, geo_principal.lng, radius=1500)
            flat = [item for items in lugares_cerca.values() for item in items][:8]
            print("→ Generando welcome contextual con Gemini para la dirección del anfitrión…")
            for p in propiedades:
                if p.lat and p.lng:
                    p.welcome = generar_welcome(
                        "Bariloche", p.barrio or "Bariloche", p.formatted, p.nombre,
                        lugares_cercanos=flat,
                    )
                else:
                    # Fallback si no hubo geocoding
                    p.welcome = {
                        "es": {"title": f"Bienvenidos al {p.nombre}",
                               "sub": f"En {p.barrio or 'Bariloche'}"},
                        "en": {"title": f"Welcome to {p.nombre}",
                               "sub": f"In {p.barrio or 'Bariloche'}"},
                        "pt": {"title": f"Bem-vindos ao {p.nombre}",
                               "sub": f"Em {p.barrio or 'Bariloche'}"},
                    }
        else:
            for p in propiedades:
                p.welcome = {
                    "es": {"title": f"Bienvenidos al {p.nombre}",
                           "sub": f"En {p.barrio or 'Bariloche'}"},
                    "en": {"title": f"Welcome to {p.nombre}",
                           "sub": f"In {p.barrio or 'Bariloche'}"},
                    "pt": {"title": f"Bem-vindos ao {p.nombre}",
                           "sub": f"Em {p.barrio or 'Bariloche'}"},
                }

        propiedades_dict = [p.__dict__ for p in propiedades]
        ctx = {
            "ciudad": ciudad,
            "telefono_host": telefono_host,
            "anfitrion": anfitrion,
            "checkin": horario_checkin,
            "checkout": horario_checkout,
            "propiedades": propiedades_dict,
        }
        template_name = TEMPLATE_BARILOCHE

    else:
        # ====================================================
        # MODO GENÉRICO: cualquier otra ciudad.
        # Places API + Gemini hacen el laburo de personalización.
        # ====================================================
        print(f"→ Modo GENÉRICO ({ciudad}) — generando contenido con Places + Gemini")
        if geo_principal:
            print(f"→ Buscando lugares cercanos a {geo_principal.ciudad or geo_principal.direccion}…")
            lugares = lugares_por_categoria(geo_principal.lat, geo_principal.lng)
            lugares = describir_lugares(lugares, geo_principal.ciudad)
            for p in propiedades:
                p.lugares = lugares
            print("→ Re-generando welcome con lugares reales como contexto…")
            flat_lugares = [item for items in lugares.values() for item in items][:8]
            for p in propiedades:
                if p.lat and p.lng:
                    p.welcome = generar_welcome(
                        p.ciudad, p.barrio, p.formatted, p.nombre, lugares_cercanos=flat_lugares
                    )
            print("→ Buscando esenciales más cercanos…")
            esenciales = obtener_esenciales(geo_principal.lat, geo_principal.lng)
        else:
            for p in propiedades:
                p.lugares = {k: [] for k, *_ in CATEGORIAS}
            esenciales = {key: None for key, *_ in ESENCIALES}

        region_label = geo_principal.region if geo_principal else ""
        geo_full = geocode(geo_principal.direccion) if geo_principal else None
        country = geo_full["country"] if geo_full else "Argentina"
        marca = generar_marca(ciudad, country)
        tip = generar_tip_local(ciudad, geo_principal.barrio if geo_principal else "", country)
        print("→ Generando tips locales con Gemini…")
        tips_locales = generar_tips_locales(ciudad, region_label, country)
        print("→ Generando outfit recommendations con Gemini…")
        outfit_actividades = (
            generar_outfit_actividades(ciudad, region_label, geo_principal.lat, geo_principal.lng)
            if geo_principal else []
        )
        print("→ Generando info útil completa con Gemini (autos, colectivos, temporadas, hikes, excursiones)…")
        info = generar_info_completa(ciudad, region_label, country)
        # Enriquecer info.autos con alquileres REALES de la zona via Places
        if geo_principal:
            print("→ Buscando alquileres de auto cerca de la propiedad…")
            alquileres = obtener_alquileres_auto(geo_principal.lat, geo_principal.lng)
            if not isinstance(info.get("autos"), dict):
                info["autos"] = {}
            info["autos"]["alquileres_cercanos"] = alquileres
            print(f"  → {len(alquileres)} alquileres encontrados")

        propiedades_dict = [p.__dict__ for p in propiedades]
        ctx = {
            "marca": marca,
            "ciudad": ciudad,
            "region": region_label,
            "tip_local": tip,
            "tips_locales": tips_locales,
            "outfit_actividades": outfit_actividades,
            "esenciales": esenciales,
            "info": info,
            "pedro_promos": False,
            "telefono_host": telefono_host,
            "anfitrion": anfitrion,
            "checkin": horario_checkin,
            "checkout": horario_checkout,
            "categorias": [
                {"key": k, "es": es, "en": en, "pt": pt}
                for k, es, en, pt, *_ in CATEGORIAS
            ],
            "propiedades": propiedades_dict,
        }
        template_name = TEMPLATE_GENERICO

    slug = slugify(anfitrion) or "guest"
    out = render(ctx, slug, template_name)

    link = f"{GITHUB_PAGES_BASE}/sites/{slug}/"
    try:
        enviar_email("volpacchio47@gmail.com", link, anfitrion, ciudad, propiedades=propiedades_dict)
    except Exception as e:
        print(f"⚠️  Email no enviado: {e}")

    print(f"✓ Listo → {out}")


if __name__ == "__main__":
    main()
