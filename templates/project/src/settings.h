// vig8 - Settings persistence
// Loads/saves user configuration from vig8_settings.toml

#pragma once

#include <string>
#include <filesystem>

struct Vig8Settings {
    // [gfx]
    std::string render_path = "rov";  // "rov" or "rtv"
    int resolution_scale = 1;         // 1 or 2
    bool fullscreen = false;

    // [game]
    bool full_game = true;  // unlock all content (skip trial mode)

    // [controls]
    // Per-slot: "auto", "none", or "keyboard"
    std::string controller_1 = "auto";
    std::string controller_2 = "none";
    std::string controller_3 = "none";
    std::string controller_4 = "none";
    // Per-slot sign-in: player 1 always connected, others opt-in
    bool connected_2 = false;
    bool connected_3 = false;
    bool connected_4 = false;

    // [network]
    int lan_port = 3074;  // UDP port for LAN discovery/QoS beacons

    // [debug]
    bool show_fps = true;
    bool show_console = false;
    bool invulnerable = false;
    bool unlock_all_cars = false;
};

// Global debug flags (defined in stubs.cpp, set from ApplySettings)
extern bool g_vig8_invulnerable;
extern bool g_vig8_unlock_all_cars;

// Per-slot sign-in state (defined in stubs.cpp, set from ApplySettings)
// Player 1 is always connected; slots 1-3 controlled by settings.
extern bool g_vig8_user_connected[4];

// Load settings from TOML file. Returns defaults if file doesn't exist or fails to parse.
Vig8Settings LoadSettings(const std::filesystem::path& path);

// Save settings to TOML file.
void SaveSettings(const std::filesystem::path& path, const Vig8Settings& settings);
