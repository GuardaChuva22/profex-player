# Standard Library Imports
import json
import logging
import os
import random # <-- Added for shuffle
import subprocess
import threading
import time
import tkinter as tk
import urllib.parse # <-- Added for URL decoding in queue view

# Third-Party Imports
# Ensure you have these installed: pip install python-vlc Pillow pystray keyboard yt-dlp spotipy
import keyboard
import pystray
from typing import TypeAlias # Import TypeAlias
import spotipy
import vlc
import yt_dlp as youtube_dl
from PIL import Image, ImageDraw
from spotipy.oauth2 import SpotifyClientCredentials

# Define the alias
PystrayIconType: TypeAlias = pystray.Icon # type: ignore

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

# --- Constants ---
APP_NAME = "Windows Defender Terminal"
WINDOW_TITLE = APP_NAME
TRAY_ICON_NAME = APP_NAME
DEFAULT_IDLE_TIMEOUT = 120  # seconds
DEFAULT_VOLUME = 50
CONFIG_FILE_PATH = os.path.join("lib", "config", "config.json")
ICON_PATH = os.path.join("lib", "icons", "icon.ico")
ERROR_SOUND_PATH = os.path.join("lib", "sounds", "error.mp3")
PLAYLISTS_DIR = os.path.join("lib", "playlists") # <-- Added directory for playlists


# Global variable for the VLC player instance
player: vlc.MediaPlayer | None = None
last_activity_time = time.time() # Used for idle timeout

# --- Configuration Loading ---
def load_config() -> dict:
    """Loads configuration from JSON file, using defaults if necessary."""
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
        "skip_backward": "ctrl+alt+left",
        "loop_toggle": "ctrl+alt+l",
        "shuffle_queue": "ctrl+alt+h", # <-- Added shuffle hotkey default
        "default_volume": DEFAULT_VOLUME,
        "idle_timeout": DEFAULT_IDLE_TIMEOUT,
        "CLIENT_ID": "YOUR_CLIENT_ID_HERE",
        "CLIENT_SECRET": "YOUR_CLIENT_SECRET_HERE"
    }

    try:
        os.makedirs(os.path.dirname(CONFIG_FILE_PATH), exist_ok=True)
        # Also ensure playlist dir exists during config load
        os.makedirs(PLAYLISTS_DIR, exist_ok=True)

        if os.path.exists(CONFIG_FILE_PATH):
            try:
                with open(CONFIG_FILE_PATH, "r", encoding='utf-8') as f: # Added encoding
                    user_config = json.load(f)
                # Merge defaults with user config, user config takes precedence
                config = {**config_defaults, **user_config}
                logging.info(f"Loaded configuration from {CONFIG_FILE_PATH}")
            except json.JSONDecodeError as e:
                logging.error(f"Error decoding {CONFIG_FILE_PATH}: {e}. Using defaults.")
                config = config_defaults
            except Exception as e:
                 logging.error(f"Error reading config file: {e}. Using default settings.")
                 config = config_defaults
        else:
            config = config_defaults
            try:
                with open(CONFIG_FILE_PATH, "w", encoding='utf-8') as f: # Added encoding
                    json.dump(config_defaults, f, indent=4)
                logging.info(f"Created default configuration file at {CONFIG_FILE_PATH}")
                logging.info(f"IMPORTANT: Please edit {CONFIG_FILE_PATH} and add your CLIENT_ID and CLIENT_SECRET.")
            except Exception as e:
                logging.error(f"Failed to write default config file: {e}")

        # Validate numeric values (volume)
        try:
            vol = int(config.get("default_volume", DEFAULT_VOLUME))
            config["default_volume"] = max(0, min(100, vol))
        except (ValueError, TypeError):
            logging.warning("Invalid default_volume in config, using default.")
            config["default_volume"] = DEFAULT_VOLUME

        # Validate numeric values (timeout)
        try:
            timeout = int(config.get("idle_timeout", DEFAULT_IDLE_TIMEOUT))
            config["idle_timeout"] = timeout # Allow 0 or negative to disable
        except (ValueError, TypeError):
            logging.warning("Invalid idle_timeout in config, using default.")
            config["idle_timeout"] = DEFAULT_IDLE_TIMEOUT

        # Ensure essential keys exist even if loaded from old file
        # (including new shuffle hotkey)
        for key, default_value in config_defaults.items():
            if key not in config:
                config[key] = default_value
                logging.info(f"Added missing config key '{key}' with default value.")

        return config

    except Exception as e:
        logging.error(f"Critical error during config loading: {e}. Using minimal defaults.")
        # Fallback with necessary defaults
        config_defaults["default_volume"] = max(0, min(100, int(DEFAULT_VOLUME)))
        config_defaults["idle_timeout"] = int(DEFAULT_IDLE_TIMEOUT)
        config_defaults["CLIENT_ID"] = "YOUR_CLIENT_ID_HERE"
        config_defaults["CLIENT_SECRET"] = "YOUR_CLIENT_SECRET_HERE"
        config_defaults["shuffle_queue"] = "ctrl+alt+h" # Ensure it's here too
        return config_defaults

