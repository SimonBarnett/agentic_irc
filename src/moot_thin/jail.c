#include "jail.h"
#include "task_ui.h"

static int powershell_present(void)
{
    char sys[MAX_PATH], path[MAX_PATH];
    UINT n = GetSystemDirectoryA(sys, MAX_PATH);
    if (n == 0 || n >= MAX_PATH)
        return 0;
    _snprintf(path, MAX_PATH, "%s\\WindowsPowerShell\\v1.0\\powershell.exe", sys);
    return GetFileAttributesA(path) != INVALID_FILE_ATTRIBUTES;
}

static void add_bin(Jail *j, const char *name)
{
    int i;
    if (!name || !name[0] || j->nbin >= JAIL_BIN_MAX)
        return;
    for (i = 0; i < j->nbin; i++) {
        if (str_ieq(j->bins[i], name))
            return;
    }
    strncpy(j->bins[j->nbin], name, sizeof(j->bins[0]) - 1);
    j->nbin++;
}

void jail_init(Jail *j, const char *allow_path, const char *extra_bins)
{
    memset(j, 0, sizeof(*j));
    strncpy(j->root, allow_path ? allow_path : ".", sizeof(j->root) - 1);
    mkdir_p(j->root);
    add_bin(j, "cmd.exe");
    add_bin(j, "hostname.exe");
    add_bin(j, "ipconfig.exe");
    add_bin(j, "whoami.exe");
    add_bin(j, "hostname");
    add_bin(j, "ipconfig");
    add_bin(j, "whoami");
    if (powershell_present()) {
        add_bin(j, "powershell.exe");
        add_bin(j, "powershell");
    }
    if (extra_bins && extra_bins[0]) {
        char buf[256];
        char *tok;
        strncpy(buf, extra_bins, sizeof(buf) - 1);
        buf[sizeof(buf) - 1] = 0;
        tok = strtok(buf, ",");
        while (tok) {
            while (*tok == ' ')
                tok++;
            add_bin(j, tok);
            tok = strtok(NULL, ",");
        }
    }
}

static void strip_slash(char *p)
{
    int n = (int)strlen(p);
    while (n > 3 && (p[n - 1] == '\\' || p[n - 1] == '/')) {
        p[n - 1] = 0;
        n--;
    }
}

int jail_in(const Jail *j, const char *target)
{
    char r[MAX_PATH], t[MAX_PATH];
    size_t n;
    if (!target || !target[0])
        return 0;
    if ((target[0] == '\\' && target[1] == '\\') || (target[0] == '/' && target[1] == '/'))
        return 0;
    if (GetFullPathNameA(j->root, MAX_PATH, r, NULL) == 0)
        return 0;
    if (GetFullPathNameA(target, MAX_PATH, t, NULL) == 0)
        return 0;
    if ((t[0] == '\\' && t[1] == '\\') || (t[0] == '/' && t[1] == '/'))
        return 0;
    strip_slash(r);
    strip_slash(t);
    if (str_ieq(r, t))
        return 1;
    n = strlen(r);
    if (_strnicmp(r, t, (int)n) == 0 && (t[n] == '\\' || t[n] == '/'))
        return 1;
    return 0;
}

int jail_bin_ok(const Jail *j, const char *argv0)
{
    const char *b;
    int i;
    if (!argv0 || !argv0[0])
        return 0;
    b = path_basename(argv0);
    for (i = 0; i < j->nbin; i++) {
        if (str_ieq(j->bins[i], b))
            return 1;
    }
    return 0;
}

int jail_meta_ok(const char *joined)
{
    const char *p;
    for (p = joined; *p; p++) {
        if (*p == '&' || *p == '|' || *p == '>' || *p == '<' || *p == '^')
            return 0;
    }
    return 1;
}

int jail_apply_trunc(const char *home, const char *jid, char *out, char *err, int *truncated)
{
    int lo = (int)strlen(out);
    int le = (int)strlen(err);
    *truncated = 0;
    if (lo + le <= RESULT_BYTES_MAX)
        return 0;
    *truncated = 1;
    if (home && jid && jid[0]) {
        char dir[MAX_PATH], path[MAX_PATH], body[RESULT_BYTES_MAX * 2 + 64];
        _snprintf(dir, MAX_PATH, "%s\\dumb\\results", home);
        mkdir_p(dir);
        _snprintf(path, MAX_PATH, "%s\\%s.txt", dir, jid);
        _snprintf(body, sizeof(body), "--- stdout ---\n%s\n--- stderr ---\n%s\n", out, err);
        write_file(path, (uint8_t *)body, (int)strlen(body));
    }
    if (lo > 4000)
        out[4000] = 0;
    if (le > 4000)
        err[4000] = 0;
    return 0;
}

static void quote_arg(const char *a, char *out, int cap)
{
    int need = 0;
    const char *p;
    for (p = a; *p; p++) {
        if (*p == ' ' || *p == '\t' || *p == '"')
            need = 1;
    }
    if (!need) {
        strncpy(out, a, cap - 1);
        out[cap - 1] = 0;
        return;
    }
    {
        int o = 0;
        if (o + 1 < cap)
            out[o++] = '"';
        for (p = a; *p && o + 2 < cap; p++) {
            if (*p == '"') {
                out[o++] = '\\';
                out[o++] = '"';
            } else
                out[o++] = *p;
        }
        if (o + 1 < cap)
            out[o++] = '"';
        out[o] = 0;
    }
}

