#!/usr/bin/env python3
"""
Gemini Business API - Complete Management GUI
Full-featured desktop application with all web app features
"""
import customtkinter as ctk
import requests
import json
import base64
import threading
import os
import re
import time
from datetime import datetime, timedelta
from PIL import Image, ImageTk, ImageDraw, ImageFont
from io import BytesIO
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import webbrowser
import cv2

# Konfigurasi
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Modern Color Scheme
COLORS = {
    'primary': '#3B82F6',      # Modern blue
    'secondary': '#8B5CF6',    # Purple
    'success': '#10B981',      # Green
    'danger': '#EF4444',       # Red
    'warning': '#F59E0B',      # Orange
    'info': '#06B6D4',         # Cyan
    'dark': '#1E293B',         # Dark slate
    'darker': '#0F172A',       # Darker slate
    'light': '#F1F5F9',        # Light gray
    'border': '#334155',       # Border gray
    'text': '#E2E8F0',         # Text light
    'text_muted': '#94A3B8',   # Muted text
}

# Modern Icons (Unicode)
ICONS = {
    'dashboard': '◼',
    'chat': '◐',
    'image': '◈',
    'video': '▶',
    'gallery': '⊞',
    'accounts': '◉',
    'settings': '◎',
    'monitor': '◬',
    'logs': '≡',
    'logout': '◁',
    'refresh': '↻',
    'play': '▶',
    'pause': '▮▮',
    'stop': '■',
    'download': '⇩',
    'upload': '⇧',
    'open': '◫',
    'folder': '▤',
    'close': '✕',
    'add': '+',
    'edit': '✎',
    'delete': '✕',
    'save': '✓',
    'check': '✓',
    'error': '!',
    'info': 'i',
    'warning': '⚠',
}

# Modern Icons (Unicode)
ICONS = {
    'dashboard': '■',
    'chat': '◐',
    'image': '◈',
    'video': '▶',
    'gallery': '⊞',
    'accounts': '◉',
    'settings': '◎',
    'monitor': '◬',
    'logs': '≡',
    'logout': '◁',
    'refresh': '↻',
    'play': '▶',
    'pause': '▮▮',
    'stop': '■',
    'download': '⇩',
    'upload': '⇧',
    'open': '◫',
    'folder': '▤',
    'close': '✕',
    'add': '+',
    'edit': '✎',
    'delete': '✕',
    'save': '✓',
    'check': '✓',
    'error': '!',
    'info': 'i',
    'warning': '⚠',
}


class APIClient:
    """API Client untuk berkomunikasi dengan server"""
    
    def __init__(self, base_url):
        self.base_url = base_url
        self.session = requests.Session()
        self.logged_in = False
        
    def login(self, admin_key):
        """Login dengan ADMIN_KEY"""
        try:
            response = self.session.post(
                f"{self.base_url}/login",
                data={"admin_key": admin_key},
                timeout=10
            )
            response.raise_for_status()
            self.logged_in = True
            return True, "Login successful"
        except Exception as e:
            self.logged_in = False
            return False, str(e)
    
    def logout(self):
        """Logout"""
        try:
            self.session.post(f"{self.base_url}/logout")
        except:
            pass
        self.logged_in = False
    
    # Account Management
    def get_accounts(self):
        """Get all accounts"""
        response = self.session.get(f"{self.base_url}/admin/accounts")
        response.raise_for_status()
        return response.json()
    
    def add_account(self, account_data):
        """Add new account"""
        response = self.session.post(
            f"{self.base_url}/admin/accounts",
            json=account_data
        )
        response.raise_for_status()
        return response.json()
    
    def update_account(self, account_id, account_data):
        """Update account"""
        response = self.session.put(
            f"{self.base_url}/admin/accounts/{account_id}",
            json=account_data
        )
        response.raise_for_status()
        return response.json()
    
    def delete_account(self, account_id):
        """Delete account"""
        response = self.session.delete(
            f"{self.base_url}/admin/accounts/{account_id}"
        )
        response.raise_for_status()
        return response.json()
    
    # Settings Management
    def get_settings(self):
        """Get system settings"""
        response = self.session.get(f"{self.base_url}/admin/settings")
        response.raise_for_status()
        return response.json()
    
    def update_settings(self, settings_data):
        """Update system settings"""
        response = self.session.put(
            f"{self.base_url}/admin/settings",
            json=settings_data
        )
        response.raise_for_status()
        return response.json()
    
    # Auto-Register
    def start_auto_register(self, count):
        """Start auto-register task - Generator.Email only"""
        data = {
            "count": count
        }
        
        response = self.session.post(
            f"{self.base_url}/admin/register/start",
            json=data
        )
        response.raise_for_status()
        return response.json()
    
    def get_register_status(self):
        """Get current register task status"""
        response = self.session.get(f"{self.base_url}/admin/register/current")
        response.raise_for_status()
        return response.json()
    
    def cancel_register_task(self, task_id, reason="cancelled"):
        """Cancel register task"""
        response = self.session.post(
            f"{self.base_url}/admin/register/cancel/{task_id}",
            json={"reason": reason}
        )
        response.raise_for_status()
        return response.json()
    
    # Monitoring
    def get_stats(self, time_range="24h"):
        """Get statistics"""
        response = self.session.get(
            f"{self.base_url}/admin/stats",
            params={"time_range": time_range}
        )
        response.raise_for_status()
        return response.json()
    
    def get_health(self):
        """Get system health"""
        response = self.session.get(f"{self.base_url}/admin/health")
        response.raise_for_status()
        return response.json()
    
    # Logs
    def get_logs(self, limit=100, skip=0):
        """Get logs"""
        response = self.session.get(
            f"{self.base_url}/admin/log",
            params={"limit": limit, "skip": skip}
        )
        response.raise_for_status()
        return response.json()
    
    # AI Operations
    def chat_completion(self, model, messages, stream=False):
        """Chat completion"""
        response = self.session.post(
            f"{self.base_url}/v1/chat/completions",
            json={
                "model": model,
                "messages": messages,
                "stream": stream
            },
            timeout=120
        )
        response.raise_for_status()
        return response.json()


