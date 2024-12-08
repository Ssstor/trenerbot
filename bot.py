from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from api_token import *
from models import engine, User, Measurement, Reminder
import telebot

bot = telebot.TeleBot(API_TOKEN)
Session = sessionmaker(bind=engine)

TEST_MODE = True

scheduler = BackgroundScheduler()
scheduler.start()

user_states = dict()

def send_reminder(chat_id):
    if chat_id in user_states:
        del user_states[chat_id]
    bot.send_message(chat_id, "Пора ввести новые измерения. Начнем с вашего веса (в кг).")
    user_states[chat_id] = {"step": "weight"}

def schedule_user_reminder(user_id, chat_id, first_measurement_date):
    session = Session()
    weekday = first_measurement_date.weekday()

    reminder = Reminder(
        user_id=user_id,
        day_of_week=weekday,
        time=first_measurement_date.replace(hour=7, minute=0)
    )
    session.add(reminder)
    session.commit()

    if TEST_MODE:
        scheduler.add_job(
            send_reminder,
            trigger=IntervalTrigger(minutes=5),
            args=[chat_id],
            id=str(reminder.id),
            replace_existing=True
        )
    else:
        scheduler.add_job(
            send_reminder,
            trigger=CronTrigger(day_of_week=weekday, hour=7, minute=0),
            args=[chat_id],
            id=str(reminder.id),
            replace_existing=True
        )

def load_reminders():
    session = Session()
    reminders = session.query(Reminder).all()
    for reminder in reminders:
        user = reminder.user
        if TEST_MODE:
            scheduler.add_job(
                send_reminder,
                trigger=IntervalTrigger(minutes=5),
                args=[user.chat_id],
                id=str(reminder.id),
                replace_existing=True
            )
        else:
            scheduler.add_job(
                send_reminder,
                trigger=CronTrigger(day_of_week=reminder.day_of_week, hour=7, minute=0),
                args=[user.chat_id],
                id=str(reminder.id),
                replace_existing=True
            )

@bot.message_handler(commands=['start'])
def start_handler(message):
    chat_id = message.chat.id
    session = Session()
    user = session.query(User).filter_by(chat_id=str(chat_id)).first()

    if user:
        bot.send_message(chat_id, f"Вы уже зарегистрированы как {user.name}.")
        
    elif chat_id in TRAINERS:
        bot.send_message(chat_id, "Вы зарегистрированы как тренер.")
        
    else:
        bot.send_message(chat_id, "Привет! Как я могу к вам обращаться?")
        user_states[chat_id] = {"step": "name"}

        
@bot.message_handler(commands=['post'])
def post_handler(message):
    chat_id = message.chat.id
    if chat_id in TRAINERS:
        bot.send_message(chat_id, "Отправьте текст поста, который вы хотите отправить всем пользователям.")
        user_states[chat_id] = {"step": "post"}
    else:
        bot.send_message(chat_id, "У вас нет прав для отправки постов.")

    print(user_states)
    print(user_states.get(message.chat.id, {}).get("step"))

@bot.message_handler(func=lambda msg: user_states.get(msg.chat.id, {}).get("step") == "post", content_types=['text', 'photo', 'video', 'document', 'audio'])
def send_post(message):
    chat_id = message.chat.id
    session = Session()
    users = session.query(User).all()

    for user in users:
        try:
            if message.text:
                bot.send_message(user.chat_id, message.text) # type: ignore

            elif message.photo:
                bot.send_photo(user.chat_id, message.photo[-1].file_id, caption=message.caption or "") # type: ignore
 
            elif message.video:
                bot.send_video(user.chat_id, message.video.file_id, caption=message.caption or "") # type: ignore
 
            elif message.document:
                bot.send_document(user.chat_id, message.document.file_id, caption=message.caption or "") # type: ignore
 
            elif message.audio:
                bot.send_audio(user.chat_id, message.audio.file_id, caption=message.caption or "") # type: ignore
 
        except Exception as e:
            print(f"Ошибка отправки для пользователя {user.chat_id}: {e}")

    bot.send_message(chat_id, "Пост успешно отправлен всем пользователям!")
    del user_states[chat_id]   

