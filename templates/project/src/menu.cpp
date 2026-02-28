// vig8 - Menu bar and config dialogs implementation

#include "menu.h"
#include "settings.h"

#include <rex/ui/menu_item.h>
#include <rex/ui/window.h>
#include <rex/ui/windowed_app.h>
#include <rex/ui/imgui_dialog.h>
#include <rex/ui/imgui_drawer.h>
#include <rex/runtime.h>
#include <rex/kernel/kernel_state.h>
#include <rex/input/input_system.h>
#include <rex/input/input.h>
#include <rex/stream.h>

#include <SDL2/SDL_gamecontroller.h>
#include <SDL2/SDL_joystick.h>

#include <imgui.h>

#include <fstream>
#include <vector>
#include <string>

using namespace rex::ui;

// ============================================================================
// Dialog classes
// ============================================================================

// Helpers for consistent button layout
static void RightAlignedButtons(float button_width = 80.0f) {
    float avail = ImGui::GetContentRegionAvail().x;
    ImGui::SetCursorPosX(ImGui::GetCursorPosX() + avail - button_width * 2 - 8);
}

// ============================================================================
// Graphics dialog
// ============================================================================

class GraphicsDialog : public ImGuiDialog {
public:
    GraphicsDialog(ImGuiDrawer* drawer, WindowedAppContext* app_context,
                   Window* window, Vig8Settings* settings,
                   const std::filesystem::path& settings_path,
                   std::function<void()> on_done)
        : ImGuiDialog(drawer), app_context_(app_context), window_(window),
          settings_(settings), settings_path_(settings_path),
          on_done_(std::move(on_done)) {
        render_path_idx_ = (settings->render_path == "rtv") ? 1 : 0;
        resolution_scale_idx_ = (settings->resolution_scale >= 2) ? 1 : 0;
        fullscreen_ = settings->fullscreen;
    }

protected:
    void OnDraw(ImGuiIO& io) override {
        (void)io;
        ImGui::SetNextWindowSize(ImVec2(400, 220), ImGuiCond_FirstUseEver);
        if (ImGui::Begin("Graphics##vig8", nullptr,
                         ImGuiWindowFlags_NoCollapse |
                         ImGuiWindowFlags_NoResize)) {
            ImGui::Text("Render Path:");
            ImGui::SameLine(160);
            ImGui::SetNextItemWidth(180);
            const char* path_items[] = {"ROV (Recommended)", "RTV"};
            ImGui::Combo("##render_path", &render_path_idx_, path_items, 2);

            ImGui::Text("Resolution Scale:");
            ImGui::SameLine(160);
            ImGui::SetNextItemWidth(180);
            const char* scale_items[] = {"1x", "2x"};
            ImGui::Combo("##resolution_scale", &resolution_scale_idx_, scale_items, 2);

            ImGui::Checkbox("Fullscreen (F11)", &fullscreen_);

            ImGui::Spacing();
            ImGui::TextDisabled("Render path and resolution scale require restart.");

            ImGui::Spacing();
            ImGui::Separator();
            ImGui::Spacing();

            RightAlignedButtons();
            if (ImGui::Button("OK", ImVec2(80, 0))) {
                settings_->render_path = (render_path_idx_ == 0) ? "rov" : "rtv";
                settings_->resolution_scale = (resolution_scale_idx_ == 0) ? 1 : 2;
                bool fs_changed = (settings_->fullscreen != fullscreen_);
                settings_->fullscreen = fullscreen_;
                SaveSettings(settings_path_, *settings_);
                // Defer fullscreen change to avoid crash during ImGui draw
                if (fs_changed && window_ && app_context_) {
                    bool fs = fullscreen_;
                    auto* w = window_;
                    app_context_->CallInUIThreadDeferred([w, fs]() {
                        w->SetFullscreen(fs);
                    });
                }
                Close();
                if (on_done_) on_done_();
            }
            ImGui::SameLine();
            if (ImGui::Button("Cancel", ImVec2(80, 0))) {
                Close();
                if (on_done_) on_done_();
            }
        }
        ImGui::End();
    }

private:
    WindowedAppContext* app_context_;
    Window* window_;
    Vig8Settings* settings_;
    std::filesystem::path settings_path_;
    std::function<void()> on_done_;
    int render_path_idx_ = 0;
    int resolution_scale_idx_ = 0;
    bool fullscreen_ = false;
};

