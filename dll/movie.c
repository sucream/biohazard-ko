/*
 * Korean subtitles for the movies.
 *
 * The game plays its AVI movies through MCI ("avivideo"): MCIAVI decodes
 * the frames on its own thread with DrawDibDraw. The game's display wrapper
 * (ddraw.dll) shows them on its Direct3D screen by watching DrawDib's
 * decompression buffer; anything drawn into the movie window itself never
 * reaches the screen.
 *
 * The Japanese movies PJ/ED4/ED5 have Japanese subtitles burned in; the
 * installer links them to the subtitle-free North American movies, and this
 * file draws Korean subtitles over the picture:
 *   - mciSendCommandA (the game's import slot) tells which movie starts
 *     playing and from which frame,
 *   - DrawDibDraw is hooked: while a subtitle is shown the frame is only
 *     decompressed (DDF_DONTDRAW), the subtitle is drawn into DrawDib's
 *     buffer (DrawDibGetBuffer, 320x240) and the buffer shown (DDF_UPDATE).
 *     Later frames are decoded as differences to the previous one, so the
 *     clean frame is put back into the buffer before the next decode.
 * If the Korean folder still holds the Japanese movie (the North American
 * one was missing at install time), the Japanese subtitle area is blacked
 * out under the Korean text.
 */
#include <windows.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "ko_movies.h"

typedef void (*log_fn)(const char *fmt, ...);
static log_fn g_log;
#define LOG(...) (g_log ? g_log(__VA_ARGS__) : (void)0)

#define A_IAT_MCISEND 0xd72588 /* game's import slot for winmm!mciSendCommandA */
#define A_MOVIE_PATH  0x6a60b0 /* path of the movie being played */

#define DDF_UPDATE_    0x2
#define DDF_DONTDRAW_  0x10
#define FRAME_MS 100   /* all movies are 10 fps */
#define COVER_MARGIN 5 /* frames blacked out around a subtitle (Japanese movie) */

typedef MCIERROR(WINAPI *mci_fn)(MCIDEVICEID, UINT, DWORD_PTR, DWORD_PTR);
typedef BOOL(WINAPI *ddd_fn)(HANDLE, HDC, int, int, int, int, LPBITMAPINFOHEADER, LPVOID, int, int, int, int, UINT);
typedef void *(WINAPI *getbuf_fn)(HANDLE, LPBITMAPINFOHEADER, DWORD, DWORD);
static mci_fn g_mci;
static ddd_fn g_ddd;
static getbuf_fn g_getbuf;

/* playback state, set on the game thread, read on the MCIAVI thread */
static volatile int g_movie = -1; /* index into ko_movies, -1: no subtitles */
static volatile int g_cover;      /* Japanese movie: hide its subtitles */
static volatile LONG g_from;      /* first frame played */
static volatile DWORD g_t0;       /* tick of the first frame drawn, 0: not yet */

/* MCIAVI thread only */
typedef struct { BITMAPINFOHEADER h; RGBQUAD pal[256]; } dib_fmt;
static HDC g_mdc;                  /* drawing surface: copy of the frame */
static HBITMAP g_bmp, g_oldbmp;
static HFONT g_font, g_oldfont;
static int g_w, g_h;
static uint8_t *g_tmp, *g_save;    /* frame in the buffer's format; clean copy */
static DWORD g_size;
static HANDLE g_dirty_hdd;         /* DrawDib whose buffer holds a subtitle */
static void *g_dirty_buf;

static void *hook_fn(void *fn, void *hook)
{
    uint8_t *p = fn, *tr;
    DWORD old;
    int32_t rel;
    /* standard hot-patchable prologue: mov edi,edi / push ebp / mov ebp,esp */
    if (!p || !(p[0] == 0x8B && p[1] == 0xFF && p[2] == 0x55 && p[3] == 0x8B && p[4] == 0xEC)) {
        LOG("movie: unexpected DrawDibDraw prologue");
        return NULL;
    }
    tr = VirtualAlloc(NULL, 16, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!tr)
        return NULL;
    memcpy(tr, p, 5);
    tr[5] = 0xE9;
    rel = (int32_t)((p + 5) - (tr + 10));
    memcpy(tr + 6, &rel, 4);
    if (!VirtualProtect(p, 5, PAGE_EXECUTE_READWRITE, &old))
        return NULL;
    p[0] = 0xE9;
    rel = (int32_t)((uint8_t *)hook - (p + 5));
    memcpy(p + 1, &rel, 4);
    VirtualProtect(p, 5, old, &old);
    FlushInstructionCache(GetCurrentProcess(), p, 5);
    return tr;
}

