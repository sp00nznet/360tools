// overrides.example.cpp -- overriding kernel functions the SDK ALREADY implements.
//
// Worked example: force all four user slots to report signed-in locally, so
// local-multiplayer titles show every controller in player-select. The SDK only
// signs in user 0; we replace the relevant XAM user functions.
//
// This differs from stubs.cpp (which defines MISSING symbols). Here the symbol
// is already exported from rexruntime.dll, so to make our definition win you
// MUST add /force:multiple to the link (project objects link before the runtime
// import lib, so the first -- ours -- is chosen). In your generated CMakeLists.txt:
//
//     target_sources(mygame PRIVATE src/overrides.example.cpp)
//     if(WIN32)
//       target_link_options(mygame PRIVATE "LINKER:/force:multiple")
//     endif()
//
// We use REX_HOOK (defines + auto-marshals) rather than REX_EXPORT, because the
// SDK already registered these names -- we only need to win the symbol, not
// re-register. The typed _entry signatures and helpers below mirror the SDK's
// own src/kernel/xam/xam_user.cpp exactly.

#include <cstring>

#include <rex/hook.h>
#include <rex/types.h>
#include <rex/string/util.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xtypes.h>

// The SDK's X_* result codes, mapped_*/ppc_ptr_t guest-pointer types, be<>,
// countof, etc. live in namespace rex (the SDK's own kernel .cpp files are
// written inside it). Pull it in so the entry signatures below resolve.
using namespace rex;

namespace {

// Which local players are "connected". Player 1 always; wire the rest to your
// settings / controller-hotplug logic.
bool g_connected[4] = {true, false, false, false};

constexpr uint64_t kUserXuid[4] = {
    0xB13EBABEBABE0001ULL, 0xB13EBABEBABE0002ULL,
    0xB13EBABEBABE0003ULL, 0xB13EBABEBABE0004ULL,
};
constexpr const char* kUserName[4] = {"Player 1", "Player 2", "Player 3", "Player 4"};

struct X_USER_SIGNIN_INFO {
  rex::be<uint64_t> xuid;
  rex::be<uint32_t> unk08;
  rex::be<uint32_t> signin_state;
  rex::be<uint32_t> unk10;
  rex::be<uint32_t> unk14;
  char name[16];
};

// 1 = signed in locally (no Live); 0 = not signed in.
u32 XamUserGetSigninState_entry(u32 user_index) {
  return (user_index < 4 && g_connected[user_index]) ? 1u : 0u;
}

i32 XamUserGetXUID_entry(u32 user_index, u32 /*type_mask*/, mapped_u64 xuid_ptr) {
  if (!xuid_ptr) return X_E_INVALIDARG;
  if (user_index >= 4 || !g_connected[user_index]) {
    *xuid_ptr = 0;
    return X_E_NO_SUCH_USER;
  }
  *xuid_ptr = kUserXuid[user_index];
  return X_E_SUCCESS;
}

i32 XamUserGetSigninInfo_entry(u32 user_index, u32 /*flags*/, ppc_ptr_t<X_USER_SIGNIN_INFO> info) {
  if (!info) return X_E_INVALIDARG;
  std::memset(info, 0, sizeof(X_USER_SIGNIN_INFO));
  if (user_index >= 4 || !g_connected[user_index]) return X_E_NO_SUCH_USER;
  info->xuid = kUserXuid[user_index];
  info->signin_state = 1;
  rex::string::util_copy_truncating(info->name, kUserName[user_index], rex::countof(info->name));
  return X_E_SUCCESS;
}

u32 XamUserGetName_entry(u32 user_index, mapped_string buffer, u32 buffer_len) {
  if (user_index >= 4) return X_E_INVALIDARG;
  if (!g_connected[user_index]) return X_E_NO_SUCH_USER;
  rex::string::util_copy_truncating(buffer, kUserName[user_index],
                                    std::min(buffer_len, uint32_t(16)));
  return X_E_SUCCESS;
}

// Tell the title sign-in state changed for the connected slots.
u32 XamShowSigninUI_entry(u32 /*pane_count*/, u32 /*flags*/) {
  uint32_t mask = 0;
  for (int i = 0; i < 4; ++i)
    if (g_connected[i]) mask |= (1u << i);
  if (auto* ks = rex::runtime::current_kernel_state()) {
    ks->BroadcastNotification(0x0000000A, mask);  // XN_SYS_SIGNINCHANGED
    ks->BroadcastNotification(0x00000009, 0);      // XN_SYS_UI (off)
  }
  return X_E_SUCCESS;
}

}  // namespace

REX_HOOK(__imp__XamUserGetSigninState, XamUserGetSigninState_entry)
REX_HOOK(__imp__XamUserGetXUID, XamUserGetXUID_entry)
REX_HOOK(__imp__XamUserGetSigninInfo, XamUserGetSigninInfo_entry)
REX_HOOK(__imp__XamUserGetName, XamUserGetName_entry)
REX_HOOK(__imp__XamShowSigninUI, XamShowSigninUI_entry)

// ---------------------------------------------------------------------------
// Overriding a GENERATED guest function (game-logic patch / license bypass).
//
// `rexglue codegen` emits guest functions as weak (DEFINE_REX_FUNC ->
// REX_WEAK_FUNC), so a strong project definition of the same sub_ wins with NO
// link flags. Call the original through its __imp__ symbol. Example (fill in a
// real address from your generated code):
//
//   #include "generated/default/mygame_init.h"   // for REX_FUNC + the decl
//   extern "C" REX_FUNC(__imp__sub_823245B0);     // the original
//   extern "C" REX_FUNC(sub_823245B0) {           // our strong override
//     // e.g. force a full content-license mask the game reads back:
//     if (uint32_t out = ctx.r3.u32) REX_STORE_U32(out, 0xFFFFFFFF);
//     ctx.r3.u32 = 0;                             // ERROR_SUCCESS
//     // or call the original first/after:  __imp__sub_823245B0(ctx, base);
//   }
// ---------------------------------------------------------------------------