// ============================================================================
// Game dialog
// ============================================================================

class GameDialog : public ImGuiDialog {
public:
    GameDialog(ImGuiDrawer* drawer, Vig8Settings* settings,
               const std::filesystem::path& settings_path,
               std::function<void()> on_done)
        : ImGuiDialog(drawer), settings_(settings),
          settings_path_(settings_path), on_done_(std::move(on_done)) {
        full_game_ = settings->full_game;
    }

protected:
    void OnDraw(ImGuiIO& io) override {
        (void)io;
        ImGui::SetNextWindowSize(ImVec2(350, 140), ImGuiCond_FirstUseEver);
        if (ImGui::Begin("Game Options##vig8", nullptr,
                         ImGuiWindowFlags_NoCollapse |
                         ImGuiWindowFlags_NoResize)) {
            ImGui::Checkbox("Unlock full game (skip trial mode)", &full_game_);

            ImGui::Spacing();
            ImGui::Separator();
            ImGui::Spacing();

            RightAlignedButtons();
            if (ImGui::Button("OK", ImVec2(80, 0))) {
                settings_->full_game = full_game_;
                SaveSettings(settings_path_, *settings_);
                Close();
                if (on_done_) on_done_();
            }
            ImGui::SameLine();
            if (ImGui::Button("Cancel", ImVec2(80, 0))) {
                Close();
                if (on_done_) on_done_();
            }
        }
        ImGui::End();
    }

private:
    Vig8Settings* settings_;
    std::filesystem::path settings_path_;
    std::function<void()> on_done_;
    bool full_game_ = true;
};

// ============================================================================
// Debug dialog
// ============================================================================

class DebugDialog : public ImGuiDialog {
public:
    DebugDialog(ImGuiDrawer* drawer, Vig8Settings* settings,
                const std::filesystem::path& settings_path,
                std::function<void()> on_done)
        : ImGuiDialog(drawer), settings_(settings),
          settings_path_(settings_path), on_done_(std::move(on_done)) {
        show_fps_ = settings->show_fps;
        show_console_ = settings->show_console;
        invulnerable_ = settings->invulnerable;
        unlock_all_cars_ = settings->unlock_all_cars;
    }

protected:
    void OnDraw(ImGuiIO& io) override {
        (void)io;
        ImGui::SetNextWindowSize(ImVec2(370, 240), ImGuiCond_FirstUseEver);
        if (ImGui::Begin("Debug Options##vig8", nullptr,
                         ImGuiWindowFlags_NoCollapse |
                         ImGuiWindowFlags_NoResize)) {
            ImGui::Checkbox("Show FPS overlay", &show_fps_);
            ImGui::Checkbox("Show debug console", &show_console_);
            ImGui::Separator();
            ImGui::Checkbox("Player invulnerable", &invulnerable_);
            ImGui::SameLine();
            ImGui::TextDisabled("(TODO)");
            ImGui::Checkbox("Unlock all vehicles", &unlock_all_cars_);
            ImGui::TextDisabled("Vehicle unlock requires restart to take effect.");

            ImGui::Spacing();
            ImGui::Separator();
            ImGui::Spacing();

            RightAlignedButtons();
            if (ImGui::Button("OK", ImVec2(80, 0))) {
                settings_->show_fps = show_fps_;
                settings_->show_console = show_console_;
                settings_->invulnerable = invulnerable_;
                settings_->unlock_all_cars = unlock_all_cars_;
                SaveSettings(settings_path_, *settings_);
                Close();
                if (on_done_) on_done_();
            }
            ImGui::SameLine();
            if (ImGui::Button("Cancel", ImVec2(80, 0))) {
                Close();
                if (on_done_) on_done_();
            }
        }
        ImGui::End();
    }

private:
    Vig8Settings* settings_;
    std::filesystem::path settings_path_;
    std::function<void()> on_done_;
    bool show_fps_ = true;
    bool show_console_ = false;
    bool invulnerable_ = false;
    bool unlock_all_cars_ = false;
};

