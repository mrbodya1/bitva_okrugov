from flask import Flask, request
import requests
import json
from datetime import datetime
import config
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
    get_all_active_participants,
    get_all_active_teams
)

app = Flask(__name__)

# Хранилище состояний пользователей (в памяти)
user_states = {}

# ========== ОТПРАВКА СООБЩЕНИЙ ВК ==========

def send_vk_message(peer_id, text, keyboard=None):
    url = "https://api.vk.com/method/messages.send"
    payload = {
        "peer_id": peer_id,
        "message": text,
        "random_id": 0,
        "v": "5.199",
        "access_token": config.VK_GROUP_TOKEN
    }
    if keyboard:
        payload["keyboard"] = json.dumps(keyboard)
    
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Ошибка отправки: {e}")

# ========== КЛАВИАТУРЫ ==========

def get_main_keyboard():
    return {
        "one_time": False,
        "buttons": [
            [{"action": {"type": "text", "label": "➕ Добавить тренировку"}, "color": "primary"}],
            [{"action": {"type": "text", "label": "📊 Моя статистика"}, "color": "primary"},
             {"action": {"type": "text", "label": "⭐️ Рейтинг"}, "color": "primary"}],
            [{"action": {"type": "text", "label": "👥 Команды"}, "color": "primary"},
             {"action": {"type": "text", "label": "📋 Правила"}, "color": "secondary"}]
        ]
    }

def get_cancel_keyboard():
    return {
        "one_time": True,
        "buttons": [
            [{"action": {"type": "text", "label": "❌ Отмена"}, "color": "secondary"}]
        ]
    }

# ========== ГЛАВНОЕ МЕНЮ ==========

def send_main_menu(peer_id, first_name):
    day = get_current_day()
    text = f"🏔️ БИТВА ОКРУГОВ\n\nПривет, {first_name}!\nДень {day}\n\nВыберите действие:"
    send_vk_message(peer_id, text, get_main_keyboard())

# ========== ОБРАБОТКА КОМАНД ==========

def handle_start(peer_id, user_id):
    participant = get_participant_by_vk(user_id)
    
    if participant:
        send_main_menu(peer_id, participant["first_name"])
        return
    
    # Проверяем, есть ли ожидающий активации участник
    user_states[user_id] = {"action": "waiting_name"}
    send_vk_message(peer_id, 
        "👋 Добро пожаловать в челлендж «Битва округов»!\n\n"
        "Для активации введите ваши имя и фамилию через пробел.\n"
        "Например: Иван Иванов",
        get_cancel_keyboard()
    )

def handle_add_workout_start(peer_id, user_id):
    participant = get_participant_by_vk(user_id)
    if not participant:
        send_vk_message(peer_id, "❌ Вы не зарегистрированы")
        return
    
    day = get_current_day()
    today_workout = get_today_workout(participant["id"], day)
    
    if today_workout:
        send_vk_message(peer_id, 
            f"❌ Вы уже добавили тренировку сегодня!\n"
            f"📏 {today_workout['original_km']} км за {today_workout['original_min']} мин",
            get_main_keyboard()
        )
        return
    
    user_states[user_id] = {"action": "waiting_distance"}
    send_vk_message(peer_id, 
        "🏃 Добавление тренировки\n\n"
        f"Введите дистанцию в километрах (минимум {config.MIN_KM} км):",
        get_cancel_keyboard()
    )

def handle_stats(peer_id, user_id):
    participant = get_participant_by_vk(user_id)
    if not participant:
        send_vk_message(peer_id, "❌ Вы не зарегистрированы")
        return
    
    stats = get_personal_stats(user_id)
    if not stats:
        send_vk_message(peer_id, "❌ Ошибка получения статистики")
        return
    
    text = f"""📊 ВАША СТАТИСТИКА

👤 {stats['name']}
📍 {stats['region']} | {stats['team']}
👑 {'Капитан' if stats['is_captain'] else 'Участник'}

🏃 Тренировок: {stats['workouts_count']}
📏 Всего км: {stats['total_km']} км
⏱ Всего минут: {stats['total_min']} мин
⚡ Средний темп: {stats['avg_pace']} мин/км"""
    
    send_vk_message(peer_id, text, get_main_keyboard())

def handle_rating(peer_id, user_id):
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
    
    send_vk_message(peer_id, text, get_main_keyboard())

def handle_teams(peer_id, user_id):
    teams = get_team_rating()
    
    text = "👥 РЕЙТИНГ КОМАНД\n\n"
    for i, t in enumerate(teams[:10], 1):
        km = t.get("total_km", 0) or 0
        points = t.get("points", 0) or 0
        text += f"{i}. {t['name']} ({t['region']}) — {km} км | {points} очк.\n"
    
    send_vk_message(peer_id, text, get_main_keyboard())

def handle_rules(peer_id):
    text = f"""📜 ПРАВИЛА ЧЕЛЛЕНДЖА

✅ Минимальная дистанция: {config.MIN_KM} км
✅ Максимальный темп: {config.MAX_PACE}:00 мин/км
✅ Одна тренировка в день
✅ Бег только на улице (дорожка в зале запрещена)
✅ Скриншот тренировки обязателен

🏆 Зачёты:
• Личный — по сумме километров
• Окружной — ХМАО против ЯНАО
• Командный — микро-команды по 4 человека"""
    
    send_vk_message(peer_id, text, get_main_keyboard())

