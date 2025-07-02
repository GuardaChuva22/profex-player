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
        "play": "ctrl+alt+p", # Note: 'play' hotkey might be less used if playback starts on adding songs
        "pause": "ctrl+alt+space",
        "resume": "ctrl+alt+r",
        "skip": "ctrl+alt+s",
        "stop": "ctrl+alt+q",
        "volume_up": "ctrl+alt+up",
        "volume_down": "ctrl+alt+down",
        "skip_forward": "ctrl+alt+right",
        "skip_backward": "ctrl+alt+left",
        "loop_toggle": "ctrl+alt+l",
        "shuffle_queue": "ctrl+alt+h",
        "view_queue_hotkey": "ctrl+alt+v", # Example for a new feature
        "default_volume": DEFAULT_VOLUME,
        "idle_timeout": DEFAULT_IDLE_TIMEOUT,
        "CLIENT_ID": "YOUR_CLIENT_ID_HERE",
        "CLIENT_SECRET": "YOUR_CLIENT_SECRET_HERE",
        "enable_discord_rpc": False, # Example for a new boolean feature
        "discord_rpc_update_interval": 15 # seconds
    }

    config = {}
    needs_saving = False

    try:
        os.makedirs(os.path.dirname(CONFIG_FILE_PATH), exist_ok=True)
        os.makedirs(PLAYLISTS_DIR, exist_ok=True)

        if os.path.exists(CONFIG_FILE_PATH):
            try:
                with open(CONFIG_FILE_PATH, "r", encoding='utf-8') as f:
                    user_config = json.load(f)
                # Start with defaults, then update with user_config
                config = {**config_defaults, **user_config}
                logging.info(f"Loaded configuration from {CONFIG_FILE_PATH}")

                # Check for any keys in user_config that are not in defaults (e.g. typos, old keys)
                for key in list(user_config.keys()): # list() for safe removal during iteration
                    if key not in config_defaults:
                        logging.warning(f"Obsolete or unknown key '{key}' found in config. It will be ignored and removed if config is re-saved.")
                        # Optionally, remove it if you want to clean up user's config file on next save.
                        # For now, we just ignore it unless needs_saving is triggered by something else.

            except json.JSONDecodeError as e:
                logging.error(f"Error decoding {CONFIG_FILE_PATH}: {e}. Using defaults and attempting to recreate.")
                config = config_defaults
                needs_saving = True # Mark for re-saving with defaults
            except Exception as e:
                 logging.error(f"Error reading config file: {e}. Using default settings and attempting to recreate.")
                 config = config_defaults
                 needs_saving = True # Mark for re-saving with defaults
        else:
            logging.info(f"Configuration file not found at {CONFIG_FILE_PATH}. Creating with defaults.")
            config = config_defaults
            needs_saving = True

        # Validate and sanitize specific configuration values
        # Volume
        try:
            vol = int(config.get("default_volume", DEFAULT_VOLUME))
            config["default_volume"] = max(0, min(100, vol))
        except (ValueError, TypeError):
            logging.warning(f"Invalid default_volume '{config.get('default_volume')}' in config, using default {DEFAULT_VOLUME}.")
            config["default_volume"] = DEFAULT_VOLUME
            needs_saving = True

        # Idle Timeout
        try:
            timeout = int(config.get("idle_timeout", DEFAULT_IDLE_TIMEOUT))
            config["idle_timeout"] = timeout # Allow 0 or negative to disable
        except (ValueError, TypeError):
            logging.warning(f"Invalid idle_timeout '{config.get('idle_timeout')}' in config, using default {DEFAULT_IDLE_TIMEOUT}.")
            config["idle_timeout"] = DEFAULT_IDLE_TIMEOUT
            needs_saving = True

        # Discord RPC Update Interval
        try:
            rpc_interval = int(config.get("discord_rpc_update_interval", 15))
            config["discord_rpc_update_interval"] = max(5, rpc_interval) # Min 5 seconds
        except (ValueError, TypeError):
            logging.warning(f"Invalid discord_rpc_update_interval '{config.get('discord_rpc_update_interval')}' in config, using default 15.")
            config["discord_rpc_update_interval"] = 15
            needs_saving = True

        # Ensure all default keys exist in the current config, adding them if missing
        for key, default_value in config_defaults.items():
            if key not in config:
                logging.info(f"Adding missing config key '{key}' with default value: {default_value}")
                config[key] = default_value
                needs_saving = True
            # Ensure boolean values are actual booleans
            elif isinstance(default_value, bool) and not isinstance(config[key], bool):
                logging.warning(f"Config value for '{key}' ('{config[key]}') is not a boolean. Attempting to convert or using default.")
                if str(config[key]).lower() in ['true', '1', 'yes']:
                    config[key] = True
                elif str(config[key]).lower() in ['false', '0', 'no']:
                    config[key] = False
                else:
                    config[key] = default_value
                needs_saving = True


        # Validate hotkey strings (basic validation - more complex validation is hard without trying to register them)
        # This is a simplistic check. The `keyboard` library will do more robust checks later.
        hotkey_keys = [k for k, v in config_defaults.items() if isinstance(v, str) and ('hotkey' in k or k in [
            "terminate", "play", "pause", "resume", "skip", "stop", "volume_up", "volume_down",
            "skip_forward", "skip_backward", "loop_toggle", "shuffle_queue"
        ])]
        for key in hotkey_keys:
            if not isinstance(config[key], str) or not config[key].strip():
                logging.warning(f"Hotkey '{key}' is invalid (empty or not a string: '{config[key]}'). Resetting to default: '{config_defaults[key]}'.")
                config[key] = config_defaults[key]
                needs_saving = True
            # Consider adding a regex here for basic format check if desired, e.g., r"([a-z0-9]+|\S+)(\s*\+\s*([a-z0-9]+|\S+))*"
            # For now, relies on the keyboard library to fail during registration for more complex issues.

        if needs_saving:
            try:
                with open(CONFIG_FILE_PATH, "w", encoding='utf-8') as f:
                    json.dump(config, f, indent=4)
                logging.info(f"Configuration file updated/created at {CONFIG_FILE_PATH}")
                if not os.path.exists(CONFIG_FILE_PATH): # If it was newly created
                     logging.info(f"IMPORTANT: Please review {CONFIG_FILE_PATH}, especially CLIENT_ID and CLIENT_SECRET if you use Spotify features.")
            except Exception as e:
                logging.error(f"Failed to write/update config file at {CONFIG_FILE_PATH}: {e}")

        return config

    except Exception as e:
        logging.critical(f"Critical error during config loading: {e}. Using minimal defaults.")
        # Fallback with necessary defaults, ensuring types are correct
        minimal_config = {
            "terminate": "ctrl+shift+q", "play": "ctrl+alt+p", "pause": "ctrl+alt+space",
            "resume": "ctrl+alt+r", "skip": "ctrl+alt+s", "stop": "ctrl+alt+q",
            "volume_up": "ctrl+alt+up", "volume_down": "ctrl+alt+down",
            "skip_forward": "ctrl+alt+right", "skip_backward": "ctrl+alt+left",
            "loop_toggle": "ctrl+alt+l", "shuffle_queue": "ctrl+alt+h",
            "view_queue_hotkey": "ctrl+alt+v",
            "default_volume": int(DEFAULT_VOLUME),
            "idle_timeout": int(DEFAULT_IDLE_TIMEOUT),
            "CLIENT_ID": "YOUR_CLIENT_ID_HERE",
            "CLIENT_SECRET": "YOUR_CLIENT_SECRET_HERE",
            "enable_discord_rpc": False,
            "discord_rpc_update_interval": 15
        }
        # Ensure all default keys are present in this minimal_config too
        for key, default_value in config_defaults.items():
            if key not in minimal_config:
                minimal_config[key] = default_value
        return minimal_config

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


