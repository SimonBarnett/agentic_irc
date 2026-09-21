#include "task_ui.h"

static int g_enabled = 1;
static int g_console = -1;
static int g_active = 0;
static int g_frame = 0;
static WORD g_attr_normal = 7;
static char g_desc[220];
static HANDLE g_out;

static int stdout_is_console(void)
{
    DWORD mode = 0;
    if (g_console >= 0)
        return g_console;
    g_out = GetStdHandle(STD_OUTPUT_HANDLE);
    if (g_out == NULL || g_out == INVALID_HANDLE_VALUE) {
        g_console = 0;
        return 0;
    }
    if (!GetConsoleMode(g_out, &mode)) {
        g_console = 0;
        return 0;
    }
    g_console = 1;
    {
        CONSOLE_SCREEN_BUFFER_INFO info;
        if (GetConsoleScreenBufferInfo(g_out, &info))
            g_attr_normal = info.wAttributes;
    }
    return 1;
}

void task_ui_set_enabled(int on)
{
    g_enabled = on ? 1 : 0;
}

static void set_color(WORD attr)
{
    if (g_out && g_out != INVALID_HANDLE_VALUE)
        SetConsoleTextAttribute(g_out, attr);
}

static void job_description(const char *job_json, char *out, int cap)
{
    char op[32];
    int i, argc;
    char *argv[16];

    op[0] = 0;
    out[0] = 0;
    if (!job_json || cap < 8)
        return;
    json_get_string(job_json, "op", op, sizeof(op));
    if (strcmp(op, "ping") == 0) {
        _snprintf(out, cap, "Task: connection check (ping)");
        return;
    }
    if (strcmp(op, "sysinfo") == 0) {
        _snprintf(out, cap, "Task: collect system information");
        return;
    }
    if (strcmp(op, "get") == 0) {
        char path[MAX_PATH];
        path[0] = 0;
        json_get_string(job_json, "path", path, sizeof(path));
        if (!path[0])
            json_get_string(job_json, "cwd", path, sizeof(path));
        _snprintf(out, cap, "Task: read file %s", path[0] ? path : "(jail)");
        return;
    }
    if (strcmp(op, "put") == 0) {
        char path[MAX_PATH];
        path[0] = 0;
        json_get_string(job_json, "path", path, sizeof(path));
        _snprintf(out, cap, "Task: write file %s", path[0] ? path : "(jail)");
        return;
    }
    if (strcmp(op, "exec") == 0) {
        int o = 0;
        argc = json_get_string_array(job_json, "argv", argv, 16);
        if (argc < 0)
            argc = 0;
        o = _snprintf(out, cap, "Task: run ");
        for (i = 0; i < argc && o < cap - 2; i++) {
            if (i)
                out[o++] = ' ';
            {
                int k = (int)strlen(argv[i]);
                if (k > cap - o - 1)
                    k = cap - o - 1;
                memcpy(out + o, argv[i], k);
                o += k;
            }
            free(argv[i]);
        }
        out[o] = 0;
        if (!argc)
            strncpy(out, "Task: run command", cap - 1);
        return;
    }
    if (op[0])
        _snprintf(out, cap, "Task: %s", op);
    else
        strncpy(out, "Task: remote job", cap - 1);
    out[cap - 1] = 0;
}

void task_ui_begin(const char *job_json)
{
    g_active = 0;
    if (!g_enabled || !stdout_is_console())
        return;
    job_description(job_json, g_desc, sizeof(g_desc));
    g_frame = 0;
    g_active = 1;
    task_ui_spin_tick();
}

void task_ui_spin_tick(void)
{
    static const char spin[] = "\\|/-";
    if (!g_active)
        return;
    g_frame++;
    set_color(g_attr_normal);
    printf("\r%s ... %c", g_desc, spin[g_frame & 3]);
    fflush(stdout);
}

static const char *json_ok(const char *result)
{
    const char *p;
    if (!result)
        return NULL;
    p = strstr(result, "\"ok\":true");
    if (p)
        return "true";
    p = strstr(result, "\"ok\":false");
    if (p)
        return "false";
    return NULL;
}

static void json_error_msg(const char *result, char *out, int cap)
{
    out[0] = 0;
    if (!result || cap < 2)
        return;
    if (json_get_string(result, "error", out, cap) >= 0 && out[0])
        return;
    if (json_get_string(result, "stderr", out, cap) >= 0 && out[0])
        return;
    strncpy(out, "job failed on this machine", cap - 1);
    out[cap - 1] = 0;
}

void task_ui_end(const char *result_json)
{
    const char *ok;
    char err[512];

    if (!g_active)
        return;
    g_active = 0;
    ok = json_ok(result_json);
    set_color(g_attr_normal);
    printf("\r%s ... ", g_desc);
    if (ok && strcmp(ok, "true") == 0) {
        set_color(FOREGROUND_GREEN | FOREGROUND_INTENSITY);
        printf("DONE");
    } else {
        set_color(FOREGROUND_RED | FOREGROUND_INTENSITY);
        printf("FAIL");
        set_color(g_attr_normal);
        printf("\n");
        json_error_msg(result_json, err, sizeof(err));
        set_color(FOREGROUND_RED | FOREGROUND_INTENSITY);
        printf("%s\n", err);
        set_color(g_attr_normal);
        return;
    }
    set_color(g_attr_normal);
    printf("\n");
}
