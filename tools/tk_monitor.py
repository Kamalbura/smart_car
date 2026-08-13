"""Tkinter monitor UI (skeleton).

This simple UI is intended for local debugging only. It does not modify
system services; it can be extended to talk to ui_backend.py via IPC or
HTTP once that grows more features.
"""
from __future__ import annotations

import tkinter as tk


def main() -> None:
    root = tk.Tk()
    root.title("Robot Stack Monitor (Skeleton)")

    label = tk.Label(root, text="AudioManager / Wakeword / STT / LLM / TTS / Vision / UART / Display", padx=20, pady=20)
    label.pack()

    status = tk.Label(root, text="Status: SIMULATION ONLY", fg="blue")
    status.pack(pady=10)

    quit_btn = tk.Button(root, text="Close", command=root.destroy)
    quit_btn.pack(pady=10)

    root.mainloop()


if __name__ == "__main__":
    main()
