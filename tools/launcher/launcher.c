#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <shlwapi.h>

#pragma comment(lib, "shlwapi.lib")

static void show_error(const char *msg) {
    MessageBoxA(NULL, msg, "ok-ww launcher", MB_ICONERROR | MB_OK);
}

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, LPSTR lpCmdLine, int nCmdShow) {
    char exePath[MAX_PATH];
    DWORD len = GetModuleFileNameA(NULL, exePath, MAX_PATH);
    if (len == 0 || len >= MAX_PATH) {
        show_error("Cannot determine launcher path.");
        return 1;
    }
    PathRemoveFileSpecA(exePath);

    char pythonPath[MAX_PATH], scriptPath[MAX_PATH], workingDir[MAX_PATH];
    if (_snprintf_s(pythonPath, MAX_PATH, _TRUNCATE, "%s\\data\\apps\\ok-ww\\python\\pythonw.exe", exePath) < 0 ||
        _snprintf_s(scriptPath, MAX_PATH, _TRUNCATE, "%s\\data\\apps\\ok-ww\\working\\main.py", exePath) < 0 ||
        _snprintf_s(workingDir, MAX_PATH, _TRUNCATE, "%s\\data\\apps\\ok-ww\\working", exePath) < 0) {
        show_error("Path too long.");
        return 1;
    }

    if (GetFileAttributesA(pythonPath) == INVALID_FILE_ATTRIBUTES) {
        show_error("Cannot find pythonw.exe.\nDid you extract the whole archive?");
        return 1;
    }
    if (GetFileAttributesA(scriptPath) == INVALID_FILE_ATTRIBUTES) {
        show_error("Cannot find main.py.\nDid you extract the whole archive?");
        return 1;
    }

    SetEnvironmentVariableA("PYTHONNOUSERSITE", "1");
    SetEnvironmentVariableA("PYTHONIOENCODING", "utf-8");
    SetEnvironmentVariableA("PYTHONUNBUFFERED", "1");
    SetEnvironmentVariableA("PYTHONPATH", "");
    SetEnvironmentVariableA("PYTHONHOME", "");
    SetEnvironmentVariableA("VIRTUAL_ENV", "");

    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    char cmdLine[MAX_PATH * 2];
    _snprintf_s(cmdLine, sizeof(cmdLine), _TRUNCATE, "\"%s\" \"%s\"", pythonPath, scriptPath);

    if (!CreateProcessA(pythonPath, cmdLine, NULL, NULL, FALSE, 0, NULL, workingDir, &si, &pi)) {
        char err[512];
        _snprintf_s(err, sizeof(err), _TRUNCATE, "Failed to start Python (error %lu).", GetLastError());
        show_error(err);
        return 1;
    }

    CloseHandle(pi.hThread);
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 0;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hProcess);
    return (int)code;
}
