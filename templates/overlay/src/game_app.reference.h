// game_app.reference.h -- annotated reference for the ReXApp subclass.
//
// `rexglue init` already generates a minimal <name>_app.h. This file shows the
// virtual hooks you can override there, what each is for, and which of the old
// (XenonRecomp-era) "battle-tested fixes" each one replaces. Copy the hooks you
// need into your generated <name>_app.h -- don't add this file to the build.
//
// In v0.8.0 the SDK's rex::ReXApp ALREADY provides, with no code from you:
//   - window + D3D12 (or Vulkan) presentation and the frame loop
//   - the ImGui debug overlay, console, and settings dialogs
//   - SDL3 input (keyboard/mouse + gamepad merged)   [replaces keyboard_driver.cpp]
//   - crash/VEH handling                              [replaces the VEH handlers]
//   - guest function dispatch                         [replaces PPC_CALL_INDIRECT_FUNC]
//   - frame pacing + guest timebase                   [replaces the VdSwap/__rdtsc fixes]
//   - path/config/logging setup
// So most projects override only a couple of hooks (or none) plus a stubs.cpp.

#pragma once

#include <rex/rex_app.h>

class MygameApp : public rex::ReXApp {
 public:
  using rex::ReXApp::ReXApp;

  static std::unique_ptr<rex::ui::WindowedApp> Create(rex::ui::WindowedAppContext& ctx) {
    return std::unique_ptr<MygameApp>(new MygameApp(ctx, "mygame", PPCImageConfig));
  }

  // --- Hooks (override only what you need) ---

  // Adjust backend/runtime config before the runtime starts. This is where the
  // old GPU CVar workarounds live (e.g. the ctxbla "allow invalid fetch
  // constants" toggle, or forcing the ROV render path for k_2_10_10_10_FLOAT +
  // MSAA white-screen titles). Inspect RuntimeConfig in <rex/runtime.h> for the
  // fields/CVars available in your SDK build.
  // void OnPreSetup(rex::RuntimeConfig& config) override { /* config.xxx = ...; */ }

  // Point the runtime at your extracted game assets / redirect data roots.
  // (Equivalent to passing --game_data_root on the command line.)
  void OnConfigurePaths(rex::PathConfig& paths) override {
    // paths.game_data_root = "...";   // defaults come from CLI args + cvars
    (void)paths;
  }

  // Patch the loaded XEX image before the guest module launches. The image is
  // mapped into guest memory here; OnPreLaunchModule is the last chance before
  // the main guest thread is created. Use for loose-file / ARK-bypass style
  // data patches.
  // void OnPostLoadXexImage() override {}
  // void OnPreLaunchModule() override {}

  // Add your own ImGui dialogs alongside the built-in overlay/console/settings.
  // void OnCreateDialogs(rex::ui::ImGuiDrawer* drawer) override { (void)drawer; }

  // Release any custom resources.
  // void OnShutdown() override {}
};