# Load config once at startup
CONFIG = load_config()

# --- API Setup using config.json ---
CLIENT_ID = CONFIG.get("CLIENT_ID")
CLIENT_SECRET = CONFIG.get("CLIENT_SECRET")
sp = None  # Initialize API client as None

if not CLIENT_ID or CLIENT_ID == "YOUR_CLIENT_ID_HERE" or \
   not CLIENT_SECRET or CLIENT_SECRET == "YOUR_CLIENT_SECRET_HERE":
    logging.warning("CLIENT_ID or CLIENT_SECRET is missing or not set in config.json.")
    logging.warning(f"Please add your credentials to: {CONFIG_FILE_PATH}")
    logging.warning("API-dependent features (e.g., Spotify links) will be disabled.")
else:
    try:
        auth_manager = SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
        sp = spotipy.Spotify(auth_manager=auth_manager)
        sp.search(q='test', type='track', limit=1) # Test authentication
        logging.info("API authentication successful using credentials from config.json.")
    except spotipy.SpotifyException as e:
        logging.error(f"API authentication failed (SpotifyException): {e}")
        logging.error("Please ensure CLIENT_ID and CLIENT_SECRET in config.json are correct.")
        sp = None
    except Exception as e:
        logging.error(f"An unexpected error occurred during API authentication: {e}")
        sp = None
# --- End API Setup ---


# --- Helper Functions (is_spotify_url, get_spotify_track_search_queries, play_error_sound, get_stream_url) ---
# ... (These functions remain unchanged from your previous version) ...
def is_spotify_url(url: str) -> bool:
    """Check if the URL is a Spotify URL."""
    return url.startswith(("https://open.spotify.com/", "spotify:"))

def get_spotify_track_search_queries(url: str) -> list[str] | None:
    """Extract track search queries (Track Name Artist1, Artist2) from a Spotify URL."""
    if not sp: # This check remains valid
        logging.error("API client not authenticated. Cannot process Spotify URL.")
        logging.error(f"Ensure CLIENT_ID and CLIENT_SECRET are set correctly in {CONFIG_FILE_PATH}")
        return None
    try:
        if "track" in url:  # Single track
            track_info = sp.track(url)
            if not track_info: return None
            artists = ", ".join([artist["name"] for artist in track_info["artists"]])
            return [f"{track_info['name']} {artists}"]
        elif "playlist" in url:  # Playlist
            results = sp.playlist_items(url, fields='items(track(name, artists(name)))')
            if not results: return None
            queries = []
            for item in results["items"]:
                if item and item["track"]: # Handle potential null tracks in playlists
                    track = item["track"]
                    artists = ", ".join([artist["name"] for artist in track["artists"]])
                    queries.append(f"{track['name']} {artists}")
            return queries if queries else None
        else:
            logging.warning(f"Unsupported Spotify URL type: {url}")
            return None
    except Exception as e:
        logging.error(f"Error fetching Spotify data for {url}: {e}")
        return None

def play_error_sound():
    """Play an error sound."""
    if not os.path.exists(ERROR_SOUND_PATH):
        logging.warning(f"Error sound file not found at: {ERROR_SOUND_PATH}")
        return
    try:
        error_player = vlc.MediaPlayer(ERROR_SOUND_PATH)
        error_player.play()
        time.sleep(0.1) # Small delay to allow playback start
        error_player.release() # Release immediately
    except Exception as e:
        logging.error(f"Error playing error sound: {e}")

