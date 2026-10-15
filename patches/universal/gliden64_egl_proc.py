#!/usr/bin/env python3
"""
Patch GLideN64's EGL function loader to look GL entry points up the way SDL does.

Under -DEGL, GLideN64 resolves every GL function, core ones included, with eglGetProcAddress.
EGL 1.4 promises that only for extensions; Mali advertises EGL_KHR_get_all_proc_addresses, the
PowerVR A133P stack (EGL 1.4, DDK 1.19) does not. Without EGL 1.5 or that extension, take each
function from libGLESv2.so.2 first and ask eglGetProcAddress only for what it does not export.
"""

PATH = "video-gliden64/src/Graphics/OpenGLContext/GLFunctions.cpp"

OLD = '''#elif defined(EGL)

#define glGetProcAddress eglGetProcAddress
#define GL_GET_PROC_ADR(proc_type, proc_name) ptr##proc_name = (proc_type) glGetProcAddress("gl"#proc_name)
#define GL_GET_PROC_ADR_EGL(proc_type, proc_name) ptr##proc_name = (proc_type) glGetProcAddress("egl"#proc_name)
'''

NEW = '''#elif defined(EGL)

#include <cstdio>
#include <cstring>
#include <dlfcn.h>

// EGL 1.4 promises eglGetProcAddress only for extensions: without EGL 1.5 or
// EGL_KHR_get_all_proc_addresses, take core entry points from the GLES library, as SDL does.
static void * eglProcAddress(const char * name)
{
	static int allFromEgl = -1;
	static void * gles = nullptr;
	if (allFromEgl < 0) {
		EGLDisplay dpy = eglGetCurrentDisplay();
		const char * version = dpy != EGL_NO_DISPLAY ? eglQueryString(dpy, EGL_VERSION) : nullptr;
		const char * extensions = dpy != EGL_NO_DISPLAY ? eglQueryString(dpy, EGL_EXTENSIONS) : nullptr;
		int major = 0, minor = 0;
		if (version != nullptr)
			sscanf(version, "%d.%d", &major, &minor);
		allFromEgl = (major > 1 || (major == 1 && minor >= 5) ||
			(extensions != nullptr && strstr(extensions, "EGL_KHR_get_all_proc_addresses") != nullptr)) ? 1 : 0;
		if (allFromEgl == 0)
			gles = dlopen("libGLESv2.so.2", RTLD_NOW);
		LOG(LOG_VERBOSE, "EGL %s: GL entry points from %s", version != nullptr ? version : "(no display)",
			allFromEgl ? "eglGetProcAddress" : "libGLESv2.so.2, then eglGetProcAddress");
	}
	void * proc = gles != nullptr ? dlsym(gles, name) : nullptr;
	if (proc == nullptr)
		proc = reinterpret_cast<void *>(eglGetProcAddress(name));
	return proc;
}

#define glGetProcAddress eglGetProcAddress
#define GL_GET_PROC_ADR(proc_type, proc_name) ptr##proc_name = (proc_type) eglProcAddress("gl"#proc_name)
#define GL_GET_PROC_ADR_EGL(proc_type, proc_name) ptr##proc_name = (proc_type) eglProcAddress("egl"#proc_name)
'''

with open(PATH, "r") as f:
    src = f.read()

if OLD not in src:
    raise SystemExit("gliden64_egl_proc.py: EGL loader block not found in " + PATH)
src = src.replace(OLD, NEW, 1)

with open(PATH, "w") as f:
    f.write(src)
print("Patched GLideN64 EGL function loader")
