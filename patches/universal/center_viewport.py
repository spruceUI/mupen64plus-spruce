#!/usr/bin/env python3
"""
Patch Rice's glViewportWrapper and glScissor calls to offset by
M64P_VIEWPORT_X. Centers 4:3 content on widescreen displays.
"""

RICE_RENDER_PATH = "video-rice/projects/unix/../../src/OGLRender.cpp"

with open(RICE_RENDER_PATH, "r") as f:
    src = f.read()

# Add stdlib.h include and offset helper
src = src.replace(
    '#include "OGLRender.h"',
    '#include "OGLRender.h"\n#include <stdlib.h>\n\nstatic int _vp_offset(void) {\n    static int off = -1;\n    if (off == -1) { const char *e = getenv("M64P_VIEWPORT_X"); off = e ? atoi(e) : 0; }\n    return off;\n}',
    1
)

# Patch glViewport in glViewportWrapper
src = src.replace(
    '        glViewport(x,y,width,height);',
    '        glViewport(x + _vp_offset(), y, width, height);',
    1
)

# Patch all glScissor calls to add X offset
src = src.replace('glScissor(0,', 'glScissor(0 + _vp_offset(),', )
src = src.replace(
    'glScissor(int(gRDP.scissor.left*windowSetting.fMultX),',
    'glScissor(int(gRDP.scissor.left*windowSetting.fMultX) + _vp_offset(),',
)
src = src.replace(
    'glScissor(windowSetting.clipping.left,',
    'glScissor(windowSetting.clipping.left + _vp_offset(),',
)

with open(RICE_RENDER_PATH, "w") as f:
    f.write(src)

print("Patched Rice OGLRender.cpp with viewport + scissor centering")
