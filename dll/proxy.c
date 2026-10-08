/* version.dll proxy: forwards all exports to the system version.dll.
 *
 * The Enigma protector maps version.dll itself without running DllMain, so
 * every stub resolves its target lazily on first call.
 */
#include <windows.h>

#define EXPORTS(X) \
    X(GetFileVersionInfoA) X(GetFileVersionInfoByHandle) X(GetFileVersionInfoExA) \
    X(GetFileVersionInfoExW) X(GetFileVersionInfoSizeA) X(GetFileVersionInfoSizeExA) \
    X(GetFileVersionInfoSizeExW) X(GetFileVersionInfoSizeW) X(GetFileVersionInfoW) \
    X(VerFindFileA) X(VerFindFileW) X(VerInstallFileA) X(VerInstallFileW) \
    X(VerLanguageNameA) X(VerLanguageNameW) X(VerQueryValueA) X(VerQueryValueW)

#define DECL_PTR(n) void *p_##n;
EXPORTS(DECL_PTR)

static const char *const g_names[] = {
#define NAME(n) #n,
    EXPORTS(NAME)
};

void proxy_init(void)
{
    static HMODULE real;
    char path[MAX_PATH];
    void **ptrs[] = {
#define PTR(n) &p_##n,
        EXPORTS(PTR)
    };
    unsigned i;
    if (!real) {
        GetSystemDirectoryA(path, MAX_PATH);
        lstrcatA(path, "\\version.dll");
        real = LoadLibraryA(path);
    }
    for (i = 0; i < sizeof ptrs / sizeof ptrs[0]; i++)
        if (!*ptrs[i])
            *ptrs[i] = (void *)GetProcAddress(real, g_names[i]);
}

/* called from the stubs with all registers saved */
void __cdecl proxy_resolve(void) { proxy_init(); }

#define DEF_STUB(n)                                   \
    __attribute__((naked)) void n##_stub(void)        \
    {                                                 \
        __asm__("cmpl $0, %0\n\t"                     \
                "jne 1f\n\t"                          \
                "pushal\n\t"                          \
                "call _proxy_resolve\n\t"             \
                "popal\n"                             \
                "1:\n\t"                              \
                "jmp *%0" ::"m"(p_##n));              \
    }
EXPORTS(DEF_STUB)
