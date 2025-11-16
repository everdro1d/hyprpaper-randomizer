# hyprpaper randomizer
Python script to randomly change my hyprpaper wallpaper to a landscape (ish) image from all files in a directory.
Implements:
- caching to avoid checking every time, checks -> caches match or not -> checks cache first, changes selected image if not match otherwise change wallpaper to selected image
- history to go back up to 10 wallpapers
- follows symlinks

## Args:
- --cache : warm cache (classify images) and exit
- --back  : rewind wallpaper using history file
- --delete-cache : remove the sqlite cache and exit
- --wallpaper-dir : path to the directory containing wallpapers
- --max-depth : integer defining the maximum depth to follow when scanning

---

## tiny-projects
A collection of tiny projects that are too small to have their own repo, and that took me less than an hour to write.

## Usage
Use branches to switch between projects.
