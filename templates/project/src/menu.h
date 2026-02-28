// vig8 - Menu bar and config dialogs
// Native Win32 menu bar + ImGui config dialogs for settings management

#pragma once

#include <memory>
#include <functional>
#include <filesystem>

namespace rex {
class Runtime;
}

namespace rex::ui {
class MenuItem;
class ImGuiDrawer;
class Window;
class WindowedAppContext;
}

struct Vig8Settings;

class MenuSystem {
public:
    MenuSystem(rex::ui::ImGuiDrawer* imgui_drawer,
               rex::ui::Window* window,
               rex::ui::WindowedAppContext* app_context,
               rex::Runtime* runtime,
               Vig8Settings* settings,
               const std::filesystem::path& settings_path,
               std::function<void()> on_settings_changed);
    ~MenuSystem();

    // Build and return the menu bar. Call once, then pass to Window::SetMainMenu().
    std::unique_ptr<rex::ui::MenuItem> BuildMenuBar();

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