# --- Helper Functions ---
def is_spotify_url(url: str) -> bool:
    """Check if the URL is a Spotify URL."""
    return url.startswith(("https://open.spotify.com/", "spotify:"))

def get_spotify_track_search_queries(url: str) -> list[str] | None:
    """
    Extract track search queries (e.g., "Track Name Artist1, Artist2")
    from a Spotify track or playlist URL.
    Returns a list of search strings or None if an error occurs or API is unavailable.
    """
    if not sp:
        logging.error("Spotify API client not authenticated. Cannot process Spotify URL.")
        logging.info(f"Ensure CLIENT_ID and CLIENT_SECRET are set correctly in {CONFIG_FILE_PATH}")
        return None
    try:
        if "track/" in url:
            track_info = sp.track(url)
            if not track_info or not track_info.get("name"):
                logging.warning(f"Could not retrieve valid track info for Spotify URL: {url}")
                return None
            artists = ", ".join([artist["name"] for artist in track_info.get("artists", [])])
            return [f"{track_info['name']} {artists}"]
        elif "playlist/" in url:
            results = sp.playlist_items(url, fields='items(track(name, artists(name)))')
            if not results or not results.get("items"):
                logging.warning(f"Could not retrieve valid playlist items for Spotify URL: {url}")
                return None
            queries = []
            for item in results["items"]:
                if item and item.get("track") and item["track"].get("name"):
                    track = item["track"]
                    artists = ", ".join([artist["name"] for artist in track.get("artists", [])])
                    queries.append(f"{track['name']} {artists}")
                else:
                    logging.debug(f"Skipping invalid or partial track data in playlist: {url}")
            return queries if queries else None # Return None if no valid queries were generated
        else:
            logging.warning(f"Unsupported Spotify URL type: {url}. Expected 'track/' or 'playlist/'.")
            return None
    except spotipy.SpotifyException as e:
        logging.error(f"Spotify API error for {url}: {e}")
        if e.http_status == 401: # Unauthorized
             logging.error("Spotify API request unauthorized. Check your CLIENT_ID and CLIENT_SECRET.")
        elif e.http_status == 403: # Forbidden
             logging.error("Spotify API request forbidden. Your credentials might be correct but lack permissions for this resource.")
        elif e.http_status == 404: # Not Found
             logging.error(f"Spotify resource not found: {url}")
        # Add more specific Spotify error handling if needed
        return None
    except Exception as e: # Catch other potential errors (network issues, etc.)
        logging.error(f"Unexpected error fetching Spotify data for {url}: {e}")
        return None

