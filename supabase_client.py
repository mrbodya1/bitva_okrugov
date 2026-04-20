from supabase import create_client, Client
import config
from datetime import datetime
import pytz

supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

moscow_tz = pytz.timezone('Europe/Moscow')

def get_current_date():
    return datetime.now(moscow_tz)

def get_current_day():
    start_date = datetime.strptime(config.START_DATE, '%Y-%m-%d').date()
    now = get_current_date().date()
    diff = (now - start_date).days + 1
    return diff if diff > 0 else 0

# ========== УЧАСТНИКИ ==========

def get_participant_by_vk(vk_id):
    try:
        response = supabase.table("participants")\
            .select("*")\
            .eq("vk_id", vk_id)\
            .eq("status", "active")\
            .execute()
        return response.data[0] if response.data else None
    except:
        return None

def get_participant_by_id(participant_id):
    try:
        response = supabase.table("participants")\
            .select("*")\
            .eq("id", participant_id)\
            .execute()
        return response.data[0] if response.data else None
    except:
        return None

def get_pending_participant_by_name(first_name, last_name):
    try:
        response = supabase.table("participants")\
            .select("*")\
            .eq("first_name", first_name)\
            .eq("last_name", last_name)\
            .eq("status", "pending")\
            .is_("vk_id", "null")\
            .execute()
        return response.data[0] if response.data else None
    except:
        return None

def activate_participant(participant_id, vk_id):
    try:
        supabase.table("participants")\
            .update({"vk_id": vk_id, "status": "active"})\
            .eq("id", participant_id)\
            .execute()
        return True
    except:
        return False

def get_all_active_participants():
    try:
        response = supabase.table("participants")\
            .select("*")\
            .eq("status", "active")\
            .execute()
        return response.data if response.data else []
    except:
        return []

def count_participants_by_region(region):
    try:
        response = supabase.table("participants")\
            .select("id", count="exact")\
            .eq("region", region)\
            .in_("status", ["active", "pending"])\
            .execute()
        return response.count if hasattr(response, 'count') else 0
    except:
        return 0

def update_participant_stats(participant_id, km, minutes):
    try:
        participant = get_participant_by_id(participant_id)
        if participant:
            supabase.table("participants")\
                .update({
                    "total_km": (participant.get("total_km", 0) or 0) + km,
                    "total_min": (participant.get("total_min", 0) or 0) + minutes
                })\
                .eq("id", participant_id)\
                .execute()
        return True
    except:
        return False

# ========== КОМАНДЫ ==========

def get_team_by_id(team_id):
    try:
        response = supabase.table("teams")\
            .select("*")\
            .eq("id", team_id)\
            .execute()
        return response.data[0] if response.data else None
    except:
        return None

def find_incomplete_team(region):
    try:
        response = supabase.table("teams")\
            .select("*")\
            .eq("region", region)\
            .eq("is_full", False)\
            .eq("status", "active")\
            .execute()
        return response.data[0] if response.data else None
    except:
        return None

def get_all_active_teams():
    try:
        response = supabase.table("teams")\
            .select("*")\
            .eq("status", "active")\
            .execute()
        return response.data if response.data else []
    except:
        return []

def create_team(name, region, captain_id=None, captain_name=None):
    try:
        data = {
            "name": name,
            "region": region,
            "captain_id": captain_id,
            "captain_name": captain_name,
            "member_count": 1,
            "is_full": False,
            "status": "active"
        }
        response = supabase.table("teams").insert(data).execute()
        return response.data[0] if response.data else None
    except:
        return None

def update_team_stats(team_id, km, minutes):
    try:
        team = get_team_by_id(team_id)
        if team:
            supabase.table("teams")\
                .update({
                    "total_km": (team.get("total_km", 0) or 0) + km,
                    "total_time": (team.get("total_time", 0) or 0) + minutes
                })\
                .eq("id", team_id)\
                .execute()
        return True
    except:
        return False

def update_team_member_count(team_id, count, is_full):
    try:
        supabase.table("teams")\
            .update({"member_count": count, "is_full": is_full})\
            .eq("id", team_id)\
            .execute()
        return True
    except:
        return False

# ========== ТРЕНИРОВКИ ==========

def add_workout(participant_id, participant_name, team_id, team_name, region, distance, duration):
    try:
        day = get_current_day()
        
        data = {
            "participant_id": participant_id,
            "participant_name": participant_name,
            "team_id": team_id,
            "team_name": team_name,
            "region": region,
            "day": day,
            "original_km": distance,
            "final_km": distance,
            "original_min": duration,
            "final_min": duration,
            "workout_date": get_current_date().date().isoformat(),
            "status": "verified",
            "submitted_at": get_current_date().isoformat()
        }
        
        response = supabase.table("workouts").insert(data).execute()
        
        # Обновляем статистику
        update_participant_stats(participant_id, distance, duration)
        update_team_stats(team_id, distance, duration)
        
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"Error adding workout: {e}")
        return None

def get_workouts_by_participant(participant_id):
    try:
        response = supabase.table("workouts")\
            .select("*")\
            .eq("participant_id", participant_id)\
            .eq("status", "verified")\
            .order("day", desc=True)\
            .execute()
        return response.data if response.data else []
    except:
        return []

