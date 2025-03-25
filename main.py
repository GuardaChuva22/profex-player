import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# Spotify API credentials
SPOTIFY_CLIENT_ID = '0562507768924591938c648a90b36587'
SPOTIFY_CLIENT_SECRET = 'c5f4c2600a5d404ca09850cbc06c5699'

# Authenticate with Spotify
sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

import subprocess
import yt_dlp as youtube_dl
import vlc
import tkinter as tk
import threading
import time
import keyboard
import json
import logging
from PIL import Image, ImageDraw
import pystray
import os
import requests
from packaging import version
import webbrowser

# Setup logging for better error and status tracking.
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# /////////////////////////// CONFIGS //////////////////////////////////////////
WINDOW_TITLE = "Windows Defender"
TRAY_ICON_NAME = "Windows Defender Terminal"
IDLE_TIMEOUT = 120  # seconds idle before termination
# /////////////////////////////////////////////////////////////////////////////

def is_spotify_url(url):
    """Check if the URL is a Spotify URL."""
    return url.startswith(('https://open.spotify.com/', 'spotify:'))

def get_spotify_track_names(url):
    """Extract track names from a Spotify playlist or song URL."""
    try:
        if 'track' in url:  # Single track
            track = sp.track(url)
            return [f"{track['name']} {track['artists'][0]['name']}"]
        elif 'playlist' in url:  # Playlist
            results = sp.playlist_tracks(url)
            tracks = []
            for item in results['items']:
                track = item['track']
                tracks.append(f"{track['name']} {track['artists'][0]['name']}")
            return tracks
        else:
            logging.warning("Unsupported Spotify URL type.")
            return None
    except Exception as e:
        logging.error(f"Error fetching Spotify data: {e}")
        return None

class PlaylistManager:
    def __init__(self):
        self.playlist = []
        self.lock = threading.Lock()
        self.current_song = None

    def add_song(self, url):
        with self.lock:
            self.playlist.append(url)

    def get_next_song(self):
        with self.lock:
            if self.playlist:
                self.current_song = self.playlist.pop(0)
                return self.current_song
            else:
                self.current_song = None
                return None

    def clear(self):
        with self.lock:
            self.playlist.clear()
            self.current_song = None

    def is_empty(self):
        with self.lock:
            return not bool(self.playlist)

def play_error_sound():
    """Play an error sound when an invalid command is entered."""
    try:
        error_sound_path = os.path.join("lib", "sounds", "error.mp3")  # Updated path
        if os.path.exists(error_sound_path):
            error_player = vlc.MediaPlayer(error_sound_path)
            error_player.play()
        else:
            logging.error("Error sound file not found.")
    except Exception as e:
        logging.error(f"Error playing error sound: {e}")

def create_tray_image():
    # Load your custom icon (supports PNG, ICO, etc.)
    icon_path = os.path.join("lib", "icons", "icon.ico")  # Updated path
    if os.path.exists(icon_path):
        try:
            image = Image.open(icon_path)
            image = image.resize((16, 16), Image.Resampling.LANCZOS)
            return image
        except Exception as e:
            logging.error(f"Error loading tray icon: {e}")
    # Fallback: create a simple default image
    image = Image.new('RGB', (16,16), color='gray')
    return image

def setup_tray_icon(root):
    def on_show(icon, item):
        """Show the window and position it at the bottom-right corner."""
        root.after(0, position_window)
        root.after(0, root.deiconify)

    def position_window():
        root.update_idletasks()  
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        window_width = 200
        window_height = 30

        x_position = screen_width - window_width - 10  # 10px margin from right
        y_position = screen_height - window_height - 75  # 75px margin from bottom
        root.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")

    def on_exit(icon, item):
        icon.stop()
        root.after(0, terminate_program)
    
    menu = pystray.Menu(
        pystray.MenuItem('Show', on_show),
        pystray.MenuItem('Exit', on_exit)
    )
    
    icon = pystray.Icon("prfx", create_tray_image(), TRAY_ICON_NAME, menu)
    return icon

def hide_window(root):
    root.withdraw()

def load_config():
    config_defaults = {
        "terminate": "ctrl+shift+q",
        "play": "ctrl+alt+p",
        "pause": "ctrl+alt+space",
        "resume": "ctrl+alt+r",
        "skip": "ctrl+alt+s",
        "stop": "ctrl+alt+q",
        "volume_up": "ctrl+alt+up",
        "volume_down": "ctrl+alt+down",
        "skip_forward": "ctrl+alt+right",
        "skip_backward": "ctrl+alt+left"
    }
    
    config_path = os.path.join("lib", "config", "config.json")
    
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        # Check if config file exists
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)
            # Merge user config with defaults (user settings take precedence)
            return {**config_defaults, **config}
        else:
            # Create default config file if it doesn't exist
            with open(config_path, "w") as f:
                json.dump(config_defaults, f, indent=4)
            return config_defaults
    except Exception as e:
        logging.warning(f"Config file error: {e}. Using default keybinds.")
        return config_defaults

