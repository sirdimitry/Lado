#include "hook.h"

#include "log.h"

namespace lado {

InputHook* InputHook::active_ = nullptr;

bool InputHook::install(HWND owner, KeyHandler on_key, MouseHandler on_mouse) {
  uninstall();
  on_key_ = std::move(on_key);
  on_mouse_ = std::move(on_mouse);
  active_ = this;

  const HINSTANCE instance = GetModuleHandleW(nullptr);
  keyboard_ = SetWindowsHookExW(WH_KEYBOARD_LL, keyboard_proc, instance, 0);
  mouse_ = SetWindowsHookExW(WH_MOUSE_LL, mouse_proc, instance, 0);
  if (keyboard_ == nullptr || mouse_ == nullptr) {
    log_message(L"hook install failed: keyboard=%d mouse=%d error=%lu",
                keyboard_ != nullptr, mouse_ != nullptr, GetLastError());
    uninstall();
    return false;
  }
  (void)owner;
  return true;
}

void InputHook::uninstall() {
  if (keyboard_ != nullptr) {
    UnhookWindowsHookEx(keyboard_);
    keyboard_ = nullptr;
  }
  if (mouse_ != nullptr) {
    UnhookWindowsHookEx(mouse_);
    mouse_ = nullptr;
  }
  if (active_ == this) active_ = nullptr;
  on_key_ = nullptr;
  on_mouse_ = nullptr;
}

LRESULT CALLBACK InputHook::keyboard_proc(int code, WPARAM wparam, LPARAM lparam) {
  if (code == HC_ACTION && active_ != nullptr && active_->on_key_) {
    const auto* data = reinterpret_cast<const KBDLLHOOKSTRUCT*>(lparam);
    KeyEvent event;
    event.vk = data->vkCode;
    event.scan = data->scanCode;
    event.flags = data->flags;
    event.down = wparam == WM_KEYDOWN || wparam == WM_SYSKEYDOWN;
    event.injected = (data->flags & LLKHF_INJECTED) != 0;
    event.extra_info = static_cast<uintptr_t>(data->dwExtraInfo);
    event.tick = data->time;
    if (active_->on_key_(event)) return 1;
  }
  return CallNextHookEx(nullptr, code, wparam, lparam);
}

LRESULT CALLBACK InputHook::mouse_proc(int code, WPARAM wparam, LPARAM lparam) {
  if (code == HC_ACTION) {
    switch (wparam) {
      case WM_LBUTTONDOWN:
      case WM_RBUTTONDOWN:
      case WM_MBUTTONDOWN:
      case WM_XBUTTONDOWN:
        if (active_ != nullptr && active_->on_mouse_) active_->on_mouse_();
        break;
      default:
        break;
    }
  }
  return CallNextHookEx(nullptr, code, wparam, lparam);
}

}  // namespace lado
