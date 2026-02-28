// vig8 - ReXGlue Recompiled Project
// Vigilante 8 Arcade Static Recompilation

#include "vig8_config.h"
#include "vig8_init.h"
#include "settings.h"
#include "menu.h"
#include "net.h"

#include <rex/cvar.h>
#include <rex/filesystem.h>
#include <rex/runtime.h>
#include <rex/logging.h>
#include <rex/kernel/xthread.h>
#include <rex/kernel/kernel_state.h>
#include <rex/graphics/graphics_system.h>
#include <rex/graphics/flags.h>
#include <rex/ui/window.h>
#include <rex/ui/window_listener.h>
#include <rex/ui/windowed_app.h>
#include <rex/ui/graphics_provider.h>
#include <rex/ui/immediate_drawer.h>
#include <rex/ui/imgui_drawer.h>
#include <rex/ui/imgui_dialog.h>
#include <rex/ui/ui_event.h>
#include <rex/ui/virtual_key.h>

#include <imgui.h>

#include <atomic>
#include <filesystem>
#include <thread>

#ifdef _WIN32
#include <windows.h>
#include <cstdio>
#include <csignal>
#include <cstdlib>
#include <cstdarg>
#include <mutex>

static FILE* g_crash_log = nullptr;
static std::mutex g_crash_mutex;

static void crash_log_write(const char* fmt, ...) {
    std::lock_guard<std::mutex> lock(g_crash_mutex);
    if (!g_crash_log) {
        g_crash_log = fopen("E:\\vig8\\vig8_crash.log", "a");
        if (!g_crash_log) return;
    }
    va_list ap;
    va_start(ap, fmt);
    vfprintf(g_crash_log, fmt, ap);
    va_end(ap);
    fflush(g_crash_log);
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
    fflush(stderr);
}

// Redirect stderr to a log file for GUI app crash diagnostics
static struct StderrRedirect_ {
    StderrRedirect_() {
        freopen("E:\\vig8\\vig8_stderr.log", "w", stderr);
        fprintf(stderr, "[vig8] stderr redirected to log file\n");
        fflush(stderr);
        // Also open dedicated crash log
        g_crash_log = fopen("E:\\vig8\\vig8_crash.log", "w");
        if (g_crash_log) {
            fprintf(g_crash_log, "[vig8] Crash log initialized\n");
            fflush(g_crash_log);
        }
        // Set terminate handler for uncaught C++ exceptions
        std::set_terminate([]() {
            crash_log_write("\n========== TERMINATE CALLED ==========\n");
            crash_log_write("Thread: %lu\n", GetCurrentThreadId());
            try { std::rethrow_exception(std::current_exception()); }
            catch (const std::exception& e) {
                crash_log_write("std::exception: %s\n", e.what());
            }
            catch (...) {
                crash_log_write("Unknown exception type\n");
            }
            crash_log_write("========================================\n");
            std::abort();
        });
    }
} g_stderr_redirect_;

