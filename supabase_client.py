from supabase import create_client, Client
import config
from datetime import datetime
import pytz
import re
import random

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
            .order("id")\
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

def get_next_team_number(region):
    """Получить следующий порядковый номер для сборной в регионе"""
    try:
        response = supabase.table("teams")\
            .select("name")\
            .eq("region", region)\
            .like("name", f"{region} Сборная #%")\
            .execute()
        
        if not response.data:
            return 1
        
        max_num = 0
        for team in response.data:
            match = re.search(r'#(\d+)$', team["name"])
            if match:
                num = int(match.group(1))
                if num > max_num:
                    max_num = num
        
        return max_num + 1
    except:
        return 1

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
        payment_data = {
            "payment_id": payment_id,
            "type": "team",
            "amount": amount,
            "team_name": team_name,
            "region": region,
            "payer_name": members[0].get("first", "") + " " + members[0].get("last", ""),
            "status": "paid",
            "created_at": get_current_date().isoformat(),
            "processed_at": get_current_date().isoformat()
        }
        supabase.table("payments").insert(payment_data).execute()
        
        team_data = {
            "name": team_name,
            "region": region,
            "member_count": 4,
            "is_full": True,
            "status": "active"
        }
        team_response = supabase.table("teams").insert(team_data).execute()
        team = team_response.data[0]
        team_id = team["id"]
        
        for i, m in enumerate(members):
            is_captain = (i == 0)
            participant_data = {
                "vk_id": None,
                "first_name": m["first"],
                "last_name": m["last"],
                "gender": m["gender"],
                "region": region,
                "team_id": team_id,
                "team_name": team_name,
                "is_captain": is_captain,
                "total_km": 0,
                "total_min": 0,
                "status": "pending",
                "registered_at": get_current_date().date().isoformat(),
                "payment_id": payment_id
            }
            response = supabase.table("participants").insert(participant_data).execute()
            
            if is_captain:
                participant_id = response.data[0]["id"]
                supabase.table("teams").update({
                    "captain_id": participant_id,
                    "captain_name": f"{m['first']} {m['last']}"
                }).eq("id", team_id).execute()
        
        return team
        
    except Exception as e:
        print(f"Error registering team: {e}")
        return None

def register_solo_payment(payment_id, region, first_name, last_name, gender, amount):
    try:
        payment_data = {
            "payment_id": payment_id,
            "type": "solo",
            "amount": amount,
            "region": region,
            "payer_name": f"{first_name} {last_name}",
            "status": "paid",
            "created_at": get_current_date().isoformat(),
            "processed_at": get_current_date().isoformat()
        }
        supabase.table("payments").insert(payment_data).execute()
        
        team = find_incomplete_team(region)
        team_id = None
        team_name = None
        is_captain = False
        
        if not team:
            team_number = get_next_team_number(region)
            team_name = f"{region} Сборная #{team_number}"
            new_team = create_team(team_name, region)
            team_id = new_team["id"]
            is_captain = True
        else:
            team_id = team["id"]
            team_name = team["name"]
            is_captain = False
            new_count = team["member_count"] + 1
            is_full = new_count >= 4
            update_team_member_count(team_id, new_count, is_full)
        
        participant_data = {
            "vk_id": None,
            "first_name": first_name,
            "last_name": last_name,
            "gender": gender,
            "region": region,
            "team_id": team_id,
            "team_name": team_name,
            "is_captain": is_captain,
            "total_km": 0,
            "total_min": 0,
            "status": "pending",
            "registered_at": get_current_date().date().isoformat(),
            "payment_id": payment_id
        }
        
        response = supabase.table("participants").insert(participant_data).execute()
        participant_id = response.data[0]["id"]
        
        if is_captain:
            supabase.table("teams").update({
                "captain_id": participant_id,
                "captain_name": f"{first_name} {last_name}"
            }).eq("id", team_id).execute()
        
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

# ========== УВЕДОМЛЕНИЯ ==========

