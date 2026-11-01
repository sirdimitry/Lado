#include "focus.h"

#include <array>
#include <filesystem>

namespace lado {
namespace {

constexpr size_t kMaxCachedProcesses = 128;

}  // namespace

Lang language_from_hkl(HKL layout) {
  if (layout == nullptr) return Lang::None;
  const WORD lang_id = LOWORD(reinterpret_cast<DWORD_PTR>(layout));
  switch (PRIMARYLANGID(lang_id)) {
    case LANG_ENGLISH:
      return Lang::En;
    case LANG_RUSSIAN:
      return Lang::Ru;
    default:
      return Lang::None;
  }
}

void FocusMonitor::adopt(HWND foreground) {
  info_ = FocusInfo{};
  info_.hwnd = foreground;
  if (foreground == nullptr) return;

  DWORD pid = 0;
  info_.thread_id = GetWindowThreadProcessId(foreground, &pid);
  info_.pid = pid;
  info_.layout = GetKeyboardLayout(info_.thread_id);
  info_.lang = language_from_hkl(info_.layout);
  info_.process = process_name(pid);
  info_.valid = true;
}

void FocusMonitor::refresh() {
  const HWND foreground = GetForegroundWindow();
  if (foreground != info_.hwnd) {
    adopt(foreground);
    return;
  }
  refresh_layout();
}

void FocusMonitor::refresh_layout() {
  if (info_.hwnd == nullptr) return;
  const DWORD thread = GetWindowThreadProcessId(info_.hwnd, nullptr);
  if (thread == 0) return;
  info_.thread_id = thread;
  const HKL layout = GetKeyboardLayout(thread);
  if (layout != info_.layout) {
    info_.layout = layout;
    info_.lang = language_from_hkl(layout);
  }
}

void FocusMonitor::set_layout(HKL layout) {
  if (layout == nullptr) return;
  info_.layout = layout;
  info_.lang = language_from_hkl(layout);
}

std::wstring FocusMonitor::process_name(DWORD pid) {
  if (pid == 0) return {};
  const auto cached = process_cache_.find(pid);
  if (cached != process_cache_.end()) return cached->second;

  std::wstring name;
  HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
  if (process != nullptr) {
    std::array<wchar_t, 1024> buffer{};
    DWORD size = static_cast<DWORD>(buffer.size());
    if (QueryFullProcessImageNameW(process, 0, buffer.data(), &size)) {
      name = std::filesystem::path(std::wstring(buffer.data(), size)).filename();
    }
    CloseHandle(process);
  }

  if (process_cache_.size() >= kMaxCachedProcesses) process_cache_.clear();
  process_cache_.emplace(pid, name);
  return name;
}

}  // namespace lado