class LoginWindow(ctk.CTkToplevel):
    """Login window"""
    
    def __init__(self, parent, api_client, on_success):
        super().__init__(parent)
        
        self.api_client = api_client
        self.on_success = on_success
        
        self.title("Login - Gemini Business2API")
        self.geometry("400x300")
        self.resizable(False, False)
        
        # Center window
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (400 // 2)
        y = (self.winfo_screenheight() // 2) - (300 // 2)
        self.geometry(f"+{x}+{y}")
        
        # Make modal
        self.transient(parent)
        self.grab_set()
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup UI"""
        # Logo
        title = ctk.CTkLabel(
            self,
            text="🤖 Msverify",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title.pack(pady=(40, 10))
        
        subtitle = ctk.CTkLabel(
            self,
            text="Management Console Login",
            font=ctk.CTkFont(size=14),
            text_color="gray"
        )
        subtitle.pack(pady=(0, 30))
        
        # Admin key input
        ctk.CTkLabel(
            self,
            text="Admin Key:",
            font=ctk.CTkFont(size=13)
        ).pack(pady=(0, 5))
        
        self.admin_key_entry = ctk.CTkEntry(
            self,
            width=300,
            height=40,
            placeholder_text="Enter your admin key",
            show="*"
        )
        self.admin_key_entry.pack(pady=(0, 20))
        self.admin_key_entry.bind("<Return>", lambda e: self.do_login())
        
        # Login button
        self.login_btn = ctk.CTkButton(
            self,
            text="Login",
            width=300,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.do_login
        )
        self.login_btn.pack(pady=(0, 10))
        
        # Status label
        self.status_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="red"
        )
        self.status_label.pack(pady=(10, 0))
        
        self.admin_key_entry.focus()
        
    def do_login(self):
        """Perform login"""
        admin_key = self.admin_key_entry.get().strip()
        
        if not admin_key:
            self.status_label.configure(text="Please enter admin key")
            return
        
        self.login_btn.configure(state="disabled", text="Logging in...")
        self.status_label.configure(text="Connecting...", text_color="gray")
        
        def login_thread():
            success, message = self.api_client.login(admin_key)
            
            self.after(0, lambda: self.handle_login_result(success, message))
        
        threading.Thread(target=login_thread, daemon=True).start()
    
    def handle_login_result(self, success, message):
        """Handle login result"""
        if success:
            self.destroy()
            self.on_success()
        else:
            self.login_btn.configure(state="normal", text="Login")
            self.status_label.configure(
                text=f"Login failed: {message}",
                text_color="red"
            )


class VideoPlayerWindow(ctk.CTkToplevel):
    """Video player window"""
    
    def __init__(self, parent, video_path):
        super().__init__(parent)
        
        self.video_path = video_path
        self.video_name = os.path.basename(video_path)
        self.is_playing = False
        self.is_paused = False
        self.cap = None
        self.current_frame = 0
        self.total_frames = 0
        self.fps = 30
        self.play_thread = None
        
        # Window config
        self.title(f"Video Player - {self.video_name}")
        self.geometry("900x650")
        
        # Make it modal
        self.transient(parent)
        self.grab_set()
        
        self.setup_ui()
        self.load_video()
        
    def setup_ui(self):
        """Setup UI"""
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Video display area
        self.video_label = ctk.CTkLabel(
            self,
            text="Loading video...",
            font=ctk.CTkFont(size=14)
        )
        self.video_label.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        
        # Controls frame
        controls = ctk.CTkFrame(self)
        controls.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 20))
        controls.grid_columnconfigure(1, weight=1)
        
        # Play/Pause button
        self.play_btn = ctk.CTkButton(
            controls,
            text=f"{ICONS['play']}  Play",
            width=100,
            command=self.toggle_play,
            font=ctk.CTkFont(size=16)
        )
        self.play_btn.grid(row=0, column=0, padx=5, pady=10)
        
        # Progress bar
        self.progress = ctk.CTkSlider(
            controls,
            from_=0,
            to=100,
            command=self.on_progress_change
        )
        self.progress.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        self.progress.set(0)
        
        # Time label
        self.time_label = ctk.CTkLabel(
            controls,
            text="00:00 / 00:00",
            font=ctk.CTkFont(size=12)
        )
        self.time_label.grid(row=0, column=2, padx=10, pady=10)
        
        # Close button
        close_btn = ctk.CTkButton(
            controls,
            text=f"{ICONS['close']}  Close",
            width=80,
            command=self.close_player,
            fg_color="red"
        )
        close_btn.grid(row=0, column=3, padx=5, pady=10)
        
    def load_video(self):
        """Load video file"""
        try:
            self.cap = cv2.VideoCapture(self.video_path)
            
            if not self.cap.isOpened():
                raise Exception("Cannot open video file")
            
            self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            
            # Update progress bar
            self.progress.configure(to=self.total_frames)
            
            # Show first frame
            self.show_frame(0)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load video: {e}")
            self.destroy()
    
    def show_frame(self, frame_number):
        """Show specific frame"""
        try:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = self.cap.read()
            
            if ret:
                # Convert BGR to RGB
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Resize to fit display (max 860x500)
                h, w = frame.shape[:2]
                max_w, max_h = 860, 500
                
                if w > max_w or h > max_h:
                    scale = min(max_w/w, max_h/h)
                    new_w, new_h = int(w*scale), int(h*scale)
                    frame = cv2.resize(frame, (new_w, new_h))
                
                # Convert to PhotoImage
                img = Image.fromarray(frame)
                photo = ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height))
                
                self.video_label.configure(image=photo, text="")
                self.video_label.image = photo
                
                self.current_frame = frame_number
                self.update_time_label()
                self.progress.set(frame_number)
                
        except Exception as e:
            print(f"Error showing frame: {e}")
    
    def toggle_play(self):
        """Toggle play/pause"""
        if self.is_playing:
            self.pause_video()
        else:
            self.play_video()
    
    def play_video(self):
        """Play video"""
        if not self.is_playing:
            self.is_playing = True
            self.is_paused = False
            self.play_btn.configure(text=f"{ICONS['pause']}  Pause")
            
            # Start play thread
            self.play_thread = threading.Thread(target=self._play_loop, daemon=True)
            self.play_thread.start()
    
    def pause_video(self):
        """Pause video"""
        self.is_playing = False
        self.is_paused = True
        self.play_btn.configure(text=f"{ICONS['play']}  Play")
    
    def _play_loop(self):
        """Play loop in background thread"""
        while self.is_playing and self.current_frame < self.total_frames - 1:
            frame_delay = 1.0 / self.fps if self.fps > 0 else 0.033
            
            self.after(0, lambda: self.show_frame(self.current_frame + 1))
            time.sleep(frame_delay)
        
        # End of video
        if self.current_frame >= self.total_frames - 1:
            self.after(0, lambda: self.play_btn.configure(text="▶ Replay"))
            self.is_playing = False
    
    def on_progress_change(self, value):
        """Handle progress bar change"""
        if not self.is_playing:
            frame_num = int(value)
            self.show_frame(frame_num)
    
    def update_time_label(self):
        """Update time label"""
        if self.fps > 0:
            current_time = self.current_frame / self.fps
            total_time = self.total_frames / self.fps
            
            current_str = time.strftime("%M:%S", time.gmtime(current_time))
            total_str = time.strftime("%M:%S", time.gmtime(total_time))
            
            self.time_label.configure(text=f"{current_str} / {total_str}")
    
    def close_player(self):
        """Close player"""
        self.is_playing = False
        if self.cap:
            self.cap.release()
        self.destroy()
    
    def destroy(self):
        """Override destroy to cleanup"""
        self.is_playing = False
        if self.cap:
            self.cap.release()
        super().destroy()


class GeminiManagementApp(ctk.CTk):
    """Main application"""
    
    def __init__(self):
        super().__init__()
        
        # Window config
        self.title("Msverify API - Management Console")
        self.geometry("1600x900")
        
        # API Client
        self.api_client = APIClient("http://localhost:7860")
        
        # Variables
        self.current_image = None
        self.current_video_url = None
        self.chat_history = []
        self.accounts_data = []
        self.settings_data = {}
        self.stats_data = {}
        
        # Setup UI
        self.setup_ui()
        
        # Show login
        self.after(100, self.show_login)
        
    def show_login(self):
        """Show login window"""
        login_window = LoginWindow(self, self.api_client, self.on_login_success)
        
    def on_login_success(self):
        """Called when login successful"""
        self.load_initial_data()
        
    def load_initial_data(self):
        """Load initial data after login"""
        threading.Thread(target=self._load_initial_data_thread, daemon=True).start()
        
    def _load_initial_data_thread(self):
        """Load data in background"""
        try:
            # Load accounts
            accounts = self.api_client.get_accounts()
            self.after(0, lambda: self.update_accounts_list(accounts))
            
            # Load stats
            stats = self.api_client.get_stats()
            self.after(0, lambda: self.update_dashboard_stats(stats))
            
        except Exception as e:
            print(f"Error loading data: {e}")
    
    def setup_ui(self):
        """Setup main UI"""
        # Configure grid
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # Sidebar
        self.setup_sidebar()
        
        # Main content
        self.setup_main_content()
        
    def setup_sidebar(self):
        """Setup sidebar"""
        sidebar = ctk.CTkFrame(self, width=250, corner_radius=0, fg_color=COLORS['darker'])
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(10, weight=1)
        
        # Logo with modern styling
        logo_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo_frame.grid(row=0, column=0, padx=20, pady=(25, 10))
        
        title = ctk.CTkLabel(
            logo_frame,
            text="▲ Msverify AI",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=COLORS['primary']
        )
        title.pack()
        
        subtitle = ctk.CTkLabel(
            logo_frame,
            text="Management Console",
            font=ctk.CTkFont(size=11),
            text_color=COLORS['text_muted']
        )
        subtitle.pack(pady=(5, 0))
        
        # Separator line
        separator = ctk.CTkFrame(sidebar, height=1, fg_color=COLORS['border'])
        separator.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 15))
        
        # Navigation buttons
        nav_buttons = [
            (f"{ICONS['dashboard']}  Dashboard", "dashboard"),
            (f"{ICONS['chat']}  Chat", "chat"),
            (f"{ICONS['image']}  Generate Image", "image"),
            (f"{ICONS['video']}  Generate Video", "video"),
            (f"{ICONS['gallery']}  Gallery", "gallery"),
            (f"{ICONS['accounts']}  Accounts", "accounts"),
            (f"{ICONS['settings']}  Settings", "settings"),
            (f"{ICONS['monitor']}  Monitor", "monitor"),
            (f"{ICONS['logs']}  Logs", "logs"),
        ]
        
        self.nav_buttons = {}
        for idx, (text, tab_id) in enumerate(nav_buttons):
            btn = ctk.CTkButton(
                sidebar,
                text=text,
                command=lambda t=tab_id: self.show_tab(t),
                height=44,
                font=ctk.CTkFont(size=13, weight="normal"),
                anchor="w",
                fg_color="transparent",
                hover_color=COLORS['dark'],
                corner_radius=10,
                border_spacing=10
            )
            btn.grid(row=idx+2, column=0, padx=12, pady=3, sticky="ew")
            self.nav_buttons[tab_id] = btn
        
        # Logout button with modern styling
        logout_btn = ctk.CTkButton(
            sidebar,
            text=f"{ICONS['logout']}  Logout",
            command=self.do_logout,
            height=42,
            font=ctk.CTkFont(size=13),
            fg_color="transparent",
            hover_color=COLORS['danger'],
            border_width=1,
            border_color=COLORS['border'],
            corner_radius=10,
            text_color=COLORS['danger']
        )
        logout_btn.grid(row=11, column=0, padx=12, pady=(15, 25), sticky="ew")
        
    def setup_main_content(self):
        """Setup main content area"""
        self.main_container = ctk.CTkFrame(self, corner_radius=0)
        self.main_container.grid(row=0, column=1, sticky="nsew")
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)
        
        # Create all tabs
        self.dashboard_frame = self.create_dashboard_tab()
        self.chat_frame = self.create_chat_tab()
        self.image_frame = self.create_image_tab()
        self.video_frame = self.create_video_tab()
        self.gallery_frame = self.create_gallery_tab()
        self.accounts_frame = self.create_accounts_tab()
        self.settings_frame = self.create_settings_tab()
        self.monitor_frame = self.create_monitor_tab()
        self.logs_frame = self.create_logs_tab()
        
        # Show dashboard by default
        self.show_tab("dashboard")
        
    def create_dashboard_tab(self):
        """Create dashboard tab"""
        frame = ctk.CTkFrame(self.main_container)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        # Header
        header = ctk.CTkFrame(frame, height=70, corner_radius=0, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header.grid_columnconfigure(0, weight=1)
        
        title = ctk.CTkLabel(
            header,
            text="📊 Dashboard",
            font=ctk.CTkFont(size=28, weight="bold")
        )
        title.grid(row=0, column=0, padx=30, pady=20, sticky="w")
        
        refresh_btn = ctk.CTkButton(
            header,
            text=f"{ICONS['refresh']}  Refresh",
            width=120,
            height=35,
            command=self.refresh_dashboard,
            fg_color="transparent",
            border_width=2
        )
        refresh_btn.grid(row=0, column=1, padx=30, pady=20)
        
        # Stats container
        stats_container = ctk.CTkScrollableFrame(frame)
        stats_container.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        stats_container.grid_columnconfigure((0, 1, 2, 3), weight=1)
        
        # Stats cards
        self.stats_cards = {}
        
        stats_info = [
            ("total_accounts", "Total Accounts", "👥", "#2196F3"),
            ("active_accounts", "Active Accounts", "✅", "#4CAF50"),
            ("failed_accounts", "Failed Accounts", "❌", "#F44336"),
            ("total_requests", "Total Requests", "📊", "#9C27B0"),
        ]
        
        for idx, (key, label, emoji, color) in enumerate(stats_info):
            card = self.create_stat_card(stats_container, emoji, label, "0", color)
            card.grid(row=0, column=idx, padx=10, pady=10, sticky="nsew")
            self.stats_cards[key] = card
        
        # Recent activity
        activity_label = ctk.CTkLabel(
            stats_container,
            text="📈 Recent Activity",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w"
        )
        activity_label.grid(row=1, column=0, columnspan=4, padx=10, pady=(20, 10), sticky="w")
        
        self.activity_text = ctk.CTkTextbox(
            stats_container,
            height=300,
            font=ctk.CTkFont(size=12)
        )
        self.activity_text.grid(row=2, column=0, columnspan=4, padx=10, pady=10, sticky="nsew")
        
        return frame
    
    def create_stat_card(self, parent, emoji, title, value, color):
        """Create a stat card"""
        card = ctk.CTkFrame(parent, fg_color=color, corner_radius=10)
        card.grid_columnconfigure(0, weight=1)
        
        emoji_label = ctk.CTkLabel(
            card,
            text=emoji,
            font=ctk.CTkFont(size=40)
        )
        emoji_label.grid(row=0, column=0, padx=20, pady=(20, 5))
        
        value_label = ctk.CTkLabel(
            card,
            text=value,
            font=ctk.CTkFont(size=32, weight="bold")
        )
        value_label.grid(row=1, column=0, padx=20, pady=5)
        
        title_label = ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=13)
        )
        title_label.grid(row=2, column=0, padx=20, pady=(5, 20))
        
        card.value_label = value_label
        return card
        
    def create_chat_tab(self):
        """Create chat tab"""
        frame = ctk.CTkFrame(self.main_container)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        # Header
        header = ctk.CTkFrame(frame, height=60, corner_radius=0, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        
        title = ctk.CTkLabel(
            header,
            text="💬 AI Chat",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title.grid(row=0, column=0, padx=30, pady=15, sticky="w")
        
        clear_btn = ctk.CTkButton(
            header,
            text="🗑️ Clear",
            width=100,
            command=self.clear_chat,
            fg_color="transparent",
            border_width=2
        )
        clear_btn.grid(row=0, column=1, padx=30, pady=15)
        
        # Chat display
        chat_container = ctk.CTkFrame(frame)
        chat_container.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))
        chat_container.grid_rowconfigure(0, weight=1)
        chat_container.grid_columnconfigure(0, weight=1)
        
        self.chat_display = ctk.CTkTextbox(
            chat_container,
            font=ctk.CTkFont(size=13),
            wrap="word"
        )
        self.chat_display.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        # Input area
        input_frame = ctk.CTkFrame(frame, height=120)
        input_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))
        input_frame.grid_columnconfigure(0, weight=1)
        
        self.chat_input = ctk.CTkTextbox(
            input_frame,
            height=80,
            font=ctk.CTkFont(size=13)
        )
        self.chat_input.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.chat_input.bind("<Control-Return>", lambda e: self.send_chat())
        
        send_btn = ctk.CTkButton(
            input_frame,
            text="Send",
            command=self.send_chat,
            height=80,
            width=150,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        send_btn.grid(row=0, column=1, padx=10, pady=10)
        
        return frame
    
    def create_image_tab(self):
        """Create image generation tab"""
        frame = ctk.CTkFrame(self.main_container)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        # Header
        header = ctk.CTkFrame(frame, height=60, corner_radius=0, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        
        title = ctk.CTkLabel(
            header,
            text="🎨 Image Generation",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title.grid(row=0, column=0, padx=30, pady=15, sticky="w")
        
        # Content
        content = ctk.CTkFrame(frame)
        content.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(1, weight=1)
        
        # Left panel
        left_panel = ctk.CTkFrame(content)
        left_panel.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(10, 5), pady=10)
        
        ctk.CTkLabel(
            left_panel,
            text="Enter your prompt:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(padx=20, pady=(20, 10), anchor="w")
        
        self.image_prompt = ctk.CTkTextbox(
            left_panel,
            height=200,
            font=ctk.CTkFont(size=13)
        )
        self.image_prompt.pack(padx=20, pady=10, fill="both", expand=True)
        
        self.image_generate_btn = ctk.CTkButton(
            left_panel,
            text=f"{ICONS['image']}  Generate Image",
            command=self.generate_image,
            height=50,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=COLORS['primary']
        )
        self.image_generate_btn.pack(padx=20, pady=20, fill="x")
        
        self.image_loading_label = ctk.CTkLabel(
            left_panel,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.image_loading_label.pack(padx=20, pady=(0, 10))
        
        # Right panel
        right_panel = ctk.CTkFrame(content)
        right_panel.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(5, 10), pady=10)
        right_panel.grid_rowconfigure(1, weight=1)
        right_panel.grid_columnconfigure(0, weight=1)
        
        preview_header = ctk.CTkFrame(right_panel, fg_color="transparent")
        preview_header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        preview_header.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(
            preview_header,
            text="Preview:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, sticky="w")
        
        save_btn = ctk.CTkButton(
            preview_header,
            text=f"{ICONS['save']}  Save",
            width=100,
            command=self.save_image,
            fg_color="transparent",
            border_width=2
        )
        save_btn.grid(row=0, column=1, padx=5)
        
        folder_btn = ctk.CTkButton(
            preview_header,
            text=f"{ICONS['folder']}  Folder",
            width=100,
            command=self.open_images_folder,
            fg_color="transparent",
            border_width=2
        )
        folder_btn.grid(row=0, column=2, padx=5)
        
        self.image_preview = ctk.CTkLabel(
            right_panel,
            text="Generated image will appear here",
            font=ctk.CTkFont(size=14),
            text_color="gray"
        )
        self.image_preview.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        
        return frame
    
    def create_video_tab(self):
        """Create video generation tab"""
        frame = ctk.CTkFrame(self.main_container)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        # Header
        header = ctk.CTkFrame(frame, height=60, corner_radius=0, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        
        title = ctk.CTkLabel(
            header,
            text="🎬 Video Generation",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title.grid(row=0, column=0, padx=30, pady=15, sticky="w")
        
        # Content
        content = ctk.CTkFrame(frame)
        content.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(1, weight=1)
        
        # Left panel
        left_panel = ctk.CTkFrame(content)
        left_panel.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(10, 5), pady=10)
        
        ctk.CTkLabel(
            left_panel,
            text="Enter your prompt:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(padx=20, pady=(20, 10), anchor="w")
        
        self.video_prompt = ctk.CTkTextbox(
            left_panel,
            height=200,
            font=ctk.CTkFont(size=13)
        )
        self.video_prompt.pack(padx=20, pady=10, fill="both", expand=True)
        
        self.video_generate_btn = ctk.CTkButton(
            left_panel,
            text=f"{ICONS['video']}  Generate Video",
            command=self.generate_video,
            height=50,
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.video_generate_btn.pack(padx=20, pady=20, fill="x")
        
        self.video_loading_label = ctk.CTkLabel(
            left_panel,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.video_loading_label.pack(padx=20, pady=(0, 10))
        
        # Right panel
        right_panel = ctk.CTkFrame(content)
        right_panel.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(5, 10), pady=10)
        right_panel.grid_rowconfigure(1, weight=1)
        right_panel.grid_columnconfigure(0, weight=1)
        
        preview_header = ctk.CTkFrame(right_panel, fg_color="transparent")
        preview_header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        preview_header.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(
            preview_header,
            text="Video Preview:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, sticky="w")
        
        open_btn = ctk.CTkButton(
            preview_header,
            text=f"{ICONS['play']}  Play",
            width=100,
            command=self.open_video,
            fg_color="transparent",
            border_width=2
        )
        open_btn.grid(row=0, column=1, padx=5)
        
        folder_btn = ctk.CTkButton(
            preview_header,
            text=f"{ICONS['folder']}  Folder",
            width=120,
            command=self.open_videos_folder,
            fg_color="transparent",
            border_width=2
        )
        folder_btn.grid(row=0, column=2, padx=5)
        
        video_preview_container = ctk.CTkFrame(right_panel)
        video_preview_container.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        video_preview_container.grid_rowconfigure(0, weight=1)
        video_preview_container.grid_columnconfigure(0, weight=1)
        
        self.video_thumbnail = ctk.CTkLabel(
            video_preview_container,
            text="🎬 Video preview will appear here",
            font=ctk.CTkFont(size=14),
            text_color="gray"
        )
        self.video_thumbnail.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.video_thumbnail.bind("<Button-1>", lambda e: self.open_video())
        
        self.video_info = ctk.CTkTextbox(
            video_preview_container,
            height=100,
            font=ctk.CTkFont(size=11),
            wrap="word"
        )
        self.video_info.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.video_info.insert("1.0", "Video info will appear here")
        self.video_info.configure(state="disabled")
        
        return frame
    
    def create_gallery_tab(self):
        """Create gallery tab to view generated images and videos"""
        frame = ctk.CTkFrame(self.main_container)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        # Header
        header = ctk.CTkFrame(frame, height=70, corner_radius=0, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header.grid_columnconfigure(0, weight=1)
        
        title = ctk.CTkLabel(
            header,
            text="🖼️ Media Gallery",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title.grid(row=0, column=0, sticky="w", padx=30, pady=(20, 0))
        
        subtitle = ctk.CTkLabel(
            header,
            text="Browse generated images and videos",
            font=ctk.CTkFont(size=13),
            text_color="gray"
        )
        subtitle.grid(row=1, column=0, sticky="w", padx=30, pady=(5, 10))
        
        refresh_btn = ctk.CTkButton(
            header,
            text=f"{ICONS['refresh']}  Refresh",
            width=120,
            command=self.refresh_gallery,
            fg_color="transparent",
            border_width=2
        )
        refresh_btn.grid(row=0, column=1, rowspan=2, padx=30, pady=20)
        
        # Content area
        content = ctk.CTkFrame(frame)
        content.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        content.grid_rowconfigure(1, weight=1)
        content.grid_columnconfigure(0, weight=1)
        
        # Tab selector
        tab_frame = ctk.CTkFrame(content, fg_color="transparent")
        tab_frame.grid(row=0, column=0, sticky="ew", padx=30, pady=(10, 0))
        
        self.gallery_tab_var = tk.StringVar(value="Images")
        
        images_btn = ctk.CTkSegmentedButton(
            tab_frame,
            values=["Images", "Videos"],
            command=self.on_gallery_tab_change,
            variable=self.gallery_tab_var
        )
        images_btn.pack(side="left")
        
        # Gallery container with scrollable frame
        gallery_container = ctk.CTkScrollableFrame(content, fg_color="transparent")
        gallery_container.grid(row=1, column=0, sticky="nsew", padx=20, pady=20)
        
        self.gallery_grid = gallery_container
        
        # Status label
        self.gallery_status = ctk.CTkLabel(
            content,
            text="Loading media files...",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.gallery_status.grid(row=2, column=0, padx=30, pady=(0, 20))
        
        # Initial load
        self.after(100, self.refresh_gallery)
        
        return frame
    
    def create_accounts_tab(self):
        """Create accounts management tab"""
        frame = ctk.CTkFrame(self.main_container)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        # Header
        header = ctk.CTkFrame(frame, height=60, corner_radius=0, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        
        title = ctk.CTkLabel(
            header,
            text="👥 Account Management",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title.grid(row=0, column=0, padx=30, pady=15, sticky="w")
        
        button_frame = ctk.CTkFrame(header, fg_color="transparent")
        button_frame.grid(row=0, column=1, padx=30, pady=15)
        
        add_btn = ctk.CTkButton(
            button_frame,
            text="➕ Add Account",
            width=140,
            command=self.show_add_account_dialog,
            fg_color="#4CAF50"
        )
        add_btn.pack(side="left", padx=5)
        
        refresh_btn = ctk.CTkButton(
            button_frame,
            text=f"{ICONS['refresh']}  Refresh",
            width=100,
            command=self.refresh_accounts,
            fg_color="transparent",
            border_width=2
        )
        refresh_btn.pack(side="left", padx=5)
        
        # Accounts list container
        list_container = ctk.CTkFrame(frame)
        list_container.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        list_container.grid_rowconfigure(0, weight=1)
        list_container.grid_columnconfigure(0, weight=1)
        
        self.accounts_list = ctk.CTkScrollableFrame(list_container)
        self.accounts_list.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.accounts_list.grid_columnconfigure(0, weight=1)
        
        # Table header
        header_frame = ctk.CTkFrame(self.accounts_list, fg_color="#1f538d")
        header_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=(0, 5))
        header_frame.grid_columnconfigure(1, weight=1)
        
        headers = [("Email", 1), ("Status", 0), ("Type", 0), ("Actions", 0)]
        for idx, (text, weight) in enumerate(headers):
            lbl = ctk.CTkLabel(
                header_frame,
                text=text,
                font=ctk.CTkFont(size=13, weight="bold")
            )
            lbl.grid(row=0, column=idx, padx=10, pady=10, sticky="w")
            if weight:
                header_frame.grid_columnconfigure(idx, weight=weight)
        
        return frame
    
    def create_settings_tab(self):
        """Create settings tab"""
        frame = ctk.CTkFrame(self.main_container)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        # Header
        header = ctk.CTkFrame(frame, height=60, corner_radius=0, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        
        title = ctk.CTkLabel(
            header,
            text="⚙️ Settings",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title.grid(row=0, column=0, padx=30, pady=15, sticky="w")
        
        button_frame = ctk.CTkFrame(header, fg_color="transparent")
        button_frame.grid(row=0, column=1, padx=30, pady=15)
        
        load_btn = ctk.CTkButton(
            button_frame,
            text=f"{ICONS['refresh']}  Load Settings",
            width=140,
            command=self.load_settings,
            fg_color="transparent",
            border_width=2
        )
        load_btn.pack(side="left", padx=5)
        
        save_btn = ctk.CTkButton(
            button_frame,
            text=f"{ICONS['save']}  Save Settings",
            width=140,
            command=self.save_settings,
            fg_color="#4CAF50"
        )
        save_btn.pack(side="left", padx=5)
        
        # Settings container
        settings_container = ctk.CTkScrollableFrame(frame)
        settings_container.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        settings_container.grid_columnconfigure(0, weight=1)
        
        self.settings_widgets = {}
        
        # Dasar (Basic)
        self.create_settings_section(
            settings_container,
            "📋 DASAR",
            [
                ("api_key", "Kunci API", "entry", ""),
                ("base_url", "Alamat Dasar", "entry", "http://127.0.0.1:7890"),
                ("proxy_for_auth", "Agen Operasi Akun", "entry", ""),
                ("proxy_for_chat", "Agen Operasi Internet", "entry", ""),
                ("browser_engine", "Browser Engine", "option", ["DP - Mendukung browser tanpa header", "UC - Undetected Chrome"]),
                ("browser_headless", "Browser tanpa header", "switch", False),
            ],
            0
        )
        
        # Pendaftaran/Pembaruan Otomatis
        self.create_settings_section(
            settings_container,
            "📝 PENDAFTARAN/PEMBARUAN OTOMATIS",
            [
                ("register_default_count", "Jumlah pendaftaran default", "entry", "1"),
                ("refresh_window_hours", "Refresh Window (hours)", "entry", "24"),
            ],
            1
        )
        
        # Generator.Email Domain Management
        self.create_generator_email_section(settings_container, 2)
        
        # Image Generation
        self.create_settings_section(
            settings_container,
            "🎨 GAMBAR DIHASILKAN",
            [
                ("image_enabled", "Mengaktifkan gambar", "switch", True),
                ("image_output_format", "Format output", "option", ["Pengeditan Base64", "URL label video HTML", "Label video Markdown"]),
                ("image_supported_models", "Model yang didukung", "text", "gemini-imagen\ngemini-2.0-flash-exp\ngemini-exp-1206"),
            ],
            4
        )
        
        # Video Generation
        self.create_settings_section(
            settings_container,
            "🎬 VIDEO DIHASILKAN",
            [
                ("video_output_format", "Format output (menggunakan model gemini-veo)", "option", ["Label video HTML", "URL", "Label video Markdown"]),
            ],
            5
        )
        
        # Public Display (Siaran Langsung)
        self.create_settings_section(
            settings_container,
            "📺 SIARAN LANGSUNG",
            [
                ("logo_url", "Logo lokasi", "entry", ""),
                ("chat_url", "Alamat logo", "entry", ""),
            ],
            6
        )
        
        # Session Settings
        self.create_settings_section(
            settings_container,
            "🔐 SESSION",
            [
                ("session_expire_hours", "Session Expire (hours)", "entry", "24"),
            ],
            7
        )
        
        # Retry/Cooldown Settings
        self.create_settings_section(
            settings_container,
            "⏱️ RETRY & COOLDOWN",
            [
                ("max_account_switch_tries", "Max Account Switch Tries", "entry", "3"),
                ("text_rate_limit_cooldown_seconds", "Text Rate Limit Cooldown (seconds)", "entry", "60"),
                ("images_rate_limit_cooldown_seconds", "Images Rate Limit Cooldown (seconds)", "entry", "60"),
                ("videos_rate_limit_cooldown_seconds", "Videos Rate Limit Cooldown (seconds)", "entry", "60"),
                ("session_cache_ttl_seconds", "Session Cache TTL (seconds)", "entry", "3600"),
                ("auto_refresh_accounts_seconds", "Auto Refresh Accounts (seconds)", "entry", "3600"),
                ("scheduled_refresh_enabled", "Scheduled Refresh Enabled", "switch", False),
                ("scheduled_refresh_interval_minutes", "Scheduled Refresh Interval (minutes)", "entry", "60"),
            ],
            8
        )
        
        return frame
    
    def create_settings_section(self, parent, title, fields, row):
        """Create a settings section"""
        section_frame = ctk.CTkFrame(parent)
        section_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=10)
        section_frame.grid_columnconfigure(1, weight=1)
        
        title_label = ctk.CTkLabel(
            section_frame,
            text=title,
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.grid(row=0, column=0, columnspan=2, padx=20, pady=(15, 10), sticky="w")
        
        for idx, field_info in enumerate(fields):
            if len(field_info) == 4:
                key, label, field_type, default = field_info
            else:
                key, label, field_type = field_info
                default = ""
            
            # Skip label types (info only)
            if field_type == "label":
                info_label = ctk.CTkLabel(
                    section_frame,
                    text="ℹ️ " + label,
                    font=ctk.CTkFont(size=12),
                    text_color="gray"
                )
                info_label.grid(row=idx+1, column=0, columnspan=2, padx=20, pady=8, sticky="w")
                continue
            
            lbl = ctk.CTkLabel(
                section_frame,
                text=label + ":",
                font=ctk.CTkFont(size=13)
            )
            lbl.grid(row=idx+1, column=0, padx=20, pady=8, sticky="nw")
            
            if field_type == "entry":
                widget = ctk.CTkEntry(section_frame, width=400)
                widget.insert(0, str(default))
            elif field_type == "switch":
                widget = ctk.CTkSwitch(section_frame, text="")
                if default:
                    widget.select()
            elif field_type == "option":
                widget = ctk.CTkOptionMenu(section_frame, values=default, width=400)
            elif field_type == "text":
                widget = ctk.CTkTextbox(section_frame, width=400, height=80)
                widget.insert("1.0", str(default))
            else:
                # Unknown field type, skip
                continue
            
            widget.grid(row=idx+1, column=1, padx=20, pady=8, sticky="w")
            self.settings_widgets[key] = (widget, field_type)
    
    def create_generator_email_section(self, parent, row):
        """Create Generator.Email domain management section"""
        section_frame = ctk.CTkFrame(parent)
        section_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=10)
        section_frame.grid_columnconfigure(0, weight=1)
        
        # Title
        title_label = ctk.CTkLabel(
            section_frame,
            text="📧 GENERATOR.EMAIL - Domain Management",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.grid(row=0, column=0, columnspan=2, padx=20, pady=(15, 10), sticky="w")
        
        # Info text
        info_label = ctk.CTkLabel(
            section_frame,
            text="Manage generator.email domains for account registration",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        info_label.grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 10), sticky="w")
        
        # Domains list (readonly textbox)
        self.domains_textbox = ctk.CTkTextbox(section_frame, width=500, height=120)
        self.domains_textbox.grid(row=2, column=0, columnspan=2, padx=20, pady=10, sticky="ew")
        self.domains_textbox.insert("1.0", "Loading domains...")
        self.domains_textbox.configure(state="disabled")
        
        # Buttons frame
        buttons_frame = ctk.CTkFrame(section_frame, fg_color="transparent")
        buttons_frame.grid(row=3, column=0, columnspan=2, padx=20, pady=(0, 15), sticky="w")
        
        refresh_btn = ctk.CTkButton(
            buttons_frame,
            text="🔄 Refresh Domains",
            command=self.load_domains,
            width=140
        )
        refresh_btn.grid(row=0, column=0, padx=(0, 10))
        
        add_btn = ctk.CTkButton(
            buttons_frame,
            text="➕ Add Domain",
            command=self.add_domain_dialog,
            width=140,
            fg_color="green",
            hover_color="darkgreen"
        )
        add_btn.grid(row=0, column=1, padx=(0, 10))
        
        remove_btn = ctk.CTkButton(
            buttons_frame,
            text="➖ Remove Domain",
            command=self.remove_domain_dialog,
            width=140,
            fg_color="red",
            hover_color="darkred"
        )
        remove_btn.grid(row=0, column=2)
        
        # Load domains on startup
        self.after(500, self.load_domains)
    
    def create_monitor_tab(self):
        """Create monitoring tab"""
        frame = ctk.CTkFrame(self.main_container)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        # Header
        header = ctk.CTkFrame(frame, height=60, corner_radius=0, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        
        title = ctk.CTkLabel(
            header,
            text="📈 System Monitor",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title.grid(row=0, column=0, padx=30, pady=15, sticky="w")
        
        auto_refresh_var = ctk.BooleanVar(value=False)
        auto_refresh = ctk.CTkSwitch(
            header,
            text="Auto-refresh",
            variable=auto_refresh_var,
            command=lambda: self.toggle_auto_refresh(auto_refresh_var.get())
        )
        auto_refresh.grid(row=0, column=1, padx=(0, 10), pady=15)
        
        refresh_btn = ctk.CTkButton(
            header,
            text=f"{ICONS['refresh']}  Refresh",
            width=100,
            command=self.refresh_monitor,
            fg_color="transparent",
            border_width=2
        )
        refresh_btn.grid(row=0, column=2, padx=30, pady=15)
        
        # Monitor content
        monitor_container = ctk.CTkScrollableFrame(frame)
        monitor_container.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        monitor_container.grid_columnconfigure(0, weight=1)
        
        # Health status
        health_frame = ctk.CTkFrame(monitor_container)
        health_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        health_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(
            health_frame,
            text="🏥 System Health",
            font=ctk.CTkFont(size=16, weight="bold")
        ).grid(row=0, column=0, columnspan=2, padx=20, pady=(15, 10), sticky="w")
        
        self.health_status_label = ctk.CTkLabel(
            health_frame,
            text="Status: Checking...",
            font=ctk.CTkFont(size=14)
        )
        self.health_status_label.grid(row=1, column=0, columnspan=2, padx=20, pady=10, sticky="w")
        
        # Account health
        accounts_health_frame = ctk.CTkFrame(monitor_container)
        accounts_health_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        accounts_health_frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(
            accounts_health_frame,
            text="👥 Accounts Health",
            font=ctk.CTkFont(size=16, weight="bold")
        ).grid(row=0, column=0, padx=20, pady=(15, 10), sticky="w")
        
        self.accounts_health_list = ctk.CTkTextbox(
            accounts_health_frame,
            height=300,
            font=ctk.CTkFont(size=12)
        )
        self.accounts_health_list.grid(row=1, column=0, padx=20, pady=(0, 15), sticky="ew")
        
        return frame
    
    def create_logs_tab(self):
        """Create logs viewer tab"""
        frame = ctk.CTkFrame(self.main_container)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        # Header
        header = ctk.CTkFrame(frame, height=60, corner_radius=0, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        
        title = ctk.CTkLabel(
            header,
            text="📝 Logs",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title.grid(row=0, column=0, padx=30, pady=15, sticky="w")
        
        button_frame = ctk.CTkFrame(header, fg_color="transparent")
        button_frame.grid(row=0, column=1, padx=30, pady=15)
        
        refresh_btn = ctk.CTkButton(
            button_frame,
            text=f"{ICONS['refresh']}  Refresh",
            width=100,
            command=self.refresh_logs,
            fg_color="transparent",
            border_width=2
        )
        refresh_btn.pack(side="left", padx=5)
        
        clear_btn = ctk.CTkButton(
            button_frame,
            text="🗑️ Clear",
            width=100,
            command=self.clear_logs_display,
            fg_color="transparent",
            border_width=2
        )
        clear_btn.pack(side="left", padx=5)
        
        # Logs display
        logs_container = ctk.CTkFrame(frame)
        logs_container.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        logs_container.grid_rowconfigure(0, weight=1)
        logs_container.grid_columnconfigure(0, weight=1)
        
        self.logs_display = ctk.CTkTextbox(
            logs_container,
            font=ctk.CTkFont(family="Courier", size=11),
            wrap="none"
        )
        self.logs_display.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        return frame
    
    def show_tab(self, tab_name):
        """Switch tabs"""
        # Hide all tabs
        for frame in [self.dashboard_frame, self.chat_frame, self.image_frame, 
                     self.video_frame, self.gallery_frame, self.accounts_frame, 
                     self.settings_frame, self.monitor_frame, self.logs_frame]:
            frame.grid_forget()
        
        # Update button colors
        for btn_id, btn in self.nav_buttons.items():
            if btn_id == tab_name:
                btn.configure(fg_color=("gray75", "gray25"))
            else:
                btn.configure(fg_color="transparent")
        
        # Show selected tab
        tab_map = {
            "dashboard": self.dashboard_frame,
            "chat": self.chat_frame,
            "image": self.image_frame,
            "video": self.video_frame,
            "gallery": self.gallery_frame,
            "accounts": self.accounts_frame,
            "settings": self.settings_frame,
            "monitor": self.monitor_frame,
            "logs": self.logs_frame,
        }
        
        if tab_name in tab_map:
            tab_map[tab_name].grid(row=0, column=0, sticky="nsew")
            
            # Load data when switching to certain tabs
            if tab_name == "accounts":
                self.refresh_accounts()
            elif tab_name == "settings":
                self.load_settings()
            elif tab_name == "monitor":
                self.refresh_monitor()
            elif tab_name == "logs":
                self.refresh_logs()
            elif tab_name == "gallery":
                self.refresh_gallery()
            elif tab_name == "dashboard":
                self.refresh_dashboard()
    
    # Dashboard methods
    def refresh_dashboard(self):
        """Refresh dashboard data"""
        if not self.api_client.logged_in:
            return
        threading.Thread(target=self._refresh_dashboard_thread, daemon=True).start()
    
    def _refresh_dashboard_thread(self):
        """Refresh dashboard in background"""
        try:
            stats = self.api_client.get_stats()
            self.after(0, lambda: self.update_dashboard_stats(stats))
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                print("Not authenticated. Please login first.")
            else:
                print(f"Error refreshing dashboard: {e}")
        except Exception as e:
            print(f"Error refreshing dashboard: {e}")
    
    def update_dashboard_stats(self, stats):
        """Update dashboard stats"""
        # Update stat cards
        if "accounts" in stats:
            acc_stats = stats["accounts"]
            total_accounts = acc_stats.get("total", 0)
            active_accounts = acc_stats.get("active", 0)
            failed_accounts = acc_stats.get("failed", 0)
        else:
            total_accounts = stats.get("total_accounts", 0)
            active_accounts = stats.get("active_accounts", 0)
            failed_accounts = stats.get("failed_accounts", 0)

        self.stats_cards["total_accounts"].value_label.configure(
            text=str(total_accounts)
        )
        self.stats_cards["active_accounts"].value_label.configure(
            text=str(active_accounts)
        )
        self.stats_cards["failed_accounts"].value_label.configure(
            text=str(failed_accounts)
        )

        if "requests" in stats:
            req_stats = stats["requests"]
            total_requests = req_stats.get("total", 0)
        else:
            total_requests = stats.get("success_count", 0) + stats.get("failed_count", 0)

        self.stats_cards["total_requests"].value_label.configure(
            text=str(total_requests)
        )
        
        # Update activity
        activity_text = "Recent Activity:\n\n"
        if "recent_requests" in stats:
            for req in stats["recent_requests"][:10]:
                timestamp = req.get("timestamp", "")
                model = req.get("model", "")
                status = req.get("status", "")
                activity_text += f"[{timestamp}] {model} - {status}\n"
        else:
            activity_text += "No recent activity"
        
        self.activity_text.delete("1.0", "end")
        self.activity_text.insert("1.0", activity_text)
    
    # Chat methods
    def send_chat(self):
        """Send chat message"""
        message = self.chat_input.get("1.0", "end-1c").strip()
        if not message:
            return
        
        self.chat_input.delete("1.0", "end")
        self.chat_display.insert("end", f"\n🧑 You:\n{message}\n\n")
        self.chat_display.see("end")
        self.chat_input.configure(state="disabled")
        self.chat_display.insert("end", "🤖 AI: Thinking...\n")
        
        def process():
            try:
                response = self.api_client.chat_completion(
                    "gemini-2.0-flash-exp",
                    [{"role": "user", "content": message}]
                )
                content = response['choices'][0]['message']['content']
                self.after(0, lambda: self._update_chat_response(content))
            except Exception as e:
                self.after(0, lambda: self._update_chat_response(f"❌ Error: {str(e)}"))
        
        threading.Thread(target=process, daemon=True).start()
    
    def _update_chat_response(self, content):
        """Update chat with response"""
        current = self.chat_display.get("1.0", "end")
        lines = current.split('\n')
        if lines and "Thinking..." in lines[-2]:
            self.chat_display.delete("end-2l", "end")
        
        self.chat_display.insert("end", f"{content}\n\n")
        self.chat_display.see("end")
        self.chat_input.configure(state="normal")
        self.chat_input.focus()
    
    def clear_chat(self):
        """Clear chat"""
        self.chat_display.delete("1.0", "end")
        self.chat_history = []
    
    # Image generation methods
    def generate_image(self):
        """Generate image"""
        prompt = self.image_prompt.get("1.0", "end-1c").strip()
        if not prompt:
            return
        
        self.image_generate_btn.configure(state="disabled", text="⏳ Generating...")
        self.image_loading_label.configure(text="⏳ Please wait...")
        self.image_preview.configure(text="Generating...", image=None)
        
        def process():
            try:
                response = self.api_client.chat_completion(
                    "gemini-imagen",
                    [{"role": "user", "content": prompt}]
                )
                content = response['choices'][0]['message']['content']
                
                try:
                    if 'data:image' in content:
                        base64_data = content.split('base64,')[1]
                    else:
                        base64_data = content
                    
                    image_data = base64.b64decode(base64_data)
                    self.current_image = Image.open(BytesIO(image_data))
                    
                    display_image = self.current_image.copy()
                    display_image.thumbnail((800, 800), Image.Resampling.LANCZOS)
                    photo = ctk.CTkImage(
                        light_image=display_image,
                        dark_image=display_image,
                        size=display_image.size
                    )
                    
                    self.after(0, lambda: self._update_image_preview(photo, None))
                except:
                    self.after(0, lambda: self._update_image_preview(None, content))
                    
            except Exception as e:
                self.after(0, lambda: self._update_image_preview(None, f"❌ Error: {str(e)}"))
        
        threading.Thread(target=process, daemon=True).start()
    
    def _update_image_preview(self, photo, text):
        """Update image preview"""
        self.image_generate_btn.configure(state="normal", text=f"{ICONS['image']}  Generate Image")
        self.image_loading_label.configure(text="")
        
        if photo:
            self.image_preview.configure(image=photo, text="")
        else:
            self.image_preview.configure(text=text or "❌ Failed", image=None)
    
    def save_image(self):
        """Save image"""
        if not self.current_image:
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG files", "*.png"), ("JPEG files", "*.jpg"), ("All files", "*.*")]
        )
        
        if filename:
            self.current_image.save(filename)
            self.image_loading_label.configure(text=f"✅ Saved: {os.path.basename(filename)}")
    
    def open_images_folder(self):
        """Open images folder in file explorer"""
        try:
            images_folder = os.path.abspath("./data/images")
            
            # Create folder if not exists
            os.makedirs(images_folder, exist_ok=True)
            
            # Open folder
            if os.name == 'nt':  # Windows
                os.startfile(images_folder)
            elif os.name == 'posix':  # macOS and Linux
                if os.uname().sysname == 'Darwin':  # macOS
                    os.system(f'open "{images_folder}"')
                else:  # Linux
                    os.system(f'xdg-open "{images_folder}"')
            
            self.image_loading_label.configure(text="📁 Images folder opened")
        except Exception as e:
            self.image_loading_label.configure(text=f"❌ Failed: {str(e)}")
    
    # Video generation methods
    def generate_video(self):
        """Generate video"""
        prompt = self.video_prompt.get("1.0", "end-1c").strip()
        if not prompt:
            return
        
        self.video_generate_btn.configure(state="disabled", text="⏳ Generating...")
        self.video_loading_label.configure(text="⏳ Please wait (3-5 minutes)...")
        self.video_thumbnail.configure(text="⏳ Generating...", image=None)
        self.video_info.configure(state="normal")
        self.video_info.delete("1.0", "end")
        self.video_info.insert("1.0", "Processing...")
        self.video_info.configure(state="disabled")
        
        def process():
            try:
                response = self.api_client.chat_completion(
                    "gemini-veo",
                    [{"role": "user", "content": prompt}]
                )
                content = response['choices'][0]['message']['content']
                self.after(0, lambda: self._update_video_preview(content))
            except Exception as e:
                self.after(0, lambda: self._update_video_preview(f"❌ Error: {str(e)}"))
        
        threading.Thread(target=process, daemon=True).start()
    
    def create_video_thumbnail_with_play_button(self, width=800, height=450):
        """Create video thumbnail"""
        img = Image.new('RGB', (width, height), color='#1a1a1a')
        draw = ImageDraw.Draw(img)
        
        center_x, center_y = width // 2, height // 2
        button_size = 80
        
        circle_bbox = [
            center_x - button_size,
            center_y - button_size,
            center_x + button_size,
            center_y + button_size
        ]
        draw.ellipse(circle_bbox, fill='#2196F3', outline='white', width=3)
        
        triangle_offset = 10
        triangle = [
            (center_x - 20 + triangle_offset, center_y - 35),
            (center_x - 20 + triangle_offset, center_y + 35),
            (center_x + 40 + triangle_offset, center_y)
        ]
        draw.polygon(triangle, fill='white')
        
        return img
    
    def _update_video_preview(self, content):
        """Update video preview"""
        self.video_generate_btn.configure(state="normal", text=f"{ICONS['video']}  Generate Video")
        self.video_loading_label.configure(text="✅ Generated!")
        
        video_url = None
        if "http" in content:
            urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', content)
            if urls:
                video_url = urls[0]
                self.current_video_url = video_url
        
        if video_url:
            thumbnail = self.create_video_thumbnail_with_play_button(800, 450)
            display_image = thumbnail.copy()
            display_image.thumbnail((800, 450), Image.Resampling.LANCZOS)
            photo = ctk.CTkImage(
                light_image=display_image,
                dark_image=display_image,
                size=display_image.size
            )
            
            self.video_thumbnail.configure(image=photo, text="", cursor="hand2")
            self.video_thumbnail.image = photo
        else:
            self.video_thumbnail.configure(text="✅ Generated\n(No preview)", image=None)
        
        self.video_info.configure(state="normal")
        self.video_info.delete("1.0", "end")
        
        if video_url:
            self.video_info.insert("1.0", f"✅ Video Generated!\n\n🔗 URL: {video_url}\n\n💡 Click thumbnail to play")
        else:
            self.video_info.insert("1.0", f"Response:\n\n{content}")
        
        self.video_info.configure(state="disabled")
    
    def open_video(self):
        """Open video di pemutar default atau browser"""
        if self.current_video_url:
            # Check if it's a local file
            if self.current_video_url.startswith('http://localhost') or self.current_video_url.startswith('http://127.0.0.1'):
                # Extract filename and try to find local file
                try:
                    # Parse URL to get filename
                    filename = self.current_video_url.split('/')[-1]
                    local_path = os.path.join('./data/videos', filename)
                    
                    if os.path.exists(local_path):
                        # Open in default system player
                        self.open_video_external(local_path)
                        self.video_loading_label.configure(text="🎬 Dibuka di pemutar default")
                    else:
                        # Fallback to browser
                        webbrowser.open(self.current_video_url)
                        self.video_loading_label.configure(text="🌐 Opened in browser")
                except:
                    webbrowser.open(self.current_video_url)
                    self.video_loading_label.configure(text="🌐 Opened in browser")
            else:
                webbrowser.open(self.current_video_url)
                self.video_loading_label.configure(text="🌐 Opened in browser")

    def open_video_external(self, filepath):
        """Open video dengan pemutar bawaan OS untuk mengurangi lag"""
        try:
            if os.name == 'nt':  # Windows
                os.startfile(filepath)
            elif os.name == 'posix':  # macOS and Linux
                if os.uname().sysname == 'Darwin':  # macOS
                    os.system(f'open "{filepath}"')
                else:  # Linux
                    os.system(f'xdg-open "{filepath}"')
        except Exception as e:
            messagebox.showerror("Error", f"Gagal membuka video: {e}")
    
    def open_videos_folder(self):
        """Open videos folder in file explorer"""
        try:
            videos_folder = os.path.abspath("./data/videos")
            
            # Create folder if not exists
            os.makedirs(videos_folder, exist_ok=True)
            
            # Open folder
            if os.name == 'nt':  # Windows
                os.startfile(videos_folder)
            elif os.name == 'posix':  # macOS and Linux
                if os.uname().sysname == 'Darwin':  # macOS
                    os.system(f'open "{videos_folder}"')
                else:  # Linux
                    os.system(f'xdg-open "{videos_folder}"')
            
            self.video_loading_label.configure(text="📁 Videos folder opened")
        except Exception as e:
            self.video_loading_label.configure(text=f"❌ Failed: {str(e)}")
    
    # Account management methods
    def refresh_accounts(self):
        """Refresh accounts list"""
        threading.Thread(target=self._refresh_accounts_thread, daemon=True).start()
    
    def _refresh_accounts_thread(self):
        """Refresh accounts in background"""
        try:
            accounts = self.api_client.get_accounts()
            self.after(0, lambda: self.update_accounts_list(accounts))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Failed to load accounts: {e}"))
    
    def update_accounts_list(self, accounts):
        """Update accounts list"""
        # Clear current list (except header)
        for widget in self.accounts_list.winfo_children()[1:]:
            widget.destroy()
        
        self.accounts_data = accounts if isinstance(accounts, list) else accounts.get("accounts", [])
        
        if not self.accounts_data:
            empty_label = ctk.CTkLabel(
                self.accounts_list,
                text="No accounts found. Click 'Add Account' to get started.",
                font=ctk.CTkFont(size=13),
                text_color="gray"
            )
            empty_label.grid(row=1, column=0, pady=50)
            return
        
        for idx, account in enumerate(self.accounts_data):
            account_frame = ctk.CTkFrame(self.accounts_list)
            account_frame.grid(row=idx+1, column=0, sticky="ew", padx=5, pady=2)
            account_frame.grid_columnconfigure(1, weight=1)
            
            # Email
            email = account.get("email", account.get("id", "Unknown"))
            email_label = ctk.CTkLabel(
                account_frame,
                text=email,
                font=ctk.CTkFont(size=12),
                anchor="w"
            )
            email_label.grid(row=0, column=1, padx=10, pady=8, sticky="w")
            
            # Status
            is_active = account.get("is_active", True)
            status_text = "✅ Active" if is_active else "❌ Inactive"
            status_color = "green" if is_active else "red"
            status_label = ctk.CTkLabel(
                account_frame,
                text=status_text,
                font=ctk.CTkFont(size=11),
                text_color=status_color
            )
            status_label.grid(row=0, column=0, padx=10, pady=8)
            
            # Type
            acc_type = account.get("type", "manual")
            type_label = ctk.CTkLabel(
                account_frame,
                text=acc_type,
                font=ctk.CTkFont(size=11),
                text_color="gray"
            )
            type_label.grid(row=0, column=2, padx=10, pady=8)
            
            # Actions
            actions_frame = ctk.CTkFrame(account_frame, fg_color="transparent")
            actions_frame.grid(row=0, column=3, padx=10, pady=8)
            
            edit_btn = ctk.CTkButton(
                actions_frame,
                text="✏️",
                width=30,
                command=lambda a=account: self.show_edit_account_dialog(a),
                fg_color="transparent",
                border_width=1
            )
            edit_btn.pack(side="left", padx=2)
            
            delete_btn = ctk.CTkButton(
                actions_frame,
                text="🗑️",
                width=30,
                command=lambda a=account: self.delete_account(a),
                fg_color="transparent",
                border_width=1,
                text_color="red"
            )
            delete_btn.pack(side="left", padx=2)
    
    def show_add_account_dialog(self):
        """Show add account dialog with manual and auto-register options"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add Account")
        dialog.geometry("600x550")
        dialog.transient(self)
        dialog.grab_set()
        
        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (600 // 2)
        y = (dialog.winfo_screenheight() // 2) - (550 // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Title
        title_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        title_frame.pack(fill="x", padx=20, pady=(20, 10))
        
        ctk.CTkLabel(
            title_frame,
            text="Add New Account",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack()
        
        # Tabview for Manual and Auto-Register
        tabview = ctk.CTkTabview(dialog, width=550)
        tabview.pack(fill="both", expand=True, padx=20, pady=(10, 20))
        
        # Tab 1: Manual Add
        tab_manual = tabview.add("📝 Manual")
        
        # Manual form
        ctk.CTkLabel(
            tab_manual,
            text="Add account manually",
            font=ctk.CTkFont(size=13),
            text_color="gray"
        ).pack(pady=(10, 20))
        
        # Email
        ctk.CTkLabel(tab_manual, text="Email:", anchor="w").pack(anchor="w", padx=30, pady=(5, 0))
        email_entry = ctk.CTkEntry(tab_manual, width=450, placeholder_text="example@gmail.com")
        email_entry.pack(padx=30, pady=5)
        
        # Password
        ctk.CTkLabel(tab_manual, text="Password:", anchor="w").pack(anchor="w", padx=30, pady=(10, 0))
        password_entry = ctk.CTkEntry(tab_manual, width=450, placeholder_text="Enter password", show="*")
        password_entry.pack(padx=30, pady=5)
        
        # Cookies (optional)
        ctk.CTkLabel(tab_manual, text="Cookies (Optional):", anchor="w").pack(anchor="w", padx=30, pady=(10, 0))
        cookies_entry = ctk.CTkTextbox(tab_manual, width=450, height=100)
        cookies_entry.pack(padx=30, pady=5)
        
        def save_manual_account():
            email = email_entry.get().strip()
            password = password_entry.get().strip()
            cookies = cookies_entry.get("1.0", "end-1c").strip()
            
            if not email:
                messagebox.showerror("Error", "Email is required")
                return
            
            account_data = {
                "email": email,
                "password": password if password else None,
                "cookies": cookies if cookies else None,
                "type": "manual"
            }
            
            try:
                self.api_client.add_account(account_data)
                dialog.destroy()
                self.refresh_accounts()
                messagebox.showinfo("Success", "Account added successfully")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to add account: {e}")
        
        manual_btn = ctk.CTkButton(
            tab_manual,
            text="💾 Add Account",
            width=200,
            height=40,
            command=save_manual_account,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        manual_btn.pack(pady=20)
        
        # Tab 2: Auto-Register
        tab_auto = tabview.add("🤖 Auto-Register")
        
        ctk.CTkLabel(
            tab_auto,
            text="Automatically create accounts with temporary email",
            font=ctk.CTkFont(size=13),
            text_color="gray"
        ).pack(pady=(10, 20))
        
        # Count
        ctk.CTkLabel(tab_auto, text="Number of accounts:", anchor="w").pack(anchor="w", padx=30, pady=(5, 0))
        count_entry = ctk.CTkEntry(tab_auto, width=450, placeholder_text="1")
        count_entry.insert(0, "1")
        count_entry.pack(padx=30, pady=5)
        
        # Email Provider info
        ctk.CTkLabel(
            tab_auto,
            text="📧 Using: Generator.Email (domains managed via API)",
            anchor="w",
            text_color="gray",
            font=ctk.CTkFont(size=11)
        ).pack(anchor="w", padx=30, pady=(10, 5))
        
        # Status label
        auto_status_label = ctk.CTkLabel(
            tab_auto,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        auto_status_label.pack(pady=(10, 0))
        
        # Progress bar
        auto_progress = ctk.CTkProgressBar(tab_auto, width=450)
        auto_progress.pack(padx=30, pady=10)
        auto_progress.set(0)
        auto_progress.pack_forget()  # Hide initially
        
        def start_auto_register():
            try:
                count = int(count_entry.get().strip())
                if count <= 0 or count > 10:
                    messagebox.showerror("Error", "Count must be between 1-10")
                    return
            except:
                messagebox.showerror("Error", "Invalid count")
                return
            
            # Disable button and show progress
            auto_btn.configure(state="disabled", text="⏳ Starting...")
            auto_status_label.configure(text=f"Starting auto-register for {count} account(s)...")
            auto_progress.pack(padx=30, pady=10)
            auto_progress.set(0)
            
            def register_thread():
                try:
                    # Start task
                    task = self.api_client.start_auto_register(count)
                    task_id = task.get("id")
                    
                    # Monitor progress
                    while True:
                        time.sleep(2)
                        status = self.api_client.get_register_status()
                        
                        if status.get("status") == "idle":
                            break
                        
                        state = status.get("state", "running")
                        completed = status.get("completed", 0)
                        total = status.get("total", count)
                        progress = completed / total if total > 0 else 0
                        
                        self.after(0, lambda p=progress, c=completed, t=total: (
                            auto_progress.set(p),
                            auto_status_label.configure(text=f"Progress: {c}/{t} accounts")
                        ))
                        
                        if state in ["completed", "failed", "cancelled"]:
                            break
                    
                    # Done
                    self.after(0, lambda: (
                        auto_btn.configure(state="normal", text="🤖 Start Auto-Register"),
                        auto_status_label.configure(text="✅ Completed! Check accounts list."),
                        auto_progress.pack_forget(),
                        self.refresh_accounts()
                    ))
                    
                    # Auto-close after 2 seconds
                    self.after(2000, dialog.destroy)
                    
                except Exception as e:
                    self.after(0, lambda: (
                        auto_btn.configure(state="normal", text="🤖 Start Auto-Register"),
                        auto_status_label.configure(text=f"❌ Error: {str(e)}", text_color="red"),
                        auto_progress.pack_forget()
                    ))
            
            threading.Thread(target=register_thread, daemon=True).start()
        
        auto_btn = ctk.CTkButton(
            tab_auto,
            text="🤖 Start Auto-Register",
            width=200,
            height=40,
            command=start_auto_register,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#FF6B35"
        )
        auto_btn.pack(pady=(10, 20))
        
        # Close button at bottom
        close_btn = ctk.CTkButton(
            dialog,
            text="❌ Close",
            width=120,
            command=dialog.destroy,
            fg_color="transparent",
            border_width=2
        )
        close_btn.pack(pady=(0, 20))
    
    def show_edit_account_dialog(self, account):
        """Show edit account dialog"""
        # Similar to add dialog but pre-filled
        messagebox.showinfo("Edit Account", f"Edit account: {account.get('email', 'Unknown')}")
    
    def delete_account(self, account):
        """Delete account"""
        account_id = account.get("id", account.get("email"))
        email = account.get("email", account_id)
        
        if messagebox.askyesno("Confirm Delete", f"Delete account: {email}?"):
            try:
                self.api_client.delete_account(account_id)
                self.refresh_accounts()
                messagebox.showinfo("Success", "Account deleted")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete: {e}")
    
    # Settings methods
    def load_settings(self):
        """Load settings"""
        threading.Thread(target=self._load_settings_thread, daemon=True).start()
    
    def _load_settings_thread(self):
        """Load settings in background"""
        try:
            settings = self.api_client.get_settings()
            self.after(0, lambda: self.update_settings_form(settings))
        except Exception as e:
            print(f"Error loading settings: {e}")
    
    def update_settings_form(self, settings):
        """Update settings form with loaded data"""
        try:
            # Map API response to form widgets
            basic = settings.get("basic", {})
            image_gen = settings.get("image_generation", {})
            video_gen = settings.get("video_generation", {})
            retry = settings.get("retry", {})
            public_display = settings.get("public_display", {})
            session = settings.get("session", {})
            
            # Helper to set widget value
            def set_value(key, value):
                if key in self.settings_widgets:
                    widget, field_type = self.settings_widgets[key]
                    try:
                        if field_type == "entry":
                            widget.delete(0, "end")
                            widget.insert(0, str(value) if value is not None else "")
                        elif field_type == "switch":
                            if value:
                                widget.select()
                            else:
                                widget.deselect()
                        elif field_type == "option":
                            widget.set(str(value) if value is not None else "")
                        elif field_type == "text":
                            widget.delete("1.0", "end")
                            # Handle list or string
                            if isinstance(value, list):
                                widget.insert("1.0", "\n".join(value))
                            else:
                                widget.insert("1.0", str(value) if value is not None else "")
                    except Exception as e:
                        print(f"Error setting {key}: {e}")
            
            # Basic settings
            set_value("api_key", basic.get("api_key", ""))
            set_value("base_url", basic.get("base_url", ""))
            set_value("proxy_for_auth", basic.get("proxy_for_auth", ""))
            set_value("proxy_for_chat", basic.get("proxy_for_chat", ""))
            set_value("browser_engine", "DP - Mendukung browser tanpa header" if basic.get("browser_engine") == "DP" else "UC - Undetected Chrome")
            set_value("browser_headless", basic.get("browser_headless", True))
            
            # Registration settings (Generator.Email only)
            set_value("register_default_count", basic.get("register_default_count", 1))
            set_value("refresh_window_hours", basic.get("refresh_window_hours", 24))
            
            # Image Generation
            set_value("image_enabled", image_gen.get("enabled", True))
            output_format = image_gen.get("output_format", "base64")
            format_map = {"base64": "Pengeditan Base64", "url": "URL label video HTML", "markdown": "Label video Markdown"}
            set_value("image_output_format", format_map.get(output_format, "Pengeditan Base64"))
            set_value("image_supported_models", image_gen.get("supported_models", []))
            
            # Video Generation
            video_format = video_gen.get("output_format", "html")
            video_format_map = {"html": "Label video HTML", "url": "URL", "markdown": "Label video Markdown"}
            set_value("video_output_format", video_format_map.get(video_format, "Label video HTML"))
            
            # Public Display
            set_value("logo_url", public_display.get("logo_url", ""))
            set_value("chat_url", public_display.get("chat_url", ""))
            
            # Session
            set_value("session_expire_hours", session.get("expire_hours", 24))
            
            # Retry/Cooldown
            set_value("max_account_switch_tries", retry.get("max_account_switch_tries", 3))
            set_value("text_rate_limit_cooldown_seconds", retry.get("text_rate_limit_cooldown_seconds", 60))
            set_value("images_rate_limit_cooldown_seconds", retry.get("images_rate_limit_cooldown_seconds", 60))
            set_value("videos_rate_limit_cooldown_seconds", retry.get("videos_rate_limit_cooldown_seconds", 60))
            set_value("session_cache_ttl_seconds", retry.get("session_cache_ttl_seconds", 3600))
            set_value("auto_refresh_accounts_seconds", retry.get("auto_refresh_accounts_seconds", 3600))
            set_value("scheduled_refresh_enabled", retry.get("scheduled_refresh_enabled", False))
            set_value("scheduled_refresh_interval_minutes", retry.get("scheduled_refresh_interval_minutes", 60))
            
            messagebox.showinfo("Success", "Settings loaded successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load settings: {e}")
            print(f"Error updating settings form: {e}")
    
    def save_settings(self):
        """Save settings"""
        try:
            # Helper to get widget value
            def get_value(key):
                if key in self.settings_widgets:
                    widget, field_type = self.settings_widgets[key]
                    try:
                        if field_type == "entry":
                            return widget.get()
                        elif field_type == "switch":
                            return widget.get() == 1
                        elif field_type == "option":
                            return widget.get()
                        elif field_type == "text":
                            text = widget.get("1.0", "end").strip()
                            # Return as list of lines
                            return [line.strip() for line in text.split("\n") if line.strip()]
                    except Exception as e:
                        print(f"Error getting {key}: {e}")
                        return None
                return None
            
            # Map browser engine display to API value
            browser_engine_value = get_value("browser_engine")
            if "DP" in browser_engine_value:
                browser_engine = "DP"
            else:
                browser_engine = "UC"
            
            # Map image output format display to API value
            image_format = get_value("image_output_format")
            image_format_map = {"Pengeditan Base64": "base64", "URL label video HTML": "url", "Label video Markdown": "markdown"}
            image_output_format = image_format_map.get(image_format, "base64")
            
            # Map video output format display to API value
            video_format = get_value("video_output_format")
            video_format_map = {"Label video HTML": "html", "URL": "url", "Label video Markdown": "markdown"}
            video_output_format = video_format_map.get(video_format, "html")
            
            # Build settings object
            settings = {
                "basic": {
                    "api_key": get_value("api_key") or "",
                    "base_url": get_value("base_url") or "http://127.0.0.1:7890",
                    "proxy_for_auth": get_value("proxy_for_auth") or "",
                    "proxy_for_chat": get_value("proxy_for_chat") or "",
                    "browser_engine": browser_engine,
                    "browser_headless": get_value("browser_headless"),
                    "register_default_count": int(get_value("register_default_count") or 1),
                    "refresh_window_hours": int(get_value("refresh_window_hours") or 24),
                },
                "image_generation": {
                    "enabled": get_value("image_enabled"),
                    "output_format": image_output_format,
                    "supported_models": get_value("image_supported_models") or [],
                },
                "video_generation": {
                    "output_format": video_output_format,
                },
                "public_display": {
                    "logo_url": get_value("logo_url") or "",
                    "chat_url": get_value("chat_url") or "",
                },
                "session": {
                    "expire_hours": int(get_value("session_expire_hours") or 24),
                },
                "retry": {
                    "max_account_switch_tries": int(get_value("max_account_switch_tries") or 3),
                    "text_rate_limit_cooldown_seconds": int(get_value("text_rate_limit_cooldown_seconds") or 60),
                    "images_rate_limit_cooldown_seconds": int(get_value("images_rate_limit_cooldown_seconds") or 60),
                    "videos_rate_limit_cooldown_seconds": int(get_value("videos_rate_limit_cooldown_seconds") or 60),
                    "session_cache_ttl_seconds": int(get_value("session_cache_ttl_seconds") or 3600),
                    "auto_refresh_accounts_seconds": int(get_value("auto_refresh_accounts_seconds") or 3600),
                    "scheduled_refresh_enabled": get_value("scheduled_refresh_enabled"),
                    "scheduled_refresh_interval_minutes": int(get_value("scheduled_refresh_interval_minutes") or 60),
                }
            }
            
            # Save via API
            threading.Thread(target=self._save_settings_thread, args=(settings,), daemon=True).start()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to prepare settings: {e}")
            print(f"Error saving settings: {e}")
    
    def _save_settings_thread(self, settings):
        """Save settings in background"""
        try:
            self.api_client.update_settings(settings)
            self.after(0, lambda: messagebox.showinfo("Success", "Settings saved successfully!"))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Failed to save settings: {e}"))
            print(f"Error in save settings thread: {e}")
    
    # Domain Management methods
    def load_domains(self):
        """Load domains from API"""
        if not self.api_client.logged_in:
            self._update_domains_display("Please login first to manage domains.")
            return
        threading.Thread(target=self._load_domains_thread, daemon=True).start()
    
    def _load_domains_thread(self):
        """Load domains in background"""
        try:
            response = self.api_client.session.get(f"{self.api_client.base_url}/admin/domains", timeout=10)
            if response.status_code == 200:
                data = response.json()
                domains = data.get("domains", [])
                
                # Format domains for display
                if domains:
                    lines = []
                    for idx, domain in enumerate(domains, 1):
                        status = "✅ Active" if domain.get("is_active") else "❌ Inactive"
                        lines.append(f"{idx}. {domain['domain']} - {status}")
                    text = "\n".join(lines)
                else:
                    text = "No domains configured. Click 'Add Domain' to add one."
                
                self.after(0, lambda: self._update_domains_display(text))
            else:
                self.after(0, lambda: self._update_domains_display(f"Error loading domains: {response.status_code}"))
        except Exception as e:
            error_msg = str(e)
            self.after(0, lambda: self._update_domains_display(f"Error: {error_msg}"))
    
    def _update_domains_display(self, text):
        """Update domains textbox"""
        self.domains_textbox.configure(state="normal")
        self.domains_textbox.delete("1.0", "end")
        self.domains_textbox.insert("1.0", text)
        self.domains_textbox.configure(state="disabled")
    
    def add_domain_dialog(self):
        """Show dialog to add new domain"""
        if not self.api_client.logged_in:
            messagebox.showerror("Error", "Please login first to manage domains.")
            return
        
        dialog = ctk.CTkInputDialog(
            text="Enter domain name (e.g., yourdomain.com):",
            title="Add Domain"
        )
        domain = dialog.get_input()
        
        if domain and domain.strip():
            self.add_domain(domain.strip())
    
    def add_domain(self, domain):
        """Add domain via API"""
        threading.Thread(target=self._add_domain_thread, args=(domain,), daemon=True).start()
    
    def _add_domain_thread(self, domain):
        """Add domain in background"""
        try:
            response = self.api_client.session.post(
                f"{self.api_client.base_url}/admin/domains",
                json={"domain": domain, "is_active": True},
                timeout=10
            )
            if response.status_code == 200:
                self.after(0, lambda: messagebox.showinfo("Success", f"Domain '{domain}' added successfully!"))
                self.after(0, self.load_domains)
            else:
                error = response.json().get("detail", "Unknown error")
                self.after(0, lambda: messagebox.showerror("Error", f"Failed to add domain: {error}"))
        except Exception as e:
            error_msg = str(e)
            self.after(0, lambda: messagebox.showerror("Error", f"Failed to add domain: {error_msg}"))
    
    def remove_domain_dialog(self):
        """Show dialog to remove domain"""
        if not self.api_client.logged_in:
            messagebox.showerror("Error", "Please login first to manage domains.")
            return
        
        dialog = ctk.CTkInputDialog(
            text="Enter domain name to remove:",
            title="Remove Domain"
        )
        domain = dialog.get_input()
        
        if domain and domain.strip():
            # Confirm removal
            result = messagebox.askyesno(
                "Confirm Removal",
                f"Are you sure you want to remove domain '{domain.strip()}'?"
            )
            if result:
                self.remove_domain(domain.strip())
    
    def remove_domain(self, domain):
        """Remove domain via API"""
        threading.Thread(target=self._remove_domain_thread, args=(domain,), daemon=True).start()
    
    def _remove_domain_thread(self, domain):
        """Remove domain in background"""
        try:
            response = self.api_client.session.delete(
                f"{self.api_client.base_url}/admin/domains/{domain}",
                timeout=10
            )
            if response.status_code == 200:
                self.after(0, lambda: messagebox.showinfo("Success", f"Domain '{domain}' removed successfully!"))
                self.after(0, self.load_domains)
            else:
                error = response.json().get("detail", "Unknown error")
                self.after(0, lambda: messagebox.showerror("Error", f"Failed to remove domain: {error}"))
        except Exception as e:
            error_msg = str(e)
            self.after(0, lambda: messagebox.showerror("Error", f"Failed to remove domain: {error_msg}"))
    
    # Monitor methods
    def toggle_auto_refresh(self, enabled):
        """Toggle auto-refresh for monitor"""
        if enabled:
            self.auto_refresh_monitor()
        else:
            if hasattr(self, 'auto_refresh_job'):
                self.after_cancel(self.auto_refresh_job)
    
    def auto_refresh_monitor(self):
        """Auto-refresh monitor every 5 seconds"""
        self.refresh_monitor()
        self.auto_refresh_job = self.after(5000, self.auto_refresh_monitor)
    
    def refresh_monitor(self):
        """Refresh monitor data"""
        threading.Thread(target=self._refresh_monitor_thread, daemon=True).start()
    
    def _refresh_monitor_thread(self):
        """Refresh monitor in background"""
        try:
            health = self.api_client.get_health()
            accounts = self.api_client.get_accounts()
            
            self.after(0, lambda: self.update_monitor_display(health, accounts))
        except Exception as e:
            print(f"Error refreshing monitor: {e}")
    
    def update_monitor_display(self, health, accounts):
        """Update monitor display"""
        # Update health status
        status = health.get("status", "unknown")
        status_text = f"Status: {status.upper()}"
        status_color = "green" if status == "healthy" else "red"
        self.health_status_label.configure(text=status_text, text_color=status_color)
        
        # Update accounts health
        self.accounts_health_list.delete("1.0", "end")
        
        accounts_list = accounts if isinstance(accounts, list) else accounts.get("accounts", [])
        
        for account in accounts_list:
            email = account.get("email", "Unknown")
            is_active = account.get("is_active", False)
            status = "✅ Active" if is_active else "❌ Inactive"
            
            self.accounts_health_list.insert("end", f"{status} - {email}\n")
    
    # Logs methods
    def refresh_logs(self):
        """Refresh logs"""
        threading.Thread(target=self._refresh_logs_thread, daemon=True).start()
    
    def _refresh_logs_thread(self):
        """Refresh logs in background"""
        try:
            logs = self.api_client.get_logs(limit=100)
            self.after(0, lambda: self.update_logs_display(logs))
        except Exception as e:
            self.after(0, lambda: self.logs_display.insert("end", f"Error loading logs: {e}\n"))
    
    def update_logs_display(self, logs):
        """Update logs display"""
        self.logs_display.delete("1.0", "end")
        
        logs_list = logs if isinstance(logs, list) else logs.get("logs", [])
        
        if not logs_list:
            self.logs_display.insert("1.0", "No logs available")
            return
        
        for log in logs_list:
            timestamp = log.get("timestamp", "")
            level = log.get("level", "INFO")
            message = log.get("message", "")
            
            self.logs_display.insert("end", f"[{timestamp}] {level}: {message}\n")
    
    def clear_logs_display(self):
        """Clear logs display"""
        self.logs_display.delete("1.0", "end")
    
    # Gallery methods
    def refresh_gallery(self):
        """Refresh gallery display"""
        threading.Thread(target=self._refresh_gallery_thread, daemon=True).start()
    
    def _refresh_gallery_thread(self):
        """Refresh gallery in background"""
        try:
            # Get current tab (images or videos)
            current_tab = self.gallery_tab_var.get().lower()
            
            # Determine folder path
            if current_tab == "images":
                folder = "./data/images"
                extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
            else:
                folder = "./data/videos"
                extensions = ('.mp4', '.webm', '.mov', '.avi')
            
            # Get list of files
            media_files = []
            if os.path.exists(folder):
                for filename in os.listdir(folder):
                    if filename.lower().endswith(extensions):
                        filepath = os.path.join(folder, filename)
                        stat = os.stat(filepath)
                        media_files.append({
                            'filename': filename,
                            'filepath': filepath,
                            'size': stat.st_size,
                            'modified': stat.st_mtime
                        })
                
                # Sort by modified time (newest first)
                media_files.sort(key=lambda x: x['modified'], reverse=True)
            
            # Update UI
            self.after(0, lambda: self._update_gallery_display(media_files, current_tab))
            
        except Exception as e:
            self.after(0, lambda: self.update_gallery_status(f"Error loading media: {e}", "red"))
    
    def _update_gallery_display(self, media_files, media_type):
        """Update gallery display with media files"""
        # Clear existing items
        for widget in self.gallery_grid.winfo_children():
            widget.destroy()
        
        if not media_files:
            no_media = ctk.CTkLabel(
                self.gallery_grid,
                text=f"No {media_type} found",
                font=ctk.CTkFont(size=14),
                text_color="gray"
            )
            no_media.pack(pady=50)
            self.update_gallery_status(f"No {media_type} found", "gray")
            return
        
        # Create grid layout
        columns = 3
        for idx, media in enumerate(media_files):
            row = idx // columns
            col = idx % columns
            
            # Create media card
            card = self.create_media_card(media, media_type)
            card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
        
        # Configure grid weights
        for col in range(columns):
            self.gallery_grid.grid_columnconfigure(col, weight=1)
        
        self.update_gallery_status(f"Found {len(media_files)} {media_type}", "green")
    
    def create_media_card(self, media, media_type):
        """Create a card for media file"""
        card = ctk.CTkFrame(self.gallery_grid, corner_radius=10, border_width=2)
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)
        
        # Thumbnail/Preview
        preview_frame = ctk.CTkFrame(card, height=200, corner_radius=8)
        preview_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        preview_frame.grid_propagate(False)
        
        if media_type == "images":
            # Load and display image thumbnail
            try:
                img = Image.open(media['filepath'])
                img.thumbnail((280, 200))
                photo = ctk.CTkImage(light_image=img, dark_image=img, size=(280, 200))
                
                preview_label = ctk.CTkLabel(preview_frame, image=photo, text="")
                preview_label.image = photo  # Keep reference
                preview_label.pack(fill="both", expand=True)
            except Exception as e:
                preview_label = ctk.CTkLabel(
                    preview_frame,
                    text=f"🖼️\nImage",
                    font=ctk.CTkFont(size=14)
                )
                preview_label.pack(fill="both", expand=True)
        else:
            # Video placeholder
            preview_label = ctk.CTkLabel(
                preview_frame,
                text=f"🎬\nVideo",
                font=ctk.CTkFont(size=14)
            )
            preview_label.pack(fill="both", expand=True)
        
        # File info
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))
        
        filename_label = ctk.CTkLabel(
            info_frame,
            text=media['filename'][:30] + "..." if len(media['filename']) > 30 else media['filename'],
            font=ctk.CTkFont(size=11),
            anchor="w"
        )
        filename_label.pack(fill="x", pady=(0, 2))
        
        # File size
        size_mb = media['size'] / (1024 * 1024)
        size_text = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{media['size'] / 1024:.1f} KB"
        
        # Modified date
        mod_time = datetime.fromtimestamp(media['modified'])
        time_diff = datetime.now() - mod_time
        if time_diff.days == 0:
            time_text = f"{time_diff.seconds // 3600}h ago"
        elif time_diff.days < 7:
            time_text = f"{time_diff.days}d ago"
        else:
            time_text = mod_time.strftime("%Y-%m-%d")
        
        size_label = ctk.CTkLabel(
            info_frame,
            text=f"{size_text} • {time_text}",
            font=ctk.CTkFont(size=10),
            text_color="gray",
            anchor="w"
        )
        size_label.pack(fill="x")
        
        # Action buttons
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)
        
        # Different button text for videos vs images
        if media_type == "videos":
            btn_text = f"{ICONS['play']}  Play"
        else:
            btn_text = f"{ICONS['open']}  Open"
        
        open_btn = ctk.CTkButton(
            btn_frame,
            text=btn_text,
            command=lambda: self.open_media_file(media['filepath']),
            height=30,
            fg_color="transparent",
            border_width=1
        )
        open_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        
        folder_btn = ctk.CTkButton(
            btn_frame,
            text=f"{ICONS['folder']}  Folder",
            command=lambda: self.open_media_folder(media['filepath']),
            height=30,
            fg_color="transparent",
            border_width=1
        )
        folder_btn.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        
        return card
    
    def on_gallery_tab_change(self, value):
        """Handle gallery tab change"""
        # Variable sudah di-set otomatis oleh CTkSegmentedButton
        # Hanya perlu refresh display
        self.refresh_gallery()
    
    def open_media_file(self, filepath):
        """Open media file - video in app player, images with default app"""
        try:
            # Check if it's a video file
            video_extensions = ('.mp4', '.webm', '.mov', '.avi')
            if filepath.lower().endswith(video_extensions):
                # Open in default system player
                self.open_video_external(filepath)
            else:
                # Open images with default application
                if os.name == 'nt':  # Windows
                    os.startfile(filepath)
                elif os.name == 'posix':  # macOS and Linux
                    if os.uname().sysname == 'Darwin':  # macOS
                        os.system(f'open "{filepath}"')
                    else:  # Linux
                        os.system(f'xdg-open "{filepath}"')
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open file: {e}")
    
    def open_media_folder(self, filepath):
        """Open folder containing the media file"""
        try:
            folder = os.path.dirname(os.path.abspath(filepath))
            if os.name == 'nt':  # Windows
                os.startfile(folder)
            elif os.name == 'posix':
                if os.uname().sysname == 'Darwin':  # macOS
                    os.system(f'open "{folder}"')
                else:  # Linux
                    os.system(f'xdg-open "{folder}"')
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open folder: {e}")
    
    def update_gallery_status(self, message, color="gray"):
        """Update gallery status label"""
        self.gallery_status.configure(text=message, text_color=color)
    
    # Application methods
    def do_logout(self):
        """Logout"""
        if messagebox.askyesno("Logout", "Are you sure you want to logout?"):
            self.api_client.logout()
            self.destroy()
            # Restart app
            GeminiManagementApp().mainloop()


if __name__ == "__main__":
    app = GeminiManagementApp()
    app.mainloop()
