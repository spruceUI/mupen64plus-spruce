#!/usr/bin/env python3
"""
Patch Rice's glViewportWrapper to offset the viewport when M64P_VIEWPORT_X
is set. This centers 4:3 content on widescreen displays (e.g. TSP/TSPS 1280x720).
"""

RICE_RENDER_PATH = "video-rice/projects/unix/../../src/OGLRender.cpp"

with open(RICE_RENDER_PATH, "r") as f:
    src = f.read()

# Add stdlib.h include for getenv/atoi
src = src.replace(
    '#include "OGLRender.h"',
    '#include "OGLRender.h"\n#include <stdlib.h>',
    1
)

# Patch the glViewport call inside glViewportWrapper
old_vp = '        glViewport(x,y,width,height);'
new_vp = '''        {
            static int vpx_off = -1;
            if (vpx_off == -1) {
                const char *e = getenv("M64P_VIEWPORT_X");
                vpx_off = e ? atoi(e) : 0;
            }
            glViewport(x + vpx_off, y, width, height);
        }'''

src = src.replace(old_vp, new_vp, 1)

with open(RICE_RENDER_PATH, "w") as f:
    f.write(src)

print("Patched Rice OGLRender.cpp with viewport centering")
