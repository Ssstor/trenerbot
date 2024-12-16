import threading
import queue
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from api_token import *
from models import engine, User, Measurement, Reminder, UserState
import telebot
import atexit

bot = telebot.TeleBot(API_TOKEN)
Session = sessionmaker(bind=engine)

TEST_MODE = False

video_path = 'meditation_video.mp4'

scheduler = BackgroundScheduler()
scheduler.start()

# Очередь для сообщений
message_queue = queue.Queue()

def state_handler_worker():
    """Фоновый поток для обработки сообщений."""
    while True:
        message = message_queue.get()
        if message is None:  # Завершающий сигнал
            break

        try:
            state_handler(message)
        except Exception as e:
            print(f"Ошибка при обработке сообщения: {e}")
        finally:
            message_queue.task_done()

# Запуск фонового потока
worker_thread = threading.Thread(target=state_handler_worker, daemon=True)
worker_thread.start()

def enqueue_message(message):
    """Добавляет сообщение в очередь для обработки."""
    message_queue.put(message)

def send_reminder(chat_id):
    with Session() as session:
        user_state = session.query(UserState).filter_by(chat_id=chat_id).first()
        if user_state:
            session.delete(user_state)
            session.commit()

        msg = bot.send_message(chat_id, "Пора ввести новые измерения. Начнем с вашего веса (в кг).")
        user_state = UserState(chat_id=chat_id, step="weight", reminder_msg_id=msg.message_id)
        session.add(user_state)
        session.commit()

def schedule_user_reminder(user_id, chat_id, first_measurement_date):
    with Session() as session:
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
                trigger=CronTrigger(day_of_week='mon', hour=7, minute=0),
                args=[chat_id],
                id=str(reminder.id),
                replace_existing=True
            )

