"""Bot de Telegram para el registro de Deudores y Abonos - Bot Nutripal."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import os
import sys
import threading
from typing import Final

import requests
import telebot
from telebot import types

# --- LOGGING ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# --- SERVIDOR HTTP NATIVO (LIBRERÍA ESTÁNDAR) ---
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Bot Deudores Nutripal Activo".encode("utf-8"))

    def log_message(self, format, *args):
        pass


def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    logger.info(f"Servidor HTTP dummy iniciado en el puerto {port}")
    server.serve_forever()


# --- CONFIGURACIÓN Y VARIABLES DE ENTORNO ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
APPS_SCRIPT_URL = os.environ.get('APPS_SCRIPT_URL', '').strip()

allowed_users_raw = os.environ.get('ALLOWED_USERS', '')
ALLOWED_USERS: Final[list[int]] = [
    int(uid.strip()) for uid in allowed_users_raw.split(',') if uid.strip().isdigit()
]

if not TELEGRAM_TOKEN:
    logger.error("❌ ERROR CRÍTICO: 'TELEGRAM_TOKEN' no configurado.")
if not APPS_SCRIPT_URL:
    logger.error("❌ ERROR CRÍTICO: 'APPS_SCRIPT_URL' no configurado.")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
user_states = {}


# --- FUNCIONES AUXILIARES ---
def enviar_a_sheets(datos: dict) -> dict:
    headers = {'Content-Type': 'application/json'}
    try:
        respuesta = requests.post(
            APPS_SCRIPT_URL, 
            data=json.dumps(datos), 
            headers=headers, 
            timeout=45,
            allow_redirects=True
        )
        logger.info(f"Respuesta HTTP {respuesta.status_code}: {respuesta.text}")
        return respuesta.json()
    except Exception as e:
        logger.error(f"❌ Error al conectar con Google Sheets: {e}")
        return {"status": "error", "message": str(e)}


def formato_clp(monto: int | float) -> str:
    return f"${int(monto):,}".replace(",", ".")


def extraer_monto_valido(texto: str) -> int | None:
    texto_limpio = texto.strip().replace(".", "").replace(",", "").replace("$", "")
    if not texto_limpio.isdigit():
        return None
    return int(texto_limpio)


def limpiar_nombre(texto: str) -> str:
    return " ".join(texto.strip().split())


def menu_principal() -> types.ReplyKeyboardMarkup:
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_nuevo = types.KeyboardButton("👤 Nuevo Deudor")
    btn_agregar_deuda = types.KeyboardButton("➕ Agregar Deuda")
    btn_abono = types.KeyboardButton("💸 Registrar Abono")
    btn_saldo = types.KeyboardButton("🔍 Consultar Saldo")
    btn_cancelar = types.KeyboardButton("❌ Cancelar")
    markup.add(btn_nuevo, btn_agregar_deuda, btn_abono, btn_saldo, btn_cancelar)
    return markup


# --- HANDLERS DE SEGURIDAD Y CONTROL ---
@bot.message_handler(func=lambda message: len(ALLOWED_USERS) > 0 and message.from_user.id not in ALLOWED_USERS)
def acceso_denegado(message):
    bot.reply_to(message, "⛔ *Acceso denegado.* Este bot es privado.", parse_mode="Markdown")


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_states.pop(message.chat.id, None)
    texto = (
        "🤖 *Bot de Registro de Deudores Nutripal*\n\n"
        "Selecciona una opción del menú inferior para comenzar:"
    )
    bot.send_message(message.chat.id, texto, reply_markup=menu_principal(), parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "❌ Cancelar")
def cancelar(message):
    user_states.pop(message.chat.id, None)
    bot.send_message(message.chat.id, "Operación cancelada. ¿Qué deseas hacer?", reply_markup=menu_principal())


# --- PASO 1: INICIO DE FLUJOS (COMANDOS Y BOTONES DEL MENÚ) ---

@bot.message_handler(func=lambda m: m.text in ["👤 Nuevo Deudor", "/nuevo"])
def inicio_nuevo_deudor(message):
    user_states[message.chat.id] = {'step': 'nuevo_nombre'}
    bot.send_message(message.chat.id, "📝 Ingresa el *Nombre y Apellido* del nuevo deudor:", parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text in ["➕ Agregar Deuda", "/masdeuda"])
def inicio_agregar_deuda(message):
    user_states[message.chat.id] = {'step': 'agregar_deuda_nombre'}
    bot.send_message(message.chat.id, "➕ Ingresa el *Nombre y Apellido* del deudor al que sumarás deuda:", parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text in ["💸 Registrar Abono", "/abono"])
def inicio_abono(message):
    user_states[message.chat.id] = {'step': 'abono_nombre'}
    bot.send_message(message.chat.id, "💸 Ingresa el *Nombre y Apellido* del deudor que realizará el abono:", parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text in ["🔍 Consultar Saldo", "/saldo"])
def inicio_saldo(message):
    user_states[message.chat.id] = {'step': 'saldo_nombre'}
    bot.send_message(message.chat.id, "🔍 Ingresa el *Nombre y Apellido* del deudor a consultar:", parse_mode="Markdown")


# --- PASO 2: PROCESAMIENTO DE PASOS INTERMEDIOS ---
@bot.message_handler(func=lambda message: message.chat.id in user_states)
def procesar_pasos(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id, {})
    step = state.get('step')

    # 1. CREAR NUEVO DEUDOR
    if step == 'nuevo_nombre':
        nombre_limpio = limpiar_nombre(message.text)
        user_states[chat_id] = {'step': 'nuevo_monto', 'nombre': nombre_limpio}
        bot.send_message(chat_id, f"Monto de la deuda inicial para *{nombre_limpio}* (solo números, ej: 150000):", parse_mode="Markdown")
        return

    if step == 'nuevo_monto':
        monto = extraer_monto_valido(message.text)
        if monto is None or monto <= 0:
            bot.send_message(chat_id, "⚠️ El monto debe contener **únicamente números**. Inténtalo de nuevo:", parse_mode="Markdown")
            return

        nombre = state['nombre']
        datos = {"accion": "nuevo", "nombre": nombre, "monto": monto}
        respuesta = enviar_a_sheets(datos)
        
        if respuesta.get("status") == "ok":
            bot.send_message(chat_id, f"✅ Deudor *{nombre}* agregado con deuda inicial de *{formato_clp(monto)}*.", parse_mode="Markdown", reply_markup=menu_principal())
        else:
            bot.send_message(chat_id, "⚠️ Ocurrió un error al guardar en la planilla.", reply_markup=menu_principal())
        user_states.pop(chat_id, None)
        return

    # 2. AGREGAR MÁS DEUDA
    if step == 'agregar_deuda_nombre':
        nombre_limpio = limpiar_nombre(message.text)
        user_states[chat_id] = {'step': 'agregar_deuda_monto', 'nombre': nombre_limpio}
        bot.send_message(chat_id, f"Monto de la **deuda adicional** a sumar para *{nombre_limpio}* (solo números, ej: 30000):", parse_mode="Markdown")
        return

    if step == 'agregar_deuda_monto':
        monto = extraer_monto_valido(message.text)
        if monto is None or monto <= 0:
            bot.send_message(chat_id, "⚠️ El monto debe contener **únicamente números**. Inténtalo de nuevo:", parse_mode="Markdown")
            return

        nombre = state['nombre']
        datos = {"accion": "agregar_deuda", "nombre": nombre, "monto": monto}
        respuesta = enviar_a_sheets(datos)
        
        if respuesta.get("status") == "ok":
            nombre_real = respuesta.get("nombre", nombre)
            deuda_inicial = respuesta.get("deuda_inicial", 0)
            deudas_agregadas = respuesta.get("deudas_agregadas", [])
            abonos = respuesta.get("abonos", 0)
            saldo = respuesta.get("saldo", 0)

            texto = (
                f"✅ *Deuda registrada para {nombre_real}*\n\n"
                f"• Deuda Inicial: {formato_clp(deuda_inicial)}\n"
            )

            for idx, d in enumerate(deudas_agregadas, start=1):
                texto += f"• Deuda Agregada {idx}: {formato_clp(d['monto'])}\n"

            texto += (
                f"• Total Abonado: {formato_clp(abonos)}\n"
                f"• *Saldo Pendiente: {formato_clp(saldo)}*"
            )

            bot.send_message(chat_id, texto, parse_mode="Markdown", reply_markup=menu_principal())
        else:
            bot.send_message(chat_id, f"❌ No se encontró al deudor *{nombre}*.", reply_markup=menu_principal())
        user_states.pop(chat_id, None)
        return

    # 3. REGISTRAR ABONO
    if step == 'abono_nombre':
        nombre_limpio = limpiar_nombre(message.text)
        user_states[chat_id] = {'step': 'abono_monto', 'nombre': nombre_limpio}
        bot.send_message(chat_id, f"Monto a abonar para *{nombre_limpio}* (solo números, ej: 25000):", parse_mode="Markdown")
        return

    if step == 'abono_monto':
        monto = extraer_monto_valido(message.text)
        if monto is None or monto <= 0:
            bot.send_message(chat_id, "⚠️ El monto debe contener **únicamente números**. Inténtalo de nuevo:", parse_mode="Markdown")
            return

        nombre = state['nombre']
        datos = {"accion": "abono", "nombre": nombre, "monto": monto}
        respuesta = enviar_a_sheets(datos)
        
        if respuesta.get("status") == "ok":
            saldo_actual = respuesta.get("saldo")
            bot.send_message(chat_id, f"✅ Abono de *{formato_clp(monto)}* registrado a *{nombre}*.\n\nSaldo pendiente: *{formato_clp(saldo_actual)}*", parse_mode="Markdown", reply_markup=menu_principal())
        else:
            bot.send_message(chat_id, f"❌ No se encontró al deudor *{nombre}* en la planilla.", reply_markup=menu_principal())
        user_states.pop(chat_id, None)
        return

    # 4. CONSULTAR SALDO
    if step == 'saldo_nombre':
        nombre = limpiar_nombre(message.text)
        datos = {"accion": "saldo", "nombre": nombre}
        respuesta = enviar_a_sheets(datos)
        
        if respuesta.get("status") == "ok":
            nombre_real = respuesta.get("nombre")
            deuda_inicial = respuesta.get("deuda_inicial", 0)
            deudas_agregadas = respuesta.get("deudas_agregadas", [])
            abonos = respuesta.get("abonos", 0)
            saldo = respuesta.get("saldo", 0)
            historial = respuesta.get("historial", [])
            
            texto = (
                f"📊 *Estado de Cuenta: {nombre_real}*\n\n"
                f"• Deuda Inicial: {formato_clp(deuda_inicial)}\n"
            )

            for idx, d in enumerate(deudas_agregadas, start=1):
                texto += f"• Deuda Agregada {idx}: {formato_clp(d['monto'])}\n"

            texto += (
                f"• Total Abonado: {formato_clp(abonos)}\n"
                f"• *Saldo Pendiente: {formato_clp(saldo)}*\n\n"
                f"📜 *Historial de Abonos:*"
            )
            
            if len(historial) == 0:
                texto += "\n_No registra abonos previos._"
            else:
                for item in historial:
                    texto += f"\n- {item['fecha']}: *{formato_clp(item['monto'])}*"

            bot.send_message(chat_id, texto, parse_mode="Markdown", reply_markup=menu_principal())
        else:
            bot.send_message(chat_id, f"❌ No se encontró al deudor *{nombre}*.", reply_markup=menu_principal())
        user_states.pop(chat_id, None)


# --- MAIN ---
def main() -> None:
    if not TELEGRAM_TOKEN:
        logger.error("Falta la variable TELEGRAM_TOKEN.")
        sys.exit(2)

    # Iniciar servidor HTTP en un hilo secundario
    threading.Thread(target=run_dummy_server, daemon=True).start()

    logger.info("Iniciando Bot de Deudores Nutripal en modo Polling...")
    bot.infinity_polling()


if __name__ == "__main__":
    main()