// ============================================================================
// Controls dialog — physical controller assignment
// ============================================================================

// Info about a physical SDL game controller
struct PhysicalController {
    int device_index;           // SDL device index (for opening/naming)
    SDL_JoystickID instance_id; // SDL instance ID (for tracking)
    std::string name;           // Human-readable name
};

// Enumerate connected SDL game controllers
static std::vector<PhysicalController> EnumerateControllers() {
    std::vector<PhysicalController> result;
    int n = SDL_NumJoysticks();
    for (int i = 0; i < n; i++) {
        if (!SDL_IsGameController(i)) continue;
        PhysicalController pc;
        pc.device_index = i;
        pc.instance_id = SDL_JoystickGetDeviceInstanceID(i);
        const char* name = SDL_GameControllerNameForIndex(i);
        pc.name = name ? name : "Unknown Controller";
        result.push_back(std::move(pc));
    }
    return result;
}

class ControlsDialog : public ImGuiDialog {
public:
    ControlsDialog(ImGuiDrawer* drawer, Vig8Settings* settings,
                   const std::filesystem::path& settings_path,
                   std::function<void()> on_done)
        : ImGuiDialog(drawer), settings_(settings),
          settings_path_(settings_path), on_done_(std::move(on_done)) {
        connected_[0] = true;  // Player 1 always connected
        connected_[1] = settings->connected_2;
        connected_[2] = settings->connected_3;
        connected_[3] = settings->connected_4;
        RefreshControllers();
    }

protected:
    void OnDraw(ImGuiIO& io) override {
        (void)io;
        ImGui::SetNextWindowSize(ImVec2(590, 280), ImGuiCond_FirstUseEver);
        if (ImGui::Begin("Controllers##vig8", nullptr,
                         ImGuiWindowFlags_NoCollapse |
                         ImGuiWindowFlags_NoResize)) {

            if (ImGui::Button("Refresh")) {
                RefreshControllers();
            }
            ImGui::SameLine();
            ImGui::TextDisabled("%d controller(s) detected",
                                (int)physical_.size());

            ImGui::Spacing();

            if (ImGui::BeginTable("##controllers", 3,
                                  ImGuiTableFlags_RowBg |
                                  ImGuiTableFlags_BordersInnerH)) {
                ImGui::TableSetupColumn("Player Slot",
                                        ImGuiTableColumnFlags_WidthFixed, 100);
                ImGui::TableSetupColumn("Connected",
                                        ImGuiTableColumnFlags_WidthFixed, 70);
                ImGui::TableSetupColumn("Assigned Controller",
                                        ImGuiTableColumnFlags_WidthStretch);
                ImGui::TableHeadersRow();

                for (int slot = 0; slot < 4; slot++) {
                    ImGui::TableNextRow();
                    ImGui::TableNextColumn();
                    ImGui::Text("Player %d", slot + 1);

                    // Connected checkbox (Player 1 always on)
                    ImGui::TableNextColumn();
                    ImGui::PushID(slot + 100);
                    if (slot == 0) {
                        bool always_on = true;
                        ImGui::BeginDisabled();
                        ImGui::Checkbox("##conn", &always_on);
                        ImGui::EndDisabled();
                    } else {
                        ImGui::Checkbox("##conn", &connected_[slot]);
                    }
                    ImGui::PopID();
                    ImGui::TableNextColumn();

                    ImGui::PushID(slot);
                    ImGui::SetNextItemWidth(-1);

                    // Build combo items: "None", then each physical controller
                    // Current selection: slot_selection_[slot]
                    //   0 = None, 1..N = physical controller index+1
                    const char* preview = "None";
                    if (slot_selection_[slot] > 0 &&
                        slot_selection_[slot] <= (int)physical_.size()) {
                        preview = physical_[slot_selection_[slot] - 1]
                                      .name.c_str();
                    }

                    if (ImGui::BeginCombo("##ctrl", preview)) {
                        // "None" option
                        if (ImGui::Selectable("None",
                                              slot_selection_[slot] == 0)) {
                            slot_selection_[slot] = 0;
                        }
                        // Each physical controller
                        for (int j = 0; j < (int)physical_.size(); j++) {
                            // Mark if already assigned to another slot
                            bool in_use = false;
                            for (int k = 0; k < 4; k++) {
                                if (k != slot &&
                                    slot_selection_[k] == j + 1) {
                                    in_use = true;
                                    break;
                                }
                            }
                            std::string label = physical_[j].name;
                            if (in_use) label += " (in use)";

                            if (ImGui::Selectable(label.c_str(),
                                                  slot_selection_[slot] ==
                                                      j + 1)) {
                                slot_selection_[slot] = j + 1;
                            }
                        }
                        ImGui::EndCombo();
                    }
                    ImGui::PopID();
                }
                ImGui::EndTable();
            }

            ImGui::Spacing();
            ImGui::Separator();
            ImGui::Spacing();

            RightAlignedButtons();
            if (ImGui::Button("OK", ImVec2(80, 0))) {
                ApplyAssignments();
                SaveSettings(settings_path_, *settings_);
                Close();
                if (on_done_) on_done_();
            }
            ImGui::SameLine();
            if (ImGui::Button("Cancel", ImVec2(80, 0))) {
                Close();
                if (on_done_) on_done_();
            }
        }
        ImGui::End();
    }

private:
    void RefreshControllers() {
        physical_ = EnumerateControllers();

        // Initialize slot selections from current SDL player index assignments
        for (int slot = 0; slot < 4; slot++)
            slot_selection_[slot] = 0;

        for (int j = 0; j < (int)physical_.size(); j++) {
            auto* gc = SDL_GameControllerFromInstanceID(
                physical_[j].instance_id);
            if (gc) {
                int player = SDL_GameControllerGetPlayerIndex(gc);
                if (player >= 0 && player < 4) {
                    slot_selection_[player] = j + 1;
                }
            }
        }
    }

