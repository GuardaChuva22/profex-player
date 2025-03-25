import json
import requests
import subprocess
import sys
import webbrowser
from packaging import version
import tkinter as tk
from tkinter import messagebox

# Configuration
CURRENT_VERSION = "1.0.0"  # Must match your app's current version
VERSION_CHECK_URL = "https://raw.githubusercontent.com/GuardaChuva22/profex-player/main/version.json"
MAIN_SCRIPT = "main.py"  # Your main application file

def check_for_updates():
    """Check for updates and return (update_available, changelog, download_url)"""
    try:
        response = requests.get(VERSION_CHECK_URL, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        # Debug print to verify data structure
        print("DEBUG - Parsed JSON:", data)
        
        if version.parse(data["version"]) > version.parse(CURRENT_VERSION):
            return (True, data.get("changelog", ""), data.get("download_url", ""))
        return (False, "", "")
        
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return (False, "", "")
    except requests.RequestException as e:
        print(f"Network error: {e}")
        return (False, "", "")
    except Exception as e:
        print(f"Unexpected error: {e}")
        return (False, "", "")

def show_update_prompt(changelog, download_url):
    """Show a popup if updates are available"""
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    
    message = f"New version available!\n\nCurrent: v{CURRENT_VERSION}\n\nWhat's new:\n{changelog}"
    user_choice = messagebox.askyesno(
        "Update Available", 
        message,
        detail="Would you like to download the update now?",
        icon="question"
    )
    
    if user_choice and download_url:
        webbrowser.open(download_url)
        root.destroy()
        sys.exit(0)  # Close the app to allow updating
    root.destroy()

def launch_main_app():
    """Start the main application"""
    try:
        subprocess.Popen([sys.executable, MAIN_SCRIPT])
    except Exception as e:
        messagebox.showerror("Error", f"Failed to start {MAIN_SCRIPT}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Check for updates
    update_available, changelog, download_url = check_for_updates()
    
    # Prompt if update exists
    if update_available:
        show_update_prompt(changelog, download_url)
    
    # Launch main app regardless (user might have chosen "Later")
    launch_main_app()