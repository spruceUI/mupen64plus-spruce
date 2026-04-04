#!/usr/bin/env python3
"""
Patch mupen64plus-core vidext.c to rotate the display for the Miyoo A30.

Creates window at 480x640 (matching panel), plugins render at 640x480
into the GL framebuffer (clipped/stretched by the viewport mismatch),
then we capture and draw rotated before swap.

Not perfect — there will be aspect ratio distortion from the viewport
mismatch — but it displays correctly oriented on the A30 panel.

Activated by M64P_ROTATE=1 env var.
"""

VIDEXT_PATH = "core/projects/unix/../../src/api/vidext.c"

with open(VIDEXT_PATH, "r") as f:
    src = f.read()

code = r'''
/* === A30 screen rotation === */
#include <GLES2/gl2.h>
#include <stdlib.h>

static int l_rot = -1;
static int l_rotW = 0, l_rotH = 0;
static GLuint l_rotTex = 0, l_rotProg = 0, l_rotVBO = 0;
static int l_rotReady = 0;

static void rot_setup(int w, int h)
{
    if (l_rotReady) return;

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

    glGenTextures(1,&l_rotTex);
    glBindTexture(GL_TEXTURE_2D,l_rotTex);
    glTexImage2D(GL_TEXTURE_2D,0,GL_RGB,w,h,0,GL_RGB,GL_UNSIGNED_BYTE,0);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
    glBindTexture(GL_TEXTURE_2D,0);

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

    l_rotW=w; l_rotH=h;
    l_rotReady=1;
}

static void rot_apply(int w, int h)
{
    if (!l_rotReady) rot_setup(w,h);

    glBindTexture(GL_TEXTURE_2D,l_rotTex);
    glCopyTexSubImage2D(GL_TEXTURE_2D,0,0,0,0,0,w,h);

    glViewport(0,0,w,h);
    glClearColor(0,0,0,1);
    glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_BLEND);
    glDisable(GL_CULL_FACE);
    glDisable(GL_SCISSOR_TEST);
    glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);

    glUseProgram(l_rotProg);
    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D,l_rotTex);
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
    glBindTexture(GL_TEXTURE_2D,0);
    glUseProgram(0);
}
/* === end A30 rotation === */

'''

last_include = src.rfind("#include")
end_of_line = src.index("\n", last_include) + 1
src = src[:end_of_line] + code + src[end_of_line:]

# === 2. Swap window dims ===

marker = '    /* set the mode */\n'
swap = '''    /* A30: swap window dims to match portrait panel */
    if (l_rot == -1) {
        const char *e = getenv("M64P_ROTATE");
        l_rot = (e && e[0] == '1') ? 1 : 0;
    }
    if (l_rot == 1) {
        int tmp = Width;
        Width = Height;
        Height = tmp;
    }

'''
src = src.replace(marker, swap + marker, 1)

# === 3. SwapBuffers ===

old_swap = '''    SDL_GL_SwapWindow(l_pWindow);
    return M64ERR_SUCCESS;
}'''
new_swap = '''    if (l_rot == 1) {
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

print("Patched vidext.c with A30 rotation (swap dims + copy-rotate)")
