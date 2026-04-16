#!/usr/bin/env python3
"""
Patch GLideN64 to integrate the SpruceOS overlay menu.

Adds overlay source files to CMakeLists.txt, resolves core API functions,
and calls emu_frontend_init/frame from DisplayWindow::swapBuffers().
"""

import os

# ============================================================
# 1. Patch CMakeLists.txt: add overlay sources and SDL2_ttf
# ============================================================
CMAKE_PATH = "video-gliden64/src/CMakeLists.txt"

with open(CMAKE_PATH, "r") as f:
    cm = f.read()

# Add overlay sources before the main GLideN64_SOURCES definition
cm = cm.replace(
    'set(GLideN64_SOURCES',
    '''# SpruceOS overlay sources
set(OVERLAY_DIR /overlay)
set(OVERLAY_SOURCES
  ${OVERLAY_DIR}/emu_overlay.c
  ${OVERLAY_DIR}/emu_overlay_cfg.c
  ${OVERLAY_DIR}/emu_overlay_sdl.c
  ${OVERLAY_DIR}/emu_frontend.c
  ${OVERLAY_DIR}/cjson/cJSON.c
)

set(GLideN64_SOURCES''',
    1
)

# Add overlay sources to the shared library target
cm = cm.replace(
    'add_library( ${GLideN64_DLL_NAME} SHARED ${GLideN64_SOURCES} ${PATH_REVISION})',
    'add_library( ${GLideN64_DLL_NAME} SHARED ${GLideN64_SOURCES} ${OVERLAY_SOURCES} ${PATH_REVISION})',
    1
)

# Add overlay include directories
cm = cm.replace(
    'include_directories("${CMAKE_CURRENT_BINARY_DIR}/inc")',
    '''include_directories("${CMAKE_CURRENT_BINARY_DIR}/inc")
include_directories(/overlay /overlay/cjson)''',
    1
)

# Add SDL2_ttf and dl to link flags via the EGL_LIB variable (our builds always use EGL)
cm = cm.replace(
    '  set(OPENGL_LIBRARIES ${EGL_LIB})',
    '  set(OPENGL_LIBRARIES ${EGL_LIB} SDL2_ttf dl)',
    1
)

with open(CMAKE_PATH, "w") as f:
    f.write(cm)
print("Patched GLideN64 CMakeLists.txt")

# ============================================================
# 2. Patch DisplayWindow.cpp: integrate overlay into swapBuffers
# ============================================================
DW_PATH = "video-gliden64/src/DisplayWindow.cpp"

with open(DW_PATH, "r") as f:
    src = f.read()

# Add overlay includes after existing includes
src = src.replace(
    '#include "FrameBuffer.h"',
    '''#include "FrameBuffer.h"

/* SpruceOS overlay menu integration */
extern "C" {
#include "emu_frontend.h"
#include "emu_overlay_render.h"
extern EmuOvlRenderBackend* overlay_sdl_get_backend(void);
}
''',
    1
)

# Add overlay init and frame call in swapBuffers, before _swapBuffers()
src = src.replace(
    '''void DisplayWindow::swapBuffers()
{
	m_drawer.drawOSD();
	m_drawer.clearStatistics();
	_swapBuffers();''',
    '''void DisplayWindow::swapBuffers()
{
	/* SpruceOS: overlay menu frame processing */
	emu_frontend_frame(m_width, m_height);

	m_drawer.drawOSD();
	m_drawer.clearStatistics();
	_swapBuffers();''',
    1
)

with open(DW_PATH, "w") as f:
    f.write(src)
print("Patched GLideN64 DisplayWindow.cpp")

# ============================================================
# 3. Patch MupenPlusAPIImpl.cpp: resolve core API and init overlay
# ============================================================
API_PATH = "video-gliden64/src/mupenplus/MupenPlusAPIImpl.cpp"

with open(API_PATH, "r") as f:
    src = f.read()

# Add overlay include and static callback functions
src = src.replace(
    '#include "../GLideN64.h"\n#include "../Config.h"',
    '''#include "../GLideN64.h"
#include "../Config.h"

/* SpruceOS overlay menu */
extern "C" {
#include "emu_frontend.h"
#include "emu_overlay_render.h"
extern EmuOvlRenderBackend* overlay_sdl_get_backend(void);
}

/* Plugin ops callbacks for the overlay (C-compatible function pointers) */
static void gliden64_swap_buffers(void) {
    CoreVideo_GL_SwapBuffers();
}

static void gliden64_cycle_aspect(void) {
    /* TODO: cycle GLideN64 aspect ratio */
}

static EmuOvlRenderBackend* gliden64_get_render(void) {
    return overlay_sdl_get_backend();
}

static void gliden64_exec_on_video_thread(void (*fn)(void* ctx), void* ctx) {
    fn(ctx);
}
''',
    1
)

# Add overlay init after the CoreVideo dlsym block
# Find a reliable anchor point near the end of PluginStartup's dlsym calls
src = src.replace(
    '	CoreVideo_GL_GetDefaultFramebuffer = (ptr_VidExt_GL_GetDefaultFramebuffer) DLSYM(_CoreLibHandle, "VidExt_GL_GetDefaultFramebuffer");',
    '''	CoreVideo_GL_GetDefaultFramebuffer = (ptr_VidExt_GL_GetDefaultFramebuffer) DLSYM(_CoreLibHandle, "VidExt_GL_GetDefaultFramebuffer");

	/* SpruceOS: resolve core API for overlay and init */
	{
		static EmuFrontendCoreAPI coreAPI;
		static EmuFrontendPluginOps pluginOps;
		coreAPI.core_cmd = (emu_fe_core_cmd_fn)
			DLSYM(_CoreLibHandle, "CoreDoCommand");
		coreAPI.add_cheat = (emu_fe_add_cheat_fn)
			DLSYM(_CoreLibHandle, "CoreAddCheat");
		coreAPI.cheat_enabled = (emu_fe_cheat_enabled_fn)
			DLSYM(_CoreLibHandle, "CoreCheatEnabled");
		pluginOps.swap_buffers = gliden64_swap_buffers;
		pluginOps.cycle_aspect = gliden64_cycle_aspect;
		pluginOps.get_render = gliden64_get_render;
		pluginOps.exec_on_video_thread = gliden64_exec_on_video_thread;
		emu_frontend_init(&coreAPI, &pluginOps);
	}''',
    1
)

with open(API_PATH, "w") as f:
    f.write(src)
print("Patched GLideN64 MupenPlusAPIImpl.cpp")
