#include "config.h"

void config_defaults(ThinConfig *c)
{
    memset(c, 0, sizeof(*c));
    strncpy(c->host, "irc.libera.chat", sizeof(c->host) - 1);
    c->port = 6697;
    strncpy(c->realname, "airc-moot-thin", sizeof(c->realname) - 1);
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

int config_validate(const ThinConfig *c, char *err, int errlen)
{
    if (!c->nick[0] || !nick_ok(c->nick)) {
        _snprintf(err, errlen, "invalid --nick");
        return -1;
    }
    if (!channel_ok(c->channel)) {
        _snprintf(err, errlen, "invalid --channel");
        return -1;
    }
    if (!msgid_ok(c->moot_id)) {
        _snprintf(err, errlen, "invalid --moot (16 hex)");
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
    if (operators_empty(c->operators)) {
        _snprintf(err, errlen, "installer MUST refuse empty --operators");
        return -1;
    }
    if (c->port <= 0 || c->port > 65535) {
        _snprintf(err, errlen, "invalid --port");
        return -1;
    }
    return 0;
}
