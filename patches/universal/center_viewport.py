#!/usr/bin/env python3
"""
Patch all video plugins to offset glViewport/glScissor X by M64P_VIEWPORT_X.
Centers 4:3 content on widescreen displays (TSP/TSPS 1280x720).
"""

import os

def get_vp_offset_helper():
    return '''
static int _vp_offset(void) {
    static int off = -1;
    if (off == -1) { const char *e = getenv("M64P_VIEWPORT_X"); off = e ? atoi(e) : 0; }
    return off;
}
'''

# ============================================================
# Rice: OGLRender.cpp
# ============================================================
RICE_PATH = "video-rice/projects/unix/../../src/OGLRender.cpp"

with open(RICE_PATH, "r") as f:
    src = f.read()

src = src.replace(
    '#include "OGLRender.h"',
    '#include "OGLRender.h"\n#include <stdlib.h>\n' + get_vp_offset_helper(),
    1
)

# Viewport in glViewportWrapper
src = src.replace(
    '        glViewport(x,y,width,height);',
    '        glViewport(x + _vp_offset(), y, width, height);',
    1
)

# All glScissor calls
src = src.replace('glScissor(0,', 'glScissor(0 + _vp_offset(),')
src = src.replace(
    'glScissor(int(gRDP.scissor.left*windowSetting.fMultX),',
    'glScissor(int(gRDP.scissor.left*windowSetting.fMultX) + _vp_offset(),',
)
src = src.replace(
    'glScissor(windowSetting.clipping.left,',
    'glScissor(windowSetting.clipping.left + _vp_offset(),',
)

with open(RICE_PATH, "w") as f:
    f.write(src)
print("Patched Rice")

# ============================================================
# Glide64mk2: OGLESglitchmain.cpp
# ============================================================
GLIDE_PATH = "video-glide64mk2/projects/unix/../../src/Glitch64/OGLESglitchmain.cpp"

with open(GLIDE_PATH, "r") as f:
    src = f.read()

# Add offset helper after includes
src = src.replace(
    '#include "glitchmain.h"',
    '#include "glitchmain.h"\n#include <stdlib.h>\n' + get_vp_offset_helper(),
    1
)

# Offset all glViewport X args (first arg is always 0 or an expression)
src = src.replace('glViewport(0, viewport_offset', 'glViewport(_vp_offset(), viewport_offset')
src = src.replace('glViewport( 0, viewport_offset', 'glViewport( _vp_offset(), viewport_offset')
src = src.replace('glViewport(0,0,width,height)', 'glViewport(_vp_offset(),0,width,height)')
src = src.replace('glViewport( 0, 0, width, height)', 'glViewport( _vp_offset(), 0, width, height)')

# Offset all glScissor X args
src = src.replace('glScissor(minx,', 'glScissor(minx + _vp_offset(),')
src = src.replace('glScissor(0, viewport_offset', 'glScissor(_vp_offset(), viewport_offset')
src = src.replace('glScissor( 0, 0, width, height)', 'glScissor( _vp_offset(), 0, width, height)')
src = src.replace('glScissor(0,0,width,height)', 'glScissor(_vp_offset(),0,width,height)')

with open(GLIDE_PATH, "w") as f:
    f.write(src)
print("Patched Glide64mk2")

# ============================================================
# GLideN64: opengl_CachedFunctions.cpp
# ============================================================
GLIDEN_PATH = "video-gliden64/src/Graphics/OpenGLContext/opengl_CachedFunctions.cpp"

with open(GLIDEN_PATH, "r") as f:
    src = f.read()

# Add offset helper
src = src.replace(
    '#include "opengl_CachedFunctions.h"',
    '#include "opengl_CachedFunctions.h"\n#include <stdlib.h>\n' + get_vp_offset_helper(),
    1
)

# Single viewport choke point
src = src.replace(
    '\t\tglViewport(_x, _y, _width, _height);',
    '\t\tglViewport(_x + _vp_offset(), _y, _width, _height);',
)

# Single scissor choke point
src = src.replace(
    '\t\tglScissor(_x, _y, _width, _height);',
    '\t\tglScissor(_x + _vp_offset(), _y, _width, _height);',
)

with open(GLIDEN_PATH, "w") as f:
    f.write(src)
print("Patched GLideN64")
