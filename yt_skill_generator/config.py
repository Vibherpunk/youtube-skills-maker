import os
from dotenv import load_dotenv

# Load .env from project root
load_dotenv()

YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')

DEFAULT_MAX_VIDEOS = 50
DEFAULT_DELAY = 2.0
