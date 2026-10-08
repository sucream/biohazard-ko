/*
 * Biohazard (1997 PC, Japanese, Steam/GOG release) Korean patch - runtime patcher.
 *
 * Loaded as a version.dll proxy. When the game creates its main window (the
 * Enigma protector has finished by then) it patches the unpacked game in
 * memory:
 *   1. room messages are served from Korean text compiled into this DLL,
 *   2. the exe's built-in strings (items, menus, system messages) are
 *      redirected to Korean versions,
 *   3. the text renderers learn code FF (half-width space),
 *   4. font page 1 is split into a static area and a dynamic area. Right
 *      before a message box opens, the glyphs that message needs are written
 *      into the dynamic area and the page is re-uploaded (the same call the
 *      game uses when it swaps font pages between stages).
 */
#include <windows.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <stdarg.h>
#include "ko_strings.h"
#include "ko_rooms.h"
#include "ko_glyphs.h"

void proxy_init(void);

/* game addresses (unpacked Biohazard.exe) */
#define A_UNPACK_PROBE 0x4912c0
#define A_TEX_UPLOAD   0x43f700
#define A_ROOM_MSG     0x4919d7
#define A_MSG_START    0x4919fb
#define A_DESC_START   0x491a9c
#define A_R1_HOOK      0x4913a2
#define A_R3_CMP       0x4923e8
#define A_R3_IDX       0x4923f2
#define A_R3_JT        0x4923f8
#define A_R4_CMP       0x491bc3
#define A_R4_IDX       0x491bd0
#define A_R4_JT        0x491bd6
#define A_R4B_CMP      0x491efc
#define A_R4B_IDX      0x491f05

#define FONT_TPAGE1 0x1f

/* jump-back targets used by the asm stubs */
uint32_t g_R1_ret = 0x4913a9;
uint32_t g_R1_loopchk = 0x491420;
uint32_t g_R3_loopchk = 0x492554;
uint32_t g_msg_ret = A_MSG_START;
uint32_t g_msg_start_ret = 0x491a02;
uint32_t g_desc_ret = 0x491aa1;

/* copies of the dispatch tables, extended for code FF */
uint8_t g_r3_idx[256];
uint32_t g_r3_jt[11];
uint8_t g_r4_idx[256];
uint32_t g_r4_jt[11];
uint8_t g_r4b_idx[256];

void stub_R1(void);
void stub_R3_half(void);
void stub_room_msg(void);
void stub_msg_start(void);
void stub_desc_start(void);

__asm__(
    ".intel_syntax noprefix\n"
    /* item-name renderer: replaces 'mov word ptr [0xc3003c], bp' after the
       F8/F9/FA compare chain. eax = code byte. FF = half-width space. */
    ".globl _stub_R1\n"
    "_stub_R1:\n"
    "  cmp eax, 0xFF\n"
    "  je 1f\n"
    "  mov word ptr ds:[0xc3003c], bp\n"
    "  jmp dword ptr [_g_R1_ret]\n"
    "1:\n"
    "  add word ptr ds:[0xc30034], 7\n"
    "  inc esi\n"
    "  jmp dword ptr [_g_R1_loopchk]\n"

    /* message renderer: FF = half-width space */
    ".globl _stub_R3_half\n"
    "_stub_R3_half:\n"
    "  add word ptr ds:[0xc30034], 7\n"
    "  inc esi\n"
    "  jmp dword ptr [_g_R3_loopchk]\n"

    /* room message lookup (replaces 0x4919d7..0x4919fb); cx = message id */
    ".globl _stub_room_msg\n"
    "_stub_room_msg:\n"
    "  push ecx\n"
    "  movzx eax, cx\n"
    "  and eax, 0x3f\n"
    "  push eax\n"
    "  call _ko_room_msg\n"
    "  add esp, 4\n"
    "  pop ecx\n"
    "  mov dword ptr ds:[0xc3f8ec], eax\n"
    "  jmp dword ptr [_g_msg_ret]\n"

    /* message box start (room and system messages): replaces
       'mov byte ptr [0xc3f8e6], 0' */
    ".globl _stub_msg_start\n"
    "_stub_msg_start:\n"
    "  pushad\n"
    "  push dword ptr ds:[0xc3f8ec]\n"
    "  call _ko_prepare\n"
    "  add esp, 4\n"
    "  popad\n"
    "  mov byte ptr ds:[0xc3f8e6], 0\n"
    "  jmp dword ptr [_g_msg_start_ret]\n"

    /* item description start: replaces 'mov [0xc3f8ec], eax' */
    ".globl _stub_desc_start\n"
    "_stub_desc_start:\n"
    "  mov dword ptr ds:[0xc3f8ec], eax\n"
    "  pushad\n"
    "  push eax\n"
    "  call _ko_prepare\n"
    "  add esp, 4\n"
    "  popad\n"
    "  jmp dword ptr [_g_desc_ret]\n"
    ".att_syntax\n");

