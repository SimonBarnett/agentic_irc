#include "config.h"

static int pin_ok_local(const char *p)
{
    int i;
    if (!p || strlen(p) != 6)
        return 0;
    for (i = 0; i < 6; i++) {
        if (p[i] < '0' || p[i] > '9')
            return 0;
    }
    return 1;
}

void config_defaults(ThinConfig *c)
{
    memset(c, 0, sizeof(*c));
    strncpy(c->host, "irc.ntsa.uk", sizeof(c->host) - 1);
    c->port = 6697;
    strncpy(c->realname, "airc-moot-thin", sizeof(c->realname) - 1);
}

void config_exe_dir(char *out, int outlen)
{
    char path[MAX_PATH];
    char *slash;
    int n;
    path[0] = 0;
    n = (int)GetModuleFileNameA(NULL, path, MAX_PATH);
    if (n <= 0 || n >= MAX_PATH)
        path[0] = 0;
    slash = strrchr(path, '\\');
    if (!slash)
        slash = strrchr(path, '/');
    if (slash)
        *slash = 0;
    if (!path[0])
        strncpy(path, ".", sizeof(path) - 1);
    strncpy(out, path, outlen - 1);
    out[outlen - 1] = 0;
}

void sanitize_hostname(const char *host, char *out, int outlen)
{
    char tmp[64];
    int i, o = 0;
    unsigned char c;
    if (outlen <= 0)
        return;
    out[0] = 0;
    if (!host)
        host = "";
    for (i = 0; host[i] && o < (int)sizeof(tmp) - 1; i++) {
        c = (unsigned char)tolower((unsigned char)host[i]);
        if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-' || c == '_') {
            tmp[o++] = (char)c;
        } else if (o > 0 && tmp[o - 1] != '-') {
            tmp[o++] = '-';
        }
    }
    tmp[o] = 0;
    while (o > 0 && tmp[o - 1] == '-')
        tmp[--o] = 0;
    i = 0;
    while (tmp[i] == '-')
        i++;
    if (!tmp[i]) {
        strncpy(out, "thin-box", outlen - 1);
        out[outlen - 1] = 0;
        return;
    }
    if (tmp[i] >= '0' && tmp[i] <= '9') {
        if (outlen < 3) {
            strncpy(out, "n", outlen - 1);
            out[outlen - 1] = 0;
            return;
        }
        out[0] = 'n';
        strncpy(out + 1, tmp + i, outlen - 2);
        out[outlen - 1] = 0;
    } else {
        strncpy(out, tmp + i, outlen - 1);
        out[outlen - 1] = 0;
    }
    if ((int)strlen(out) > 32)
        out[32] = 0;
    if (!nick_ok(out))
        strncpy(out, "thin-box", outlen - 1);
    out[outlen - 1] = 0;
}

static void default_nick_from_hostname(const char *hostname, char *out, int outlen)
{
    char hostpart[40];
    int n;
    if (outlen <= 0)
        return;
    out[0] = 0;
    sanitize_hostname(hostname, hostpart, sizeof(hostpart));
    _snprintf(out, outlen, "m3-%s", hostpart);
    n = (int)strlen(out);
    if (n > 32)
        out[32] = 0;
    if (!nick_ok(out))
        strncpy(out, "m3-thin-box", outlen - 1);
    out[outlen - 1] = 0;
}

int pairing_channel_forbidden(const char *channel)
{
    char low[64];
    if (!channel || !channel[0])
        return 0;
    str_lower_copy(low, channel, sizeof(low));
    return strcmp(low, "#bobiverse") == 0;
}

void config_self_heal_ex(ThinConfig *c, const char *exe_dir, const char *hostname)
{
    if (exe_dir && exe_dir[0] && !c->exe_dir[0])
        strncpy(c->exe_dir, exe_dir, sizeof(c->exe_dir) - 1);
    if (!c->home[0] && c->exe_dir[0])
        strncpy(c->home, c->exe_dir, sizeof(c->home) - 1);
    if (!c->allow_path[0] && c->home[0])
        _snprintf(c->allow_path, sizeof(c->allow_path), "%s\\jail", c->home);
    if (!c->nick[0] && hostname && hostname[0])
        default_nick_from_hostname(hostname, c->nick, sizeof(c->nick));
}

void config_self_heal(ThinConfig *c)
{
    char host[MAX_COMPUTERNAME_LENGTH + 1];
    DWORD n = MAX_COMPUTERNAME_LENGTH + 1;
    if (!c->exe_dir[0])
        config_exe_dir(c->exe_dir, sizeof(c->exe_dir));
    host[0] = 0;
    GetComputerNameA(host, &n);
    config_self_heal_ex(c, c->exe_dir, host);
}

int config_try_load_ini(ThinConfig *c, const char *path)
{
    char err[256];
    if (!path || !path[0])
        return 0;
    if (GetFileAttributesA(path) == INVALID_FILE_ATTRIBUTES)
        return 0;
    err[0] = 0;
    return config_load_ini(c, path, err, sizeof(err));
}