# ========== ОБРАБОТКА СОСТОЯНИЙ ==========

def handle_state(user_id, peer_id, text):
    state = user_states.get(user_id)
    if not state:
        return False
    
    if text == "❌ Отмена":
        del user_states[user_id]
        participant = get_participant_by_vk(user_id)
        if participant:
            send_main_menu(peer_id, participant["first_name"])
        else:
            send_vk_message(peer_id, "Действие отменено. Напишите /start для начала.")
        return True
    
    # Ожидание имени и фамилии для активации
    if state["action"] == "waiting_name":
        parts = text.split()
        if len(parts) < 2:
            send_vk_message(peer_id, "❌ Введите имя и фамилию через пробел:")
            return True
        
        first_name = parts[0]
        last_name = parts[1]
        
        pending = get_pending_participant_by_name(first_name, last_name)
        
        if not pending:
            send_vk_message(peer_id, 
                "❌ Участник не найден. Проверьте правильность имени и фамилии или зарегистрируйтесь на сайте.",
                get_cancel_keyboard()
            )
            return True
        
        # Активируем участника
        activate_participant(pending["id"], user_id)
        del user_states[user_id]
        
        send_vk_message(peer_id, 
            f"✅ Активация успешна!\n\n"
            f"Добро пожаловать, {first_name}!\n"
            f"Округ: {pending['region']}\n"
            f"Команда: {pending['team_name']}"
        )
        send_main_menu(peer_id, first_name)
        return True
    
    # Ожидание дистанции
    if state["action"] == "waiting_distance":
        try:
            distance = float(text.replace(",", "."))
        except:
            send_vk_message(peer_id, "❌ Введите число (например: 5.2):", get_cancel_keyboard())
            return True
        
        if distance < config.MIN_KM:
            send_vk_message(peer_id, f"❌ Минимальная дистанция: {config.MIN_KM} км", get_cancel_keyboard())
            return True
        
        user_states[user_id] = {
            "action": "waiting_duration",
            "distance": distance
        }
        send_vk_message(peer_id, f"✅ Дистанция: {distance} км\n\nВведите время в минутах:", get_cancel_keyboard())
        return True
    
    # Ожидание времени
    if state["action"] == "waiting_duration":
        try:
            duration = int(text)
        except:
            send_vk_message(peer_id, "❌ Введите целое число минут:", get_cancel_keyboard())
            return True
        
        if duration <= 0:
            send_vk_message(peer_id, "❌ Время должно быть больше 0:", get_cancel_keyboard())
            return True
        
        distance = state["distance"]
        pace = duration / distance
        
        if pace > config.MAX_PACE:
            send_vk_message(peer_id, f"❌ Максимальный темп: {config.MAX_PACE}:00 мин/км\nВаш темп: {pace:.2f} мин/км", get_cancel_keyboard())
            return True
        
        participant = get_participant_by_vk(user_id)
        if not participant:
            del user_states[user_id]
            send_vk_message(peer_id, "❌ Ошибка: участник не найден")
            return True
        
        # Сохраняем тренировку
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
            send_vk_message(peer_id,
                f"✅ Тренировка добавлена!\n\n"
                f"📅 День {day}\n"
                f"📏 Дистанция: {distance} км\n"
                f"⏱ Время: {duration} мин\n"
                f"⚡ Темп: {pace:.2f} мин/км"
            )
        else:
            send_vk_message(peer_id, "❌ Ошибка при сохранении тренировки")
        
        send_main_menu(peer_id, participant["first_name"])
        return True
    
    return False

# ========== ВЕБХУК ДЛЯ ВК ==========

@app.route("/", methods=["POST"])
def webhook():
    data = request.json
    
    # Подтверждение сервера
    if data.get("type") == "confirmation":
        return config.VK_CONFIRMATION
    
    # Обработка сообщений
    if data.get("type") == "message_new":
        msg = data["object"]["message"]
        user_id = msg["from_id"]
        peer_id = msg["peer_id"]
        text = msg.get("text", "").strip()
        
        # Игнорируем сообщения из чатов
        if peer_id > 2000000000:
            return "ok"
        
        # Проверяем состояния
        if handle_state(user_id, peer_id, text):
            return "ok"
        
        # Обработка команд
        if text in ["/start", "меню", "Меню", "начать"]:
            handle_start(peer_id, user_id)
        elif text == "➕ Добавить тренировку":
            handle_add_workout_start(peer_id, user_id)
        elif text == "📊 Моя статистика":
            handle_stats(peer_id, user_id)
        elif text == "⭐️ Рейтинг":
            handle_rating(peer_id, user_id)
        elif text == "👥 Команды":
            handle_teams(peer_id, user_id)
        elif text == "📋 Правила":
            handle_rules(peer_id)
        elif text == "/stats":
            # Отладочная информация
            participants = get_all_active_participants()
            teams = get_all_active_teams()
            send_vk_message(peer_id, f"📊 Статистика челленджа:\n\nУчастников: {len(participants)}\nКоманд: {len(teams)}")
        else:
            participant = get_participant_by_vk(user_id)
            if participant:
                send_main_menu(peer_id, participant["first_name"])
            else:
                send_vk_message(peer_id, "Напишите /start для начала работы")
    
    return "ok"

# ========== ЗАПУСК ==========

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)