def get_stream_url(query: str) -> list[str] | None:
    """Get direct audio stream URL(s) from YouTube based on query or URL."""
    global last_activity_time
    last_activity_time = time.time()

    ydl_opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "extract_audio": True,
        "noplaylist": True,
        "no_warnings": True,
        "source_address": "0.0.0.0",
        "default_search": "ytsearch1",
        "skip_download": True,
        "logtostderr": False,
        "ignoreerrors": True,
    }
    urls = []
    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            logging.info(f"Searching for: {query}")
            info = ydl.extract_info(query, download=False)
            if not info:
                logging.warning(f"Could not find anything for query: {query}")
                return None
            if "entries" in info and info["entries"]:
                logging.info(f"Processing {len(info['entries'])} entries from playlist/search result...")
                for entry in info["entries"]:
                    if entry and entry.get("url"):
                        urls.append(entry["url"])
                        logging.debug(f"Found stream URL for: {entry.get('title', 'Unknown Entry')}")
                    else:
                        logging.warning(f"Skipping unavailable video in playlist: {entry.get('title', 'Unknown Entry') if entry else 'Invalid Entry'}")
            elif info.get("url"):
                 urls.append(info["url"])
                 logging.info(f"Found stream URL for: {info.get('title', 'Unknown Title')}")
            else:
                 logging.warning(f"No stream URL found in result for: {query}")
                 return None
        return urls if urls else None
    except youtube_dl.utils.DownloadError as e:
        logging.error(f"yt-dlp download error for '{query}': {e}")
        play_error_sound()
        return None
    except Exception as e:
        logging.error(f"Unexpected error retrieving stream URL for '{query}': {e}")
        play_error_sound()
        return None


