#!/usr/bin/env python3
"""
Patch mupen64plus-core vidext.c to rotate the display for the Miyoo A30.

The A30 panel is 480x640 portrait with no hardware rotation. This patch:
  - Creates the SDL window at 480x640 (matching the panel)
  - Creates an FBO at the game's native resolution (e.g. 640x480)
  - Plugins render to the FBO via GetDefaultFramebuffer
  - On swap, draws the FBO texture rotated 90 CCW onto the real screen
  - Uses 24-bit depth on the FBO to match Mali's default framebuffer

Activated by M64P_ROTATE=1 env var.
"""

VIDEXT_PATH = "core/projects/unix/../../src/api/vidext.c"

with open(VIDEXT_PATH, "r") as f:
    src = f.read()

# === 1. Rotation code block — inserted after last #include ===

code = r'''
/* === A30 screen rotation === */
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
#include <stdlib.h>

static int l_rot = -1; /* -1=unchecked, 0=off, 1=on */
static int l_rotW = 0, l_rotH = 0;
static GLuint l_rotFBO = 0, l_rotColor = 0, l_rotDepth = 0;
static GLuint l_rotProg = 0, l_rotVBO = 0;

static void rot_init_gl(int w, int h)
{
    /* shader */
    const char *vs =
        "attribute vec2 p; attribute vec2 t;"
        "varying vec2 v;"
        "void main(){gl_Position=vec4(p,0,1);v=t;}";
    const char *fs =
        "precision mediump float;"
        "varying vec2 v; uniform sampler2D s;"
        "void main(){gl_FragColor=texture2D(s,v);}";
    GLuint v1=glCreateShader(GL_VERTEX_SHADER);
    glShaderSource(v1,1,&vs,0); glCompileShader(v1);
    GLuint f1=glCreateShader(GL_FRAGMENT_SHADER);
    glShaderSource(f1,1,&fs,0); glCompileShader(f1);
    l_rotProg=glCreateProgram();
    glAttachShader(l_rotProg,v1); glAttachShader(l_rotProg,f1);
    glBindAttribLocation(l_rotProg,0,"p");
    glBindAttribLocation(l_rotProg,1,"t");
    glLinkProgram(l_rotProg);
    glDeleteShader(v1); glDeleteShader(f1);

    /* FBO color texture at game resolution */
    glGenTextures(1,&l_rotColor);
    glBindTexture(GL_TEXTURE_2D,l_rotColor);
    glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,0);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);

    /* FBO depth renderbuffer — 24-bit to match Mali default FB */
    glGenRenderbuffers(1,&l_rotDepth);
    glBindRenderbuffer(GL_RENDERBUFFER,l_rotDepth);
    glRenderbufferStorage(GL_RENDERBUFFER,GL_DEPTH_COMPONENT24_OES,w,h);

    /* FBO */
    glGenFramebuffers(1,&l_rotFBO);
    glBindFramebuffer(GL_FRAMEBUFFER,l_rotFBO);
    glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,l_rotColor,0);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,GL_RENDERBUFFER,l_rotDepth);

    /* verify */
    GLenum status = glCheckFramebufferStatus(GL_FRAMEBUFFER);
    if (status != GL_FRAMEBUFFER_COMPLETE) {
        /* fallback to 16-bit depth if 24 not supported */
        glBindRenderbuffer(GL_RENDERBUFFER,l_rotDepth);
        glRenderbufferStorage(GL_RENDERBUFFER,GL_DEPTH_COMPONENT16,w,h);
        glFramebufferRenderbuffer(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,GL_RENDERBUFFER,l_rotDepth);
    }

    /* clear FBO to black */
    glClearColor(0,0,0,1);
    glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);

    /* 90 CCW rotation quad: pos(x,y) + texcoord(u,v) */
    float q[]={
        -1,-1, 0,1,
         1,-1, 0,0,
        -1, 1, 1,1,
         1, 1, 1,0,
    };
    glGenBuffers(1,&l_rotVBO);
    glBindBuffer(GL_ARRAY_BUFFER,l_rotVBO);
    glBufferData(GL_ARRAY_BUFFER,sizeof(q),q,GL_STATIC_DRAW);
    glBindBuffer(GL_ARRAY_BUFFER,0);

    l_rotW=w; l_rotH=h;
}

static void rot_blit(int sw, int sh)
{
    glBindFramebuffer(GL_FRAMEBUFFER,0);
    glViewport(0,0,sw,sh);
    glClearColor(0,0,0,1);
    glClear(GL_COLOR_BUFFER_BIT);

    glDisable(GL_DEPTH_TEST);
    glDisable(GL_BLEND);
    glDisable(GL_CULL_FACE);
    glDisable(GL_SCISSOR_TEST);
    glDisable(GL_STENCIL_TEST);
    glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);
    glDepthMask(GL_FALSE);

    glUseProgram(l_rotProg);
    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D,l_rotColor);
    glUniform1i(glGetUniformLocation(l_rotProg,"s"),0);

    glBindBuffer(GL_ARRAY_BUFFER,l_rotVBO);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0,2,GL_FLOAT,GL_FALSE,16,(void*)0);
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1,2,GL_FLOAT,GL_FALSE,16,(void*)8);
    glDrawArrays(GL_TRIANGLE_STRIP,0,4);

    glDisableVertexAttribArray(0);
    glDisableVertexAttribArray(1);
    glBindBuffer(GL_ARRAY_BUFFER,0);
    glUseProgram(0);
    glDepthMask(GL_TRUE);
}
/* === end A30 rotation === */

'''