int config_key_path(const ThinConfig *c, char *out, int outlen)
{
    if (c->key_path[0]) {
        strncpy(out, c->key_path, outlen - 1);
        out[outlen - 1] = 0;
        return 0;
    }
    if (!c->home[0]) {
        out[0] = 0;
        return -1;
    }
    _snprintf(out, outlen, "%s\\dumb\\connector.key", c->home);
    return 0;
}

static void set_key(ThinConfig *c, const char *k, const char *v)
{
    char key[64];
    int i, j = 0;
    for (i = 0; k[i] && j < (int)sizeof(key) - 1; i++) {
        if (k[i] == '-' || k[i] == '_')
            continue;
        key[j++] = (char)tolower((unsigned char)k[i]);
    }
    key[j] = 0;
    if (strcmp(key, "nick") == 0)
        strncpy(c->nick, v, sizeof(c->nick) - 1);
    else if (strcmp(key, "channel") == 0)
        strncpy(c->channel, v, sizeof(c->channel) - 1);
    else if (strcmp(key, "moot") == 0 || strcmp(key, "mootid") == 0 || strcmp(key, "id") == 0)
        strncpy(c->moot_id, v, sizeof(c->moot_id) - 1);
    else if (strcmp(key, "home") == 0)
        strncpy(c->home, v, sizeof(c->home) - 1);
    else if (strcmp(key, "allowpath") == 0)
        strncpy(c->allow_path, v, sizeof(c->allow_path) - 1);
    else if (strcmp(key, "operators") == 0)
        strncpy(c->operators, v, sizeof(c->operators) - 1);
    else if (strcmp(key, "key") == 0 || strcmp(key, "keypath") == 0)
        strncpy(c->key_path, v, sizeof(c->key_path) - 1);
    else if (strcmp(key, "host") == 0)
        strncpy(c->host, v, sizeof(c->host) - 1);
    else if (strcmp(key, "port") == 0)
        c->port = atoi(v);
    else if (strcmp(key, "hello") == 0)
        strncpy(c->hello, v, sizeof(c->hello) - 1);
    else if (strcmp(key, "realname") == 0)
        strncpy(c->realname, v, sizeof(c->realname) - 1);
    else if (strcmp(key, "fromnick") == 0)
        strncpy(c->from_nick, v, sizeof(c->from_nick) - 1);
    else if (strcmp(key, "jobin") == 0)
        strncpy(c->job_in, v, sizeof(c->job_in) - 1);
    else if (strcmp(key, "jobout") == 0)
        strncpy(c->job_out, v, sizeof(c->job_out) - 1);
    else if (strcmp(key, "allowbin") == 0)
        strncpy(c->allow_bin_extra, v, sizeof(c->allow_bin_extra) - 1);
    else if (strcmp(key, "pin") == 0)
        strncpy(c->pin, v, sizeof(c->pin) - 1);
}

int config_load_ini(ThinConfig *c, const char *path, char *err, int errlen)
{
    char buf[8192];
    int n = 0;
    char *line, *save;
    if (read_file(path, (uint8_t *)buf, (int)sizeof(buf) - 1, &n) != 0) {
        _snprintf(err, errlen, "cannot read config %s", path);
        return -1;
    }
    buf[n] = 0;
    line = buf;
    while (line && *line) {
        char *nl = strchr(line, '\n');
        char *eq;
        if (nl) {
            *nl = 0;
            save = nl + 1;
        } else {
            save = NULL;
        }
        if (line[0] && line[strlen(line) - 1] == '\r')
            line[strlen(line) - 1] = 0;
        while (*line == ' ' || *line == '\t')
            line++;
        if (*line && *line != '#' && *line != ';' && *line != '[') {
            eq = strchr(line, '=');
            if (eq) {
                char k[64], v[512];
                int kl = (int)(eq - line);
                char *vv = eq + 1;
                while (kl > 0 && (line[kl - 1] == ' ' || line[kl - 1] == '\t'))
                    kl--;
                if (kl > (int)sizeof(k) - 1)
                    kl = (int)sizeof(k) - 1;
                memcpy(k, line, kl);
                k[kl] = 0;
                while (*vv == ' ' || *vv == '\t')
                    vv++;
                strncpy(v, vv, sizeof(v) - 1);
                v[sizeof(v) - 1] = 0;
                set_key(c, k, v);
            }
        }
        line = save;
    }
    return 0;
}

