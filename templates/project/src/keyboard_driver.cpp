// simpsons - Keyboard-to-gamepad input driver implementation

#include "keyboard_driver.h"

#include <rex/input/input.h>
#include <rex/ui/virtual_key.h>
#include <rex/ui/window.h>

#include <cstring>

using namespace rex::ui;
using namespace rex::input;

KeyboardInputDriver::KeyboardInputDriver(rex::ui::Window* window)
    : InputDriver(window, 0) {
    if (window) {
        window->AddInputListener(this, 0);
    }
}

KeyboardInputDriver::~KeyboardInputDriver() {
    if (window()) {
        window()->RemoveInputListener(this);
    }
}

X_STATUS KeyboardInputDriver::Setup() {
    return X_STATUS_SUCCESS;
}

uint16_t KeyboardInputDriver::MapKeyToButton(VirtualKey key) {
    switch (key) {
        case VirtualKey::kW:     case VirtualKey::kUp:    return X_INPUT_GAMEPAD_DPAD_UP;
        case VirtualKey::kS:     case VirtualKey::kDown:  return X_INPUT_GAMEPAD_DPAD_DOWN;
        case VirtualKey::kA:     case VirtualKey::kLeft:  return X_INPUT_GAMEPAD_DPAD_LEFT;
        case VirtualKey::kD:     case VirtualKey::kRight: return X_INPUT_GAMEPAD_DPAD_RIGHT;
        case VirtualKey::kZ:     case VirtualKey::kJ:     return X_INPUT_GAMEPAD_A;
        case VirtualKey::kX:     case VirtualKey::kK:     return X_INPUT_GAMEPAD_B;
        case VirtualKey::kC:     case VirtualKey::kL:     return X_INPUT_GAMEPAD_X;
        case VirtualKey::kV:                              return X_INPUT_GAMEPAD_Y;
        case VirtualKey::kReturn:                         return X_INPUT_GAMEPAD_START;
        case VirtualKey::kBack:  case VirtualKey::kEscape: return X_INPUT_GAMEPAD_BACK;
        case VirtualKey::kQ:                              return X_INPUT_GAMEPAD_LEFT_SHOULDER;
        case VirtualKey::kE:                              return X_INPUT_GAMEPAD_RIGHT_SHOULDER;
        default:                                          return 0;
    }
}

void KeyboardInputDriver::OnKeyDown(KeyEvent& e) {
    uint16_t button = MapKeyToButton(e.virtual_key());
    if (button) {
        buttons_.fetch_or(button, std::memory_order_relaxed);
        return;
    }
    if (e.virtual_key() == VirtualKey::k1)
        left_trigger_.store(255, std::memory_order_relaxed);
    else if (e.virtual_key() == VirtualKey::k3)
        right_trigger_.store(255, std::memory_order_relaxed);
}

void KeyboardInputDriver::OnKeyUp(KeyEvent& e) {
    uint16_t button = MapKeyToButton(e.virtual_key());
    if (button) {
        buttons_.fetch_and(~button, std::memory_order_relaxed);
        return;
    }
    if (e.virtual_key() == VirtualKey::k1)
        left_trigger_.store(0, std::memory_order_relaxed);
    else if (e.virtual_key() == VirtualKey::k3)
        right_trigger_.store(0, std::memory_order_relaxed);
}

X_RESULT KeyboardInputDriver::GetCapabilities(uint32_t user_index,
                                               uint32_t flags,
                                               X_INPUT_CAPABILITIES* out_caps) {
    // Keyboard always claims user 0 as a connected gamepad
    if (user_index != 0) return X_ERROR_DEVICE_NOT_CONNECTED;
    if (out_caps) {
        std::memset(out_caps, 0, sizeof(*out_caps));
        out_caps->type = 0x01;       // XINPUT_DEVTYPE_GAMEPAD
        out_caps->sub_type = 0x01;   // XINPUT_DEVSUBTYPE_GAMEPAD
        out_caps->gamepad.buttons = 0xFFFF;
        out_caps->gamepad.left_trigger = 0xFF;
        out_caps->gamepad.right_trigger = 0xFF;
        out_caps->gamepad.thumb_lx = static_cast<int16_t>(0x7FFF);
        out_caps->gamepad.thumb_ly = static_cast<int16_t>(0x7FFF);
        out_caps->gamepad.thumb_rx = static_cast<int16_t>(0x7FFF);
        out_caps->gamepad.thumb_ry = static_cast<int16_t>(0x7FFF);
    }
    return X_ERROR_SUCCESS;
}

X_RESULT KeyboardInputDriver::GetState(uint32_t user_index,
                                        X_INPUT_STATE* out_state) {
    // Keyboard always claims user 0
    if (user_index != 0) return X_ERROR_DEVICE_NOT_CONNECTED;
    if (out_state) {
        uint16_t current = buttons_.load(std::memory_order_relaxed);
        if (current != prev_buttons_) {
            packet_number_++;
            prev_buttons_ = current;
        }
        out_state->packet_number = packet_number_;
        out_state->gamepad.buttons = current;
        out_state->gamepad.left_trigger = left_trigger_.load(std::memory_order_relaxed);
        out_state->gamepad.right_trigger = right_trigger_.load(std::memory_order_relaxed);
        out_state->gamepad.thumb_lx = 0;
        out_state->gamepad.thumb_ly = 0;
        out_state->gamepad.thumb_rx = 0;
        out_state->gamepad.thumb_ry = 0;
    }
    return X_ERROR_SUCCESS;
}

X_RESULT KeyboardInputDriver::SetState(uint32_t user_index,
                                        X_INPUT_VIBRATION* vibration) {
    if (user_index != 0) return X_ERROR_DEVICE_NOT_CONNECTED;
    return X_ERROR_SUCCESS;
}

X_RESULT KeyboardInputDriver::GetKeystroke(uint32_t user_index, uint32_t flags,
                                            X_INPUT_KEYSTROKE* out_keystroke) {
    if (user_index != 0) return X_ERROR_DEVICE_NOT_CONNECTED;
    return X_ERROR_EMPTY;
}