def get_notification_template(event_key):
    try:
        response = supabase.table("notifications")\
            .select("*")\
            .eq("event_key", event_key)\
            .eq("is_active", True)\
            .execute()
        return response.data[0] if response.data else None
    except:
        return None

# ========== ЖЕРЕБЬЁВКА ==========

def get_teams_warmup_stats():
    """Получить статистику команд за разминку"""
    teams = get_all_active_teams()
    
    warmup_stats = []
    for team in teams:
        stats = supabase.table("workouts")\
            .select("final_km, final_min")\
            .eq("team_id", team["id"])\
            .eq("status", "verified")\
            .execute()
        
        total_km = sum(w["final_km"] for w in stats.data) if stats.data else 0
        total_min = sum(w["final_min"] for w in stats.data) if stats.data else 0
        
        warmup_stats.append({
            "id": team["id"],
            "name": team["name"],
            "region": team["region"],
            "total_km": total_km,
            "total_min": total_min
        })
    
    warmup_stats.sort(key=lambda x: x["total_km"], reverse=True)
    return warmup_stats

def create_stage_pairs(stage):
    """Создать пары для этапа"""
    
    calendar = supabase.table("calendar")\
        .select("stage_date")\
        .eq("stage", stage)\
        .execute()
    
    if not calendar.data:
        return None
    
    match_date = calendar.data[0]["stage_date"]
    
    if stage == 1:
        teams = get_teams_warmup_stats()
    else:
        teams = supabase.table("teams")\
            .select("*")\
            .eq("status", "active")\
            .order("points", desc=True)\
            .order("wins", desc=True)\
            .order("total_km", desc=True)\
            .execute().data
    
    if len(teams) < 2:
        return None
    
    pairs = []
    if stage == 1:
        mid = len(teams) // 2
        basket_a = teams[:mid]
        basket_b = teams[mid:]
        random.shuffle(basket_a)
        random.shuffle(basket_b)
        for ta, tb in zip(basket_a, basket_b):
            pairs.append({"team1": ta, "team2": tb})
    else:
        for i in range(0, len(teams), 2):
            if i + 1 < len(teams):
                pairs.append({"team1": teams[i], "team2": teams[i+1]})
    
    for pair in pairs:
        supabase.table("matches").insert({
            "stage": stage,
            "match_date": match_date,
            "team1_id": pair["team1"]["id"],
            "team1_name": pair["team1"]["name"],
            "team2_id": pair["team2"]["id"],
            "team2_name": pair["team2"]["name"],
            "status": "pending"
        }).execute()
    
    return {"count": len(pairs), "date": match_date}

def create_playoff_pairs():
    """Создать пары для полуфиналов (топ-4)"""
    top4 = supabase.table("teams")\
        .select("*")\
        .eq("status", "active")\
        .order("points", desc=True)\
        .order("wins", desc=True)\
        .order("total_km", desc=True)\
        .limit(4)\
        .execute().data
    
    if len(top4) < 4:
        return None
    
    calendar = supabase.table("calendar")\
        .select("stage_date")\
        .eq("stage", 8)\
        .execute()
    
    if not calendar.data:
        return None
    
    match_date = calendar.data[0]["stage_date"]
    
    semi_pairs = [
        {"team1": top4[0], "team2": top4[3]},
        {"team1": top4[1], "team2": top4[2]}
    ]
    
    for pair in semi_pairs:
        supabase.table("matches").insert({
            "stage": "semi",
            "match_date": match_date,
            "team1_id": pair["team1"]["id"],
            "team1_name": pair["team1"]["name"],
            "team2_id": pair["team2"]["id"],
            "team2_name": pair["team2"]["name"],
            "status": "pending"
        }).execute()
    
    return {"count": 2, "date": match_date, "top4": top4}

def create_final_pairs(semi_winners):
    """Создать финальные пары"""
    if len(semi_winners) < 2:
        return None
    
    calendar = supabase.table("calendar")\
        .select("stage_date")\
        .eq("stage", 9)\
        .execute()
    
    if not calendar.data:
        return None
    
    match_date = calendar.data[0]["stage_date"]
    
    supabase.table("matches").insert({
        "stage": "final",
        "match_date": match_date,
        "team1_id": semi_winners[0]["id"],
        "team1_name": semi_winners[0]["name"],
        "team2_id": semi_winners[1]["id"],
        "team2_name": semi_winners[1]["name"],
        "status": "pending"
    }).execute()
    
    return {"date": match_date}

