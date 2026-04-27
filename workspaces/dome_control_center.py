"""
dome_control_center.py — DOME 4.0 Unified Agent Control Center

A single-window GUI that replaces 6 terminal windows with a clean,
dark-mode control panel. Launches the exact same `python main.py`
commands as START_ALL_AGENTS.bat, but captures output into a pretty UI.

NO agent code is modified. This is a pure visual wrapper.

Usage:
    python dome_control_center.py
    (or double-click START_DOME.bat)
"""

import os
import sys
import subprocess
import threading
import signal
import time
from collections import deque
from datetime import datetime, timedelta

import customtkinter as ctk

# ─── Configuration ────────────────────────────────────────────────────────────

AGENTS = [
    {
        "id": "creator",
        "name": "Creator Agent",
        "desc": "Creates new MPOWR reservations from TripWorks webhooks",
        "cwd": r"C:\DOME_CORE\workspaces\MPWR_Reservation_Agent",
        "cmd": [sys.executable, "main.py"],
        "color": "#4CAF50",  # Green
    },
    {
        "id": "updater",
        "name": "Update / Cancel Agent",
        "desc": "Reschedules and cancels MPOWR reservations",
        "cwd": r"C:\DOME_CORE\workspaces\MPWR_Update_Cancel_Agent",
        "cmd": [sys.executable, "main.py"],
        "color": "#2196F3",  # Blue
    },
    {
        "id": "payment",
        "name": "Payment Agent",
        "desc": "Settles payments and checks deposits/overdue rentals",
        "cwd": r"C:\DOME_CORE\workspaces\MPWR_Payment_Agent",
        "cmd": [sys.executable, "main.py"],
        "color": "#FF9800",  # Orange
    },
    {
        "id": "waiver_recon",
        "name": "Waiver Recon",
        "desc": "Hourly MPOWR waiver scraper (Polaris signed counts)",
        "cwd": r"C:\DOME_CORE\workspaces\Waiver_Recon_Agent\backend",
        "cmd": [sys.executable, "main.py"],
        "color": "#9C27B0",  # Purple
    },
    {
        "id": "waiver_links",
        "name": "Waiver Link Scraper",
        "desc": "Scrapes waiver join links and QR codes from MPOWR",
        "cwd": r"C:\DOME_CORE\workspaces\Waiver_Recon_Agent\backend",
        "cmd": [sys.executable, "waiver_link_daemon.py"],
        "color": "#00BCD4",  # Cyan
    },
    {
        "id": "waiver_webhooks",
        "name": "Waiver Webhooks",
        "desc": "Processes TripWorks waiver.completed webhook events",
        "cwd": r"C:\DOME_CORE\workspaces\Waiver_Recon_Agent\backend",
        "cmd": [sys.executable, "waiver_webhook_daemon.py"],
        "color": "#E91E63",  # Pink
    },
]

MAX_LOG_LINES = 500  # Per agent — prune oldest when exceeded

# ─── Colors ───────────────────────────────────────────────────────────────────

BG_DARK = "#1a1a2e"
BG_CARD = "#16213e"
BG_CARD_SELECTED = "#0f3460"
BG_LOG = "#0d1117"
TEXT_PRIMARY = "#e6e6e6"
TEXT_SECONDARY = "#8b949e"
TEXT_SUCCESS = "#3fb950"
TEXT_ERROR = "#f85149"
TEXT_WARNING = "#d29922"
ACCENT = "#e94560"


# ─── Agent Process Manager ────────────────────────────────────────────────────

