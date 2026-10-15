/* Native Xbox / SDL bridge for the explicitly supported PST:EE build.
 * No executable-file writes or background input. The startup loader installs
 * one fingerprint-guarded registration hook, removed after binding on the Lua
 * thread; the normal game loop then calls the bridge from its UI callbacks.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <bcrypt.h>
#include <xinput.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <math.h>
#include <stdlib.h>
#include <stdio.h>

typedef struct lua_State lua_State;
typedef int (*LuaFunction)(lua_State *);
typedef void (*PushClosure)(lua_State *, LuaFunction, int);
typedef void (*PushNumber)(lua_State *, double);
typedef double (*ToNumber)(lua_State *, int, int *);
typedef DWORD (WINAPI *GetPadState)(DWORD, XINPUT_STATE *);
typedef void *(*GetMouseFocus)(void);
typedef unsigned (*GetMouseState)(int *, int *);
typedef void (*GetWindowSize)(void *, int *, int *);
typedef unsigned (*GetWindowId)(void *);
typedef unsigned (*GetTicks)(void);
typedef void (*WarpMouse)(void *, int, int);
typedef int (*PushEvent)(void *);
typedef int (*WaitEventTimeout)(void *, int);
typedef int (*GetScancode)(int);
typedef int (*SdlShowCursor)(int);
typedef int (*SdlEventWatch)(void *, void *);
typedef void (*AddEventWatch)(SdlEventWatch, void *);

static unsigned char *engine;
static PushClosure push_closure;
static PushNumber push_number;
static ToNumber to_number;
static GetPadState get_pad;
static GetMouseFocus mouse_focus;
static GetMouseFocus keyboard_focus;
static GetMouseState mouse_state;
static GetWindowSize window_size;
static GetWindowId window_id;
static GetTicks get_ticks;
static WarpMouse warp_mouse;
static PushEvent push_event;
static WaitEventTimeout wait_event_timeout;
static unsigned movie_a_previous;
#define CONTROLLER_MOVIE_KEY_ID 0x5053544du
static GetScancode get_scancode;
static SdlShowCursor show_cursor;
static AddEventWatch add_event_watch;
static int event_watch_installed;
static volatile LONG physical_click_serial;
#define CONTROLLER_MOUSE_ID 0x50535450u
static int cursor_hidden_by_mod;
static int cursor_visibility_before_drive = 1;
static int last_slot = -1;
typedef int (*SetVideoPointer)(void *, void *, int, int);
static SetVideoPointer original_set_video_pointer;
static void *desired_video, *desired_pointer;
static int desired_pointer_flags, desired_pointer_mode;
static HANDLE runtime_log=INVALID_HANDLE_VALUE;
static unsigned runtime_log_lines;
static volatile int controller_steering_active;

typedef union {
    unsigned char bytes[56];
    struct {
        uint32_t type, timestamp, window, which;
        uint8_t button, state, clicks, padding;
        int32_t x, y;
    } mouse;
    struct {
        uint32_t type, timestamp, window;
        uint8_t state, repeat, padding2, padding3;
        int32_t scancode, key;
        uint16_t mod;
        uint16_t padding4;
        uint32_t unused;
    } key;
    struct {
        uint32_t type, timestamp, window, which, state;
        int32_t x, y, xrel, yrel;
    } motion;
    struct {
        uint32_t type, timestamp, window, which;
        int32_t x, y;
        uint32_t direction;
        float precise_x, precise_y;
        int32_t mouse_x, mouse_y;
    } wheel;
} SdlEvent;

_Static_assert(sizeof(SdlEvent) == 56, "SDL2 event union size");
_Static_assert(offsetof(SdlEvent, mouse.button) == 16, "SDL2 mouse button offset");
_Static_assert(offsetof(SdlEvent, mouse.x) == 20, "SDL2 mouse coordinate offset");
_Static_assert(offsetof(SdlEvent, key.scancode) == 16, "SDL2 keysym offset");
_Static_assert(offsetof(SdlEvent, motion.x) == 20, "SDL2 motion coordinate offset");
_Static_assert(offsetof(SdlEvent, wheel.y) == 20, "SDL2 wheel vertical offset");
_Static_assert(offsetof(SdlEvent, wheel.direction) == 24, "SDL2 wheel direction offset");

/* Watches may execute on an SDL worker thread. Only increment an atomic
 * counter; Lua consumes it on the game thread. Do not filter any stock input.
 */
static int watch_physical_input(void *unused, void *input) {
    (void)unused;
    const SdlEvent *event=input;
    if (event->mouse.type==0x401 && event->mouse.which!=CONTROLLER_MOUSE_ID)
        InterlockedIncrement(&physical_click_serial);
    return 1;
}