static HANDLE g_log;

static void logf(const char *fmt, ...)
{
    char buf[512];
    va_list ap;
    DWORD n;
    if (!g_log)
        return;
    va_start(ap, fmt);
    n = wvsprintfA(buf, fmt, ap);
    va_end(ap);
    WriteFile(g_log, buf, n, &n, NULL);
    WriteFile(g_log, "\r\n", 2, &n, NULL);
}

static int write_mem(uint32_t addr, const void *src, size_t len)
{
    DWORD old;
    if (!VirtualProtect((void *)addr, len, PAGE_EXECUTE_READWRITE, &old))
        return 0;
    memcpy((void *)addr, src, len);
    VirtualProtect((void *)addr, len, old, &old);
    FlushInstructionCache(GetCurrentProcess(), (void *)addr, len);
    return 1;
}

static int expect(uint32_t addr, const char *hex)
{
    const uint8_t *p = (const uint8_t *)addr;
    while (*hex) {
        char t[3] = {hex[0], hex[1], 0};
        if (*p != (uint8_t)strtoul(t, NULL, 16)) {
            logf("unexpected bytes at %08x", (unsigned)(uintptr_t)p);
            return 0;
        }
        p++;
        hex += 2;
    }
    return 1;
}

static void put32(uint32_t addr, uint32_t v) { write_mem(addr, &v, 4); }

static void put_jmp(uint32_t at, void *target, int total_len)
{
    uint8_t b[64];
    int i;
    int32_t rel = (int32_t)((uint32_t)(uintptr_t)target - (at + 5));
    b[0] = 0xE9;
    memcpy(b + 1, &rel, 4);
    for (i = 5; i < total_len; i++)
        b[i] = 0x90;
    write_mem(at, b, total_len);
}

/* ------------------------------------------------------------ messages -- */

/* Korean text for the room the game loaded last (its path is kept in the
   exe's "./jpn/stageN/roomXXXV.rdt" buffer); falls back to the original. */
const uint8_t *__cdecl ko_room_msg(int id)
{
    const char *path = (const char *)0x4acf00;
    const uint8_t *room = *(const uint8_t **)0xc3aba0;
    const uint8_t *txt = *(const uint8_t **)(room + 0x74);
    int i;
    for (i = 0; i < KO_NUM_ROOMS; i++) {
        const ko_room *r = &ko_rooms[i];
        if ((path[17] | 0x20) == (r->key[0] | 0x20) && (path[18] | 0x20) == (r->key[1] | 0x20) &&
            (path[19] | 0x20) == (r->key[2] | 0x20) && (path[20] | 0x20) == (r->key[3] | 0x20)) {
            if ((uint32_t)id < r->count && r->offs[id] != 0xFFFFFFFF)
                return ko_room_blob + r->offs[id];
            break;
        }
    }
    return txt + ((const uint16_t *)txt)[id];
}

/* ---------------------------------------------------- dynamic glyphs -- */
typedef int(__cdecl *upload_fn)(void *buf, int tpage, int clut, int slot);
static upload_fn g_orig_upload;
static uint8_t *g_page;        /* working copy of the page-1 TIM */
static uint32_t g_page_size;
static uint32_t g_page_pix;    /* offset of pixel data in the TIM */
static int g_page_clut, g_page_slot;
static const uint16_t *g_cur_list; /* glyph list currently in the dynamic area */
static int g_uploading;

static uint32_t tim_size(const uint8_t *t, uint32_t *pix)
{
    uint32_t p = 8;
    if (*(const uint32_t *)(t + 4) & 8)
        p += *(const uint32_t *)(t + p);
    *pix = p + 12;
    return p + *(const uint32_t *)(t + p);
}

static void put_glyph(int cell, const uint8_t *g)
{
    int x = (cell % 18) * 14, y = (cell / 18) * 14, r;
    uint8_t *dst = g_page + g_page_pix + y * 128 + x / 2;
    for (r = 0; r < 14; r++)
        memcpy(dst + r * 128, g + r * 7, 7);
}

