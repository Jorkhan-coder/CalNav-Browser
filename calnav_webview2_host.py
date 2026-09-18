"""
calnav_webview2_host.py — Embeds Microsoft Edge WebView2 (Chromium, full
codec set incl. H.264/AAC + Widevine) inside a QWidget via comtypes + the
official WebView2Loader.dll.

Why this exists: QtWebEngine (the browser's main Chromium engine) ships
without proprietary codecs (no H.264/AAC), so Twitch/YouTube-legacy/Netflix
fail with generic playback errors even though the site itself loads fine.
WebView2 is a real, fully-licensed Edge build and does not have this gap.

WebView2Loader.dll (vendor/webview2/) is Microsoft's own small, freely
redistributable loader (MIT-licensed, from the official
Microsoft.Web.WebView2 NuGet package) — it locates the WebView2 Runtime
that ships with Windows 10/11 (or Edge) and bootstraps it. No separate
install step for the end user; only the actual WebView2 Runtime must be
present on the system, which is true by default on virtually all Windows
10/11 machines.

Requires: pip install comtypes
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import sys
from ctypes import HRESULT, c_int, c_int64, c_long, c_void_p, c_wchar_p

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import QWidget

# ── Availability check ─────────────────────────────────────────────────────

WEBVIEW2_AVAILABLE: bool = False
WEBVIEW2_UNAVAILABLE_REASON: str = ""

if sys.platform != "win32":
    WEBVIEW2_UNAVAILABLE_REASON = "Windows only"
else:
    try:
        import comtypes
        from comtypes import IUnknown, GUID, COMMETHOD, COMObject, POINTER as CP
        WEBVIEW2_AVAILABLE = True
    except ImportError as _e:
        WEBVIEW2_UNAVAILABLE_REASON = f"comtypes non installato: {_e}"


def _loader_dll_path() -> "str | None":
    if getattr(sys, "frozen", False):
        base = os.path.join(getattr(sys, "_MEIPASS", ""), "webview2")
    else:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "webview2")
    path = os.path.join(base, "WebView2Loader.dll")
    return path if os.path.exists(path) else None


if WEBVIEW2_AVAILABLE and _loader_dll_path() is None:
    WEBVIEW2_AVAILABLE = False
    WEBVIEW2_UNAVAILABLE_REASON = "WebView2Loader.dll non trovato (vendor/webview2/)"


# ── Everything below is only defined when WEBVIEW2_AVAILABLE ──────────────

if WEBVIEW2_AVAILABLE:

    class _RECT(ctypes.Structure):
        _fields_ = [
            ("left", c_long), ("top", c_long),
            ("right", c_long), ("bottom", c_long),
        ]

    class _EventRegistrationToken(ctypes.Structure):
        _fields_ = [("value", c_int64)]

    _S_OK = 0

    def _filler(name: str):
        """A vtable-slot placeholder for methods we never call — the exact
        param types don't matter since comtypes only marshals args on an
        actual call, and we never invoke these."""
        return COMMETHOD([], HRESULT, name)

    # ── ICoreWebView2 (client-side proxy — methods we call) ────────────────
    # Slots must be declared in the EXACT order of the real interface so the
    # vtable offsets line up; unused slots use _filler().

    class ICoreWebView2(IUnknown):
        _iid_ = GUID("{76ECEACB-0462-4D94-AC83-423A6793775E}")
        _methods_ = [
            _filler("get_Settings"),                                        # 0
            COMMETHOD([], HRESULT, "get_Source",                           # 1
                      (["out", "retval"], CP(c_wchar_p), "uri")),
            COMMETHOD([], HRESULT, "Navigate",                              # 2
                      (["in"], c_wchar_p, "uri")),
            _filler("NavigateToString"),                                    # 3
            _filler("add_NavigationStarting"),                              # 4
            _filler("remove_NavigationStarting"),                           # 5
            _filler("add_ContentLoading"),                                  # 6
            _filler("remove_ContentLoading"),                               # 7
            COMMETHOD([], HRESULT, "add_SourceChanged",                     # 8
                      (["in"], c_void_p, "eventHandler"),
                      (["out", "retval"], CP(_EventRegistrationToken), "token")),
            _filler("remove_SourceChanged"),                                # 9
            _filler("add_HistoryChanged"),                                  # 10
            _filler("remove_HistoryChanged"),                               # 11
            COMMETHOD([], HRESULT, "add_NavigationCompleted",               # 12
                      (["in"], c_void_p, "eventHandler"),
                      (["out", "retval"], CP(_EventRegistrationToken), "token")),
            _filler("remove_NavigationCompleted"),                         # 13
            _filler("add_FrameNavigationStarting"),                        # 14
            _filler("remove_FrameNavigationStarting"),                     # 15
            _filler("add_FrameNavigationCompleted"),                       # 16
            _filler("remove_FrameNavigationCompleted"),                    # 17
            _filler("add_ScriptDialogOpening"),                            # 18
            _filler("remove_ScriptDialogOpening"),                         # 19
            _filler("add_PermissionRequested"),                            # 20
            _filler("remove_PermissionRequested"),                         # 21
            _filler("add_ProcessFailed"),                                  # 22
            _filler("remove_ProcessFailed"),                               # 23
            _filler("AddScriptToExecuteOnDocumentCreated"),                # 24
            _filler("RemoveScriptToExecuteOnDocumentCreated"),             # 25
            _filler("ExecuteScript"),                                      # 26
            _filler("CapturePreview"),                                     # 27
            COMMETHOD([], HRESULT, "Reload"),                              # 28
            _filler("PostWebMessageAsJson"),                               # 29
            _filler("PostWebMessageAsString"),                             # 30
            _filler("add_WebMessageReceived"),                             # 31
            _filler("remove_WebMessageReceived"),                          # 32
            _filler("CallDevToolsProtocolMethod"),                         # 33
            _filler("get_BrowserProcessId"),                               # 34
            _filler("get_CanGoBack"),                                      # 35
            _filler("get_CanGoForward"),                                   # 36
            COMMETHOD([], HRESULT, "GoBack"),                              # 37
            COMMETHOD([], HRESULT, "GoForward"),                           # 38
            _filler("GetDevToolsProtocolEventReceiver"),                   # 39
            COMMETHOD([], HRESULT, "Stop"),                                # 40
            _filler("add_NewWindowRequested"),                             # 41
            _filler("remove_NewWindowRequested"),                          # 42
            COMMETHOD([], HRESULT, "add_DocumentTitleChanged",             # 43
                      (["in"], c_void_p, "eventHandler"),
                      (["out", "retval"], CP(_EventRegistrationToken), "token")),
            _filler("remove_DocumentTitleChanged"),                        # 44
            # NOTE: deliberately a filler, not a real COMMETHOD. Calling
            # get_DocumentTitle (here) together with get_Source (above) in
            # the same run — regardless of order, and even via completely
            # separate manual vtable dispatch bypassing comtypes entirely —
            # reliably crashed the whole process several seconds later, at
            # window-close time. Root cause not identified despite extensive
            # isolation testing. Using only ONE of the two getters (get_Source,
            # for address-bar URL tracking) was consistently crash-free, so
            # this engine window does not track the live page title.
            _filler("get_DocumentTitle"),                                  # 45
        ]

    # ── ICoreWebView2Controller ─────────────────────────────────────────────

    class ICoreWebView2Controller(IUnknown):
        _iid_ = GUID("{4D00C0D1-9434-4EB6-8078-8697A560334F}")
        _methods_ = [
            _filler("get_IsVisible"),                                      # 0
            COMMETHOD([], HRESULT, "put_IsVisible",                        # 1
                      (["in"], c_int, "isVisible")),
            _filler("get_Bounds"),                                         # 2
            COMMETHOD([], HRESULT, "put_Bounds",                           # 3
                      (["in"], _RECT, "bounds")),
            _filler("get_ZoomFactor"),                                     # 4
            _filler("put_ZoomFactor"),                                     # 5
            _filler("add_ZoomFactorChanged"),                              # 6
            _filler("remove_ZoomFactorChanged"),                           # 7
            _filler("SetBoundsAndZoomFactor"),                             # 8
            _filler("MoveFocus"),                                         # 9
            _filler("add_MoveFocusRequested"),                             # 10
            _filler("remove_MoveFocusRequested"),                         # 11
            _filler("add_GotFocus"),                                       # 12
            _filler("remove_GotFocus"),                                    # 13
            _filler("add_LostFocus"),                                      # 14
            _filler("remove_LostFocus"),                                   # 15
            _filler("add_AcceleratorKeyPressed"),                          # 16
            _filler("remove_AcceleratorKeyPressed"),                       # 17
            _filler("get_ParentWindow"),                                   # 18
            _filler("put_ParentWindow"),                                   # 19
            _filler("NotifyParentWindowPositionChanged"),                  # 20
            COMMETHOD([], HRESULT, "Close"),                               # 21
            COMMETHOD([], HRESULT, "get_CoreWebView2",                     # 22
                      (["out", "retval"], CP(CP(ICoreWebView2)), "coreWebView2")),
        ]

    # ── ICoreWebView2Environment ────────────────────────────────────────────

    class ICoreWebView2Environment(IUnknown):
        _iid_ = GUID("{B96D755E-0319-4E92-A296-23436F46A1FC}")
        _methods_ = [
            COMMETHOD([], HRESULT, "CreateCoreWebView2Controller",
                      (["in"], wt.HWND, "parentWindow"),
                      (["in"], c_void_p, "handler")),
            _filler("CreateWebResourceResponse"),
            _filler("get_BrowserVersionString"),
            _filler("add_NewBrowserVersionAvailable"),
            _filler("remove_NewBrowserVersionAvailable"),
        ]

    # ── Async completion / event handlers (we implement these; native code
    #    calls Invoke on them) ───────────────────────────────────────────────

    class ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler(IUnknown):
        _iid_ = GUID("{4E8A3389-C9D8-4BD2-B6B5-124FEE6CC14D}")
        _methods_ = [
            COMMETHOD([], HRESULT, "Invoke",
                      (["in"], c_int, "errorCode"),
                      (["in"], CP(ICoreWebView2Environment), "result")),
        ]

    class ICoreWebView2CreateCoreWebView2ControllerCompletedHandler(IUnknown):
        _iid_ = GUID("{6C4819F3-C9B7-4260-8127-C9F5BDE7F68C}")
        _methods_ = [
            COMMETHOD([], HRESULT, "Invoke",
                      (["in"], c_int, "errorCode"),
                      (["in"], CP(ICoreWebView2Controller), "result")),
        ]

    class ICoreWebView2SourceChangedEventHandler(IUnknown):
        _iid_ = GUID("{3C067F9F-5388-4772-8B48-79F7EF1AB37C}")
        _methods_ = [
            COMMETHOD([], HRESULT, "Invoke",
                      (["in"], c_void_p, "sender"),
                      (["in"], c_void_p, "args")),
        ]

    class ICoreWebView2NavigationCompletedEventHandler(IUnknown):
        _iid_ = GUID("{D33A35BF-1C49-4F98-93AB-006E0533FE1C}")
        _methods_ = [
            COMMETHOD([], HRESULT, "Invoke",
                      (["in"], c_void_p, "sender"),
                      (["in"], c_void_p, "args")),
        ]

    class _AsyncEnvHandler(COMObject):
        _com_interfaces_ = [ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler]

        def __init__(self, callback):
            super().__init__()
            self._callback = callback

        def Invoke(self, errorCode, result):
            self._callback(errorCode, result)
            return _S_OK

    class _AsyncControllerHandler(COMObject):
        _com_interfaces_ = [ICoreWebView2CreateCoreWebView2ControllerCompletedHandler]

        def __init__(self, callback):
            super().__init__()
            self._callback = callback

        def Invoke(self, errorCode, result):
            self._callback(errorCode, result)
            return _S_OK

    class _SourceChangedHandler(COMObject):
        _com_interfaces_ = [ICoreWebView2SourceChangedEventHandler]

        def __init__(self, callback):
            super().__init__()
            self._callback = callback

        def Invoke(self, sender, args):
            self._callback()
            return _S_OK

    class _NavigationCompletedHandler(COMObject):
        _com_interfaces_ = [ICoreWebView2NavigationCompletedEventHandler]

        def __init__(self, callback):
            super().__init__()
            self._callback = callback

        def Invoke(self, sender, args):
            self._callback()
            return _S_OK

    # ── DLL entry point ─────────────────────────────────────────────────────

    _dll = ctypes.WinDLL(_loader_dll_path())
    _dll.CreateCoreWebView2EnvironmentWithOptions.restype = HRESULT
    _dll.CreateCoreWebView2EnvironmentWithOptions.argtypes = [
        c_wchar_p, c_wchar_p, c_void_p,
        CP(ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler),
    ]

    # ── WebView2EmbedWidget ──────────────────────────────────────────────────

    class WebView2EmbedWidget(QWidget):
        """
        QWidget that embeds a Microsoft Edge WebView2 control in-place.

        Usage:
            w = WebView2EmbedWidget(parent)
            w.init_browser(pending_url="https://twitch.tv")
        Initialisation is asynchronous (COM callbacks); navigate() before
        the controller is ready is queued and flushed once it comes up.
        """

        urlChanged = pyqtSignal(str)
        titleChanged = pyqtSignal(str)
        ready = pyqtSignal()

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
            self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setMinimumSize(100, 60)

            self._environment = None
            self._controller: "ICoreWebView2Controller | None" = None
            self._webview: "ICoreWebView2 | None" = None
            self._pending_url = ""

            self._last_url = ""
            self._last_title = ""

            # Keep every handler object alive for the widget's lifetime —
            # COM does not keep python-side callback objects alive on its own.
            self._handlers = []

        # ── Initialisation ────────────────────────────────────────────────

        def init_browser(self, user_data_dir: str, pending_url: str = "") -> str:
            try:
                comtypes.CoInitialize()
            except Exception:
                pass

            self._pending_url = pending_url
            try:
                os.makedirs(user_data_dir, exist_ok=True)
                env_handler = _AsyncEnvHandler(self._on_environment_created)
                self._handlers.append(env_handler)
                hr = _dll.CreateCoreWebView2EnvironmentWithOptions(
                    None, user_data_dir, None,
                    env_handler.QueryInterface(
                        ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler
                    ),
                )
                if hr != _S_OK:
                    return f"CreateCoreWebView2EnvironmentWithOptions: 0x{hr & 0xFFFFFFFF:08X}"
                return ""
            except Exception as exc:
                return str(exc)

        def _on_environment_created(self, error_code, environment):
            if error_code != _S_OK or environment is None:
                return
            self._environment = environment
            try:
                hwnd = int(self.winId())
                ctrl_handler = _AsyncControllerHandler(self._on_controller_created)
                self._handlers.append(ctrl_handler)
                environment.CreateCoreWebView2Controller(
                    hwnd,
                    ctrl_handler.QueryInterface(
                        ICoreWebView2CreateCoreWebView2ControllerCompletedHandler
                    ),
                )
            except Exception:
                pass

        def _on_controller_created(self, error_code, controller):
            if error_code != _S_OK or controller is None:
                return
            self._controller = controller
            try:
                controller.put_Bounds(self._get_rect())
                controller.put_IsVisible(1)
                self._webview = controller.get_CoreWebView2()

                src_handler = _SourceChangedHandler(self._on_source_changed)
                nav_handler = _NavigationCompletedHandler(self._on_navigation_completed)
                self._handlers += [src_handler, nav_handler]

                self._webview.add_SourceChanged(
                    src_handler.QueryInterface(ICoreWebView2SourceChangedEventHandler)
                )
                self._webview.add_NavigationCompleted(
                    nav_handler.QueryInterface(ICoreWebView2NavigationCompletedEventHandler)
                )
                # No add_DocumentTitleChanged — see get_DocumentTitle's filler
                # note above on why this engine window doesn't track title.

                if self._pending_url:
                    self.navigate(self._pending_url)
                    self._pending_url = ""
                self.ready.emit()
            except Exception:
                pass

        # ── Helpers ───────────────────────────────────────────────────────

        def _get_rect(self) -> _RECT:
            r = _RECT()
            r.left = r.top = 0
            r.right = max(self.width(), 1)
            r.bottom = max(self.height(), 1)
            return r

        # Invoked directly from a native COM event callback
        # (ICoreWebView2SourceChangedEventHandler.Invoke / NavigationCompleted)
        # — deferred to a fresh Qt event-loop iteration rather than calling
        # back into WebView2 synchronously from within that call stack.

        def _on_source_changed(self):
            QTimer.singleShot(0, self._update_url)

        def _on_navigation_completed(self):
            QTimer.singleShot(0, self._update_url)

        def _update_url(self):
            url = self.current_url
            if url and url != self._last_url:
                self._last_url = url
                self.urlChanged.emit(url)

        # ── Navigation ────────────────────────────────────────────────────

        def navigate(self, url: str):
            if not url.startswith(("http://", "https://", "file://")):
                url = "http://" + url
            if self._webview is None:
                self._pending_url = url
                return
            try:
                self._webview.Navigate(url)
            except Exception:
                pass

        def go_back(self):
            if self._webview:
                try:
                    self._webview.GoBack()
                except Exception:
                    pass

        def go_forward(self):
            if self._webview:
                try:
                    self._webview.GoForward()
                except Exception:
                    pass

        def refresh(self):
            if self._webview:
                try:
                    self._webview.Reload()
                except Exception:
                    pass

        def stop(self):
            if self._webview:
                try:
                    self._webview.Stop()
                except Exception:
                    pass

        # ── Properties ────────────────────────────────────────────────────

        @property
        def current_url(self) -> str:
            if self._webview:
                try:
                    return self._webview.get_Source() or ""
                except Exception:
                    pass
            return ""

        @property
        def current_title(self) -> str:
            # Always "" — see get_DocumentTitle's filler note above.
            return ""

        # ── Qt events ─────────────────────────────────────────────────────

        def resizeEvent(self, event):
            super().resizeEvent(event)
            if self._controller:
                try:
                    self._controller.put_Bounds(self._get_rect())
                except Exception:
                    pass

        def shutdown(self):
            """Close and detach the WebView2 controller.

            Must be called explicitly by the owning top-level window's
            closeEvent — Qt does NOT send closeEvent to child widgets when
            their parent window closes.
            """
            if self._controller:
                try:
                    self._controller.Close()
                except Exception:
                    pass
                self._controller = None
            self._webview = None
            self._environment = None

        def closeEvent(self, event):
            self.shutdown()
            super().closeEvent(event)

else:
    # ── Stub when comtypes/WebView2Loader is unavailable ──────────────────

    class WebView2EmbedWidget(QWidget):   # type: ignore[no-redef]
        urlChanged = pyqtSignal(str)
        titleChanged = pyqtSignal(str)
        ready = pyqtSignal()

        def __init__(self, parent=None):
            super().__init__(parent)

        def init_browser(self, user_data_dir: str, pending_url: str = "") -> str:
            return WEBVIEW2_UNAVAILABLE_REASON

        def navigate(self, url: str): pass
        def go_back(self):            pass
        def go_forward(self):         pass
        def refresh(self):            pass
        def stop(self):               pass

        @property
        def current_url(self)   -> str: return ""

        @property
        def current_title(self) -> str: return ""
