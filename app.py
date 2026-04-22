from flask import Flask, request, render_template, redirect, url_for, jsonify
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
    supabase,
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
    register_solo_payment,
    get_notification_template,
    create_stage_pairs,
    create_playoff_pairs,
    calculate_stage_results,
    get_stage_matches,
    get_top4_teams
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
    """Отправка сообщения пользователю в ЛС"""
    try:
        vk = vk_api.VkApi(token=config.VK_GROUP_TOKEN).get_api()
        params = {
            'user_id': user_id,
            'message': text,
            'random_id': random.randint(1, 2147483647),
            'from_group': 1
        }
        if keyboard:
            params['keyboard'] = keyboard
            print(f"📤 Отправка клавиатуры для user_id={user_id}")
        
        vk.messages.send(**params)
        print(f"✅ Сообщение отправлено в ЛС для user_id={user_id}")
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки в ЛС: {e}")
        return False

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

def send_to_chat_text(chat_id, message):
    """Отправка текстового сообщения в общий чат"""
    try:
        vk = vk_api.VkApi(token=config.VK_GROUP_TOKEN).get_api()
        vk.messages.send(
            peer_id=chat_id,
            message=message,
            random_id=random.randint(1, 2147483647),
            from_group=1
        )
        print(f"✅ Текст отправлен в чат {chat_id}")
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки текста в чат: {e}")
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
    
    return False

# ========== ФОРМИРОВАНИЕ И ОТПРАВКА УВЕДОМЛЕНИЙ ==========

def send_match_notification(event_key, stage=None, date=None, matches=None, **kwargs):
    """Отправить уведомление с матчами в общий чат"""
    template = get_notification_template(event_key)
    if not template:
        print(f"❌ Шаблон {event_key} не найден")
        return
    
    lines = []
    
    # Заголовок
    if template.get("header"):
        header = template["header"]
        if stage is not None:
            header = header.replace("{stage}", str(stage))
        if date:
            header = header.replace("{date}", date)
        lines.append(header)
        lines.append("")
    
    # Матчи
    if matches:
        for m in matches:
            if m["team1_km"] > m["team2_km"]:
                line = f"✅ {m['team1_name']} {m['team1_km']:.1f} км 🆚 {m['team2_km']:.1f} км {m['team2_name']} ❌"
            elif m["team2_km"] > m["team1_km"]:
                line = f"❌ {m['team1_name']} {m['team1_km']:.1f} км 🆚 {m['team2_km']:.1f} км {m['team2_name']} ✅"
            else:
                if m.get("team1_time", 0) < m.get("team2_time", 0):
                    line = f"✅ {m['team1_name']} {m['team1_km']:.1f} км 🆚 {m['team2_km']:.1f} км {m['team2_name']} ❌"
                else:
                    line = f"❌ {m['team1_name']} {m['team1_km']:.1f} км 🆚 {m['team2_km']:.1f} км {m['team2_name']} ✅"
            lines.append(line)
        lines.append("")
    
    # Топ-4
    if event_key == "top4" and kwargs.get("teams"):
        for i, team in enumerate(kwargs["teams"], 1):
            emoji = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"][i-1]
            lines.append(f"{emoji} {team['name']} — {team['points']} очков (+{team['diff']})")
        lines.append("")
    
    # Подвал
    if template.get("footer"):
        footer = template["footer"]
        # Заменяем литерал \n на реальный перенос строки
        footer = footer.replace('\\n', '\n')
        for key, value in kwargs.items():
            if value is not None:
                footer = footer.replace(f"{{{key}}}", str(value))
        lines.append(footer)
    
    message = "\n".join(lines).strip()
    
    if config.VK_CHAT_ID:
        send_to_chat_text(config.VK_CHAT_ID, message)
        print(f"✅ Уведомление {event_key} отправлено")

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

