import os
import sys
from typing import List

# Ensure workspace root is in PYTHONPATH for importing src modules
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from src.transcribe import get_transcript
from src.evaluator import evaluate_transcript
from src.skill_builder import build_universal_skill
from src.publisher import publish_skills_to_github, publish_to_ikf

from .api import search_videos, get_channel_videos, get_playlist_videos
from .utils import rate_limit

def _gather_video_ids(config: dict) -> List[str]:
    """Collect video IDs based on user configuration.
    Returns a deduplicated list respecting max_videos limit.
    """
    ids: List[str] = []
    max_v = config.get('max_videos', 50)

    if config.get('query'):
        ids.extend(search_videos(config['query'], max_results=max_v))
    if config.get('channel_id'):
        ids.extend(get_channel_videos(config['channel_id'], max_results=max_v))
    if config.get('playlist_id'):
        ids.extend(get_playlist_videos(config['playlist_id'], max_results=max_v))
    if config.get('video_ids'):
        ids.extend([vid.strip() for vid in config['video_ids'] if vid.strip()])

    # Deduplicate while preserving order
    seen = set()
    unique_ids = []
    for vid in ids:
        if vid not in seen:
            seen.add(vid)
            unique_ids.append(vid)
        if len(unique_ids) >= max_v:
            break
    return unique_ids[:max_v]

def run_pipeline(config: dict) -> None:
    """Main orchestration for the generalized YouTube skill generator.

    Args:
        config: Dictionary containing user‑provided options.
    """
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
    from rich.console import Console
    console = Console()

    delay = float(config.get('delay', 2.0))
    dry_run = config.get('dry_run', False)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        
        gather_task = progress.add_task("[cyan]Gathering video IDs...", total=None)
        video_ids = _gather_video_ids(config)
        progress.update(gather_task, completed=1, total=1, description=f"[cyan]Found {len(video_ids)} video(s)")

        if not video_ids:
            console.print("[yellow]No videos found matching the criteria.[/yellow]")
            return

        main_task = progress.add_task("[green]Processing videos...", total=len(video_ids))
        generated_skills = []

        for idx, vid in enumerate(video_ids, 1):
            progress.update(main_task, description=f"[green]Processing ({idx}/{len(video_ids)}): [bold]{vid}[/bold]", advance=0)
            progress.console.print(f"  [dim]▶ Fetching transcript for {vid}[/dim]")
            # Transcript extraction (cached inside get_transcript)
            transcript = get_transcript(vid, data_dir='data')
            if not transcript:
                progress.console.print(f"  [red]✗ Skipping {vid} – no transcript available.[/red]")
                rate_limit(delay)
                progress.advance(main_task)
                continue

            # Basic metadata retrieval – title and channel via YouTube Data API
            # Re‑use the search endpoint for simplicity (fetch video details)
            # We'll perform a lightweight request for title/channel.
            # Using the same API wrapper:
            from .api import _request
            try:
                video_info = _request('videos', {
                    'part': 'snippet',
                    'id': vid,
                })
                snippet = video_info['items'][0]['snippet'] if video_info.get('items') else {}
                title = snippet.get('title', f'Video {vid}')
                channel_name = snippet.get('channelTitle', 'Unknown')
                progress.console.print(f"  [dim]▶ Evaluating: {title[:50]}...[/dim]")
            except Exception as e:
                progress.console.print(f"  [yellow]Failed to fetch metadata for {vid}: {e}[/yellow]")
                title = f'Video {vid}'
                channel_name = 'Unknown'

            # Evaluation via LLMs (uses environment keys internally)
            eval_result = evaluate_transcript(vid, title, transcript, api_key=os.getenv('GEMINI_API_KEY'))
            if not eval_result:
                progress.console.print(f"  [red]✗ Evaluation failed for {vid} – skipping.[/red]")
                rate_limit(delay)
                progress.advance(main_task)
                continue

            if not eval_result.get('is_teachable_skill'):
                progress.console.print(f"  [yellow]✗ Video {vid} deemed not teachable – skipping.[/yellow]")
                rate_limit(delay)
                progress.advance(main_task)
                continue

            # Build skill data structure expected by skill_builder
            skill_data = {
                'name': eval_result.get('technique_description', f'skill_{vid}').replace(' ', '-').lower(),
                'description': eval_result.get('technique_description', ''),
                'keywords': eval_result.get('keywords', []),
                'difficulty': 'intermediate',
                'prerequisites': [],
                'skill_body': eval_result.get('technique_description', ''),
                'references': [],
            }
            video_meta = {
                'videoId': vid,
                'title': title,
                'channelName': channel_name,
                'link': f'https://www.youtube.com/watch?v={vid}',
            }
            skill_path = build_universal_skill(skill_data, [video_meta], output_dir="data/ai-skills/skills")
            generated_skills.append(skill_path)
            progress.console.print(f"  [green]✓ Skill generated at {skill_path}[/green]")
            progress.advance(main_task)
            rate_limit(delay)

    if not generated_skills:
        console.print("[yellow]No skills were generated during this run.[/yellow]")
        return

    if dry_run:
        console.print("[blue]Dry‑run mode enabled – skipping GitHub publish.[/blue]")
        return

    console.print("[cyan]Publishing skills to the main GitHub repository...[/cyan]")
    publish_success = publish_skills_to_github()
    if publish_success:
        console.print("[cyan]Publishing to i‑know‑kung‑fu repository...[/cyan]")
        publish_to_ikf()
    else:
        console.print("[red]Primary publishing failed – skipping secondary publish.[/red]")
