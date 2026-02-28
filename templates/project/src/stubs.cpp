// Missing kernel stubs for Vigilante 8 Arcade
// These are Xbox 360 APIs not yet implemented in the ReXGlue SDK.
// Most are non-essential: networking, USB camera, and UI dialogs.

#include "vig8_config.h"
#include "settings.h"
#include <rex/runtime/guest/context.h>
#include <rex/runtime/guest/memory.h>
#include <rex/kernel/kernel_state.h>
#include <cstring>

using namespace rex::runtime::guest;

// Global debug flags (set from ApplySettings in main.cpp)
bool g_vig8_invulnerable = false;
bool g_vig8_unlock_all_cars = false;

// Per-slot sign-in state: player 1 always connected, others opt-in
bool g_vig8_user_connected[4] = {true, false, false, false};

// Simple stub macro that returns a value
#define VIG8_STUB_RETURN(name, val) \
    extern "C" PPC_FUNC(name) { (void)base; ctx.r3.u64 = (val); }

#define VIG8_STUB(name) VIG8_STUB_RETURN(name, 0)

// Networking overrides moved to net.cpp:
//   XNetUnregisterInAddr, XNetConnect, XNetGetConnectStatus,
//   XNetQosLookup, WSAGetOverlappedResult, and others.

// XAM UI stubs
VIG8_STUB(__imp__XamShowGamerCardUIForXUID)
VIG8_STUB(__imp__XamShowAchievementsUI)
VIG8_STUB(__imp__XamShowMarketplaceUI)
VIG8_STUB_RETURN(__imp__XamUserCreateStatsEnumerator, 1)  // fail = no stats
VIG8_STUB(__imp__XamVoiceSubmitPacket)

// Content license — override the weak wrapper sub_823245B0 to return full
// license mask, bypassing the SDK's XamContentGetLicenseMask (which returns
// no-license). The generated code declares sub_823245B0 as PPC_WEAK_FUNC,
// so our strong definition takes precedence.
// Calling convention: r3 = output pointer for mask, r4 = overlapped (ignored)
// Returns 0 (success) in r3.
extern "C" PPC_FUNC(sub_823245B0) {
    uint32_t mask_ptr = ctx.r3.u32;
    if (mask_ptr)
        PPC_STORE_U32(mask_ptr, 0xFFFFFFFF);  // full license
    ctx.r3.u32 = 0;  // ERROR_SUCCESS
}

// Kernel memory allocation
VIG8_STUB(__imp__ExAllocatePoolWithTag)  // NULL = allocation failed

// USB Camera stubs (XUsbcam*)
VIG8_STUB_RETURN(__imp__XUsbcamCreate, 1)  // fail
VIG8_STUB(__imp__XUsbcamDestroy)
VIG8_STUB(__imp__XUsbcamGetState)
VIG8_STUB_RETURN(__imp__XUsbcamSetConfig, 1)
VIG8_STUB_RETURN(__imp__XUsbcamSetView, 1)
VIG8_STUB_RETURN(__imp__XUsbcamSetCaptureMode, 1)
VIG8_STUB_RETURN(__imp__XUsbcamReadFrame, 1)

// ObReferenceObject - reference counting stub
VIG8_STUB(__imp__ObReferenceObject)

// ============================================================================
// Multi-user sign-in overrides (local multiplayer support)
// ============================================================================
// The SDK only signs in user index 0. For local multiplayer the game needs all
// 4 user indices to report as signed-in so controllers appear in the player
// selection menu. We override the GUEST_FUNCTION_HOOK symbols — since our
// object files link before rexkernel.lib, these definitions take precedence.

// Unique XUIDs for each local player (arbitrary but distinct)
static const uint64_t kUserXuids[4] = {
    0xB13EBABEBABE0001ULL,
    0xB13EBABEBABE0002ULL,
    0xB13EBABEBABE0003ULL,
    0xB13EBABEBABE0004ULL,
};

static const char* kUserNames[4] = {
    "Player 1", "Player 2", "Player 3", "Player 4"
};

// XamUserGetSigninState(user_index) -> signin_state
// Return 1 (signed in locally) for connected user indices only.
extern "C" PPC_FUNC(__imp__XamUserGetSigninState) {
    uint32_t user_index = ctx.r3.u32;
    ctx.r3.u64 = (user_index < 4 && g_vig8_user_connected[user_index]) ? 1 : 0;
}

// XamUserGetSigninInfo(user_index, flags, info_ptr) -> HRESULT
// X_USER_SIGNIN_INFO layout (40 bytes, big-endian):
//   +0  uint64_t xuid
//   +8  uint32_t unk08
//   +12 uint32_t signin_state
//   +16 uint32_t unk10
//   +20 uint32_t unk14
//   +24 char     name[16]
extern "C" PPC_FUNC(__imp__XamUserGetSigninInfo) {
    uint32_t user_index = ctx.r3.u32;
    // r4 = flags (unused)
    uint32_t info_ptr = ctx.r5.u32;

    if (!info_ptr) {
        ctx.r3.u64 = 0x80070057;  // X_E_INVALIDARG
        return;
    }

    // Zero the struct
    std::memset(base + info_ptr, 0, 40);

    if (user_index >= 4 || !g_vig8_user_connected[user_index]) {
        ctx.r3.u64 = 0x80070490;  // X_E_NO_SUCH_USER
        return;
    }

    PPC_STORE_U64(info_ptr + 0, kUserXuids[user_index]);
    PPC_STORE_U32(info_ptr + 12, 1);  // signin_state = signed in locally
    // Copy name (raw bytes, not endian-swapped)
    const char* name = kUserNames[user_index];
    std::memcpy(base + info_ptr + 24, name, std::strlen(name) + 1);

    ctx.r3.u64 = 0;  // X_E_SUCCESS
}

