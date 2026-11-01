#include "secure.h"

#include <UIAutomation.h>

#include <chrono>
#include <iterator>
#include <string>

#include "log.h"

namespace lado {
namespace {

constexpr DWORD kPollMilliseconds = 300;
constexpr ULONGLONG kStuckMilliseconds = 2000;

// Declared locally so the binary does not depend on which GUID import library
// the active toolchain ships (MSVC uuid.lib vs MinGW libuuid).
constexpr GUID kClsidCUIAutomation = {
    0xff48dba4, 0x60ef, 0x4201,
    {0xaa, 0x87, 0x54, 0x10, 0x3e, 0xef, 0x59, 0x4e}};
constexpr GUID kIidIUIAutomation = {
    0x30cbe57d, 0xd9d0, 0x452a,
    {0xab, 0x13, 0x7a, 0xc5, 0xac, 0x48, 0x25, 0xee}};

// Cheap native check first: a focused classic Edit with ES_PASSWORD.
bool classic_password_focus(HWND foreground) {
  const DWORD thread = GetWindowThreadProcessId(foreground, nullptr);
  if (thread == 0) return false;
  GUITHREADINFO info = {};
  info.cbSize = sizeof(info);
  if (!GetGUIThreadInfo(thread, &info) || info.hwndFocus == nullptr) return false;

  wchar_t class_name[64] = {};
  if (GetClassNameW(info.hwndFocus, class_name, static_cast<int>(std::size(class_name))) == 0) {
    return false;
  }
  if (_wcsicmp(class_name, L"Edit") != 0) return false;
  const LONG style = GetWindowLongW(info.hwndFocus, GWL_STYLE);
  return (style & ES_PASSWORD) != 0;
}

bool uia_password_focus(IUIAutomation* automation) {
  if (automation == nullptr) return false;
  IUIAutomationElement* element = nullptr;
  if (FAILED(automation->GetFocusedElement(&element)) || element == nullptr) {
    return false;
  }
  bool secure = false;
  VARIANT value;
  VariantInit(&value);
  if (SUCCEEDED(element->GetCurrentPropertyValue(UIA_IsPasswordPropertyId, &value))) {
    secure = value.vt == VT_BOOL && value.boolVal == VARIANT_TRUE;
  }
  VariantClear(&value);
  element->Release();
  return secure;
}

}  // namespace

void SecureWatcher::start() {
  {
    std::lock_guard<std::mutex> guard(mutex_);
    if (started_) return;
    started_ = true;
    stop_ = false;
  }
  thread_ = std::thread([this] { worker(); });
}

bool SecureWatcher::stop() {
  {
    std::lock_guard<std::mutex> guard(mutex_);
    stop_ = true;
  }
  cv_.notify_all();
  if (!thread_.joinable()) return true;

  if (WaitForSingleObject(reinterpret_cast<HANDLE>(thread_.native_handle()),
                          3000) == WAIT_OBJECT_0) {
    thread_.join();
    return true;
  }
  // A UIA call is still blocked inside another application. Detach and let the
  // process exit reclaim it; the owner must not delete this object then.
  thread_.detach();
  return false;
}

void SecureWatcher::refresh_soon() {
  {
    std::lock_guard<std::mutex> guard(mutex_);
    refresh_ = true;
  }
  cv_.notify_all();
}

SecureState SecureWatcher::effective_state() const {
  const ULONGLONG busy = busy_since_.load(std::memory_order_relaxed);
  if (busy != 0 && GetTickCount64() - busy > kStuckMilliseconds) {
    return SecureState::Unknown;
  }
  return state_.load(std::memory_order_relaxed);
}

void SecureWatcher::worker() {
  const HRESULT com = CoInitializeEx(nullptr, COINIT_MULTITHREADED);

  IUIAutomation* automation = nullptr;
  const HRESULT created =
      CoCreateInstance(kClsidCUIAutomation, nullptr, CLSCTX_INPROC_SERVER,
                       kIidIUIAutomation, reinterpret_cast<void**>(&automation));
  if (FAILED(created) || automation == nullptr) {
    log_message(L"UIA unavailable (hr=0x%08lx); classic password check only",
                static_cast<unsigned long>(created));
    automation = nullptr;
  }

  while (true) {
    {
      std::unique_lock<std::mutex> lock(mutex_);
      cv_.wait_for(lock, std::chrono::milliseconds(kPollMilliseconds),
                   [this] { return stop_ || refresh_; });
      if (stop_) break;
      refresh_ = false;
    }

    const HWND foreground = GetForegroundWindow();
    if (foreground == nullptr) {
      state_.store(SecureState::Clear, std::memory_order_relaxed);
      continue;
    }

    if (classic_password_focus(foreground)) {
      state_.store(SecureState::Secure, std::memory_order_relaxed);
      continue;
    }

    if (automation == nullptr) {
      state_.store(SecureState::Clear, std::memory_order_relaxed);
      continue;
    }

    busy_since_.store(GetTickCount64(), std::memory_order_relaxed);
    const SecureState result =
        uia_password_focus(automation) ? SecureState::Secure : SecureState::Clear;
    busy_since_.store(0, std::memory_order_relaxed);
    state_.store(result, std::memory_order_relaxed);
  }

  if (automation != nullptr) automation->Release();
  if (SUCCEEDED(com)) CoUninitialize();
}

}  // namespace lado
