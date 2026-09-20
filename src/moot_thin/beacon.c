#include "beacon.h"
#include "pair.h"

#include <time.h>
#include <wininet.h>

static void trim_cr(char *s)
{
    int n = (int)strlen(s);
    while (n > 0 && (s[n - 1] == '\n' || s[n - 1] == '\r' || s[n - 1] == ' ' || s[n - 1] == '\t'))
        s[--n] = 0;
}

static int looks_https(const char *u)
{
    return u && _strnicmp(u, "https://", 8) == 0;
}

int invite_expired(const InviteDoc *inv, unsigned long now)
{
    if (!inv)
        return 1;
    return now >= inv->expires_unix;
}

static int invite_fill_from_json(const char *text, InviteDoc *out)
{
    char kind[32];
    int port = 0, v = 0, exp = 0;
    memset(out, 0, sizeof(*out));
    kind[0] = 0;
    if (json_get_string(text, "kind", kind, sizeof(kind)) < 0)
        return -1;
    if (strcmp(kind, INVITE_KIND) != 0)
        return -1;
    json_get_int(text, "v", &v);
    out->v = v;
    if (out->v != 1)
        return -1;
    if (json_get_string(text, "host", out->host, sizeof(out->host)) < 0)
        strncpy(out->host, "irc.libera.chat", sizeof(out->host) - 1);
    if (json_get_int(text, "port", &port) == 0 && port > 0)
        out->port = port;
    else
        out->port = 6697;
    if (json_get_string(text, "channel", out->channel, sizeof(out->channel)) < 0)
        return -1;
    if (json_get_string(text, "moot", out->moot_id, sizeof(out->moot_id)) < 0)
        return -1;
    json_get_string(text, "pair", out->pair_id, sizeof(out->pair_id));
    if (json_get_string(text, "pin", out->pin, sizeof(out->pin)) < 0)
        return -1;
    json_get_string(text, "chair", out->chair, sizeof(out->chair));
    if (json_get_int(text, "expires", &exp) == 0)
        out->expires_unix = (unsigned long)exp;
    if (!channel_ok(out->channel) || !msgid_ok(out->moot_id) || !pin_ok(out->pin))
        return -1;
    if (out->pair_id[0] && !msgid_ok(out->pair_id))
        return -1;
    return 0;
}

int invite_parse_json(const char *text, InviteDoc *out)
{
    if (!text || !out)
        return -1;
    if (strstr(text, "psk") || strstr(text, "connector.key"))
        return -1;
    return invite_fill_from_json(text, out);
}

static int invite_parse_ini_text(char *buf, InviteDoc *out)
{
    char *line, *save;
    memset(out, 0, sizeof(*out));
    out->port = 6697;
    strncpy(out->host, "irc.libera.chat", sizeof(out->host) - 1);
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
        trim_cr(line);
        while (*line == ' ' || *line == '\t')
            line++;
        if (*line && *line != '#' && *line != ';' && *line != '[') {
            eq = strchr(line, '=');
            if (eq) {
                *eq = 0;
                trim_cr(line);
                {
                    char *v = eq + 1;
                    while (*v == ' ' || *v == '\t')
                        v++;
                    trim_cr(v);
                    if (_stricmp(line, "v") == 0)
                        out->v = atoi(v);
                    else if (_stricmp(line, "kind") == 0) {
                        if (strcmp(v, INVITE_KIND) != 0)
                            return -1;
                    } else if (_stricmp(line, "host") == 0)
                        strncpy(out->host, v, sizeof(out->host) - 1);
                    else if (_stricmp(line, "port") == 0)
                        out->port = atoi(v);
                    else if (_stricmp(line, "channel") == 0)
                        strncpy(out->channel, v, sizeof(out->channel) - 1);
                    else if (_stricmp(line, "moot") == 0)
                        strncpy(out->moot_id, v, sizeof(out->moot_id) - 1);
                    else if (_stricmp(line, "pair") == 0)
                        strncpy(out->pair_id, v, sizeof(out->pair_id) - 1);
                    else if (_stricmp(line, "pin") == 0)
                        strncpy(out->pin, v, sizeof(out->pin) - 1);
                    else if (_stricmp(line, "chair") == 0)
                        strncpy(out->chair, v, sizeof(out->chair) - 1);
                    else if (_stricmp(line, "expires") == 0)
                        out->expires_unix = (unsigned long)atoi(v);
                }
            }
        }
        line = save;
    }
    if (out->v != 1)
        return -1;
    if (!channel_ok(out->channel) || !msgid_ok(out->moot_id) || !pin_ok(out->pin))
        return -1;
    return 0;
}

int invite_apply(ThinConfig *c, const InviteDoc *inv, unsigned long now)
{
    if (!c || !inv)
        return -1;
    if (invite_expired(inv, now))
        return -2;
    if (inv->host[0])
        strncpy(c->host, inv->host, sizeof(c->host) - 1);
    if (inv->port > 0)
        c->port = inv->port;
    strncpy(c->channel, inv->channel, sizeof(c->channel) - 1);
    strncpy(c->moot_id, inv->moot_id, sizeof(c->moot_id) - 1);
    strncpy(c->pin, inv->pin, sizeof(c->pin) - 1);
    if (inv->pair_id[0])
        strncpy(c->pair_id, inv->pair_id, sizeof(c->pair_id) - 1);
    c->expires_unix = inv->expires_unix;
    c->pairing = 1;
    return 0;
}

