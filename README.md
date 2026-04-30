# Bariloche Automatizacion

Sistema automatico:
1. Lee la ultima fila de Google Sheets.
2. Genera un sitio por propiedad desde `template_maestro.html`.
3. Envia email al dueno con el link generado.

## Variables de entorno (GitHub Secrets)
- `SPREADSHEET_ID`
- `WORKSHEET_NAME`
- `GOOGLE_CREDENTIALS_JSON_B64`
- `EMAIL_USER`
- `EMAIL_PASS`
- `SITE_BASE_URL`

## Ejecucion local
```bash
python3 -m pip install -r requirements.txt
python3 main.py
```