int jail_exec(Jail *j, char **argv, int argc, const char *cwd, int timeout_s,
              char *out, int outcap, char *err, int errcap, int *rc)
{
    char cmdline[1024];
    char cwd_full[MAX_PATH];
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    SECURITY_ATTRIBUTES sa;
    HANDLE or_ = NULL, ow = NULL, er_ = NULL, ew = NULL;
    DWORD wait;
    DWORD code = 1;
    int i, o = 0;
    DWORD t0;

    out[0] = 0;
    err[0] = 0;
    *rc = 1;
    if (j->busy)
        return JAIL_EXEC_BUSY;
    if (argc < 1)
        return JAIL_EXEC_EMPTY;
    if (!jail_bin_ok(j, argv[0]))
        return JAIL_EXEC_BIN;
    cmdline[0] = 0;
    for (i = 0; i < argc; i++) {
        char q[256];
        quote_arg(argv[i], q, sizeof(q));
        if (i) {
            if ((int)strlen(cmdline) + 2 >= (int)sizeof(cmdline))
                return JAIL_EXEC_BIN;
            strcat(cmdline, " ");
        }
        if ((int)strlen(cmdline) + (int)strlen(q) >= (int)sizeof(cmdline))
            return JAIL_EXEC_BIN;
        strcat(cmdline, q);
    }
    if (strstr(cmdline, "..") || strstr(cmdline, "\\\\") || strstr(cmdline, "//"))
        return JAIL_EXEC_JAIL;
    if (!jail_meta_ok(cmdline))
        return JAIL_EXEC_META;
    if (!cwd || !cwd[0])
        cwd = j->root;
    if ((cwd[0] == '\\' && cwd[1] == '\\') || (cwd[0] == '/' && cwd[1] == '/'))
        return JAIL_EXEC_JAIL;
    if (!jail_in(j, cwd))
        return JAIL_EXEC_JAIL;
    GetFullPathNameA(cwd, MAX_PATH, cwd_full, NULL);
    if (timeout_s < 1)
        timeout_s = 1;
    if (timeout_s > 60)
        timeout_s = 60;

    j->busy = 1;
    sa.nLength = sizeof(sa);
    sa.lpSecurityDescriptor = NULL;
    sa.bInheritHandle = TRUE;
    if (!CreatePipe(&or_, &ow, &sa, 0) || !CreatePipe(&er_, &ew, &sa, 0)) {
        j->busy = 0;
        return JAIL_EXEC_FAIL;
    }
    SetHandleInformation(or_, HANDLE_FLAG_INHERIT, 0);
    SetHandleInformation(er_, HANDLE_FLAG_INHERIT, 0);
    memset(&si, 0, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
    si.hStdOutput = ow;
    si.hStdError = ew;
    memset(&pi, 0, sizeof(pi));
    if (!CreateProcessA(NULL, cmdline, NULL, NULL, TRUE, CREATE_NO_WINDOW, NULL, cwd_full, &si, &pi)) {
        CloseHandle(or_);
        CloseHandle(ow);
        CloseHandle(er_);
        CloseHandle(ew);
        j->busy = 0;
        return JAIL_EXEC_FAIL;
    }
    CloseHandle(ow);
    CloseHandle(ew);
    t0 = GetTickCount();
    for (;;) {
        DWORD n;
        char tmp[512];
        wait = WaitForSingleObject(pi.hProcess, 50);
        if (PeekNamedPipe(or_, NULL, 0, NULL, &n, NULL) && n) {
            DWORD g = 0;
            if (n > sizeof(tmp))
                n = sizeof(tmp);
            if (ReadFile(or_, tmp, n, &g, NULL) && g) {
                int ol = (int)strlen(out);
                int room = outcap - 1 - ol;
                if (room > 0) {
                    if ((int)g > room)
                        g = (DWORD)room;
                    memcpy(out + ol, tmp, g);
                    out[ol + (int)g] = 0;
                }
            }
        }
        if (PeekNamedPipe(er_, NULL, 0, NULL, &n, NULL) && n) {
            DWORD g = 0;
            if (n > sizeof(tmp))
                n = sizeof(tmp);
            if (ReadFile(er_, tmp, n, &g, NULL) && g) {
                int ol = (int)strlen(err);
                int room = errcap - 1 - ol;
                if (room > 0) {
                    if ((int)g > room)
                        g = (DWORD)room;
                    memcpy(err + ol, tmp, g);
                    err[ol + (int)g] = 0;
                }
            }
        }
        task_ui_spin_tick();
        if (wait == WAIT_OBJECT_0)
            break;
        if ((int)(GetTickCount() - t0) / 1000 >= timeout_s) {
            TerminateProcess(pi.hProcess, 1);
            CloseHandle(or_);
            CloseHandle(er_);
            CloseHandle(pi.hThread);
            CloseHandle(pi.hProcess);
            j->busy = 0;
            return JAIL_EXEC_TIMEOUT;
        }
        (void)o;
    }
    GetExitCodeProcess(pi.hProcess, &code);
    /* drain */
    for (;;) {
        DWORD g = 0;
        char tmp[512];
        if (!ReadFile(or_, tmp, sizeof(tmp), &g, NULL) || g == 0)
            break;
        {
            int ol = (int)strlen(out);
            int room = outcap - 1 - ol;
            if (room > 0) {
                if ((int)g > room)
                    g = (DWORD)room;
                memcpy(out + ol, tmp, g);
                out[ol + (int)g] = 0;
            }
        }
    }
    for (;;) {
        DWORD g = 0;
        char tmp[512];
        if (!ReadFile(er_, tmp, sizeof(tmp), &g, NULL) || g == 0)
            break;
        {
            int ol = (int)strlen(err);
            int room = errcap - 1 - ol;
            if (room > 0) {
                if ((int)g > room)
                    g = (DWORD)room;
                memcpy(err + ol, tmp, g);
                err[ol + (int)g] = 0;
            }
        }
    }
    CloseHandle(or_);
    CloseHandle(er_);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    *rc = (int)code;
    j->busy = 0;
    return 0;
}
