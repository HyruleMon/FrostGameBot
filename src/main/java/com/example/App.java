package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

@SpringBootApplication
@RestController
public class App {

    private static final String GROUPME_POST_URL = "https://api.groupme.com/v3/bots/post";

    // Map Group IDs to their Bot IDs from Environment Variables
    private static final Map<String, String> BOT_MAP = Map.of(
        "12345678", System.getenv().getOrDefault("BOT_ID_MAIN", ""),
        "87654321", System.getenv().getOrDefault("BOT_ID_SUBTOPIC", "")
    );

    // Global in-memory storage for active games per group_id
    private static final Map<String, GameState> games = new ConcurrentHashMap<>();

    public static void main(String[] args) {
        SpringApplication.run(App.class, args);
    }

    @PostMapping("/")
    public Map<String, String> webhook(@RequestBody Map<String, Object> payload) {
        Map<String, String> response = new HashMap<>();

        // Ignore messages from bots/system
        String senderType = (String) payload.get("sender_type");
        if (!"user".equals(senderType)) {
            response.put("status", "ignored");
            return response;
        }

        String groupId = String.valueOf(payload.get("group_id"));
        String senderName = (String) payload.getOrDefault("name", "Player");
        String text = ((String) payload.getOrDefault("text", "")).trim().toLowerCase();

        // Get matching Bot ID for the room
        String botId = BOT_MAP.getOrDefault(groupId, System.getenv("BOT_ID"));
        if (botId == null || botId.isEmpty()) {
            response.put("status", "unconfigured_group");
            return response;
        }

        GameState game = games.computeIfAbsent(groupId, k -> new GameState());

        // --- GAME COMMANDS ---
        if ("!startgame".equals(text)) {
            game.reset();
            game.active = true;
            game.players.add(senderName);
            sendGroupMeMessage(botId, "🎮 Chaos Wheel Game started by **" + senderName + "**! Second player type `!join` to enter.");
        } 
        else if ("!join".equals(text) && game.active && game.players.size() == 1) {
            if (!senderName.equals(game.players.get(0))) {
                game.players.add(senderName);
                String p1 = game.players.get(0);
                String p2 = game.players.get(1);
                sendGroupMeMessage(botId, "⚔️ **" + p2 + "** joined! The match is set:\nPlayer 1: " + p1 + "\nPlayer 2: " + p2 + "\n\n👉 **" + p1 + "**, type `!spin` to begin!");
            }
        } 
        else if ("!spin".equals(text) && game.active && game.players.size() == 2) {
            String currentPName = game.players.get(game.currentTurn);
            if (!senderName.equals(currentPName)) {
                sendGroupMeMessage(botId, "⏳ It's not your turn, " + senderName + "! Waiting on **" + currentPName + "**.");
            } else {
                String resultText = game.processSpin();
                sendGroupMeMessage(botId, resultText);
            }
        } 
        else if ("!status".equals(text) && game.active) {
            StringBuilder status = new StringBuilder("📊 **Current Game Status**\n");
            status.append("Pressure Gauge: ").append(game.pressure).append("%\n");
            status.append("Current Turn: ").append(game.players.get(game.currentTurn)).append("\n\n**Wheel Odds:**\n");
            for (Map.Entry<String, Double> entry : game.tiles.entrySet()) {
                if (entry.getValue() > 0) {
                    status.append(String.format(" - %s: %.1f%%\n", entry.getKey(), entry.getValue()));
                }
            }
            sendGroupMeMessage(botId, status.toString());
        }

        response.put("status", "ok");
        return response;
    }

