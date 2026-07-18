import os
import httpx
from urllib.parse import urlencode

BASE_URL = "https://www.googleapis.com/youtube/v3"

def _request(endpoint: str, params: dict):
    """Internal helper to perform a GET request to the YouTube Data API.
    Raises httpx.HTTPStatusError on non‑200 responses.
    """
    api_key = os.getenv('YOUTUBE_API_KEY')
    params['key'] = api_key
    url = f"{BASE_URL}/{endpoint}?{urlencode(params)}"
    response = httpx.get(url, timeout=10.0)
    response.raise_for_status()
    return response.json()

def search_videos(query: str, max_results: int = 25):
    """Search YouTube for videos matching *query*.
    Returns a list of video IDs.
    """
    data = _request(
        "search",
        {
            "part": "id",
            "q": query,
            "type": "video",
            "maxResults": max_results,
        },
    )
    return [item["id"]["videoId"] for item in data.get("items", [])]

def get_playlist_videos(playlist_id: str, max_results: int = 50):
    """Retrieve video IDs from a playlist.
    Handles pagination automatically up to *max_results*.
    """
    video_ids = []
    page_token = None
    while len(video_ids) < max_results:
        params = {
            "part": "contentDetails",
            "playlistId": playlist_id,
            "maxResults": min(50, max_results - len(video_ids)),
        }
        if page_token:
            params["pageToken"] = page_token
        data = _request("playlistItems", params)
        for item in data.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return video_ids

def get_channel_videos(channel_id: str, max_results: int = 50):
    """Fetch the most recent video IDs from a channel.
    Uses the *search* endpoint ordered by date.
    """
    data = _request(
        "search",
        {
            "part": "id",
            "channelId": channel_id,
            "order": "date",
            "type": "video",
            "maxResults": max_results,
        },
    )
    return [item["id"]["videoId"] for item in data.get("items", [])]
