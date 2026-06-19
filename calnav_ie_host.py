"""
calnav_ie_host.py — Embeds IE/MSHTML WebBrowser2 inside a QWidget via comtypes.

Uses the COM OLE in-place activation protocol — no QAxContainer required.
Works on Windows 10/11 as long as MSHTML (ieframe.dll) is present.

Requires: pip install comtypes
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import sys
from ctypes import HRESULT, c_int, c_long, c_uint, c_ushort

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget

# ── Availability check ─────────────────────────────────────────────────────────

IE_AVAILABLE: bool = False
IE_UNAVAILABLE_REASON: str = ""

if sys.platform != "win32":
    IE_UNAVAILABLE_REASON = "Windows only"
else:
    try:
        import comtypes
        import comtypes.client
        from comtypes import (
            IUnknown, GUID, COMMETHOD, COMObject,
            POINTER as CP, CLSCTX_INPROC_SERVER,
        )
        IE_AVAILABLE = True
    except ImportError as _e:
        IE_UNAVAILABLE_REASON = f"comtypes non installato: {_e}"


# ── Everything below is only defined when IE_AVAILABLE ────────────────────────

if IE_AVAILABLE:

    # ── Structures ─────────────────────────────────────────────────────────────

    class _RECT(ctypes.Structure):
        _fields_ = [
            ("left",   c_long),
            ("top",    c_long),
            ("right",  c_long),
            ("bottom", c_long),
        ]

    class _SIZE(ctypes.Structure):
        _fields_ = [("cx", c_long), ("cy", c_long)]

    class _FRAMEINFO(ctypes.Structure):
        """OLEINPLACEFRAMEINFO"""
        _fields_ = [
            ("cb",            c_uint),
            ("fMDIApp",       c_int),
            ("hwndFrame",     wt.HWND),
            ("haccel",        ctypes.c_void_p),
            ("cAccelEntries", c_uint),
        ]

    # ── HRESULT constants ──────────────────────────────────────────────────────

    _S_OK    = 0
    _E_NOTIMPL = ctypes.c_long(0x80004001).value
    _INPLACE_E_NOTOOLSPACE = ctypes.c_long(0x800401A1).value

    # ── COM interface definitions ──────────────────────────────────────────────
    # Method lists contain ONLY the new methods each interface adds.
    # comtypes builds the full vtable from the inheritance chain.

    class IOleWindow(IUnknown):
        _iid_ = GUID("{00000114-0000-0000-C000-000000000046}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetWindow",
                      (["out"], CP(wt.HWND), "phwnd")),
            COMMETHOD([], HRESULT, "ContextSensitiveHelp",
                      (["in"], c_int, "fEnterMode")),
        ]

    class IOleInPlaceUIWindow(IOleWindow):
        _iid_ = GUID("{00000115-0000-0000-C000-000000000046}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetBorder",
                      (["out"], CP(_RECT), "lprectBorder")),
            COMMETHOD([], HRESULT, "RequestBorderSpace",
                      (["in"], CP(_RECT), "pborderwidths")),
            COMMETHOD([], HRESULT, "SetBorderSpace",
                      (["in"], CP(_RECT), "pborderwidths")),
            COMMETHOD([], HRESULT, "SetActiveObject",
                      (["in"], ctypes.c_void_p, "pActiveObject"),
                      (["in"], ctypes.c_wchar_p, "pszObjName")),
        ]

    class IOleInPlaceFrame(IOleInPlaceUIWindow):
        _iid_ = GUID("{00000116-0000-0000-C000-000000000046}")
        _methods_ = [
            COMMETHOD([], HRESULT, "InsertMenus",
                      (["in"], wt.HWND, "hmenuShared"),
                      (["in"], ctypes.c_void_p, "lpMenuWidths")),
            COMMETHOD([], HRESULT, "SetMenu",
                      (["in"], wt.HWND, "hmenuShared"),
                      (["in"], ctypes.c_void_p, "holemenu"),
                      (["in"], wt.HWND, "hwndActiveObject")),
            COMMETHOD([], HRESULT, "RemoveMenus",
                      (["in"], wt.HWND, "hmenuShared")),
            COMMETHOD([], HRESULT, "SetStatusText",
                      (["in"], ctypes.c_wchar_p, "pszStatusText")),
            COMMETHOD([], HRESULT, "EnableModeless",
                      (["in"], c_int, "fEnable")),
            COMMETHOD([], HRESULT, "TranslateAccelerator",
                      (["in"], ctypes.c_void_p, "lpmsg"),
                      (["in"], c_ushort, "wID")),
        ]

    class IOleInPlaceSite(IOleWindow):
        _iid_ = GUID("{00000119-0000-0000-C000-000000000046}")
        _methods_ = [
            COMMETHOD([], HRESULT, "CanInPlaceActivate"),
            COMMETHOD([], HRESULT, "OnInPlaceActivate"),
            COMMETHOD([], HRESULT, "OnUIActivate"),
            COMMETHOD([], HRESULT, "GetWindowContext",
                      (["out"], CP(CP(IOleInPlaceFrame)),      "ppFrame"),
                      (["out"], CP(CP(IOleInPlaceUIWindow)),   "ppDoc"),
                      (["out"], CP(_RECT),                     "lprcPosRect"),
                      (["out"], CP(_RECT),                     "lprcClipRect"),
                      (["in", "out"], CP(_FRAMEINFO),          "lpFrameInfo")),
            COMMETHOD([], HRESULT, "Scroll",
                      (["in"], _SIZE, "scrollExtant")),
            COMMETHOD([], HRESULT, "OnUIDeactivate",
                      (["in"], c_int, "fUndoable")),
            COMMETHOD([], HRESULT, "OnInPlaceDeactivate"),
            COMMETHOD([], HRESULT, "DiscardUndoState"),
            COMMETHOD([], HRESULT, "DeactivateAndUndo"),
            COMMETHOD([], HRESULT, "OnPosRectChange",
                      (["in"], CP(_RECT), "lprcPosRect")),
        ]

    class IOleClientSite(IUnknown):
        _iid_ = GUID("{00000118-0000-0000-C000-000000000046}")
        _methods_ = [
            COMMETHOD([], HRESULT, "SaveObject"),
            COMMETHOD([], HRESULT, "GetMoniker",
                      (["in"], c_uint, "dwAssign"),
                      (["in"], c_uint, "dwWhichMoniker"),
                      (["out"], CP(ctypes.c_void_p), "ppmk")),
            COMMETHOD([], HRESULT, "GetContainer",
                      (["out"], CP(ctypes.c_void_p), "ppContainer")),
            COMMETHOD([], HRESULT, "ShowObject"),
            COMMETHOD([], HRESULT, "OnShowWindow",
                      (["in"], c_int, "fShow")),
            COMMETHOD([], HRESULT, "RequestNewObjectLayout"),
        ]

    class IOleObject(IUnknown):
        _iid_ = GUID("{00000112-0000-0000-C000-000000000046}")
        _methods_ = [
            COMMETHOD([], HRESULT, "SetClientSite",
                      (["in"], CP(IOleClientSite), "pClientSite")),
            COMMETHOD([], HRESULT, "GetClientSite",
                      (["out"], CP(CP(IOleClientSite)), "ppClientSite")),
            COMMETHOD([], HRESULT, "SetHostNames",
                      (["in"], ctypes.c_wchar_p, "szContainerApp"),
                      (["in"], ctypes.c_wchar_p, "szContainerObj")),
            COMMETHOD([], HRESULT, "Close",
                      (["in"], c_uint, "dwSaveOption")),
            COMMETHOD([], HRESULT, "SetMoniker",
                      (["in"], c_uint, "dwWhichMoniker"),
                      (["in"], ctypes.c_void_p, "pmk")),
            COMMETHOD([], HRESULT, "GetMoniker",
                      (["in"], c_uint, "dwAssign"),
                      (["in"], c_uint, "dwWhichMoniker"),
                      (["out"], CP(ctypes.c_void_p), "ppmk")),
            COMMETHOD([], HRESULT, "InitFromData",
                      (["in"], ctypes.c_void_p, "pDataObject"),
                      (["in"], c_int, "fCreation"),
                      (["in"], c_uint, "dwReserved")),
            COMMETHOD([], HRESULT, "GetClipboardData",
                      (["in"], c_uint, "dwReserved"),
                      (["out"], CP(ctypes.c_void_p), "ppDataObject")),
            COMMETHOD([], HRESULT, "DoVerb",
                      (["in"], c_long, "iVerb"),
                      (["in"], ctypes.c_void_p, "lpmsg"),
                      (["in"], CP(IOleClientSite), "pActiveSite"),
                      (["in"], c_long, "lindex"),
                      (["in"], wt.HWND, "hwndParent"),
                      (["in"], CP(_RECT), "lprcPosRect")),
            COMMETHOD([], HRESULT, "EnumVerbs",
                      (["out"], CP(ctypes.c_void_p), "ppEnumOleVerb")),
            COMMETHOD([], HRESULT, "Update"),
            COMMETHOD([], HRESULT, "IsUpToDate"),
            COMMETHOD([], HRESULT, "GetUserClassID",
                      (["out"], CP(GUID), "pClsid")),
            COMMETHOD([], HRESULT, "GetUserType",
                      (["in"], c_uint, "dwFormOfType"),
                      (["out"], CP(ctypes.c_wchar_p), "pszUserType")),
            COMMETHOD([], HRESULT, "SetExtent",
                      (["in"], c_uint, "dwDrawAspect"),
                      (["in"], CP(_SIZE), "psizel")),
            COMMETHOD([], HRESULT, "GetExtent",
                      (["in"], c_uint, "dwDrawAspect"),
                      (["out"], CP(_SIZE), "psizel")),
            COMMETHOD([], HRESULT, "Advise",
                      (["in"], ctypes.c_void_p, "pAdvSink"),
                      (["out"], CP(c_uint), "pdwConnection")),
            COMMETHOD([], HRESULT, "Unadvise",
                      (["in"], c_uint, "dwConnection")),
            COMMETHOD([], HRESULT, "EnumAdvise",
                      (["out"], CP(ctypes.c_void_p), "ppenumAdvise")),
            COMMETHOD([], HRESULT, "GetMiscStatus",
                      (["in"], c_uint, "dwAspect"),
                      (["out"], CP(c_uint), "pdwStatus")),
            COMMETHOD([], HRESULT, "SetColorScheme",
                      (["in"], ctypes.c_void_p, "pLogpal")),
        ]

    class IOleInPlaceObject(IOleWindow):
        _iid_ = GUID("{00000113-0000-0000-C000-000000000046}")
        _methods_ = [
            COMMETHOD([], HRESULT, "InPlaceDeactivate"),
            COMMETHOD([], HRESULT, "UIDeactivate"),
            COMMETHOD([], HRESULT, "SetObjectRects",
                      (["in"], CP(_RECT), "lprcPosRect"),
                      (["in"], CP(_RECT), "lprcClipRect")),
            COMMETHOD([], HRESULT, "ReactivateAndUndo"),
        ]

    # ── _BrowserHost ───────────────────────────────────────────────────────────

    class _BrowserHost(COMObject):
        """
        Implements IOleClientSite + IOleInPlaceSite + IOleInPlaceFrame.

        The single object serves all three interface roles; comtypes exposes
        separate vtable-pointers for each through QueryInterface.
        """
        _com_interfaces_ = [IOleClientSite, IOleInPlaceSite, IOleInPlaceFrame]

        def __init__(self, hwnd: int, get_rect):
            super().__init__()
            self._hwnd = hwnd
            self._get_rect = get_rect   # () -> _RECT

        # ── IOleWindow (shared by IOleInPlaceSite and IOleInPlaceFrame) ────────

        def GetWindow(self, phwnd):
            phwnd[0] = self._hwnd
            return _S_OK

        def ContextSensitiveHelp(self, fEnterMode):
            return _S_OK

        # ── IOleClientSite ─────────────────────────────────────────────────────

        def SaveObject(self):
            return _E_NOTIMPL

        def GetMoniker(self, dwAssign, dwWhichMoniker, ppmk):
            return _E_NOTIMPL

        def GetContainer(self, ppContainer):
            return _E_NOTIMPL

        def ShowObject(self):
            return _S_OK

        def OnShowWindow(self, fShow):
            return _S_OK

        def RequestNewObjectLayout(self):
            return _E_NOTIMPL

        # ── IOleInPlaceSite ───────────────────────────────────────────────────

        def CanInPlaceActivate(self):
            return _S_OK

        def OnInPlaceActivate(self):
            return _S_OK

        def OnUIActivate(self):
            return _S_OK

        def GetWindowContext(self, ppFrame, ppDoc, lprcPosRect, lprcClipRect, lpFrameInfo):
            try:
                # Return ourself as the IOleInPlaceFrame
                frame = self.QueryInterface(IOleInPlaceFrame)
                ppFrame[0] = frame

                # No separate doc-level UI window
                ppDoc[0] = None

                # Current position / clip rectangles
                r = self._get_rect()
                lprcPosRect[0] = r
                lprcClipRect[0] = r

                # Fill the OLEINPLACEFRAMEINFO the caller allocated (cb is pre-set)
                fi = lpFrameInfo[0]
                fi.fMDIApp = 0
                fi.hwndFrame = self._hwnd
                fi.haccel = None
                fi.cAccelEntries = 0
            except Exception:
                pass
            return _S_OK

        def Scroll(self, scrollExtant):
            return _S_OK

        def OnUIDeactivate(self, fUndoable):
            return _S_OK

        def OnInPlaceDeactivate(self):
            return _S_OK

        def DiscardUndoState(self):
            return _S_OK

        def DeactivateAndUndo(self):
            return _S_OK

        def OnPosRectChange(self, lprcPosRect):
            return _S_OK

        # ── IOleInPlaceUIWindow (also part of IOleInPlaceFrame) ───────────────

        def GetBorder(self, lprectBorder):
            return _INPLACE_E_NOTOOLSPACE

        def RequestBorderSpace(self, pborderwidths):
            return _INPLACE_E_NOTOOLSPACE

        def SetBorderSpace(self, pborderwidths):
            return _S_OK

        def SetActiveObject(self, pActiveObject, pszObjName):
            return _S_OK

        # ── IOleInPlaceFrame ──────────────────────────────────────────────────

        def InsertMenus(self, hmenuShared, lpMenuWidths):
            return _S_OK

        def SetMenu(self, hmenuShared, holemenu, hwndActiveObject):
            return _S_OK

        def RemoveMenus(self, hmenuShared):
            return _S_OK

        def SetStatusText(self, pszStatusText):
            return _S_OK

        def EnableModeless(self, fEnable):
            return _S_OK

        def TranslateAccelerator(self, lpmsg, wID):
            return _E_NOTIMPL

    # ── IEEmbedWidget ──────────────────────────────────────────────────────────

    _CLSID_WB2 = GUID("{8856F961-340A-11D0-A96B-00C04FD705A2}")
    _OLEIVERB_INPLACEACTIVATE = -5

    class IEEmbedWidget(QWidget):
        """
        QWidget that embeds the IE/MSHTML WebBrowser2 COM control in-place.

        Usage:
            w = IEEmbedWidget(parent)
            err = w.init_browser()      # returns "" on success, error string otherwise
            if not err:
                w.navigate("https://example.com")
        """

        urlChanged   = pyqtSignal(str)
        titleChanged = pyqtSignal(str)

        def __init__(self, parent=None):
            super().__init__(parent)
            # Force a real Win32 HWND before any COM work
            self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
            self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setMinimumSize(100, 60)

            self._host: _BrowserHost | None = None
            self._ole:  IOleObject          | None = None
            self._ipo:  IOleInPlaceObject   | None = None
            self._wb2   = None   # IWebBrowser2 (via GetBestInterface / IDispatch)
            self._poll: QTimer | None = None

            self._last_url   = ""
            self._last_title = ""

        # ── Initialisation ────────────────────────────────────────────────────

        def init_browser(self) -> str:
            """
            Create and in-place-activate the WebBrowser2 COM control.

            Returns "" on success, or an error description string on failure.
            """
            try:
                comtypes.CoInitialize()

                # The HWND must exist before we talk to COM
                hwnd = int(self.winId())

                # Create the WebBrowser2 in-process COM object
                self._ole = comtypes.client.CreateObject(
                    _CLSID_WB2,
                    interface=IOleObject,
                    clsctx=CLSCTX_INPROC_SERVER,
                )

                # Wire up the client site (our host object)
                self._host = _BrowserHost(hwnd, self._get_rect)
                cs = self._host.QueryInterface(IOleClientSite)
                self._ole.SetClientSite(cs)
                self._ole.SetHostNames("CalNav", "CalNav IE Host")

                # In-place activate — this creates the child HWND inside ours
                r = self._get_rect()
                self._ole.DoVerb(
                    _OLEIVERB_INPLACEACTIVATE,
                    None,   # no MSG
                    cs,
                    0,      # lindex
                    hwnd,
                    ctypes.byref(r),
                )

                # Interface for resize
                self._ipo = self._ole.QueryInterface(IOleInPlaceObject)

                # Interface for navigation — try typelib-backed first, fall back to raw
                try:
                    self._wb2 = comtypes.client.GetBestInterface(self._ole)
                except Exception:
                    from comtypes.automation import IDispatch
                    self._wb2 = self._ole.QueryInterface(IDispatch)

                # Poll for URL / title updates
                self._poll = QTimer(self)
                self._poll.timeout.connect(self._poll_location)
                self._poll.start(600)

                return ""

            except Exception as exc:
                return str(exc)

        # ── Helpers ───────────────────────────────────────────────────────────

        def _get_rect(self) -> _RECT:
            r = _RECT()
            r.left = r.top = 0
            r.right  = max(self.width(),  1)
            r.bottom = max(self.height(), 1)
            return r

        # ── Navigation ────────────────────────────────────────────────────────

        def navigate(self, url: str):
            if self._wb2 is None:
                return
            if not url.startswith(("http://", "https://", "file://")):
                url = "http://" + url
            try:
                self._wb2.Navigate(url)
            except Exception:
                pass

        def go_back(self):
            if self._wb2:
                try:
                    self._wb2.GoBack()
                except Exception:
                    pass

        def go_forward(self):
            if self._wb2:
                try:
                    self._wb2.GoForward()
                except Exception:
                    pass

        def refresh(self):
            if self._wb2:
                try:
                    self._wb2.Refresh()
                except Exception:
                    pass

        def stop(self):
            if self._wb2:
                try:
                    self._wb2.Stop()
                except Exception:
                    pass

        # ── Properties ────────────────────────────────────────────────────────

        @property
        def current_url(self) -> str:
            if self._wb2:
                try:
                    return self._wb2.LocationURL or ""
                except Exception:
                    pass
            return ""

        @property
        def current_title(self) -> str:
            if self._wb2:
                try:
                    return self._wb2.LocationName or ""
                except Exception:
                    pass
            return ""

        # ── Polling ───────────────────────────────────────────────────────────

        def _poll_location(self):
            url = self.current_url
            if url and url != self._last_url:
                self._last_url = url
                self.urlChanged.emit(url)
            title = self.current_title
            if title and title != self._last_title:
                self._last_title = title
                self.titleChanged.emit(title)

        # ── Qt events ─────────────────────────────────────────────────────────

        def resizeEvent(self, event):
            super().resizeEvent(event)
            if self._ipo:
                try:
                    r = self._get_rect()
                    self._ipo.SetObjectRects(ctypes.byref(r), ctypes.byref(r))
                except Exception:
                    pass

        def closeEvent(self, event):
            if self._poll:
                self._poll.stop()
                self._poll = None
            if self._ipo:
                try:
                    self._ipo.InPlaceDeactivate()
                except Exception:
                    pass
                self._ipo = None
            if self._ole:
                try:
                    self._ole.Close(0)
                except Exception:
                    pass
                self._ole = None
            self._host = None
            self._wb2  = None
            super().closeEvent(event)

else:
    # ── Stub when comtypes is unavailable ─────────────────────────────────────

    class IEEmbedWidget(QWidget):   # type: ignore[no-redef]
        urlChanged   = pyqtSignal(str)
        titleChanged = pyqtSignal(str)

        def __init__(self, parent=None):
            super().__init__(parent)

        def init_browser(self) -> str:
            return IE_UNAVAILABLE_REASON

        def navigate(self, url: str): pass
        def go_back(self):            pass
        def go_forward(self):         pass
        def refresh(self):            pass
        def stop(self):               pass

        @property
        def current_url(self)   -> str: return ""

        @property
        def current_title(self) -> str: return ""