static int read_memory(uintptr_t address, void *out, size_t bytes) {
    SIZE_T count = 0;
    return address > 0xffff && ReadProcessMemory(GetCurrentProcess(), (const void *)address, out, bytes, &count) && count == bytes;
}
static uintptr_t read_pointer(uintptr_t address) {
    uintptr_t out = 0;
    read_memory(address, &out, sizeof(out));
    return out;
}
static void log_runtime(int operation,int a,int b,int c) {
    if (runtime_log==INVALID_HANDLE_VALUE || runtime_log_lines++>=5000) return;
    uintptr_t chitin=read_pointer((uintptr_t)engine+0x72c278),game=read_pointer(chitin+0x10c8);
    uint16_t state=0; uint8_t icon=0; int32_t count=0,run=0;
    read_memory(game+0x78b0,&state,2); read_memory(game+0x78b8,&icon,1);
    read_memory(game+0xa2b0,&count,4); read_memory(game+0xb9c0,&run,4);
    uint32_t id=UINT32_MAX; int32_t point[2]={0}; uint16_t action=0,action_ticks=0;
    uintptr_t head=read_pointer(game+0xa2a0);
    if (head && read_memory(head+0x10,&id,4)) {
        uintptr_t actor=read_pointer((uintptr_t)engine+0x72d868+((id>>16)&0x7fff)*16);
        read_memory(actor+0xc,point,8); read_memory(actor+0x3f0,&action,2);
        read_memory(actor+0x3ec,&action_ticks,2);
    }
    char line[300]; int length=snprintf(line,sizeof(line),"%u op=%d a=%d b=%d c=%d state=%u icon=%u selected=%d run=%d leader=%u xy=%d,%d action=%u actionTicks=%u\r\n",
        get_ticks ? get_ticks() : 0,operation,a,b,c,state,icon,count,run,id,point[0],point[1],action,action_ticks);
    if (length>0 && length<(int)sizeof(line)) {DWORD written=0; WriteFile(runtime_log,line,(DWORD)length,&written,NULL);}
}
static void log_party_members(void) {
    if (runtime_log==INVALID_HANDLE_VALUE) return;
    uintptr_t chitin=read_pointer((uintptr_t)engine+0x72c278),game=read_pointer(chitin+0x10c8);
    int32_t count=0; if (!read_memory(game+0xa2b0,&count,4) || count<1 || count>6) return;
    uintptr_t node=read_pointer(game+0xa2a0);
    IMAGE_NT_HEADERS64 *nt=(IMAGE_NT_HEADERS64 *)(engine+((IMAGE_DOS_HEADER *)engine)->e_lfanew);
    for (int n=0;n<count && node && runtime_log_lines<5000;++n) {
        uint32_t id=UINT32_MAX; uint16_t generation=0,action=0; int32_t point[2]={0}; uint8_t type=0,flags=0,speed=0;
        if (!read_memory(node+0x10,&id,4)) break;
        node=read_pointer(node);
        uintptr_t row=(uintptr_t)engine+0x72d860+((id>>16)&0x7fff)*16,actor=read_pointer(row+8);
        if (!read_memory(row,&generation,2) || generation!=(uint16_t)id || !read_memory(actor+8,&type,1) || type!=0x31) continue;
        read_memory(actor+0xc,point,8); read_memory(actor+0x3f0,&action,2); read_memory(actor+0x3958,&flags,1);
        if (flags&4) read_memory(actor+0x3960,&speed,1);
        else {
            uintptr_t animation=read_pointer(actor+0x3950),method=read_pointer(read_pointer(animation)+0xc0);
            if (method>=(uintptr_t)engine+0x1000 && method<(uintptr_t)engine+nt->OptionalHeader.SizeOfImage)
                speed=((uint8_t (*)(void *))method)((void *)animation);
        }
        char line[180]; int length=snprintf(line,sizeof(line),"%u member=%d id=%u xy=%d,%d moveScale=%u action=%u\r\n",get_ticks(),n,id,point[0],point[1],speed,action);
        if (length>0 && length<(int)sizeof(line)) {DWORD written=0; WriteFile(runtime_log,line,(DWORD)length,&written,NULL); ++runtime_log_lines;}
    }
}

static int supported_executable(void) {
    static const unsigned char expected[32] = {
        0x99,0xae,0x15,0x86,0x0c,0xfd,0xbc,0xda,0xad,0x0f,0x48,0xe0,0x05,0xee,0xe2,0x14,
        0x44,0x04,0x6b,0x21,0xde,0x84,0x8c,0x1d,0xea,0xb9,0x36,0x7e,0x82,0x46,0xa3,0xc5
    };
    wchar_t path[32768];
    DWORD length = GetModuleFileNameW(NULL, path, 32768);
    if (!length || length >= 32768) return 0;
    HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 0;
    BCRYPT_ALG_HANDLE algorithm = NULL;
    BCRYPT_HASH_HANDLE hash = NULL;
    DWORD object_size = 0, used = 0;
    unsigned char result[32], chunk[32768];
    unsigned char *object = NULL;
    int valid = 0;
    if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, NULL, 0) < 0) goto done;
    if (BCryptGetProperty(algorithm, BCRYPT_OBJECT_LENGTH, (PUCHAR)&object_size, sizeof(object_size), &used, 0) < 0) goto done;
    object = HeapAlloc(GetProcessHeap(), 0, object_size);
    if (!object || BCryptCreateHash(algorithm, &hash, object, object_size, NULL, 0, 0) < 0) goto done;
    for (;;) {
        DWORD got = 0;
        if (!ReadFile(file, chunk, sizeof(chunk), &got, NULL)) goto done;
        if (!got) break;
        if (BCryptHashData(hash, chunk, got, 0) < 0) goto done;
    }
    if (BCryptFinishHash(hash, result, sizeof(result), 0) < 0) goto done;
    valid = memcmp(result, expected, sizeof(result)) == 0;
done:
    if (hash) BCryptDestroyHash(hash);
    if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0);
    if (object) HeapFree(GetProcessHeap(), 0, object);
    CloseHandle(file);
    return valid;
}

/* Read-only position lookup mirrors the examined engine's object lookup and
 * world-to-client conversion. Every pointer read can fail without dereference.
 * No writes to actors, action queues, or game memory occur here.
 */