int config_parse_argv(ThinConfig *c, int argc, char **argv, char *err, int errlen)
{
    int i;
    (void)err;
    (void)errlen;
    for (i = 1; i < argc; i++) {
        const char *a = argv[i];
        const char *v = NULL;
        if (strcmp(a, "--help") == 0 || strcmp(a, "-h") == 0) {
            c->help = 1;
            continue;
        }
        if (strcmp(a, "--version") == 0) {
            c->version = 1;
            continue;
        }
        if (strcmp(a, "--selftest") == 0) {
            c->selftest = 1;
            continue;
        }
        if (strcmp(a, "--offline") == 0) {
            c->offline = 1;
            continue;
        }
        if (strcmp(a, "--once") == 0) {
            c->once = 1;
            continue;
        }
        if (strcmp(a, "--chair") == 0) {
            c->chair = 1;
            continue;
        }
        if (strncmp(a, "--", 2) != 0)
            continue;
        if (i + 1 < argc)
            v = argv[++i];
        else
            v = "";
        if (strcmp(a, "--config") == 0)
            strncpy(c->config_path, v, sizeof(c->config_path) - 1);
        else
            set_key(c, a + 2, v);
    }
    return 0;
}

int operators_empty(const char *ops)
{
    const char *p = ops ? ops : "";
    while (*p) {
        if (*p != ',' && *p != ' ' && *p != '\t')
            return 0;
        p++;
    }
    return 1;
}

int operator_allowed(const char *ops, const char *nick)
{
    char buf[512];
    char *tok, *ctx = NULL;
    if (!ops || !nick)
        return 0;
    strncpy(buf, ops, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = 0;
    tok = strtok(buf, ",");
    while (tok) {
        while (*tok == ' ' || *tok == '\t')
            tok++;
        {
            char *e = tok + strlen(tok);
            while (e > tok && (e[-1] == ' ' || e[-1] == '\t')) {
                e--;
                *e = 0;
            }
        }
        if (*tok && str_ieq(tok, nick))
            return 1;
        tok = strtok(NULL, ",");
        (void)ctx;
    }
    return 0;
}

void operators_add(char *ops, int cap, const char *nick)
{
    int n;
    if (!ops || cap <= 1 || !nick || !nick[0])
        return;
    if (operator_allowed(ops, nick))
        return;
    if (operators_empty(ops)) {
        strncpy(ops, nick, cap - 1);
        ops[cap - 1] = 0;
        return;
    }
    n = (int)strlen(ops);
    if (n + 1 + (int)strlen(nick) >= cap)
        return;
    ops[n] = ',';
    strncpy(ops + n + 1, nick, cap - n - 2);
    ops[cap - 1] = 0;
}

int config_write_paired(const ThinConfig *c)
{
    char dir[MAX_PATH], path[MAX_PATH], body[1024];
    const char *home = c->home[0] ? c->home : c->exe_dir;
    if (!home[0])
        return -1;
    _snprintf(dir, MAX_PATH, "%s\\dumb", home);
    mkdir_p(dir);
    _snprintf(path, MAX_PATH, "%s\\paired.ini", dir);
    _snprintf(body, sizeof(body),
              "; written after PIN pair. No PSK, no PIN. Do not commit.\n"
              "[client]\n"
              "nick=%s\n"
              "channel=%s\n"
              "moot=%s\n"
              "home=%s\n"
              "allow_path=%s\n"
              "operators=%s\n"
              "host=%s\n"
              "port=%d\n"
              "hello=%s\n",
              c->nick, c->channel, c->moot_id, c->home, c->allow_path, c->operators,
              c->host, c->port, c->hello);
    return write_file(path, (uint8_t *)body, (int)strlen(body));
}

int config_validate(const ThinConfig *c, char *err, int errlen)
{
    if (!c->nick[0] || !nick_ok(c->nick)) {
        _snprintf(err, errlen, "invalid --nick");
        return -1;
    }
    if (!channel_ok(c->channel)) {
        _snprintf(err, errlen, "missing channel (add channel=#name to airc-moot-thin.ini beside the exe)");
        return -1;
    }
    if ((c->chair || c->pairing) && pairing_channel_forbidden(c->channel)) {
        _snprintf(err, errlen, "pairing on #bobiverse is forbidden (use a private channel e.g. #airc-moot)");
        return -1;
    }
    if (c->port <= 0 || c->port > 65535) {
        _snprintf(err, errlen, "invalid --port");
        return -1;
    }
    if (!c->home[0]) {
        _snprintf(err, errlen, "missing --home");
        return -1;
    }
    if (!c->allow_path[0]) {
        _snprintf(err, errlen, "missing --allow-path");
        return -1;
    }
    if (c->chair || c->pairing) {
        if (c->pin[0] && !pin_ok_local(c->pin)) {
            _snprintf(err, errlen, "invalid --pin (6 digits)");
            return -1;
        }
        return 0;
    }
    if (!msgid_ok(c->moot_id)) {
        _snprintf(err, errlen, "invalid --moot (16 hex)");
        return -1;
    }
    if (operators_empty(c->operators)) {
        _snprintf(err, errlen, "installer MUST refuse empty --operators");
        return -1;
    }
    return 0;
}