    void ApplyAssignments() {
        // First, unassign all controllers (set player index to -1)
        for (auto& pc : physical_) {
            auto* gc = SDL_GameControllerFromInstanceID(pc.instance_id);
            if (gc) {
                SDL_GameControllerSetPlayerIndex(gc, -1);
            }
        }

        // Then assign selected controllers to their slots
        for (int slot = 0; slot < 4; slot++) {
            int sel = slot_selection_[slot];
            if (sel > 0 && sel <= (int)physical_.size()) {
                auto* gc = SDL_GameControllerFromInstanceID(
                    physical_[sel - 1].instance_id);
                if (gc) {
                    SDL_GameControllerSetPlayerIndex(gc, slot);
                }
            }
        }

        // Save controller names to settings for reference
        auto get_name = [&](int slot) -> std::string {
            int sel = slot_selection_[slot];
            if (sel > 0 && sel <= (int)physical_.size())
                return physical_[sel - 1].name;
            return "none";
        };
        settings_->controller_1 = get_name(0);
        settings_->controller_2 = get_name(1);
        settings_->controller_3 = get_name(2);
        settings_->controller_4 = get_name(3);

        // Save connected state and update sign-in globals
        settings_->connected_2 = connected_[1];
        settings_->connected_3 = connected_[2];
        settings_->connected_4 = connected_[3];
        g_vig8_user_connected[0] = true;
        g_vig8_user_connected[1] = connected_[1];
        g_vig8_user_connected[2] = connected_[2];
        g_vig8_user_connected[3] = connected_[3];

        // Notify the game that sign-in state changed so it re-queries
        auto* ks = rex::kernel::kernel_state();
        if (ks) {
            uint32_t mask = 0;
            for (int i = 0; i < 4; i++)
                if (g_vig8_user_connected[i]) mask |= (1u << i);
            ks->BroadcastNotification(0x0000000A, mask);  // XN_SYS_SIGNINCHANGED
        }
    }