// XamUserGetXUID(user_index, type_mask, xuid_ptr) -> HRESULT
extern "C" PPC_FUNC(__imp__XamUserGetXUID) {
    uint32_t user_index = ctx.r3.u32;
    // r4 = type_mask (unused — we always return the xuid)
    uint32_t xuid_ptr = ctx.r5.u32;

    if (!xuid_ptr) {
        ctx.r3.u64 = 0x80070057;  // X_E_INVALIDARG
        return;
    }

    if (user_index >= 4 || !g_vig8_user_connected[user_index]) {
        PPC_STORE_U64(xuid_ptr, 0);
        ctx.r3.u64 = (user_index >= 4) ? 0x80070057 : 0x80070490;
        return;
    }

    PPC_STORE_U64(xuid_ptr, kUserXuids[user_index]);
    ctx.r3.u64 = 0;  // X_E_SUCCESS
}

// XamUserGetName(user_index, buffer, buffer_len) -> result
extern "C" PPC_FUNC(__imp__XamUserGetName) {
    uint32_t user_index = ctx.r3.u32;
    uint32_t buffer_ptr = ctx.r4.u32;
    uint32_t buffer_len = ctx.r5.u32;

    if (user_index >= 4 || !g_vig8_user_connected[user_index]) {
        ctx.r3.u64 = (user_index >= 4) ? 0x80070057 : 0x80070490;
        return;
    }

    const char* name = kUserNames[user_index];
    uint32_t copy_len = std::min(buffer_len, (uint32_t)(std::strlen(name) + 1));
    if (buffer_ptr && copy_len > 0) {
        std::memcpy(base + buffer_ptr, name, copy_len);
        // Ensure null termination
        *(base + buffer_ptr + copy_len - 1) = 0;
    }

    ctx.r3.u64 = 0;  // X_E_SUCCESS
}

// XamUserCheckPrivilege(user_index, mask, out_value) -> result
extern "C" PPC_FUNC(__imp__XamUserCheckPrivilege) {
    uint32_t user_index = ctx.r3.u32;
    // r4 = mask (unused)
    uint32_t out_ptr = ctx.r5.u32;

    if (user_index != 0xFF && user_index >= 4) {
        ctx.r3.u64 = 0x80070057;  // X_E_INVALIDARG
        return;
    }

    // Grant all privileges
    if (out_ptr) PPC_STORE_U32(out_ptr, 0);
    ctx.r3.u64 = 0;  // X_ERROR_SUCCESS
}

// XamUserGetMembershipTier(user_index) -> tier
extern "C" PPC_FUNC(__imp__XamUserGetMembershipTier) {
    uint32_t user_index = ctx.r3.u32;
    if (user_index >= 4) {
        ctx.r3.u64 = 0x80070057;
        return;
    }
    ctx.r3.u64 = 6;  // Gold
}

// XamShowSigninUI(unk, unk_mask) -> result
// Broadcast sign-in changed with connected users bitmask.
extern "C" PPC_FUNC(__imp__XamShowSigninUI) {
    (void)base;
    auto* ks = rex::kernel::kernel_state();
    if (ks) {
        uint32_t mask = 0;
        for (int i = 0; i < 4; i++)
            if (g_vig8_user_connected[i]) mask |= (1u << i);
        // XN_SYS_SIGNINCHANGED
        ks->BroadcastNotification(0x0000000A, mask);
        // XN_SYS_UI off
        ks->BroadcastNotification(0x00000009, 0);
    }
    ctx.r3.u64 = 0;  // X_ERROR_SUCCESS
}

// XamUserIsOnlineEnabled(user_index) -> bool
extern "C" PPC_FUNC(__imp__XamUserIsOnlineEnabled) {
    (void)base;
    ctx.r3.u64 = 1;
}

// ============================================================================
// Vehicle unlock override
// ============================================================================
// sub_821B80F0 reads vehicle data structures. At offset 196, bits 12-15
// (mask 0xF0000) indicate the vehicle is unlocked. If those bits are 0,
// the vehicle is locked (skipped). We override the weak symbol to force
// those bits set before calling the original implementation.

// Forward-declare the generated implementation
extern "C" void __imp__sub_821B80F0(PPCContext& ctx, uint8_t* base);

extern "C" PPC_FUNC(sub_821B80F0) {
    if (g_vig8_unlock_all_cars) {
        uint32_t struct_ptr = ctx.r3.u32;
        if (struct_ptr) {
            uint32_t val = PPC_LOAD_U32(struct_ptr + 196);
            val |= 0xF0000;  // force bits 12-15 set = unlocked
            PPC_STORE_U32(struct_ptr + 196, val);
        }
    }
    // Call original implementation
    __imp__sub_821B80F0(ctx, base);
}
