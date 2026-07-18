from prompt_toolkit.application import Application
from prompt_toolkit.layout.containers import VSplit, HSplit
from prompt_toolkit.widgets import Frame, TextArea, Button, Label, Checkbox
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.key_binding import KeyBindings

from .pipeline import run_pipeline

def launch_tui():
    """Launch the interactive TUI for configuring the generator."""
    # Define form fields
    query_field = TextArea(multiline=False)
    channel_field = TextArea(multiline=False)
    playlist_field = TextArea(multiline=False)
    video_ids_field = TextArea(multiline=False)
    max_videos_field = TextArea(text="50", multiline=False)
    delay_field = TextArea(text="2.0", multiline=False)
    dry_run_cb = Checkbox(text="Dry Run (Skip pushing to GitHub)")

    def do_start():
        app.exit(result=True)

    def do_cancel():
        app.exit(result=False)

    start_button = Button("Start", handler=do_start)
    cancel_button = Button("Cancel", handler=do_cancel)

    # Assemble layout
    body = HSplit([
        Label(text="YouTube Skill Generator Configuration", style="class:title"),
        Label(text="Enter at least one source (Query, Channel ID, Playlist ID, or Video IDs)."),
        Label(text="Press TAB to navigate fields. Press ENTER on Start to begin."),
        Frame(body=query_field, title="Search Query"),
        Frame(body=channel_field, title="Channel ID"),
        Frame(body=playlist_field, title="Playlist ID"),
        Frame(body=video_ids_field, title="Video IDs (comma-separated)"),
        Frame(body=max_videos_field, title="Max Videos (default: 50)"),
        Frame(body=delay_field, title="Delay between API calls in seconds (default: 2.0)"),
        dry_run_cb,
        VSplit([start_button, cancel_button])
    ])

    root_container = Frame(body, title="yt-skill-generator")
    layout = Layout(root_container)

    # Key bindings
    kb = KeyBindings()
    
    @kb.add('c-c')
    def _(event):
        event.app.exit(result=False)

    @kb.add('tab')
    def _(event):
        event.app.layout.focus_next()

    @kb.add('s-tab')
    def _(event):
        event.app.layout.focus_previous()

    app = Application(
        layout=layout, 
        key_bindings=kb, 
        full_screen=True, 
        mouse_support=True
    )

    result = app.run()

    if result:
        # User pressed Start
        config = {
            'query': query_field.text.strip(),
            'channel_id': channel_field.text.strip(),
            'playlist_id': playlist_field.text.strip(),
            'video_ids': [v.strip() for v in video_ids_field.text.split(',')] if video_ids_field.text.strip() else [],
            'max_videos': int(max_videos_field.text.strip() or "50"),
            'delay': float(delay_field.text.strip() or "2.0"),
            'dry_run': dry_run_cb.checked,
        }
        print("Starting pipeline with config:")
        print(config)
        run_pipeline(config)
    else:
        print("Operation cancelled.")