def play_error_sound():
    """
    Plays a short error sound.
    Logs a warning if the sound file is missing or if playback fails.
    """
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
        "ignoreerrors": True, # Suppress yt-dlp's own error messages to console for unavailable videos
        "no_warnings": True,
        # "verbose": True, # Uncomment for debugging yt-dlp issues
        # "dump_json": True, # Uncomment to see full JSON extract for debugging
    }
    stream_urls = []
    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            logging.info(f"Searching for stream(s) for query/URL: '{query}'")
            # extract_info can raise DownloadError for various reasons (video unavailable, network issues etc.)
            info_dict = ydl.extract_info(query, download=False)

            if not info_dict:
                logging.warning(f"yt-dlp found no information for query: '{query}'")
                return None

            # Handle playlists or multiple search results
            if "entries" in info_dict and info_dict["entries"]:
                logging.info(f"Processing {len(info_dict['entries'])} entries from yt-dlp result...")
                for entry in info_dict["entries"]:
                    if entry and entry.get("url"): # 'url' here is the direct streamable URL
                        stream_urls.append(entry["url"])
                        logging.debug(f"Found stream URL for: {entry.get('title', 'Unknown Entry')}")
                    else:
                        logging.warning(f"Skipping entry with no stream URL: {entry.get('title', 'Unknown Entry') if entry else 'Invalid Entry'}")
            # Handle single video result
            elif info_dict.get("url"):
                 stream_urls.append(info_dict["url"])
                 logging.info(f"Found single stream URL for: {info_dict.get('title', 'Unknown Title')}")
            else:
                 logging.warning(f"No direct stream URL found in yt-dlp result for: '{query}'")
                 # This case might occur if yt-dlp returns metadata but no streamable format.
                 return None # No usable URLs

        return stream_urls if stream_urls else None

    except youtube_dl.utils.DownloadError as e:
        # This is a broad exception from yt-dlp, often for unavailable videos or network issues.
        # yt-dlp (with ignoreerrors=True) might still return some info for playlists even if some items fail.
        # However, if the initial query itself fails (e.g. invalid URL, no search results), it can land here.
        logging.warning(f"yt-dlp download error for '{query}': {e}. This may indicate the video/playlist is unavailable or a network issue.")
        # play_error_sound() # Potentially annoying if many items in a playlist fail
        return stream_urls if stream_urls else None # Return any URLs found so far, or None
    except Exception as e:
        logging.error(f"Unexpected error during yt-dlp processing for '{query}': {e}", exc_info=True)
        play_error_sound() # Play error for unexpected issues
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
            if not self.playlist:
                logging.info("Playlist is empty, cannot shuffle.")
                print("Playlist is empty, cannot shuffle.")
                return

            if len(self.playlist) > 1:
                # Preserve the currently playing song (if any, and if it's at the start of internal list before shuffle)
                # This interpretation of "currently playing" is based on `get_next_song` popping from index 0.
                # If `current_song_url` is what's playing, and it's also in the list to be shuffled,
                # we might want to keep it at the top or handle it specially.
                # For now, a simple shuffle of the existing `self.playlist` items.
                random.shuffle(self.playlist)
                logging.info("Playlist shuffled.")
                print("Playlist shuffled.")
            else: # Only one song
                 logging.info("Only one song in queue, cannot shuffle.")
                 print("Only one song in queue, cannot shuffle.")


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

    def remove_at(self, index: int) -> str | None:
        """Removes a song at the specified index (0-based). Returns the URL of the removed song or None."""
        with self.lock:
            if 0 <= index < len(self.playlist):
                removed_url = self.playlist.pop(index)
                logging.info(f"Removed item at index {index}: {removed_url[:70]}...")
                return removed_url
            else:
                logging.warning(f"Invalid index for removal: {index}. Queue size: {len(self.playlist)}")
                return None

    def get_current_song_title(self) -> str | None:
        """Attempts to get a displayable title for the current song."""
        if not self.current_song_url:
            return None
        try:
            if "googlevideo.com" in self.current_song_url and "title=" in self.current_song_url:
                title_part = self.current_song_url.split('title=')[1].split('&')[0]
                return urllib.parse.unquote_plus(title_part)
            # Add more parsers here for other URL types if needed
        except Exception as e:
            logging.debug(f"Could not parse title from current_song_url: {e}")
        return self.current_song_url # Fallback to URL
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
    def display_queue_helper(args_str: str = ""): # Accept args_str for verbosity
        verbose = args_str.strip().lower() == "-v" or args_str.strip().lower() == "--verbose"
        queue_items = playlist_manager.view_queue()
        current_song_title = playlist_manager.get_current_song_title()

        if not queue_items and not current_song_title:
            print("Queue is empty and nothing is playing.")
            logging.info("Queue is empty and nothing is playing (display_queue_helper).")
            return

        print("\n--- Current Queue ---")
        if current_song_title:
            now_playing_str = f"Now Playing: {current_song_title[:100]}"
            if verbose and playlist_manager.current_song_url and playlist_manager.current_song_url != current_song_title:
                now_playing_str += f" (URL: {playlist_manager.current_song_url[:70]}...)"
            print(now_playing_str)
        elif playlist_manager.current_song_url: # Fallback if title parsing failed but URL exists
            print(f"Now Playing: {playlist_manager.current_song_url[:100]}")


        if not queue_items:
            print("Queue is empty (after current song).")
        else:
            print("Up Next:")
            for i, url in enumerate(queue_items):
                display_name = f"  {i}: {url[:70]}..." # Default view
                try:
                    if "googlevideo.com" in url and "title=" in url:
                        title_part = url.split('title=')[1].split('&')[0]
                        decoded_title = urllib.parse.unquote_plus(title_part)
                        display_name = f"  {i}: {decoded_title}"[:70]
                        if verbose and url != decoded_title: # Only show URL if it's different from title part
                            display_name += f" (URL: {url[:50]}...)"
                    elif verbose: # If no title, but verbose, show more of URL
                        display_name = f"  {i}: {url}"
                except Exception:
                    if verbose: # If error and verbose, show full URL
                        display_name = f"  {i}: {url}"
                print(display_name)
        print(f"---------------------\nTotal items in upcoming queue: {len(queue_items)}\n")
        logging.info(f"Displayed queue with {len(queue_items)} upcoming items. Current: {current_song_title if current_song_title else 'None'}")

    # --- Helper for remove ---
    def remove_from_queue_helper(index_str: str):
         if not index_str:
             print("Usage: remove <index_number_from_queue_view>")
             play_error_sound()
             return
         try:
             index = int(index_str)
             removed_item_url = playlist_manager.remove_at(index)
             if removed_item_url:
                 removed_title = removed_item_url # Fallback to URL
                 try: # Attempt to decode title for better message
                     if "googlevideo.com" in removed_item_url and "title=" in removed_item_url:
                         title_part = removed_item_url.split('title=')[1].split('&')[0]
                         removed_title = urllib.parse.unquote_plus(title_part)
                 except Exception:
                     pass # Ignore decoding errors, use URL as title
                 print(f"Removed from queue: {removed_title[:70]}")
             else:
                 play_error_sound()
                 print(f"Failed to remove item: Invalid index {index}. Use 'queue' or 'list' command to see valid indices.")
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
        filename = args.strip() # Remove leading/trailing whitespace from the whole arg string first

        # Check for append flag and extract filename
        if filename.startswith("-a ") or filename.startswith("--append "):
            parts = filename.split(" ", 1)
            append = True
            filename = parts[1].strip() if len(parts) > 1 else ""

        if not filename: # Check if filename is empty after potential flag stripping
            print("Usage: loadqueue [--append|-a] <filename>")
            play_error_sound()
            return
        playlist_manager.load_queue(filename, append=append)

    # --- Command Actions Dictionary ---
    command_actions = {
        "play": lambda query: play_spotify_or_youtube_search(query) if query else print("Usage: play <query/url>"),
        "volume": lambda level: set_volume(level) if level else print("Usage: volume <0-100>"),
        "vol": lambda level: set_volume(level) if level else print("Usage: vol <0-100>"), # Alias
        "loop": lambda _: playlist_manager.toggle_loop(),
        "clear": lambda _: playlist_manager.clear(),
        "skip": lambda _: skip_song(),
        "next": lambda _: skip_song(), # Alias
        "pause": lambda _: pause_song(),
        "resume": lambda _: resume_song(),
        "stop": lambda _: stop_song(),
        "exit": lambda _: terminate_program(),
        "quit": lambda _: terminate_program(), #Alias
        "shuffle": lambda _: playlist_manager.shuffle(),
        "savequeue": lambda filename: playlist_manager.save_queue(filename) if filename else print("Usage: savequeue <filename>"),
        "loadqueue": load_queue_helper,
        "queue": display_queue_helper,
        "list": display_queue_helper,  # Alias
        "remove": remove_from_queue_helper,
        "help": lambda _: display_help(), # New help command
    }

    action = command_actions.get(verb)
    if action:
        try:
            action(args_str) # Pass the argument string (args_str)
        except TypeError as e:
            # Check if the error is due to unexpected arguments for no-arg functions
            # (e.g., calling `clear` with an argument)
            # This is a bit fragile as it depends on the error message string.
            if "takes 0 positional arguments but" in str(e) or "got an unexpected keyword argument" in str(e):
                logging.warning(f"Command '{verb}' does not accept arguments. Argument '{args_str}' ignored.")
                try:
                    action("") # Retry with no arguments
                except Exception as retry_e:
                    logging.error(f"Error re-executing command '{verb}' without arguments: {retry_e}", exc_info=True)
                    play_error_sound()
            elif "missing 1 required positional argument" in str(e):
                 logging.error(f"Command '{verb}' is missing a required argument. Usage: {verb} <argument>")
                 print(f"Usage error for command '{verb}'. It requires an argument.")
                 play_error_sound()
            else:
                 logging.error(f"TypeError executing command '{verb} {args_str}': {e}", exc_info=True)
                 play_error_sound()
        except Exception as e:
            logging.error(f"Error executing command '{verb} {args_str}': {e}", exc_info=True)
            play_error_sound()
    else:
        logging.warning(f"Unknown command: '{command}'")
        print(f"Unknown command: '{command}'. Type 'help' for a list of commands.")
        play_error_sound()