/* subtitle of the frame on screen; *cover: the Japanese subtitle area must
   be hidden */
static const wchar_t *current_sub(int *cover)
{
    int f, i;
    *cover = 0;
    if (!g_t0)
        return NULL;
    f = g_from + (int)((GetTickCount() - g_t0 + FRAME_MS / 2) / FRAME_MS);
    for (i = 0; i < (int)KO_NUM_SUBS; i++) {
        if (ko_subs[i].movie != g_movie)
            continue;
        if (g_cover && f >= ko_subs[i].start - COVER_MARGIN && f < ko_subs[i].end + COVER_MARGIN)
            *cover = 1;
        if (f >= ko_subs[i].start && f < ko_subs[i].end)
            return ko_subs[i].text;
    }
    return NULL;
}

/* put the clean frame back into the buffer of hdd if a subtitle was drawn
   into it */
static void restore(HANDLE hdd)
{
    dib_fmt fmt;
    if (!g_dirty_buf)
        return;
    if (hdd == g_dirty_hdd && g_getbuf(hdd, &fmt.h, sizeof fmt, 0) == g_dirty_buf)
        memcpy(g_dirty_buf, g_save, g_size);
    g_dirty_buf = NULL; /* a different DrawDib: the old buffer is gone */
}

static int prepare(const BITMAPINFOHEADER *bh)
{
    BITMAPINFOHEADER dh = {sizeof dh, bh->biWidth, labs(bh->biHeight), 1, 32};
    DWORD size = ((bh->biWidth * bh->biBitCount + 31) / 32) * 4 * labs(bh->biHeight);
    void *px;
    if (g_mdc && bh->biWidth == g_w && labs(bh->biHeight) == g_h && size == g_size)
        return 1;
    if (g_mdc) {
        SelectObject(g_mdc, g_oldbmp);
        SelectObject(g_mdc, g_oldfont);
        DeleteObject(g_bmp);
        DeleteObject(g_font);
        DeleteDC(g_mdc);
        HeapFree(GetProcessHeap(), 0, g_tmp);
        HeapFree(GetProcessHeap(), 0, g_save);
        g_mdc = NULL;
    }
    g_mdc = CreateCompatibleDC(NULL);
    g_bmp = CreateDIBSection(NULL, (BITMAPINFO *)&dh, DIB_RGB_COLORS, &px, NULL, 0);
    g_tmp = HeapAlloc(GetProcessHeap(), 0, size);
    g_save = HeapAlloc(GetProcessHeap(), 0, size);
    if (!g_mdc || !g_bmp || !g_tmp || !g_save) {
        if (g_mdc)
            DeleteDC(g_mdc);
        if (g_bmp)
            DeleteObject(g_bmp);
        HeapFree(GetProcessHeap(), 0, g_tmp);
        HeapFree(GetProcessHeap(), 0, g_save);
        g_mdc = NULL;
        return 0;
    }
    g_w = dh.biWidth;
    g_h = dh.biHeight;
    g_size = size;
    g_font = CreateFontW(-(g_h * 6 / 100), 0, 0, 0, FW_BOLD, 0, 0, 0, HANGUL_CHARSET, OUT_TT_PRECIS,
                         CLIP_DEFAULT_PRECIS, ANTIALIASED_QUALITY, DEFAULT_PITCH, L"Malgun Gothic");
    g_oldbmp = SelectObject(g_mdc, g_bmp);
    g_oldfont = SelectObject(g_mdc, g_font);
    SetBkMode(g_mdc, TRANSPARENT);
    return 1;
}

/* subtitle block anchored to the bottom like the Japanese ones (which end
   at line 232 of 240), white with a black outline */
