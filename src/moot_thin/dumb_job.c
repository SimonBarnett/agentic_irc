#include "dumb_job.h"
#include "aes256gcm.h"

int parse_dumb_line(const char *body, SealLine *out)
{
    char ver[8], to[40], from[40], id[24], is[8], ns[8], chunk[DUMB_CHUNK + 8];
    memset(out, 0, sizeof(*out));
    if (!body || strncmp(body, "DUMB v1 ", 8) != 0)
        return -1;
    if (sscanf(body, "DUMB %7s %39s %39s %23s %7s %7s %307s", ver, to, from, id, is, ns, chunk) < 7)
        return -1;
    if (strcmp(ver, "v1") != 0)
        return -1;
    if (!nick_ok(to) || !nick_ok(from) || !msgid_ok(id))
        return -1;
    if (strlen(is) > 2 || strlen(ns) > 2)
        return -1;
    out->i = atoi(is);
    out->n = atoi(ns);
    if (out->n < 1 || out->n > DUMB_MAX_N || out->i < 1 || out->i > out->n)
        return -1;
    strncpy(out->to_nick, to, sizeof(out->to_nick) - 1);
    strncpy(out->from_nick, from, sizeof(out->from_nick) - 1);
    strncpy(out->msg_id, id, sizeof(out->msg_id) - 1);
    strncpy(out->chunk, chunk, sizeof(out->chunk) - 1);
    return 0;
}

void frag_init(FragStore *s)
{
    memset(s, 0, sizeof(*s));
}

static void bag_free(FragStore *s, int k)
{
    int i;
    for (i = 0; i < DUMB_MAX_N; i++) {
        free(s->bags[k].parts[i]);
        s->bags[k].parts[i] = NULL;
    }
    memset(&s->bags[k], 0, sizeof(s->bags[k]));
}

char *frag_add(FragStore *s, const SealLine *ln)
{
    int k = -1, i;
    DWORD now = GetTickCount();
    char *out;
    int total = 0;
    if (ln->n > DUMB_MAX_N || ln->i < 1 || ln->i > ln->n)
        return NULL;
    for (i = 0; i < 8; i++) {
        if (s->bags[i].used && (now - s->bags[i].t0) > BAG_TTL_MS)
            bag_free(s, i);
    }
    for (i = 0; i < 8; i++) {
        if (s->bags[i].used && str_ieq(s->bags[i].from, ln->from_nick) && str_ieq(s->bags[i].id, ln->msg_id)) {
            k = i;
            break;
        }
    }
    if (k < 0) {
        for (i = 0; i < 8; i++) {
            if (!s->bags[i].used) {
                k = i;
                break;
            }
        }
        if (k < 0)
            return NULL;
        memset(&s->bags[k], 0, sizeof(s->bags[k]));
        s->bags[k].used = 1;
        strncpy(s->bags[k].from, ln->from_nick, sizeof(s->bags[k].from) - 1);
        strncpy(s->bags[k].id, ln->msg_id, sizeof(s->bags[k].id) - 1);
        s->bags[k].n = ln->n;
        s->bags[k].t0 = now;
    }
    if (s->bags[k].n != ln->n) {
        bag_free(s, k);
        return NULL;
    }
    {
        int idx = ln->i - 1;
        if (s->bags[k].parts[idx]) {
            if (strcmp(s->bags[k].parts[idx], ln->chunk) != 0) {
                bag_free(s, k);
                return NULL;
            }
        } else {
            s->bags[k].parts[idx] = xstrdup(ln->chunk);
            s->bags[k].have++;
        }
    }
    if (s->bags[k].have < s->bags[k].n)
        return NULL;
    for (i = 0; i < s->bags[k].n; i++)
        total += (int)strlen(s->bags[k].parts[i]);
    out = (char *)malloc(total + 1);
    if (!out) {
        bag_free(s, k);
        return NULL;
    }
    out[0] = 0;
    for (i = 0; i < s->bags[k].n; i++)
        strcat(out, s->bags[k].parts[i]);
    bag_free(s, k);
    return out;
}

