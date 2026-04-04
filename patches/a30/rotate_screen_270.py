#!/usr/bin/env python3
"""
Patch mupen64plus-core vidext.c to rotate the GL framebuffer 270 degrees
on every swap. This fixes the Miyoo A30's 270-degree rotated panel
(480x640 physical, 640x480 logical) for all video plugins.

Strategy:
  - Swap Width/Height in VidExt_SetVideoMode so the SDL window matches
    the physical portrait panel (480x640)
  - In VidExt_GL_SwapBuffers, copy the framebuffer to a texture, then
    draw it rotated 270 degrees before calling SDL_GL_SwapWindow
"""

import re

VIDEXT_PATH = "core/projects/unix/../../src/api/vidext.c"

with open(VIDEXT_PATH, "r") as f:
    src = f.read()

# === 1. Add rotation globals and helpers after the existing includes/globals ===

rotation_code = r'''
/* === A30 screen rotation (270 degrees) === */
#include <GLES2/gl2.h>

static int l_RotateEnabled = 0;
static int l_GameWidth = 0;
static int l_GameHeight = 0;
static GLuint l_RotTex = 0;
static GLuint l_RotProg = 0;
static GLuint l_RotVBO = 0;
static int l_RotInitialized = 0;

static const char *l_RotVertSrc =
    "attribute vec2 aPos;\n"
    "attribute vec2 aTC;\n"
    "varying vec2 vTC;\n"
    "void main() {\n"
    "    gl_Position = vec4(aPos, 0.0, 1.0);\n"
    "    vTC = aTC;\n"
    "}\n";

static const char *l_RotFragSrc =
    "precision mediump float;\n"
    "varying vec2 vTC;\n"
    "uniform sampler2D uTex;\n"
    "void main() {\n"
    "    gl_FragColor = texture2D(uTex, vTC);\n"
    "}\n";

static GLuint rot_compile_shader(GLenum type, const char *src)
{
    GLuint s = glCreateShader(type);
    glShaderSource(s, 1, &src, NULL);
    glCompileShader(s);
    return s;
}

static void rot_init(int gameW, int gameH)
{
    if (l_RotInitialized) return;

    /* shader program */
    GLuint vs = rot_compile_shader(GL_VERTEX_SHADER, l_RotVertSrc);
    GLuint fs = rot_compile_shader(GL_FRAGMENT_SHADER, l_RotFragSrc);
    l_RotProg = glCreateProgram();
    glAttachShader(l_RotProg, vs);
    glAttachShader(l_RotProg, fs);
    glBindAttribLocation(l_RotProg, 0, "aPos");
    glBindAttribLocation(l_RotProg, 1, "aTC");
    glLinkProgram(l_RotProg);
    glDeleteShader(vs);
    glDeleteShader(fs);

    /* texture to capture framebuffer */
    glGenTextures(1, &l_RotTex);
    glBindTexture(GL_TEXTURE_2D, l_RotTex);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, gameW, gameH, 0, GL_RGB, GL_UNSIGNED_BYTE, NULL);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glBindTexture(GL_TEXTURE_2D, 0);

    /* 270-degree rotation: fullscreen quad with rotated tex coords
     * Vertex layout: x, y, u, v
     * 270 CCW rotation tex coords map the landscape framebuffer
     * onto the portrait panel correctly */
    float verts[] = {
        /* pos (NDC)     tex coord (270 CCW) */
        -1.0f, -1.0f,   1.0f, 0.0f,
         1.0f, -1.0f,   1.0f, 1.0f,
        -1.0f,  1.0f,   0.0f, 0.0f,
         1.0f,  1.0f,   0.0f, 1.0f,
    };
    glGenBuffers(1, &l_RotVBO);
    glBindBuffer(GL_ARRAY_BUFFER, l_RotVBO);
    glBufferData(GL_ARRAY_BUFFER, sizeof(verts), verts, GL_STATIC_DRAW);
    glBindBuffer(GL_ARRAY_BUFFER, 0);

    l_RotInitialized = 1;
}

static void rot_draw_rotated(int screenW, int screenH, int gameW, int gameH)
{
    if (!l_RotInitialized)
        rot_init(gameW, gameH);

    /* capture current framebuffer into texture */
    glBindTexture(GL_TEXTURE_2D, l_RotTex);
    glCopyTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, 0, 0, gameW, gameH);

    /* clear and set up for rotated draw */
    glViewport(0, 0, screenW, screenH);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_BLEND);
    glDisable(GL_CULL_FACE);
    glDisable(GL_SCISSOR_TEST);

    glUseProgram(l_RotProg);
    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, l_RotTex);
    glUniform1i(glGetUniformLocation(l_RotProg, "uTex"), 0);

    glBindBuffer(GL_ARRAY_BUFFER, l_RotVBO);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 16, (void*)0);
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 16, (void*)8);

    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);

    glDisableVertexAttribArray(0);
    glDisableVertexAttribArray(1);
    glBindBuffer(GL_ARRAY_BUFFER, 0);
    glBindTexture(GL_TEXTURE_2D, 0);
    glUseProgram(0);
}
/* === end A30 rotation === */

'''

# Insert after the last #include
last_include = src.rfind("#include")
end_of_include_line = src.index("\n", last_include) + 1
src = src[:end_of_include_line] + rotation_code + src[end_of_include_line:]

# === 2. Patch VidExt_SetVideoMode to swap Width/Height ===
# Insert before the "set the mode" comment block, which precedes the if/else DebugMessage

swap_marker = '    /* set the mode */\n'
swap_code = '''    /* A30: swap dimensions for portrait panel and enable rotation */
    {
        const char *rot_env = getenv("M64P_ROTATE");
        if (rot_env && rot_env[0] == '1') {
            l_RotateEnabled = 1;
            l_GameWidth = Width;
            l_GameHeight = Height;
            int tmp = Width;
            Width = Height;
            Height = tmp;
        }
    }

'''

src = src.replace(swap_marker, swap_code + swap_marker, 1)

# === 3. Patch VidExt_GL_SwapBuffers to rotate before swap ===

old_swap = '''    SDL_GL_SwapWindow(l_pWindow);
    return M64ERR_SUCCESS;
}'''

new_swap = '''    /* A30: rotate framebuffer before presenting */
    if (l_RotateEnabled) {
        int sw, sh;
        SDL_GetWindowSize(l_pWindow, &sw, &sh);
        rot_draw_rotated(sw, sh, l_GameWidth, l_GameHeight);
    }

    SDL_GL_SwapWindow(l_pWindow);
    return M64ERR_SUCCESS;
}'''

src = src.replace(old_swap, new_swap, 1)

with open(VIDEXT_PATH, "w") as f:
    f.write(src)

print("Patched vidext.c with 270-degree screen rotation support")
