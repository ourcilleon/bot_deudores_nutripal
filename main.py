import os
import json
import threading
import requests
import telebot
from telebot import types
from flask import Flask

# --- SERVIDOR FLASK PARA RENDER ---
app = Flask('')

@app.route('/')
def home():
    return "Bot de Telegram activo y corriendo."

def run_http():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_http, daemon=True).start()

# --- CONFIGURACIÓN Y VARIABLES DE ENTORNO ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
APPS_SCRIPT_URL = os.environ.get('APPS_SCRIPT_URL')

allowed_users_raw = os.environ.get('ALLOWED_USERS', '')
ALLOWED_USERS = [int(uid.strip()) for uid in allowed_users_raw.split(',') if uid.strip().isdigit()]

if not TELEGRAM_TOKEN:
    print("❌ ERROR CRÍTICO: 'TELEGRAM_TOKEN' no configurado.")
if not APPS_SCRIPT_URL:
    print("❌ ERROR CRÍTICO: 'APPS_SCRIPT_URL' no configurado.")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
user_states = {}

def enviar_a_sheets(datos):
    headers = {'Content-Type': 'application/json'}
    try:
        respuesta = requests.post(
            APPS_SCRIPT_URL, 
            data=json.dumps(datos), 
            headers=headers, 
            timeout=15
        )
        return respuesta.json()
    except Exception as e:
        print(f"❌ Error al conectar con Google Sheets: {e}")
        return {"status": "error", "message": str(e)}

def formato_clp(monto):
    return f"${int(monto):,}".replace(",", ".")

def extraer_monto_valido(texto):
    texto_limpio = texto.strip().replace(".", "").replace(",", "").replace("$", "")
    if not texto_limpio.isdigit():
        return None
    return int(texto_limpio)

def menu_principal():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_nuevo = types.KeyboardButton("➕ Agregar Deudor")
    btn_abono = types.KeyboardButton("💸 Registrar Abono")
    btn_saldo = types.KeyboardButton("🔍 Consultar Saldo")
    btn_cancelar = types.KeyboardButton("❌ Cancelar")
    markup.add(btn_nuevo, btn_abono, btn_saldo, btn_cancelar)
    return markup

@bot.message_handler(func=lambda message: len(ALLOWED_USERS) > 0 and message.from_user.id not in ALLOWED_USERS)
def acceso_denegado(message):
    bot.reply_to(message, "⛔ *Acceso denegado.* Este bot es privado.", parse_mode="Markdown")

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_states.pop(message.chat.id, None)
    texto = (
        "🤖 *Bot de Registro de Deudores*\n\n"
        "Selecciona una opción del menú inferior para comenzar:"
    )
    bot.send_message(message.chat.id, texto, reply_markup=menu_principal(), parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "❌ Cancelar")
def cancelar(message):
    user_states.pop(message.chat.id, None)
    bot.send_message(message.chat.id, "Operación cancelada. ¿Qué deseas hacer?", reply_markup=menu_principal())

# --- PASO 1: INICIO DE FLUJOS ---
@bot.message_handler(func=lambda m: m.text == "➕ Agregar Deudor" or m.text == "/nuevo")
def inicio_nuevo(message):
    user_states[message.chat.id] = {'step': 'nuevo_nombre'}
    bot.send_message(message.chat.id, "📝 Ingresa el *Nombre y Apellido* del nuevo deudor:", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "💸 Registrar Abono" or m.text == "/abono")
def inicio_abono(message):
    user_states[message.chat.id] = {'step': 'abono_nombre'}
    bot.send_message(message.chat.id, "💸 Ingresa el *Nombre y Apellido* del deudor que realizará el abono:", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🔍 Consultar Saldo" or m.text == "/saldo")
def inicio_saldo(message):
    user_states[message.chat.id] = {'step': 'saldo_nombre'}
    bot.send_message(message.chat.id, "🔍 Ingresa el *Nombre y Apellido* del deudor a consultar:", parse_mode="Markdown")

# --- PASO 2: PROCESAMIENTO ---
@bot.message_handler(func=lambda message: message.chat.id in user_states)
def procesar_pasos(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id, {})
    step = state.get('step')

    if step == 'nuevo_nombre':
        user_states[chat_id] = {'step': 'nuevo_monto', 'nombre': message.text.strip()}
        bot.send_message(chat_id, f"Monto de la deuda inicial para *{message.text.strip()}* (solo números, ej: 150000):", parse_mode="Markdown")
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

    if step == 'abono_nombre':
        user_states[chat_id] = {'step': 'abono_monto', 'nombre': message.text.strip()}
        bot.send_message(chat_id, f"Monto a abonar para *{message.text.strip()}* (solo números, ej: 25000):", parse_mode="Markdown")
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

    if step == 'saldo_nombre':
        nombre = message.text.strip()
        datos = {"accion": "saldo", "nombre": nombre}
        respuesta = enviar_a_sheets(datos)
        
        if respuesta.get("status") == "ok":
            nombre_real = respuesta.get("nombre")
            deuda = respuesta.get("deuda")
            abonos = respuesta.get("abonos")
            saldo = respuesta.get("saldo")
            historial = respuesta.get("historial", [])
            
            texto = (
                f"📊 *Estado de Cuenta: {nombre_real}*\n\n"
                f"• Deuda Inicial: {formato_clp(deuda)}\n"
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

print("Iniciando bot con historial de abonos...")
bot.infinity_polling()