    private static void sendGroupMeMessage(String botId, String messageText) {
        if (botId == null || botId.isEmpty()) return;

        RestTemplate restTemplate = new RestTemplate();
        Map<String, String> body = new HashMap<>();
        body.put("bot_id", botId);
        body.put("text", messageText);

        try {
            restTemplate.postForEntity(GROUPME_POST_URL, body, String.class);
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    // ---------------------------------------------------------
    // GAME ENGINE & STATE CLASS
    // ---------------------------------------------------------
    static class GameState {
        boolean active = false;
        List<String> players = new ArrayList<>();
        int currentTurn = 0;
        int pressure = 0;
        Map<String, Double> tiles = new LinkedHashMap<>();
        
        String lastHitWinLose = null;
        String lastEffect = null;
        String frozenTile = null;
        int freezeTurns = 0;
        int blackoutTurns = 0;

        Map<String, List<String>> pendingEffects = new HashMap<>();

        private static final Map<String, Double> DEFAULT_TILES = Map.ofEntries(
            Map.entry("You Lose", 5.0), Map.entry("You Win", 5.0),
            Map.entry("Increase You Lose", 25.0), Map.entry("Increase You Win", 25.0),
            Map.entry("Invert Growth", 4.0), Map.entry("Snowball", 4.0),
            Map.entry("Decay", 4.0), Map.entry("Freeze", 4.0),
            Map.entry("Echo", 4.0), Map.entry("Second Chance", 4.0),
            Map.entry("Double Win", 4.0), Map.entry("Mirror", 4.0),
            Map.entry("Swap", 4.0), Map.entry("Safe Zone", 4.0),
            Map.entry("Glitch", 4.0), Map.entry("Paradox", 4.0),
            Map.entry("Blackout", 4.0), Map.entry("Quantum", 4.0),
            Map.entry("Reroll Reality", 4.0), Map.entry("Pressure Gauge", 4.0)
        );

        public GameState() {
            reset();
        }

        public void reset() {
            active = false;
            players.clear();
            currentTurn = 0;
            pressure = 0;
            tiles = new LinkedHashMap<>(DEFAULT_TILES);
            lastHitWinLose = null;
            lastEffect = null;
            frozenTile = null;
            freezeTurns = 0;
            blackoutTurns = 0;
            pendingEffects.put("p1", new ArrayList<>());
            pendingEffects.put("p2", new ArrayList<>());
        }

        public void normalizeTiles() {
            double total = tiles.values().stream().mapToDouble(Double::doubleValue).sum();
            if (total <= 0) {
                tiles = new LinkedHashMap<>(DEFAULT_TILES);
                return;
            }
            for (String key : tiles.keySet()) {
                tiles.put(key, Math.max(0.0, (tiles.get(key) / total) * 100.0));
            }
        }

        public String spinWheel() {
            normalizeTiles();
            double randVal = Math.random() * 100.0;
            double cumulative = 0.0;
            for (Map.Entry<String, Double> entry : tiles.entrySet()) {
                cumulative += entry.getValue();
                if (randVal <= cumulative) {
                    return entry.getKey();
                }
            }
            return "You Lose";
        }

        public String processSpin() {
            int playerIdx = currentTurn;
            int targetPlayerIdx = currentTurn;
            
            String pName = players.get(playerIdx);
            String targetName = players.get(targetPlayerIdx);

            String tile = spinWheel();

            if (freezeTurns > 0) {
                freezeTurns--;
                if (freezeTurns == 0) frozenTile = null;
            }

            String pKey = "p" + (playerIdx + 1);
            List<String> effects = pendingEffects.get(pKey);

            if (effects.contains("safe_zone") && "You Lose".equals(tile)) {
                effects.remove("safe_zone");
                return "🛡️ " + pName + " hit **You Lose**, but Safe Zone protected them!";
            }

            if (effects.contains("second_chance") && "You Lose".equals(tile)) {
                effects.remove("second_chance");
                String newTile = spinWheel();
                return "🔄 " + pName + " hit **You Lose**, but Second Chance triggered a respin! New landing: **" + newTile + "**.";
            }

            List<String> narration = new ArrayList<>();
            narration.add("🌀 **" + pName + "** spun the wheel and landed on **" + tile + "**!");

            if (blackoutTurns > 0) {
                blackoutTurns--;
                narration.set(0, "🙈 **" + pName + "** spun the wheel, but a **Blackout** hid the result! (" + blackoutTurns + " turns left)");
            }

            // --- TILE EFFECTS ---
            switch (tile) {
                case "You Win":
                    lastHitWinLose = "You Win";
                    if (effects.contains("double_win")) {
                        effects.remove("double_win");
                        narration.add("🏆 **DOUBLE WIN!** " + targetName + " wins the game!");
                    } else {
                        narration.add("🏆 **" + targetName + " WINS THE GAME!**");
                    }
                    reset();
                    return String.join("\n", narration);

                case "You Lose":
                    lastHitWinLose = "You Lose";
                    narration.add("💀 **" + targetName + " HIT YOU LOSE!** Game Over.");
                    reset();
                    return String.join("\n", narration);

                case "Increase You Lose":
                    if (!"Increase You Lose".equals(frozenTile)) {
                        tiles.put("You Lose", tiles.get("You Lose") + 5.0);
                        tiles.put("Increase You Lose", Math.max(0.0, tiles.get("Increase You Lose") - 5.0));
                    }
                    narration.add("📈 You Lose increased by 5%, this tile decreased by 5%.");
                    break;

                case "Increase You Win":
                    if (!"Increase You Win".equals(frozenTile)) {
                        tiles.put("You Win", tiles.get("You Win") + 5.0);
                        tiles.put("Increase You Win", Math.max(0.0, tiles.get("Increase You Win") - 5.0));
                    }
                    narration.add("📈 You Win increased by 5%, this tile decreased by 5%.");
                    break;

                case "Invert Growth":
                    tiles.put("You Lose", Math.max(0.0, tiles.get("You Lose") + 10.0));
                    tiles.put("You Win", Math.max(0.0, tiles.get("You Win") - 10.0));
                    narration.add("💥 Invert Growth: You Lose +10%, You Win -10%.");
                    break;

                case "Snowball":
                    if (lastHitWinLose != null) {
                        tiles.put(lastHitWinLose, tiles.get(lastHitWinLose) + 10.0);
                        narration.add("❄️ Snowball: " + lastHitWinLose + " gained +10%!");
                    } else {
                        narration.add("❄️ Snowball hit, but neither Win nor Lose has been landed on yet.");
                    }
                    break;

                case "Decay":
                    for (String k : tiles.keySet()) {
                        if (!k.equals("Decay") && !k.equals(frozenTile)) {
                            tiles.put(k, Math.max(0.0, tiles.get(k) - 2.0));
                        }
                    }
                    narration.add("☣️ Decay: Every other tile reduced by 2%!");
                    break;

                case "Freeze":
                    List<String> keys = new ArrayList<>(tiles.keySet());
                    frozenTile = keys.get((int) (Math.random() * keys.size()));
                    freezeTurns = 3;
                    narration.add("🧊 Freeze: **" + frozenTile + "** is locked for 3 turns!");
                    break;

                case "Echo":
                    if (lastEffect != null) {
                        narration.add("🔊 Echo repeats the previous effect (**" + lastEffect + "**)!");
                    } else {
                        narration.add("🔊 Echo hit, but there is no previous spin effect to repeat.");
                    }
                    break;

                case "Second Chance":
                    pendingEffects.get("p" + (targetPlayerIdx + 1)).add("second_chance");
                    narration.add("🛡️ Second Chance applied!");
                    break;

                case "Double Win":
                    pendingEffects.get("p" + (targetPlayerIdx + 1)).add("double_win");
                    narration.add("⚡ Double Win active! Next You Win counts twice.");
                    break;

                case "Mirror":
                    narration.add("🪞 Mirror triggered! Next turn's effects will target the opposite player.");
                    break;

                case "Swap":
                    List<String> p1Eff = new ArrayList<>(pendingEffects.get("p1"));
                    pendingEffects.put("p1", pendingEffects.get("p2"));
                    pendingEffects.put("p2", p1Eff);
                    narration.add("🔄 Swap! Both players traded active status effects.");
                    break;

                case "Safe Zone":
                    pendingEffects.get("p" + (targetPlayerIdx + 1)).add("safe_zone");
                    narration.add("🛡️ Safe Zone applied!");
                    break;

                case "Glitch":
                    narration.add("👾 Glitch! Triggering all tiles currently at 5%...");
                    for (Map.Entry<String, Double> entry : tiles.entrySet()) {
                        if (Math.abs(entry.getValue() - 5.0) < 0.1 && !"Glitch".equals(entry.getKey())) {
                            narration.add("  -> Glitch hit: " + entry.getKey());
                        }
                    }
                    break;

                case "Paradox":
                    pendingEffects.get("p" + (targetPlayerIdx + 1)).add("paradox");
                    narration.add("🌀 Paradox set: Next spin Win resets wheel; Lose doubles You Lose %!");
                    break;

                case "Blackout":
                    blackoutTurns = 2;
                    narration.add("👁️‍🗨️ Blackout triggered! Next 2 spin results are hidden.");
                    break;

                case "Quantum":
                    narration.add("⚛️ Quantum: Next spin generates 2 options for the player to pick!");
                    break;

                case "Reroll Reality":
                    tiles = new LinkedHashMap<>(DEFAULT_TILES);
                    narration.add("🌌 Reroll Reality! All tile percentages reset to default.");
                    break;

                case "Pressure Gauge":
                    pressure += 10;
                    narration.add("⚡ Pressure Gauge hit! Meter at **" + pressure + "%**.");
                    if (pressure >= 100) {
                        narration.add("🚨 **100% PRESSURE REACHED!** Wheel resets, auto-triggering random spin...");
                        tiles = new LinkedHashMap<>(DEFAULT_TILES);
                        pressure = 0;
                        narration.add(processSpin());
                    }
                    break;
            }

            if (!"Echo".equals(tile)) {
                lastEffect = tile;
            }

            normalizeTiles();

            currentTurn = 1 - currentTurn;
            String nextPName = players.get(currentTurn);
            narration.add("\n👉 **" + next_pName + "**, type `!spin` when you are ready to go!");

            return String.join("\n", narration);
        }
    }
}
