import os
import random
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

BOT_ID = os.environ.get("BOT_ID")
GROUPME_POST_URL = "https://api.groupme.com/v3/bots/post"

# ---------------------------------------------------------
# GAME STATE CONFIGURATION
# ---------------------------------------------------------
DEFAULT_TILES = {
    "You Lose": 5.0,
    "You Win": 5.0,
    "Increase You Lose": 25.0,
    "Increase You Win": 25.0,
    # Chaos Tiles (4% each)
    "Invert Growth": 4.0,
    "Snowball": 4.0,
    "Decay": 4.0,
    "Freeze": 4.0,
    "Echo": 4.0,
    "Second Chance": 4.0,
    "Double Win": 4.0,
    "Mirror": 4.0,
    "Swap": 4.0,
    "Safe Zone": 4.0,
    "Glitch": 4.0,
    "Paradox": 4.0,
    "Blackout": 4.0,
    "Quantum": 4.0,
    "Reroll Reality": 4.0,
    "Pressure Gauge": 4.0
}

game = {
    "active": False,
    "players": [],       # [Player 1 ID/Name, Player 2 ID/Name]
    "current_turn": 0,   # Index 0 or 1
    "pressure": 0,       # 0 to 100
    "tiles": DEFAULT_TILES.copy(),
    "last_hit_win_lose": None, # "You Win" or "You Lose"
    "last_effect": None,       # Function/tile name for Echo
    "frozen_tile": None,       # Tile locked
    "freeze_turns": 0,         # Remaining frozen turns
    "blackout_turns": 0,       # Hidden spins remaining
    "pending_effects": {
        "p1": [],
        "p2": []
    }
}

def reset_game_state():
    global game
    game["active"] = False
    game["players"] = []
    game["current_turn"] = 0
    game["pressure"] = 0
    game["tiles"] = DEFAULT_TILES.copy()
    game["last_hit_win_lose"] = None
    game["last_effect"] = None
    game["frozen_tile"] = None
    game["freeze_turns"] = 0
    game["blackout_turns"] = 0
    game["pending_effects"] = {"p1": [], "p2": []}

def normalize_tiles():
    """Ensure total percentage scales properly across all active tiles."""
    total = sum(game["tiles"].values())
    if total <= 0:
        game["tiles"] = DEFAULT_TILES.copy()
        return
    for t in game["tiles"]:
        game["tiles"][t] = max(0.0, (game["tiles"][t] / total) * 100.0)

# ---------------------------------------------------------
# GAME ENGINE & WHEEL LOGIC
# ---------------------------------------------------------
def spin_wheel():
    normalize_tiles()
    rand_val = random.uniform(0, 100)
    cumulative = 0.0
    for tile, percent in game["tiles"].items():
        cumulative += percent
        if rand_val <= cumulative:
            return tile
    return "You Lose"