@bot.message_handler(func=lambda msg: msg.chat.id in user_states)
def state_handler(message):
    chat_id = message.chat.id
    state = user_states[chat_id]
    session = Session()

    bot.delete_message(chat_id, message.message_id)

    if state["step"] == "name":
        name = message.text
        user = User(chat_id=str(chat_id), name=name, first_measurement_date=datetime.now())
        session.add(user)
        session.commit()

        schedule_user_reminder(user.id, chat_id, user.first_measurement_date)
        bot.send_message(chat_id, f"Приятно познакомиться, {name}! Давайте начнем с вашего веса (в кг).")
        state["step"] = "weight"

    elif state["step"] == "weight":
        try:
            weight = float(message.text)
            state["weight"] = weight
            msg = bot.send_message(chat_id, "Введите объем левой руки (в см).")
            state["prev_msg_id"] = msg.message_id
            state["step"] = "left_arm"
        except ValueError:
            bot.send_message(chat_id, "Пожалуйста, введите число.")

    elif state["step"] == "left_arm":
        try:
            left_arm = float(message.text)
            state["left_arm"] = left_arm
            msg = bot.send_message(chat_id, "Введите объем правой руки (в см).")
            state["prev_msg_id"] = msg.message_id
            state["step"] = "right_arm"
        except ValueError:
            bot.send_message(chat_id, "Пожалуйста, введите число.")

    elif state["step"] == "right_arm":
        try:
            right_arm = float(message.text)
            state["right_arm"] = right_arm
            msg = bot.send_message(chat_id, "Введите объем груди (в см).")
            state["prev_msg_id"] = msg.message_id
            state["step"] = "chest"
        except ValueError:
            bot.send_message(chat_id, "Пожалуйста, введите число.")

    elif state["step"] == "chest":
        try:
            chest = float(message.text)
            state["chest"] = chest
            msg = bot.send_message(chat_id, "Введите объем талии (в см).")
            state["prev_msg_id"] = msg.message_id
            state["step"] = "waist"
        except ValueError:
            bot.send_message(chat_id, "Пожалуйста, введите число.")

    elif state["step"] == "waist":
        try:
            waist = float(message.text)
            state["waist"] = waist
            msg = bot.send_message(chat_id, "Введите объем бедер (в см).")
            state["prev_msg_id"] = msg.message_id
            state["step"] = "hips"
        except ValueError:
            bot.send_message(chat_id, "Пожалуйста, введите число.")

    elif state["step"] == "hips":
        try:
            hips = float(message.text)
            state["hips"] = hips
            msg = bot.send_message(chat_id, "Введите объем левой ноги (в см).")
            state["prev_msg_id"] = msg.message_id
            state["step"] = "left_leg"
        except ValueError:
            bot.send_message(chat_id, "Пожалуйста, введите число.")

    elif state["step"] == "left_leg":
        try:
            left_leg = float(message.text)
            state["left_leg"] = left_leg
            msg = bot.send_message(chat_id, "Введите объем правой ноги (в см).")
            state["prev_msg_id"] = msg.message_id
            state["step"] = "right_leg"
        except ValueError:
            bot.send_message(chat_id, "Пожалуйста, введите число.")

    elif state["step"] == "right_leg":
        try:
            right_leg = float(message.text)
            state["right_leg"] = right_leg
            save_measurement(chat_id, state, message)

            
            if "prev_msg_id" in state:
                bot.delete_message(chat_id, state["prev_msg_id"])
            bot.send_message(chat_id, "Спасибо! Ваши данные сохранены.")
            del user_states[chat_id]
        except ValueError:
            bot.send_message(chat_id, "Пожалуйста, введите число.")
    

def save_measurement(chat_id, data, message):
    session = Session()
    user = session.query(User).filter_by(chat_id=str(chat_id)).first()
    if user:
        version = session.query(Measurement).filter_by(user_id=user.id).count() + 1
        
        last_measurement = session.query(Measurement).filter_by(user_id=user.id).order_by(Measurement.timestamp.desc()).first()

        measurement = Measurement(
            user_id=user.id,
            version=version,
            timestamp=datetime.now(),
            weight=data["weight"],
            left_arm=data["left_arm"],
            right_arm=data["right_arm"],
            chest=data["chest"],
            waist=data["waist"],
            hips=data["hips"],
            left_leg=data["left_leg"],
            right_leg=data["right_leg"]
        )
        session.add(measurement)
        session.commit()

        current_date = datetime.now().strftime("%d.%m.%Y")
        summary = f"Измерения от {current_date}:\n"
        if last_measurement:
            def format_change(current, previous):
                change = current - previous
                sign = "+" if change > 0 else ""
                return f"{current} см ({sign}{change:.1f} см)"

            summary += f"Талия: {format_change(data['waist'], last_measurement.waist)}\n"
            summary += f"Грудь: {format_change(data['chest'], last_measurement.chest)}\n"
            summary += f"Руки: {format_change(data['left_arm'], last_measurement.left_arm)} / {format_change(data['right_arm'], last_measurement.right_arm)}\n"
            summary += f"Бедра: {format_change(data['hips'], last_measurement.hips)}\n"
            summary += f"Ноги: {format_change(data['left_leg'], last_measurement.left_leg)} / {format_change(data['right_leg'], last_measurement.right_leg)}\n"
            summary += f"Вес: {data['weight']} кг ({data['weight'] - last_measurement.weight:+.1f} кг)"
            
        else:
            summary += f"Талия: {data['waist']} см\n"
            summary += f"Грудь: {data['chest']} см\n"
            summary += f"Руки: {data['left_arm']} см / {data['right_arm']} см\n"
            summary += f"Бедра: {data['hips']} см\n"
            summary += f"Ноги: {data['left_leg']} см / {data['right_leg']} см\n"
            summary += f"Вес: {data['weight']} кг"


        bot.send_message(chat_id, summary)

        for trainer_id in TRAINERS:
            trainer_message = (
                f"Новые измерения от пользователя:\n"
                f"Имя: {user.name}\n"
                f"Telegram: @{message.chat.username if message.chat.username else 'Нет'}\n"
                f"{summary}"
            )
            bot.send_message(trainer_id, trainer_message)

        del user_states[chat_id]


load_reminders()

bot.polling(True)


