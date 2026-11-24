# WorldWard as a claude.ai artifact

A personal-play build that runs WorldWard entirely in a private claude.ai
page. Pyodide (Python 3.13 in WebAssembly) runs the unchanged App host and
Engine; the interface's `/api/` requests are answered in-process.

- **Saves** are mirrored to the viewer's private claude.ai storage
  (`db`, under `data/users/<id>/`), or to this browser if that is unavailable.
- **Claude assistance** uses the page's `sample` capability on the viewer's own
  claude.ai plan. No API key exists here. Claude only proposes one listed action
  for the player's own words; the Engine validates it and the player confirms.
  It needs a browser with WebAssembly stack switching (JSPI); otherwise play
  continues without assistance.
- Not included: the Historical Grand Archive, reference documents, images,
  tests and evidence. Not Alpha evidence (gate A4-G08 needs a protected provider
  with a finite budget).

## Files

| File | Role |
| --- | --- |
| `page.html` | Page template: boot overlay, inlined App styles, markup and scripts |
| `boot.js` | Starts Pyodide, routes `/api/` requests, mirrors saves, connects `sample` |
| `bridge.py` | In-page host: real App handler without a socket |
| `claude_assist.py` | Claude transport and configuration for the Engine broker |

## Build

```bash
python -B tools/build_claude_artifact.py --output /path/outside/repo --pyodide /path/to/pyodide-files
```

The Pyodide folder must hold the npm `pyodide@0.29.3` package files and the
`sqlite3` wheel from the 0.29.3 GitHub release; every file is checked against
hashes pinned in the build script. The build verifies the joined checkout first.
Archives are published as base64 `.txt` files because artifacts serve no `.zip`.