static int player_screen_position(double *sx, double *sy) {
    uintptr_t chitin = read_pointer((uintptr_t)engine + 0x72c278);
    uintptr_t game = read_pointer(chitin + 0x10c8);
    uintptr_t video = read_pointer(chitin + 0x268);
    uintptr_t world = read_pointer(chitin + 0x260);
    if (!game || !video || !world) return 0;
    uint8_t area_index = 0;
    int16_t party_count = 0;
    if (!read_memory(game + 0xa178, &area_index, 1) || area_index > 11) return 0;
    if (!read_memory(game + 0xa218, &party_count, 2) || party_count < 1 || party_count > 6) return 0;
    uintptr_t area = read_pointer(game + 0xa180 + (uintptr_t)area_index * 8);
    if (!area) return 0;
    int selected = 0;
    uintptr_t vtable = read_pointer(world);
    uintptr_t getter = read_pointer(vtable + 0x1c0);
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)engine;
    IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(engine + dos->e_lfanew);
    if (getter >= (uintptr_t)engine + 0x1000 && getter < (uintptr_t)engine + nt->OptionalHeader.SizeOfImage) {
        selected = ((int16_t (*)(void *))getter)((void *)world);
    }
    if (selected < 0 || selected >= party_count) selected = 0;
    uint32_t actor_id = 0;
    if (!read_memory(game + 0xa200 + (uintptr_t)selected * 4, &actor_id, 4) || actor_id == UINT32_MAX) return 0;
    /* Selected portrait can be invalid for multi-selection. Mirror the
     * examined CGameGroup leader getter, instead of assuming portrait zero.
     */
    int32_t selected_count = 0;
    if (read_memory(game + 0xa2b0, &selected_count, 4) && selected_count > 0 && selected_count <= 6) {
        uintptr_t head = read_pointer(game + 0xa2a0);
        uint32_t leader = UINT32_MAX;
        if (head && read_memory(head + 0x10, &leader, 4) && leader != UINT32_MAX) actor_id = leader;
    }
    uintptr_t row = (uintptr_t)engine + 0x72d860 + ((actor_id >> 16) & 0x7fff) * 16;
    uint16_t generation = 0;
    if (!read_memory(row, &generation, 2) || generation != (uint16_t)actor_id) return 0;
    uintptr_t actor = read_pointer(row + 8);
    int32_t position[2], view[2], scroll[2], dimensions[2], offsets[2];
    uint16_t reference_width = 0, reference_height = 0;
    float zoom = 0;
    if (!actor || !read_memory(actor + 0xc, position, 8)) return 0;
    if (!read_memory(area + 0x650, view, 8) || !read_memory(area + 0x698, scroll, 8)) return 0;
    if (!read_memory(video + 0x150, dimensions, 8) || !read_memory(video + 0x188, offsets, 8)) return 0;
    if (!read_memory((uintptr_t)engine + 0x72120c, &reference_width, 2) || !read_memory((uintptr_t)engine + 0x721210, &reference_height, 2)) return 0;
    if (!read_memory(area + 0xa14, &zoom, 4)) return 0;
    if (!reference_width || !reference_height || !isfinite(zoom) || zoom < 0.125f || zoom > 8.0f) return 0;
    if (position[0] < 0 || position[1] < 0 || position[0] > 32767 || position[1] > 32767) return 0;
    *sx = (((double)(position[0] - scroll[0] + view[0]) * dimensions[0] / reference_width) - offsets[1]) / zoom;
    *sy = (((double)(position[1] - scroll[1] + view[1]) * dimensions[1] / reference_height) - offsets[0]) / zoom;
    return isfinite(*sx) && isfinite(*sy);
}

static int foreground_game(void) {
    DWORD process = 0;
    GetWindowThreadProcessId(GetForegroundWindow(), &process);
    return process == GetCurrentProcessId();
}
static int poll_pad(XINPUT_STATE *state) {
    memset(state, 0, sizeof(*state));
    if (!get_pad) return 0;
    if (last_slot >= 0 && get_pad((DWORD)last_slot, state) == ERROR_SUCCESS) return 1;
    for (DWORD slot = 0; slot < 4; ++slot) {
        if (get_pad(slot, state) == ERROR_SUCCESS) {
            last_slot = (int)slot;
            return 1;
        }
    }
    last_slot = -1;
    memset(state, 0, sizeof(*state));
    return 0;
}
static void mouse_click(void *window, int x, int y, unsigned button) {
    SdlEvent event;
    memset(&event, 0, sizeof(event));
    event.mouse.timestamp = get_ticks();
    event.mouse.window = window_id(window);
    event.mouse.which = CONTROLLER_MOUSE_ID;
    event.mouse.button = (uint8_t)button;
    event.mouse.clicks = 1;
    event.mouse.x = x;
    event.mouse.y = y;
    event.mouse.type = 0x401;
    event.mouse.state = 1;
    push_event(&event);
    event.mouse.type = 0x402;
    event.mouse.state = 0;
    push_event(&event);
}
static void synchronize_pointer(void *window, int x, int y);
static void mouse_double_click(void *window,int x,int y) {
    /* This engine detects a double click from two successive left downs at
     * the same point, not SDL's clicks field (event loop RVA 4a5a85).
     */
    synchronize_pointer(window,x,y);
    mouse_click(window,x,y,1);
    mouse_click(window,x,y,1);
}
static void synchronize_pointer(void *window, int x, int y) {
    /* The engine caches hover/object state from motion, separately from the
     * button coordinates. Movement must establish that state before clicking.
     */
    warp_mouse(window, x, y);
    SdlEvent motion;
    memset(&motion, 0, sizeof(motion));
    motion.motion.type = 0x400;
    motion.motion.timestamp = get_ticks();
    motion.motion.window = window_id(window);
    motion.motion.which = CONTROLLER_MOUSE_ID;
    motion.motion.x = x;
    motion.motion.y = y;
    push_event(&motion);
}
static int queue_world_zoom(void *window, int direction, int width, int height, int focused) {
    if (!focused || !window || width<=0 || height<=0 || (direction!=1 && direction!=-1)) return 0;
    /* Use the stock wheel path. Center its anchor in the world, away from a
     * previously hovered toolbar or scrollable panel. Lua retains cursor hide.
     * Common SDL2 wheel fields are stable; newer fields occupy zero padding in
     * older builds. https://wiki.libsdl.org/SDL2/SDL_MouseWheelEvent
     */
    int x=width/2, y=height*3/8;
    synchronize_pointer(window,x,y);
    SdlEvent event; memset(&event,0,sizeof(event));
    event.wheel.type=0x403; event.wheel.timestamp=get_ticks();
    event.wheel.window=window_id(window); event.wheel.y=direction;
    event.wheel.which=CONTROLLER_MOUSE_ID;
    event.wheel.precise_y=(float)direction;
    event.wheel.mouse_x=x; event.wheel.mouse_y=y;
    push_event(&event);
    return 1;
}
static void set_drive_cursor_hidden(int hide) {
    if (hide && !cursor_hidden_by_mod) {
        cursor_visibility_before_drive = show_cursor(-1);
        cursor_hidden_by_mod = 1;
    }
    if (hide) {
        show_cursor(0);
        if (original_set_video_pointer) {
            uintptr_t chitin = read_pointer((uintptr_t)engine + 0x72c278);
            void *video = (void *)read_pointer(chitin + 0x268);
            if (video) {
                if (!desired_video) {
                    desired_video = video;
                    desired_pointer = (void *)read_pointer((uintptr_t)video + 0x160);
                    read_memory((uintptr_t)video + 4, &desired_pointer_mode, 4);
                }
                original_set_video_pointer(video, NULL, 0, desired_pointer_mode);
            }
        }
    }
    else if (cursor_hidden_by_mod) {
        cursor_hidden_by_mod = 0;
        uintptr_t chitin = read_pointer((uintptr_t)engine + 0x72c278);
        void *video = (void *)read_pointer(chitin + 0x268);
        if (original_set_video_pointer && video && desired_video == video)
            original_set_video_pointer(video, desired_pointer, desired_pointer_flags, desired_pointer_mode);
        desired_video = desired_pointer = NULL;
        show_cursor(cursor_visibility_before_drive > 0 ? 1 : 0);
    }
}
static void keyboard_event_marked(void *window, int key, int down, uint32_t marker) {
    SdlEvent event;
    memset(&event, 0, sizeof(event));
    event.key.type = down ? 0x300 : 0x301;
    event.key.timestamp = get_ticks();
    event.key.window = window ? window_id(window) : 0;
    event.key.state = down ? 1 : 0;
    event.key.scancode = get_scancode(key);
    event.key.key = key;
    event.key.unused = marker;
    push_event(&event);
}
static void keyboard_event(void *window, int key, int down) {
    keyboard_event_marked(window,key,down,0);
}