@app.route("/rating")
def rating_page():
    return render_template("rating.html")

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
        print(f"🔐 Подтверждение сервера")
        return config.VK_CONFIRMATION
    
    if data.get("type") == "message_new":
        msg = data["object"]["message"]
        user_id = msg["from_id"]
        peer_id = msg["peer_id"]
        text = msg.get("text", "").strip()
        attachments = msg.get("attachments", [])
        
        print(f"📨 СООБЩЕНИЕ: user={user_id}, peer={peer_id}, text='{text}'")
        
        # Проверка chatid
        if text in ['/chatid', '/chat_id', 'chatid', 'chat_id']:
            print(f"🔍 КОМАНДА chatid ОБНАРУЖЕНА!")
            try:
                vk = vk_api.VkApi(token=config.VK_GROUP_TOKEN).get_api()
                vk.messages.send(
                    user_id=user_id,
                    message=f"📋 Peer ID: {peer_id}",
                    random_id=random.randint(1, 2147483647),
                    from_group=1
                )
                print(f"✅ Peer ID {peer_id} отправлен в ЛС")
            except Exception as e:
                print(f"❌ Ошибка отправки chatid: {e}")
            return 'ok'
        
        # Проверяем, чат это или ЛС
        is_chat = peer_id > 2000000000
        
        # Игнорируем сообщения из чатов
        if is_chat:
            print(f"⏭️ Сообщение из чата, игнорируем")
            return 'ok'
        
        # Проверяем, есть ли фото и ждём ли мы скриншот
        state = user_states.get(user_id)
        if state and state.get("action") == "waiting_screenshot":
            if attachments and attachments[0].get("type") == "photo":
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
                    return 'ok'
                
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
                    
                    send_vk_message(user_id,
                        f"✅ Тренировка принята!\n\n"
                        f"📅 День {day}\n"
                        f"📏 Дистанция: {distance} км\n"
                        f"⏱ Время: {duration} мин\n"
                        f"⚡ Темп: {pace:.2f} мин/км",
                        get_main_keyboard()
                    )
                    
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
                
                return 'ok'
            else:
                send_vk_message(user_id, "❌ Отправьте скриншот (фото):", get_cancel_keyboard())
                return 'ok'
        
        # Обработка текстовых состояний
        if handle_state(user_id, text):
            return 'ok'
        
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
    
    return 'ok'

# ========== ТЕСТОВЫЕ МАРШРУТЫ ==========

@app.route("/test/create-pairs/<int:stage>", methods=["GET", "POST"])
def test_create_pairs(stage):
    result = create_stage_pairs(stage)
    if result:
        return f"✅ Создано {result['count']} пар для этапа {stage} (дата: {result['date']})"
    return "❌ Ошибка создания пар"

@app.route("/test/create-playoff", methods=["GET", "POST"])
def test_create_playoff():
    result = create_playoff_pairs()
    if result:
        return f"✅ Создано {result['count']} пар для полуфиналов"
    return "❌ Ошибка создания пар"

@app.route("/test/calculate/<int:stage>", methods=["GET", "POST"])
def test_calculate_stage(stage):
    results = calculate_stage_results(stage)
    return jsonify({"count": len(results), "results": results})

@app.route("/test/calculate-semi", methods=["GET", "POST"])
def test_calculate_semi():
    """Подсчёт результатов полуфинала"""
    results = calculate_stage_results("semi")
    return jsonify({"count": len(results), "results": results})

@app.route("/test/calculate-final", methods=["GET", "POST"])
def test_calculate_final():
    """Подсчёт результатов финала"""
    results = calculate_stage_results("final")
    return jsonify({"count": len(results), "results": results})

