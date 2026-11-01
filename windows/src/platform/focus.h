// Foreground window, its keyboard layout and its executable name.
#pragma once

#include <windows.h>

#include <string>
#include <unordered_map>

#include "layout.h"

namespace lado {

struct FocusInfo {
  HWND hwnd = nullptr;
  DWORD pid = 0;
  DWORD thread_id = 0;
  HKL layout = nullptr;
  Lang lang = Lang::None;
  std::wstring process;  // executable file name, e.g. chrome.exe
  bool valid = false;
};

Lang language_from_hkl(HKL layout);

class FocusMonitor {
 public:
  // Full refresh; cheap when the foreground window did not change.
  void refresh();
  // Re-reads only the input layout. Called before every correction so a
  // just-switched layout is not sampled stale.
  void refresh_layout();

  const FocusInfo& info() const { return info_; }

 private:
  std::wstring process_name(DWORD pid);
  void adopt(HWND foreground);

  FocusInfo info_;
  std::unordered_map<DWORD, std::wstring> process_cache_;
};

}  // namespace lado
