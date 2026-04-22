from flask import Flask, request, render_template, redirect, url_for
import requests
import json
import uuid
import random
from datetime import datetime
import config
import yookassa
from yookassa import Payment
import vk_api
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from supabase_client import (
    get_participant_by_vk,
    get_pending_participant_by_name,
    activate_participant,
    add_workout,
    get_today_workout,
    get_personal_stats,
    get_rating,
    get_team_rating,
    get_current_day,
    count_participants_by_region,
    register_team_payment,
    register_solo_payment
)

app = Flask(__name__)

# Инициализация ЮKassa
if config.YOOKASSA_SHOP_ID and config.YOOKASSA_SECRET_KEY:
    yookassa.Configuration.account_id = config.YOOKASSA_SHOP_ID
    yookassa.Configuration.secret_key = config.YOOKASSA_SECRET_KEY

# Хранилище состояний пользователей
user_states = {}

# ========== ОТПРАВКА СООБЩЕНИЙ ВК ==========

def send_vk_message(user_id, text, keyboard=None):
    try:
        vk = vk_api.VkApi(token=config.VK_GROUP_TOKEN).get_api()
        params = {
            'user_id': user_id,  # ← для ЛС
            'message': text,
            'random_id': random.randint(1, 2147483647),
            'from_group': 1
        }
        if keyboard:
            params['keyboard'] = keyboard
        
        print(f"📤 Отправка сообщения для user_id={user_id}: {text[:50]}...")
        vk.messages.send(**params)
        print(f"✅ Сообщение отправлено")
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        return False

# ========== КЛАВИАТУРЫ ==========