static void draw_sub(const wchar_t *text, int cover, int w, int h)
{
    RECT r = {0, 0, w, h}, t;
    int o = h / 240, dx, dy, th;
    if (cover) {
        RECT c = {0, h * 186 / 240, w, h * 238 / 240};
        FillRect(g_mdc, &c, GetStockObject(BLACK_BRUSH));
    }
    if (!text)
        return;
    DrawTextW(g_mdc, text, -1, &r, DT_CENTER | DT_CALCRECT | DT_NOPREFIX);
    th = r.bottom - r.top;
    r.left = 0;
    r.right = w;
    r.bottom = h * 232 / 240;
    r.top = r.bottom - th;
    SetTextColor(g_mdc, RGB(0, 0, 0));
    for (dy = -o; dy <= o; dy++)
        for (dx = -o; dx <= o; dx++) {
            if (!dx && !dy)
                continue;
            t = r;
            OffsetRect(&t, dx, dy);
            DrawTextW(g_mdc, text, -1, &t, DT_CENTER | DT_NOPREFIX);
        }
    SetTextColor(g_mdc, RGB(255, 255, 255));
    DrawTextW(g_mdc, text, -1, &r, DT_CENTER | DT_NOPREFIX);
}

#ifdef MOVIE_TEST
/* test builds: save each frame whose subtitle changed as a .bmp in the game
   folder */
static void dump_frame(const wchar_t *sub)
{
    static const wchar_t *last;
    static int n;
    BITMAPINFOHEADER bh = {sizeof bh, g_w, g_h, 1, 24};
    BITMAPFILEHEADER fh = {0x4d42};
    int stride = (g_w * 3 + 3) & ~3;
    void *px;
    char name[32];
    HANDLE f;
    DWORD wr;
    if (sub == last)
        return;
    last = sub;
    px = HeapAlloc(GetProcessHeap(), 0, stride * g_h);
    GetDIBits(g_mdc, g_bmp, 0, g_h, px, (BITMAPINFO *)&bh, DIB_RGB_COLORS);
    fh.bfOffBits = sizeof fh + sizeof bh;
    fh.bfSize = fh.bfOffBits + stride * g_h;
    wsprintfA(name, "movtest_%02d.bmp", n++);
    f = CreateFileA(name, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, NULL);
    WriteFile(f, &fh, sizeof fh, &wr, NULL);
    WriteFile(f, &bh, sizeof bh, &wr, NULL);
    WriteFile(f, px, stride * g_h, &wr, NULL);
    CloseHandle(f);
    HeapFree(GetProcessHeap(), 0, px);
}
#endif

static BOOL WINAPI my_ddd(HANDLE hdd, HDC hdc, int xd, int yd, int dxd, int dyd, LPBITMAPINFOHEADER bi, LPVOID bits,
                          int xs, int ys, int dxs, int dys, UINT fl)
{
    dib_fmt fmt;
    const wchar_t *sub;
    uint8_t *buf;
    int cover;
    BOOL r;
    if (!(fl & DDF_UPDATE_))
        restore(hdd); /* about to decode the next frame */
    if (g_movie < 0 || (fl & DDF_DONTDRAW_) || !g_getbuf)
        return g_ddd(hdd, hdc, xd, yd, dxd, dyd, bi, bits, xs, ys, dxs, dys, fl);
    if (bits && !(fl & DDF_UPDATE_) && !g_t0)
        g_t0 = GetTickCount();
    sub = current_sub(&cover);
    if (!sub && !cover)
        return g_ddd(hdd, hdc, xd, yd, dxd, dyd, bi, bits, xs, ys, dxs, dys, fl);
    if (fl & DDF_UPDATE_) /* redraw: the buffer still holds the subtitle */
        return g_ddd(hdd, hdc, xd, yd, dxd, dyd, bi, bits, xs, ys, dxs, dys, fl);

    r = g_ddd(hdd, hdc, xd, yd, dxd, dyd, bi, bits, xs, ys, dxs, dys, fl | DDF_DONTDRAW_);
    memset(&fmt, 0, sizeof fmt);
    buf = g_getbuf(hdd, &fmt.h, sizeof fmt, 0);
    if (buf && fmt.h.biCompression == BI_RGB && fmt.h.biBitCount >= 16 && prepare(&fmt.h)) {
        memcpy(g_save, buf, g_size);
        SetDIBitsToDevice(g_mdc, 0, 0, g_w, g_h, 0, 0, 0, g_h, buf, (BITMAPINFO *)&fmt, DIB_RGB_COLORS);
        draw_sub(sub, cover, g_w, g_h);
        GdiFlush();
        if (GetDIBits(g_mdc, g_bmp, 0, g_h, g_tmp, (BITMAPINFO *)&fmt, DIB_RGB_COLORS) == g_h) {
            memcpy(buf, g_tmp, g_size); /* written from user mode, which the wrapper notices */
            g_dirty_hdd = hdd;
            g_dirty_buf = buf;
        }
#ifdef MOVIE_TEST
        dump_frame(sub);
#endif
    }
    g_ddd(hdd, hdc, xd, yd, dxd, dyd, bi, NULL, xs, ys, dxs, dys, fl | DDF_UPDATE_);
    return r;
}