int load_connector_key(const char *path, uint8_t key[32])
{
    uint8_t buf[4096];
    int n = 0;
    static const uint8_t magic[] = {'A', 'I', 'R', 'C', '1'};
    if (read_file(path, buf, (int)sizeof(buf), &n) != 0)
        return -1;
    if (n >= 5 && memcmp(buf, magic, 5) == 0) {
        uint8_t plain[4096];
        int pn = 0;
        if (dpapi_unprotect(buf + 5, n - 5, plain, (int)sizeof(plain), &pn) != 0)
            return -1;
        if (pn != 32)
            return -1;
        memcpy(key, plain, 32);
        return 0;
    }
    if (n == 32) {
        memcpy(key, buf, 32);
        return 0;
    }
    return -1;
}

static void json_err(char *result, int cap, const char *op, const char *id, const char *error)
{
    _snprintf(result, cap, "{\"v\":1,\"op\":\"%s\",\"id\":\"%s\",\"ok\":false,\"error\":\"%s\"}",
              op ? op : "", id ? id : "", error);
}

int run_job_json(const char *job_json, const char *from_nick, const ThinConfig *cfg, Jail *jail,
                 char *result, int resultcap)
{
    char op[32], id[24], cwd[MAX_PATH], path[MAX_PATH], b64[JSON_MAX];
    char *argv[16];
    int argc = 0, i, timeout_s = 20;
    memset(argv, 0, sizeof(argv));
    op[0] = 0;
    id[0] = 0;
    cwd[0] = 0;
    path[0] = 0;
    b64[0] = 0;
    json_get_string(job_json, "op", op, sizeof(op));
    json_get_string(job_json, "id", id, sizeof(id));
    if (!operator_allowed(cfg->operators, from_nick)) {
        json_err(result, resultcap, op, id, "operator");
        return 0;
    }
    if (strcmp(op, "ping") == 0) {
        _snprintf(result, resultcap, "{\"v\":1,\"op\":\"ping\",\"id\":\"%s\",\"ok\":true,\"rc\":0}", id);
        return 0;
    }
    if (strcmp(op, "sysinfo") == 0) {
        char machine[MAX_COMPUTERNAME_LENGTH + 1];
        char user[256];
        DWORD mn = MAX_COMPUTERNAME_LENGTH + 1, un = 256;
        machine[0] = 0;
        user[0] = 0;
        GetComputerNameA(machine, &mn);
        GetUserNameA(user, &un);
        _snprintf(result, resultcap,
                  "{\"v\":1,\"op\":\"sysinfo\",\"id\":\"%s\",\"ok\":true,\"sys\":{\"os\":\"win32\",\"machine\":\"%s\",\"user\":\"%s\"}}",
                  id, machine, user);
        return 0;
    }
    if (strcmp(op, "get") == 0 || strcmp(op, "put") == 0) {
        const char *bn;
        json_get_string(job_json, "path", path, sizeof(path));
        if (!path[0])
            json_get_string(job_json, "cwd", path, sizeof(path));
        if ((path[0] == '\\' && path[1] == '\\') || (path[0] == '/' && path[1] == '/')) {
            json_err(result, resultcap, op, id, "jail");
            return 0;
        }
        if (!(path[0] && (path[1] == ':' || path[0] == '\\' || path[0] == '/'))) {
            char joined[MAX_PATH];
            _snprintf(joined, MAX_PATH, "%s\\%s", jail->root, path);
            strncpy(path, joined, sizeof(path) - 1);
        }
        if (!jail_in(jail, path)) {
            json_err(result, resultcap, op, id, "jail");
            return 0;
        }
        bn = path_basename(path);
        if (str_ieq(bn, "identity.json") || str_ieq(bn, "connector.key") || str_ieq(bn, "peers.json")) {
            json_err(result, resultcap, op, id, "jail");
            return 0;
        }
        if (strcmp(op, "get") == 0) {
            uint8_t data[12 * 1024 + 1];
            int n = 0;
            char hex[72], b64o[18000];
            uint8_t sh[32];
            if (read_file(path, data, sizeof(data) - 1, &n) != 0) {
                json_err(result, resultcap, op, id, "jail");
                return 0;
            }
            sha256(data, n, sh);
            hex_encode(sh, 32, hex, sizeof(hex));
            b64o[0] = 0;
            if (n <= 12 * 1024)
                b64_encode(data, n, b64o, sizeof(b64o));
            _snprintf(result, resultcap,
                      "{\"v\":1,\"op\":\"get\",\"id\":\"%s\",\"ok\":true,\"sha256\":\"%s\",\"b64\":\"%s\"}",
                      id, hex, b64o);
            return 0;
        }
        {
            uint8_t raw[12 * 1024];
            int rn;
            uint8_t sh[32];
            char hex[72];
            json_get_string(job_json, "b64", b64, sizeof(b64));
            rn = b64_decode(b64, raw, sizeof(raw));
            if (rn < 0)
                rn = 0;
            if (write_file(path, raw, rn) != 0) {
                json_err(result, resultcap, op, id, "jail");
                return 0;
            }
            sha256(raw, rn, sh);
            hex_encode(sh, 32, hex, sizeof(hex));
            _snprintf(result, resultcap, "{\"v\":1,\"op\":\"put\",\"id\":\"%s\",\"ok\":true,\"sha256\":\"%s\"}", id, hex);
            return 0;
        }
    }
    if (strcmp(op, "exec") == 0) {
        char out[RESULT_BYTES_MAX + 8];
        char errb[RESULT_BYTES_MAX + 8];
        char out_esc[RESULT_BYTES_MAX * 2];
        char err_esc[RESULT_BYTES_MAX * 2];
        int rc = 1, truncated = 0, st;
        json_get_int(job_json, "timeout_s", &timeout_s);
        json_get_string(job_json, "cwd", cwd, sizeof(cwd));
        argc = json_get_string_array(job_json, "argv", argv, 16);
        if (argc < 0)
            argc = 0;
        if (!cwd[0])
            strncpy(cwd, jail->root, sizeof(cwd) - 1);
        st = jail_exec(jail, argv, argc, cwd, timeout_s, out, sizeof(out), errb, sizeof(errb), &rc);
        for (i = 0; i < argc; i++)
            free(argv[i]);
        if (st == -2) {
            json_err(result, resultcap, op, id, "busy");
            return 0;
        }
        if (st == -3) {
            json_err(result, resultcap, op, id, "bin");
            return 0;
        }
        if (st == -4) {
            json_err(result, resultcap, op, id, "jail");
            return 0;
        }
        if (st == -5) {
            json_err(result, resultcap, op, id, "timeout");
            return 0;
        }
        if (st != 0) {
            json_err(result, resultcap, op, id, "bin");
            return 0;
        }
        jail_apply_trunc(cfg->home, id, out, errb, &truncated);
        json_escape(out, out_esc, sizeof(out_esc));
        json_escape(errb, err_esc, sizeof(err_esc));
        _snprintf(result, resultcap,
                  "{\"v\":1,\"op\":\"exec\",\"id\":\"%s\",\"ok\":%s,\"rc\":%d,\"stdout\":\"%s\",\"stderr\":\"%s\",\"truncated\":%s}",
                  id, rc == 0 ? "true" : "false", rc, out_esc, err_esc, truncated ? "true" : "false");
        return 0;
    }
    json_err(result, resultcap, op, id, "op");
    return 0;
}

int dumb_irc_lines(const uint8_t *blob, int blob_len, const char *to_nick, const char *from_nick,
                   const char *msg_id, char lines[][LINE_MAX], int max_lines)
{
    char b64[JSON_MAX];
    int bl, n, i, chunk;
    if (b64_encode(blob, blob_len, b64, sizeof(b64)) < 0)
        return -1;
    bl = (int)strlen(b64);
    n = (bl + DUMB_CHUNK - 1) / DUMB_CHUNK;
    if (n < 1)
        n = 1;
    if (n > DUMB_MAX_N || n > max_lines)
        return -1;
    for (i = 0; i < n; i++) {
        chunk = bl - i * DUMB_CHUNK;
        if (chunk > DUMB_CHUNK)
            chunk = DUMB_CHUNK;
        _snprintf(lines[i], LINE_MAX, "DUMB v1 %s %s %s %d %d %.*s",
                  to_nick, from_nick, msg_id, i + 1, n, chunk, b64 + i * DUMB_CHUNK);
    }
    return n;
}
