#!/usr/bin/env python3
"""
Patch mupen64plus-core to handle SIGUSR1 as save-state-and-quit.

When SIGUSR1 is received, mupen saves state to the current slot then
stops emulation cleanly. This matches PPSSPP and ScummVM behavior in
SpruceOS, allowing the homebutton_watchdog to trigger save-and-exit.

The signal flag is checked in VidExt_GL_SwapBuffers (runs every frame).
"""

# === 1. Patch main.c: add signal handler and setup function ===

MAIN_PATH = "core/projects/unix/../../src/main/main.c"

with open(MAIN_PATH, "r") as f:
    src = f.read()

# Add signal.h include
src = src.replace(
    '#include <stdlib.h>',
    '#include <signal.h>\n#include <stdlib.h>',
    1
)

# Add handler and setup before main_stop()
handler = r'''
/* === SpruceOS: SIGUSR1 = save state and quit === */
volatile sig_atomic_t g_SaveAndQuit = 0;

static void sigusr1_handler(int sig)
{
    (void)sig;
    g_SaveAndQuit = 1;
}

void main_setup_sigusr1(void)
{
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = sigusr1_handler;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0;
    sigaction(SIGUSR1, &sa, NULL);
}
/* === end SpruceOS SIGUSR1 === */

'''

src = src.replace(
    'void main_stop(void)\n{',
    handler + 'void main_stop(void)\n{',
    1
)

# Register handler at emulation start
src = src.replace(
    '    g_EmulatorRunning = 1;',
    '    main_setup_sigusr1();\n    g_EmulatorRunning = 1;',
    1
)

with open(MAIN_PATH, "w") as f:
    f.write(src)

# === 2. Patch main.h: add declarations ===

MAINH_PATH = "core/projects/unix/../../src/main/main.h"

with open(MAINH_PATH, "r") as f:
    h_src = f.read()

h_src = h_src.replace(
    'void main_stop(void);',
    'void main_stop(void);\nvoid main_setup_sigusr1(void);\nextern volatile sig_atomic_t g_SaveAndQuit;',
    1
)

# Add signal.h include
h_src = h_src.replace(
    '#define __MAIN_H__',
    '#define __MAIN_H__\n\n#include <signal.h>',
    1
)

with open(MAINH_PATH, "w") as f:
    f.write(h_src)

# === 3. Patch vidext.c: check flag every frame in SwapBuffers ===

VIDEXT_PATH = "core/projects/unix/../../src/api/vidext.c"

with open(VIDEXT_PATH, "r") as f:
    v_src = f.read()

# Add include for main.h
v_src = v_src.replace(
    '#include "osal/preproc.h"',
    '#include "osal/preproc.h"\n#include "main/main.h"\n#include "main/savestates.h"',
    1
)

# Add check at the top of VidExt_GL_SwapBuffers
old_swap = 'EXPORT m64p_error CALL VidExt_GL_SwapBuffers(void)\n{'
new_swap = '''EXPORT m64p_error CALL VidExt_GL_SwapBuffers(void)
{
    /* SpruceOS: check for SIGUSR1 save-and-quit */
    if (g_SaveAndQuit) {
        g_SaveAndQuit = 0;
        main_state_save(1, NULL);
        main_stop();
        return M64ERR_SUCCESS;
    }
'''

v_src = v_src.replace(old_swap, new_swap, 1)

with open(VIDEXT_PATH, "w") as f:
    f.write(v_src)

print("Patched mupen64plus core with SIGUSR1 save-and-quit support")