    Vig8Settings* settings_;
    std::filesystem::path settings_path_;
    std::function<void()> on_done_;
    std::vector<PhysicalController> physical_;
    int slot_selection_[4] = {};  // 0=None, 1..N=physical index+1
    bool connected_[4] = {true, false, false, false};
};

// ============================================================================
// MenuSystem implementation
// ============================================================================

struct MenuSystem::Impl {
    ImGuiDrawer* imgui_drawer;
    Window* window;
    WindowedAppContext* app_context;
    rex::Runtime* runtime;
    Vig8Settings* settings;
    std::filesystem::path settings_path;
    std::function<void()> on_settings_changed;

    // Active dialog tracking
    GraphicsDialog* gfx_dialog = nullptr;
    GameDialog* game_dialog = nullptr;
    DebugDialog* debug_dialog = nullptr;
    ControlsDialog* controls_dialog = nullptr;

    template <typename T>
    std::function<void()> MakeOnDone(T*& tracking_ptr, bool notify = true) {
        return [this, &tracking_ptr, notify]() {
            app_context->CallInUIThreadDeferred([this, &tracking_ptr, notify]() {
                tracking_ptr = nullptr;
                if (notify && on_settings_changed) on_settings_changed();
            });
        };
    }

    void ShowGraphicsDialog() {
        if (gfx_dialog) return;
        gfx_dialog = new GraphicsDialog(imgui_drawer, app_context, window,
                                        settings, settings_path,
                                        MakeOnDone(gfx_dialog));
    }

    void ShowGameDialog() {
        if (game_dialog) return;
        game_dialog = new GameDialog(imgui_drawer, settings, settings_path,
                                     MakeOnDone(game_dialog));
    }

    void ShowDebugDialog() {
        if (debug_dialog) return;
        debug_dialog = new DebugDialog(imgui_drawer, settings, settings_path,
                                       MakeOnDone(debug_dialog));
    }

    void ShowControlsDialog() {
        if (controls_dialog) return;
        controls_dialog = new ControlsDialog(
            imgui_drawer, settings, settings_path,
            MakeOnDone(controls_dialog, false));
    }

    void ShowAbout() {
        ImGuiDialog::ShowMessageBox(
            imgui_drawer,
            "About Vigilante 8 Arcade",
            "Vigilante 8 Arcade - Static Recompilation\n\n"
            "Built with ReXGlue SDK\n"
            "https://github.com/sp00nznet/vig8");
    }

    void SaveState() {
        if (!runtime || !runtime->kernel_state()) {
            ImGuiDialog::ShowMessageBox(imgui_drawer, "Save State",
                                        "Runtime not available.");
            return;
        }

        // Allocate a large buffer for state serialization
        constexpr size_t kMaxStateSize = 256 * 1024 * 1024;  // 256 MB
        std::vector<uint8_t> buffer(kMaxStateSize);
        rex::stream::ByteStream stream(buffer.data(), buffer.size());

        if (!runtime->kernel_state()->Save(&stream)) {
            ImGuiDialog::ShowMessageBox(imgui_drawer, "Save State",
                                        "Failed to save state.");
            return;
        }

        // Write only the bytes that were used
        auto save_path = settings_path.parent_path() / "vig8_savestate.bin";
        std::ofstream f(save_path, std::ios::binary);
        if (!f) {
            ImGuiDialog::ShowMessageBox(imgui_drawer, "Save State",
                                        "Failed to open save file.");
            return;
        }
        f.write(reinterpret_cast<const char*>(buffer.data()), stream.offset());
        f.close();

        ImGuiDialog::ShowMessageBox(
            imgui_drawer, "Save State",
            ("State saved to " + save_path.filename().string() +
             " (" + std::to_string(stream.offset() / 1024) + " KB)").c_str());
    }