static int movie_playing(void) {
    /* Same active-engine/player checks as this build's Infinity_GetCurrentMovie.
     * This excludes the looping flame widget and the Movies selection screen. */
    uintptr_t chitin=read_pointer((uintptr_t)engine+0x72c278);
    uintptr_t movie=read_pointer(chitin+0x10d8);
    return movie && read_pointer(chitin+0x260)==movie && read_pointer(movie+0x58)!=0;
}
static int movie_skip_edge(int connected,int focused,int playing,unsigned buttons) {
    unsigned a=connected ? buttons&XINPUT_GAMEPAD_A : 0;
    int skip=connected && focused && playing && a && !movie_a_previous;
    movie_a_previous=a;
    return skip;
}
static int poll_filtered_movie_event(SdlEvent *event) {
    for (int n=0;n<16;n++) {
        int result=wait_event_timeout(event,0);
        if (!result || !event || (event->key.type!=0x300 && event->key.type!=0x301)
            || event->key.unused!=CONTROLLER_MOVIE_KEY_ID || movie_playing()) return result;
    }
    return 0;
}
static int poll_with_movie_skip(SdlEvent *event) {
    XINPUT_STATE pad;
    int connected=poll_pad(&pad);
    int playing=movie_playing();
    if (movie_skip_edge(connected,foreground_game(),playing,pad.Gamepad.wButtons)) {
        void *window=keyboard_focus();
        if (!window) window=mouse_focus();
        if (window) {
            keyboard_event_marked(window,27,1,CONTROLLER_MOVIE_KEY_ID);
            keyboard_event_marked(window,27,0,CONTROLLER_MOVIE_KEY_ID);
        }
    }
    /* Never let a queued movie Escape leak into the main menu after playback
     * ends. Only our marked keys are discarded; ordinary events are untouched. */
    return poll_filtered_movie_event(event);
}

#include "nearby_targets.h"