@app.route("/test/notify/<event_key>", methods=["GET", "POST"])
def test_send_notification(event_key):
    """Универсальный обработчик уведомлений"""
    
    # Жеребьёвка этапа: stage_pairing_1, stage_pairing_2, ...
    if event_key.startswith("stage_pairing_"):
        stage = int(event_key.split("_")[-1])
        matches = get_stage_matches(stage)
        if matches:
            calendar = supabase.table("calendar").select("stage_date").eq("stage", stage).execute()
            date_str = calendar.data[0]["stage_date"] if calendar.data else f"этап {stage}"
            
            lines = [f"🔥 ЖЕРЕБЬЁВКА ЭТАПА №{stage} ({date_str})", ""]
            for m in matches:
                if not m.get("team1_km") and not m.get("team2_km"):
                    lines.append(f"{m['team1_name']} 🆚 {m['team2_name']}")
            lines.append("")
            lines.append("Удачи всем командам! 🏃‍♂️")
            send_to_chat_text(config.VK_CHAT_ID, "\n".join(lines))
            return f"✅ Жеребьёвка этапа {stage} отправлена"
    
    # Предварительные/окончательные этапа: stage_1_preliminary, stage_2_final, ...
    elif event_key.startswith("stage_") and ("_preliminary" in event_key or "_final" in event_key):
        parts = event_key.split("_")
        stage = int(parts[1])
        n_type = parts[2]  # "preliminary" или "final"
        
        matches = get_stage_matches(stage)
        if matches:
            formatted = []
            for m in matches:
                formatted.append({
                    "team1_name": m["team1_name"], "team1_km": m.get("team1_km", 0),
                    "team2_name": m["team2_name"], "team2_km": m.get("team2_km", 0)
                })
            
            calendar = supabase.table("calendar").select("stage_date").eq("stage", stage).execute()
            date_str = calendar.data[0]["stage_date"] if calendar.data else f"этап {stage}"
            
            send_match_notification(
                f"stage_{n_type}",
                stage=stage,
                date=date_str,
                matches=formatted,
                rating_url="https://bitva-okrugov.onrender.com/rating"
            )
            return f"✅ {n_type} этапа {stage} отправлено"
    
    # Топ-4
    elif event_key == "top4":
        teams = get_top4_teams()
        if teams and len(teams) >= 4:
            formatted = [{"name": t["name"], "points": t["points"], "diff": t["wins"] - t["losses"]} for t in teams]
            send_match_notification("top4", teams=formatted, semi_date="24 июня",
                                    team1=teams[0]["name"], team4=teams[3]["name"],
                                    team2=teams[1]["name"], team3=teams[2]["name"])
            return "✅ Топ-4 отправлен"
    
    # Пары полуфинала
    elif event_key == "semi_pairs":
        top4 = get_top4_teams()
        if top4 and len(top4) >= 4:
            lines = [
                "🔥 ПОЛУФИНАЛЫ | 24 июня",
                "",
                f"🥇 {top4[0]['name']} 🆚 {top4[3]['name']}",
                f"🥈 {top4[1]['name']} 🆚 {top4[2]['name']}",
                "",
                "Удачи всем командам! 🏃‍♂️"
            ]
            send_to_chat_text(config.VK_CHAT_ID, "\n".join(lines))
            return "✅ Пары полуфинала отправлены"
    
    # Предварительные/окончательные полуфинала
    elif event_key in ["semi_preliminary", "semi_final"]:
        matches = get_stage_matches("semi")
        if matches:
            formatted = []
            for m in matches:
                formatted.append({
                    "team1_name": m["team1_name"], "team1_km": m.get("team1_km", 0),
                    "team2_name": m["team2_name"], "team2_km": m.get("team2_km", 0)
                })
            n_type = "preliminary" if "preliminary" in event_key else "final"
            send_match_notification(f"semi_{n_type}", date="24 июня", matches=formatted)
            return f"✅ {n_type} полуфинала отправлено"
    
    # Пары финала
    elif event_key == "final_pairs":
    semi_matches = get_stage_matches("semi")
    winners, losers = [], []
    for m in semi_matches:
        if m.get("winner_id"):
            if m["winner_id"] == m.get("team1_id"):
                winners.append(m["team1_name"]); losers.append(m["team2_name"])
            else:
                winners.append(m["team2_name"]); losers.append(m["team1_name"])
    if len(winners) >= 2 and len(losers) >= 2:
        send_match_notification("final_pairs",
            final_team1=winners[0], final_team2=winners[1],
            third_team1=losers[0], third_team2=losers[1])
        return "✅ Пары финала отправлены"
    
    # Предварительные/окончательные финала
    elif event_key in ["final_preliminary", "final_final"]:
        matches = get_stage_matches("final")
        if matches:
            formatted = []
            for m in matches:
                formatted.append({
                    "team1_name": m["team1_name"], "team1_km": m.get("team1_km", 0),
                    "team2_name": m["team2_name"], "team2_km": m.get("team2_km", 0)
                })
            n_type = "preliminary" if "preliminary" in event_key else "final"
            
            # Для final_final определяем победителя
            if n_type == "final" and matches:
                m = matches[0]
                winner = m["team1_name"] if m.get("winner_id") == m.get("team1_id") else m["team2_name"]
                second = m["team2_name"] if winner == m["team1_name"] else m["team1_name"]
                send_match_notification("final_final", date="27 июня", winner=winner, second=second, third="?",
                                        rating_url="https://bitva-okrugov.onrender.com/rating")
            else:
                send_match_notification(f"final_{n_type}", date="27 июня", matches=formatted)
            return f"✅ {n_type} финала отправлено"
    
    return f"❌ Неизвестный event_key: {event_key}"

