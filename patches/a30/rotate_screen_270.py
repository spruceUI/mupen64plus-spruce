#!/usr/bin/env python3
"""
Patch mupen64plus-core vidext.c to rotate the GL framebuffer for the
Miyoo A30's 270-degree rotated panel (480x640 physical, 640x480 logical).

Strategy:
  - Create the SDL window at swapped dimensions (HxW) to match the panel
  - Plugins render to an FBO at their requested resolution (WxH)
  - On swap, draw the FBO texture rotated 90 CCW onto the real screen
  - Activated by M64P_ROTATE=1 env var
"""

VIDEXT_PATH = "core/projects/unix/../../src/api/vidext.c"

with open(VIDEXT_PATH, "r") as f:
    src = f.read()

# === 1. Add rotation code after includes ===

rotation_code = r'''
/* === A30 screen rotation === */
#include <GLES2/gl2.h>
#include <stdlib.h>

static int l_RotEnabled = -1; /* -1=unchecked, 0=off, 1=on */
static int l_RotGameW = 0;
static int l_RotGameH = 0;
static GLuint l_RotFBO = 0;
static GLuint l_RotFBOTex = 0;
static GLuint l_RotFBODepth = 0;
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

static void rot_check_env(void)
{
    if (l_RotEnabled == -1) {
        const char *e = getenv("M64P_ROTATE");
        l_RotEnabled = (e && e[0] == '1') ? 1 : 0;
    }
}

static void rot_setup(int gameW, int gameH)
{
    if (l_RotReady) return;

    /* shader */
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

    /* FBO for plugins to render into at their native resolution */
    glGenTextures(1, &l_RotFBOTex);
    glBindTexture(GL_TEXTURE_2D, l_RotFBOTex);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, gameW, gameH, 0, GL_RGBA, GL_UNSIGNED_BYTE, NULL);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);

    glGenRenderbuffers(1, &l_RotFBODepth);
    glBindRenderbuffer(GL_RENDERBUFFER, l_RotFBODepth);
    glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT16, gameW, gameH);

    glGenFramebuffers(1, &l_RotFBO);
    glBindFramebuffer(GL_FRAMEBUFFER, l_RotFBO);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, l_RotFBOTex, 0);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, l_RotFBODepth);

    /* bind FBO so plugins render to it */
    glBindFramebuffer(GL_FRAMEBUFFER, l_RotFBO);

    /* 90 CCW rotation quad */
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

    l_RotGameW = gameW;
    l_RotGameH = gameH;
    l_RotReady = 1;
}

static void rot_blit(int screenW, int screenH)
{
    /* draw FBO texture rotated onto the real screen */
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    glViewport(0, 0, screenW, screenH);
    glClearColor(0.0f, 0.0f, 0.0f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_BLEND);
    glDisable(GL_CULL_FACE);
    glDisable(GL_SCISSOR_TEST);

    glUseProgram(l_RotProg);
    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, l_RotFBOTex);
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

    /* re-bind FBO for next frame */
    glBindFramebuffer(GL_FRAMEBUFFER, l_RotFBO);
}
/* === end A30 rotation === */

'''

last_include = src.rfind("#include")
end_of_include_line = src.index("\n", last_include) + 1
src = src[:end_of_include_line] + rotation_code + src[end_of_include_line:]

# === 2. Swap window dimensions in VidExt_SetVideoMode ===

swap_marker = '    /* set the mode */\n'
swap_code = '''    /* A30: check rotation env and swap window dims to match portrait panel */
    rot_check_env();
    int l_OrigWidth = Width, l_OrigHeight = Height;
    if (l_RotEnabled == 1) {
        Width = l_OrigHeight;
        Height = l_OrigWidth;
    }

'''
src = src.replace(swap_marker, swap_code + swap_marker, 1)

# === 3. After GL context creation, set up FBO and restore reported size ===
# Find the SDL_ShowCursor line which comes after window/context setup

show_cursor = '    SDL_ShowCursor(SDL_DISABLE);\n'
fbo_setup = '''
    /* A30: create FBO at game resolution, bind it, report original size to plugins */
    if (l_RotEnabled == 1) {
        rot_setup(l_OrigWidth, l_OrigHeight);
        /* report the game's logical size, not the swapped window size */
        Width = l_OrigWidth;
        Height = l_OrigHeight;
    }

'''
src = src.replace(show_cursor, show_cursor + fbo_setup, 1)

# === 4. VidExt_GL_GetDefaultFramebuffer returns FBO ===

old_getfb = '''    return 0;
}

EXPORT m64p_error CALL VidExt_VK_GetSurface'''
new_getfb = '''    if (l_RotEnabled == 1 && l_RotFBO != 0)
        return l_RotFBO;
    return 0;
}

EXPORT m64p_error CALL VidExt_VK_GetSurface'''
src = src.replace(old_getfb, new_getfb, 1)

# === 5. Patch VidExt_GL_SwapBuffers ===

old_swap = '''    SDL_GL_SwapWindow(l_pWindow);
    return M64ERR_SUCCESS;
}'''

new_swap = '''    /* A30: blit rotated FBO to screen */
    if (l_RotEnabled == 1 && l_RotReady) {
        int sw, sh;
        SDL_GetWindowSize(l_pWindow, &sw, &sh);
        rot_blit(sw, sh);
    }

    SDL_GL_SwapWindow(l_pWindow);
    return M64ERR_SUCCESS;
}'''

src = src.replace(old_swap, new_swap, 1)

with open(VIDEXT_PATH, "w") as f:
    f.write(src)

print("Patched vidext.c with FBO-based screen rotation")