def display_help():
    """Displays a list of available commands and their basic usage."""
    print("\n--- Available Commands ---")
    help_text = {
        "play <query/url>": "Plays a song/playlist from YouTube/Spotify or searches YouTube.",
        "pause": "Pauses the current playback.",
        "resume": "Resumes the current playback.",
        "skip | next": "Skips to the next song in the queue.",
        "stop": "Stops playback and clears the queue.",
        "volume <0-100> | vol <0-100>": "Sets the volume.",
        "loop": "Toggles looping of the current queue.",
        "shuffle": "Shuffles the songs in the queue.",
        "clear": "Clears all songs from the queue.",
        "queue [-v|--verbose] | list [-v|--verbose]": "Displays the current song queue. -v for more details.",
        "remove <index>": "Removes a song from the queue by its index (from 'queue' command).",
        "savequeue <filename>": "Saves the current queue to a file in 'lib/playlists/'.",
        "loadqueue [--append|-a] <filename>": "Loads a queue from a file. Use --append or -a to add to existing queue.",
        "exit | quit": "Exits the application.",
        "help": "Displays this help message."
    }
    for command, description in help_text.items():
        print(f"  {command:<40} - {description}")
    print("------------------------\n")
    logging.info("Displayed help commands.")


def play_spotify_or_youtube_search(query: str):
    """
    Determines if the query is a Spotify URL to fetch track names,
    or a general query/YouTube URL to search/fetch directly from YouTube.
    Then adds the found stream URLs to the playlist.
    """
    if not query:
        logging.warning("Play command received with no query/URL.")
        print("Usage: play <query/URL>")
        play_error_sound()
        return

    stream_urls_to_play = []

    if is_spotify_url(query):
        logging.info(f"Processing Spotify URL: {query}")
        search_queries_for_yt = get_spotify_track_search_queries(query) # Returns list of "Title Artist" strings
        if search_queries_for_yt:
            logging.info(f"Found {len(search_queries_for_yt)} track(s) from Spotify URL. Now searching on YouTube.")
            for i, yt_query in enumerate(search_queries_for_yt):
                logging.info(f"Searching YouTube for Spotify track {i+1}/{len(search_queries_for_yt)}: '{yt_query}'")
                # Get single best match from YouTube for each Spotify track
                # Modifying ydl_opts for single search might be too complex here,
                # rely on yt-dlp's default search behavior (ytsearch1:)
                yt_stream_urls = get_stream_url(f"ytsearch1:{yt_query}") # Explicitly search YouTube
                if yt_stream_urls: # get_stream_url returns a list
                    stream_urls_to_play.append(yt_stream_urls[0]) # Add first result
                    logging.info(f"Found YouTube stream for '{yt_query}': {yt_stream_urls[0][:70]}...")
                else:
                    logging.warning(f"Could not find a YouTube stream for Spotify track: '{yt_query}'")
                    print(f"Warning: Could not find YouTube stream for: {yt_query[:50]}...") # User feedback
            if not stream_urls_to_play:
                 logging.error(f"Could not find any playable YouTube streams for tracks from Spotify URL: {query}")
                 print(f"Error: No YouTube streams found for tracks from the Spotify link.")
                 play_error_sound()
        else:
            logging.error(f"Could not get track info from Spotify URL: {query}")
            print(f"Error: Could not process Spotify link.")
            play_error_sound()
    else:
        # General query or direct YouTube URL
        logging.info(f"Processing as direct query/YouTube URL: {query}")
        yt_stream_urls = get_stream_url(query)
        if yt_stream_urls:
            stream_urls_to_play.extend(yt_stream_urls)
        else:
            logging.error(f"Could not find any playable stream(s) for query/URL: {query}")
            print(f"Error: Could not find anything for: {query[:70]}...")
            play_error_sound()

    if stream_urls_to_play:
        logging.info(f"Adding {len(stream_urls_to_play)} stream(s) to playback queue.")
        play_stream(stream_urls_to_play) # play_stream handles adding to PlaylistManager
    # else: errors already logged and user informed by now