static const ko_dyn *find_dyn(const ko_dyn *tab, int n, uint32_t off)
{
    int lo = 0, hi = n - 1;
    while (lo <= hi) {
        int mid = (lo + hi) / 2;
        if (tab[mid].off == off)
            return &tab[mid];
        if (tab[mid].off < off)
            lo = mid + 1;
        else
            hi = mid - 1;
    }
    return NULL;
}

void __cdecl ko_prepare(const uint8_t *msg)
{
    const ko_dyn *d = NULL;
    const uint16_t *list = NULL;
    int i;
    if (!g_page)
        return;
    if (msg >= ko_room_blob && msg < ko_room_blob + sizeof ko_room_blob) {
        d = find_dyn(ko_room_dyn, KO_NUM_ROOM_DYN, (uint32_t)(msg - ko_room_blob));
        list = ko_room_dyn_list;
    } else if (msg >= ko_blob && msg < ko_blob + sizeof ko_blob) {
        d = find_dyn(ko_str_dyn, KO_NUM_STR_DYN, (uint32_t)(msg - ko_blob));
        list = ko_str_dyn_list;
    }
    if (!d || !d->count)
        return;
    list += d->start;
    if (list == g_cur_list)
        return;
    for (i = 0; i < d->count; i++)
        put_glyph(i, ko_glyphs[list[i]]);
    g_cur_list = list;
    g_uploading = 1;
    g_orig_upload(g_page, FONT_TPAGE1, g_page_clut, g_page_slot);
    g_uploading = 0;
}

static void flush_strings(void);

static int __cdecl hook_upload(void *buf, int tpage, int clut, int slot)
{
    if ((tpage & 0xffff) == FONT_TPAGE1 && !g_uploading) {
        /* the game (re)loads font page 1: keep a copy to edit later */
        uint32_t pix, size = tim_size(buf, &pix);
        if (g_page && size != g_page_size) {
            HeapFree(GetProcessHeap(), 0, g_page);
            g_page = NULL;
        }
        if (!g_page)
            g_page = HeapAlloc(GetProcessHeap(), 0, size);
        memcpy(g_page, buf, size);
        g_page_size = size;
        g_page_pix = pix;
        g_page_clut = clut;
        g_page_slot = slot;
        g_cur_list = NULL;
        logf("font page 1 captured (%lu bytes, clut %d, slot %d)", size, clut, slot);
    }
    flush_strings();
    return g_orig_upload(buf, tpage, clut, slot);
}

/* ------------------------------------------------------------ patching -- */

static int patch_fonts(void)
{
    uint8_t *tramp;
    if (!expect(A_TEX_UPLOAD, "64a10000000055"))
        return 0;
    tramp = VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    memcpy(tramp, (void *)A_TEX_UPLOAD, 7);
    tramp[7] = 0xE9;
    *(int32_t *)(tramp + 8) = (int32_t)((A_TEX_UPLOAD + 7) - ((uint32_t)(uintptr_t)tramp + 12));
    g_orig_upload = (upload_fn)tramp;
    put_jmp(A_TEX_UPLOAD, (void *)hook_upload, 7);
    return 1;
}

