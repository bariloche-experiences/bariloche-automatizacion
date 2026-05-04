"""
test_local.py — Probá el sistema en TU PC con APIs reales antes de pushear.

USO:
  1. Activá tu .venv (o instalá deps: pip install -r requirements.txt)
  2. Tené el credentials.json en este directorio (descargalo de Google Cloud)
  3. Creá un .env con: GOOGLE_MAPS_API_KEY=...   GEMINI_API_KEY=...
  4. Ejecutá:  python test_local.py "Av. Bustillo 5000, Bariloche"
              python test_local.py "Av. Colón 1500, Mar del Plata"
              python test_local.py "Cabildo 2200, San Isidro"

Genera sites/test/index.html que podés abrir en el navegador y ver el resultado real.
NO toca el Sheet, NO manda email — es solo prueba local.
"""

import os
import sys
from pathlib import Path

# Permitir cargar .env si existe (sin dependencia extra)
env_file = Path(".env")
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# Setear vars vacías para que main.py no falle al importar
os.environ.setdefault("SHEET_ID", "test")
os.environ.setdefault("EMAIL_USER", "test@test.com")
os.environ.setdefault("EMAIL_PASS", "test")
os.environ.setdefault("GITHUB_PAGES_BASE", "https://example.com")

if not os.environ.get("GOOGLE_MAPS_API_KEY"):
    print("✗ Falta GOOGLE_MAPS_API_KEY. Definila en .env o como variable de entorno.")
    sys.exit(1)
if not os.environ.get("GEMINI_API_KEY"):
    print("✗ Falta GEMINI_API_KEY.")
    sys.exit(1)

from main import (
    CIUDADES_PEDRO, geocode, lugares_por_categoria, describir_lugares,
    obtener_esenciales, obtener_alquileres_auto, generar_marca, generar_welcome,
    generar_tip_local, generar_tips_locales, generar_outfit_actividades,
    generar_info_completa, normalize_video, render, Propiedad, CATEGORIAS, ESENCIALES,
    TEMPLATE_BARILOCHE, TEMPLATE_GENERICO,
)


