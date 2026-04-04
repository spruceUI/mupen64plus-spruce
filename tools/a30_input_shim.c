/*
 * a30_input_shim - Input remapper for Miyoo A30 + mupen64plus
 *
 * Reads keyboard events from the A30's button input device (event3),
 * handles R2-hold modifier for C-button combos, and emits remapped
 * keyboard events via uinput.
 *
 * When R2 is NOT held: buttons pass through as-is.
 * When R2 IS held: face buttons become C-button keycodes.
 *
 * Usage: a30_input_shim <input_device> &
 *        e.g. a30_input_shim /dev/input/event3 &
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

    /* enable key events */
    ioctl(fd, UI_SET_EVBIT, EV_KEY);

    /* register all keycodes we might emit (0-255 covers standard keys) */
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

    /* small delay for device to register */
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

    /* grab the input device so events don't go elsewhere */
    ioctl(input_fd, EVIOCGRAB, 1);

    uinput_fd = setup_uinput();
    if (uinput_fd < 0) {
        close(input_fd);
        return 1;
    }

    int r2_held = 0;

    struct input_event ev;
    while (running) {
        ssize_t n = read(input_fd, &ev, sizeof(ev));
        if (n != sizeof(ev))
            break;

        /* pass through non-key events (SYN, etc.) */
        if (ev.type != EV_KEY) {
            emit(uinput_fd, ev.type, ev.code, ev.value);
            continue;
        }

        /* track R2 state but don't forward it — R2 is consumed as modifier */
        if (ev.code == KC_R2) {
            r2_held = (ev.value != 0); /* 1=press, 2=repeat, 0=release */
            continue;
        }

        /* when R2 held, remap face buttons to C-button keycodes */
        if (r2_held) {
            int remapped = -1;
            switch (ev.code) {
                case KC_A: remapped = KC_C_DOWN;  break;
                case KC_B: remapped = KC_C_RIGHT; break;
                case KC_X: remapped = KC_C_LEFT;  break;
                case KC_Y: remapped = KC_C_UP;    break;
            }
            if (remapped >= 0) {
                emit_key(uinput_fd, remapped, ev.value);
                continue;
            }
        }

        /* pass through everything else unchanged */
        emit_key(uinput_fd, ev.code, ev.value);
    }

    /* cleanup */
    ioctl(input_fd, EVIOCGRAB, 0);
    close(input_fd);

    ioctl(uinput_fd, UI_DEV_DESTROY);
    close(uinput_fd);

    return 0;
}