static int patch_text(void)
{
    if (!expect(A_ROOM_MSG, "a1a0abc3008b5074") || !expect(A_MSG_START, "c605e6f8c30000") ||
        !expect(A_DESC_START, "a3ecf8c300"))
        return 0;
    put_jmp(A_ROOM_MSG, (void *)stub_room_msg, A_MSG_START - A_ROOM_MSG);
    put_jmp(A_MSG_START, (void *)stub_msg_start, 7);
    put_jmp(A_DESC_START, (void *)stub_desc_start, 5);

    /* R1: item names */
    if (!expect(A_R1_HOOK, "66892d3c00c300"))
        return 0;
    put_jmp(A_R1_HOOK, (void *)stub_R1, 7);

    /* R3: message window glyphs; idx indexed by code-1 */
    if (!expect(A_R3_CMP, "81f9f9000000") || !expect(A_R3_IDX, "8a919c254900") ||
        !expect(A_R3_JT, "ff249574254900"))
        return 0;
    memcpy(g_r3_idx, (void *)0x49259c, 0xFA);
    memcpy(g_r3_jt, (void *)0x492574, 10 * 4);
    g_r3_jt[10] = (uint32_t)(uintptr_t)stub_R3_half;
    memset(g_r3_idx + 0xFA, 9, 4); /* FB..FE: ordinary glyph */
    g_r3_idx[0xFF - 1] = 10;
    write_mem(A_R3_CMP + 2, "\xfe", 1);
    put32(A_R3_IDX + 2, (uint32_t)(uintptr_t)g_r3_idx);
    put32(A_R3_JT + 3, (uint32_t)(uintptr_t)g_r3_jt);

    /* R4: typewriter state machine; idx indexed by code-1 */
    if (!expect(A_R4_CMP, "3df9000000") || !expect(A_R4_IDX, "8a88e8204900") ||
        !expect(A_R4_JT, "ff248dc0204900"))
        return 0;
    memcpy(g_r4_idx, (void *)0x4920e8, 0xFA);
    memcpy(g_r4_jt, (void *)0x4920c0, 10 * 4);
    g_r4_jt[10] = 0x492060; /* ordinary character */
    memset(g_r4_idx + 0xFA, 10, 5); /* FB..FF */
    write_mem(A_R4_CMP + 1, "\xfe", 1);
    put32(A_R4_IDX + 2, (uint32_t)(uintptr_t)g_r4_idx);
    put32(A_R4_JT + 3, (uint32_t)(uintptr_t)g_r4_jt);

    /* R4b: look-ahead scanner; idx indexed by code-5 */
    if (!expect(A_R4B_CMP, "3df5000000") || !expect(A_R4B_IDX, "8a88f4214900"))
        return 0;
    memcpy(g_r4b_idx, (void *)0x4921f4, 0xF6);
    memset(g_r4b_idx + 0xF6, 3, 5); /* FB..FF: one byte */
    write_mem(A_R4B_CMP + 1, "\xfa", 1);
    put32(A_R4B_IDX + 2, (uint32_t)(uintptr_t)g_r4b_idx);
    return 1;
}

/* String tables are filled in by the protector some time after the code is
   unpacked, so only slots that already hold the original pointer are
   patched; the rest is retried later. */
static uint8_t g_str_done[KO_NUM_REFS + 1];

static void flush_strings(void)
{
    static int done;
    int i, pending = 0;
    if (done)
        return;
    for (i = 0; i < KO_NUM_REFS; i++) {
        uint32_t site = ko_refs[i].site;
        if (g_str_done[i])
            continue;
        if (*(volatile uint32_t *)site != ko_refs[i].orig) {
            pending++;
            continue;
        }
        put32(site, (uint32_t)(uintptr_t)(ko_blob + ko_refs[i].offset));
        g_str_done[i] = 1;
    }
    if (!pending) {
        done = 1;
        logf("strings: %d refs patched", KO_NUM_REFS);
    }
}

static void apply_patches(void)
{
    volatile uint8_t *probe = (volatile uint8_t *)A_UNPACK_PROBE;
    if (!(probe[0] == 0x8A && probe[1] == 0x4C && probe[2] == 0x24 && probe[3] == 0x04)) {
        logf("unexpected executable version - not patching");
        return;
    }
    logf("fonts: %s", patch_fonts() ? "ok" : "FAILED");
    logf("text: %s", patch_text() ? "ok" : "FAILED");
    flush_strings();
}

/* The protector verifies the image and rejects foreign threads during
   start-up, so patching runs on the game's own thread when it creates its
   main window (the protector is finished by then). */
static HHOOK g_cbt;
static int g_patched;

static LRESULT CALLBACK cbt_proc(int code, WPARAM wp, LPARAM lp)
{
    if (code == HCBT_CREATEWND && !g_patched) {
        CBT_CREATEWNDA *cw = (CBT_CREATEWNDA *)lp;
        const char *cls = cw->lpcs->lpszClass;
        if ((uintptr_t)cls > 0xffff && !lstrcmpA(cls, "BIOHAZARD")) {
            g_patched = 1;
            apply_patches();
        }
    }
    return CallNextHookEx(g_cbt, code, wp, lp);
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r)
{
    (void)r;
    if (reason == DLL_PROCESS_ATTACH) {
        char buf[8];
        DisableThreadLibraryCalls(h);
        if (GetEnvironmentVariableA("KOPATCH_LOG", buf, sizeof buf)) {
            g_log = CreateFileA("kopatch.log", GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, 0, NULL);
            if (g_log == INVALID_HANDLE_VALUE)
                g_log = NULL;
        }
        g_cbt = SetWindowsHookExA(WH_CBT, cbt_proc, h, GetCurrentThreadId());
    }
    return TRUE;
}
