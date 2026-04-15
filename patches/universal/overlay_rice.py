#!/usr/bin/env python3
"""
Patch mupen64plus-video-rice to integrate the SpruceOS overlay menu.

Adds overlay source files to the build, resolves core API functions,
and calls emu_frontend_init/frame from UpdateScreen().
"""

import os

# ============================================================
# 1. Patch Makefile: add overlay sources and SDL2_ttf
# ============================================================
MAKEFILE_PATH = "video-rice/projects/unix/Makefile"

with open(MAKEFILE_PATH, "r") as f:
    mk = f.read()

# Add overlay source files after the last source file
mk = mk.replace(
    '$(SRCDIR)/Video.cpp',
    '''$(SRCDIR)/Video.cpp \\
	/overlay/emu_overlay.c \\
	/overlay/emu_overlay_cfg.c \\
	/overlay/emu_overlay_sdl.c \\
	/overlay/emu_frontend.c \\
	/overlay/cjson/cJSON.c''',
    1
)

# Add overlay include path to CFLAGS
mk = mk.replace(
    'CFLAGS += $(OPTFLAGS) $(WARNFLAGS) -ffast-math -fno-strict-aliasing -fvisibility=hidden -I$(SRCDIR)',
    'CFLAGS += $(OPTFLAGS) $(WARNFLAGS) -ffast-math -fno-strict-aliasing -fvisibility=hidden -I$(SRCDIR) -I/overlay -I/overlay/cjson',
    1
)

# Add SDL2_ttf and dl to linker flags
mk = mk.replace(
    'LDLIBS += $(SDL_LDLIBS)',
    'LDLIBS += $(SDL_LDLIBS) -lSDL2_ttf -ldl',
    1
)

with open(MAKEFILE_PATH, "w") as f:
    f.write(mk)
print("Patched Rice Makefile")

# ============================================================
# 2. Patch Video.cpp: integrate overlay
# ============================================================
VIDEO_PATH = "video-rice/src/Video.cpp"

with open(VIDEO_PATH, "r") as f:
    src = f.read()

# Add overlay includes after the existing includes
src = src.replace(
    '#include "version.h"',
    '''#include "version.h"

/* SpruceOS overlay menu integration */
#include "emu_frontend.h"
#include "emu_overlay_render.h"
extern EmuOvlRenderBackend* overlay_sdl_get_backend(void);

static bool s_overlayReady = false;

/* Plugin ops callbacks for the overlay */
static void rice_swap_buffers(void) {
    CoreVideo_GL_SwapBuffers();
}

static void rice_cycle_aspect(void) {
    /* TODO: cycle Rice aspect ratio */
}

static EmuOvlRenderBackend* rice_get_render(void) {
    return overlay_sdl_get_backend();
}

static void rice_exec_on_video_thread(void (*fn)(void* ctx), void* ctx) {
    fn(ctx); /* Rice is single-threaded */
}
''',
    1
)

# In PluginStartup, resolve core API functions after CoreLibHandle is set
# Find the end of PluginStartup to add the core API resolution
src = src.replace(
    '    if (l_PluginInit)\n        return M64ERR_ALREADY_INIT;',
    '''    if (l_PluginInit)
        return M64ERR_ALREADY_INIT;

    /* SpruceOS: resolve core API for overlay */
    {
        static EmuFrontendCoreAPI s_coreAPI;
        static EmuFrontendPluginOps s_pluginOps;
        s_coreAPI.core_cmd = (emu_fe_core_cmd_fn)
            osal_dynlib_getproc(CoreLibHandle, "CoreDoCommand");
        s_coreAPI.add_cheat = (emu_fe_add_cheat_fn)
            osal_dynlib_getproc(CoreLibHandle, "CoreAddCheat");
        s_coreAPI.cheat_enabled = (emu_fe_cheat_enabled_fn)
            osal_dynlib_getproc(CoreLibHandle, "CoreCheatEnabled");
        s_pluginOps.swap_buffers = rice_swap_buffers;
        s_pluginOps.cycle_aspect = rice_cycle_aspect;
        s_pluginOps.get_render = rice_get_render;
        s_pluginOps.exec_on_video_thread = rice_exec_on_video_thread;
        emu_frontend_init(&s_coreAPI, &s_pluginOps);
        s_overlayReady = true;
    }''',
    1
)

# In UpdateScreen, call emu_frontend_frame after rendering
src = src.replace(
    'EXPORT void CALL UpdateScreen(void)\n{',
    '''EXPORT void CALL UpdateScreen(void)
{
    /* SpruceOS: overlay menu frame processing */
    if (s_overlayReady)
        emu_frontend_frame(windowSetting.uDisplayWidth, windowSetting.uDisplayHeight);
''',
    1
)

with open(VIDEO_PATH, "w") as f:
    f.write(src)
print("Patched Rice Video.cpp")
