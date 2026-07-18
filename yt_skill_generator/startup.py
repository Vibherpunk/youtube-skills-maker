import os
from pathlib import Path
from dotenv import set_key
from rich.console import Console
from rich.prompt import Prompt

from .api import search_videos

console = Console()

def verify_env():
    """Verify that required API keys are present and valid, prompting if not."""
    env_path = Path(".env")
    if not env_path.exists():
        env_path.touch()

    api_key = os.getenv("YOUTUBE_API_KEY")
    
    while not api_key or not _is_youtube_key_valid(api_key):
        if not api_key:
            console.print("[yellow]YouTube API Key not found.[/yellow]")
        else:
            console.print("[red]The provided YouTube API Key appears to be invalid.[/red]")
        
        api_key = Prompt.ask("Please enter your YouTube API Key")
        
        # Save it and reload in os.environ for the current session
        set_key(str(env_path), "YOUTUBE_API_KEY", api_key)
        os.environ["YOUTUBE_API_KEY"] = api_key

    # Optionally prompt for Gemini key if not present
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        console.print("\n[dim]Gemini API Key is optional but recommended for fallback evaluation.[/dim]")
        gemini_key = Prompt.ask("Please enter your Gemini API Key (or press Enter to skip)", default="")
        if gemini_key:
            set_key(str(env_path), "GEMINI_API_KEY", gemini_key)
            os.environ["GEMINI_API_KEY"] = gemini_key

    console.print("[green]Environment verified successfully![/green]\n")

def _is_youtube_key_valid(api_key: str) -> bool:
    """Do a test run to check if the YouTube API key works."""
    # Temporarily set the environ so api module picks it up
    original_key = os.environ.get("YOUTUBE_API_KEY")
    os.environ["YOUTUBE_API_KEY"] = api_key
    try:
        # A simple query returning 1 result
        search_videos("test", max_results=1)
        return True
    except Exception as e:
        return False
    finally:
        if original_key:
            os.environ["YOUTUBE_API_KEY"] = original_key
        else:
            del os.environ["YOUTUBE_API_KEY"]
