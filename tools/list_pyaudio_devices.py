#!/usr/bin/env python3
"""List PyAudio input devices."""
import ctypes
try:
    ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(
        None, ctypes.c_char_p, ctypes.c_int,
        ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
    )
    def py_error_handler(f, l, fn, e, fmt): pass
    asound = ctypes.cdll.LoadLibrary("libasound.so.2")
    asound.snd_lib_error_set_handler(ERROR_HANDLER_FUNC(py_error_handler))
except: pass

import pyaudio

pa = pyaudio.PyAudio()
print("=== PyAudio Input Devices ===")
for i in range(pa.get_device_count()):
    info = pa.get_device_info_by_index(i)
    if info["maxInputChannels"] > 0:
        name = info["name"]
        inputs = info["maxInputChannels"]
        rate = info["defaultSampleRate"]
        print(f"Index {i}: {name}")
        print(f"         inputs={inputs}, rate={rate}")
pa.terminate()
