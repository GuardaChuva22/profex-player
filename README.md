# Profex Player

"For freedom 🏴‍☠️"

Profex Player is a stealthy, command-line and hotkey-driven music player that supports YouTube and Spotify link playback. It runs hidden in the system tray and can be controlled globally.

## Features

*   **Stealth Operation**: Runs from the system tray with a generic name ("Windows Defender Terminal" by default) and icon. The main interaction window can be hidden.
*   **YouTube & Spotify Support**: Play individual tracks or playlists from YouTube (direct URL or search) and Spotify (track or playlist URLs, which are then searched on YouTube).
*   **Global Hotkeys**: Control playback (play, pause, skip, volume, etc.) from anywhere in your OS. All hotkeys are configurable.
*   **Command-Line Interface**: Access all features through a simple command interface in the popup window.
*   **Playlist Management**:
    *   View the current queue (`queue` or `list` command, with verbose option).
    *   Shuffle the queue (`shuffle` command and hotkey).
    *   Save and load queues to/from files (`savequeue`, `loadqueue` commands).
    *   Remove songs from the queue by index (`remove` command).
    *   Clear the entire queue (`clear` command).
    *   Toggle loop mode for the queue (`loop` command and hotkey).
*   **Configurable**: Hotkeys, default volume, idle timeout, and Spotify API credentials can be configured via `lib/config/config.json`.
*   **Auto-Shutdown Features**:
    *   Idle timeout (terminates if inactive for a set period).
    *   Terminates if the Windows lock screen (LogonUI.exe) is detected.
*   **Error Handling**: Plays an error sound for many user-facing errors. Detailed logging for troubleshooting.

## Default Hotkeys

These are the default hotkeys. You can customize them in `lib/config/config.json`.

*   **Terminate App:** `ctrl+shift+q`
*   **Pause Playback:** `ctrl+alt+space`
*   **Resume/Play:** `ctrl+alt+r` (Note: `play` is also `ctrl+alt+p` but `resume` is generally more used)
*   **Skip Track:** `ctrl+alt+s`
*   **Stop Playback & Clear Queue:** `ctrl+alt+q`
*   **Volume Up:** `ctrl+alt+up`
*   **Volume Down:** `ctrl+alt+down`
*   **Seek Forward (10s):** `ctrl+alt+right`
*   **Seek Backward (10s):** `ctrl+alt+left`
*   **Toggle Loop Queue:** `ctrl+alt+l`
*   **Shuffle Queue:** `ctrl+alt+h`
*   **(Example) View Queue:** `ctrl+alt+v` (Note: This hotkey is configured by default but currently only logs that it needs a target function for notifications. The `queue` command in the text interface is functional.)

⚠️ **Important**: Some default keybinds might conflict with system shortcuts or other applications. Please check `lib/config/config.json` and adjust them if necessary.

## Commands

Interact with the player by typing commands into its window (accessible from the system tray icon).

*   `play <query/url>`: Plays a song/playlist from YouTube/Spotify or searches YouTube.
    *   Example (YouTube URL): `play https://www.youtube.com/watch?v=dQw4w9WgXcQ`
    *   Example (YouTube Search): `play Never Gonna Give You Up`
    *   Example (Spotify Track URL): `play https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT`
    *   Example (Spotify Playlist URL): `play https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M`
*   `pause`: Pauses the current playback.
*   `resume`: Resumes the current playback.
*   `skip` / `next`: Skips to the next song in the queue.
*   `stop`: Stops playback and clears the entire queue.
*   `volume <0-100>` / `vol <0-100>`: Sets the volume (e.g., `volume 75`).
*   `loop`: Toggles looping of the current queue.
*   `shuffle`: Shuffles the songs currently in the queue.
*   `clear`: Clears all songs from the queue.
*   `queue [-v|--verbose]` / `list [-v|--verbose]`: Displays the current song queue.
    *   Use `-v` or `--verbose` for more detailed output (e.g., includes URLs).
*   `remove <index>`: Removes a song from the queue by its index (0-based, as shown in the `queue` command).
*   `savequeue <filename>`: Saves the current queue to a file (e.g., `savequeue mymix`). Files are saved in `lib/playlists/`.
    *   The `.txt` extension is added automatically if not provided.
*   `loadqueue [--append|-a] <filename>`: Loads a queue from a file.
    *   Example: `loadqueue mymix` (replaces current queue)
    *   Example: `loadqueue --append mymix` or `loadqueue -a mymix` (adds to current queue)
*   `exit` / `quit`: Exits the application.
*   `help`: Displays a list of available commands.

## Setup & Configuration

1.  **Dependencies**: Ensure you have Python installed. Install required packages using pip:
    ```bash
    pip install python-vlc Pillow pystray keyboard yt-dlp spotipy
    ```
    You also need VLC media player installed on your system, as `python-vlc` is a binding to it.

2.  **Configuration File (`lib/config/config.json`)**:
    *   On the first run, a default `config.json` will be created in the `lib/config/` directory.
    *   **Spotify API Credentials**: To play Spotify links (which are searched on YouTube), you need to provide your Spotify API `CLIENT_ID` and `CLIENT_SECRET`.
        *   Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/).
        *   Create an app to get your credentials.
        *   Edit `config.json` and replace `"YOUR_CLIENT_ID_HERE"` and `"YOUR_CLIENT_SECRET_HERE"` with your actual credentials.
    *   **Hotkeys**: You can customize all hotkeys in this file. Refer to the `keyboard` library's format for hotkey strings (e.g., `ctrl+alt+s`).
    *   **Other Settings**: `default_volume`, `idle_timeout` can also be adjusted.

## How It Works

*   **Spotify Links**: When a Spotify link is provided, the application uses the Spotify API to fetch track names and artists. It then searches for these tracks on YouTube using `yt-dlp`.
*   **YouTube Links/Search**: Direct YouTube links are played, and search queries use `yt-dlp` to find and stream the best audio match.
*   **Playback**: VLC is used for media playback via `python-vlc`.
*   **Global Hotkeys**: The `keyboard` library listens for system-wide hotkeys.
*   **System Tray**: `pystray` manages the system tray icon and menu.

## Disclaimer

This tool is for educational and personal use. Please respect copyright laws and the terms of service of Spotify and YouTube. Downloading or streaming copyrighted material without permission may be illegal in your country.