def test(direccion: str, nombre_propiedad: str = "Casa de Prueba"):
    print(f"\n{'='*60}")
    print(f"TEST: {direccion}")
    print(f"{'='*60}\n")

    print("→ Geocoding…")
    geo = geocode(direccion)
    if not geo:
        print("✗ No se pudo geocodificar la dirección. Abortando.")
        return
    print(f"  ✓ Ciudad: {geo['ciudad']}, Barrio: {geo['barrio']}, Región: {geo['region']}")
    print(f"  ✓ Coords: {geo['lat']}, {geo['lng']}")

    es_bariloche = geo["ciudad"].lower().strip() in CIUDADES_PEDRO
    print(f"  ✓ Modo: {'BARILOCHE' if es_bariloche else 'GENÉRICO'}")

    # Crear una propiedad de prueba
    p = Propiedad(
        idx=1,
        nombre=nombre_propiedad,
        direccion=geo["formatted"],
        lat=geo["lat"], lng=geo["lng"],
        barrio=geo["barrio"], ciudad=geo["ciudad"],
        formatted=geo["formatted"],
        maps_link=f"https://www.google.com/maps/search/?api=1&query={direccion.replace(' ','+')}",
        instagram="",
        video_es=normalize_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        video_en={"kind": "none", "embed_url": "", "raw_url": "", "message": ""},
        wifi_ssid="WIFI_TEST", wifi_pass="test1234",
        welcome={}, recomendaciones=[],
    )

    if es_bariloche:
        # Modo Bariloche: solo welcome dinámico
        print("→ Buscando lugares cerca para welcome…")
        lugares_cerca = lugares_por_categoria(p.lat, p.lng, radius=1500)
        flat = [item for items in lugares_cerca.values() for item in items][:8]
        print(f"  ✓ {len(flat)} lugares encontrados cerca")
        print("→ Generando welcome con Gemini…")
        p.welcome = generar_welcome("Bariloche", p.barrio, p.formatted, p.nombre, lugares_cercanos=flat)
        print(f"  ✓ Welcome ES: \"{p.welcome.get('es', {}).get('sub', '')}\"")

        ctx = {
            "ciudad": geo["ciudad"],
            "telefono_host": "+5491131952798",
            "anfitrion": "Test Anfitrion",
            "checkin": "15:00", "checkout": "10:00",
            "propiedades": [p.__dict__],
        }
        out = render(ctx, "test", TEMPLATE_BARILOCHE)
    else:
        # Modo genérico: pipeline completo
        print("→ Lugares por categoría (Places API)…")
        lugares = lugares_por_categoria(p.lat, p.lng)
        for k, items in lugares.items():
            print(f"  ✓ {k}: {len(items)} lugares")
        print("→ Descripciones por Gemini…")
        lugares = describir_lugares(lugares, geo["ciudad"])
        p.lugares = lugares
        flat = [item for items in lugares.values() for item in items][:8]
        print("→ Welcome contextual (Gemini)…")
        p.welcome = generar_welcome(geo["ciudad"], geo["barrio"], geo["formatted"], p.nombre, lugares_cercanos=flat)
        print(f"  ✓ Welcome ES: \"{p.welcome.get('es', {}).get('sub', '')}\"")
        print("→ Esenciales (farmacia/cajero/hospital/nafta)…")
        esenciales = obtener_esenciales(p.lat, p.lng)
        for k, v in esenciales.items():
            print(f"  ✓ {k}: {v['nombre'] if v else '—'}")
        print("→ Marca (theme + emoji)…")
        marca = generar_marca(geo["ciudad"], geo["country"])
        print(f"  ✓ theme={marca.get('theme')}  badge=\"{marca.get('hero_badge')}\"")
        print("→ Tips locales (Gemini)…")
        tips_locales = generar_tips_locales(geo["ciudad"], geo["region"], geo["country"])
        print(f"  ✓ {len(tips_locales)} tips generados")
        print("→ Outfit recommendations (Gemini)…")
        outfit_actividades = generar_outfit_actividades(geo["ciudad"], geo["region"], p.lat, p.lng)
        print(f"  ✓ {len(outfit_actividades)} actividades generadas")
        print("→ Info completa (Gemini): instrucciones/autos/colectivos/temporadas/hikes/excursiones…")
        info = generar_info_completa(geo["ciudad"], geo["region"], geo["country"])
        print(f"  ✓ instrucciones: {len(info.get('instrucciones', []))}")
        print(f"  ✓ temporadas:    {len(info.get('temporadas', []))}")
        print(f"  ✓ hikes:         {len(info.get('hikes', []))}")
        print(f"  ✓ excursiones:   {len(info.get('excursiones', []))}")
        print(f"  ✓ autos.tips:    {len(info.get('autos', {}).get('tips', []))}")
        print(f"  ✓ colectivos.lineas: {len(info.get('colectivos', {}).get('lineas_principales', []))}")
        print("→ Alquileres de auto reales cerca (Places)…")
        alquileres = obtener_alquileres_auto(p.lat, p.lng)
        print(f"  ✓ {len(alquileres)} alquileres encontrados")
        for a in alquileres:
            print(f"    - {a['nombre']} · {a.get('telefono', 'sin tel')} · ⭐{a.get('rating', '?')}")
        if not isinstance(info.get("autos"), dict):
            info["autos"] = {}
        info["autos"]["alquileres_cercanos"] = alquileres
        tip = generar_tip_local(geo["ciudad"], geo["barrio"], geo["country"])

        ctx = {
            "marca": marca, "ciudad": geo["ciudad"], "region": geo["region"],
            "tip_local": tip, "tips_locales": tips_locales,
            "outfit_actividades": outfit_actividades, "esenciales": esenciales,
            "info": info, "pedro_promos": False,
            "telefono_host": "+5491131952798", "anfitrion": "Test Anfitrion",
            "checkin": "15:00", "checkout": "11:00",
            "categorias": [{"key": k, "es": es, "en": en, "pt": pt}
                           for k, es, en, pt, *_ in CATEGORIAS],
            "propiedades": [p.__dict__],
        }
        out = render(ctx, "test", TEMPLATE_GENERICO)

    print(f"\n✓ Listo: abrí en el navegador → file://{Path(out).resolve()}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    direccion = sys.argv[1]
    nombre = sys.argv[2] if len(sys.argv) > 2 else "Casa de Prueba"
    test(direccion, nombre)