    void LoadState() {
        // KernelState::Restore while the game is actively running is unsafe
        // (it modifies threads, memory, and kernel objects mid-execution).
        // Show a warning instead of crashing.
        ImGuiDialog::ShowMessageBox(
            imgui_drawer, "Load State",
            "Load state is not yet supported while the game is running.\n\n"
            "Save states can be created for future use once\n"
            "a safe restore mechanism is implemented.");
    }
};

MenuSystem::MenuSystem(ImGuiDrawer* imgui_drawer, Window* window,
                       WindowedAppContext* app_context,
                       rex::Runtime* runtime,
                       Vig8Settings* settings,
                       const std::filesystem::path& settings_path,
                       std::function<void()> on_settings_changed)
    : impl_(std::make_unique<Impl>()) {
    impl_->imgui_drawer = imgui_drawer;
    impl_->window = window;
    impl_->app_context = app_context;
    impl_->runtime = runtime;
    impl_->settings = settings;
    impl_->settings_path = settings_path;
    impl_->on_settings_changed = std::move(on_settings_changed);
}

MenuSystem::~MenuSystem() = default;

std::unique_ptr<MenuItem> MenuSystem::BuildMenuBar() {
    auto* ctx = impl_.get();

    // Root menu bar
    auto root = MenuItem::Create(MenuItem::Type::kNormal);

    // --- File menu ---
    auto file_menu = MenuItem::Create(MenuItem::Type::kPopup, "File");

    file_menu->AddChild(MenuItem::Create(
        MenuItem::Type::kString, "Save State...",
        [ctx]() { ctx->SaveState(); }));

    file_menu->AddChild(MenuItem::Create(
        MenuItem::Type::kString, "Load State...",
        [ctx]() { ctx->LoadState(); }));

    file_menu->AddChild(MenuItem::Create(MenuItem::Type::kSeparator));

    file_menu->AddChild(MenuItem::Create(
        MenuItem::Type::kString, "Exit",
        [ctx]() { ctx->app_context->QuitFromUIThread(); }));

    root->AddChild(std::move(file_menu));

    // --- Config menu ---
    auto config_menu = MenuItem::Create(MenuItem::Type::kPopup, "Config");

    config_menu->AddChild(MenuItem::Create(
        MenuItem::Type::kString, "Controllers...",
        [ctx]() { ctx->ShowControlsDialog(); }));

    config_menu->AddChild(MenuItem::Create(
        MenuItem::Type::kString, "Graphics...",
        [ctx]() { ctx->ShowGraphicsDialog(); }));

    config_menu->AddChild(MenuItem::Create(
        MenuItem::Type::kString, "Game...",
        [ctx]() { ctx->ShowGameDialog(); }));

    config_menu->AddChild(MenuItem::Create(
        MenuItem::Type::kString, "Debug...",
        [ctx]() { ctx->ShowDebugDialog(); }));

    root->AddChild(std::move(config_menu));

    // --- Help menu ---
    auto help_menu = MenuItem::Create(MenuItem::Type::kPopup, "Help");

    help_menu->AddChild(MenuItem::Create(
        MenuItem::Type::kString, "About...",
        [ctx]() { ctx->ShowAbout(); }));

    root->AddChild(std::move(help_menu));

    return root;
}
