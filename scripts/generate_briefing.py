#!/usr/bin/env python3
"""
Genera el pre-market briefing diario para https://simoninversiones.netlify.app

Usa Anthropic API con el server tool web_search para investigar mercados
del día y producir un JSON estructurado que se escribe a data/latest.js.

Requiere ANTHROPIC_API_KEY en el entorno.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import anthropic

MODEL = "claude-sonnet-4-6"
# Eastern Time. Durante EDT (mar-nov) usar -4. Durante EST (nov-mar) usar -5.
# Lo determinamos por la fecha — Python no tiene zoneinfo de pytz por defecto.
def _et_offset(now_utc: datetime) -> timezone:
    """Aproxima EDT/EST a partir de la fecha UTC. Para precisión completa, usar zoneinfo."""
    # DST en EE.UU.: segundo domingo de marzo a primer domingo de noviembre.
    # Aproximación simple: marzo a noviembre = EDT (-4), resto = EST (-5).
    month = now_utc.month
    if 3 <= month <= 10:
        return timezone(timedelta(hours=-4))
    if month == 11 and now_utc.day < 7:
        return timezone(timedelta(hours=-4))
    if month == 3 and now_utc.day >= 8:
        return timezone(timedelta(hours=-4))
    return timezone(timedelta(hours=-5))


JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"type": "string", "description": "Fecha del briefing en formato YYYY-MM-DD"},
        "generated_at": {"type": "string", "description": "ISO timestamp con zona ET"},
        "macro": {
            "type": "array",
            "description": "4-5 bullets de contexto macro con fuente citada",
            "items": {
                "type": "object",
                "properties": {
                    "point": {"type": "string"},
                    "source": {"type": "string"},
                },
                "required": ["point", "source"],
                "additionalProperties": False,
            },
        },
        "watchlist": {
            "type": "array",
            "description": "3-5 ideas de watchlist con análisis completo",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "name": {"type": "string"},
                    "thesis": {"type": "string"},
                    "risk": {"type": "string", "enum": ["Bajo", "Medio", "Alto"]},
                    "catalyst": {"type": "string"},
                    "level": {"type": "string"},
                    "action": {"type": "string", "enum": ["Watch", "Consider", "Avoid"]},
                },
                "required": ["ticker", "name", "thesis", "risk", "catalyst", "level", "action"],
                "additionalProperties": False,
            },
        },
        "caution": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "detail": {"type": "string"},
            },
            "required": ["summary", "detail"],
            "additionalProperties": False,
        },
        "top_picks": {
            "type": "array",
            "description": "Exactamente 3 picks ranqueados",
            "items": {
                "type": "object",
                "properties": {
                    "rank": {"type": "integer"},
                    "ticker": {"type": "string"},
                    "name": {"type": "string"},
                    "action": {"type": "string", "enum": ["Watch", "Consider", "Avoid"]},
                    "reason": {"type": "string"},
                    "role": {"type": "string"},
                },
                "required": ["rank", "ticker", "name", "action", "reason", "role"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["date", "generated_at", "macro", "watchlist", "caution", "top_picks"],
    "additionalProperties": False,
}


SYSTEM_PROMPT = """Eres un analista financiero personal de Simon Osorio. Generas su briefing pre-market diario.

CONTEXTO: Simon es fundador de una firma boutique (Osorio Capital Management) enfocada en inversiones bajo/medio riesgo. Mercados objetivo: EE.UU. y Latinoamérica. Este briefing es uso personal (no contenido público para clientes), por lo que puedes usar tickers específicos y dar análisis concreto.

UNIVERSO DE INSTRUMENTOS A CONSIDERAR (bajo/medio riesgo):
- ETFs broad market (VTI, VOO, ITOT) y sectoriales conservadores
- Bonos investment-grade y bond ETFs (AGG, BND, LQD)
- Fondos indexados
- Acciones grandes y estables (blue chips)
- Dividend stocks y dividend growth ETFs (VIG, SCHD, NOBL)
- REITs conservadores (VNQ, residencial/industrial diversificado)
- Money market funds
- Treasury bills (BIL, SGOV)
- Portafolios diversificados (target-date, balanced)

ESTRUCTURA DEL OUTPUT (JSON con este esquema):

1. macro: 4-5 bullets de contexto del día. Cada uno con punto + fuente citada.
   - Tasas (Fed funds, 10Y Treasury, 30Y, T-Bills cortos)
   - Inflación reciente (CPI, PCE, PPI)
   - Calendario económico del día (FOMC, NFP, releases)
   - Divisas LatAm (USD/COP, USD/MXN)
   - Eventos relevantes (earnings, geopolítica, energía)

2. watchlist: 3-5 ideas con ticker, nombre, tesis (1-2 líneas), riesgo (Bajo/Medio/Alto), catalizador del día, nivel a vigilar, acción (Watch/Consider/Avoid).

3. caution: una señal de cautela del día — algo a NO comprar o a vigilar como riesgo.

4. top_picks: EXACTAMENTE 3 picks ranqueados (rank 1, 2, 3). Cada uno con ticker, nombre, acción (Watch/Consider/Avoid), razón concreta del día, y rol en portafolio (ej. "Parking de liquidez", "Acumulación de calidad a largo plazo", "Núcleo equity").

