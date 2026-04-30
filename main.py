import base64
import os
import re
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse

import gspread
from jinja2 import Environment, FileSystemLoader
from slugify import slugify


def get_env(name: str, required: bool = True, default: str = "") -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"Falta variable de entorno obligatoria: {name}")
    return value


def normalize_url(url: str) -> str:
    if not url:
        return ""

    raw = url.strip()

    if "youtube.com/watch" in raw:
        parsed = urlparse(raw)
        video_id = parse_qs(parsed.query).get("v", [""])[0]
        if video_id:
            return f"https://www.youtube.com/embed/{video_id}"

    if "youtu.be/" in raw:
        video_id = raw.rstrip("/").split("/")[-1]
        return f"https://www.youtube.com/embed/{video_id}"

    if "drive.google.com/file/d/" in raw:
        match = re.search(r"/file/d/([^/]+)/", raw)
        if match:
            return f"https://drive.google.com/file/d/{match.group(1)}/preview"

    if "drive.google.com/open?id=" in raw:
        parsed = urlparse(raw)
        file_id = parse_qs(parsed.query).get("id", [""])[0]
        if file_id:
            return f"https://drive.google.com/file/d/{file_id}/preview"

    if "photos.google.com" in raw:
        return raw

    return raw


def parse_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return fallback


def build_default_steps(depto_num: int, direccion: str) -> List[Dict[str, str]]:
    return [
        {
            "es": "🚗 Estaciona en el lugar indicado en el video",
            "en": "🚗 Park in the spot shown in the video",
            "pt": "🚗 Estacione no local indicado no video",
        },
        {
            "es": f"🏠 Tu depto es el Depto {depto_num} · {direccion}",
            "en": f"🏠 Your apartment is Apt {depto_num} · {direccion}",
            "pt": f"🏠 Seu apartamento e o Apto {depto_num} · {direccion}",
        },
        {
            "es": "🔑 Retira las llaves como se muestra en el video",
            "en": "🔑 Pick up the keys as shown in the video",
            "pt": "🔑 Retire as chaves conforme mostrado no video",
        },
    ]


def parse_property(row: Dict[str, Any], idx: int, direccion: str) -> Dict[str, Any]:
    prefix = f"d{idx}"

    nombre = row.get(f"nombre_propiedad_{prefix}") or row.get(f"nombre_{prefix}") or f"Propiedad {idx}"
    video_es = normalize_url(row.get(f"video_checkin_{prefix}", ""))
    video_en = normalize_url(row.get(f"video_checkin_en_{prefix}", video_es))
    maps_link = row.get(f"maps_link_{prefix}") or row.get(f"ubicacion_{prefix}") or "https://maps.google.com"

    return {
        "nombre": nombre,
        "nombre_video_es": row.get(f"nombre_video_es_{prefix}", f"{nombre} · Depto {idx}"),
        "nombre_video_en": row.get(f"nombre_video_en_{prefix}", f"{nombre} · Apt {idx}"),
        "video_desc_es": row.get(f"video_desc_es_{prefix}", "Estacionamiento, ubicacion y llaves"),
        "video_desc_en": row.get(f"video_desc_en_{prefix}", "Parking, location & keys"),
        "video_checkin_es": video_es,
        "video_checkin_en": video_en,
        "maps_link": maps_link,
        "wifi_ssid": row.get(f"wifi_ssid_{prefix}", "WIFI"),
        "wifi_pass": row.get(f"wifi_pass_{prefix}", "password"),
        "welcome_titulo": row.get(f"welcome_titulo_{prefix}", f"Bienvenidos a {nombre}"),
        "welcome_sub": row.get(f"welcome_sub_{prefix}", "Tu guia completa para disfrutar Bariloche"),
        "steps": build_default_steps(idx, direccion),
    }


