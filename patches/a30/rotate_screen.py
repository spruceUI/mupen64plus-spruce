#!/usr/bin/env python3
"""
Patch mupen64plus-core vidext.c to rotate the display for the Miyoo A30.

The A30 panel is 480x640 portrait. Mali fullscreen always creates a 480x640
framebuffer. Plugins need 640x480 for the game — they get clipped without FBO.

This patch:
  - Saves the real EGL surface framebuffer ID before creating anything
  - Creates an FBO at 640x480 so plugins can render the full game unclipped
  - On swap: saves GL state, binds real screen FB, draws FBO rotated 90 CCW,
    restores GL state, re-binds FBO for next frame
  - GetDefaultFramebuffer returns FBO id for plugins that query it

Activated by M64P_ROTATE=1 env var.
"""

VIDEXT_PATH = "core/projects/unix/../../src/api/vidext.c"

with open(VIDEXT_PATH, "r") as f:
    src = f.read()

code = r'''
/* === A30 screen rotation === */
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
#include <stdlib.h>

static int l_rot = -1;
static GLint l_rotScreenFB = -1;
static int l_rotW = 0, l_rotH = 0;
static GLuint l_rotFBO = 0, l_rotColor = 0, l_rotDepth = 0;
static GLuint l_rotProg = 0, l_rotVBO = 0;

static void rot_init(int gameW, int gameH)
{
    /* save EGL surface FB id BEFORE creating our FBO */
    glGetIntegerv(GL_FRAMEBUFFER_BINDING, &l_rotScreenFB);

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
    glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,gameW,gameH,0,GL_RGBA,GL_UNSIGNED_BYTE,0);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);

    /* depth — try 24-bit (matches Mali default), fallback 16 */
    glGenRenderbuffers(1,&l_rotDepth);
    glBindRenderbuffer(GL_RENDERBUFFER,l_rotDepth);
    glRenderbufferStorage(GL_RENDERBUFFER,GL_DEPTH_COMPONENT24_OES,gameW,gameH);

    glGenFramebuffers(1,&l_rotFBO);
    glBindFramebuffer(GL_FRAMEBUFFER,l_rotFBO);
    glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,l_rotColor,0);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,GL_RENDERBUFFER,l_rotDepth);

    if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
        glBindRenderbuffer(GL_RENDERBUFFER,l_rotDepth);
        glRenderbufferStorage(GL_RENDERBUFFER,GL_DEPTH_COMPONENT16,gameW,gameH);
        glFramebufferRenderbuffer(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,GL_RENDERBUFFER,l_rotDepth);
    }

    /* clear FBO to black */
    glClearColor(0,0,0,1);
    glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);

    /* 90 CCW rotation quad */
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

    l_rotW=gameW; l_rotH=gameH;
}

static void rot_blit(int scrW, int scrH)
{
    /* save GL state */
    GLint sProg, sTex, sVBO, sActive, sVP[4];
    GLboolean sDepth, sBlend, sCull, sScissor, sDepthMask;
    glGetIntegerv(GL_CURRENT_PROGRAM, &sProg);
    glGetIntegerv(GL_TEXTURE_BINDING_2D, &sTex);
    glGetIntegerv(GL_ARRAY_BUFFER_BINDING, &sVBO);
    glGetIntegerv(GL_ACTIVE_TEXTURE, &sActive);
    glGetIntegerv(GL_VIEWPORT, sVP);
    glGetBooleanv(GL_DEPTH_WRITEMASK, &sDepthMask);
    sDepth = glIsEnabled(GL_DEPTH_TEST);
    sBlend = glIsEnabled(GL_BLEND);
    sCull = glIsEnabled(GL_CULL_FACE);
    sScissor = glIsEnabled(GL_SCISSOR_TEST);

    /* bind real screen, draw rotated FBO texture */
    glBindFramebuffer(GL_FRAMEBUFFER, l_rotScreenFB);
    glViewport(0,0,scrW,scrH);
    glClearColor(0,0,0,1);
    glClear(GL_COLOR_BUFFER_BIT);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_BLEND);
    glDisable(GL_CULL_FACE);
    glDisable(GL_SCISSOR_TEST);
    glDepthMask(GL_FALSE);
    glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);

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

    /* restore GL state */
    glDisableVertexAttribArray(0);
    glDisableVertexAttribArray(1);
    glBindBuffer(GL_ARRAY_BUFFER, sVBO);
    glActiveTexture(sActive);
    glBindTexture(GL_TEXTURE_2D, sTex);
    glUseProgram(sProg);
    glViewport(sVP[0], sVP[1], sVP[2], sVP[3]);
    glDepthMask(sDepthMask);
    if (sDepth) glEnable(GL_DEPTH_TEST); else glDisable(GL_DEPTH_TEST);
    if (sBlend) glEnable(GL_BLEND); else glDisable(GL_BLEND);
    if (sCull) glEnable(GL_CULL_FACE); else glDisable(GL_CULL_FACE);
    if (sScissor) glEnable(GL_SCISSOR_TEST); else glDisable(GL_SCISSOR_TEST);

    /* re-bind FBO for next frame */
    glBindFramebuffer(GL_FRAMEBUFFER, l_rotFBO);
}
/* === end A30 rotation === */

'''

last_include = src.rfind("#include")
end_of_line = src.index("\n", last_include) + 1
src = src[:end_of_line] + code + src[end_of_line:]

# === 2. Check env var ===

marker = '    /* set the mode */\n'
env_check = '''    /* A30: check rotation env */
    if (l_rot == -1) {
        const char *e = getenv("M64P_ROTATE");
        l_rot = (e && e[0] == '1') ? 1 : 0;
    }

'''
src = src.replace(marker, env_check + marker, 1)

# === 3. After ShowCursor: clear screen, create FBO ===

cursor = '    SDL_ShowCursor(SDL_DISABLE);\n'
setup = '''
    /* A30: clear screen, create FBO at game resolution */
    if (l_rot == 1 && l_rotFBO == 0) {
        glClearColor(0,0,0,1);
        glClear(GL_COLOR_BUFFER_BIT);
        SDL_GL_SwapWindow(l_pWindow);
        glClear(GL_COLOR_BUFFER_BIT);
        rot_init(Width, Height);
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

# === 5. SwapBuffers ===

old_swap = '''    SDL_GL_SwapWindow(l_pWindow);
    return M64ERR_SUCCESS;
}'''
new_swap = '''    if (l_rot == 1 && l_rotFBO != 0) {
        int sw, sh;
        SDL_GetWindowSize(l_pWindow, &sw, &sh);
        rot_blit(sw, sh);
        SDL_GL_SwapWindow(l_pWindow);
        return M64ERR_SUCCESS;
    }

    SDL_GL_SwapWindow(l_pWindow);
    return M64ERR_SUCCESS;
}'''
src = src.replace(old_swap, new_swap, 1)

with open(VIDEXT_PATH, "w") as f:
    f.write(src)

print("Patched vidext.c with A30 rotation (FBO + screen FB query + state restore)")