REGLAS DURAS:
- NUNCA inventes datos. Usa SIEMPRE web_search para verificar precios, yields, eventos, fechas.
- CITA fuentes en el campo "source" de cada bullet macro (Bloomberg, Reuters, FT, Trading Economics, FRED, CNBC, Yahoo Finance, etc.).
- Si no hay datos disponibles para algún punto, declara "datos no disponibles" en lugar de inventar.
- Usa el marco Watch / Consider / Avoid. NUNCA digas "compra X" como orden directa.
- Tono: profesional, sobrio, español, sin promesas de rentabilidad.
- Cada idea debe tener tesis específica del día — no análisis genérico.

PROCESO:
1. Usa web_search varias veces para reunir datos verificados del día.
2. Sintetiza el contexto macro.
3. Selecciona watchlist y top picks consistentes con el contexto.
4. Devuelve SOLO el JSON estructurado conforme al esquema. Sin texto adicional, sin markdown."""


def build_user_message(date_str: str, et_iso: str) -> str:
    return f"""Genera el pre-market briefing del día {date_str} para Simon Osorio.

date: "{date_str}"
generated_at: "{et_iso}"

Investiga vía web_search los siguientes datos antes de responder:
1. Futuros S&P 500 pre-apertura y cierre previo del SPX
2. Yields Treasury: 10Y, 30Y, 3M T-Bill (último dato disponible)
3. Fed funds rate actual y próximas decisiones FOMC
4. Inflación reciente (CPI, PPI último release)
5. Calendario económico del día en EE.UU.
6. USD/COP y USD/MXN último valor
7. Earnings o eventos macro relevantes hoy
8. Yields y precios actuales de ETFs candidatos del universo (BIL, SGOV, VTI, VIG, SCHD, VNQ, TLT, AGG, BND, LQD, según relevancia del día)

Después de investigar, produce el JSON conforme al esquema. Exactamente 3 picks en top_picks."""


def call_claude(client: anthropic.Anthropic, user_message: str, max_iterations: int = 5):
    """Llama a Claude con web_search y maneja pause_turn hasta obtener respuesta final."""
    messages = [{"role": "user", "content": user_message}]
    iteration = 0

    while iteration < max_iterations:
        response = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            output_config={"format": {"type": "json_schema", "schema": JSON_SCHEMA}},
            messages=messages,
        )

        if response.stop_reason == "pause_turn":
            # Server-side tool loop hit iteration limit; resume.
            messages = [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": response.content},
            ]
            iteration += 1
            continue

        return response

    raise RuntimeError(f"Excedido max_iterations ({max_iterations}) sin completar el briefing")


def extract_json(response) -> dict:
    """Extrae el primer bloque de texto y parsea como JSON."""
    text = next((block.text for block in response.content if block.type == "text"), None)
    if not text:
        raise RuntimeError("La respuesta no contiene bloque de texto. Stop reason: " + str(response.stop_reason))

    # output_config.format garantiza JSON válido, pero por seguridad limpiamos
    # cualquier wrap accidental.
    text = text.strip()
    if text.startswith("```"):
        # quitar fence si aparece
        lines = text.split("\n")
        text = "\n".join(line for line in lines if not line.startswith("```"))

    return json.loads(text)


def write_briefing(briefing: dict, output_path: str = "data/latest.js") -> None:
    """Escribe el briefing como window.BRIEFING = {...};"""
    js_content = (
        "window.BRIEFING = "
        + json.dumps(briefing, ensure_ascii=False, indent=2)
        + ";\n"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(js_content)


def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY no está definida en el entorno", file=sys.stderr)
        return 1

    now_utc = datetime.now(timezone.utc)
    et = _et_offset(now_utc)
    now_et = now_utc.astimezone(et)
    date_str = now_et.strftime("%Y-%m-%d")
    et_iso = now_et.strftime("%Y-%m-%dT%H:%M:%S%z")
    # Insertar dos puntos en el offset para formato ISO 8601 estándar
    et_iso = et_iso[:-2] + ":" + et_iso[-2:]

    print(f"[INFO] Generando briefing para {date_str} (ET: {et_iso})", file=sys.stderr)

    client = anthropic.Anthropic(api_key=api_key)
    user_message = build_user_message(date_str, et_iso)

    try:
        response = call_claude(client, user_message)
        briefing = extract_json(response)
    except json.JSONDecodeError as e:
        print(f"ERROR: JSON inválido en respuesta del modelo: {e}", file=sys.stderr)
        return 2
    except anthropic.APIError as e:
        print(f"ERROR: Anthropic API error: {e}", file=sys.stderr)
        return 3

    # Validación mínima de coherencia
    if briefing.get("date") != date_str:
        print(f"WARN: El modelo devolvió date={briefing.get('date')}, esperaba {date_str}. Forzando.", file=sys.stderr)
        briefing["date"] = date_str
    if not briefing.get("generated_at"):
        briefing["generated_at"] = et_iso
    if len(briefing.get("top_picks", [])) != 3:
        print(f"WARN: top_picks tiene {len(briefing.get('top_picks', []))} items, esperaba 3", file=sys.stderr)

    write_briefing(briefing)
    print(f"[OK] Escrito data/latest.js — {len(briefing['watchlist'])} ideas, {len(briefing['top_picks'])} picks", file=sys.stderr)

    # Imprime el JSON a stdout para que sea visible en GitHub Actions logs
    print(json.dumps(briefing, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