def get_main_keyboard():
    keyboard = VkKeyboard()
    keyboard.add_button('➕ Добавить тренировку', color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button('📊 Моя статистика', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('⭐️ Рейтинг', color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button('👥 Команды', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('📋 Правила', color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()

def get_cancel_keyboard():
    keyboard = VkKeyboard()
    keyboard.add_button('❌ Отмена', color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()

# ========== ГЛАВНОЕ МЕНЮ ==========

def send_main_menu(user_id, first_name):
    day = get_current_day()
    text = f"🏔️ БИТВА ОКРУГОВ\n\nПривет, {first_name}!\nДень {day}\n\nВыберите действие:"
    send_vk_message(user_id, text, get_main_keyboard())

# ========== ОБРАБОТКА КОМАНД БОТА ==========

def handle_start(user_id):
    participant = get_participant_by_vk(user_id)
    
    if participant:
        send_main_menu(user_id, participant["first_name"])
        return
    
    user_states[user_id] = {"action": "waiting_name"}
    send_vk_message(user_id, 
        "👋 Добро пожаловать в челлендж «Битва округов»!\n\n"
        "Для активации введите ваши имя и фамилию через пробел.\n"
        "Например: Иван Иванов",
        get_cancel_keyboard()
    )

def handle_add_workout_start(user_id):
    participant = get_participant_by_vk(user_id)
    if not participant:
        send_vk_message(user_id, "❌ Вы не зарегистрированы")
        return
    
    day = get_current_day()
    today_workout = get_today_workout(participant["id"], day)
    
    if today_workout:
        send_vk_message(user_id, 
            f"❌ Вы уже добавили тренировку сегодня!\n"
            f"📏 {today_workout['original_km']} км за {today_workout['original_min']} мин",
            get_main_keyboard()
        )
        return
    
    user_states[user_id] = {"action": "waiting_distance"}
    send_vk_message(user_id, 
        f"🏃 Добавление тренировки\n\nВведите дистанцию в км (минимум {config.MIN_KM} км):",
        get_cancel_keyboard()
    )

def handle_stats(user_id):
    participant = get_participant_by_vk(user_id)
    if not participant:
        send_vk_message(user_id, "❌ Вы не зарегистрированы")
        return
    
    stats = get_personal_stats(user_id)
    if not stats:
        send_vk_message(user_id, "❌ Ошибка получения статистики")
        return
    
    text = f"""📊 ВАША СТАТИСТИКА

👤 {stats['name']}
📍 {stats['region']} | {stats['team']}
👑 {'Капитан' if stats['is_captain'] else 'Участник'}

🏃 Тренировок: {stats['workouts_count']}
📏 Всего км: {stats['total_km']} км
⏱ Всего минут: {stats['total_min']} мин
⚡ Средний темп: {stats['avg_pace']} мин/км"""
    
    send_vk_message(user_id, text, get_main_keyboard())

def handle_rating(user_id):
    rating = get_rating()
    
    text = "🏆 РЕЙТИНГ\n\n👨 МУЖЧИНЫ:\n"
    for i, p in enumerate(rating["men"][:5], 1):
        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}."
        km = p.get("total_km", 0) or 0
        text += f"{medal} {p['first_name']} {p['last_name']} — {km} км\n"
    
    text += "\n👩 ЖЕНЩИНЫ:\n"
    for i, p in enumerate(rating["women"][:5], 1):
        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}."
        km = p.get("total_km", 0) or 0
        text += f"{medal} {p['first_name']} {p['last_name']} — {km} км\n"
    
    text += f"\n📍 ОКРУЖНОЙ ЗАЧЁТ:\n"
    text += f"ХМАО: {rating['regions']['hmao']} км\n"
    text += f"ЯНАО: {rating['regions']['ynao']} км\n"
    text += f"👑 Лидер: {rating['regions']['leader']}"
    
    send_vk_message(user_id, text, get_main_keyboard())

def handle_teams(user_id):
    teams = get_team_rating()
    
    text = "👥 РЕЙТИНГ КОМАНД\n\n"
    for i, t in enumerate(teams[:10], 1):
        km = t.get("total_km", 0) or 0
        points = t.get("points", 0) or 0
        text += f"{i}. {t['name']} ({t['region']}) — {km} км | {points} очк.\n"
    
    send_vk_message(user_id, text, get_main_keyboard())

def handle_rules(user_id):
    text = f"""📜 ПРАВИЛА ЧЕЛЛЕНДЖА

✅ Минимальная дистанция: {config.MIN_KM} км
✅ Максимальный темп: {config.MAX_PACE}:00 мин/км
✅ Одна тренировка в день
✅ Бег только на улице

🏆 Зачёты:
• Личный — по сумме километров
• Окружной — ХМАО против ЯНАО
• Командный — микро-команды по 4 человека"""
    
    send_vk_message(user_id, text, get_main_keyboard())

# ========== ОБРАБОТКА СОСТОЯНИЙ ==========

def handle_state(user_id, text):
    state = user_states.get(user_id)
    if not state:
        return False
    
    if text == "❌ Отмена":
        del user_states[user_id]
        participant = get_participant_by_vk(user_id)
        if participant:
            send_main_menu(user_id, participant["first_name"])
        else:
            send_vk_message(user_id, "Действие отменено. Напишите /start для начала.")
        return True
    
    # Ожидание имени и фамилии
    if state["action"] == "waiting_name":
        parts = text.split()
        if len(parts) < 2:
            send_vk_message(user_id, "❌ Введите имя и фамилию через пробел:")
            return True
        
        first_name = parts[0]
        last_name = parts[1]
        
        pending = get_pending_participant_by_name(first_name, last_name)
        
        if not pending:
            send_vk_message(user_id, 
                "❌ Участник не найден. Проверьте правильность имени и фамилии или зарегистрируйтесь на сайте:\n"
                f"{request.host_url}",
                get_cancel_keyboard()
            )
            return True
        
        activate_participant(pending["id"], user_id)
        del user_states[user_id]
        
        send_vk_message(user_id, 
            f"✅ Активация успешна!\n\n"
            f"Добро пожаловать, {first_name}!\n"
            f"Округ: {pending['region']}\n"
            f"Команда: {pending['team_name']}"
        )
        send_main_menu(user_id, first_name)
        return True
    
    # Ожидание дистанции
    if state["action"] == "waiting_distance":
        try:
            distance = float(text.replace(",", "."))
        except:
            send_vk_message(user_id, "❌ Введите число (например: 5.2):", get_cancel_keyboard())
            return True
        
        if distance < config.MIN_KM:
            send_vk_message(user_id, f"❌ Минимальная дистанция: {config.MIN_KM} км", get_cancel_keyboard())
            return True
        
        user_states[user_id] = {
            "action": "waiting_duration",
            "distance": distance
        }
        send_vk_message(user_id, f"✅ Дистанция: {distance} км\n\nВведите время в минутах:", get_cancel_keyboard())
        return True
    
    # Ожидание времени
    if state["action"] == "waiting_duration":
        try:
            duration = int(text)
        except:
            send_vk_message(user_id, "❌ Введите целое число минут:", get_cancel_keyboard())
            return True
        
        if duration <= 0:
            send_vk_message(user_id, "❌ Время должно быть больше 0:", get_cancel_keyboard())
            return True
        
        distance = state["distance"]
        pace = duration / distance
        
        if pace > config.MAX_PACE:
            send_vk_message(user_id, f"❌ Максимальный темп: {config.MAX_PACE}:00 мин/км\nВаш темп: {pace:.2f} мин/км", get_cancel_keyboard())
            return True
        
        # Переходим к запросу скриншота
        user_states[user_id] = {
            "action": "waiting_screenshot",
            "distance": distance,
            "duration": duration
        }
        send_vk_message(user_id, 
            "📸 Отправьте скриншот тренировки (должны быть видны дата, дистанция и темп):",
            get_cancel_keyboard()
        )
        return True
        
        workout = add_workout(
            participant["id"],
            f"{participant['first_name']} {participant['last_name']}",
            participant["team_id"],
            participant["team_name"],
            participant["region"],
            distance,
            duration
        )
        
        del user_states[user_id]
        
        if workout:
            day = get_current_day()
            send_vk_message(user_id,
                f"✅ Тренировка добавлена!\n\n"
                f"📅 День {day}\n"
                f"📏 Дистанция: {distance} км\n"
                f"⏱ Время: {duration} мин\n"
                f"⚡ Темп: {pace:.2f} мин/км"
            )
        else:
            send_vk_message(user_id, "❌ Ошибка при сохранении тренировки")
        
        send_main_menu(user_id, participant["first_name"])
        return True
    
    return False

# ========== ОТПРАВКА В ЧАТ С ФОТО ==========

def send_to_chat_with_photo(chat_id, message, photo_attachment):
    """Отправка сообщения с фото в общий чат"""
    try:
        vk = vk_api.VkApi(token=config.VK_GROUP_TOKEN).get_api()
        vk.messages.send(
            peer_id=chat_id,
            message=message,
            attachment=photo_attachment,
            random_id=random.randint(1, 2147483647),
            from_group=1
        )
        print(f"✅ Скриншот отправлен в чат {chat_id}")
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки в чат: {e}")
        return False

# ========== ВЕБ-СТРАНИЦЫ ==========

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register/team")
def register_team():
    return render_template("register_team.html")

@app.route("/register/solo")
def register_solo():
    return render_template("register_solo.html")

# ========== СОЗДАНИЕ ПЛАТЕЖЕЙ ==========

@app.route("/create_team_payment", methods=["POST"])
def create_team_payment():
    team_name = request.form.get("team_name")
    region = request.form.get("region")
    promo_code = request.form.get("promo_code", "").strip().upper()
    
    members = [
        {"first": request.form.get("cap_first"), "last": request.form.get("cap_last"), "gender": request.form.get("cap_gender")},
        {"first": request.form.get("m2_first"), "last": request.form.get("m2_last"), "gender": request.form.get("m2_gender")},
        {"first": request.form.get("m3_first"), "last": request.form.get("m3_last"), "gender": request.form.get("m3_gender")},
        {"first": request.form.get("m4_first"), "last": request.form.get("m4_last"), "gender": request.form.get("m4_gender")}
    ]
    
    for i, m in enumerate(members):
        if not m["first"] or not m["last"] or not m["gender"]:
            return render_template("error.html", error=f"Участник {i+1}: заполните все поля")
    
    current_count = count_participants_by_region(region)
    if current_count + 4 > config.MAX_PER_REGION:
        return render_template("error.html", 
            error=f"В округе {region} осталось только {config.MAX_PER_REGION - current_count} мест"
        )
    
    if promo_code == config.SECRET_PROMO_CODE:
        payment_id = f"promo_{uuid.uuid4()}"
        register_team_payment(payment_id, team_name, region, members, 0)
        return render_template("success.html", 
            message=f"✅ Команда «{team_name}» зарегистрирована БЕСПЛАТНО по промокоду!"
        )
    
    idempotence_key = str(uuid.uuid4())
    payment = Payment.create({
        "amount": {"value": f"{config.PRICE_TEAM}.00", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": url_for('payment_success', _external=True)},
        "description": f"Регистрация команды {team_name}",
        "metadata": {"type": "team", "team_name": team_name, "region": region, "members": json.dumps(members)},
        "capture": True
    }, idempotence_key)
    
    return redirect(payment.confirmation.confirmation_url)

@app.route("/create_solo_payment", methods=["POST"])
def create_solo_payment():
    region = request.form.get("region")
    first_name = request.form.get("first_name")
    last_name = request.form.get("last_name")
    gender = request.form.get("gender")
    promo_code = request.form.get("promo_code", "").strip().upper()
    
    if not first_name or not last_name or not gender:
        return render_template("error.html", error="Заполните все поля")
    
    current_count = count_participants_by_region(region)
    if current_count >= config.MAX_PER_REGION:
        return render_template("error.html", error=f"Регистрация в округе {region} закрыта")
    
    if promo_code == config.SECRET_PROMO_CODE:
        payment_id = f"promo_{uuid.uuid4()}"
        register_solo_payment(payment_id, region, first_name, last_name, gender, 0)
        return render_template("success.html",
            message=f"✅ {first_name} {last_name} зарегистрирован БЕСПЛАТНО по промокоду!"
        )
    
    idempotence_key = str(uuid.uuid4())
    payment = Payment.create({
        "amount": {"value": f"{config.PRICE_SOLO}.00", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": url_for('payment_success', _external=True)},
        "description": f"Индивидуальная регистрация {first_name} {last_name}",
        "metadata": {"type": "solo", "region": region, "first_name": first_name, "last_name": last_name, "gender": gender},
        "capture": True
    }, idempotence_key)
    
    return redirect(payment.confirmation.confirmation_url)

@app.route("/payment/success")
def payment_success():
    return render_template("success.html", message="Спасибо за регистрацию в челлендже «Битва округов»!")

# ========== WEBHOOK ДЛЯ ЮKASSA ==========

@app.route("/yookassa-webhook", methods=["POST"])
def yookassa_webhook():
    event = request.json
    payment = event.get("object")
    
    if event.get("event") == "payment.succeeded":
        payment_id = payment.get("id")
        metadata = payment.get("metadata")
        
        if metadata.get("type") == "team":
            members = json.loads(metadata.get("members", "[]"))
            register_team_payment(payment_id, metadata.get("team_name"), metadata.get("region"), members, config.PRICE_TEAM)
        elif metadata.get("type") == "solo":
            register_solo_payment(payment_id, metadata.get("region"), metadata.get("first_name"), 
                                metadata.get("last_name"), metadata.get("gender"), config.PRICE_SOLO)
    
    return "OK", 200

# ========== ВЕБХУК ДЛЯ ВК ==========

@app.route("/vk-webhook", methods=["POST"])
def vk_webhook():
    data = request.json
    
    if data.get("type") == "confirmation":
        return config.VK_CONFIRMATION
    
    if data.get("type") == "message_new":
        msg = data["object"]["message"]
        user_id = msg["from_id"]
        peer_id = msg["peer_id"]
        text = msg.get("text", "").strip()
        
        # 🔥 САМАЯ ПЕРВАЯ ПРОВЕРКА - логируем ВСЁ
        print(f"📨 СООБЩЕНИЕ: user={user_id}, peer={peer_id}, text='{text}'")
        
        # 🔑 Обработка /chatid ДО ВСЕХ ОСТАЛЬНЫХ ПРОВЕРОК
        if text == '/chatid':
            print(f"🔍 КОМАНДА /chatid ОБНАРУЖЕНА!")
            try:
                vk = vk_api.VkApi(token=config.VK_GROUP_TOKEN).get_api()
                vk.messages.send(
                    user_id=user_id,
                    message=f"Peer ID: {peer_id}",
                    random_id=random.randint(1, 2147483647),
                    from_group=1
                )
                print(f"✅ Ответ отправлен в ЛС")
            except Exception as e:
                print(f"❌ Ошибка: {e}")
            return 'ok'
        
        # Только потом проверяем чат/ЛС
        is_chat = peer_id > 2000000000
        if is_chat:
            print(f"⏭️ Сообщение из чата, игнорируем")
            return 'ok'
        
        # ... весь остальной код ...
        
        # Проверяем, есть ли фото и ждём ли мы скриншот
        state = user_states.get(user_id)
        if state and state.get("action") == "waiting_screenshot":
            if attachments and attachments[0].get("type") == "photo":
                # Получаем фото
                photo = attachments[0]["photo"]
                owner_id = photo.get("owner_id")
                photo_id = photo.get("id")
                access_key = photo.get("access_key", "")
                
                photo_attachment = f"photo{owner_id}_{photo_id}"
                if access_key:
                    photo_attachment += f"_{access_key}"
                
                distance = state["distance"]
                duration = state["duration"]
                
                participant = get_participant_by_vk(user_id)
                if not participant:
                    del user_states[user_id]
                    send_vk_message(user_id, "❌ Ошибка: участник не найден")
                    return "ok"
                
                # Сохраняем тренировку в БД
                workout = add_workout(
                    participant["id"],
                    f"{participant['first_name']} {participant['last_name']}",
                    participant["team_id"],
                    participant["team_name"],
                    participant["region"],
                    distance,
                    duration
                )
                
                del user_states[user_id]
                
                if workout:
                    day = get_current_day()
                    pace = duration / distance
                    
                    # Уведомление участнику
                    send_vk_message(user_id,
                        f"✅ Тренировка принята!\n\n"
                        f"📅 День {day}\n"
                        f"📏 Дистанция: {distance} км\n"
                        f"⏱ Время: {duration} мин\n"
                        f"⚡ Темп: {pace:.2f} мин/км",
                        get_main_keyboard()
                    )
                    
                    # Отправка в общий чат
                    chat_id = config.VK_CHAT_ID
                    if chat_id:
                        chat_msg = (f"✅ ТРЕНИРОВКА ПРИНЯТА\n\n"
                                   f"👤 {participant['first_name']} {participant['last_name']}\n"
                                   f"📍 {participant['region']} | {participant['team_name']}\n"
                                   f"📅 День {day}\n"
                                   f"📏 {distance} км\n"
                                   f"⏱ {duration} мин\n"
                                   f"⚡ Темп: {pace:.2f} мин/км")
                        send_to_chat_with_photo(chat_id, chat_msg, photo_attachment)
                else:
                    send_vk_message(user_id, "❌ Ошибка при сохранении тренировки", get_main_keyboard())
                
                return "ok"
            else:
                send_vk_message(user_id, "❌ Отправьте скриншот (фото):", get_cancel_keyboard())
                return "ok"
        
        # Обработка текстовых состояний
        if handle_state(user_id, text):
            return "ok"
        
        # Обработка команд
        if text in ["/start", "меню", "Меню", "начать"]:
            handle_start(user_id)
        elif text == "➕ Добавить тренировку":
            handle_add_workout_start(user_id)
        elif text == "📊 Моя статистика":
            handle_stats(user_id)
        elif text == "⭐️ Рейтинг":
            handle_rating(user_id)
        elif text == "👥 Команды":
            handle_teams(user_id)
        elif text == "📋 Правила":
            handle_rules(user_id)
        else:
            participant = get_participant_by_vk(user_id)
            if participant:
                send_main_menu(user_id, participant["first_name"])
            else:
                send_vk_message(user_id, "Напишите /start для начала работы")
    
    return "ok"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
