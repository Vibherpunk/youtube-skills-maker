import argparse
from .tui import launch_tui
from .pipeline import run_pipeline
from .startup import verify_env

def main():
    # Verify environment keys before proceeding
    verify_env()

    parser = argparse.ArgumentParser(description='YouTube Skill Generator')
    parser.add_argument('--query', type=str, help='Search query')
    parser.add_argument('--channel-id', type=str, help='Channel ID')
    parser.add_argument('--playlist-id', type=str, help='Playlist ID')
    parser.add_argument('--video-ids', type=str, help='Comma‑separated video IDs')
    parser.add_argument('--max-videos', type=int, default=50, help='Maximum videos to process')
    parser.add_argument('--delay', type=float, default=2.0, help='Delay between API calls (seconds)')
    parser.add_argument('--dry-run', action='store_true', help='Do not push to GitHub')
    parser.add_argument('--tui', action='store_true', help='Launch interactive TUI')
    args = parser.parse_args()

    if args.tui:
        launch_tui()
    else:
        config = {
            'query': args.query,
            'channel_id': args.channel_id,
            'playlist_id': args.playlist_id,
            'video_ids': [v.strip() for v in args.video_ids.split(',')] if args.video_ids else [],
            'max_videos': args.max_videos,
            'delay': args.delay,
            'dry_run': args.dry_run,
        }
        run_pipeline(config)

if __name__ == '__main__':
    main()
