# hyprpaper randomizer
Python script to randomly change my hyprpaper wallpaper from all files in a directory, selecting by monitor orientation when requested.
Implements:
- caching to avoid checking image data every time
- allows for multiple caches and multiple source dirs per cache
- history to go back up to 50 wallpapers
- follows symlinks and has configurable max depth to search
- luminance measurement for light/dark mode selection
- per-monitor random selection
- selection matching monitor orientation
- tab completion via [argcomplete](https://github.com/kislyuk/argcomplete) (bash & zsh)

## Args:
### Cache Init
- `--cache-init NAME` : initialize a new cache and set it as active
- `--wallpaper-dir PATH` : wallpaper source directory (repeatable, used with `--cache-init`)
- `--max-depth N` : maximum directory depth to scan (used with `--cache-init`, default: 2)
- `--no-populate` : skip initial population when using `--cache-init`

### Cache Management
- `--cache-list` : list all caches
- `--cache-update NAME` : update and prune an existing cache
- `--cache-switch NAME` : switch to a cache, clear history, and apply a wallpaper
- `--cache-delete NAME` : delete a cache (or `all` to delete every cache)
- `--cache-cycle` : cycle (switch) through existing caches

### Normal Run
- `--back` : rewind to previous wallpaper using history
- `--light` : select only light wallpapers (luminance > midpoint)
- `--dark` : select only dark wallpapers (luminance < midpoint)
- `--multi` : apply one randomly selected wallpaper per monitor
- `--fit-mode MODE` : change wallpaper fit mode (`contain`, `cover`, `tile`, or `fill`; default: `contain`)
- `--use-vertical` : when monitor transform is vertical (1 or 3), select portrait images; otherwise use horizontal images (0 or 2)

## Tab completion

Tab completion is provided via [argcomplete](https://github.com/kislyuk/argcomplete) (bash & zsh).

When installed via the flake, completion scripts are automatically placed in the standard locations (`share/bash-completion/completions/` and `share/zsh/site-functions/`) and will be picked up by any shell that sources system completions — no manual setup required.

`--wallpaper-dir <TAB>` expands directories and `--cache-switch/update/delete <TAB>` suggests existing cache names.
