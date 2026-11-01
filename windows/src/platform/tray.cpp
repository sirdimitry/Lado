#include "tray.h"

#include <cwchar>
#include <iterator>

#include "log.h"
#include "resource.h"

namespace lado {
namespace {

int tray_icon_size() {
  const UINT dpi = GetDpiForSystem();
  int size = 0;
  if (dpi != 0) {
    size = GetSystemMetricsForDpi(SM_CXSMICON, dpi);
  }
  if (size <= 0) size = GetSystemMetrics(SM_CXSMICON);
  return size > 0 ? size : 16;
}

}  // namespace

bool TrayIcon::create(HINSTANCE instance, HWND owner, UINT callback_message) {
  const int size = tray_icon_size();
  icons_[0] = reinterpret_cast<HICON>(LoadImageW(instance, MAKEINTRESOURCEW(IDI_RU),
                                            IMAGE_ICON, size, size, LR_DEFAULTCOLOR));
  icons_[1] = reinterpret_cast<HICON>(LoadImageW(instance, MAKEINTRESOURCEW(IDI_EN),
                                            IMAGE_ICON, size, size, LR_DEFAULTCOLOR));
  icons_[2] = reinterpret_cast<HICON>(LoadImageW(instance, MAKEINTRESOURCEW(IDI_RU_SECURE),
                                            IMAGE_ICON, size, size, LR_DEFAULTCOLOR));
  icons_[3] = reinterpret_cast<HICON>(LoadImageW(instance, MAKEINTRESOURCEW(IDI_EN_SECURE),
                                            IMAGE_ICON, size, size, LR_DEFAULTCOLOR));
  icons_[4] = reinterpret_cast<HICON>(LoadImageW(instance, MAKEINTRESOURCEW(IDI_OTHER),
                                            IMAGE_ICON, size, size, LR_DEFAULTCOLOR));
  icons_[5] = reinterpret_cast<HICON>(LoadImageW(instance, MAKEINTRESOURCEW(IDI_PAUSED),
                                            IMAGE_ICON, size, size, LR_DEFAULTCOLOR));
  for (HICON icon : icons_) {
    if (icon == nullptr) {
      log_message(L"tray icon resource missing");
      return false;
    }
  }
  has_icon_ = true;

  data_.cbSize = sizeof(data_);
  data_.hWnd = owner;
  data_.uID = 1;
  data_.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP;
  data_.uCallbackMessage = callback_message;
  data_.hIcon = icons_[0];
  wcscpy(data_.szTip, L"Lado");
  data_.szTip[std::size(data_.szTip) - 1] = L'\0';
  if (!Shell_NotifyIconW(NIM_ADD, &data_)) {
    log_message(L"Shell_NotifyIcon(NIM_ADD) failed: %lu", GetLastError());
    return false;
  }
  visible_ = true;
  current_kind_ = TrayIconKind::Ru;
  current_tooltip_ = L"Lado";
  return true;
}

void TrayIcon::destroy() {
  if (visible_) {
    Shell_NotifyIconW(NIM_DELETE, &data_);
    visible_ = false;
  }
  for (HICON& icon : icons_) {
    if (icon != nullptr) {
      DestroyIcon(icon);
      icon = nullptr;
    }
  }
  has_icon_ = false;
}

HICON TrayIcon::icon_for(TrayIconKind kind) const {
  switch (kind) {
    case TrayIconKind::Ru: return icons_[0];
    case TrayIconKind::En: return icons_[1];
    case TrayIconKind::RuSecure: return icons_[2];
    case TrayIconKind::EnSecure: return icons_[3];
    case TrayIconKind::Other: return icons_[4];
    case TrayIconKind::Paused: return icons_[5];
  }
  return icons_[4];
}

void TrayIcon::update(TrayIconKind kind, const std::wstring& tooltip) {
  if (!visible_ || !has_icon_) return;
  if (kind == current_kind_ && tooltip == current_tooltip_) return;

  data_.hIcon = icon_for(kind);
  wcsncpy(data_.szTip, tooltip.c_str(), std::size(data_.szTip) - 1);
  data_.szTip[std::size(data_.szTip) - 1] = L'\0';
  data_.uFlags = NIF_ICON | NIF_TIP;
  if (!Shell_NotifyIconW(NIM_MODIFY, &data_)) {
    // The shell may have restarted; re-add once.
    data_.uFlags |= NIF_MESSAGE;
    if (Shell_NotifyIconW(NIM_ADD, &data_)) visible_ = true;
  }
  current_kind_ = kind;
  current_tooltip_ = tooltip;
}

}  // namespace lado