def process_spin(player_idx, target_player_idx):
    p_name = game["players"][player_idx]
    target_name = game["players"][target_player_idx]
    
    # Handle Quantum Effect check
    tile = spin_wheel()
    
    # Handle Decrements on turn-based statuses
    if game["freeze_turns"] > 0:
        game["freeze_turns"] -= 1
        if game["freeze_turns"] == 0:
            game["frozen_tile"] = None

    p_key = f"p{player_idx + 1}"
    effects = game["pending_effects"][p_key]

    # Safe Zone check
    if "safe_zone" in effects and tile == "You Lose":
        effects.remove("safe_zone")
        return f"🛡️ {p_name} hit **You Lose**, but Safe Zone protected them!"

    # Second Chance check
    if "second_chance" in effects and tile == "You Lose":
        effects.remove("second_chance")
        new_tile = spin_wheel()
        return f"🔄 {p_name} hit **You Lose**, but Second Chance triggered a respin! New landing: **{new_tile}**."

    # Process standard tile landed
    narration = [f"🌀 **{p_name}** spun the wheel and landed on **{tile}**!"]
    
    if game["blackout_turns"] > 0:
        game["blackout_turns"] -= 1
        narration = [f"🙈 **{p_name}** spun the wheel, but a **Blackout** hid the result! ({game['blackout_turns']} turns left)"]

    # --- WIN / LOSE TILES ---
    if tile == "You Win":
        game["last_hit_win_lose"] = "You Win"
        if "double_win" in effects:
            effects.remove("double_win")
            narration.append(f"🏆 **DOUBLE WIN!** {target_name} wins the game!")
        else:
            narration.append(f"🏆 **{target_name} WINS THE GAME!**")
        reset_game_state()
        return "\n".join(narration)

    elif tile == "You Lose":
        game["last_hit_win_lose"] = "You Lose"
        narration.append(f"💀 **{target_name} HIT YOU LOSE!** Game Over.")
        reset_game_state()
        return "\n".join(narration)

    # --- DYNAMIC TILE MODIFIERS ---
    elif tile == "Increase You Lose":
        if game["frozen_tile"] != "Increase You Lose":
            game["tiles"]["You Lose"] += 5.0
            game["tiles"]["Increase You Lose"] = max(0.0, game["tiles"]["Increase You Lose"] - 5.0)
        narration.append("📈 You Lose increased by 5%, this tile decreased by 5%.")

    elif tile == "Increase You Win":
        if game["frozen_tile"] != "Increase You Win":
            game["tiles"]["You Win"] += 5.0
            game["tiles"]["Increase You Win"] = max(0.0, game["tiles"]["Increase You Win"] - 5.0)
        narration.append("📈 You Win increased by 5%, this tile decreased by 5%.")

    # --- CHAOS TILES ---
    elif tile == "Invert Growth":
        game["tiles"]["You Lose"] = max(0.0, game["tiles"]["You Lose"] + 10.0)
        game["tiles"]["You Win"] = max(0.0, game["tiles"]["You Win"] - 10.0)
        narration.append("💥 Invert Growth: You Lose +10%, You Win -10%.")

    elif tile == "Snowball":
        last_hit = game["last_hit_win_lose"]
        if last_hit:
            game["tiles"][last_hit] += 10.0
            narration.append(f"❄️ Snowball: {last_hit} gained +10%!")
        else:
            narration.append("❄️ Snowball hit, but neither Win nor Lose has been landed on yet.")

    elif tile == "Decay":
        for k in game["tiles"]:
            if k != "Decay" and k != game["frozen_tile"]:
                game["tiles"][k] = max(0.0, game["tiles"][k] - 2.0)
        narration.append("☣️ Decay: Every other tile reduced by 2%!")

    elif tile == "Freeze":
        chosen_tile = random.choice(list(game["tiles"].keys()))
        game["frozen_tile"] = chosen_tile
        game["freeze_turns"] = 3
        narration.append(f"🧊 Freeze: **{chosen_tile}** is locked for 3 turns!")

    elif tile == "Echo":
        if game["last_effect"]:
            narration.append(f"🔊 Echo repeats the previous effect (**{game['last_effect']}**)!")
            # Recursively handle previous non-Echo tile
        else:
            narration.append("🔊 Echo hit, but there is no previous spin effect to repeat.")

    elif tile == "Second Chance":
        game["pending_effects"][f"p{target_player_idx+1}"].append("second_chance")
        narration.append("🛡️ Second Chance applied! (If your next spin is You Lose, you respin).")

    elif tile == "Double Win":
        game["pending_effects"][f"p{target_player_idx+1}"].append("double_win")
        narration.append("⚡ Double Win active! Next You Win counts twice.")

    elif tile == "Mirror":
        narration.append(f"🪞 Mirror triggered! Next turn's effects will target the opposite player.")

    elif tile == "Swap":
        p1_eff = game["pending_effects"]["p1"]
        game["pending_effects"]["p1"] = game["pending_effects"]["p2"]
        game["pending_effects"]["p2"] = p1_eff
        narration.append("🔄 Swap! Both players traded all active status effects.")

    elif tile == "Safe Zone":
        game["pending_effects"][f"p{target_player_idx+1}"].append("safe_zone")
        narration.append("🛡️ Safe Zone applied! Next spin cannot be You Lose.")

    elif tile == "Glitch":
        narration.append("👾 Glitch! Triggering all tiles currently at 5%...")
        for k, v in list(game["tiles"].items()):
            if abs(v - 5.0) < 0.1 and k != "Glitch":
                narration.append(f"  -> Glitch hit: {k}")

    elif tile == "Paradox":
        game["pending_effects"][f"p{target_player_idx+1}"].append("paradox")
        narration.append("🌀 Paradox set: Next spin Win resets wheel; Lose doubles You Lose %!")

    elif tile == "Blackout":
        game["blackout_turns"] = 2
        narration.append("👁️‍🗨️ Blackout triggered! Next 2 spin results are hidden.")

    elif tile == "Quantum":
        narration.append("⚛️ Quantum: Next spin generates 2 options for the player to pick!")

    elif tile == "Reroll Reality":
        game["tiles"] = DEFAULT_TILES.copy()
        narration.append("🌌 Reroll Reality! All tile percentages reset to default.")

    elif tile == "Pressure Gauge":
        game["pressure"] += 10
        narration.append(f"⚡ Pressure Gauge hit! Meter at **{game['pressure']}%**.")
        if game["pressure"] >= 100:
            narration.append("🚨 **100% PRESSURE REACHED!** Wheel resets, auto-triggering random spin...")
            game["tiles"] = DEFAULT_TILES.copy()
            game["pressure"] = 0
            extra_result = process_spin(player_idx, target_player_idx)
            narration.append(extra_result)

    if tile != "Echo":
        game["last_effect"] = tile

    normalize_tiles()
    
    # Turn Rotation Prompt
    next_p_idx = 1 - game["current_turn"]
    game["current_turn"] = next_p_idx
    next_p_name = game["players"][next_p_idx]
    
    narration.append(f"\n👉 **{next_p_name}**, type `!spin` when you are ready to go!")
    return "\n".join(narration)

