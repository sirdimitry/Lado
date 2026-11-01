#include "secure.h"

// WIN32_LEAN_AND_MEAN keeps OLE out of <windows.h>, but the SDK's UI Automation
// headers require COM/OLE declarations (interface, IUnknown, VARIANT).
#include <ole2.h>
#include <oleauto.h>
#include <UIAutomation.h>

#include <chrono>
#include <iterator>
#include <string>
#include <utility>

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
constexpr GUID kIidTextPattern = {
    0x32eba289, 0x3583, 0x42c9,
    {0x9c, 0x59, 0x3b, 0x6d, 0x9a, 0x1e, 0x9b, 0x6a}};

constexpr size_t kSelectionMaxChars = 500;

// Cheap native check first: a focused classic Edit with ES_PASSWORD.
bool classic_password_focus(HWND foreground) {
  const DWORD thread = GetWindowThreadProcessId(foreground, nullptr);
  if (thread == 0) return false;
  GUITHREADINFO info = {};
  info.cbSize = sizeof(info);
  if (!GetGUIThreadInfo(thread, &info) || info.hwndFocus == nullptr) return false;

  wchar_t class_name[64] = {};
  if (GetClassNameW(info.hwndFocus, class_name,
                    static_cast<int>(std::size(class_name))) == 0) {
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

SelectionResult query_selection(IUIAutomation* automation) {
  SelectionResult result;
  if (automation == nullptr) return result;

  const HWND foreground = GetForegroundWindow();
  if (foreground == nullptr) return result;
  // Never read from a password field, including the classic path.
  if (classic_password_focus(foreground)) return result;

  DWORD foreground_pid = 0;
  GetWindowThreadProcessId(foreground, &foreground_pid);

  IUIAutomationElement* element = nullptr;
  if (FAILED(automation->GetFocusedElement(&element)) || element == nullptr) {
    return result;
  }

  int pid = 0;
  element->get_CurrentProcessId(&pid);
  if (pid != static_cast<int>(foreground_pid)) {
    element->Release();
    return result;
  }

  VARIANT value;
  VariantInit(&value);
  bool password = false;
  if (SUCCEEDED(element->GetCurrentPropertyValue(UIA_IsPasswordPropertyId, &value))) {
    password = value.vt == VT_BOOL && value.boolVal == VARIANT_TRUE;
  }
  VariantClear(&value);
  if (password) {
    element->Release();
    return result;
  }

  IUIAutomationTextPattern* pattern = nullptr;
  if (FAILED(element->GetCurrentPatternAs(
          UIA_TextPatternId, kIidTextPattern,
          reinterpret_cast<void**>(&pattern))) ||
      pattern == nullptr) {
    element->Release();
    return result;
  }
  element->Release();

  IUIAutomationTextRangeArray* ranges = nullptr;
  if (FAILED(pattern->GetSelection(&ranges)) || ranges == nullptr) {
    pattern->Release();
    return result;
  }
  pattern->Release();

  int count = 0;
  ranges->get_Length(&count);
  if (count > 1) {
    result.status = SelectionStatus::Refused;
  } else if (count == 1) {
    IUIAutomationTextRange* range = nullptr;
    if (SUCCEEDED(ranges->GetElement(0, &range)) && range != nullptr) {
      BSTR text = nullptr;
      if (SUCCEEDED(range->GetText(static_cast<int>(kSelectionMaxChars + 100),
                                   &text)) &&
          text != nullptr) {
        std::wstring value(text, SysStringLen(text));
        SysFreeString(text);
        if (!value.empty()) {
          if (value.size() > kSelectionMaxChars ||
              value.find_first_of(L"\r\n") != std::wstring::npos) {
            result.status = SelectionStatus::Refused;
          } else {
            result.status = SelectionStatus::Text;
            result.text = std::move(value);
          }
        }
      }
      range->Release();
    }
  }
  ranges->Release();
  return result;
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

void SecureWatcher::request_selection() {
  {
    std::lock_guard<std::mutex> guard(mutex_);
    if (!started_ || stop_) return;
    selection_requested_ = true;
    selection_consumed_ = false;
    ++selection_request_id_;
  }
  cv_.notify_all();
}

bool SecureWatcher::take_selection(SelectionResult* result) {
  if (result == nullptr) return false;
  std::lock_guard<std::mutex> guard(mutex_);
  if (selection_consumed_ || selection_done_id_ < selection_request_id_) {
    return false;
  }
  *result = selection_result_;
  selection_consumed_ = true;
  return true;
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
    bool do_selection = false;
    uint64_t selection_id = 0;
    {
      std::unique_lock<std::mutex> lock(mutex_);
      cv_.wait_for(lock, std::chrono::milliseconds(kPollMilliseconds),
                   [this] {
                     return stop_ || refresh_ || selection_requested_;
                   });
      if (stop_) break;
      refresh_ = false;
      if (selection_requested_) {
        selection_requested_ = false;
        do_selection = true;
        selection_id = selection_request_id_;
      }
    }

    if (do_selection) {
      busy_since_.store(GetTickCount64(), std::memory_order_relaxed);
      SelectionResult result = query_selection(automation);
      busy_since_.store(0, std::memory_order_relaxed);
      {
        std::lock_guard<std::mutex> guard(mutex_);
        selection_result_ = std::move(result);
        selection_done_id_ = selection_id;
      }
      cv_.notify_all();
      continue;
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
