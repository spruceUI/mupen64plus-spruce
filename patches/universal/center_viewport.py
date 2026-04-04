#!/usr/bin/env python3
"""
Patch mupen64plus-core vidext.c to offset glViewport calls when
M64P_VIEWPORT_X is set. This centers 4:3 content on widescreen displays.

The window is created at full display size. glViewport gets an X offset
so the rendered content appears centered. The full framebuffer is cleared
to black each frame so sidebars are clean.
"""

VIDEXT_PATH = "core/projects/unix/../../src/api/vidext.c"

with open(VIDEXT_PATH, "r") as f:
    src = f.read()

# Add viewport offset global after last #include
last_include = src.rfind("#include")
end_of_line = src.index("\n", last_include) + 1

offset_code = r'''
/* === SpruceOS: viewport centering for widescreen === */
static int l_vpOffsetX = -1; /* -1 = unchecked */

static int vp_get_offset(void) {
    if (l_vpOffsetX == -1) {
        const char *e = getenv("M64P_VIEWPORT_X");
        l_vpOffsetX = (e) ? atoi(e) : 0;
    }
    return l_vpOffsetX;
}
/* === end viewport centering === */

'''

src = src[:end_of_line] + offset_code + src[end_of_line:]

# Patch VidExt_SetVideoMode: after window creation, clear to black
cursor = '    SDL_ShowCursor(SDL_DISABLE);\n'
clear_code = '''
    /* SpruceOS: clear full screen to black (for widescreen sidebars) */
    if (vp_get_offset() > 0 && l_RenderMode == M64P_RENDER_OPENGL) {
        glClearColor(0.0f, 0.0f, 0.0f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT);
        SDL_GL_SwapWindow(l_pWindow);
        glClear(GL_COLOR_BUFFER_BIT);
    }

'''
src = src.replace(cursor, cursor + clear_code, 1)

with open(VIDEXT_PATH, "w") as f:
    f.write(src)

# Now patch Rice's glViewportWrapper to add the offset
RICE_RENDER_PATH = "video-rice/projects/unix/../../src/OGLRender.cpp"

with open(RICE_RENDER_PATH, "r") as f:
    rice_src = f.read()

# Patch the glViewport call inside glViewportWrapper
old_vp = '        glViewport(x,y,width,height);'
new_vp = '''        {
            const char *vpx_env = getenv("M64P_VIEWPORT_X");
            int vpx_off = vpx_env ? atoi(vpx_env) : 0;
            glViewport(x + vpx_off, y, width, height);
        }'''

rice_src = rice_src.replace(old_vp, new_vp, 1)

with open(RICE_RENDER_PATH, "w") as f:
    f.write(rice_src)

print("Patched vidext.c and Rice OGLRender.cpp with viewport centering")
