#ifndef UNICODE
#define UNICODE 1
#endif
#ifndef _UNICODE
#define _UNICODE 1
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <psapi.h>
#include <stdint.h>
#include <wchar.h>
#include <string.h>
#include <stdio.h>

static FILE *log_file;
static void record(const char *message) {
    if (log_file) { fprintf(log_file, "%s\n", message); fflush(log_file); }
}
static uintptr_t mapped_image_base(HANDLE process, const wchar_t *filename) {
    uintptr_t address = 0;
    MEMORY_BASIC_INFORMATION info;
    wchar_t path[32768];
    while (VirtualQueryEx(process, (const void *)address, &info, sizeof(info)) == sizeof(info)) {
        if (info.State == MEM_COMMIT && info.Type == MEM_IMAGE && info.BaseAddress == info.AllocationBase) {
            DWORD length = K32GetMappedFileNameW(process, info.AllocationBase, path, 32768);
            if (length && length < 32768) {
                path[length] = 0;
                wchar_t *name = wcsrchr(path, L'\\');
                if (name && _wcsicmp(name + 1, filename) == 0) return (uintptr_t)info.AllocationBase;
            }
        }
        uintptr_t next = (uintptr_t)info.BaseAddress + info.RegionSize;
        if (next <= address) break;
        address = next;
    }
    return 0;
}
typedef struct {
    uint64_t ldr_load_dll;
    uint16_t length, maximum_length;
    uint32_t padding;
    uint64_t path;
    uint64_t module;
} RemoteLoadBlock;
static int same_copy_running(const wchar_t *executable) {
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snapshot == INVALID_HANDLE_VALUE) return 1;
    PROCESSENTRY32W entry;
    memset(&entry, 0, sizeof(entry));
    entry.dwSize = sizeof(entry);
    int result = 0;
    if (Process32FirstW(snapshot, &entry)) do {
        if (_wcsicmp(entry.szExeFile, L"Torment.exe") != 0) continue;
        HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, entry.th32ProcessID);
        if (!process) continue;
        wchar_t path[32768];
        DWORD size = 32768;
        if (QueryFullProcessImageNameW(process, 0, path, &size) && _wcsicmp(path, executable) == 0) result = 1;
        CloseHandle(process);
    } while (!result && Process32NextW(snapshot, &entry));
    CloseHandle(snapshot);
    return result;
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR command_line, int show) {
    (void)instance; (void)previous; (void)command_line; (void)show;
    wchar_t directory[32768], executable[32768], library[32768], config[32768], log_path[32768];
    DWORD size = GetModuleFileNameW(NULL, directory, 32768);
    if (!size || size >= 32768) return 1;
    wchar_t *separator = wcsrchr(directory, L'\\');
    if (!separator) return 1;
    *separator = 0;
    if (wcslen(directory) > 32000) return 1;
    swprintf(executable, 32768, L"%ls\\Torment.exe", directory);
    swprintf(library, 32768, L"%ls\\override\\pstcontroller.dll", directory);
    swprintf(config, 32768, L"%ls\\engine.lua", directory);
    swprintf(log_path, 32768, L"%ls\\controller-loader.log", directory);
    log_file = _wfopen(log_path, L"w");
    record("Controller Lab startup loader 0.1.0");
    FILE *settings = _wfopen(config, L"rb");
    char config_text[4096] = {0};
    if (!settings) goto invalid_profile;
    fread(config_text, 1, sizeof(config_text) - 1, settings);
    fclose(settings);
    if (!strstr(config_text, "engine_name=\"Planescape Torment - Controller Lab\"")) goto invalid_profile;
    if (same_copy_running(executable)) {
        record("Refused: this working copy is already running");
        MessageBoxW(NULL, L"Close the running Controller Lab game before launching again.", L"Controller Lab", MB_OK);
        if (log_file) fclose(log_file);
        return 1;
    }
    HMODULE local_library = LoadLibraryExW(library, NULL, DONT_RESOLVE_DLL_REFERENCES);
    if (!local_library) goto invalid_plugin;
    FARPROC entry = GetProcAddress(local_library, "PSTController_Initialize");
    if (!entry) { FreeLibrary(local_library); goto invalid_plugin; }
    uintptr_t initialization_offset = (uintptr_t)entry - (uintptr_t)local_library;
    FreeLibrary(local_library);
    STARTUPINFOW startup;
    PROCESS_INFORMATION child;
    memset(&startup, 0, sizeof(startup)); startup.cb = sizeof(startup);
    memset(&child, 0, sizeof(child));
    if (!CreateProcessW(executable, NULL, NULL, NULL, FALSE, CREATE_SUSPENDED, NULL, directory, &startup, &child)) goto invalid_plugin;
    record("Created the working copy suspended");
    SIZE_T bytes = sizeof(RemoteLoadBlock) + (wcslen(library) + 1) * sizeof(wchar_t);
    void *remote_path = VirtualAllocEx(child.hProcess, NULL, bytes, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    void *remote_stub = NULL;
    SIZE_T written = 0;
    HANDLE thread = NULL;
    DWORD initialized = 0;
    if (!remote_path) goto child_failure;
    /* The suspended process has ntdll mapped before its PEB loader list is
     * initialized. Inspect only the child we created, without assuming ASLR
     * bases match our process or requiring KernelBase to be loaded already.
     */
    HMODULE local_ntdll = GetModuleHandleW(L"ntdll.dll");
    FARPROC local_ldr = GetProcAddress(local_ntdll, "LdrLoadDll");
    uintptr_t remote_ntdll = mapped_image_base(child.hProcess, L"ntdll.dll");
    if (!local_ldr || !remote_ntdll) { record("Failed to locate the child's ntdll mapping"); goto child_failure; }
    RemoteLoadBlock block;
    memset(&block, 0, sizeof(block));
    block.ldr_load_dll = remote_ntdll + (uintptr_t)local_ldr - (uintptr_t)local_ntdll;
    block.length = (uint16_t)(wcslen(library) * sizeof(wchar_t));
    block.maximum_length = block.length + sizeof(wchar_t);
    block.path = (uintptr_t)remote_path + sizeof(block);
    if (!WriteProcessMemory(child.hProcess, remote_path, &block, sizeof(block), &written) || written != sizeof(block)) goto child_failure;
    if (!WriteProcessMemory(child.hProcess, (void *)(uintptr_t)block.path, library, block.maximum_length, &written) || written != block.maximum_length) goto child_failure;
    /* Win64 thread entry -> LdrLoadDll(NULL, NULL, &unicode_path, &module).
     * This fixed stub uses only volatile registers and the ABI shadow space.
     */
    static const unsigned char stub[] = {
        0x48,0x83,0xec,0x38, 0x4c,0x8b,0x19,
        0x4c,0x8d,0x49,0x18, 0x4c,0x8d,0x41,0x08,
        0x31,0xd2, 0x31,0xc9, 0x41,0xff,0xd3,
        0x48,0x83,0xc4,0x38, 0xc3
    };
    remote_stub = VirtualAllocEx(child.hProcess, NULL, sizeof(stub), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    DWORD old_protection = 0;
    if (!remote_stub || !WriteProcessMemory(child.hProcess, remote_stub, stub, sizeof(stub), &written) || written != sizeof(stub)) goto child_failure;
    if (!VirtualProtectEx(child.hProcess, remote_stub, sizeof(stub), PAGE_EXECUTE_READ, &old_protection)) goto child_failure;
    FlushInstructionCache(child.hProcess, remote_stub, sizeof(stub));
    record("Resolved native loader in the suspended child's mapped image");
    thread = CreateRemoteThread(child.hProcess, NULL, 0, (LPTHREAD_START_ROUTINE)remote_stub, remote_path, 0, NULL);
    if (!thread || WaitForSingleObject(thread, 10000) != WAIT_OBJECT_0) goto child_failure;
    DWORD load_status = 0;
    if (!GetExitCodeThread(thread, &load_status) || load_status != 0) { record("LdrLoadDll returned a failure status"); goto child_failure; }
    CloseHandle(thread); thread = NULL;
    SIZE_T read = 0;
    if (!ReadProcessMemory(child.hProcess, remote_path, &block, sizeof(block), &read) || read != sizeof(block)) goto child_failure;
    VirtualFreeEx(child.hProcess, remote_path, 0, MEM_RELEASE); remote_path = NULL;
    VirtualFreeEx(child.hProcess, remote_stub, 0, MEM_RELEASE); remote_stub = NULL;
    uintptr_t remote_library = (uintptr_t)block.module;
    if (!remote_library) goto child_failure;
    record("Loaded native bridge in the working copy");
    thread = CreateRemoteThread(child.hProcess, NULL, 0, (LPTHREAD_START_ROUTINE)(remote_library + initialization_offset), NULL, 0, NULL);
    if (!thread || WaitForSingleObject(thread, 10000) != WAIT_OBJECT_0 || !GetExitCodeThread(thread, &initialized) || initialized != 1) goto child_failure;
    CloseHandle(thread); thread = NULL;
    record("Executable fingerprint and Lua startup hook verified");
    if (ResumeThread(child.hThread) == (DWORD)-1) goto child_failure;
    record("Game resumed; native Lua registration will run on the game thread");
    CloseHandle(child.hThread); CloseHandle(child.hProcess);
    if (log_file) fclose(log_file);
    return 0;
child_failure:
    record("Startup failed; stopped only the suspended child created by this loader");
    if (thread) CloseHandle(thread);
    TerminateProcess(child.hProcess, 1);
    WaitForSingleObject(child.hProcess, 2000);
    CloseHandle(child.hThread); CloseHandle(child.hProcess);
invalid_plugin:
    MessageBoxW(NULL, L"Controller Lab could not initialize its native bridge. See controller-loader.log. Only PST:EE 3.2.2.0 with the verified executable is supported.", L"Controller Lab", MB_OK | MB_ICONERROR);
    if (log_file) fclose(log_file);
    return 1;
invalid_profile:
    record("Refused: the isolated Controller Lab profile is missing");
    MessageBoxW(NULL, L"This prototype must run in the copied game with its Controller Lab profile.", L"Controller Lab", MB_OK | MB_ICONERROR);
    if (log_file) fclose(log_file);
    return 1;
}
