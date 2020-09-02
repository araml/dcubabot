#!/usr/bin/python3
# -*- coding: utf-8 -*-

# STL imports
import sys
import logging
import pytz
import datetime

# Non STL imports
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ChatAction, ParseMode
from telegram.ext import (
    Updater, Filters, MessageHandler, CallbackQueryHandler)

# Local imports
# from tokenz import *
from models import *
from deletablecommandhandler import DeletableCommandHandler
from orga2Utils import noitip, asm
from errors import error_callback
import labos
from river import getMatches
from campus import is_campus_up
from vencimientoFinales import get_vencimiento, parse_cuatri_y_anio

# TODO:Move this out of here
logging.basicConfig(
    level=logging.INFO,
    # level=logging.DEBUG,
    format='[%(asctime)s] - [%(name)s] - [%(levelname)s] - %(message)s',
    filename="bots.log")


# Globals ...... yes, globals
logger = logging.getLogger("DCUBABOT")
admin_ids = [137497264, 187622583]  # @Rozen, @dgarro
command_handlers = {}


def start(update, context):
    msg = update.message.reply_text(
        "Hola, ¿qué tal? ¡Mandame /help si no sabés qué puedo hacer!",
        quote=False)
    context.sent_messages.append(msg)


def help(update, context):
    message_text = ""
    with db_session:
        for command in select(c for c in Command
                              if c.description and c.enabled).order_by(lambda c: c.name):
            message_text += "/" + command.name + " - " + command.description + "\n"
    msg = update.message.reply_text(message_text, quote=False)
    context.sent_messages.append(msg)


def estasvivo(update, context):
    msg = update.message.reply_text("Sí, estoy vivo.", quote=False)
    context.sent_messages.append(msg)


def list_buttons(update, context, listable_type):
    with db_session:
        buttons = select(l for l in listable_type if l.validated).order_by(
            lambda l: l.name)
        keyboard = []
        columns = 3
        for k in range(0, len(buttons), columns):
            row = [InlineKeyboardButton(
                text=button.name, url=button.url, callback_data=button.url)
                for button in buttons[k:k + columns]]

            keyboard.append(row)
        reply_markup = InlineKeyboardMarkup(keyboard)
        msg = update.message.reply_text(text="Grupos: ", disable_web_page_preview=True,
                                        reply_markup=reply_markup, quote=False)
        context.sent_messages.append(msg)


def listar(update, context):
    list_buttons(update, context, Obligatoria)


def listaroptativa(update, context):
    list_buttons(update, context, Optativa)


def listareci(update, context):
    list_buttons(update, context, ECI)


def listarotro(update, context):
    list_buttons(update, context, Otro)


def cubawiki(update, context):
    with db_session:
        group = select(o for o in Obligatoria if o.chat_id == update.message.chat.id and
                       o.cubawiki_url is not None).first()
        if group:
            msg = update.message.reply_text(group.cubawiki_url, quote=False)
            context.sent_messages.append(msg)


def log_message(update, context):
    user = str(update.message.from_user.id)
    chat = str(update.message.chat.id)
    # EAFP
    try:
        user_at_group = user + " @ " + update.message.chat.title
    except Exception:
        user_at_group = user
    user_at_group = f"{user_at_group}({chat})"
    logger.info(user_at_group + ": " + update.message.text)


def felizdia_text(today):
    meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
             "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    dia = str(today.day)
    mes = int(today.month)

    if mes == 3 and today.day == 8:
        return "Hoy es 8 de Marzo"
    else:
        mes = meses[mes - 1]
        return "Feliz " + dia + " de " + mes


# https://stackoverflow.com/a/11236372/1576803
def get_hora_feliz_dia():
    tz = pytz.timezone("America/Argentina/Buenos_Aires")
    now = datetime.datetime.now(tz).date()
    midnight = tz.localize(datetime.datetime.combine(now,
                                                     datetime.time(0, 0, 3)),
                           is_dst=None)
    return midnight.astimezone(pytz.utc).time()