static int movie_index(const char *path)
{
    const char *base = path, *p;
    int i, n;
    for (p = path; *p; p++)
        if (*p == '\\' || *p == '/')
            base = p + 1;
#ifdef MOVIE_TEST
    /* test builds: the title movie (played on start-up) stands in for MOVIE_TEST */
    if (!lstrcmpiA(base, "OJ.avi"))
        base = MOVIE_TEST;
#endif
    for (i = 0; i < KO_NUM_MOVIES; i++) {
        n = lstrlenA(ko_movies[i].name);
        if (CompareStringA(LOCALE_INVARIANT, NORM_IGNORECASE, base, n, ko_movies[i].name, n) == CSTR_EQUAL &&
            base[n] == '.')
            return i;
    }
    return -1;
}

static void hook_drawdib(void)
{
    HMODULE m;
    /* MCIAVI unloads msvfw32 when the last movie is closed: pin it so the
       hook stays in place for the next movie */
    if (g_ddd || !GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_PIN, "msvfw32.dll", &m))
        return;
    g_getbuf = (getbuf_fn)GetProcAddress(m, "DrawDibGetBuffer");
    g_ddd = hook_fn(GetProcAddress(m, "DrawDibDraw"), my_ddd);
    LOG("movie: DrawDibDraw hook %s", g_ddd ? "ok" : "FAILED");
}

static MCIERROR WINAPI my_mci(MCIDEVICEID id, UINT msg, DWORD_PTR flags, DWORD_PTR param)
{
    MCIERROR r;
    if (msg == MCI_PLAY) {
        /* set up before playing: MCIAVI starts drawing right away */
        const char *path = (const char *)A_MOVIE_PATH;
        int m = g_ddd ? movie_index(path) : -1;
        g_movie = -1;
        if (m >= 0) {
            WIN32_FILE_ATTRIBUTE_DATA fa;
            g_cover = !GetFileAttributesExA(path, GetFileExInfoStandard, &fa) ||
                      fa.nFileSizeLow != ko_movies[m].us_size;
            g_from = (flags & MCI_FROM) && param ? (LONG)((MCI_PLAY_PARMS *)param)->dwFrom : 0;
            g_t0 = 0;
            g_movie = m;
            LOG("movie: %s from %ld%s", path, g_from, g_cover ? " (Japanese movie)" : "");
        }
    } else if (msg == MCI_CLOSE) {
        g_movie = -1;
    }
    r = g_mci(id, msg, flags, param);
    if (msg == MCI_OPEN && !r)
        hook_drawdib(); /* msvfw32 is loaded by MCIAVI */
    return r;
}

int ko_movie_init(log_fn log)
{
    void **slot = (void **)A_IAT_MCISEND;
    DWORD old;
    g_log = log;
    if (*slot != (void *)GetProcAddress(LoadLibraryA("winmm.dll"), "mciSendCommandA"))
        return 0;
    g_mci = (mci_fn)*slot;
    if (!VirtualProtect(slot, 4, PAGE_READWRITE, &old))
        return 0;
    *slot = (void *)my_mci;
    VirtualProtect(slot, 4, old, &old);
    return 1;
}