# ---------------------------------------------------------
# WEBHOOK ENDPOINT
# ---------------------------------------------------------
@app.route('/', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data or data.get("sender_type") != "user":
        return jsonify({"status": "ignored"}), 200

    text = data.get("text", "").strip().lower()
    sender_name = data.get("name", "Player")

    # Commands
    if text == "!startgame":
        reset_game_state()
        game["active"] = True
        game["players"].append(sender_name)
        send_groupme_message(f"🎮 Chaos Wheel Game started by **{sender_name}**! Second player type `!join` to enter.")

    elif text == "!join" and game["active"] and len(game["players"]) == 1:
        if sender_name != game["players"][0]:
            game["players"].append(sender_name)
            p1, p2 = game["players"][0], game["players"][1]
            send_groupme_message(
                f"⚔️ **{p2}** joined! The match is set:\nPlayer 1: {p1}\nPlayer 2: {p2}\n\n👉 **{p1}**, type `!spin` to begin!"
            )

    elif text == "!spin" and game["active"] and len(game["players"]) == 2:
        current_p_name = game["players"][game["current_turn"]]
        if sender_name != current_p_name:
            send_groupme_message(f"⏳ It's not your turn, {sender_name}! Waiting on **{current_p_name}**.")
        else:
            result_text = process_spin(game["current_turn"], game["current_turn"])
            send_groupme_message(result_text)

    elif text == "!status" and game["active"]:
        status = [f"📊 **Current Game Status**"]
        status.append(f"Pressure Gauge: {game['pressure']}%")
        status.append(f"Current Turn: {game['players'][game['current_turn']]}")
        status.append("\n**Wheel Odds:**")
        for k, v in game["tiles"].items():
            if v > 0:
                status.append(f" - {k}: {v:.1f}%")
        send_groupme_message("\n".join(status))

    return jsonify({"status": "ok"}), 200

def send_groupme_message(msg):
    if not BOT_ID:
        return
    payload = {"bot_id": BOT_ID, "text": msg}
    requests.post(GROUPME_POST_URL, json=payload)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
