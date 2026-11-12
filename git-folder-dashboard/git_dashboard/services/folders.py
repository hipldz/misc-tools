"""Platform folder selection; Windows uses the native Common Item Dialog.

COM interface/option definitions:
https://learn.microsoft.com/en-us/windows/win32/shell/common-file-dialog
"""

import ctypes
import os
import threading
from uuid import UUID

_picker_lock = threading.Lock()


class GUID(ctypes.Structure):
    _fields_ = [("data1", ctypes.c_uint32), ("data2", ctypes.c_uint16),
                ("data3", ctypes.c_uint16), ("data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(UUID(value).bytes_le)


def _check(result):
    if result < 0:
        raise OSError("Windows folder dialog failed (HRESULT 0x{0:08X}).".format(result & 0xffffffff))


def _invoke(pointer, slot, result_type, argument_types=(), *arguments):
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    function = ctypes.WINFUNCTYPE(result_type, ctypes.c_void_p, *argument_types)(table[slot])
    return function(pointer, *arguments)


class WindowsFolderDialog:
    """An STA COM dialog with deterministic release, also probeable without Show."""

    def __enter__(self):
        self.pointer = ctypes.c_void_p()
        self.ole = ctypes.WinDLL("ole32")
        self.ole.CoInitializeEx.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        self.ole.CoInitializeEx.restype = ctypes.c_int32
        self.ole.CoCreateInstance.argtypes = (ctypes.POINTER(GUID), ctypes.c_void_p, ctypes.c_uint32,
                                              ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
        self.ole.CoCreateInstance.restype = ctypes.c_int32
        self.ole.CoTaskMemFree.argtypes = (ctypes.c_void_p,)
        self.ole.CoTaskMemFree.restype = None
        self.ole.CoUninitialize.argtypes = ()
        self.ole.CoUninitialize.restype = None
        _check(self.ole.CoInitializeEx(None, 2))  # COINIT_APARTMENTTHREADED
        try:
            clsid = GUID.parse("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")
            interface = GUID.parse("D57C7288-D4AD-4768-BE02-9D969532D960")
            _check(self.ole.CoCreateInstance(ctypes.byref(clsid), None, 1,
                                             ctypes.byref(interface), ctypes.byref(self.pointer)))
            flags = ctypes.c_uint32()
            _check(_invoke(self.pointer, 10, ctypes.c_int32, (ctypes.POINTER(ctypes.c_uint32),), ctypes.byref(flags)))
            # Pick folders, require filesystem paths, preserve the working directory.
            self.options = flags.value | 0x20 | 0x40 | 0x8 | 0x800
            _check(_invoke(self.pointer, 9, ctypes.c_int32, (ctypes.c_uint32,), self.options))
            _check(_invoke(self.pointer, 17, ctypes.c_int32, (ctypes.c_wchar_p,), "Select workspace folder"))
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def _show(self):
        user32 = ctypes.WinDLL("user32")
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        return _invoke(self.pointer, 3, ctypes.c_int32, (ctypes.c_void_p,), user32.GetForegroundWindow())

    def select(self):
        result = self._show()
        if result & 0xffffffff == 0x800704c7:  # User cancelled.
            return ""
        _check(result)
        item, value = ctypes.c_void_p(), ctypes.c_void_p()
        try:
            _check(_invoke(self.pointer, 20, ctypes.c_int32, (ctypes.POINTER(ctypes.c_void_p),), ctypes.byref(item)))
            _check(_invoke(item, 5, ctypes.c_int32, (ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)),
                           0x80058000, ctypes.byref(value)))  # SIGDN_FILESYSPATH
            return ctypes.wstring_at(value)
        finally:
            if value:
                self.ole.CoTaskMemFree(value)
            if item:
                _invoke(item, 2, ctypes.c_uint32)

    def __exit__(self, exc_type, exc_value, traceback):
        if self.pointer:
            _invoke(self.pointer, 2, ctypes.c_uint32)
            self.pointer = ctypes.c_void_p()
        self.ole.CoUninitialize()


def choose_folder():
    with _picker_lock:
        if os.name == "nt":
            with WindowsFolderDialog() as dialog:
                return dialog.select()
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        try:
            root.withdraw()
            root.attributes("-topmost", True)
            return filedialog.askdirectory(title="Select workspace folder")
        finally:
            root.destroy()