# --- Background Threads ---
def playback_loop():
    """Continuously play songs from the playlist."""
    global player, last_activity_time
    default_volume = CONFIG.get("default_volume", DEFAULT_VOLUME)
    playback_attempt_delay = 1  # seconds, initial delay for retrying playback after error

    while True:
        next_song_url = playlist_manager.get_next_song()
        if next_song_url:
            current_song_display_name = playlist_manager.get_current_song_title() or next_song_url[:70]
            logging.info(f"Attempting to play: {current_song_display_name} (URL: {next_song_url[:70]}...)")
            last_activity_time = time.time() # Update activity time when we start trying to play

            try:
                if player is not None: # Ensure player is properly released if it exists
                    player.release()
                    player = None
                    logging.debug("Previous player instance released.")

                # Create new player instance for the new song
                # For network streams, adding options might be beneficial for robustness
                # e.g., "--network-caching=1000" (in ms)
                # These options are VLC specific and passed as a list of strings
                vlc_instance = vlc.Instance("--no-xlib") # --no-xlib for headless, add other options if needed
                player = vlc_instance.media_player_new()
                media = vlc_instance.media_new(next_song_url)
                # media.add_option("network-caching=1500") # Example: increase network cache
                player.set_media(media)

                if not player.audio_set_volume(default_volume):
                    logging.warning(f"Failed to set volume to {default_volume} for {current_song_display_name}. Current volume: {player.audio_get_volume()}")

                if player.play() == -1:
                    logging.error(f"Failed to start playback for {current_song_display_name}.")
                    play_error_sound()
                    # No need to release here, will be handled at the start of the next iteration or in finally
                    time.sleep(playback_attempt_delay) # Wait before trying next song
                    continue

                logging.info(f"Playback started for: {current_song_display_name}. Volume: {player.audio_get_volume()}")
                playback_attempt_delay = 1 # Reset delay on successful play

                # Monitor playback state
                while True:
                    if player is None: # Player might have been stopped and released by another thread (e.g. stop_song)
                        logging.info(f"Player released externally during playback of {current_song_display_name}.")
                        break

                    state = player.get_state()
                    if state == vlc.State.Playing:
                        last_activity_time = time.time() # Update activity while playing
                    elif state in (vlc.State.Ended, vlc.State.Stopped, vlc.State.Error):
                        log_level = logging.INFO
                        if state == vlc.State.Error:
                            log_level = logging.ERROR
                            play_error_sound() # Play error sound specifically for VLC errors
                        elif state == vlc.State.Ended:
                            logging.info(f"Finished playing: {current_song_display_name}")
                        elif state == vlc.State.Stopped:
                             logging.info(f"Playback stopped for: {current_song_display_name}")

                        logging.log(log_level, f"Playback state for {current_song_display_name}: {state}")
                        break # Exit inner loop to get next song or wait
                    time.sleep(0.2) # Polling interval for player state

            except Exception as e: # Catch-all for unexpected errors during setup or monitoring
                logging.error(f"Unexpected error during playback processing for {current_song_display_name}: {e}", exc_info=True)
                play_error_sound()
                # Increase delay for retrying after an unexpected error
                playback_attempt_delay = min(playback_attempt_delay * 2, 60) # Exponential backoff up to 1 minute
                logging.info(f"Waiting {playback_attempt_delay}s before trying next song due to unexpected error.")
                time.sleep(playback_attempt_delay)
            finally:
                # Ensure player is released if it still exists and loop is about to pick next song or if an error occurred
                if player is not None:
                    current_state = player.get_state()
                    if current_state not in [vlc.State.Playing, vlc.State.Paused]: # Only release if not actively playing/paused
                        logging.debug(f"Releasing player for {current_song_display_name} in finally block. State: {current_state}")
                        player.release()
                        player = None
                    else:
                        logging.debug(f"Player for {current_song_display_name} still active (State: {current_state}), not releasing in finally block immediately.")
        else:
            # No song in queue, wait a bit before checking again
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

        # Register shuffle hotkey
        if CONFIG.get("shuffle_queue"):
            try:
                keyboard.add_hotkey(CONFIG["shuffle_queue"], playlist_manager.shuffle)
            except Exception as e:
                logging.error(f"Failed to register hotkey 'shuffle_queue' ({CONFIG['shuffle_queue']}): {e}")
        else:
            logging.warning("Config key 'shuffle_queue' is empty or not found. Shuffle hotkey disabled.")

        # Register view_queue_hotkey (example, currently does nothing without a handler)
        if CONFIG.get("view_queue_hotkey"):
            try:
                # You would need a function like `lambda: display_queue_helper()`
                # but display_queue_helper currently prints to console, which isn't ideal for a global hotkey response.
                # For now, let's imagine it calls a function `show_queue_notification()`
                # keyboard.add_hotkey(CONFIG["view_queue_hotkey"], show_queue_notification_function)
                logging.info(f"Hotkey 'view_queue_hotkey' ({CONFIG['view_queue_hotkey']}) is configured but needs a target function.")
            except Exception as e:
                logging.error(f"Failed to register hotkey 'view_queue_hotkey' ({CONFIG['view_queue_hotkey']}): {e}")
        else:
            logging.warning("Config key 'view_queue_hotkey' is empty or not found. View queue hotkey disabled.")

        logging.info("--- Hotkeys Registered ---")
        # Define which config keys are actual hotkeys
        hotkey_config_keys = [
            "terminate", "play", "pause", "resume", "skip", "stop",
            "volume_up", "volume_down", "skip_forward", "skip_backward",
            "loop_toggle", "shuffle_queue", "view_queue_hotkey"
        ]

        registered_hotkeys_summary = {}

        for cfg_key in hotkey_config_keys:
            hotkey_val = CONFIG.get(cfg_key)
            if hotkey_val:
                # To avoid logging the same physical hotkey multiple times if different actions map to it (e.g. play & resume)
                # We can map the action to the hotkey string.
                # However, the current setup logs the config key name to the hotkey string.
                # Let's refine this to log the actual hotkey string and the function it's tied to (conceptually).
                # For simplicity here, we'll just log the config key and its assigned hotkey string.
                if hotkey_val not in registered_hotkeys_summary.values():
                     logging.info(f"  Action '{cfg_key}' -> Hotkey '{hotkey_val}'")
                     registered_hotkeys_summary[cfg_key] = hotkey_val
                else:
                    # Find which other action already uses this hotkey
                    existing_action = [k for k, v in registered_hotkeys_summary.items() if v == hotkey_val]
                    logging.info(f"  Action '{cfg_key}' -> Hotkey '{hotkey_val}' (Shared with: {existing_action})")
            else:
                logging.info(f"  Action '{cfg_key}' -> Not configured (empty or missing)")
        logging.info("--- End Hotkeys Registered ---")

        keyboard.wait() # Blocks this thread, waiting for hotkey events
    except ValueError as e: # This can be raised by keyboard.add_hotkey for invalid hotkey strings
         logging.error(f"Invalid hotkey configuration detected: {e}. Please check your config.json.")
         logging.error("Some hotkeys may not function correctly. The application will continue to run.")
         # The thread will likely exit if keyboard.wait() isn't reached or if add_hotkey fails critically before wait().
         # If add_hotkey raises ValueError, it stops processing further hotkeys in the try block.
    except Exception as e:
        logging.error(f"An unexpected error occurred in the hotkey listener thread: {e}")
        logging.error("Global hotkeys may not function.")
        # This thread might terminate, but the main app should continue.


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