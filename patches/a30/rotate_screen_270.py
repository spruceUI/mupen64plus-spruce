#!/usr/bin/env python3
"""
Patch mupen64plus-core vidext.c to rotate the GL framebuffer on every swap.
Fixes the Miyoo A30's 270-degree rotated panel (480x640 physical, 640x480 logical).

Strategy:
  - Do NOT change window dimensions — plugins render at their native resolution
  - In VidExt_GL_SwapBuffers, capture the framebuffer to a texture, then
    draw it rotated back into the same framebuffer before presenting
  - The Mali fbdev driver's implicit rotation cancels our pre-rotation
  - Activated by M64P_ROTATE=1 env var
"""

VIDEXT_PATH = "core/projects/unix/../../src/api/vidext.c"

with open(VIDEXT_PATH, "r") as f:
    src = f.read()

# === 1. Add rotation globals and helpers after the existing includes ===

rotation_code = r'''
/* === A30 screen rotation === */
#include <GLES2/gl2.h>
#include <stdlib.h>

static int l_RotateEnabled = -1; /* -1=unchecked, 0=off, 1=on */
static int l_RotGameW = 0;
static int l_RotGameH = 0;
static GLuint l_RotTex = 0;
static GLuint l_RotProg = 0;
static GLuint l_RotVBO = 0;
static int l_RotReady = 0;

static const char *l_RotVS =
    "attribute vec2 aPos;\n"
    "attribute vec2 aTC;\n"
    "varying vec2 vTC;\n"
    "void main() {\n"
    "    gl_Position = vec4(aPos, 0.0, 1.0);\n"
    "    vTC = aTC;\n"
    "}\n";

static const char *l_RotFS =
    "precision mediump float;\n"
    "varying vec2 vTC;\n"
    "uniform sampler2D uTex;\n"
    "void main() {\n"
    "    gl_FragColor = texture2D(uTex, vTC);\n"
    "}\n";

static void rot_setup(int w, int h)
{
    if (l_RotReady) return;

    /* compile shaders */
    GLuint vs = glCreateShader(GL_VERTEX_SHADER);
    glShaderSource(vs, 1, &l_RotVS, NULL);
    glCompileShader(vs);
    GLuint fs = glCreateShader(GL_FRAGMENT_SHADER);
    glShaderSource(fs, 1, &l_RotFS, NULL);
    glCompileShader(fs);
    l_RotProg = glCreateProgram();
    glAttachShader(l_RotProg, vs);
    glAttachShader(l_RotProg, fs);
    glBindAttribLocation(l_RotProg, 0, "aPos");
    glBindAttribLocation(l_RotProg, 1, "aTC");
    glLinkProgram(l_RotProg);
    glDeleteShader(vs);
    glDeleteShader(fs);

    /* texture for framebuffer capture */
    glGenTextures(1, &l_RotTex);
    glBindTexture(GL_TEXTURE_2D, l_RotTex);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, w, h, 0, GL_RGB, GL_UNSIGNED_BYTE, NULL);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glBindTexture(GL_TEXTURE_2D, 0);

    /* fullscreen quad with rotated tex coords
     * The Mali fbdev maps the framebuffer onto the A30's physically
     * rotated panel with an implicit 90 CW rotation. We pre-rotate
     * 90 CCW to cancel it out. */
    float verts[] = {
        /* x      y      u     v   */
        -1.0f, -1.0f,  0.0f, 1.0f,
         1.0f, -1.0f,  0.0f, 0.0f,
        -1.0f,  1.0f,  1.0f, 1.0f,
         1.0f,  1.0f,  1.0f, 0.0f,
    };
    glGenBuffers(1, &l_RotVBO);
    glBindBuffer(GL_ARRAY_BUFFER, l_RotVBO);
    glBufferData(GL_ARRAY_BUFFER, sizeof(verts), verts, GL_STATIC_DRAW);
    glBindBuffer(GL_ARRAY_BUFFER, 0);

    l_RotGameW = w;
    l_RotGameH = h;
    l_RotReady = 1;
}

static void rot_apply(int w, int h)
{
    if (!l_RotReady) rot_setup(w, h);

    /* save GL state we're about to clobber */
    GLint prevProg, prevTex, prevVBO;
    GLboolean prevDepth, prevBlend, prevCull, prevScissor;
    glGetIntegerv(GL_CURRENT_PROGRAM, &prevProg);
    glGetIntegerv(GL_TEXTURE_BINDING_2D, &prevTex);
    glGetIntegerv(GL_ARRAY_BUFFER_BINDING, &prevVBO);
    prevDepth = glIsEnabled(GL_DEPTH_TEST);
    prevBlend = glIsEnabled(GL_BLEND);
    prevCull = glIsEnabled(GL_CULL_FACE);
    prevScissor = glIsEnabled(GL_SCISSOR_TEST);

    /* capture current framebuffer into texture */
    glBindTexture(GL_TEXTURE_2D, l_RotTex);
    glCopyTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, 0, 0, w, h);

    /* draw rotated fullscreen quad */
    glViewport(0, 0, w, h);
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

    /* restore GL state */
    glDisableVertexAttribArray(0);
    glDisableVertexAttribArray(1);
    glBindBuffer(GL_ARRAY_BUFFER, prevVBO);
    glBindTexture(GL_TEXTURE_2D, prevTex);
    glUseProgram(prevProg);
    if (prevDepth) glEnable(GL_DEPTH_TEST);
    if (prevBlend) glEnable(GL_BLEND);
    if (prevCull) glEnable(GL_CULL_FACE);
    if (prevScissor) glEnable(GL_SCISSOR_TEST);
}
/* === end A30 rotation === */

'''

# Insert after the last #include
last_include = src.rfind("#include")
end_of_include_line = src.index("\n", last_include) + 1
src = src[:end_of_include_line] + rotation_code + src[end_of_include_line:]

# === 2. Patch VidExt_GL_SwapBuffers to rotate before swap ===

old_swap = '''    SDL_GL_SwapWindow(l_pWindow);
    return M64ERR_SUCCESS;
}'''

new_swap = '''    /* A30: pre-rotate framebuffer to cancel Mali fbdev's implicit rotation */
    if (l_RotateEnabled == -1) {
        const char *e = getenv("M64P_ROTATE");
        l_RotateEnabled = (e && e[0] == '1') ? 1 : 0;
    }
    if (l_RotateEnabled) {
        int w, h;
        SDL_GetWindowSize(l_pWindow, &w, &h);
        rot_apply(w, h);
    }

    SDL_GL_SwapWindow(l_pWindow);
    return M64ERR_SUCCESS;
}'''

src = src.replace(old_swap, new_swap, 1)

with open(VIDEXT_PATH, "w") as f:
    f.write(src)

print("Patched vidext.c with screen rotation support (no dimension swap)")
