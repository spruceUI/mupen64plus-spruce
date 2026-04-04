#!/usr/bin/env python3
"""
Patch mupen64plus-core vidext.c to center a smaller render resolution
within a larger display. When M64P_CENTER_X is set, it offsets the
SDL window position to center horizontally.

This fixes 4:3 content being left-aligned on 16:9 displays.
"""

VIDEXT_PATH = "core/projects/unix/../../src/api/vidext.c"

with open(VIDEXT_PATH, "r") as f:
    src = f.read()

# Replace SDL_WINDOWPOS_UNDEFINED with centered position when env var set
old = '        l_pWindow = SDL_CreateWindow(l_pWindowTitle, SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED, Width, Height, windowFlags);'
new = '''        {
            int winX = SDL_WINDOWPOS_UNDEFINED;
            int winY = SDL_WINDOWPOS_UNDEFINED;
            const char *cx = getenv("M64P_CENTER_X");
            if (cx) winX = atoi(cx);
            const char *cy = getenv("M64P_CENTER_Y");
            if (cy) winY = atoi(cy);
            l_pWindow = SDL_CreateWindow(l_pWindowTitle, winX, winY, Width, Height, windowFlags);
        }'''

src = src.replace(old, new, 1)

with open(VIDEXT_PATH, "w") as f:
    f.write(src)

print("Patched vidext.c with window position centering support")
