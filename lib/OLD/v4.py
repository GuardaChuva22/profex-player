import subprocess
import yt_dlp as youtube_dl 
import vlc
import tkinter as tk
import threading
import time
import keyboard
import json
from PIL import Image, ImageDraw
import pystray
import os
import ctypes

# /////////////////////////// CONFIGS //////////////////////////////////////////
nomeDaJanela = "Windows Defender"
nomeDoIconeNoTray = "Windows Defender Terminal"
tempoIdle = 120 # 180 = 3 minutes idle
# /////////////////////////////////////////////////////////////////////////////

def play_error_sound():
    """Play an error sound when an invalid command is entered."""
    error_player = vlc.MediaPlayer("error.mp3")  # Ensure error.mp3 is in the same directory
    error_player.play()

def create_tray_image():
    # Load your custom icon (supports PNG, ICO, etc.)
    image = Image.open('icon.ico')  # Replace with your icon file path
    image = image.resize((16, 16), Image.Resampling.LANCZOS)  # Resize if needed
    return image

def setup_tray_icon(root):
    def on_show(icon, item):
        """Show the window and move it to the bottom-right corner."""
        root.after(0, position_window)
        root.after(0, root.deiconify)

    def position_window():
        """Move the window to the bottom-right corner of the screen."""
        root.update_idletasks()  
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        window_width = 200
        window_height = 30

        x_position = screen_width - window_width - 10  # 10px margin from the right
        y_position = screen_height - window_height - 75  # 50px margin from the bottom

        root.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")

    
    def on_exit(icon, item):
        icon.stop()
        root.after(0, root.destroy)
    
    menu = pystray.Menu(
        pystray.MenuItem('Show', on_show),
        pystray.MenuItem('Exit', on_exit)
    )
    
    icon = pystray.Icon("prfx", create_tray_image(), nomeDoIconeNoTray, menu)
    return icon

def hide_window(root):
    root.withdraw()