static void (*set_world_view)(void *,uint64_t,int16_t);
static uintptr_t follow_owner_world;
static int32_t follow_owner_id=-1;
static int follow_owned;
static int controller_camera_follow(int mode,int focused) {
    uintptr_t chitin=read_pointer((uintptr_t)engine+0x72c278);
    uintptr_t world=read_pointer(chitin+0x1148);
    int32_t current=-1; int result=0;
    if (!world || !read_memory(world+0xa58,&current,4) || !point_is_writable(world+0xa58)) return 0;
    if (mode==0) {
        if (follow_owned && follow_owner_world==world && current==follow_owner_id) {
            int32_t unlocked=-1; memcpy((void *)(world+0xa58),&unlocked,4); result=1;
        }
        follow_owned=0;
    } else if (focused && read_pointer(chitin+0x260)==world && mode==1 && current==-1) {
        uintptr_t game,area,video; uint32_t leader=UINT32_MAX; int32_t origin[2];
        if (interaction_context(&game,&area,&video) && selected_origin(game,area,&leader,origin)) {
            int32_t lock=(int32_t)leader;
            memcpy((void *)(world+0xa58),&lock,4);
            follow_owner_world=world; follow_owner_id=lock; follow_owned=1; result=1;
        }
    } else if (focused && read_pointer(chitin+0x260)==world && mode==2) {
        /* Explicit manual camera input takes priority over any follow lock,
         * including one left behind by an earlier plugin/selection change. */
        int32_t unlocked=-1; memcpy((void *)(world+0xa58),&unlocked,4);
        follow_owned=0; result=1;
    }
    int32_t after=-1; read_memory(world+0xa58,&after,4);
    log_runtime(19,mode,current,after);
    return result;
}
static int pan_world_camera(int dx,int dy,int width,int height,int focused) {
    if (!focused || !set_world_view || width<=0 || height<=0
        || dx < -128 || dx > 128 || dy < -128 || dy > 128 || (!dx && !dy)) return 0;
    uintptr_t chitin=read_pointer((uintptr_t)engine+0x72c278);
    uintptr_t world=read_pointer(chitin+0x1148);
    uintptr_t game,area,video;
    if (!world || read_pointer(chitin+0x260)!=world || !interaction_context(&game,&area,&video)) return 0;
    int32_t current[2],dimensions[2]; uint16_t rw=0,rh=0; float zoom=0;
    if (!read_memory(area+0x698,current,8) || !read_memory(video+0x150,dimensions,8)
        || !read_memory(area+0xa14,&zoom,4)
        || !read_memory((uintptr_t)engine+0x72120c,&rw,2)
        || !read_memory((uintptr_t)engine+0x721210,&rh,2)
        || dimensions[0]<=0 || dimensions[1]<=0 || !rw || !rh
        || !isfinite(zoom) || zoom<0.125f || zoom>8.0f
        || current[0]<-32768 || current[0]>32767 || current[1]<-32768 || current[1]>32767) return 0;
    /* Mirror the stock view-point command. Its renderer clamps to the area
     * limits and handles invalidation; duration zero applies on the next frame.
     * Convert client pixels to world units using the stock point projection.
     */
    int32_t target[2]={current[0]+(int32_t)lround((double)dx*rw*zoom/dimensions[0]),
        current[1]+(int32_t)lround((double)dy*rh*zoom/dimensions[1])};
    uint64_t point; memcpy(&point,target,8);
    set_world_view((void *)world,point,0);
    return 1;
}

/* Operation 0 polls; 1 warps only this game's cursor; 2 queues a mouse click;
 * 3 queues one keyboard edge; 4 synchronizes hover before a steering click;
 * 5 hides/restores the game's cursor for controller movement.
 * All SDL mutations are queued for the next game event loop, on the UI thread.
 */
static int dispatch(lua_State *state) {
    if (!event_watch_installed && add_event_watch) {
        /* First Lua poll occurs after the game's SDL startup. */
        add_event_watch(watch_physical_input,NULL);
        event_watch_installed=1;
    }
    int operation = (int)to_number(state, 1, NULL);
    int a = (int)to_number(state, 2, NULL);
    int b = (int)to_number(state, 3, NULL);
    int c = (int)to_number(state, 4, NULL);
    int focused = foreground_game();
    if (!focused) set_drive_cursor_hidden(0);
    else if (cursor_hidden_by_mod) set_drive_cursor_hidden(1);
    if (operation == 5) set_drive_cursor_hidden(focused && a != 0);
    void *window = mouse_focus();
    if (!window) window = keyboard_focus();
    int x = 0, y = 0, width = 0, height = 0;
    mouse_state(&x, &y);
    if (window) window_size(window, &width, &height);
    if (operation==12) {log_runtime(operation,a,b,c); if(a==200) log_party_members();}
    if ((operation>=6 && operation<=8) || operation==15) return dispatch_nearby(state,operation,(uint32_t)a,b,window,width,height,focused);
    if (operation>=9 && operation<=11) return dispatch_steering(state,operation,a,b,focused,c==1);
    if (operation==16) {
        int queued=queue_world_zoom(window,a,width,height,focused);
        log_runtime(operation,a,0,queued); push_number(state,queued); return 1;
    }
    if (operation==18) {
        int moved=pan_world_camera(a,b,width,height,focused);
        log_runtime(18,a,b,moved);
        push_number(state,moved); return 1;
    }
    if (operation==19) {push_number(state,controller_camera_follow(a,focused)); return 1;}
    if (window && width > 0 && height > 0) {
        if (focused && operation == 1) {
            if (a < 0) a = 0;
            if (b < 0) b = 0;
            if (a >= width) a = width - 1;
            if (b >= height) b = height - 1;
            warp_mouse(window, a, b);
        } else if (focused && operation==17 && a>=0 && b>=0 && a<width && b<height) {
            mouse_double_click(window,a,b);
            log_runtime(operation,a,b,1);
        } else if (focused && (operation == 2 || operation == 4) && a >= 0 && b >= 0 && a < width && b < height) {
            if (operation == 4) synchronize_pointer(window, a, b);
            mouse_click(window, a, b, c == 3 ? 3 : 1);
        } else if (operation == 3 && (focused || !b) && a > 0) {
            keyboard_event(window, a, b != 0);
            log_runtime(operation,a,b,c);
        }
    }
    if (!window && operation == 3 && !b && a > 0) keyboard_event(NULL, a, 0);
    XINPUT_STATE pad;
    int connected = poll_pad(&pad);
    if (!connected) set_drive_cursor_hidden(0);
    if (!focused) memset(&pad.Gamepad, 0, sizeof(pad.Gamepad));
    double px = 0, py = 0;
    int position_valid = focused && player_screen_position(&px, &py);
    int32_t selected_count = 0;
    uintptr_t chitin = read_pointer((uintptr_t)engine + 0x72c278);
    uintptr_t game = read_pointer(chitin + 0x10c8);
    if (!read_memory(game + 0xa2b0, &selected_count, 4) || selected_count < 0 || selected_count > 6) selected_count = 0;
    double values[20] = {
        connected, pad.Gamepad.wButtons, pad.Gamepad.sThumbLX, pad.Gamepad.sThumbLY,
        pad.Gamepad.sThumbRX, pad.Gamepad.sThumbRY, pad.Gamepad.bLeftTrigger,
        pad.Gamepad.bRightTrigger, x, y, width, height, get_ticks(), focused,
        px, py, position_valid, selected_count,
        (uint32_t)InterlockedCompareExchange(&physical_click_serial,0,0), movie_playing()
    };
    for (size_t index = 0; index < 20; ++index) push_number(state, values[index]);
    return 20;
}

