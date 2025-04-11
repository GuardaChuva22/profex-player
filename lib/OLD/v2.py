import yt_dlp as youtube_dl
import vlc
import tkinter as tk
from tkinter import scrolledtext
import threading
import time
import keyboard
import json
from PIL import Image, ImageDraw  # New imports
import pystray                     # New import

# /////////////////////////// CONFIGS //////////////////////////////////////////

nomeDaJanela = "Terminal"
nomeDoIconeNoTray = "Windows Defender Terminal"

# /////////////////////////////////////////////////////////////////////////////

# -------------------- New Tray Functions --------------------
def create_tray_image():
    image = Image.new('RGB', (16, 16), 'black')
    dc = ImageDraw.Draw(image)
    dc.rectangle((0, 0, 15, 15), fill='white')
    return image

def setup_tray_icon(root):
    def on_show(icon, item):
        root.after(0, root.deiconify)
    
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
            # If query is a URL, extract info directly.
            if query.startswith(('http://', 'https://')):
                info = ydl.extract_info(query, download=False)
            else:
                info = ydl.extract_info(f"ytsearch:{query}", download=False)
            if not info:
                return None

            # Handle playlists
            if 'entries' in info:
                return [entry['url'] for entry in info['entries']]
            else:
                return [info['url']]
        except Exception as e:
            print(f"Error retrieving stream URL: {e}")
            return None

def playback_loop():
    """Continuously play songs from the playlist in a single thread."""
    global current_song, player, playlist
    while True:
        with playlist_lock:
            if playlist:
                current_song = playlist.pop(0)
            else:
                current_song = None

        if current_song:
            player = vlc.MediaPlayer(current_song)
            # Update GUI from the main thread
            root.after(0, lambda cs=current_song: (
                output_text.insert(tk.END, f"Now playing: {cs}\n"),
                output_text.see(tk.END)
            ))
            player.play()

            # Wait until the song has really finished
            while True:
                state = player.get_state()
                # Debug: print(state)
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
    # Update GUI (this runs on the main thread)
    root.after(0, lambda: (
        output_text.insert(tk.END, f"Added to queue: {urls}\n"),
        output_text.see(tk.END)
    ))

def skip_song():
    """Skip the current song."""
    global player
    if player and player.get_state() not in (vlc.State.Ended, vlc.State.Stopped, vlc.State.Error):
        player.stop()
        root.after(0, lambda: (
            output_text.insert(tk.END, "Skipped current song.\n"),
            output_text.see(tk.END)
        ))
    else:
        root.after(0, lambda: (
            output_text.insert(tk.END, "No song is currently playing.\n"),
            output_text.see(tk.END)
        ))

def pause_song():
    """Pause the current song."""
    global player
    if player and player.get_state() == vlc.State.Playing:
        player.pause()
        root.after(0, lambda: (
            output_text.insert(tk.END, "Song paused.\n"),
            output_text.see(tk.END)
        ))
    else:
        root.after(0, lambda: (
            output_text.insert(tk.END, "No song is currently playing.\n"),
            output_text.see(tk.END)
        ))

def resume_song():
    """Resume the paused song."""
    global player
    # If player exists and its state is Paused, resume it.
    if player and player.get_state() == vlc.State.Paused:
        player.play()
        root.after(0, lambda: (
            output_text.insert(tk.END, "Song resumed.\n"),
            output_text.see(tk.END)
        ))
    elif not player:
        root.after(0, lambda: (
            output_text.insert(tk.END, "No song is currently paused or stopped.\n"),
            output_text.see(tk.END)
        ))
    else:
        root.after(0, lambda: (
            output_text.insert(tk.END, "No song is currently paused.\n"),
            output_text.see(tk.END)
        ))

def stop_song():
    """Stop the current song and clear the queue."""
    global player, playlist, current_song
    if player:
        player.stop()
        player = None
    current_song = None
    with playlist_lock:
        playlist.clear()
    root.after(0, lambda: (
        output_text.insert(tk.END, "Playback stopped and queue cleared.\n"),
        output_text.see(tk.END)
    ))

def set_volume(volume_level):
    """Set the volume of the current song."""
    global player
    if player:
        try:
            volume_level = int(volume_level)
            if 0 <= volume_level <= 100:
                player.audio_set_volume(volume_level)
                root.after(0, lambda: (
                    output_text.insert(tk.END, f"Volume set to {volume_level}.\n"),
                    output_text.see(tk.END)
                ))
            else:
                root.after(0, lambda: (
                    output_text.insert(tk.END, "Volume must be between 0 and 100.\n"),
                    output_text.see(tk.END)
                ))
        except ValueError:
            root.after(0, lambda: (
                output_text.insert(tk.END, "Invalid volume level. Use a number between 0 and 100.\n"),
                output_text.see(tk.END)
            ))
    else:
        root.after(0, lambda: (
            output_text.insert(tk.END, "No song is currently playing.\n"),
            output_text.see(tk.END)
        ))

def handle_command(command, output_text):
    """Process commands entered in the GUI."""
    if command.startswith("play "):
        query = command[5:].strip()
        if not query:
            output_text.insert(tk.END, "Please specify a song or playlist.\n")
            return
        urls = get_stream_url(query)
        if urls:
            output_text.insert(tk.END, f"Added to queue: {query}\n")
            play_stream(urls)
        else:
            output_text.insert(tk.END, "No results found.\n")
    elif command.startswith("volume "):
        volume_level = command[7:].strip()
        set_volume(volume_level)
    elif command == "clear":
        with playlist_lock:
            playlist.clear()
        output_text.insert(tk.END, "Queue cleared.\n")
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
        output_text.insert(tk.END,
            "Unknown command. Use 'play <song/playlist>', 'volume <0-100>', 'clear', 'skip', 'pause', 'resume', 'stop', or 'exit'.\n")
    output_text.see(tk.END)

def terminate_program():
    """Terminate the program immediately."""
    output_text.insert(tk.END, "Terminating program...\n")
    output_text.see(tk.END)
    root.destroy()

keybinds = load_config()

def listen_for_hotkeys():
    """Listen for global hotkeys."""
    keyboard.add_hotkey(keybinds["terminate"], terminate_program)
    # Replace "your_default_song_url_here" with a valid URL if needed.
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
    handle_command(command, output_text)

# Create the main Tkinter window
root = tk.Tk()
root.title(nomeDaJanela)
root.iconbitmap('icon.ico')  # For Windows
root.geometry("200x100")
root.configure(bg='black')

# New window close handler
root.protocol('WM_DELETE_WINDOW', lambda: hide_window(root))

# Setup system tray icon
tray_icon = setup_tray_icon(root)
tray_thread = threading.Thread(target=tray_icon.run, daemon=True)
tray_thread.start()

# Start hidden
root.withdraw()

# Create a scrolled text widget for output.
output_text = scrolledtext.ScrolledText(
    root,
    wrap=tk.WORD,
    state='normal',
    height=1,
    bg='black',
    fg='white',
    insertbackground='white'
)
output_text.pack(fill=tk.BOTH, expand=True)

# Create an input field.
input_field = tk.Entry(
    root,
    bg='black',
    fg='white',
    insertbackground='white'
)
input_field.pack(fill=tk.X, padx=5, pady=5)
input_field.bind("<Return>", on_enter)

# Start the playback thread once (it will run indefinitely)
playback_thread = threading.Thread(target=playback_loop, daemon=True)
playback_thread.start()

# Start the Tkinter main loop
root.mainloop()