last_include = src.rfind("#include")
end_of_line = src.index("\n", last_include) + 1
src = src[:end_of_line] + code + src[end_of_line:]

# === 2. In VidExt_SetVideoMode: swap dims for window creation ===

marker = '    /* set the mode */\n'
swap = '''    /* A30: check rotation, swap window dims to match portrait panel */
    if (l_rot == -1) {
        const char *e = getenv("M64P_ROTATE");
        l_rot = (e && e[0] == '1') ? 1 : 0;
    }
    int l_gameW = Width, l_gameH = Height;
    if (l_rot == 1) {
        Width = l_gameH;
        Height = l_gameW;
    }

'''
src = src.replace(marker, swap + marker, 1)

# === 3. After GL context + ShowCursor: create FBO, clear screen, restore dims ===

cursor = '    SDL_ShowCursor(SDL_DISABLE);\n'
setup = '''
    /* A30: clear real screen, create FBO at game res, restore dims for plugins */
    if (l_rot == 1 && l_rotFBO == 0) {
        glClearColor(0,0,0,1);
        glClear(GL_COLOR_BUFFER_BIT);
        SDL_GL_SwapWindow(l_pWindow);
        glClear(GL_COLOR_BUFFER_BIT);
        rot_init_gl(l_gameW, l_gameH);
        Width = l_gameW;
        Height = l_gameH;
    }

'''
src = src.replace(cursor, cursor + setup, 1)

# === 4. GetDefaultFramebuffer returns FBO ===

old_fb = '''    return 0;
}

EXPORT m64p_error CALL VidExt_VK_GetSurface'''
new_fb = '''    if (l_rot == 1 && l_rotFBO != 0)
        return l_rotFBO;
    return 0;
}

EXPORT m64p_error CALL VidExt_VK_GetSurface'''
src = src.replace(old_fb, new_fb, 1)

# === 5. SwapBuffers: blit rotated FBO then swap ===

old_swap = '''    SDL_GL_SwapWindow(l_pWindow);
    return M64ERR_SUCCESS;
}'''
new_swap = '''    if (l_rot == 1 && l_rotFBO != 0) {
        int sw, sh;
        SDL_GetWindowSize(l_pWindow, &sw, &sh);
        rot_blit(sw, sh);
        SDL_GL_SwapWindow(l_pWindow);
        /* re-bind FBO for next frame */
        glBindFramebuffer(GL_FRAMEBUFFER, l_rotFBO);
        return M64ERR_SUCCESS;
    }

    SDL_GL_SwapWindow(l_pWindow);
    return M64ERR_SUCCESS;
}'''
src = src.replace(old_swap, new_swap, 1)

with open(VIDEXT_PATH, "w") as f:
    f.write(src)

print("Patched vidext.c with A30 screen rotation (FBO + 24-bit depth)")
