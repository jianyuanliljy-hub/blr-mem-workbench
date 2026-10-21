/* Small Unicode launcher. All scientific code runs in the shared portable runtime. */
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <wchar.h>
#include <stdio.h>

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR arguments, int show) {
    wchar_t directory[32768], python[32768], command[32768];
    DWORD length = GetModuleFileNameW(NULL, directory, 32768);
    if (!length || length >= 32768) return 1;
    wchar_t *last = wcsrchr(directory, L'\\');
    if (!last) return 1;
    *last = L'\0';
    if (swprintf(python, 32768, L"%ls\\_runtime\\pythonw.exe", directory) < 0 ||
        swprintf(command, 32768, L"\"%ls\" -I -B -X utf8 \"%ls\\launch.pyw\" %ls",
                 python, directory, arguments) < 0) return 1;
    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION process = {0};
    startup.cb = sizeof(startup);
    if (!CreateProcessW(python, command, NULL, NULL, FALSE,
                        CREATE_UNICODE_ENVIRONMENT | CREATE_NO_WINDOW, NULL, directory, &startup, &process)) {
        MessageBoxW(NULL, L"The program could not start. Extract the complete ZIP first.\n"
                          L"See START_HERE.txt, or run Diagnose.cmd for details.",
                    L"BLR MEM Workbench", MB_OK | MB_ICONERROR);
        return 1;
    }
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD code = 1;
    GetExitCodeProcess(process.hProcess, &code);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return (int)code;
}
