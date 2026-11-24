# Music

No music ships with this tool. Clips render without music until you add some.

## Adding a track

1. Put an audio file (mp3, m4a or wav) in this folder.
2. Optional: open `music_config.json` and add a line with the second at which
   the track gets going, for example `"my-track.mp3": 12`. The clip's music
   starts from there.
3. Use it for every clip by setting `CLIP_TOOL_DEFAULT_MUSIC=my-track.mp3` in
   `config.env`, or per clip with `"music_path": "my-track.mp3"` in the
   decisions file, or with `--music my-track.mp3` in overlay mode.

## Use music you have the right to use

Only add tracks you are licensed to publish with: royalty-free libraries, music
you have paid a licence for, or music you made. A chart song baked into the video
file can get the post muted or taken down, and it is not covered by the licence
that applies when you pick a song inside the Instagram or TikTok app. If you want
a trending song, render the clip without music and add the song in the app when
you post.