def load_config():
    try:
        with open("config.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("Config file not found! Using default keybinds.")
        return {
            "terminate": "ctrl+shift+q",
            "play": "ctrl+alt+p",
            "pause": "ctrl+alt+space",
            "resume": "ctrl+alt+r",
            "skip": "ctrl+alt+s",
            "stop": "ctrl+alt+q",
            "volume_up": "ctrl+alt+up",
            "volume_down": "ctrl+alt+down"
        }

# Global variables for playlist and player
playlist = []
playlist_lock = threading.Lock()  # Protect access to the playlist
current_song = None
player = None

# Global variable to track the last time music was actively playing.
last_music_time = time.time()

def get_stream_url(query):
    """Get the direct audio stream URL(s) from YouTube."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'extract_audio': True,
        'noplaylist': False,
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            if query.startswith(('http://', 'https://')):
                info = ydl.extract_info(query, download=False)
            else:
                info = ydl.extract_info(f"ytsearch:{query}", download=False)
            if not info:
                return None
            if 'entries' in info:
                return [entry['url'] for entry in info['entries']]
            else:
                return [info['url']]
        except Exception as e:
            print(f"Error retrieving stream URL: {e}")
            return None

def playback_loop():
    """Continuously play songs from the playlist in a single thread."""
    global current_song, player, playlist, last_music_time
    while True:
        with playlist_lock:
            if playlist:
                current_song = playlist.pop(0)
            else:
                current_song = None

        if current_song:
            player = vlc.MediaPlayer(current_song)
            player.play()
            # Reset idle timer as soon as a song starts
            last_music_time = time.time()

            while True:
                state = player.get_state()
                if state == vlc.State.Playing:
                    last_music_time = time.time()
                if state in (vlc.State.Ended, vlc.State.Stopped, vlc.State.Error):
                    break
                time.sleep(1)
            player = None
        else:
            time.sleep(1)

def play_stream(urls):
    """Add song(s) to the queue."""
    global playlist
    with playlist_lock:
        for url in urls:
            playlist.append(url)

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

def stop_song():
    """Stop the current song and clear the queue."""
    global player, playlist, current_song
    if player:
        player.stop()
        player = None
    current_song = None
    with playlist_lock:
        playlist.clear()

def set_volume(volume_level):
    """Set the volume of the current song."""
    global player
    if player:
        try:
            volume_level = int(volume_level)
            if 0 <= volume_level <= 100:
                player.audio_set_volume(volume_level)
        except ValueError:
            play_error_sound()

def handle_command(command):
    """Process commands entered in the GUI."""
    if command.startswith("play "):
        query = command[5:].strip()
        if not query:
            play_error_sound()
            return
        urls = get_stream_url(query)
        if urls:
            play_stream(urls)
        else:
            play_error_sound()
    elif command.startswith("volume "):
        volume_level = command[7:].strip()
        set_volume(volume_level)
    elif command == "clear":
        with playlist_lock:
            playlist.clear()
    elif command == "skip":
        skip_song()
    elif command == "pause":
        pause_song()
    elif command == "resume":
        resume_song()
    elif command == "stop":
        stop_song()
    elif command == "exit":
        root.destroy()
    else:
        play_error_sound()

def terminate_program():
    root.destroy()
    os._exit(0)

keybinds = load_config()

def listen_for_hotkeys():
    """Listen for global hotkeys."""
    keyboard.add_hotkey(keybinds["terminate"], terminate_program)
    keyboard.add_hotkey(keybinds["play"], lambda: play_stream(["your_default_song_url_here"]))
    keyboard.add_hotkey(keybinds["pause"], pause_song)
    keyboard.add_hotkey(keybinds["resume"], resume_song)
    keyboard.add_hotkey(keybinds["skip"], skip_song)
    keyboard.add_hotkey(keybinds["stop"], stop_song)
    keyboard.add_hotkey(keybinds["volume_up"],
                        lambda: set_volume(min(100, (player.audio_get_volume() if player else 0) + 10)))
    keyboard.add_hotkey(keybinds["volume_down"],
                        lambda: set_volume(max(0, (player.audio_get_volume() if player else 0) - 10)))
    keyboard.wait()  # Keep listening for hotkeys

# Start the hotkey listener in a daemon thread.
hotkey_thread = threading.Thread(target=listen_for_hotkeys, daemon=True)
hotkey_thread.start()

def on_enter(event):
    """Handle the Enter key press in the input field."""
    command = input_field.get().strip()
    input_field.delete(0, tk.END)
    handle_command(command)

# ------------------- Idle Monitor Thread -------------------
def idle_monitor():
    """
    Terminates the app if no music has been playing for 3 minutes.
    It checks if the player is not actively playing and compares the time elapsed
    since the last active playback.
    """
    global last_music_time, player
    while True:
        if player and player.get_state() == vlc.State.Playing:
            last_music_time = time.time()
        else:
            if time.time() - last_music_time > tempoIdle:  
                print("No music playing for 3 minutes. Terminating app.")
                terminate_program()
        time.sleep(1)

# Start the idle monitor thread.
idle_thread = threading.Thread(target=idle_monitor, daemon=True)
idle_thread.start()

# ------------------- TASKLIST Lock Monitor Thread -------------------
def monitor_lock_tasklist():
    """
    Uses the TASKLIST command to check if 'LogonUI.exe' is running.
    If found, it indicates that Windows is locked and the app terminates.
    """
    while True:
        try:
            output = subprocess.check_output("TASKLIST", shell=True, encoding="cp1252", errors="ignore")
            if "LogonUI.exe" in output:
                print("Windows locked detected via TASKLIST. Terminating app.")
                terminate_program()
        except Exception as e:
            print(f"Error checking TASKLIST: {e}")
        time.sleep(1)

# Start the lock monitor thread.
lock_thread = threading.Thread(target=monitor_lock_tasklist, daemon=True)
lock_thread.start()

# ------------------- Main Tkinter Window Setup -------------------
root = tk.Tk()
root.title(nomeDaJanela)
root.resizable(False, False)
root.iconbitmap('icon.ico')  # For Windows
root.geometry("200x30")  # Smaller window to fit only the input field
root.configure(bg='black')

# New window close handler: hide instead of destroy
root.protocol('WM_DELETE_WINDOW', lambda: hide_window(root))

# Setup system tray icon
tray_icon = setup_tray_icon(root)
tray_thread = threading.Thread(target=tray_icon.run, daemon=True)
tray_thread.start()

# Start hidden
root.withdraw()

# Create an input field
input_field = tk.Entry(root, bg='black', fg='white', insertbackground='white')
input_field.pack(fill=tk.X, padx=5, pady=5)
input_field.bind("<Return>", on_enter)

# Start the playback thread (it will run indefinitely)
playback_thread = threading.Thread(target=playback_loop, daemon=True)
playback_thread.start()

# Start the Tkinter main loop
root.mainloop()