def load_reminders():
    with Session() as session:
        reminders = session.query(Reminder).all()
        for reminder in reminders:
            user = reminder.user
            if TEST_MODE:
                scheduler.add_job(
                    send_reminder,
                    trigger=IntervalTrigger(minutes=1),
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

def send_meditation_video(chat_id):
    with Session() as session:
        user_state = session.query(UserState).filter_by(chat_id=chat_id).first()

        with open(video_path, 'rb') as video:
            if user_state:
                if user_state.meditation_video_message_id:
                    try:
                        bot.send_message(chat_id, "Пора медитировать!", reply_to_message_id=user_state.meditation_video_message_id)
                    except Exception:
                        video_message = bot.send_video(chat_id, video=video, caption="Ваше медитативное видео")
                        user_state.meditation_video_message_id = video_message.message_id
                        session.commit()
                else:
                    video_message = bot.send_video(chat_id, video=video, caption="Ваше медитативное видео")
                    user_state.meditation_video_message_id = video_message.message_id
                    session.commit()

@bot.message_handler(commands=['start'])
def start_handler(message):
    chat_id = message.chat.id
    with Session() as session:
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()

        if user:
            bot.send_message(chat_id, f"Вы уже зарегистрированы как {user.name}.")
        else:
            bot.send_message(chat_id, "Здравствуйте! Как я могу к вам обращаться?")
            user_state = UserState(chat_id=chat_id, step="name")
            session.add(user_state)
            session.commit()

@bot.message_handler(commands=['post'])
def post_handler(message):
    chat_id = message.chat.id
    if chat_id in TRAINERS:
        bot.send_message(chat_id, "Отправьте текст поста, который вы хотите отправить всем пользователям.")
        with Session() as session:
            user_state = session.query(UserState).filter_by(chat_id=chat_id).first()
            if user_state:
                # Обновляем существующее состояние вместо создания нового
                user_state.step = "post"
                session.commit()
            else:
                # Создаем новое состояние, если его нет
                user_state = UserState(chat_id=chat_id, step="post")
                session.add(user_state)
                session.commit()
    else:
        bot.send_message(chat_id, "У вас нет прав для отправки постов.")

def get_user_state(chat_id):
    with Session() as session:
        return session.query(UserState).filter_by(chat_id=chat_id).first()

@bot.message_handler(func=lambda msg: get_user_state(msg.chat.id) and get_user_state(msg.chat.id).step == "post", content_types=['text', 'photo', 'video', 'document', 'audio'])
def send_post(message):
    chat_id = message.chat.id
    with Session() as session:
        users = session.query(User).all()

        for user in users:
            try:
                if message.text:
                    bot.send_message(user.chat_id, message.text)

                elif message.photo:
                    bot.send_photo(user.chat_id, message.photo[-1].file_id, caption=message.caption or "")

                elif message.video:
                    bot.send_video(user.chat_id, message.video.file_id, caption=message.caption or "")

                elif message.document:
                    bot.send_document(user.chat_id, message.document.file_id, caption=message.caption or "")

                elif message.audio:
                    bot.send_audio(user.chat_id, message.audio.file_id, caption=message.caption or "")

            except Exception as e:
                print(f"Ошибка отправки для пользователя {user.chat_id}: {e}")

        bot.send_message(chat_id, "Пост успешно отправлен всем пользователям!")

        user_state = session.query(UserState).filter_by(chat_id=chat_id).first()
        
        if user_state:
            session.delete(user_state)
            session.commit()

@bot.message_handler(commands=['meditation'])
def meditation_handler(message):
    chat_id = message.chat.id
    with Session() as session:
        user_state = session.query(UserState).filter_by(chat_id=chat_id).first()
        if user_state is None:
            user_state = UserState(chat_id=chat_id, step="meditation_time")
            session.add(user_state)
            session.commit()

        bot.send_message(chat_id, "Пожалуйста, введите время, в которое вы хотите получать медитативное видео каждый день (формат 00:00 - 23:59):")
        user_state.step = 'meditation_time'
        session.commit()

@bot.message_handler(func=lambda msg: get_user_state(msg.chat.id) and get_user_state(msg.chat.id).step == "meditation_time")
def set_meditation_time(message):
    chat_id = message.chat.id
    time_str = message.text
    try:
        meditation_time = datetime.strptime(time_str, "%H:%M")
        with Session() as session:
            user_state = session.query(UserState).filter_by(chat_id=chat_id).first()
            if user_state:
                user_state.meditation_time = meditation_time.strftime("%H:%M")
                user_state.step = "meditation_video"
                session.commit()

            with open(video_path, 'rb') as video:
                video_message = bot.send_video(chat_id, video=video, caption="Ваше медитативное видео")
                user_state.meditation_video_message_id = video_message.message_id
                session.commit()

            if TEST_MODE:
                scheduler.add_job(
                    send_meditation_video,
                    trigger=IntervalTrigger(minutes=10),
                    args=[chat_id],
                    id=f"meditation_{chat_id}",
                    replace_existing=True
                )
            else:
                scheduler.add_job(
                    send_meditation_video,
                    trigger=CronTrigger(hour=meditation_time.hour, minute=meditation_time.minute),
                    args=[chat_id],
                    id=f"meditation_{chat_id}",
                    replace_existing=True
                )
            bot.send_message(chat_id, f"Медитативное видео будет отправляться каждый день в {meditation_time.strftime('%H:%M')}.")
    except ValueError:
        bot.send_message(chat_id, "Пожалуйста, введите время в правильном формате (00:00 - 23:59).")

def check_user_state(chat_id):
    with Session() as session:
        user_state = session.query(UserState).filter_by(chat_id=chat_id).first()
        return user_state is not None

@bot.message_handler(func=lambda msg: check_user_state(msg.chat.id))
def state_handler(message):
    chat_id = message.chat.id
    with Session() as session:
        user_state = session.query(UserState).filter_by(chat_id=chat_id).first()

        if user_state:
            state = user_state.step
            if state == "name":
                name = message.text
                user = User(chat_id=str(chat_id), name=name, first_measurement_date=datetime.now())
                session.add(user)
                session.commit()

                schedule_user_reminder(user.id, chat_id, user.first_measurement_date)
                bot.send_message(chat_id, f"Приятно познакомиться, {name}! Давайте начнем с вашего веса (в кг).")
                user_state.step = "weight"
                session.commit()

            elif state == "weight":
                try:
                    weight = float(message.text)
                    user_state.weight = weight
                    bot.send_message(chat_id, "Введите объем левой руки (в см).")
                    user_state.step = "left_arm"
                    session.commit()
                except ValueError:
                    bot.send_message(chat_id, "Пожалуйста, введите число.")

            elif state == "left_arm":
                try:
                    left_arm = float(message.text)
                    user_state.left_arm = left_arm
                    bot.send_message(chat_id, "Введите объем правой руки (в см).")
                    user_state.step = "right_arm"
                    session.commit()
                except ValueError:
                    bot.send_message(chat_id, "Пожалуйста, введите число.")

            elif state == "right_arm":
                try:
                    right_arm = float(message.text)
                    user_state.right_arm = right_arm
                    bot.send_message(chat_id, "Введите объем груди (в см).")
                    user_state.step = "chest"
                    session.commit()
                except ValueError:
                    bot.send_message(chat_id, "Пожалуйста, введите число.")

            elif state == "chest":
                try:
                    chest = float(message.text)
                    user_state.chest = chest
                    bot.send_message(chat_id, "Введите объем талии (в см).")
                    user_state.step = "waist"
                    session.commit()
                except ValueError:
                    bot.send_message(chat_id, "Пожалуйста, введите число.")

            elif state == "waist":
                try:
                    waist = float(message.text)
                    user_state.waist = waist
                    bot.send_message(chat_id, "Введите объем бедер (в см).")
                    user_state.step = "hips"
                    session.commit()
                except ValueError:
                    bot.send_message(chat_id, "Пожалуйста, введите число.")

            elif state == "hips":
                try:
                    hips = float(message.text)
                    user_state.hips = hips
                    bot.send_message(chat_id, "Введите объем левой ноги (в см).")
                    user_state.step = "left_leg"
                    session.commit()
                except ValueError:
                    bot.send_message(chat_id, "Пожалуйста, введите число.")

            elif state == "left_leg":
                try:
                    left_leg = float(message.text)
                    user_state.left_leg = left_leg
                    bot.send_message(chat_id, "Введите объем правой ноги (в см).")
                    user_state.step = "right_leg"
                    session.commit()
                except ValueError:
                    bot.send_message(chat_id, "Пожалуйста, введите число.")

            elif state == "right_leg":
                try:
                    right_leg = float(message.text)
                    user_state.right_leg = right_leg
                    save_measurement(chat_id, user_state, message)
                    bot.send_message(chat_id, "Спасибо! Ваши данные сохранены.")
                    session.delete(user_state)
                    session.commit()
                except ValueError:
                    bot.send_message(chat_id, "Пожалуйста, введите число.")

def save_measurement(chat_id, user_state, message):
    with Session() as session:
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if user:
            version = session.query(Measurement).filter_by(user_id=user.id).count() + 1

            last_measurement = session.query(Measurement).filter_by(user_id=user.id).order_by(Measurement.timestamp.desc()).first()

            measurement = Measurement(
                user_id=user.id,
                version=version,
                timestamp=datetime.now(),
                weight=user_state.weight,
                left_arm=user_state.left_arm,
                right_arm=user_state.right_arm,
                chest=user_state.chest,
                waist=user_state.waist,
                hips=user_state.hips,
                left_leg=user_state.left_leg,
                right_leg=user_state.right_leg
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

                summary += f"Талия: {format_change(user_state.waist, last_measurement.waist)}\n"
                summary += f"Грудь: {format_change(user_state.chest, last_measurement.chest)}\n"
                summary += f"Руки: {format_change(user_state.left_arm, last_measurement.left_arm)} / {format_change(user_state.right_arm, last_measurement.right_arm)}\n"
                summary += f"Бедра: {format_change(user_state.hips, last_measurement.hips)}\n"
                summary += f"Ноги: {format_change(user_state.left_leg, last_measurement.left_leg)} / {format_change(user_state.right_leg, last_measurement.right_leg)}\n"
                summary += f"Вес: {user_state.weight} кг ({user_state.weight - last_measurement.weight:+.1f} кг)"

            else:
                summary += f"Талия: {user_state.waist} см\n"
                summary += f"Грудь: {user_state.chest} см\n"
                summary += f"Руки: {user_state.left_arm} см / {user_state.right_arm} см\n"
                summary += f"Бедра: {user_state.hips} см\n"
                summary += f"Ноги: {user_state.left_leg} см / {user_state.right_leg} см\n"
                summary += f"Вес: {user_state.weight} кг"

            bot.send_message(chat_id, summary)

            for trainer_id in TRAINERS:
                trainer_message = (
                    f"Новые измерения от пользователя:\n"
                    f"Имя: {user.name}\n"
                    f"Telegram: @{message.chat.username if message.chat.username else 'Нет'}\n"
                    f"{summary}"
                )
                bot.send_message(trainer_id, trainer_message)

load_reminders()

bot.polling(none_stop=True, timeout=60)

def shutdown_worker():
    message_queue.put(None)
    worker_thread.join()

atexit.register(shutdown_worker)