# ========== ПОДСЧЁТ РЕЗУЛЬТАТОВ ==========

def calculate_stage_results(stage):
    """Подсчитать результаты этапа"""
    
    matches = supabase.table("matches")\
        .select("*")\
        .eq("stage", stage)\
        .eq("status", "pending")\
        .execute().data
    
    results = []
    for m in matches:
        team1_stats = supabase.table("workouts")\
            .select("final_km, final_min")\
            .eq("team_id", m["team1_id"])\
            .eq("workout_date", m["match_date"])\
            .eq("status", "verified")\
            .execute()
        
        team2_stats = supabase.table("workouts")\
            .select("final_km, final_min")\
            .eq("team_id", m["team2_id"])\
            .eq("workout_date", m["match_date"])\
            .eq("status", "verified")\
            .execute()
        
        team1_km = sum(w["final_km"] for w in team1_stats.data) if team1_stats.data else 0
        team1_time = sum(w["final_min"] for w in team1_stats.data) if team1_stats.data else 0
        team2_km = sum(w["final_km"] for w in team2_stats.data) if team2_stats.data else 0
        team2_time = sum(w["final_min"] for w in team2_stats.data) if team2_stats.data else 0
        
        if team1_km > team2_km:
            winner_id = m["team1_id"]
        elif team2_km > team1_km:
            winner_id = m["team2_id"]
        else:
            winner_id = m["team1_id"] if team1_time < team2_time else m["team2_id"]
        
        supabase.table("matches").update({
            "team1_km": team1_km,
            "team2_km": team2_km,
            "team1_time": team1_time,
            "team2_time": team2_time,
            "winner_id": winner_id,
            "status": "completed"
        }).eq("id", m["id"]).execute()
        
        try:
            if winner_id == m["team1_id"]:
                supabase.rpc('increment_team_points', {'team_id': m["team1_id"], 'is_win': True}).execute()
                supabase.rpc('increment_team_points', {'team_id': m["team2_id"], 'is_win': False}).execute()
            else:
                supabase.rpc('increment_team_points', {'team_id': m["team2_id"], 'is_win': True}).execute()
                supabase.rpc('increment_team_points', {'team_id': m["team1_id"], 'is_win': False}).execute()
        except:
            # Fallback если RPC не работает
            if winner_id == m["team1_id"]:
                supabase.table("teams").update({"points": supabase.raw("points + 1"), "wins": supabase.raw("wins + 1")}).eq("id", m["team1_id"]).execute()
                supabase.table("teams").update({"losses": supabase.raw("losses + 1")}).eq("id", m["team2_id"]).execute()
            else:
                supabase.table("teams").update({"points": supabase.raw("points + 1"), "wins": supabase.raw("wins + 1")}).eq("id", m["team2_id"]).execute()
                supabase.table("teams").update({"losses": supabase.raw("losses + 1")}).eq("id", m["team1_id"]).execute()
        
        results.append({
            "team1_name": m["team1_name"],
            "team1_km": team1_km,
            "team1_time": team1_time,
            "team2_name": m["team2_name"],
            "team2_km": team2_km,
            "team2_time": team2_time
        })
    
    return results

def get_stage_matches(stage):
    """Получить все матчи этапа"""
    try:
        response = supabase.table("matches")\
            .select("*")\
            .eq("stage", stage)\
            .order("id")\
            .execute()
        return response.data if response.data else []
    except:
        return []

def get_top4_teams():
    """Получить топ-4 команды"""
    try:
        response = supabase.table("teams")\
            .select("*")\
            .eq("status", "active")\
            .order("points", desc=True)\
            .order("wins", desc=True)\
            .order("total_km", desc=True)\
            .limit(4)\
            .execute()
        return response.data if response.data else []
    except:
        return []
