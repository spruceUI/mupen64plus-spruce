/*
 * a30_input_shim - Input remapper for Miyoo A30 + mupen64plus
 *
 * Reads keyboard events from the A30's button input device (event3).
 * Normally does NOT grab — events pass through to SDL and the
 * homebutton_watchdog as usual.
 *
 * When R2 is held: grabs event3, remaps face buttons to C-button
 * keycodes via uinput. On R2 release: ungrabs, back to normal.
 *
 * This allows the home button / game switcher to work normally
 * while still providing R2-hold C-button combos.
 *
 * Usage: a30_input_shim <input_device> &
 *
 * A30 button keycodes (from platform cfg):
 *   A=57(space) B=29(lctrl) X=42(lshift) Y=56(lalt)
 *   L1=15(tab) L2=18(e) R1=14(backspace) R2=20(t)
 *   Start=28(enter) Select=97(rctrl)
 *   DPad: Up=103 Down=108 Left=105 Right=106
 *
 * C-button output keycodes (chosen to not conflict):
 *   C-Up=22(u) C-Down=36(j) C-Left=37(k) C-Right=38(l)
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <linux/input.h>
#include <linux/uinput.h>
#include <signal.h>

/* A30 physical keycodes */
#define KC_A       57   /* space */
#define KC_B       29   /* lctrl */
#define KC_X       42   /* lshift */
#define KC_Y       56   /* lalt */
#define KC_R2      20   /* t */

/* C-button output keycodes */
#define KC_C_UP    22   /* u */
#define KC_C_DOWN  36   /* j */
#define KC_C_LEFT  37   /* k */
#define KC_C_RIGHT 38   /* l */

static volatile int running = 1;
static int uinput_fd = -1;

static void handle_signal(int sig)
{
    (void)sig;
    running = 0;
}

static int setup_uinput(void)
{
    int fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
    if (fd < 0) {
        perror("open /dev/uinput");
        return -1;
    }

    ioctl(fd, UI_SET_EVBIT, EV_KEY);
    for (int i = 0; i < 256; i++)
        ioctl(fd, UI_SET_KEYBIT, i);

    struct uinput_user_dev uidev;
    memset(&uidev, 0, sizeof(uidev));
    snprintf(uidev.name, UINPUT_MAX_NAME_SIZE, "a30_mupen_shim");
    uidev.id.bustype = BUS_VIRTUAL;
    uidev.id.vendor  = 0x1234;
    uidev.id.product = 0x5678;
    uidev.id.version = 1;

    write(fd, &uidev, sizeof(uidev));
    ioctl(fd, UI_DEV_CREATE);
    usleep(100000);

    return fd;
}

static void emit(int fd, int type, int code, int value)
{
    struct input_event ev;
    memset(&ev, 0, sizeof(ev));
    ev.type = type;
    ev.code = code;
    ev.value = value;
    write(fd, &ev, sizeof(ev));
}

static void emit_key(int fd, int code, int value)
{
    emit(fd, EV_KEY, code, value);
    emit(fd, EV_SYN, SYN_REPORT, 0);
}

int main(int argc, char *argv[])
{
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <input_device>\n", argv[0]);
        return 1;
    }

    signal(SIGTERM, handle_signal);
    signal(SIGINT, handle_signal);

    int input_fd = open(argv[1], O_RDONLY);
    if (input_fd < 0) {
        perror("open input device");
        return 1;
    }

    /* do NOT grab on startup — let watchdog and SDL read event3 normally */

    uinput_fd = setup_uinput();
    if (uinput_fd < 0) {
        close(input_fd);
        return 1;
    }

    int r2_held = 0;
    int grabbed = 0;

    struct input_event ev;
    while (running) {
        ssize_t n = read(input_fd, &ev, sizeof(ev));
        if (n != sizeof(ev))
            break;

        if (ev.type != EV_KEY)
            continue; /* ignore non-key events when not grabbed */

        if (ev.code == KC_R2) {
            if (ev.value == 1 && !r2_held) {
                /* R2 pressed: grab event3 so face buttons only go through shim */
                r2_held = 1;
                ioctl(input_fd, EVIOCGRAB, 1);
                grabbed = 1;
            } else if (ev.value == 0 && r2_held) {
                /* R2 released: ungrab, back to normal */
                r2_held = 0;
                if (grabbed) {
                    ioctl(input_fd, EVIOCGRAB, 0);
                    grabbed = 0;
                }
            }
            continue; /* R2 is consumed, never forwarded */
        }

        /* when R2 held (grabbed), remap face buttons to C-button keycodes */
        if (r2_held) {
            int remapped = -1;
            switch (ev.code) {
                case KC_A: remapped = KC_C_RIGHT; break; /* East  → C-Right */
                case KC_B: remapped = KC_C_DOWN;  break; /* South → C-Down  */
                case KC_X: remapped = KC_C_UP;    break; /* North → C-Up    */
                case KC_Y: remapped = KC_C_LEFT;  break; /* West  → C-Left  */
            }
            if (remapped >= 0) {
                emit_key(uinput_fd, remapped, ev.value);
            }
            /* while grabbed, all other keys are consumed (not forwarded) */
            continue;
        }

        /* when not grabbed, do nothing — events go through event3 to SDL directly */
    }

    /* cleanup */
    if (grabbed)
        ioctl(input_fd, EVIOCGRAB, 0);
    close(input_fd);

    ioctl(uinput_fd, UI_DEV_DESTROY);
    close(uinput_fd);

    return 0;
}
