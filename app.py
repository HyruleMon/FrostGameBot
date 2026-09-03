import os
import random
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Map Group IDs to their respective Bot IDs
# Replace these placeholder IDs with your actual Group IDs and Bot IDs
BOT_MAP = {
    "12345678": os.environ.get("BOT_ID_MAIN"),      # Main Group ID : Main Bot ID
    "87654321": os.environ.get("BOT_ID_SUBTOPIC"),   # Subtopic Group ID : Subtopic Bot ID
}

GROUPME_POST_URL = "https://api.groupme.com/v3/bots/post"

# Default game state template
DEFAULT_TILES = {
    "You Lose": 5.0,
    "You Win": 5.0,
    "Increase You Lose": 25.0,
    "Increase You Win": 25.0,
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

# Store game instances per group ID so games in different topics don't collide
games = {}

def get_or_create_game(group_id):
    if group_id not in games:
        games[group_id] = {
            "active": False,
            "players": [],
            "current_turn": 0,
            "pressure": 0,
            "tiles": DEFAULT_TILES.copy(),
            "last_hit_win_lose": None,
            "last_effect": None,
            "frozen_tile": None,
            "freeze_turns": 0,
            "blackout_turns": 0,
            "pending_effects": {"p1": [], "p2": []}
        }
    return games[group_id]

def reset_game_state(group_id):
    if group_id in games:
        del games[group_id]

@app.route('/', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data or data.get("sender_type") != "user":
        return jsonify({"status": "ignored"}), 200

    group_id = str(data.get("group_id"))
    text = data.get("text", "").strip().lower()
    sender_name = data.get("name", "Player")

    # Find the correct Bot ID for the group that sent the message
    bot_id = BOT_MAP.get(group_id) or os.environ.get("BOT_ID")

    if not bot_id:
        return jsonify({"status": "unconfigured_group"}), 200

    game = get_or_create_game(group_id)

    # --- GAME COMMANDS ---
    if text == "!startgame":
        reset_game_state(group_id)
        game = get_or_create_game(group_id)
        game["active"] = True
        game["players"].append(sender_name)
        send_groupme_message(bot_id, f"🎮 Chaos Wheel Game started in this chat by **{sender_name}**! Second player type `!join` to enter.")

    elif text == "!join" and game["active"] and len(game["players"]) == 1:
        if sender_name != game["players"][0]:
            game["players"].append(sender_name)
            p1, p2 = game["players"][0], game["players"][1]
            send_groupme_message(
                bot_id,
                f"⚔️ **{p2}** joined! Match set:\nPlayer 1: {p1}\nPlayer 2: {p2}\n\n👉 **{p1}**, type `!spin` to begin!"
            )

    elif text == "!spin" and game["active"] and len(game["players"]) == 2:
        current_p_name = game["players"][game["current_turn"]]
        if sender_name != current_p_name:
            send_groupme_message(bot_id, f"⏳ It's not your turn, {sender_name}! Waiting on **{current_p_name}**.")
        else:
            # Process game turn (using the logic from your process_spin function)
            # ...
            pass

    return jsonify({"status": "ok"}), 200

def send_groupme_message(bot_id, msg):
    if not bot_id:
        return
    payload = {"bot_id": bot_id, "text": msg}
    requests.post(GROUPME_POST_URL, json=payload)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