def get_today_workout(participant_id, day):
    try:
        response = supabase.table("workouts")\
            .select("*")\
            .eq("participant_id", participant_id)\
            .eq("day", day)\
            .eq("status", "verified")\
            .execute()
        return response.data[0] if response.data else None
    except:
        return None

# ========== РЕГИСТРАЦИЯ ==========

def register_team_payment(payment_id, team_name, region, members, amount):
    try:
        data = {
            "payment_id": payment_id,
            "type": "team",
            "amount": amount,
            "team_name": team_name,
            "region": region,
            "payer_name": members[0].get("first", "") + " " + members[0].get("last", ""),
            "data_json": str(members),
            "status": "pending",
            "created_at": get_current_date().isoformat()
        }
        supabase.table("payments").insert(data).execute()
        
        # Создаём команду
        team = create_team(team_name, region)
        if not team:
            return None
        
        team_id = team["id"]
        
        # Добавляем участников
        for i, m in enumerate(members):
            participant_data = {
                "vk_id": None,
                "first_name": m["first"],
                "last_name": m["last"],
                "gender": m["gender"],
                "region": region,
                "team_id": team_id,
                "team_name": team_name,
                "is_captain": (i == 0),
                "status": "pending",
                "registered_at": get_current_date().date().isoformat(),
                "payment_id": payment_id
            }
            supabase.table("participants").insert(participant_data).execute()
        
        supabase.table("payments")\
            .update({"status": "paid", "processed_at": get_current_date().isoformat()})\
            .eq("payment_id", payment_id)\
            .execute()
        
        return team
    except Exception as e:
        print(f"Error registering team: {e}")
        return None

def register_solo_payment(payment_id, region, first_name, last_name, gender, amount):
    try:
        data = {
            "payment_id": payment_id,
            "type": "solo",
            "amount": amount,
            "region": region,
            "payer_name": f"{first_name} {last_name}",
            "status": "pending",
            "created_at": get_current_date().isoformat()
        }
        supabase.table("payments").insert(data).execute()
        
        # Ищем неполную команду
        team = find_incomplete_team(region)
        team_id = None
        team_name = None
        is_captain = False
        
        if not team:
            team = create_team(f"{region} Сборная", region)
            team_id = team["id"]
            team_name = team["name"]
            is_captain = True
        else:
            team_id = team["id"]
            team_name = team["name"]
            # Обновляем количество участников
            new_count = team["member_count"] + 1
            is_full = new_count >= 4
            update_team_member_count(team_id, new_count, is_full)
        
        # Добавляем участника
        participant_data = {
            "vk_id": None,
            "first_name": first_name,
            "last_name": last_name,
            "gender": gender,
            "region": region,
            "team_id": team_id,
            "team_name": team_name,
            "is_captain": is_captain,
            "status": "pending",
            "registered_at": get_current_date().date().isoformat(),
            "payment_id": payment_id
        }
        supabase.table("participants").insert(participant_data).execute()
        
        supabase.table("payments")\
            .update({"status": "paid", "processed_at": get_current_date().isoformat()})\
            .eq("payment_id", payment_id)\
            .execute()
        
        return {"team_id": team_id, "team_name": team_name}
    except Exception as e:
        print(f"Error registering solo: {e}")
        return None

# ========== СТАТИСТИКА И РЕЙТИНГ ==========

def get_personal_stats(vk_id):
    participant = get_participant_by_vk(vk_id)
    if not participant:
        return None
    
    workouts = get_workouts_by_participant(participant["id"])
    total_km = participant.get("total_km", 0) or 0
    total_min = participant.get("total_min", 0) or 0
    
    avg_pace = total_min / total_km if total_km > 0 else 0
    
    return {
        "name": f"{participant['first_name']} {participant['last_name']}",
        "region": participant["region"],
        "team": participant["team_name"],
        "is_captain": participant["is_captain"],
        "total_km": total_km,
        "total_min": total_min,
        "avg_pace": round(avg_pace, 2),
        "workouts_count": len(workouts)
    }

def get_rating():
    participants = get_all_active_participants()
    
    men = [p for p in participants if p["gender"] == "М"]
    women = [p for p in participants if p["gender"] == "Ж"]
    
    men.sort(key=lambda x: x.get("total_km", 0) or 0, reverse=True)
    women.sort(key=lambda x: x.get("total_km", 0) or 0, reverse=True)
    
    hmao_total = 0
    ynao_total = 0
    
    for p in participants:
        km = p.get("total_km", 0) or 0
        if p["gender"] == "Ж":
            km = km * 1.2
        
        if p["region"] == "ХМАО":
            hmao_total += km
        else:
            ynao_total += km
    
    return {
        "men": men[:10],
        "women": women[:10],
        "regions": {
            "hmao": round(hmao_total, 1),
            "ynao": round(ynao_total, 1),
            "leader": "ХМАО" if hmao_total > ynao_total else "ЯНАО"
        }
    }

def get_team_rating():
    teams = get_all_active_teams()
    teams.sort(key=lambda x: (x.get("points", 0) or 0, x.get("total_km", 0) or 0), reverse=True)
    return teams[:25]