int invite_write_files(const ThinConfig *c, const InviteDoc *inv)
{
    char jp[MAX_PATH], ip[MAX_PATH], json[1024], ini[1024];
    const char *dir;
    if (!c || !inv)
        return -1;
    dir = c->exe_dir[0] ? c->exe_dir : ".";
    _snprintf(jp, MAX_PATH, "%s\\airc-invite.json", dir);
    _snprintf(ip, MAX_PATH, "%s\\airc-invite.ini", dir);
    _snprintf(json, (int)sizeof(json),
              "{\"v\":1,\"kind\":\"airc-invite\",\"host\":\"%s\",\"port\":%d,"
              "\"channel\":\"%s\",\"moot\":\"%s\",\"pair\":\"%s\",\"pin\":\"%s\","
              "\"expires\":%lu,\"chair\":\"%s\"}\n",
              inv->host, inv->port, inv->channel, inv->moot_id, inv->pair_id,
              inv->pin, inv->expires_unix, inv->chair);
    if (strstr(json, "psk") || strstr(json, "connector.key"))
        return -1;
    _snprintf(ini, (int)sizeof(ini),
              "v=1\nkind=airc-invite\nhost=%s\nport=%d\nchannel=%s\nmoot=%s\n"
              "pair=%s\npin=%s\nexpires=%lu\nchair=%s\n",
              inv->host, inv->port, inv->channel, inv->moot_id, inv->pair_id,
              inv->pin, inv->expires_unix, inv->chair);
    if (write_file(jp, (const uint8_t *)json, (int)strlen(json)) != 0)
        return -1;
    if (write_file(ip, (const uint8_t *)ini, (int)strlen(ini)) != 0)
        return -1;
    info("INFO wrote airc-invite.json");
    return 0;
}

static int load_path(ThinConfig *c, const char *path, int json)
{
    char buf[JSON_MAX];
    int n = 0;
    InviteDoc inv;
    unsigned long now;
    if (read_file(path, (uint8_t *)buf, (int)sizeof(buf) - 1, &n) != 0)
        return -1;
    buf[n] = 0;
    if (json) {
        if (invite_parse_json(buf, &inv) != 0)
            return -3;
    } else {
        if (invite_parse_ini_text(buf, &inv) != 0)
            return -3;
    }
    now = (unsigned long)time(NULL);
    return invite_apply(c, &inv, now);
}

int invite_load_sibling(ThinConfig *c, const char *exe_dir)
{
    char p[MAX_PATH];
    int rc;
    const char *dir = (exe_dir && exe_dir[0]) ? exe_dir : ".";
    _snprintf(p, MAX_PATH, "%s\\airc-invite.ini", dir);
    if (GetFileAttributesA(p) != INVALID_FILE_ATTRIBUTES) {
        rc = load_path(c, p, 0);
        if (rc == 0 || rc == -2)
            return rc;
    }
    _snprintf(p, MAX_PATH, "%s\\airc-invite.json", dir);
    if (GetFileAttributesA(p) != INVALID_FILE_ATTRIBUTES)
        return load_path(c, p, 1);
    return -1;
}

int read_first_https_url(const char *path, char *out, int outlen)
{
    char buf[1024];
    int n = 0;
    char *line;
    if (!path || !out || outlen < 9)
        return -1;
    out[0] = 0;
    if (read_file(path, (uint8_t *)buf, (int)sizeof(buf) - 1, &n) != 0)
        return -1;
    buf[n] = 0;
    line = buf;
    while (line && *line) {
        char *nl = strchr(line, '\n');
        if (nl)
            *nl = 0;
        trim_cr(line);
        while (*line == ' ' || *line == '\t')
            line++;
        if (*line && *line != '#') {
            if (!looks_https(line))
                return -1;
            strncpy(out, line, outlen - 1);
            out[outlen - 1] = 0;
            return 0;
        }
        line = nl ? nl + 1 : NULL;
    }
    return -1;
}

int invite_fetch_https(const char *url, char *out, int outlen)
{
    HINTERNET ses, req;
    DWORD n = 0;
    int o = 0;
    if (!looks_https(url) || !out || outlen < 2)
        return -1;
    out[0] = 0;
    ses = InternetOpenA("airc-moot-thin", INTERNET_OPEN_TYPE_PRECONFIG, NULL, NULL, 0);
    if (!ses)
        return -1;
    req = InternetOpenUrlA(ses, url, NULL, 0,
                           INTERNET_FLAG_SECURE | INTERNET_FLAG_RELOAD | INTERNET_FLAG_NO_CACHE_WRITE, 0);
    if (!req) {
        InternetCloseHandle(ses);
        return -1;
    }
    while (o + 1 < outlen) {
        n = 0;
        if (!InternetReadFile(req, out + o, (DWORD)(outlen - 1 - o), &n) || n == 0)
            break;
        o += (int)n;
    }
    out[o] = 0;
    InternetCloseHandle(req);
    InternetCloseHandle(ses);
    return o > 0 ? 0 : -1;
}