# --- Playlist Management ---
class PlaylistManager:
    def __init__(self):
        self.playlist: list[str] = []
        self.lock = threading.Lock()
        self.current_song_url: str | None = None
        self.loop_queue = False
        # Playlist directory ensured during config load

    def add_song(self, url: str):
        with self.lock:
            self.playlist.append(url)
            logging.info(f"Added to queue: {url[:50]}...")

    def add_songs(self, urls: list[str]):
        with self.lock:
            self.playlist.extend(urls)
            logging.info(f"Added {len(urls)} songs to the queue.")

    def get_next_song(self) -> str | None:
        # Method unchanged
        with self.lock:
            if not self.playlist:
                if self.loop_queue and self.current_song_url:
                    logging.info("Looping: Re-playing last song.")
                    return self.current_song_url
                else:
                    self.current_song_url = None
                    return None
            next_song_url = self.playlist.pop(0)
            if self.loop_queue and self.current_song_url:
                if not self.playlist or self.playlist[-1] != self.current_song_url:
                    self.playlist.append(self.current_song_url)
            self.current_song_url = next_song_url
            return self.current_song_url

    def toggle_loop(self):
        # Method unchanged
        with self.lock:
            self.loop_queue = not self.loop_queue
            status = "ON" if self.loop_queue else "OFF"
            logging.info(f"Loop queue toggled: {status}")
            if self.loop_queue and self.current_song_url and self.current_song_url not in self.playlist:
                 self.playlist.append(self.current_song_url)
            print(f"Loop queue: {status}")
            return self.loop_queue

    def clear(self):
        # Method unchanged
        with self.lock:
            self.playlist.clear()
            self.current_song_url = None
            logging.info("Playlist cleared.")

    def is_empty(self) -> bool:
        # Method unchanged
        with self.lock:
            return not bool(self.playlist)

    # --- NEW/MODIFIED METHODS for Queue Management ---
    def shuffle(self):
        """Shuffles the current playlist."""
        with self.lock:
            if len(self.playlist) > 1:
                random.shuffle(self.playlist)
                logging.info("Playlist shuffled.")
                print("Playlist shuffled.") # User feedback
            elif self.playlist:
                 logging.info("Only one song in queue, cannot shuffle.")
                 print("Only one song in queue, cannot shuffle.")
            else:
                 logging.info("Playlist is empty, cannot shuffle.")
                 print("Playlist is empty, cannot shuffle.")

    def _get_playlist_filepath(self, filename: str) -> str | None:
        """Constructs and validates a playlist filepath."""
        if not filename:
            logging.error("Playlist filename cannot be empty.")
            return None
        basename = os.path.basename(filename.strip())
        if not basename:
            logging.error("Playlist filename cannot be empty after stripping.")
            return None
        if not basename.lower().endswith((".txt", ".m3u")): # Allow .txt or .m3u
             basename += ".txt" # Default to .txt
        # Basic check for potentially problematic characters
        if any(c in basename for c in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']):
             logging.error(f"Invalid characters in playlist filename: {basename}")
             return None
        return os.path.join(PLAYLISTS_DIR, basename)

    def save_queue(self, filename: str):
        """Saves the current playlist URLs to a file."""
        filepath = self._get_playlist_filepath(filename)
        if not filepath:
            play_error_sound()
            print("Error: Invalid playlist filename.")
            return

        with self.lock:
            playlist_copy = list(self.playlist)

        if not playlist_copy:
            logging.warning("Queue is empty, nothing to save.")
            print("Queue is empty, nothing to save.")
            return

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                for url in playlist_copy:
                    f.write(url + '\n')
            logging.info(f"Playlist saved to {filepath} ({len(playlist_copy)} tracks).")
            print(f"Playlist saved as '{os.path.basename(filepath)}'")
        except IOError as e:
            logging.error(f"Error saving playlist to {filepath}: {e}")
            print(f"Error: Could not save playlist file: {e}")
            play_error_sound()
        except Exception as e:
            logging.error(f"Unexpected error saving playlist: {e}")
            print(f"Error: An unexpected error occurred while saving: {e}")
            play_error_sound()

    def load_queue(self, filename: str, append: bool = False):
        """Loads playlist URLs from a file, replacing or appending to the current queue."""
        filepath = self._get_playlist_filepath(filename)
        if not filepath:
            play_error_sound()
            print("Error: Invalid playlist filename.")
            return

        if not os.path.exists(filepath):
            logging.error(f"Playlist file not found: {filepath}")
            print(f"Error: Playlist file '{os.path.basename(filepath)}' not found.")
            play_error_sound()
            return

        loaded_urls = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    url = line.strip()
                    if url and not url.startswith('#'): # Ignore empty lines and comments
                        loaded_urls.append(url)

            if not loaded_urls:
                logging.warning(f"Playlist file '{filepath}' is empty or contains no valid URLs.")
                print(f"Playlist file '{os.path.basename(filepath)}' is empty.")
                return

            with self.lock:
                if not append:
                    self.playlist.clear()
                    self.current_song_url = None
                    action_msg = "replaced"
                else:
                    action_msg = "appended to"
                self.playlist.extend(loaded_urls)

            logging.info(f"Playlist loaded from {filepath} ({len(loaded_urls)} tracks), {action_msg} queue.")
            print(f"Loaded {len(loaded_urls)} tracks from '{os.path.basename(filepath)}'. Queue {action_msg}.")

        except IOError as e:
            logging.error(f"Error loading playlist from {filepath}: {e}")
            print(f"Error: Could not load playlist file: {e}")
            play_error_sound()
        except Exception as e:
            logging.error(f"Unexpected error loading playlist: {e}")
            print(f"Error: An unexpected error occurred while loading: {e}")
            play_error_sound()

    def view_queue(self) -> list[str]:
        """Returns a copy of the current playlist."""
        with self.lock:
            return list(self.playlist)

    def remove_at(self, index: int) -> bool:
        """Removes a song at the specified index (0-based)."""
        with self.lock:
            if 0 <= index < len(self.playlist):
                removed_url = self.playlist.pop(index)
                logging.info(f"Removed item at index {index}: {removed_url[:50]}...")
                return True
            else:
                logging.warning(f"Invalid index for removal: {index}. Queue size: {len(self.playlist)}")
                return False
    # --- End Queue Management Methods ---


# Initialize playlist manager
playlist_manager = PlaylistManager()

# --- Playback Control Functions ---
# ... (play_stream, skip_song, pause_song, resume_song, stop_song, set_volume, adjust_volume, seek remain the same) ...
def play_stream(urls: list[str]):
    """Add song(s) to the queue."""
    global last_activity_time
    last_activity_time = time.time()
    if urls:
        playlist_manager.add_songs(urls)
    else:
        logging.warning("play_stream called with no URLs.")
        play_error_sound()

def skip_song():
    """Skip the current song."""
    global player, last_activity_time
    last_activity_time = time.time()
    logging.info("Skip requested.")
    if player:
        player.stop()

def pause_song():
    """Pause the current song."""
    global player, last_activity_time
    last_activity_time = time.time()
    if player and player.is_playing():
        player.pause()
        logging.info("Playback paused.")

def resume_song():
    """Resume the paused song."""
    global player, last_activity_time
    last_activity_time = time.time()
    if player and not player.is_playing():
        player.play()
        logging.info("Playback resumed.")

def stop_song():
    """Stop the current song and clear the queue."""
    global player, last_activity_time
    last_activity_time = time.time()
    logging.info("Stop requested. Clearing queue and stopping playback.")
    playlist_manager.clear()
    if player:
        player.stop()
        player.release()
        player = None

def set_volume(volume_level_str: str):
    """Set the volume of the current song."""
    global player, last_activity_time
    last_activity_time = time.time()
    try:
        vol = int(volume_level_str)
        if 0 <= vol <= 100:
            if player:
                player.audio_set_volume(vol)
                logging.info(f"Volume set to {vol}")
            else:
                logging.warning("Cannot set volume: No player active.")
        else:
            logging.warning(f"Invalid volume level: {vol}. Must be between 0 and 100.")
            play_error_sound()
    except ValueError:
        logging.error(f"Invalid volume input: '{volume_level_str}'. Must be a number.")
        play_error_sound()

def adjust_volume(delta: int):
    """Adjust volume up or down."""
    global player, last_activity_time
    last_activity_time = time.time()
    if player:
        current_volume = player.audio_get_volume()
        new_volume = max(0, min(100, current_volume + delta))
        player.audio_set_volume(new_volume)
        logging.info(f"Volume adjusted to {new_volume}")
    else:
         logging.warning("Cannot adjust volume: No player active.")

def seek(delta_ms: int):
    """Seek forward or backward in the current song."""
    global player, last_activity_time
    last_activity_time = time.time()
    if player and player.is_seekable():
        current_time = player.get_time()
        new_time = max(0, current_time + delta_ms)
        player.set_time(new_time)
        direction = "forward" if delta_ms > 0 else "backward"
        logging.info(f"Seek {direction} by {abs(delta_ms)//1000}s. New time: {new_time//1000}s")
    elif player:
        logging.warning("Cannot seek: Stream is not seekable or player not active.")
    else:
        logging.warning("Cannot seek: No player active.")


# --- Command Handling ---
def handle_command(command: str):
    """Process commands entered in the GUI or potentially other sources."""
    global last_activity_time, playlist_manager # Ensure playlist_manager is accessible
    last_activity_time = time.time()
    command = command.strip()
    if not command:
        return

    parts = command.split(" ", 1)
    verb = parts[0].lower()
    args_str = parts[1].strip() if len(parts) > 1 else ""

    # --- Helper for queue display ---
    def display_queue_helper():
        queue_items = playlist_manager.view_queue()
        if not queue_items:
            print("Queue is empty.")
            logging.info("Queue is empty.")
            return

        print("\n--- Current Queue ---")
        for i, url in enumerate(queue_items):
            display_name = f"{i}: {url[:70]}..." # Default view
            try: # Attempt to decode title from common streaming URLs
                if "googlevideo.com" in url and "title=" in url:
                    title_part = url.split('title=')[1].split('&')[0]
                    decoded_title = urllib.parse.unquote_plus(title_part)
                    display_name = f"{i}: {decoded_title}"[:70] # Show index and decoded title
            except Exception:
                pass # Ignore decoding errors, use default display_name

            print(display_name)
        print(f"---------------------\nTotal items in queue: {len(queue_items)}\n")
        logging.info(f"Displayed queue with {len(queue_items)} items.")

    # --- Helper for remove ---
    def remove_from_queue_helper(index_str: str):
         if not index_str:
             print("Usage: remove <index_number>")
             play_error_sound()
             return
         try:
             index = int(index_str)
             if playlist_manager.remove_at(index):
                 print(f"Removed item at index {index}.")
             else:
                 play_error_sound()
                 print(f"Failed to remove item: Invalid index {index}.")
         except ValueError:
             play_error_sound()
             print(f"Invalid index: '{index_str}'. Please provide a number.")
         except Exception as e:
             play_error_sound()
             print(f"Error removing item: {e}")
             logging.error(f"Error in remove command: {e}")

     # --- Helper for loadqueue ---
    def load_queue_helper(args: str):
        append = False
        filename = args
        if args.startswith("-a ") or args.startswith("--append "):
            append = True
            filename = args.split(" ", 1)[1].strip()

        if not filename:
            print("Usage: loadqueue [--append|-a] <filename>")
            play_error_sound()
            return
        playlist_manager.load_queue(filename, append=append)

    # --- Command Actions Dictionary ---
    command_actions = {
        "play": lambda query: play_spotify_or_youtube(query) if query else print("Usage: play <query/url>"),
        "volume": lambda level: set_volume(level) if level else print("Usage: volume <0-100>"),
        "vol": lambda level: set_volume(level) if level else print("Usage: vol <0-100>"),
        "loop": lambda _: playlist_manager.toggle_loop(),
        "clear": lambda _: playlist_manager.clear(),
        "skip": lambda _: skip_song(),
        "pause": lambda _: pause_song(),
        "resume": lambda _: resume_song(),
        "stop": lambda _: stop_song(),
        "exit": lambda _: terminate_program(),
        "quit": lambda _: terminate_program(),
        "next": lambda _: skip_song(),
        "shuffle": lambda _: playlist_manager.shuffle(),
        "savequeue": lambda filename: playlist_manager.save_queue(filename) if filename else print("Usage: savequeue <filename>"),
        "loadqueue": load_queue_helper, # Use helper for append logic
        "queue": lambda _: display_queue_helper(),
        "list": lambda _: display_queue_helper(), # Alias
        "remove": lambda index_str: remove_from_queue_helper(index_str),
    }

    action = command_actions.get(verb)
    if action:
        try:
            # Pass the argument string (args_str) directly to the lambda/helper
            action(args_str)
        except TypeError as e:
            # More robust check for argument errors
            if "positional argument" in str(e) or "unexpected keyword argument" in str(e) or "missing" in str(e):
                 logging.error(f"Command '{verb}' usage error: {e}")
                 print(f"Usage error for command '{verb}'. Check arguments or use command without args.")
                 play_error_sound()
            else: # Re-raise other TypeErrors if needed
                 logging.error(f"Error executing command '{verb} {args_str}': {e}")
                 play_error_sound()
                 # raise e # Optionally re-raise for debugging
        except Exception as e:
            logging.error(f"Error executing command '{verb} {args_str}': {e}")
            play_error_sound()
    else:
        logging.warning(f"Unknown command: {command}")
        play_error_sound()

# ... (play_spotify_or_youtube function remains the same) ...
def play_spotify_or_youtube(query: str):
    """Helper to decide whether to process Spotify or YouTube."""
    # This function remains unchanged
    if not query:
        logging.warning("Play command received with no query.")
        play_error_sound()
        return
    if is_spotify_url(query):
        # ... (spotify handling) ...
        logging.info(f"Processing Spotify URL: {query}")
        search_queries = get_spotify_track_search_queries(query)
        if search_queries:
            all_urls = []
            for sq in search_queries:
                urls = get_stream_url(sq) # Get URL(s) for each track
                if urls:
                    all_urls.extend(urls) # Collect all stream URLs
            if all_urls:
                 play_stream(all_urls)
            else:
                 logging.error(f"Could not find any playable streams for Spotify URL: {query}")
                 play_error_sound()
        else:
            logging.error(f"Could not get track info from Spotify URL: {query}")
            play_error_sound()
    else:
        # ... (youtube handling) ...
        logging.info(f"Processing YouTube query/URL: {query}")
        urls = get_stream_url(query)
        if urls:
            play_stream(urls)
        else:
            logging.error(f"Could not find playable stream for query: {query}")
            play_error_sound()

# --- Background Threads ---

# ... (playback_loop remains the same) ...
def playback_loop():
    """Continuously play songs from the playlist."""
    global player, last_activity_time
    default_volume = CONFIG.get("default_volume", DEFAULT_VOLUME)
    while True:
        next_song_url = playlist_manager.get_next_song()
        if next_song_url:
            logging.info(f"Attempting to play: {next_song_url[:70]}...")
            last_activity_time = time.time()
            try:
                if player:
                    player.release()
                    player = None
                player = vlc.MediaPlayer(next_song_url)
                player.audio_set_volume(default_volume)
                player.play()
                logging.info(f"Playback started. Volume: {default_volume}")
                # Monitor playback state
                while True:
                    if not player: break
                    state = player.get_state()
                    if state == vlc.State.Playing:
                         last_activity_time = time.time()
                    if state in (vlc.State.Ended, vlc.State.Stopped, vlc.State.Error):
                        log_level = logging.INFO if state != vlc.State.Error else logging.ERROR
                        logging.log(log_level, f"Playback finished/stopped/error (State: {state})")
                        break
                    time.sleep(0.2)
                if player:
                    player.release()
                    player = None
            except Exception as e:
                logging.error(f"Error during playback of {next_song_url[:70]}...: {e}")
                if player:
                    player.release()
                    player = None
                play_error_sound()
                time.sleep(1)
        else:
            time.sleep(0.5)


def listen_for_hotkeys():
    """Listen for global hotkeys defined in the config."""
    logging.info("Starting hotkey listener.")
    try:
        keyboard.add_hotkey(CONFIG["terminate"], terminate_program)
        keyboard.add_hotkey(CONFIG["play"], resume_song)
        keyboard.add_hotkey(CONFIG["pause"], pause_song)
        keyboard.add_hotkey(CONFIG["resume"], resume_song)
        keyboard.add_hotkey(CONFIG["skip"], skip_song)
        keyboard.add_hotkey(CONFIG["stop"], stop_song)
        keyboard.add_hotkey(CONFIG["volume_up"], lambda: adjust_volume(10))
        keyboard.add_hotkey(CONFIG["volume_down"], lambda: adjust_volume(-10))
        keyboard.add_hotkey(CONFIG["skip_forward"], lambda: seek(10000))
        keyboard.add_hotkey(CONFIG["skip_backward"], lambda: seek(-10000))
        keyboard.add_hotkey(CONFIG["loop_toggle"], playlist_manager.toggle_loop)
        # --- Added Shuffle Hotkey ---
        if "shuffle_queue" in CONFIG: # Check if key exists in config
            keyboard.add_hotkey(CONFIG["shuffle_queue"], playlist_manager.shuffle)
        else:
             logging.warning("Config key 'shuffle_queue' not found. Shuffle hotkey disabled.")
        # --- End Added ---

        logging.info("Hotkeys registered:")
        logged_keys = set() # Prevent duplicate logging if alias used
        for key, val in CONFIG.items():
             # Exclude non-hotkey config entries and credentials
             if key not in ["default_volume", "idle_timeout", "CLIENT_ID", "CLIENT_SECRET"] and val not in logged_keys:
                 logging.info(f"  {key}: {val}")
                 logged_keys.add(val)

        keyboard.wait()
    except ValueError as e:
         # Catch specific error from keyboard lib if hotkey is invalid
         logging.error(f"Invalid hotkey configuration: {e}. Please check config.json.")
         logging.error("Hotkeys may not function correctly.")
         # Keep thread alive maybe, or terminate? For now, just log.
    except Exception as e:
        logging.error(f"Failed to initialize or run hotkey listener: {e}")
        logging.error("Hotkeys will not function.")


# ... (idle_monitor, monitor_lock_tasklist remain the same) ...
def idle_monitor():
    """Terminates the app if idle for too long."""
    global last_activity_time
    timeout = CONFIG.get("idle_timeout", DEFAULT_IDLE_TIMEOUT)
    if timeout <= 0:
        logging.info("Idle timeout disabled (timeout <= 0 in config).")
        return
    logging.info(f"Idle monitor started with timeout: {timeout} seconds.")
    while True:
        try:
            idle_duration = time.time() - last_activity_time
            if idle_duration > timeout:
                logging.info(f"Idle timeout ({timeout}s) reached. Terminating application.")
                terminate_program()
        except Exception as e:
            logging.error(f"Error in idle monitor loop: {e}")
        time.sleep(5)

def monitor_lock_tasklist():
    """Terminates the app if Windows lock screen (LogonUI.exe) is detected."""
    logging.info("Windows lock screen monitor started.")
    while True:
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            output = subprocess.check_output(
                "TASKLIST", shell=True, encoding="cp850", errors="ignore", startupinfo=startupinfo
            )
            if "LogonUI.exe" in output:
                logging.info("Windows lock screen detected (LogonUI.exe running). Terminating.")
                terminate_program()
        except FileNotFoundError:
             logging.error("TASKLIST command not found. Cannot monitor lock screen.")
             return
        except Exception as e:
            logging.error(f"Error checking TASKLIST for lock screen: {e}")
        time.sleep(10)


# --- GUI / Tray Icon ---
# ... (create_tray_image, setup_tray_icon, hide_window, on_enter_pressed, terminate_program remain the same) ...
def create_tray_image() -> Image.Image:
    """Creates the tray icon image, falling back to a default."""
    if os.path.exists(ICON_PATH):
        try:
            image = Image.open(ICON_PATH)
            image = image.resize((16, 16), Image.Resampling.LANCZOS)
            return image
        except Exception as e:
            logging.error(f"Error loading tray icon '{ICON_PATH}': {e}")
    logging.warning("Using fallback tray icon.")
    image = Image.new("RGB", (16, 16), color="darkblue")
    dc = ImageDraw.Draw(image)
    dc.rectangle([(4, 4), (12, 12)], fill="lightblue")
    return image

def setup_tray_icon(root_window: tk.Tk) -> PystrayIconType:
    """Sets up the system tray icon and its menu."""
    def on_show(icon, item):
        logging.debug("Show action triggered from tray.")
        root_window.after(0, position_window)
        root_window.after(0, root_window.deiconify)
        root_window.after(10, root_window.focus_force)

    def position_window():
        root_window.update_idletasks()
        screen_width = root_window.winfo_screenwidth()
        screen_height = root_window.winfo_screenheight()
        window_width = 250
        window_height = 40
        x_pos = screen_width - window_width - 15
        y_pos = screen_height - window_height - 80
        root_window.geometry(f"{window_width}x{window_height}+{x_pos}+{y_pos}")
        logging.debug(f"Positioned window at {x_pos}, {y_pos}")

    def on_exit(icon, item):
        logging.info("Exit action triggered from tray.")
        icon.stop()
        root_window.after(0, terminate_program)

    menu = pystray.Menu(
        pystray.MenuItem("Show", on_show, default=True),
        pystray.MenuItem("Exit", on_exit),
    )
    icon = pystray.Icon(TRAY_ICON_NAME.lower().replace(" ", "_"), create_tray_image(), TRAY_ICON_NAME, menu)
    return icon

def hide_window(root_window: tk.Tk):
    """Hide the main window."""
    logging.debug("Hiding main window.")
    root_window.withdraw()

def on_enter_pressed(event: tk.Event, input_widget: tk.Entry):
    """Handle Enter key press in the input field."""
    command = input_widget.get().strip()
    logging.info(f"Command entered: {command}")
    input_widget.delete(0, tk.END)
    if command:
        # Call handle_command in the main thread (it's already there)
        # Use root.after to ensure it runs in the event loop if needed elsewhere,
        # but here direct call is fine as it's triggered by event binding.
        handle_command(command)

def terminate_program():
    """Cleanly shuts down the application."""
    logging.info("Initiating shutdown sequence...")
    global player
    if player:
        try:
            player.stop()
            player.release()
            player = None
            logging.info("VLC Player stopped and released.")
        except Exception as e:
            logging.error(f"Error stopping/releasing VLC player: {e}")
    try:
        if root and root.winfo_exists():
            root.destroy()
            logging.info("Tkinter window destroyed.")
    except Exception as e:
        logging.warning(f"Error destroying Tkinter window: {e}")
    logging.info("Exiting application.")
    os._exit(0)


# --- Main Execution ---
if __name__ == "__main__":
    # --- Tkinter GUI Setup ---
    root = tk.Tk()
    root.title(WINDOW_TITLE)
    root.resizable(False, False)
    try:
        if os.path.exists(ICON_PATH):
            root.iconbitmap(ICON_PATH)
    except Exception as e:
        logging.error(f"Failed to set window icon: {e}")
    root.geometry("250x40")
    root.configure(bg="black")
    root.protocol("WM_DELETE_WINDOW", lambda: hide_window(root))

    input_field = tk.Entry(root, bg="gray10", fg="white", insertbackground="white", font=("Consolas", 10))
    input_field.pack(fill=tk.X, padx=5, pady=5, expand=True)
    input_field.bind("<Return>", lambda event: on_enter_pressed(event, input_field))

    # --- System Tray Setup ---
    tray_icon = setup_tray_icon(root)
    tray_thread = threading.Thread(target=tray_icon.run, daemon=True)
    tray_thread.start()
    logging.info("System tray icon thread started.")

    root.withdraw() # Start hidden

    # --- Start Background Threads ---
    playback_thread = threading.Thread(target=playback_loop, daemon=True)
    playback_thread.start()
    logging.info("Playback loop thread started.")

    hotkey_thread = threading.Thread(target=listen_for_hotkeys, daemon=True)
    hotkey_thread.start()

    idle_thread = threading.Thread(target=idle_monitor, daemon=True)
    idle_thread.start()

    if os.name == 'nt':
        lock_thread = threading.Thread(target=monitor_lock_tasklist, daemon=True)
        lock_thread.start()
    else:
        logging.info("Windows lock screen monitor not started (not on Windows).")

    # --- Start GUI Main Loop ---
    logging.info(f"{APP_NAME} started successfully. Main window is hidden.")
    logging.info("Use tray icon to show/exit or hotkeys for control.")
    try:
        root.mainloop()
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received.")
    finally:
        terminate_program()