// VEH handler: log ALL crashes/exceptions (runs on any thread)
static LONG CALLBACK CrashVEH(EXCEPTION_POINTERS* ep) {
    auto* ctx = ep->ContextRecord;
    auto* rec = ep->ExceptionRecord;
    // Skip breakpoints and single-step (debugger noise)
    if (rec->ExceptionCode == EXCEPTION_BREAKPOINT ||
        rec->ExceptionCode == EXCEPTION_SINGLE_STEP) return EXCEPTION_CONTINUE_SEARCH;
    crash_log_write("\n========== EXCEPTION ==========\n");
    crash_log_write("Thread: %lu\n", GetCurrentThreadId());
    crash_log_write("Exception: 0x%08lX at RIP=0x%016llX\n",
            rec->ExceptionCode, (unsigned long long)ctx->Rip);
    if (rec->ExceptionCode == STATUS_ACCESS_VIOLATION) {
        crash_log_write("Access address: 0x%016llX (%s)\n",
                (unsigned long long)rec->ExceptionInformation[1],
                rec->ExceptionInformation[0] == 0 ? "READ" : "WRITE");
    }
    if (rec->ExceptionCode == 0xE06D7363) {
        crash_log_write("*** C++ EXCEPTION (throw) ***\n");
        // Try to extract exception message from MSVC exception info
        if (rec->NumberParameters >= 3 && rec->ExceptionInformation[0] == 0x19930520) {
            __try {
                std::exception* ex = reinterpret_cast<std::exception*>(rec->ExceptionInformation[1]);
                if (ex) {
                    crash_log_write("what(): %s\n", ex->what());
                }
            } __except(EXCEPTION_EXECUTE_HANDLER) {
                crash_log_write("(could not read exception object)\n");
            }
        }
    }
    crash_log_write("RAX=0x%016llX RBX=0x%016llX RCX=0x%016llX RDX=0x%016llX\n",
            ctx->Rax, ctx->Rbx, ctx->Rcx, ctx->Rdx);
    crash_log_write("RSI=0x%016llX RDI=0x%016llX RSP=0x%016llX RBP=0x%016llX\n",
            ctx->Rsi, ctx->Rdi, ctx->Rsp, ctx->Rbp);
    crash_log_write("R8 =0x%016llX R9 =0x%016llX R10=0x%016llX R11=0x%016llX\n",
            ctx->R8, ctx->R9, ctx->R10, ctx->R11);
    crash_log_write("R12=0x%016llX R13=0x%016llX R14=0x%016llX R15=0x%016llX\n",
            ctx->R12, ctx->R13, ctx->R14, ctx->R15);
    __try {
        crash_log_write("\nStack (RSP):\n");
        uint64_t* sp = (uint64_t*)ctx->Rsp;
        for (int i = 0; i < 16; i++) {
            __try {
                crash_log_write("  [RSP+%02X] = 0x%016llX\n", i*8, sp[i]);
            } __except(EXCEPTION_EXECUTE_HANDLER) {
                crash_log_write("  [RSP+%02X] = <unreadable>\n", i*8);
            }
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) {}
    crash_log_write("================================\n");
    return EXCEPTION_CONTINUE_SEARCH;
}

// VEH handler: catch null page reads in guest memory and return 0
// Decodes common x86-64 load instructions and zeros the destination register.
static LONG CALLBACK NullPageHandler(EXCEPTION_POINTERS* ep) {
    auto* ctx = ep->ContextRecord;
    auto* rec = ep->ExceptionRecord;
    if (rec->ExceptionCode != STATUS_ACCESS_VIOLATION) return EXCEPTION_CONTINUE_SEARCH;
    if (rec->ExceptionInformation[0] != 0) return EXCEPTION_CONTINUE_SEARCH; // reads only
    uint64_t addr = rec->ExceptionInformation[1];
    uint64_t base = ctx->Rsi;
    if (base >= 0x100000000ULL && base <= 0x200000000ULL &&
        addr >= base && addr < base + 0x10000) {
        uint8_t* rip = (uint8_t*)ctx->Rip;
        int rex = 0, oplen = 0;
        uint8_t op = rip[0];
        if ((op & 0xF0) == 0x40) { rex = op; op = rip[1]; oplen = 1; }

        uint64_t* regs[] = { &ctx->Rax, &ctx->Rcx, &ctx->Rdx, &ctx->Rbx,
                              &ctx->Rsp, &ctx->Rbp, &ctx->Rsi, &ctx->Rdi,
                              &ctx->R8, &ctx->R9, &ctx->R10, &ctx->R11,
                              &ctx->R12, &ctx->R13, &ctx->R14, &ctx->R15 };

        // Helper: decode ModR/M + SIB + displacement length
        auto calc_modrm_len = [](uint8_t* p, int prefix_len) -> int {
            uint8_t modrm = p[prefix_len + 1]; // after prefix+opcode(s)
            int mod = (modrm >> 6) & 3;
            int rm = modrm & 7;
            int len = prefix_len + 2; // prefix + opcode + modrm
            if (rm == 4 && mod != 3) len++; // SIB
            if (mod == 0 && rm == 5) len += 4; // RIP-relative
            else if (mod == 1) len += 1;
            else if (mod == 2) len += 4;
            return len;
        };

        auto get_reg = [&](uint8_t modrm) -> int {
            int reg = (modrm >> 3) & 7;
            if (rex & 0x04) reg += 8; // REX.R
            return reg;
        };

        bool handled = false;

        if (op == 0x8B) {
            // MOV r, r/m (32/64-bit)
            int reg = get_reg(rip[oplen + 1]);
            int insn_len = calc_modrm_len(rip, oplen);
            if (reg < 16) *regs[reg] = 0;
            ctx->Rip += insn_len;
            handled = true;
        }
        else if (op == 0x0F) {
            uint8_t op2 = rip[oplen + 1];
            if (op2 == 0xB6 || op2 == 0xB7) {
                // MOVZX r, r/m8 (B6) or r/m16 (B7)
                int reg = get_reg(rip[oplen + 2]);
                // +1 for the 0x0F prefix byte
                int insn_len = calc_modrm_len(rip, oplen + 1);
                if (reg < 16) *regs[reg] = 0;
                ctx->Rip += insn_len;
                handled = true;
            }
            else if (op2 == 0xBE || op2 == 0xBF) {
                // MOVSX r, r/m8 (BE) or r/m16 (BF)
                int reg = get_reg(rip[oplen + 2]);
                int insn_len = calc_modrm_len(rip, oplen + 1);
                if (reg < 16) *regs[reg] = 0;
                ctx->Rip += insn_len;
                handled = true;
            }
        }
        else if (op == 0x8A) {
            // MOV r8, r/m8
            int reg = get_reg(rip[oplen + 1]);
            int insn_len = calc_modrm_len(rip, oplen);
            if (reg < 16) *regs[reg] = (*regs[reg] & ~0xFFULL); // zero low byte
            ctx->Rip += insn_len;
            handled = true;
        }
        else if (op == 0x63) {
            // MOVSXD r64, r/m32
            int reg = get_reg(rip[oplen + 1]);
            int insn_len = calc_modrm_len(rip, oplen);
            if (reg < 16) *regs[reg] = 0;
            ctx->Rip += insn_len;
            handled = true;
        }

        if (handled) return EXCEPTION_CONTINUE_EXECUTION;

        // Fallback: log unhandled instruction encoding
        static int _unhandled = 0;
        if (++_unhandled <= 20) {
            crash_log_write("[NULLPAGE] Unhandled load at guest 0x%04llX, op=0x%02X%02X, RIP=0x%016llX\n",
                    addr - base, rip[0], rip[1], (unsigned long long)ctx->Rip);
        }
    }
    return EXCEPTION_CONTINUE_SEARCH;
}

static struct NullPageGuard_ {
    NullPageGuard_() {
        AddVectoredExceptionHandler(0, CrashVEH);      // log all exceptions (low priority)
        AddVectoredExceptionHandler(1, NullPageHandler); // handle null page (high priority)
    }
} g_null_page_guard_;
#endif

static void ApplyConsoleVisibility(bool show) {
#ifdef _WIN32
    HWND console = GetConsoleWindow();
    if (console) {
        ShowWindow(console, show ? SW_SHOW : SW_HIDE);
    }
#endif
}

class DebugOverlayDialog : public rex::ui::ImGuiDialog {
public:
    bool visible = true;

    DebugOverlayDialog(rex::ui::ImGuiDrawer* imgui_drawer)
        : ImGuiDialog(imgui_drawer) {}
protected:
    void OnDraw(ImGuiIO& io) override {
        // Always call Begin/End to keep the ImGui frame active — returning
        // early with no ImGui calls causes the drawer to stop requesting
        // redraws, which stalls the entire render pipeline.
        if (!visible) {
            ImGui::SetNextWindowPos(ImVec2(-100, -100));
            ImGui::SetNextWindowSize(ImVec2(1, 1));
            ImGui::SetNextWindowBgAlpha(0.0f);
            ImGui::Begin("Debug##overlay", nullptr,
                         ImGuiWindowFlags_NoDecoration |
                         ImGuiWindowFlags_NoInputs |
                         ImGuiWindowFlags_NoBackground);
            ImGui::End();
            return;
        }
        ImGui::SetNextWindowPos(ImVec2(10, 10), ImGuiCond_FirstUseEver);
        ImGui::SetNextWindowSize(ImVec2(220, 60), ImGuiCond_FirstUseEver);
        ImGui::SetNextWindowBgAlpha(0.5f);
        if (ImGui::Begin("Debug##overlay", nullptr, ImGuiWindowFlags_NoCollapse)) {
            ImGui::Text("%.1f FPS (%.2f ms)", io.Framerate, 1000.0f / io.Framerate);
        }
        ImGui::End();
    }
};

class Vig8App : public rex::ui::WindowedApp,
                public rex::ui::WindowListener,
                public rex::ui::WindowInputListener {
public:
    static std::unique_ptr<rex::ui::WindowedApp> Create(rex::ui::WindowedAppContext& ctx) {
        return std::make_unique<Vig8App>(ctx);
    }

    Vig8App(rex::ui::WindowedAppContext& ctx)
        : WindowedApp(ctx, "vig8", "[game_directory]") {
        AddPositionalOption("game_directory");
    }

    bool OnInitialize() override {
        auto exe_dir = rex::filesystem::GetExecutableFolder();

        // Game directory: arg or default to exe_dir/assets
        std::filesystem::path game_dir;
        if (auto arg = GetArgument("game_directory")) {
            game_dir = *arg;
        } else {
            game_dir = exe_dir / "assets";
        }

        // Load user settings from vig8_settings.toml
        settings_path_ = std::filesystem::absolute(game_dir).parent_path()
                          / "vig8_settings.toml";
        settings_ = LoadSettings(settings_path_);

        // Apply render path from settings (before runtime init)
        rex::cvar::SetFlagByName("render_target_path_d3d12",
                                 settings_.render_path);

        // Apply resolution scale CVars
        REXCVAR_SET(draw_resolution_scale_x, settings_.resolution_scale);
        REXCVAR_SET(draw_resolution_scale_y, settings_.resolution_scale);

        // Apply debug flags
        g_vig8_invulnerable = settings_.invulnerable;
        g_vig8_unlock_all_cars = settings_.unlock_all_cars;

        // Hide console on startup if configured
        ApplyConsoleVisibility(settings_.show_console);

        std::string log_file_cvar = REXCVAR_GET(log_file);
        std::string log_level_str = REXCVAR_GET(log_level);
        if (REXCVAR_GET(log_verbose) && log_level_str == "info") {
            log_level_str = "trace";
        }
        auto log_config = rex::BuildLogConfig(
            log_file_cvar.empty() ? nullptr : log_file_cvar.c_str(),
            log_level_str, {});
        rex::InitLogging(log_config);
        rex::RegisterLogLevelCallback();
        REXLOG_INFO("vig8 starting");
        REXLOG_INFO("  Game directory: {}", game_dir.string());

        // Create and initialize runtime
        runtime_ = std::make_unique<rex::Runtime>(game_dir);
        runtime_->set_app_context(&app_context());

        auto status = runtime_->Setup(
            static_cast<uint32_t>(PPC_CODE_BASE),
            static_cast<uint32_t>(PPC_CODE_SIZE),
            static_cast<uint32_t>(PPC_IMAGE_BASE),
            static_cast<uint32_t>(PPC_IMAGE_SIZE),
            PPCFuncMappings);
        if (XFAILED(status)) {
            REXLOG_ERROR("Runtime setup failed: {:08X}", status);
            return false;
        }

        // Load XEX image
        status = runtime_->LoadXexImage("game:\\default.xex");
        if (XFAILED(status)) {
            REXLOG_ERROR("Failed to load XEX: {:08X}", status);
            return false;
        }

        // Create window
        window_ = rex::ui::Window::Create(app_context(), "Vigilante 8 Arcade", 1280, 720);
        if (!window_) {
            REXLOG_ERROR("Failed to create window");
            return false;
        }

        window_->AddListener(this);
        window_->AddInputListener(this, 0);
        window_->Open();

        // Setup graphics presenter and ImGui
        auto* graphics_system = runtime_->graphics_system();
        if (graphics_system && graphics_system->presenter()) {
            auto* presenter = graphics_system->presenter();
            auto* provider = graphics_system->provider();
            if (provider) {
                immediate_drawer_ = provider->CreateImmediateDrawer();
                if (immediate_drawer_) {
                    immediate_drawer_->SetPresenter(presenter);
                    imgui_drawer_ = std::make_unique<rex::ui::ImGuiDrawer>(window_.get(), 64);
                    imgui_drawer_->SetPresenterAndImmediateDrawer(presenter, immediate_drawer_.get());

                    // Debug FPS overlay (visibility controlled by settings)
                    debug_overlay_ = std::unique_ptr<DebugOverlayDialog>(
                        new DebugOverlayDialog(imgui_drawer_.get()));
                    debug_overlay_->visible = settings_.show_fps;

                    // Menu system with config dialogs
                    menu_system_ = std::make_unique<MenuSystem>(
                        imgui_drawer_.get(), window_.get(), &app_context(),
                        runtime_.get(),
                        &settings_, settings_path_,
                        [this]() { ApplySettings(); });
                    auto menu = menu_system_->BuildMenuBar();
                    window_->SetMainMenu(std::move(menu));
                    window_->CompleteMainMenuItemsUpdate();

                    runtime_->set_display_window(window_.get());
                    runtime_->set_imgui_drawer(imgui_drawer_.get());
                }
            }
            window_->SetPresenter(presenter);
        }

        // Apply fullscreen after presenter is fully wired up
        if (settings_.fullscreen) {
            auto* w = window_.get();
            app_context().CallInUIThreadDeferred([w]() {
                w->SetFullscreen(true);
            });
        }

        // Initialize LAN networking (after runtime so kernel_state is available)
        NetInit(settings_.lan_port);

        // Launch module in background
        app_context().CallInUIThreadDeferred([this]() {
            auto main_thread = runtime_->LaunchModule();
            if (!main_thread) {
                REXLOG_ERROR("Failed to launch module");
                app_context().QuitFromUIThread();
                return;
            }

            module_thread_ = std::thread([this, main_thread = std::move(main_thread)]() mutable {
                try {
                    main_thread->Wait(0, 0, 0, nullptr);
                } catch (const std::exception& e) {
                    fprintf(stderr, "\n========== C++ EXCEPTION ==========\n");
                    fprintf(stderr, "Thread: %lu\n", GetCurrentThreadId());
                    fprintf(stderr, "what(): %s\n", e.what());
                    fprintf(stderr, "====================================\n");
                    fflush(stderr);
                } catch (...) {
                    fprintf(stderr, "\n========== UNKNOWN C++ EXCEPTION ==========\n");
                    fprintf(stderr, "Thread: %lu\n", GetCurrentThreadId());
                    fprintf(stderr, "=============================================\n");
                    fflush(stderr);
                }
                REXLOG_INFO("Execution complete");
                if (!shutting_down_.load(std::memory_order_acquire)) {
                    app_context().CallInUIThread([this]() {
                        app_context().QuitFromUIThread();
                    });
                }
            });
        });

        return true;
    }

    void OnClosing(rex::ui::UIEvent& e) override {
        (void)e;
        REXLOG_INFO("Window closing, shutting down...");
        shutting_down_.store(true, std::memory_order_release);
        if (runtime_ && runtime_->kernel_state()) {
            runtime_->kernel_state()->TerminateTitle();
        }
        app_context().QuitFromUIThread();
    }

    void OnDestroy() override {
        // Menu/dialog cleanup (before drawer)
        menu_system_.reset();
        // ImGui cleanup (reverse of setup)
        debug_overlay_.reset();
        if (imgui_drawer_) {
            imgui_drawer_->SetPresenterAndImmediateDrawer(nullptr, nullptr);
            imgui_drawer_.reset();
        }
        if (immediate_drawer_) {
            immediate_drawer_->SetPresenter(nullptr);
            immediate_drawer_.reset();
        }
        if (runtime_) {
            runtime_->set_display_window(nullptr);
            runtime_->set_imgui_drawer(nullptr);
        }
        // Window/runtime cleanup
        if (window_) {
            window_->SetPresenter(nullptr);
        }
        if (module_thread_.joinable()) {
            module_thread_.join();
        }
        if (window_) {
            window_->RemoveInputListener(this);
            window_->RemoveListener(this);
        }
        // Shut down LAN networking before runtime is destroyed
        NetShutdown();

        window_.reset();
        runtime_.reset();
    }

    // WindowInputListener: F11 toggles fullscreen
    void OnKeyDown(rex::ui::KeyEvent& e) override {
        if (e.virtual_key() == rex::ui::VirtualKey::kF11) {
            settings_.fullscreen = !settings_.fullscreen;
            SaveSettings(settings_path_, settings_);
            // Defer fullscreen change to next UI frame to avoid
            // surface/presenter conflicts during event processing
            bool fs = settings_.fullscreen;
            auto* w = window_.get();
            app_context().CallInUIThreadDeferred([w, fs]() {
                w->SetFullscreen(fs);
            });
            e.set_handled(true);
        }
    }

private:
    // Called when settings are changed via a config dialog
    void ApplySettings() {
        // Debug overlay visibility
        if (debug_overlay_) {
            debug_overlay_->visible = settings_.show_fps;
        }

        // Debug console visibility
        ApplyConsoleVisibility(settings_.show_console);

        // Debug flags
        g_vig8_invulnerable = settings_.invulnerable;
        g_vig8_unlock_all_cars = settings_.unlock_all_cars;

        // Multi-user sign-in state
        g_vig8_user_connected[0] = true;
        g_vig8_user_connected[1] = settings_.connected_2;
        g_vig8_user_connected[2] = settings_.connected_3;
        g_vig8_user_connected[3] = settings_.connected_4;

        // Render path changes require restart (just saved to file)
        REXLOG_INFO("Settings applied (render_path={}, show_fps={}, full_game={}, "
                    "show_console={}, invulnerable={}, unlock_all_cars={})",
                    settings_.render_path,
                    settings_.show_fps ? "true" : "false",
                    settings_.full_game ? "true" : "false",
                    settings_.show_console ? "true" : "false",
                    settings_.invulnerable ? "true" : "false",
                    settings_.unlock_all_cars ? "true" : "false");
    }

    std::unique_ptr<rex::Runtime> runtime_;
    std::unique_ptr<rex::ui::Window> window_;
    std::thread module_thread_;
    std::atomic<bool> shutting_down_{false};
    std::unique_ptr<rex::ui::ImmediateDrawer> immediate_drawer_;
    std::unique_ptr<rex::ui::ImGuiDrawer> imgui_drawer_;
    std::unique_ptr<DebugOverlayDialog> debug_overlay_;
    std::unique_ptr<MenuSystem> menu_system_;
    Vig8Settings settings_;
    std::filesystem::path settings_path_;
};

XE_DEFINE_WINDOWED_APP(vig8, Vig8App::Create)
