// Low-level keyboard and mouse hooks. The callbacks are invoked on the thread
// that installed the hook (the UI thread) and must return immediately; all
// buffering and decisions live above this layer.
#pragma once

#include <windows.h>

#include <cstdint>
#include <functional>

namespace lado {

struct KeyEvent {
  UINT vk = 0;
  UINT scan = 0;
  DWORD flags = 0;
  bool down = false;
  bool injected = false;
  uintptr_t extra_info = 0;
  ULONGLONG tick = 0;
};

// Returns true to swallow the key.
using KeyHandler = std::function<bool(const KeyEvent&)>;
using MouseHandler = std::function<void()>;

class InputHook {
 public:
  bool install(HWND owner, KeyHandler on_key, MouseHandler on_mouse);
  void uninstall();
  bool installed() const { return keyboard_ != nullptr && mouse_ != nullptr; }

 private:
  static LRESULT CALLBACK keyboard_proc(int code, WPARAM wparam, LPARAM lparam);
  static LRESULT CALLBACK mouse_proc(int code, WPARAM wparam, LPARAM lparam);

  static InputHook* active_;

  HHOOK keyboard_ = nullptr;
  HHOOK mouse_ = nullptr;
  KeyHandler on_key_;
  MouseHandler on_mouse_;
};

}  // namespace lado