def get_latest_row() -> Dict[str, Any]:
    spreadsheet_id = get_env("SPREADSHEET_ID")
    worksheet_name = os.environ.get("WORKSHEET_NAME", "").strip()

    gc = gspread.service_account(filename="credentials.json")
    spreadsheet = gc.open_by_key(spreadsheet_id)
    if worksheet_name:
        try:
            ws = spreadsheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            ws = spreadsheet.get_worksheet(0)
    else:
        ws = spreadsheet.get_worksheet(0)

    if ws is None:
        raise RuntimeError("No se encontro ninguna pestana en el Google Sheet")
    rows = ws.get_all_records()
    if not rows:
        raise RuntimeError("La hoja no tiene registros")
    return rows[-1]


def render_property_site(template_name: str, output_dir: Path, context: Dict[str, Any]) -> Path:
    env = Environment(loader=FileSystemLoader(str(Path.cwd())))
    template = env.get_template(template_name)
    html = template.render(**context)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "index.html"
    output_file.write_text(html, encoding="utf-8")
    return output_file


def enviar_email(destinatario: str, link_web: str) -> None:
    user = get_env("EMAIL_USER")
    password = get_env("EMAIL_PASS")

    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = destinatario
    msg["Subject"] = "Tu web ya esta lista 🚀"
    msg.set_content(f"Hola,\n\nTu web ya esta publicada:\n{link_web}\n\nGracias.")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)


def build_credentials_from_env() -> None:
    if Path("credentials.json").exists():
        return

    encoded = os.environ.get("GOOGLE_CREDENTIALS_JSON_B64", "").strip()
    raw_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip()

    if encoded:
        decoded = base64.b64decode(encoded).decode("utf-8")
        Path("credentials.json").write_text(decoded, encoding="utf-8")
        return

    if raw_json:
        Path("credentials.json").write_text(raw_json, encoding="utf-8")
        return

    raise RuntimeError("No se encontro credencial de Google en variables de entorno")


def get_owner_email(row: Dict[str, Any]) -> str:
    for key in ("email_dueno", "email", "correo", "mail_dueno"):
        value = str(row.get(key, "")).strip()
        if value:
            return value
    return get_env("EMAIL_USER", required=False, default="").strip()


def main() -> None:
    build_credentials_from_env()

    row = get_latest_row()
    cantidad = min(parse_int(row.get("cantidad_propiedades", 1), 1), 10)

    marca = row.get("marca", "Bariloche Experiencias")
    ciudad = row.get("ciudad", "Bariloche")
    direccion = row.get("direccion", "La Florida 3566")
    telefono_host = str(row.get("telefono_host", "5491131952798"))
    checkin = row.get("checkin", "15:00")
    checkout = row.get("checkout", "10:00")
    email_dueno = get_owner_email(row)

    propiedades = [parse_property(row, idx, direccion) for idx in range(1, cantidad + 1)]

    template_name = os.environ.get("TEMPLATE_NAME", "template_maestro.html")
    output_root = Path(os.environ.get("OUTPUT_ROOT", "outputs"))
    base_url = os.environ.get("SITE_BASE_URL", "")

    for prop in propiedades:
        slug = slugify(prop["nombre"]) or f"propiedad-{propiedades.index(prop)+1}"
        out_dir = output_root / slug
        render_property_site(
            template_name=template_name,
            output_dir=out_dir,
            context={
                "marca": marca,
                "ciudad": ciudad,
                "direccion": direccion,
                "telefono_host": telefono_host,
                "checkin": checkin,
                "checkout": checkout,
                "welcome_titulo": prop["welcome_titulo"],
                "welcome_sub": prop["welcome_sub"],
                "propiedades": [prop],
            },
        )

        link_web = f"{base_url.rstrip('/')}/{slug}/" if base_url else str((out_dir / 'index.html').resolve())
        if email_dueno:
            enviar_email(email_dueno, link_web)
            print(f"Email enviado a: {email_dueno}")
        else:
            print("No se encontro email de destino, se omite envio")

        print(f"Web generada: {out_dir / 'index.html'}")


if __name__ == "__main__":
    main()