static int initialize_bindings(void) {
    if (!supported_executable()) return 0;
    engine = (unsigned char *)GetModuleHandleW(NULL);
    static const unsigned char clear_code[8]={0x48,0x83,0xec,0x38,0x83,0x79,0x20,0};
    static const unsigned char move_code[5]={0x48,0x89,0x54,0x24,0x10};
    static const unsigned char run_code[10]={0x48,0x89,0x5c,0x24,0x18,0x48,0x89,0x7c,0x24,0x20};
    static const unsigned char view_code[10]={0x48,0x89,0x54,0x24,0x10,0x53,0x48,0x83,0xec,0x20};
    static const unsigned char pending_code[10]={0x48,0x89,0x5c,0x24,0x10,0x56,0x48,0x83,0xec,0x20};
    static const unsigned char path_code[10]={0x48,0x89,0x5c,0x24,0x10,0x57,0x48,0x83,0xec,0x20};
    static const unsigned char action_point_code[7]={0x48,0x8b,0x0e,0x49,0x89,0x4e,0x70};
    static const unsigned char follow_store_code[6]={0x89,0x83,0x58,0x0a,0,0};
    if (memcmp(engine+0x124f50,clear_code,8) || memcmp(engine+0x127320,move_code,5)
        || memcmp(engine+0x1a0e80,run_code,10) || memcmp(engine+0x366ac0,view_code,10)
        || memcmp(engine+0x164e30,pending_code,10) || memcmp(engine+0x41d350,path_code,10)
        || memcmp(engine+0x12482e,action_point_code,7)
        || memcmp(engine+0x35aa6a,follow_store_code,6)) return 0;
    group_clear_actions=(void (*)(void *))(engine+0x124f50);
    group_move=(void (*)(void *,uint64_t,int,uint16_t,uint64_t))(engine+0x127320);
    prepare_group_run=(void (*)(void *))(engine+0x1a0e80);
    clear_pending_actions=(void (*)(void *,int))(engine+0x164e30);
    request_move_path=(uint16_t (*)(void *,const int32_t *))(engine+0x41d350);
    set_world_view=(void (*)(void *,uint64_t,int16_t))(engine+0x366ac0);
    wchar_t log_path[32768];
    DWORD log_length=GetModuleFileNameW(NULL,log_path,32768);
    if (log_length && log_length<32730) {
        wchar_t *slash=wcsrchr(log_path,L'\\');
        if (slash) {
            wcscpy(slash+1,L"controller-runtime.log");
            runtime_log=CreateFileW(log_path,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
        }
    }
    /* Addresses are accepted only after the full executable SHA-256 check. */
    push_closure = (PushClosure)(engine + 0xe44c0);
    push_number = (PushNumber)(engine + 0xe4290);
    to_number = (ToNumber)(engine + 0xe3e90);
    HMODULE xinput = LoadLibraryW(L"xinput1_4.dll");
    if (!xinput) xinput = LoadLibraryW(L"xinput9_1_0.dll");
    if (xinput) get_pad = (GetPadState)(uintptr_t)GetProcAddress(xinput, "XInputGetState");
#define SDL_BIND(variable, type, name) variable = (type)(uintptr_t)GetProcAddress((HMODULE)engine, name); if (!variable) return 0
    SDL_BIND(mouse_focus, GetMouseFocus, "SDL_GetMouseFocus");
    SDL_BIND(keyboard_focus, GetMouseFocus, "SDL_GetKeyboardFocus");
    SDL_BIND(mouse_state, GetMouseState, "SDL_GetMouseState");
    SDL_BIND(window_size, GetWindowSize, "SDL_GetWindowSize");
    SDL_BIND(window_id, GetWindowId, "SDL_GetWindowID");
    SDL_BIND(get_ticks, GetTicks, "SDL_GetTicks");
    SDL_BIND(warp_mouse, WarpMouse, "SDL_WarpMouseInWindow");
    SDL_BIND(push_event, PushEvent, "SDL_PushEvent");
    SDL_BIND(get_scancode, GetScancode, "SDL_GetScancodeFromKey");
    SDL_BIND(show_cursor, SdlShowCursor, "SDL_ShowCursor");
    SDL_BIND(add_event_watch, AddEventWatch, "SDL_AddEventWatch");
#undef SDL_BIND
    return 1;
}

__declspec(dllexport) int luaopen_pstcontroller(lua_State *state) {
    if (!initialize_bindings()) return 0;
    push_closure(state, dispatch, 0);
    return 1;
}

typedef void (*SetGlobal)(lua_State *, const char *);
static SetGlobal original_set_global;
static lua_State *bound_state;
static unsigned char saved_prologue[15];

static void absolute_jump(unsigned char *destination, const void *function) {
    destination[0] = 0xff;
    destination[1] = 0x25;
    memset(destination + 2, 0, 4);
    memcpy(destination + 6, &function, sizeof(function));
}

static int filtered_video_pointer(void *video, void *pointer, int flags, int mode) {
    desired_video = video; desired_pointer = pointer;
    desired_pointer_flags = flags; desired_pointer_mode = mode;
    return original_set_video_pointer(video, cursor_hidden_by_mod ? NULL : pointer, flags, mode);
}

static int patch_checked_bytes(unsigned char *target, const unsigned char *expected, size_t size, void *replacement) {
    if (size < 14 || memcmp(target, expected, size) != 0) return 0;
    DWORD old = 0;
    if (!VirtualProtect(target, size, PAGE_EXECUTE_READWRITE, &old)) return 0;
    memset(target, 0x90, size);
    absolute_jump(target, replacement);
    DWORD ignored;
    VirtualProtect(target, size, old, &ignored);
    FlushInstructionCache(GetCurrentProcess(), target, size);
    return 1;
}

static unsigned char *make_steering_wait_gate(void) {
    unsigned char *gate=VirtualAlloc(NULL,128,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
    if (!gate) return NULL;
    size_t used=0;
    gate[used++]=0x9c; /* pushfq: preserve flags and RAX around the scope test */
    gate[used++]=0x50;
    gate[used++]=0x48; gate[used++]=0xb8;
    const volatile void *flag=&controller_steering_active;
    memcpy(gate+used,&flag,8); used+=8;
    gate[used++]=0x80; gate[used++]=0x38; gate[used++]=0;
    gate[used++]=0x58;
    gate[used++]=0x74; gate[used++]=15; /* inactive: original two loads */
    gate[used++]=0x9d;
    absolute_jump(gate+used,engine+0x127e3b); used+=14; /* skip only optional SmallWait creation */
    gate[used++]=0x9d;
    gate[used++]=0x48; gate[used++]=0xb8;
    const void *chitin_slot=engine+0x72c278;
    memcpy(gate+used,&chitin_slot,8); used+=8;
    gate[used++]=0x48; gate[used++]=0x8b; gate[used++]=0x00; /* mov rax,[rax] */
    static const unsigned char game_load[7]={0x48,0x8b,0x88,0xc8,0x10,0,0};
    memcpy(gate+used,game_load,7); used+=7;
    absolute_jump(gate+used,engine+0x127ddc); used+=14;
    DWORD old=0;
    if (!VirtualProtect(gate,128,PAGE_EXECUTE_READ,&old)) {VirtualFree(gate,0,MEM_RELEASE); return NULL;}
    FlushInstructionCache(GetCurrentProcess(),gate,used);
    return gate;
}
static int install_steering_wait_filter(void) {
    /* The standard formation route inserts opcode 83 (SmallWait) in this
     * optional block. Skip it ONLY while our group-order call is on the stack.
     * Movement actions, formation offsets and other game waits are intact.
     */
    static const unsigned char original[14]={0x48,0x8b,0x05,0xa3,0x44,0x60,0,0x48,0x8b,0x88,0xc8,0x10,0,0};
    if (memcmp(engine+0x127dce,original,14)) return 0;
    unsigned char *gate=make_steering_wait_gate();
    return gate && patch_checked_bytes(engine+0x127dce,original,14,gate);
}

static unsigned char *make_steering_face_gate(void) {
    unsigned char *gate=VirtualAlloc(NULL,160,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
    if (!gate) return NULL;
    size_t used=0;
    gate[used++]=0x9c; gate[used++]=0x50;
    gate[used++]=0x48; gate[used++]=0xb8;
    const volatile void *flag=&controller_steering_active;
    memcpy(gate+used,&flag,8); used+=8;
    gate[used++]=0x80; gate[used++]=0x38; gate[used++]=0;
    gate[used++]=0x58; gate[used++]=0x74; gate[used++]=15;
    gate[used++]=0x9d;
    absolute_jump(gate+used,engine+0x127b92); used+=14; /* skip follower Face allocation/list insert */
    gate[used++]=0x9d;
    /* Original allocator call, using the existing caller's shadow space. */
    gate[used++]=0x48; gate[used++]=0xb8;
    const void *allocator=engine+0x580078;
    memcpy(gate+used,&allocator,8); used+=8;
    gate[used++]=0xff; gate[used++]=0xd0;
    gate[used++]=0x48; gate[used++]=0x85; gate[used++]=0xc0;
    gate[used++]=0x75; gate[used++]=14;
    absolute_jump(gate+used,engine+0x127b83); used+=14;
    static const unsigned char slot_load[4]={0x48,0x8b,0x4d,0x88};
    memcpy(gate+used,slot_load,4); used+=4;
    absolute_jump(gate+used,engine+0x127b59); used+=14;
    DWORD old=0;
    if (!VirtualProtect(gate,160,PAGE_EXECUTE_READ,&old)) {VirtualFree(gate,0,MEM_RELEASE); return NULL;}
    FlushInstructionCache(GetCurrentProcess(),gate,used); return gate;
}
static int install_steering_face_filter(void) {
    static const unsigned char original[14]={0xe8,0x28,0x85,0x45,0,0x48,0x85,0xc0,0x74,0x2e,0x48,0x8b,0x4d,0x88};
    if (memcmp(engine+0x127b4b,original,14)) return 0;
    unsigned char *gate=make_steering_face_gate();
    return gate && patch_checked_bytes(engine+0x127b4b,original,14,gate);
}

static int install_visual_filters(void) {
    /* Both sites are checked in addition to the complete executable hash.
     * The cursor setter is a whole 17-byte leaf with no RIP-relative operands.
     * The marker gate skips ONLY its draw block; actor/order fields are intact.
     */
    static const unsigned char pointer_code[17] = {
        0x44,0x89,0x49,0x04,0xb8,0x01,0x00,0x00,0x00,0x48,0x89,0x91,0x60,0x01,0x00,0x00,0xc3
    };
    static const unsigned char marker_code[16] = {
        0x83,0xbe,0x44,0x49,0x00,0x00,0xff,0x74,0x5a,0x48,0x8b,0x8e,0x50,0x39,0x00,0x00
    };
    if (memcmp(engine + 0x4a7eb0, pointer_code, 17) || memcmp(engine + 0x3e1de2, marker_code, 16)) return 0;
    unsigned char *leaf = VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    unsigned char *gate = VirtualAlloc(NULL, 128, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!leaf || !gate) return 0;
    memcpy(leaf, pointer_code, 17);
    size_t used = 0;
    gate[used++] = 0x50;                       /* push rax */
    gate[used++] = 0x48; gate[used++] = 0xb8;   /* mov rax, flag address */
    void *flag = &cursor_hidden_by_mod;
    memcpy(gate + used, &flag, 8); used += 8;
    gate[used++] = 0x80; gate[used++] = 0x38; gate[used++] = 0; /* cmp byte [rax],0 */
    gate[used++] = 0x58;                       /* pop rax (preserves flags) */
    gate[used++] = 0x74; gate[used++] = 14;     /* hidden==0: original gate */
    absolute_jump(gate + used, engine + 0x3e1e45); used += 14;
    memcpy(gate + used, marker_code, 7); used += 7;
    gate[used++] = 0x75; gate[used++] = 14;     /* destination!=-1: draw */
    absolute_jump(gate + used, engine + 0x3e1e45); used += 14;
    memcpy(gate + used, marker_code + 9, 7); used += 7;
    absolute_jump(gate + used, engine + 0x3e1df2); used += 14;
    DWORD old = 0;
    if (!VirtualProtect(leaf, 64, PAGE_EXECUTE_READ, &old) || !VirtualProtect(gate, 128, PAGE_EXECUTE_READ, &old)) return 0;
    FlushInstructionCache(GetCurrentProcess(), leaf, 64);
    FlushInstructionCache(GetCurrentProcess(), gate, used);
    original_set_video_pointer = (SetVideoPointer)leaf;
    return patch_checked_bytes(engine + 0x4a7eb0, pointer_code, 17, (void *)filtered_video_pointer)
        && patch_checked_bytes(engine + 0x3e1de2, marker_code, 16, gate);
}
static void register_native_on_lua_thread(lua_State *state, const char *name) {
    original_set_global(state, name);
    if (bound_state != state && strcmp(name, "Infinity_GetNumCharacters") == 0) {
        bound_state = state;
        push_closure(state, dispatch, 0);
        original_set_global(state, "PSTPadNative");
        /* Registration happens on the UI thread. Restore the one startup hook
         * immediately; all later game calls keep the original implementation.
         */
        DWORD protection = 0;
        if (VirtualProtect(engine + 0xe4920, sizeof(saved_prologue), PAGE_EXECUTE_READWRITE, &protection)) {
            memcpy(engine + 0xe4920, saved_prologue, sizeof(saved_prologue));
            DWORD ignored;
            VirtualProtect(engine + 0xe4920, sizeof(saved_prologue), protection, &ignored);
            FlushInstructionCache(GetCurrentProcess(), engine + 0xe4920, sizeof(saved_prologue));
        }
    }
}

/* Called once by our launcher before the game's main thread starts. The bridge
 * is registered later by the game's own Lua initialization on its own thread.
 */
__declspec(dllexport) DWORD WINAPI PSTController_Initialize(void *unused) {
    (void)unused;
    if (!initialize_bindings()) return 0;
    if (!install_visual_filters()) return 0;
    if (!install_steering_wait_filter()) return 0;
    if (!install_steering_face_filter()) return 0;
    /* SDL_PollEvent is a seven-byte tail call followed by nine padding bytes.
     * The checked replacement uses the original timeout implementation with
     * timeout zero, and runs on the game's event thread even before Lua/UI. */
    static const unsigned char poll_code[16]={0x33,0xd2,0xe9,0x09,0x04,0,0,0xcc,0xcc,0xcc,0xcc,0xcc,0xcc,0xcc,0xcc,0xcc};
    wait_event_timeout=(WaitEventTimeout)(engine+0x4d0d20);
    if (!patch_checked_bytes(engine+0x4d0910,poll_code,sizeof(poll_code),(void *)poll_with_movie_skip)) return 0;
    static const unsigned char expected_prologue[15] = {
        0x48,0x89,0x5c,0x24,0x08,0x48,0x89,0x74,0x24,0x10,0x57,0x48,0x83,0xec,0x20
    };
    unsigned char *target = engine + 0xe4920;
    if (memcmp(target, expected_prologue, sizeof(expected_prologue)) != 0) return 0;
    unsigned char *trampoline = VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!trampoline) return 0;
    memcpy(saved_prologue, target, sizeof(saved_prologue));
    memcpy(trampoline, target, sizeof(saved_prologue));
    absolute_jump(trampoline + sizeof(saved_prologue), target + sizeof(saved_prologue));
    DWORD old = 0;
    if (!VirtualProtect(trampoline, 64, PAGE_EXECUTE_READ, &old)) {
        VirtualFree(trampoline, 0, MEM_RELEASE);
        return 0;
    }
    FlushInstructionCache(GetCurrentProcess(), trampoline, 64);
    original_set_global = (SetGlobal)trampoline;
    unsigned char replacement[15];
    memset(replacement, 0x90, sizeof(replacement));
    absolute_jump(replacement, (const void *)register_native_on_lua_thread);
    if (!VirtualProtect(target, sizeof(replacement), PAGE_EXECUTE_READWRITE, &old)) return 0;
    memcpy(target, replacement, sizeof(replacement));
    DWORD ignored;
    VirtualProtect(target, sizeof(replacement), old, &ignored);
    FlushInstructionCache(GetCurrentProcess(), target, sizeof(replacement));
    return 1;
}