def felizdia(context):
    today = datetime.date.today()
    msg_coronavirus = "Y recuerden amigos, cuarentena no es lo mismo que vacaciones, SEAN RESPONSABLES Y QUÉDENSE EN SUS CASITAS!"
    chat_id = -1001067544716
    context.bot.send_message(chat_id=chat_id, text=felizdia_text(today))
    context.bot.send_message(chat_id=chat_id, text=msg_coronavirus)
    mandar_imagen(chat_id, context, "files/heman.jpg")


def suggest_listable(update, context, listable_type):
    try:
        name, url = " ".join(context.args).split("|")
        if not (name and url):
            raise Exception("not userneim")
    except Exception:
        msg = update.message.reply_text("Hiciste algo mal, la idea es que pongas:\n" +
                                        update.message.text.split()[0] +
                                        " <nombre>|<link>",
                                        quote=False)
        context.sent_messages.append(msg)
        return
    with db_session:
        group = listable_type(name=name, url=url)
    keyboard = [
        [
            InlineKeyboardButton(
                text="Aceptar", callback_data=f"Listable|{group.id}|1"),
            InlineKeyboardButton(
                text="Rechazar", callback_data=f"Listable|{group.id}|0")
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.sendMessage(chat_id=137497264,
                            text=listable_type.__name__ + ": " + name + "\n" + url,
                            reply_markup=reply_markup)
    msg = update.message.reply_text("OK, se lo mando a Rozen.", quote=False)
    context.sent_messages.append(msg)


def sugerirgrupo(update, context):
    suggest_listable(update, context, Obligatoria)


def sugeriroptativa(update, context):
    suggest_listable(update, context, Optativa)


def sugerireci(update, context):
    suggest_listable(update, context, ECI)


def sugerirotro(update, context):
    suggest_listable(update, context, Otro)


def listarlabos(update, context):
    args = context.args
    mins = int(args[0]) if len(args) > 0 else 0
    instant = labos.aware_now() + datetime.timedelta(minutes=mins)
    respuesta = '\n'.join(labos.events_at(instant))
    msg = update.message.reply_text(text=respuesta, quote=False)
    context.sent_messages.append(msg)


def flan(update, context):
    responder_imagen(update, context, 'files/Plandeestudios.png')


def togglecommand(update, context):
    if context.args and update.message.from_user.id in admin_ids:
        command_name = context.args[0]
        if command_name not in command_handlers:
            update.message.reply_text(text=f"No existe el comando /{command_name}.",
                                      quote=False)
            return
        with db_session:
            command = Command.get(name=command_name)
            command.enabled = not command.enabled
            if command.enabled:
                action = "activado"
                context.dispatcher.add_handler(command_handlers[command_name])
            else:
                action = "desactivado"
                context.dispatcher.remove_handler(
                    command_handlers[command_name])
            update.message.reply_text(text=f"Comando /{command_name} {action}.",
                                      quote=False)


def sugerir(update, context):
    update.message.reply_text(
        text=f"Ahora en mas las sugerencias las vamos a tomar en github:\n "
        "https://github.com/rozen03/dcubabot/issues", quote=False)


def sugerirNoticia(update, context):
    user = update.message.from_user
    name = user.first_name  # Agarro el nombre para ver quien fue
    # /sugerirNoticia <texto>
    texto = str.join(" ", context.args)
    try:
        # Esto es re cabeza pero no me acuerdo por que está asi
        if not (texto and isinstance(texto, str)):
            raise Exception
    except Exception:
        update.message.reply_text(
            text="Loc@, pusisiste algo mal, la idea es q pongas:\n "
                 "/sugerirNoticia <texto>")
        return
    try:
        with db_session:
            noticia = Noticia(text=texto)
            commit()  # Hago el commmit para que tenga un id
            idNoticia = noticia.id
        keyboard = [
            [
                InlineKeyboardButton("Aceptar", callback_data="Noticia|" +
                                     str(noticia.id) + '|1'),
                InlineKeyboardButton(
                    "Rechazar", callback_data="noticia|" + str(noticia.id) + '|0')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.sendMessage(chat_id=137497264, text=f"Noticia-{name}: {texto}",
                                reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        update.message.reply_text(text="Ok, se lo pregunto a Rozen")
    except Exception as inst:
        logger.exception(inst)


# Manda una imagen a partir de su path al chat del update dado
def mandar_imagen(chat_id, context, file_path):
    context.bot.sendChatAction(chat_id=chat_id, action=ChatAction.UPLOAD_PHOTO)
    with db_session:
        file = File.get(path=file_path)
    if file:
        msg = context.bot.send_photo(
            chat_id=chat_id, photo=file.file_id, quote=False)
    else:
        msg = context.bot.send_photo(
            chat_id=chat_id, photo=open(file_path, 'rb'), quote=False)
        with db_session:
            File(path=file_path, file_id=msg.photo[0].file_id)

    context.sent_messages.append(msg)

# Responde una imagen a partir de su path al chat del update dado
def responder_imagen(update, context, file_path):
    mandar_imagen(update.message.chat_id, context, file_path)


''' La funcion button se encarga de tomar todos los botones
    que se apreten en el bot (y que no sean links)'''

# TODO: Posiblemente usar Double Dispatch para ver como
# Cada Boton de validacion hace lo mismo o no


def button(update, context):
    query = update.callback_query
    message = query.message
    buttonType, id, action = query.data.split("|")
    with db_session:
        if buttonType == "Listable":
            group = Listable[int(id)]
            if action == "1":
                group.validated = True
                action_text = "\n¡Aceptado!"
            else:
                group.delete()
                action_text = "\n¡Rechazado!"
            context.bot.editMessageText(chat_id=message.chat_id,
                                        message_id=message.message_id,
                                        text=message.text + action_text)
        if buttonType == "Noticia":
            noticia = Noticia[int(id)]
            if action == "1":
                noticia.validated = True
                action_text = "\n¡Aceptado!"
                context.bot.sendMessage(chat_id="@NoticiasDC",
                                        text=noticia.text, parse_mode=ParseMode.MARKDOWN)
            else:
                noticia.delete()
                action_text = "\n¡Rechazado!"
            context.bot.editMessageText(chat_id=message.chat_id,
                                        message_id=message.message_id,
                                        text=message.text + action_text)
        if buttonType == "Donde":
            context.bot.sendMessage(chat_id = message.chat_id,
                                    text = action)


def hoyJuegaRiver(context):
    context.bot.sendMessage(chat_id=-1001067544716, text="Hoy Juega River")


def actualizarRiver(context):
    for matchTime in getMatches():
        for h in [9, 13, 16]:  # varios horarios por si las dudas
            context.job_queue.run_once(callback=hoyJuegaRiver,
                                       when=matchTime.replace(hour=h))


def add_all_handlers(dispatcher):
    descriptions = []
    dispatcher.add_handler(MessageHandler(
        (Filters.text | Filters.command), log_message), group=1)
    with db_session:
        for command in select(c for c in Command):
            handler = DeletableCommandHandler(
                command.name, globals()[command.name])
            command_handlers[command.name] = handler
            if command.enabled:
                dispatcher.add_handler(handler)
                if command.description:
                    descriptions.append((command.name, command.description))
    dispatcher.add_handler(CallbackQueryHandler(button))
    print(descriptions)
    dispatcher.bot.set_my_commands(descriptions)


def checodepers(update, context):
    if not context.args:
        ejemplo = """ Ejemplo de uso:
  /checodepers Hola, tengo un mensaje mucho muy importante que me gustaria que respondan
"""
        msg = update.message.reply_text(ejemplo, quote=False)
        context.sent_messages.append(msg)
        return
    user = update.message.from_user
    try:
        if not user.username:
            raise Exception("not userneim")
        message = " ".join(context.args)
        context.bot.sendMessage(
            chat_id="-311333765", text=f"{user.first_name}(@{user.username}) : {message}")
    except Exception:
        context.bot.forward_message(
            "-311333765", update.message.chat_id, update.message.message_id)
        print("Malio sal", str(user))
    msg = update.message.reply_text(
        "OK, se lo mando a les codepers.", quote=False)
    context.sent_messages.append(msg)

def checodeppers(update, context):
    checodepers(update, context)

def campusvivo(update, context):

    msg = update.message.reply_text("Bancá que me fijo...", quote=False)

    campus_response_text = is_campus_up()

    context.bot.editMessageText(chat_id=msg.chat_id,
                                message_id=msg.message_id,
                                text=msg.text + "\n" + campus_response_text)

    context.sent_messages.append(msg)

def cuandovence(update, context):
    ejemplo = "\nCuatris: 1c, 2c, i, inv, invierno, v, ver, verano.\nEjemplo: /cuandovence verano2010"
    if not context.args:
        ayuda = "Pasame cuatri y año en que aprobaste los TPs." + ejemplo
        msg = update.message.reply_text(ayuda, quote=False)
        context.sent_messages.append(msg)
        return
    try:
        linea_entrada = "".join(context.args).lower()
        cuatri, anio = parse_cuatri_y_anio(linea_entrada)
    except Exception:
        msg = update.message.reply_text("¿Me pasás las cosas bien? Es cuatri+año."+ejemplo, quote=False)
        context.sent_messages.append(msg)
        return

    vencimiento = get_vencimiento(cuatri, anio)
    msg = update.message.reply_text(vencimiento, quote=False, parse_mode=ParseMode.MARKDOWN)
    context.sent_messages.append(msg)


def list_response_buttons(update, context, listable_type):
    with db_session:
        buttons = select(l for l in listable_type if l.validated).order_by(
            lambda l: l.name)
        keyboard = []
        columns = 3
        for k in range(0, len(buttons), columns):
            row = [InlineKeyboardButton(
                text=button.name, callback_data='Donde|| ' + button.url )
                for button in buttons[k:k + columns]]

            keyboard.append(row)
        reply_markup = InlineKeyboardMarkup(keyboard)
        msg = update.message.reply_text(text="Lugares: ", disable_web_page_preview=True,
                                        reply_markup=reply_markup, quote=False)
        context.sent_messages.append(msg)

def sugerirdonde(update, context):
    suggest_listable(update, context, Donde)

# Esta funcion presenta botones con las posibles ubicaciones de lugares dentro de
# la facultad
def donde(update, context):
    list_response_buttons(update, context, Donde)

def main():

    try:
        global update_id
        # Telegram bot Authorization Token
        botname = "DCUBABOT"
        print("Iniciando DCUBABOT")
        logger.info("Iniciando")
        init_db("dcubabot.sqlite3")
        updater = Updater(token=token, use_context=True)
        dispatcher = updater.dispatcher

        updater.job_queue.run_daily(
            callback=felizdia,
            time=get_hora_feliz_dia()
        )

        #updater.job_queue.run_once(callback=actualizarRiver, when=0)
        #updater.job_queue.run_daily(callback=actualizarRiver, time=datetime.time())

        updater.job_queue.run_repeating(
            callback=labos.update, interval=datetime.timedelta(hours=1))
        dispatcher.add_error_handler(error_callback)
        add_all_handlers(dispatcher)
        # Start running the bot

        print([(j.name, j.interval) for j in updater.job_queue.jobs()])
        updater.start_polling(clean=True)
    except Exception as inst:
        logger.critical("ERROR AL INICIAR EL DCUBABOT")
        logger.exception(inst)


if __name__ == '__main__':
    from tokenz import *
    main()
