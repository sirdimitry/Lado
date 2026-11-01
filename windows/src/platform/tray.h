// Notification-area icon and its tooltip. Icons are pre-rendered per DPI so the
// RU/EN marker stays readable at 100%, 150% and 200%.
#pragma once

#include <windows.h>
#include <shellapi.h>

#include <string>

namespace lado {

enum class TrayIconKind { Ru, En, RuSecure, EnSecure, Other, Paused };

class TrayIcon {
 public:
  bool create(HINSTANCE instance, HWND owner, UINT callback_message);
  void destroy();
  void update(TrayIconKind kind, const std::wstring& tooltip);
  bool visible() const { return visible_; }

 private:
  HICON icon_for(TrayIconKind kind) const;

  NOTIFYICONDATAW data_{};
  HICON icons_[6] = {};
  TrayIconKind current_kind_ = TrayIconKind::Other;
  std::wstring current_tooltip_;
  bool visible_ = false;
  bool has_icon_ = false;
};

}  // namespace lado