def get_stream_url(query):
    """Get the direct audio stream URL(s) from YouTube. Handles playlists more efficiently."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'extract_audio': True,
        'noplaylist': True,  # Process each video individually,
        'no_warnings': True,
        'source_address': '0.0.0.0',
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            if query.startswith(('http://', 'https://')):
                info = ydl.extract_info(query, download=False)
            else:
                info = ydl.extract_info(f"ytsearch:{query}", download=False)

            if not info:
                return None

            if 'entries' in info:  # If it's a playlist
                urls = []
                for entry in info['entries']:
                    if entry and 'url' in entry:
                        urls.append(entry['url'])
                    else:
                        logging.warning(f"Skipping unavailable video: {entry.get('title', 'Unknown')}")
                return urls if urls else None
            else:  # Single video
                return [info.get('url')]
        except Exception as e:
            logging.error(f"Error retrieving stream URL: {e}")
            return None

def playback_loop(playlist_manager):
    """Continuously play songs from the playlist in a single thread."""
    global player, last_music_time
    while True:
        try:
            current_song = playlist_manager.get_next_song()
            if current_song:
                logging.info(f"Playing song: {current_song}")
                player = vlc.MediaPlayer(current_song)
                if player:  # Ensure player is initialized
                    player.play()
                    # Reset idle timer when a song starts
                    last_music_time = time.time()

                    while True:
                        state = player.get_state()
                        if state == vlc.State.Playing:
                            last_music_time = time.time()
                        if state in (vlc.State.Ended, vlc.State.Stopped, vlc.State.Error):
                            break
                        time.sleep(0.5)  # faster polling interval
                    player = None
            else:
                time.sleep(0.5)
        except Exception as e:
            logging.error(f"Error in playback loop: {e}")
            time.sleep(1)

def play_stream(urls, playlist_manager):
    """Add song(s) to the queue."""
    if urls:
        for url in urls:
            playlist_manager.add_song(url)
    else:
        play_error_sound()

def skip_song():
    """Skip the current song."""
    global player
    if player and player.get_state() not in (vlc.State.Ended, vlc.State.Stopped, vlc.State.Error):
        player.stop()

def pause_song():
    """Pause the current song."""
    global player
    if player and player.get_state() == vlc.State.Playing:
        player.pause()

def resume_song():
    """Resume the paused song."""
    global player
    if player and player.get_state() == vlc.State.Paused:
        player.play()

def stop_song(playlist_manager):
    """Stop the current song and clear the queue."""
    global player
    if player:
        player.stop()
        player = None
    playlist_manager.clear()

def set_volume(volume_level):
    """Set the volume of the current song."""
    global player
    try:
        vol = int(volume_level)
        if 0 <= vol <= 100:
            if player:
                player.audio_set_volume(vol)
        else:
            play_error_sound()
    except ValueError:
        play_error_sound()

def skip_forward():
    """Skip 10 seconds forward in the current song."""
    global player
    if player and player.get_state() in (vlc.State.Playing, vlc.State.Paused):
        current_time = player.get_time()
        new_time = current_time + 10000  # 10,000 ms = 10 seconds
        player.set_time(new_time)

def skip_backward():
    """Skip 10 seconds backward in the current song."""
    global player
    if player and player.get_state() in (vlc.State.Playing, vlc.State.Paused):
        current_time = player.get_time()
        new_time = max(0, current_time - 10000)
        player.set_time(new_time)

def handle_command(command, playlist_manager):
    """Process commands entered in the GUI."""
    if command.startswith("play "):
        query = command[5:].strip()
        if not query:
            play_error_sound()
            return

        if is_spotify_url(query):  # Handle Spotify URLs
            track_names = get_spotify_track_names(query)
            if track_names:
                for track_name in track_names:
                    urls = get_stream_url(track_name)
                    if urls:
                        play_stream(urls, playlist_manager)
            else:
                play_error_sound()
        else:  # Handle YouTube queries
            urls = get_stream_url(query)
            if urls:
                play_stream(urls, playlist_manager)
            else:
                play_error_sound()
    elif command.startswith("volume "):
        volume_level = command[7:].strip()
        set_volume(volume_level)
    elif command == "clear":
        playlist_manager.clear()
    elif command == "skip":
        skip_song()
    elif command == "pause":
        pause_song()
    elif command == "resume":
        resume_song()
    elif command == "stop":
        stop_song(playlist_manager)
    elif command == "exit":
        terminate_program()
    else:
        play_error_sound()

def terminate_program():
    try:
        root.destroy()
    except Exception as e:
        logging.error(f"Error destroying root window: {e}")
    os._exit(0)

def listen_for_hotkeys(playlist_manager):
    """Listen for global hotkeys."""
    keybinds = load_config()
    keyboard.add_hotkey(keybinds["terminate"], terminate_program)
    keyboard.add_hotkey(keybinds["play"], lambda: play_stream(["your_default_song_url_here"], playlist_manager))
    keyboard.add_hotkey(keybinds["pause"], pause_song)
    keyboard.add_hotkey(keybinds["resume"], resume_song)
    keyboard.add_hotkey(keybinds["skip"], skip_song)
    keyboard.add_hotkey(keybinds["stop"], lambda: stop_song(playlist_manager))
    keyboard.add_hotkey(keybinds["volume_up"],
                        lambda: set_volume(min(100, (player.audio_get_volume() if player else 0) + 10)))
    keyboard.add_hotkey(keybinds["volume_down"],
                        lambda: set_volume(max(0, (player.audio_get_volume() if player else 0) - 10)))
    keyboard.add_hotkey(keybinds["skip_forward"], skip_forward)
    keyboard.add_hotkey(keybinds["skip_backward"], skip_backward)
    keyboard.wait()  # Keep listening for hotkeys

def on_enter(event, playlist_manager):
    """Handle the Enter key press in the input field."""
    command = input_field.get().strip()
    input_field.delete(0, tk.END)
    handle_command(command, playlist_manager)

# Initialize player as None at the start of the program
player = None
last_music_time = time.time()  # Initialize last_music_time

def idle_monitor():
    """
    Terminates the app if no music has been playing for a set timeout.
    Checks the time elapsed since the last active playback.
    """
    global last_music_time, player
    while True:
        try:
            # Check if player is initialized and playing
            if player is not None and player.get_state() == vlc.State.Playing:
                last_music_time = time.time()
            elif time.time() - last_music_time > IDLE_TIMEOUT:  
                logging.info("Idle timeout reached. Terminating app.")
                terminate_program()
        except Exception as e:
            logging.error(f"Error in idle monitor: {e}")
        time.sleep(1)

def monitor_lock_tasklist():
    """
    Uses the TASKLIST command to check if 'LogonUI.exe' is running.
    If detected, terminates the app (indicative of Windows being locked).
    """
    while True:
        try:
            output = subprocess.check_output("TASKLIST", shell=True, encoding="cp1252", errors="ignore")
            if "LogonUI.exe" in output:
                logging.info("Windows lock detected. Terminating app.")
                terminate_program()
        except Exception as e:
            logging.error(f"Error checking TASKLIST: {e}")
        time.sleep(1)

# Initialize playlist manager
playlist_manager = PlaylistManager()

# Start the hotkey listener in a daemon thread.
hotkey_thread = threading.Thread(target=listen_for_hotkeys, args=(playlist_manager,), daemon=True)
hotkey_thread.start()

# ------------------- Main Tkinter Window Setup -------------------
root = tk.Tk()
root.title(WINDOW_TITLE)
root.resizable(False, False)
try:
    icon_path = os.path.join("lib", "icons", "icon.ico")  # Updated path
    root.iconbitmap(icon_path)  # For Windows icon
except Exception as e:
    logging.error(f"Error setting window icon: {e}")
root.geometry("200x30")  # Small window for the input field only
root.configure(bg='black')
root.protocol('WM_DELETE_WINDOW', lambda: hide_window(root))

# Setup system tray icon
tray_icon = setup_tray_icon(root)
tray_thread = threading.Thread(target=tray_icon.run, daemon=True)
tray_thread.start()

# Start hidden
root.withdraw()

# Create an input field for commands
input_field = tk.Entry(root, bg='black', fg='white', insertbackground='white')
input_field.pack(fill=tk.X, padx=5, pady=5)
input_field.bind("<Return>", lambda event: on_enter(event, playlist_manager))

# Start the playback thread (runs indefinitely)
playback_thread = threading.Thread(target=playback_loop, args=(playlist_manager,), daemon=True)
playback_thread.start()

# Start the idle monitor thread
idle_thread = threading.Thread(target=idle_monitor, daemon=True)
idle_thread.start()

# Start the lock monitor thread
lock_thread = threading.Thread(target=monitor_lock_tasklist, daemon=True)
lock_thread.start()

root.mainloop()