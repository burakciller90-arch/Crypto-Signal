# Galactech Shared Visual Audit

This is a host-level, project-neutral Chromium visual-audit tool installed by UID501 at:

```
/Users/Shared/Galactech/bin/galactech-visual-audit
```

The source of truth is versioned in Crypto Signal only because the UID501 GitHub administrator runner currently belongs to that repository. The installed executable is deliberately placed under `/Users/Shared/Galactech`, not inside any project volume, so UID502/UID503/UID504 project runners can call the same tool without copying implementation code into their projects.

## Safety model

The shared recorder does **not** accept arbitrary shell or arbitrary JavaScript from scenario files. A scenario is limited to four UI actions: `wait`, `scroll`, `click`, and `screenshot`. Projects own their selectors and must keep scenarios read-only. The tool never discovers and clicks arbitrary controls by itself.

The installer only writes under `/Users/Shared/Galactech`. It does not write to Durdurulmaz, Quantum Capital, Crypto Signal runtime databases, or any project data volume.

## Output

Every run can produce:

- initial/final/full-page PNG screenshots;
- per-step screenshots;
- Chrome screencast JPEG frames;
- `audit.mp4` via system ffmpeg when present, otherwise the isolated bundled `imageio-ffmpeg` encoder;
- DOM snapshot;
- accessibility tree;
- interactive-element inventory;
- browser Runtime/Log/Network events;
- manifest with viewport, actions, duration, and video availability.

## Example

```bash
cat > "$RUNNER_TEMP/scenario.json" <<'JSON'
{
  "actions": [
    {"type": "wait", "seconds": 1},
    {"type": "scroll", "delta_y": 650, "name": "stream-down"},
    {"type": "click", "selector": ".message-summary", "index": 0, "name": "open-first-message", "optional": true},
    {"type": "screenshot", "name": "expanded-message"}
  ]
}
JSON

/Users/Shared/Galactech/bin/galactech-visual-audit \
  --url http://127.0.0.1:48700/ \
  --scenario "$RUNNER_TEMP/scenario.json" \
  --output-dir "$RUNNER_TEMP/visual-audit" \
  --width 1440 --height 900
```

A project workflow should upload the output directory with `actions/upload-artifact@v4`. The project remains responsible for starting its own product service and choosing safe selectors.