class AgentProcess:
    """Manages a single agent subprocess and its log buffer."""

    def __init__(self, config: dict):
        self.config = config
        self.process: subprocess.Popen | None = None
        self.log_buffer: deque = deque(maxlen=MAX_LOG_LINES)
        self.started_at: datetime | None = None
        self._reader_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._intentional_stop = False  # Track if stop was user-initiated
        self._crash_count = 0  # Track consecutive crashes for auto-restart protection
        self._last_crash_time: datetime | None = None

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    @property
    def uptime_str(self) -> str:
        if not self.started_at or not self.is_running:
            return ""
        delta = datetime.now() - self.started_at
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    @property
    def last_log_line(self) -> str:
        if self.log_buffer:
            line = self.log_buffer[-1]
            # Trim to 60 chars for sidebar preview
            return line[:60] + "…" if len(line) > 60 else line
        return "Waiting…"

    def start(self):
        if self.is_running:
            return

        self._stop_event.clear()
        self.log_buffer.clear()

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"  # Force line-buffered output
        env["PYTHONIOENCODING"] = "utf-8"  # Prevent cp1252 crashes on emoji characters

        try:
            # CREATE_NEW_PROCESS_GROUP allows clean termination on Windows
            self.process = subprocess.Popen(
                self.config["cmd"],
                cwd=self.config["cwd"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                bufsize=1,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            self.started_at = datetime.now()
            self._intentional_stop = False
            self.log_buffer.append(f"[Control Center] Agent started (PID: {self.process.pid})")

            # Start background thread to read stdout
            self._reader_thread = threading.Thread(
                target=self._read_stdout, daemon=True, name=f"reader-{self.config['id']}"
            )
            self._reader_thread.start()

        except Exception as e:
            self.log_buffer.append(f"[Control Center] ❌ Failed to start: {e}")
            self.process = None

    def stop(self):
        if not self.process:
            return

        self._stop_event.set()
        self._intentional_stop = True
        self.log_buffer.append("[Control Center] Stopping agent…")

        try:
            self.process.terminate()
            # Wait up to 5 seconds for graceful shutdown
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)

            self.log_buffer.append("[Control Center] Agent stopped.")
        except Exception as e:
            self.log_buffer.append(f"[Control Center] Error stopping: {e}")
        finally:
            self.process = None
            self.started_at = None

    def restart(self):
        self.log_buffer.append("[Control Center] 🔄 Restarting agent…")
        self.stop()
        time.sleep(0.5)
        self._intentional_stop = False
        self._crash_count = 0
        self.start()

    def check_and_auto_restart(self):
        """Check if process died unexpectedly and auto-restart it."""
        if self._intentional_stop:
            return  # User stopped it, don't auto-restart
        if self.process is None:
            return  # Never started
        if self.is_running:
            return  # Still alive

        # Process died unexpectedly
        exit_code = self.process.returncode
        self.process = None
        self.started_at = None

        # Reset crash counter if last crash was more than 5 minutes ago
        if self._last_crash_time and (datetime.now() - self._last_crash_time).total_seconds() > 300:
            self._crash_count = 0

        self._crash_count += 1
        self._last_crash_time = datetime.now()

        if self._crash_count >= 3:
            self.log_buffer.append(
                f"[Control Center] ⛔ Agent crashed {self._crash_count} times in 5 minutes. "
                f"Auto-restart disabled. Use the Restart button to try again."
            )
            return

        self.log_buffer.append(
            f"[Control Center] ⚠️ Agent exited unexpectedly (code: {exit_code}). "
            f"Auto-restarting in 5 seconds… (crash {self._crash_count}/3)"
        )
        time.sleep(5)
        if not self._intentional_stop:  # Check again in case user stopped during the wait
            self.start()

    def _read_stdout(self):
        """Background thread: reads stdout line-by-line into the log buffer."""
        try:
            for line in iter(self.process.stdout.readline, ""):
                if self._stop_event.is_set():
                    break
                stripped = line.rstrip("\n\r")
                if stripped:
                    self.log_buffer.append(stripped)
        except Exception:
            pass  # Process closed, thread exits naturally


# ─── GUI Application ──────────────────────────────────────────────────────────

class DOMEControlCenter(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window setup
        self.title("DOME 4.0 Control Center")
        self.geometry("1200x700")
        self.minsize(900, 500)
        self.configure(fg_color=BG_DARK)

        # Initialize agent processes
        self.agents: list[AgentProcess] = [AgentProcess(cfg) for cfg in AGENTS]
        self.selected_index = 0

        # Track UI elements for updates
        self._card_frames: list[ctk.CTkFrame] = []
        self._status_labels: list[ctk.CTkLabel] = []
        self._name_labels: list[ctk.CTkLabel] = []
        self._preview_labels: list[ctk.CTkLabel] = []
        self._uptime_labels: list[ctk.CTkLabel] = []
        self._card_buttons: list[dict] = []  # {"start": btn, "stop": btn, "restart": btn}
        self._shutting_down = False

        self._build_ui()

        # Bind window close to clean shutdown
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Start periodic UI refresh
        self._refresh_ui()

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=50)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="🚀  DOME 4.0 Control Center",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left", padx=20, pady=10)

        self._clock_label = ctk.CTkLabel(
            header, text="", font=ctk.CTkFont(size=13), text_color=TEXT_SECONDARY
        )
        self._clock_label.pack(side="right", padx=20)

        # ── Main Content (sidebar + log viewer) ──────────────────────────
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=8, pady=(4, 0))

        # Left sidebar
        self._sidebar = ctk.CTkScrollableFrame(
            content, width=320, fg_color=BG_DARK, corner_radius=8,
            scrollbar_button_color=BG_CARD, scrollbar_button_hover_color=BG_CARD_SELECTED
        )
        self._sidebar.pack(side="left", fill="y", padx=(0, 4), pady=0)

        for i, agent in enumerate(self.agents):
            self._build_agent_card(i, agent)

        # Right log panel
        log_container = ctk.CTkFrame(content, fg_color=BG_CARD, corner_radius=8)
        log_container.pack(side="right", fill="both", expand=True)

        # Log header
        self._log_header = ctk.CTkLabel(
            log_container,
            text=f"📋  {self.agents[0].config['name']}",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_PRIMARY, anchor="w",
        )
        self._log_header.pack(fill="x", padx=15, pady=(10, 5))

        self._log_desc = ctk.CTkLabel(
            log_container,
            text=self.agents[0].config["desc"],
            font=ctk.CTkFont(size=11),
            text_color=TEXT_SECONDARY, anchor="w",
        )
        self._log_desc.pack(fill="x", padx=15, pady=(0, 5))

        # Log text widget
        self._log_text = ctk.CTkTextbox(
            log_container, fg_color=BG_LOG, text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Consolas", size=12),
            corner_radius=6, border_width=0,
            state="disabled", wrap="word",
        )
        self._log_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Clear logs button in the log header
        self._clear_logs_btn = ctk.CTkButton(
            log_container, text="🗑 Clear", fg_color="#30363d", hover_color="#484f58",
            height=24, width=70, corner_radius=4, font=ctk.CTkFont(size=11),
            command=self._clear_selected_logs,
        )
        self._clear_logs_btn.place(relx=1.0, rely=0.0, x=-15, y=10, anchor="ne")

        # Copy logs button
        self._copy_logs_btn = ctk.CTkButton(
            log_container, text="📋 Copy", fg_color="#30363d", hover_color="#484f58",
            height=24, width=70, corner_radius=4, font=ctk.CTkFont(size=11),
            command=self._copy_logs,
        )
        self._copy_logs_btn.place(relx=1.0, rely=0.0, x=-95, y=10, anchor="ne")

        # Configure text tags for color coding
        self._log_text._textbox.tag_configure("success", foreground=TEXT_SUCCESS)
        self._log_text._textbox.tag_configure("error", foreground=TEXT_ERROR)
        self._log_text._textbox.tag_configure("warning", foreground=TEXT_WARNING)
        self._log_text._textbox.tag_configure("info", foreground=TEXT_PRIMARY)
        self._log_text._textbox.tag_configure("control", foreground="#58a6ff")

        # Bind copy shortcuts
        self._log_text.bind("<Control-c>", lambda e: self._copy_logs())
        self._log_text.bind("<Command-c>", lambda e: self._copy_logs())

        # ── Bottom Action Bar ────────────────────────────────────────────
        action_bar = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=50)
        action_bar.pack(fill="x", padx=0, pady=0)
        action_bar.pack_propagate(False)

        btn_style = {"height": 32, "corner_radius": 6, "font": ctk.CTkFont(size=13, weight="bold")}

        ctk.CTkButton(
            action_bar, text="▶  Start All", fg_color="#2ea043", hover_color="#3fb950",
            command=self._start_all, **btn_style
        ).pack(side="left", padx=(15, 5), pady=9)

        ctk.CTkButton(
            action_bar, text="⏹  Stop All", fg_color="#da3633", hover_color="#f85149",
            command=self._stop_all, **btn_style
        ).pack(side="left", padx=5, pady=9)

        ctk.CTkButton(
            action_bar, text="🔄  Restart Selected", fg_color="#1f6feb", hover_color="#388bfd",
            command=self._restart_selected, **btn_style
        ).pack(side="left", padx=5, pady=9)

        # Status summary
        self._status_summary = ctk.CTkLabel(
            action_bar, text="", font=ctk.CTkFont(size=12), text_color=TEXT_SECONDARY
        )
        self._status_summary.pack(side="right", padx=15)

    def _build_agent_card(self, index: int, agent: AgentProcess):
        """Build a single agent card in the sidebar."""
        cfg = agent.config

        card = ctk.CTkFrame(
            self._sidebar, fg_color=BG_CARD, corner_radius=8, height=90,
            border_width=1, border_color="#30363d"
        )
        card.pack(fill="x", padx=4, pady=3)
        card.pack_propagate(False)

        # Make the card clickable
        card.bind("<Button-1>", lambda e, i=index: self._select_agent(i))

        # Top row: status dot + name + uptime
        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=10, pady=(8, 2))

        status_label = ctk.CTkLabel(
            top_row, text="⚫", font=ctk.CTkFont(size=12), text_color=TEXT_SECONDARY, width=18
        )
        status_label.pack(side="left")

        name_label = ctk.CTkLabel(
            top_row, text=cfg["name"],
            font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT_PRIMARY, anchor="w",
        )
        name_label.pack(side="left", padx=(4, 0))
        name_label.bind("<Button-1>", lambda e, i=index: self._select_agent(i))

        uptime_label = ctk.CTkLabel(
            top_row, text="", font=ctk.CTkFont(size=10), text_color=TEXT_SECONDARY
        )
        uptime_label.pack(side="right")

        # Preview line
        preview_label = ctk.CTkLabel(
            card, text="Waiting…",
            font=ctk.CTkFont(family="Consolas", size=10), text_color=TEXT_SECONDARY,
            anchor="w", wraplength=280
        )
        preview_label.pack(fill="x", padx=14, pady=(0, 2))
        preview_label.bind("<Button-1>", lambda e, i=index: self._select_agent(i))

        # Button row
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(0, 6))

        btn_small = {"height": 22, "corner_radius": 4, "font": ctk.CTkFont(size=10), "width": 55}

        start_btn = ctk.CTkButton(
            btn_row, text="▶ Start", fg_color="#238636", hover_color="#2ea043",
            command=lambda i=index: self._start_agent(i), **btn_small
        )
        start_btn.pack(side="left", padx=(0, 3))

        stop_btn = ctk.CTkButton(
            btn_row, text="⏹ Stop", fg_color="#da3633", hover_color="#f85149",
            command=lambda i=index: self._stop_agent(i), **btn_small
        )
        stop_btn.pack(side="left", padx=(0, 3))

        restart_btn = ctk.CTkButton(
            btn_row, text="🔄 Restart", fg_color="#1f6feb", hover_color="#388bfd",
            command=lambda i=index: self._restart_agent(i), **btn_small
        )
        restart_btn.pack(side="left")

        # Store references
        self._card_frames.append(card)
        self._status_labels.append(status_label)
        self._name_labels.append(name_label)
        self._preview_labels.append(preview_label)
        self._uptime_labels.append(uptime_label)
        self._card_buttons.append({"start": start_btn, "stop": stop_btn, "restart": restart_btn})

    def _select_agent(self, index: int):
        """Switch the log viewer to the selected agent."""
        self.selected_index = index
        cfg = self.agents[index].config

        # Update log header
        self._log_header.configure(text=f"📋  {cfg['name']}")
        self._log_desc.configure(text=cfg["desc"])

        # Update card highlight
        for i, card in enumerate(self._card_frames):
            if i == index:
                card.configure(fg_color=BG_CARD_SELECTED, border_color=cfg["color"])
            else:
                card.configure(fg_color=BG_CARD, border_color="#30363d")

        # Force immediate log refresh
        self._update_log_viewer()

    def _update_log_viewer(self):
        """Refresh the log text widget with the selected agent's buffer."""
        agent = self.agents[self.selected_index]
        log_lines = list(agent.log_buffer)

        # Check if user has scrolled up (don't auto-scroll if so)
        try:
            yview = self._log_text._textbox.yview()
            at_bottom = yview[1] >= 0.98
        except Exception:
            at_bottom = True

        self._log_text.configure(state="normal")
        self._log_text._textbox.delete("1.0", "end")

        for line in log_lines:
            tag = self._classify_line(line)
            self._log_text._textbox.insert("end", line + "\n", tag)

        self._log_text.configure(state="disabled")

        if at_bottom:
            self._log_text._textbox.see("end")

    def _classify_line(self, line: str) -> str:
        """Determine color tag based on log content."""
        lower = line.lower()
        if "[control center]" in lower:
            return "control"
        if "❌" in line or "error" in lower or "failed" in lower or "critical" in lower:
            return "error"
        if "✅" in line or "success" in lower or "pushed" in lower or "created" in lower:
            return "success"
        if "⚠️" in line or "warning" in lower or "skipping" in lower or "retry" in lower:
            return "warning"
        return "info"

    def _refresh_ui(self):
        """Periodic UI refresh (every 1 second)."""
        if self._shutting_down:
            return

        # Update clock
        now = datetime.now()
        self._clock_label.configure(text=now.strftime("%I:%M:%S %p  •  %b %d, %Y"))

        # Update each agent card + check for crashes
        running_count = 0
        for i, agent in enumerate(self.agents):
            is_running = agent.is_running

            if is_running:
                running_count += 1
                self._status_labels[i].configure(text="🟢")
                self._uptime_labels[i].configure(text=agent.uptime_str)
            else:
                self._status_labels[i].configure(text="🔴")
                self._uptime_labels[i].configure(text="")

                # Auto-restart detection (runs in background thread to not block UI)
                if not agent._intentional_stop and agent.process is not None:
                    threading.Thread(target=agent.check_and_auto_restart, daemon=True).start()

            self._preview_labels[i].configure(text=agent.last_log_line)

        # Update status summary
        self._status_summary.configure(
            text=f"{running_count}/{len(self.agents)} agents running"
        )

        # Update log viewer
        self._update_log_viewer()

        # Schedule next refresh
        self.after(1000, self._refresh_ui)

    # ── Agent Controls ────────────────────────────────────────────────────

    def _start_agent(self, index: int):
        agent = self.agents[index]
        if not agent.is_running:
            threading.Thread(target=agent.start, daemon=True).start()

    def _stop_agent(self, index: int):
        agent = self.agents[index]
        if agent.is_running:
            threading.Thread(target=agent.stop, daemon=True).start()

    def _restart_agent(self, index: int):
        """Restart a specific agent by index (used by per-card restart buttons)."""
        agent = self.agents[index]
        threading.Thread(target=agent.restart, daemon=True).start()

    def _restart_selected(self):
        self._restart_agent(self.selected_index)

    def _clear_selected_logs(self):
        """Clear the log buffer for the currently selected agent."""
        agent = self.agents[self.selected_index]
        agent.log_buffer.clear()
        agent.log_buffer.append("[Control Center] Logs cleared.")
        self._update_log_viewer()

    def _copy_logs(self):
        """Copy logs from the text widget to the clipboard."""
        try:
            # Try to get selected text first
            selected = self._log_text._textbox.get("sel.first", "sel.last")
            text_to_copy = selected
        except Exception:
            # No selection, copy all
            text_to_copy = self._log_text.get("1.0", "end-1c")
        
        if text_to_copy:
            self.clipboard_clear()
            self.clipboard_append(text_to_copy)
            self.update() # Keep clipboard updated

    def _start_all(self):
        for i in range(len(self.agents)):
            self._start_agent(i)

    def _stop_all(self):
        threads = []
        for agent in self.agents:
            if agent.is_running:
                t = threading.Thread(target=agent.stop, daemon=True)
                t.start()
                threads.append(t)
        # Wait for all to finish
        for t in threads:
            t.join(timeout=10)

    def _on_close(self):
        """Clean shutdown: stop all agents then close the window."""
        self._shutting_down = True
        self._stop_all()
        self.destroy()


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = DOMEControlCenter()

    # Auto-start all agents on launch
    app.after(500, app._start_all)

    # Select first agent by default
    app._select_agent(0)

    app.mainloop()


if __name__ == "__main__":
    main()
