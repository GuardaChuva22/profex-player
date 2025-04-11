import yt_dlp as youtube_dl
import vlc
import tkinter as tk
from tkinter import scrolledtext
import threading
import time
import keyboard
import json

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
current_song = None
player = None

def get_stream_url(query):
    """Get the direct audio stream URL from YouTube."""
    ydl_opts = {
        'format': 'bestaudio/best',  # Choose the best audio quality
        'quiet': True,  # Suppress yt-dlp output
        'extract_audio': True,  # Extract audio-only formats
        'noplaylist': False,  # Allow playlists
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            # Check if the query is a valid URL
            if query.startswith(('http://', 'https://')):
                info = ydl.extract_info(query, download=False)
            else:
                # If not a URL, search for the song by name
                info = ydl.extract_info(f"ytsearch:{query}", download=False)

            if not info:
                return None

            # Handle playlists
            if 'entries' in info:
                return [entry['url'] for entry in info['entries']]  # Return list of URLs
            else:
                return [info['url']]  # Return single URL as a list
        except Exception as e:
            print(f"Error retrieving stream URL: {e}")
            return None

def play_next_song():
    """Play the next song in the playlist."""
    global current_song, player, playlist

    if playlist:
        current_song = playlist.pop(0)  # Get the next song from the queue
        player = vlc.MediaPlayer(current_song)
        player.play()
        output_text.insert(tk.END, f"Now playing: {current_song}\n")
        output_text.see(tk.END)

        # Wait for the song to finish
        while player.is_playing():
            time.sleep(1)

        # Play the next song
        play_next_song()
    else:
        output_text.insert(tk.END, "Playlist is empty.\n")
        output_text.see(tk.END)

def play_stream(urls):
    """Add songs to the playlist and start playing if nothing is playing."""
    global playlist, player

    for url in urls:
        playlist.append(url)  # Add URLs to the playlist

    # Start playing only if nothing is currently playing
    if not player or not player.is_playing():
        play_next_song()

def skip_song():
    """Skip the current song and play the next one."""
    global player

    if player and player.is_playing():
        player.stop()  # Stop the current song
        output_text.insert(tk.END, "Skipped current song.\n")
        output_text.see(tk.END)
        play_next_song()  # Immediately play the next song
    else:
        output_text.insert(tk.END, "No song is currently playing.\n")
        output_text.see(tk.END)

def pause_song():
    """Pause the currently playing song."""
    global player

    if player and player.is_playing():
        player.pause()
        output_text.insert(tk.END, "Song paused.\n")
        output_text.see(tk.END)
    else:
        output_text.insert(tk.END, "No song is currently playing.\n")
        output_text.see(tk.END)

def resume_song():
    """Resume the paused song."""
    global player

    if player and not player.is_playing():
        player.play()
        output_text.insert(tk.END, "Song resumed.\n")
        output_text.see(tk.END)
    elif not player:
        output_text.insert(tk.END, "No song is currently paused or stopped.\n")
        output_text.see(tk.END)
    else:
        output_text.insert(tk.END, "No song is currently paused.\n")
        output_text.see(tk.END)

def stop_song():
    """Stop the currently playing song and clear the queue."""
    global player, playlist, current_song

    if player:
        player.stop()  # Stop the current song
        player = None  # Reset the player object
        current_song = None  # Reset the current song
        playlist.clear()  # Clear the queue
        output_text.insert(tk.END, "Playback stopped and queue cleared.\n")
        output_text.see(tk.END)
    else:
        output_text.insert(tk.END, "No song is currently playing.\n")
        output_text.see(tk.END)

def set_volume(volume_level):
    """Set the volume of the currently playing song."""
    global player

    if player:
        try:
            volume_level = int(volume_level)
            if 0 <= volume_level <= 100:  # Ensure volume is within valid range
                player.audio_set_volume(volume_level)
                output_text.insert(tk.END, f"Volume set to {volume_level}.\n")
                output_text.see(tk.END)
            else:
                output_text.insert(tk.END, "Volume must be between 0 and 100.\n")
                output_text.see(tk.END)
        except ValueError:
            output_text.insert(tk.END, "Invalid volume level. Use a number between 0 and 100.\n")
            output_text.see(tk.END)
    else:
        output_text.insert(tk.END, "No song is currently playing.\n")
        output_text.see(tk.END)

def handle_command(command, output_text):
    """Handle user commands."""
    global playlist

    if command.startswith("play "):
        query = command[5:]
        if not query:
            output_text.insert(tk.END, "Please specify a song or playlist.\n")
            return

        # Get the stream URL(s)
        urls = get_stream_url(query)
        if urls:
            output_text.insert(tk.END, f"Added to queue: {query}\n")
            play_stream(urls)
        else:
            output_text.insert(tk.END, "No results found.\n")
    elif command.startswith("volume "):
        volume_level = command[7:]
        set_volume(volume_level)
    elif command == "clear":
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
        output_text.insert(tk.END, "Unknown command. Use 'play <song/playlist>', 'volume <0-100>', 'clear', 'skip', 'pause', 'resume', 'stop', or 'exit'.\n")

    # Auto-scroll to the bottom
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
    keyboard.add_hotkey(keybinds["play"], lambda: play_stream(["your_default_song_url_here"]))  # Replace with actual URL
    keyboard.add_hotkey(keybinds["pause"], pause_song)
    keyboard.add_hotkey(keybinds["resume"], resume_song)
    keyboard.add_hotkey(keybinds["skip"], skip_song)
    keyboard.add_hotkey(keybinds["stop"], stop_song)
    keyboard.add_hotkey(keybinds["volume_up"], lambda: set_volume(min(100, player.audio_get_volume() + 10)))
    keyboard.add_hotkey(keybinds["volume_down"], lambda: set_volume(max(0, player.audio_get_volume() - 10)))

    keyboard.wait()  # Keep listening

# Start hotkey listener in a separate thread
hotkey_thread = threading.Thread(target=listen_for_hotkeys, daemon=True)
hotkey_thread.start()

def on_enter(event):
    """Handle the Enter key press in the input field."""
    command = input_field.get().strip()
    input_field.delete(0, tk.END)  # Clear the input field
    handle_command(command, output_text)

# Create the main window
root = tk.Tk()
root.title("Terminal")
root.geometry("200x100")  # Small window size

# Set background color for the window
root.configure(bg='black')  # Change 'black' to any color you like

# Create a scrolled text widget for output
output_text = scrolledtext.ScrolledText(
    root,
    wrap=tk.WORD,
    state='normal',
    height=1,
    bg='black',  # Background color
    fg='white',  # Text color
    insertbackground='white'  # Cursor color
)
output_text.pack(fill=tk.BOTH, expand=True)

# Create an input field at the bottom
input_field = tk.Entry(
    root,
    bg='black',  # Background color
    fg='white',  # Text color
    insertbackground='white'  # Cursor color
)
input_field.pack(fill=tk.X, padx=5, pady=5)
input_field.bind("<Return>", on_enter)  # Bind Enter key to the input field

# Start the Tkinter main loop
root.mainloop()