@app.route("/test/cleanup", methods=["GET", "POST"])
def test_cleanup():
    try:
        supabase.table("participants").delete().like("first_name", "Тест%").execute()
        supabase.table("teams").delete().or_("name.like.%Тест%,name.like.%Сборная%").execute()
        supabase.table("matches").delete().neq("id", 0).execute()
        supabase.table("calendar").delete().eq("is_test", True).execute()
        return "✅ Тестовые данные удалены"
    except Exception as e:
        return f"❌ Ошибка: {e}"

@app.route("/test/full-notifications", methods=["GET", "POST"])
def test_full_notifications():
    """Полный прогон всех уведомлений от жеребьёвки до финала"""
    results = []
    
    try:
        # ========== ЭТАП 1 ==========
        results.append("--- ЭТАП 1 ---")
        
        pairs = create_stage_pairs(1)
        if pairs:
            matches = get_stage_matches(1)
            if matches:
                lines = ["🔥 ЖЕРЕБЬЁВКА ЭТАПА №1 (9 мая)", ""]
                for m in matches:
                    lines.append(f"{m['team1_name']} 🆚 {m['team2_name']}")
                lines.append("")
                lines.append("Удачи всем командам! 🏃‍♂️")
                send_to_chat_text(config.VK_CHAT_ID, "\n".join(lines))
                results.append("✅ Жеребьёвка отправлена")
        
        calc = calculate_stage_results(1)
        matches = get_stage_matches(1)
        if matches:
            formatted = []
            for m in matches:
                formatted.append({
                    "team1_name": m["team1_name"], "team1_km": m.get("team1_km", 0), "team1_time": m.get("team1_time", 0),
                    "team2_name": m["team2_name"], "team2_km": m.get("team2_km", 0), "team2_time": m.get("team2_time", 0)
                })
            
            send_match_notification("stage_preliminary", stage=1, date="9 мая", matches=formatted)
            results.append("✅ Предварительные результаты отправлены")
            
            send_match_notification("stage_final", stage=1, date="9 мая", matches=formatted, 
                                    rating_url="https://bitva-okrugov.onrender.com/rating")
            results.append("✅ Окончательные результаты отправлены")
        
        # ========== ЭТАПЫ 2-7 ==========
        for stage in range(2, 8):
            results.append(f"--- ЭТАП {stage} ---")
            
            date_str = ["11 мая", "13 мая", "15 мая", "17 мая", "19 мая", "21 мая"][stage - 2]
            
            pairs = create_stage_pairs(stage)
            calculate_stage_results(stage)
            matches = get_stage_matches(stage)
            
            if matches:
                formatted = []
                for m in matches:
                    formatted.append({
                        "team1_name": m["team1_name"], "team1_km": m.get("team1_km", 0), "team1_time": m.get("team1_time", 0),
                        "team2_name": m["team2_name"], "team2_km": m.get("team2_km", 0), "team2_time": m.get("team2_time", 0)
                    })
                
                send_match_notification("stage_preliminary", stage=stage, date=date_str, matches=formatted)
                send_match_notification("stage_final", stage=stage, date=date_str, matches=formatted,
                                        rating_url="https://bitva-okrugov.onrender.com/rating")
                results.append(f"✅ Этап {stage}: уведомления отправлены")
        
        # ========== ТОП-4 ==========
        results.append("--- ТОП-4 ---")
        
        teams = get_top4_teams()
        if teams and len(teams) >= 4:
            formatted = []
            for t in teams:
                formatted.append({
                    "name": t["name"], "points": t["points"], "diff": t["wins"] - t["losses"]
                })
            
            send_match_notification(
                "top4", teams=formatted, semi_date="24 мая",
                team1=teams[0]["name"], team4=teams[3]["name"],
                team2=teams[1]["name"], team3=teams[2]["name"]
            )
            results.append("✅ Топ-4 отправлен")
        else:
            results.append("⚠️ Недостаточно команд для топ-4")
            return jsonify(results)
        
        # ========== ПОЛУФИНАЛЫ ==========
        results.append("--- ПОЛУФИНАЛЫ ---")
        
        playoff = create_playoff_pairs()
        if not playoff:
            results.append("⚠️ Не удалось создать пары полуфиналов")
            return jsonify(results)
        
        calc_semi = calculate_stage_results("semi")
        matches = get_stage_matches("semi")
        
        if not matches or len(matches) < 2:
            results.append("⚠️ Полуфиналы: недостаточно матчей")
            return jsonify(results)
        
        formatted = []
        for m in matches:
            formatted.append({
                "team1_name": m["team1_name"], "team1_km": m.get("team1_km", 0), "team1_time": m.get("team1_time", 0),
                "team2_name": m["team2_name"], "team2_km": m.get("team2_km", 0), "team2_time": m.get("team2_time", 0)
            })
        
        send_match_notification("semi_preliminary", date="24 мая", matches=formatted)
        results.append("✅ Предварительные результаты полуфиналов отправлены")
        
        winner1 = None
        winner2 = None
        loser1 = None
        loser2 = None
        
        if matches[0].get("winner_id"):
            if matches[0]["winner_id"] == matches[0].get("team1_id"):
                winner1 = {"id": matches[0]["team1_id"], "name": matches[0]["team1_name"]}
                loser1 = {"id": matches[0]["team2_id"], "name": matches[0]["team2_name"]}
            else:
                winner1 = {"id": matches[0]["team2_id"], "name": matches[0]["team2_name"]}
                loser1 = {"id": matches[0]["team1_id"], "name": matches[0]["team1_name"]}
        
        if len(matches) > 1 and matches[1].get("winner_id"):
            if matches[1]["winner_id"] == matches[1].get("team1_id"):
                winner2 = {"id": matches[1]["team1_id"], "name": matches[1]["team1_name"]}
                loser2 = {"id": matches[1]["team2_id"], "name": matches[1]["team2_name"]}
            else:
                winner2 = {"id": matches[1]["team2_id"], "name": matches[1]["team2_name"]}
                loser2 = {"id": matches[1]["team1_id"], "name": matches[1]["team1_name"]}
        
        final_team1 = winner1["name"] if winner1 else "?"
        final_team2 = winner2["name"] if winner2 else "?"
        third_team1 = loser1["name"] if loser1 else "?"
        third_team2 = loser2["name"] if loser2 else "?"
        
        send_match_notification("semi_final", date="24 мая", matches=formatted,
                                final_date="27 мая",
                                final_team1=final_team1,
                                final_team2=final_team2,
                                third_team1=third_team1,
                                third_team2=third_team2,
                                rating_url="https://bitva-okrugov.onrender.com/rating")
        results.append("✅ Окончательные результаты полуфиналов отправлены")
        
        # ========== ФИНАЛ ==========
        results.append("--- ФИНАЛ ---")
        
        if not winner1 or not winner2:
            results.append("⚠️ Нет двух победителей полуфиналов")
            return jsonify(results)
        
        supabase.table("matches").insert({
            "stage": "final",
            "match_date": "2026-05-27",
            "team1_id": winner1["id"],
            "team1_name": winner1["name"],
            "team2_id": winner2["id"],
            "team2_name": winner2["name"],
            "status": "pending"
        }).execute()
        
        calculate_stage_results("final")
        final_matches = get_stage_matches("final")
        
        if not final_matches or len(final_matches) == 0:
            results.append("⚠️ Финал: нет матчей")
            return jsonify(results)
        
        m = final_matches[0]
        formatted_final = [{
            "team1_name": m["team1_name"], "team1_km": m.get("team1_km", 0), "team1_time": m.get("team1_time", 0),
            "team2_name": m["team2_name"], "team2_km": m.get("team2_km", 0), "team2_time": m.get("team2_time", 0)
        }]
        
        if m.get("winner_id"):
            if m["winner_id"] == m.get("team1_id"):
                winner_team = m["team1_name"]
                second_team = m["team2_name"]
            else:
                winner_team = m["team2_name"]
                second_team = m["team1_name"]
        else:
            winner_team = winner1["name"]
            second_team = winner2["name"]
        
        third_team = "?"
        if loser1 and loser1["name"] not in [winner_team, second_team]:
            third_team = loser1["name"]
        elif loser2 and loser2["name"] not in [winner_team, second_team]:
            third_team = loser2["name"]
        
        send_match_notification("final_preliminary", date="27 мая", matches=formatted_final)
        results.append("✅ Предварительные результаты финала отправлены")
        
        send_match_notification("final_final", date="27 мая",
                                winner=winner_team, second=second_team, third=third_team,
                                rating_url="https://bitva-okrugov.onrender.com/rating")
        results.append("✅ Окончательные результаты финала отправлены")
        
        return jsonify(results)
        
    except Exception as e:
        results.append(f"❌ ОШИБКА: {str(e)}")
        import traceback
        results.append(traceback.format_exc())
        return jsonify(results), 500

# ========== ЗАПУСК ==========

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
