#include "util.h"
#include "config.h"
#include "jail.h"
#include "moot.h"
#include "dumb_job.h"
#include "aes256gcm.h"
#include "irc_tls.h"

/* Keep in sync with VERSION */
#define AIRC_THIN_VERSION "0.1.0"

static void usage(void)
{
    info("airc-moot-thin %s — Win32 ANSI thin moot CLI (not an LLM)", AIRC_THIN_VERSION);
    info("usage: airc-moot-thin.exe --nick N --channel #chan --moot 16hex --home DIR --allow-path DIR --operators nicks");
    info("  [--key PATH] [--config FILE.ini] [--host HOST] [--port N] [--hello TEXT] [--once]");
    info("  --selftest   offline checks, no sockets");
    info("  --offline --from-nick N --job-in job.json [--job-out result.json]");
    info("empty --operators is refused. Does not claim Windows 95 TLS.");
}

static int load_key_or_none(const ThinConfig *cfg, uint8_t key[32], int *have)
{
    char path[MAX_PATH];
    *have = 0;
    if (cfg->key_path[0])
        strncpy(path, cfg->key_path, MAX_PATH - 1);
    else
        _snprintf(path, MAX_PATH, "%s\\dumb\\connector.key", cfg->home);
    path[MAX_PATH - 1] = 0;
    if (GetFileAttributesA(path) == INVALID_FILE_ATTRIBUTES)
        return 0;
    if (load_connector_key(path, key) != 0) {
        info("INFO key unreadable");
        return -1;
    }
    *have = 1;
    {
        uint8_t fp[32];
        char hex[72];
        sha256(key, 32, fp);
        hex_encode(fp, 32, hex, sizeof(hex));
        info("INFO keyfp=%s", hex);
    }
    return 0;
}

static int selftest(void)
{
    ThinConfig cfg;
    Jail jail;
    char err[256];
    char line[256];
    char tmpdir[MAX_PATH], ini[MAX_PATH], jailp[MAX_PATH];
    int fails = 0;
    DWORD pid = GetCurrentProcessId();

    info("INFO selftest airc-moot-thin %s ptr=%d", AIRC_THIN_VERSION, (int)sizeof(void *));

    GetTempPathA(MAX_PATH, tmpdir);
    _snprintf(jailp, MAX_PATH, "%sairc-thin-%lu", tmpdir, (unsigned long)pid);
    mkdir_p(jailp);
    _snprintf(ini, MAX_PATH, "%s\\t.ini", jailp);

    /* config: empty operators */
    {
        ThinConfig c;
        config_defaults(&c);
        strncpy(c.nick, "thin-box", sizeof(c.nick) - 1);
        strncpy(c.channel, "#ops", sizeof(c.channel) - 1);
        strncpy(c.moot_id, "0123456789abcdef", sizeof(c.moot_id) - 1);
        strncpy(c.home, jailp, sizeof(c.home) - 1);
        strncpy(c.allow_path, jailp, sizeof(c.allow_path) - 1);
        c.operators[0] = 0;
        if (config_validate(&c, err, sizeof(err)) == 0 || !strstr(err, "operators")) {
            info("FAIL empty operators");
            fails++;
        } else
            info("INFO empty operators refused");
    }

    /* INI parse */
    {
        char body[512];
        ThinConfig c;
        _snprintf(body, sizeof(body),
                  "[client]\nnick=thin-box\nchannel=#ops\nmoot=0123456789abcdef\nhome=%s\nallow_path=%s\noperators=alice,cm-bob\n",
                  jailp, jailp);
        write_file(ini, (uint8_t *)body, (int)strlen(body));
        config_defaults(&c);
        if (config_load_ini(&c, ini, err, sizeof(err)) != 0 || config_validate(&c, err, sizeof(err)) != 0) {
            info("FAIL ini parse %s", err);
            fails++;
        } else if (!operator_allowed(c.operators, "ALICE") || !operator_allowed(c.operators, "cm-bob")) {
            info("FAIL operators list");
            fails++;
        } else
            info("INFO config parse ok");
    }

    jail_init(&jail, jailp, "");
    {
        char esc[MAX_PATH];
        _snprintf(esc, MAX_PATH, "%s\\..\\Windows\\win.ini", jailp);
        if (jail_in(&jail, "\\\\server\\share\\x") || jail_in(&jail, "//server/share/x") || jail_in(&jail, esc)) {
            info("FAIL jail escape");
            fails++;
        } else if (!jail_in(&jail, jailp)) {
            info("FAIL jail root");
            fails++;
        } else
            info("INFO jail refuse ok");
    }

    /* AES-GCM known vector (Python cryptography / seal.dumb_open_bytes) */
    {
        uint8_t key[32], blob[128], pt[128];
        int pn = 0, bn;
        const char *blob_hex = "0102030405060708090a0b0c01507382d2268963858899fb4e9f767c14bc8fd55e95c4790ea2c59d7f03107e72e67adda31cd8f667954d7248703b3eb582e3b2f1d462c441bba7";
        const char *want = "{\"v\":1,\"op\":\"ping\",\"id\":\"0123456789abcdef\"}";
        hex_decode("00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff", key, 32);
        bn = hex_decode(blob_hex, blob, sizeof(blob));
        if (bn < 0 || dumb_open(key, "#ops", "box", "alice", "0123456789abcdef", blob, bn, pt, sizeof(pt), &pn) != 0) {
            info("FAIL aesgcm open");
            fails++;
        } else {
            pt[pn] = 0;
            if (strcmp((char *)pt, want) != 0) {
                info("FAIL aesgcm plaintext");
                fails++;
            } else
                info("INFO aesgcm vector ok");
        }
    }

    /* operator drop + ping */
    {
        char job[128], res[512];
        config_defaults(&cfg);
        strncpy(cfg.nick, "box", sizeof(cfg.nick) - 1);
        strncpy(cfg.channel, "#ops", sizeof(cfg.channel) - 1);
        strncpy(cfg.moot_id, "0123456789abcdef", sizeof(cfg.moot_id) - 1);
        strncpy(cfg.home, jailp, sizeof(cfg.home) - 1);
        strncpy(cfg.allow_path, jailp, sizeof(cfg.allow_path) - 1);
        strncpy(cfg.operators, "alice", sizeof(cfg.operators) - 1);
        strncpy(job, "{\"v\":1,\"op\":\"exec\",\"id\":\"0123456789abcdef\",\"argv\":[\"hostname\"]}", sizeof(job) - 1);
        run_job_json(job, "mallory", &cfg, &jail, res, sizeof(res));
        if (!strstr(res, "\"error\":\"operator\"")) {
            info("FAIL operator drop %s", res);
            fails++;
        } else
            info("INFO operator drop ok");
        strncpy(job, "{\"v\":1,\"op\":\"ping\",\"id\":\"0123456789abcdef\"}", sizeof(job) - 1);
        run_job_json(job, "alice", &cfg, &jail, res, sizeof(res));
        if (!strstr(res, "\"ok\":true") || !strstr(res, "ping")) {
            info("FAIL ping %s", res);
            fails++;
        } else
            info("INFO ping ok");
    }

    /* exec hostname */
    {
        char job[192], res[4096];
        _snprintf(job, sizeof(job),
                  "{\"v\":1,\"op\":\"exec\",\"id\":\"0123456789abcdef\",\"argv\":[\"hostname\"],\"cwd\":\"%s\"}",
                  jailp);
        /* JSON cwd backslashes — use jail root default */
        strncpy(job, "{\"v\":1,\"op\":\"exec\",\"id\":\"0123456789abcdef\",\"argv\":[\"hostname\"]}", sizeof(job) - 1);
        run_job_json(job, "alice", &cfg, &jail, res, sizeof(res));
        if (!strstr(res, "\"op\":\"exec\"") || !strstr(res, "\"rc\":") || !strstr(res, "stdout")) {
            info("FAIL exec framing %s", res);
            fails++;
        } else
            info("INFO exec stdout/rc ok");
    }

    /* truncation */
    {
        char big[9001];
        char errb[32];
        int trunc = 0;
        memset(big, 'B', 9000);
        big[9000] = 0;
        errb[0] = 0;
        jail_apply_trunc(jailp, "0123456789abcdef", big, errb, &trunc);
        if (!trunc || strlen(big) > 4000) {
            info("FAIL truncation");
            fails++;
        } else {
            char spill[MAX_PATH];
            _snprintf(spill, MAX_PATH, "%s\\dumb\\results\\0123456789abcdef.txt", jailp);
            if (GetFileAttributesA(spill) == INVALID_FILE_ATTRIBUTES) {
                info("FAIL truncation spill");
                fails++;
            } else
                info("INFO truncation flag ok");
        }
    }

    moot_join_line("0123456789abcdef", line, sizeof(line));
    if (strcmp(line, "MOOT v1 JOIN 0123456789abcdef") != 0) {
        info("FAIL moot join");
        fails++;
    } else
        info("INFO moot JOIN ok");

    {
        SealLine sl;
        if (parse_dumb_line("DUMB v1 bob alice 0123456789abcdef 1 100 AAAA", &sl) == 0) {
            info("FAIL dumb n=100");
            fails++;
        } else
            info("INFO dumb n=100 dropped");
    }

    if (fails) {
        info("INFO selftest FAIL %d", fails);
        return 1;
    }
    info("INFO selftest ok");
    return 0;
}

static int offline_job(ThinConfig *cfg)
{
    Jail jail;
    uint8_t raw[JSON_MAX];
    char job[JSON_MAX], res[JSON_MAX];
    int n = 0;
    char err[256];
    if (config_validate(cfg, err, sizeof(err)) != 0) {
        info("INFO %s", err);
        return 2;
    }
    if (!cfg->from_nick[0]) {
        info("INFO missing --from-nick");
        return 2;
    }
    if (!cfg->job_in[0] || read_file(cfg->job_in, raw, sizeof(raw) - 1, &n) != 0) {
        info("INFO cannot read --job-in");
        return 2;
    }
    raw[n] = 0;
    memcpy(job, raw, n + 1);
    jail_init(&jail, cfg->allow_path, cfg->allow_bin_extra);
    run_job_json(job, cfg->from_nick, cfg, &jail, res, sizeof(res));
    if (cfg->job_out[0])
        write_file(cfg->job_out, (uint8_t *)res, (int)strlen(res));
    info("%s", res);
    return 0;
}

static DWORD last_privmsg;

static void say(IrcConn *irc, const char *chan, const char *msg)
{
    char line[LINE_MAX];
    DWORD now = GetTickCount();
    if (last_privmsg && now - last_privmsg < FLOOD_MS)
        Sleep(FLOOD_MS - (now - last_privmsg));
    _snprintf(line, sizeof(line), "PRIVMSG %s :%s", chan, msg);
    irc_send_line(irc, line);
    last_privmsg = GetTickCount();
}

static void handle_privmsg(IrcConn *irc, ThinConfig *cfg, Jail *jail, FragStore *frags,
                           const uint8_t *key, int have_key, const char *live_nick,
                           const char *prefix, const char *target, const char *body)
{
    char src[64];
    const char *bang;
    SealLine sl;
    if (_stricmp(target, cfg->channel) != 0)
        return;
    bang = strchr(prefix, '!');
    if (bang) {
        int n = (int)(bang - prefix);
        if (n > 62)
            n = 62;
        memcpy(src, prefix, n);
        src[n] = 0;
    } else {
        strncpy(src, prefix, sizeof(src) - 1);
        src[sizeof(src) - 1] = 0;
    }
    if (parse_dumb_line(body, &sl) != 0)
        return;
    if (!str_ieq(sl.from_nick, src)) {
        info("INFO DUMB prefix != from_nick, drop");
        return;
    }
    if (!str_ieq(sl.to_nick, cfg->nick) && !str_ieq(sl.to_nick, live_nick))
        return;
    if (!operator_allowed(cfg->operators, src)) {
        info("INFO dumb drop operator from=%s", src);
        return;
    }
    {
        char *b64 = frag_add(frags, &sl);
        uint8_t blob[JSON_MAX];
        uint8_t pt[JSON_MAX];
        char result[JSON_MAX];
        int bn, pn = 0;
        uint8_t outb[JSON_MAX];
        int on = 0;
        char lines[DUMB_MAX_N][LINE_MAX];
        int nl, i;
        if (!b64)
            return;
        bn = b64_decode(b64, blob, sizeof(blob));
        free(b64);
        if (bn < 0 || !have_key) {
            info("INFO dumb job id=%s decrypt failed", sl.msg_id);
            return;
        }
        if (dumb_open(key, cfg->channel, sl.to_nick, src, sl.msg_id, blob, bn, pt, sizeof(pt), &pn) != 0) {
            info("INFO dumb job id=%s decrypt failed", sl.msg_id);
            return;
        }
        pt[pn] = 0;
        run_job_json((char *)pt, src, cfg, jail, result, sizeof(result));
        if (dumb_seal(key, cfg->channel, src, cfg->nick, sl.msg_id, (uint8_t *)result, (int)strlen(result), outb, sizeof(outb), &on) != 0)
            return;
        nl = dumb_irc_lines(outb, on, src, cfg->nick, sl.msg_id, lines, DUMB_MAX_N);
        for (i = 0; i < nl; i++)
            say(irc, cfg->channel, lines[i]);
        info("INFO dumb job id=%s from=%s", sl.msg_id, src);
    }
}

static int session(ThinConfig *cfg, Jail *jail, const uint8_t *key, int have_key)
{
    IrcConn *irc;
    char err[256], line[1024], capa[512], mjoin[128];
    char live[NICK_MAX + 8];
    int got_001 = 0, got_join = 0;
    DWORD t0, last_capa;
    FragStore frags;
    int use_tls = (cfg->port == 6697);

    strncpy(live, cfg->nick, sizeof(live) - 1);
    frag_init(&frags);
    irc = irc_new();
    if (!irc)
        return -1;
    info("INFO connecting %s:%d tls=%d", cfg->host, cfg->port, use_tls);
    if (irc_connect(irc, cfg->host, cfg->port, use_tls, err, sizeof(err)) != 0) {
        info("INFO connect failed %s", err);
        irc_free(irc);
        return -1;
    }
    irc_send_line(irc, "CAP LS 302");
    {
        char n[80], u[160];
        _snprintf(n, sizeof(n), "NICK %s", live);
        _snprintf(u, sizeof(u), "USER %s 0 * :%s", live, cfg->realname);
        irc_send_line(irc, n);
        irc_send_line(irc, u);
    }
    /* CAP LS without CAP END stalls 001 on IRCv3 (Libera). No SASL in this client. */
    irc_send_line(irc, "CAP END");
    t0 = GetTickCount();
    while (!got_001) {
        int r = irc_recv_line(irc, line, sizeof(line), 1000);
        if (r < 0) {
            info("INFO NO 001 (recv fail)");
            irc_free(irc);
            return -1;
        }
        if (r == 0) {
            if ((int)(GetTickCount() - t0) > 30000) {
                info("INFO NO 001");
                irc_free(irc);
                return -1;
            }
            continue;
        }
        if (strncmp(line, "PING ", 5) == 0) {
            char pong[LINE_MAX];
            _snprintf(pong, sizeof(pong), "PONG %s", line + 5);
            irc_send_line(irc, pong);
        }
        if (strstr(line, " 001 "))
            got_001 = 1;
        if (strstr(line, " 433 ") || strstr(line, " 432 ")) {
            char n[80];
            _snprintf(live, sizeof(live), "%s_l", cfg->nick);
            _snprintf(n, sizeof(n), "NICK %s", live);
            irc_send_line(irc, n);
            info("INFO nick -> %s (still accept %s)", live, cfg->nick);
        }
    }
    if (!got_001) {
        irc_free(irc);
        return -1;
    }
    Sleep(1000);
    {
        char j[80];
        _snprintf(j, sizeof(j), "JOIN %s", cfg->channel);
        irc_send_line(irc, j);
    }
    t0 = GetTickCount();
    while (!got_join) {
        int r = irc_recv_line(irc, line, sizeof(line), 1000);
        if (r < 0)
            break;
        if (r == 0) {
            if ((int)(GetTickCount() - t0) > 30000) {
                info("INFO NO JOIN");
                irc_free(irc);
                return -1;
            }
            continue;
        }
        if (strncmp(line, "PING ", 5) == 0) {
            char pong[LINE_MAX];
            _snprintf(pong, sizeof(pong), "PONG %s", line + 5);
            irc_send_line(irc, pong);
        }
        if (strstr(line, "JOIN"))
            got_join = 1;
    }
    if (cfg->hello[0])
        say(irc, cfg->channel, cfg->hello);
    capa_line(cfg->nick, cfg->allow_path, have_key, capa, sizeof(capa));
    say(irc, cfg->channel, capa);
    moot_join_line(cfg->moot_id, mjoin, sizeof(mjoin));
    say(irc, cfg->channel, mjoin);
    info("INFO joined %s as %s moot=%s", cfg->channel, live, cfg->moot_id);
    last_capa = GetTickCount();
    for (;;) {
        int r = irc_recv_line(irc, line, sizeof(line), 1000);
        if ((int)(GetTickCount() - last_capa) >= CAPA_MS) {
            say(irc, cfg->channel, capa);
            say(irc, cfg->channel, mjoin);
            last_capa = GetTickCount();
        }
        if (r < 0)
            break;
        if (r == 0)
            continue;
        if (strncmp(line, "PING ", 5) == 0) {
            char pong[LINE_MAX];
            _snprintf(pong, sizeof(pong), "PONG %s", line + 5);
            irc_send_line(irc, pong);
            continue;
        }
        if (strstr(line, " PRIVMSG ")) {
            char *sp, *tgt, *body;
            char prefix[128];
            prefix[0] = 0;
            sp = line;
            if (line[0] == ':') {
                char *p2 = strchr(line + 1, ' ');
                if (!p2)
                    continue;
                {
                    int n = (int)(p2 - (line + 1));
                    if (n > 126)
                        n = 126;
                    memcpy(prefix, line + 1, n);
                    prefix[n] = 0;
                }
                sp = p2 + 1;
            }
            if (strncmp(sp, "PRIVMSG ", 8) != 0)
                continue;
            tgt = sp + 8;
            body = strstr(tgt, " :");
            if (!body)
                continue;
            *body = 0;
            body += 2;
            handle_privmsg(irc, cfg, jail, &frags, key, have_key, live, prefix, tgt, body);
        }
    }
    irc_free(irc);
    return 0;
}

int main(int argc, char **argv)
{
    ThinConfig cfg;
    Jail jail;
    char err[256];
    uint8_t key[32];
    int have_key = 0;
    int rc;

    config_defaults(&cfg);
    config_parse_argv(&cfg, argc, argv, err, sizeof(err));
    if (cfg.help) {
        usage();
        return 0;
    }
    if (cfg.version) {
        info("airc-moot-thin %s", AIRC_THIN_VERSION);
        return 0;
    }
    if (cfg.selftest)
        return selftest();
    if (cfg.config_path[0]) {
        if (config_load_ini(&cfg, cfg.config_path, err, sizeof(err)) != 0) {
            info("INFO %s", err);
            return 2;
        }
        /* CLI again so flags win over ini. Do NOT config_defaults here:
         * that wiped nick/home and the second load_ini used a cleared path. */
        config_parse_argv(&cfg, argc, argv, err, sizeof(err));
    }
    if (cfg.offline)
        return offline_job(&cfg);
    if (config_validate(&cfg, err, sizeof(err)) != 0) {
        info("INFO %s", err);
        usage();
        return 2;
    }
    mkdir_p(cfg.home);
    jail_init(&jail, cfg.allow_path, cfg.allow_bin_extra);
    if (load_key_or_none(&cfg, key, &have_key) != 0)
        return 2;
    info("INFO airc-moot-thin %s nick=%s jail=%s ptr=%d", AIRC_THIN_VERSION, cfg.nick, cfg.allow_path, (int)sizeof(void *));
    if (cfg.once)
        return session(&cfg, &jail, key, have_key) == 0 ? 0 : 1;
    {
        int backoff = 1000;
        for (;;) {
            rc = session(&cfg, &jail, key, have_key);
            info("INFO session end rc=%d", rc);
            info("INFO reconnect in %d ms", backoff);
            Sleep(backoff);
            backoff *= 2;
            if (backoff > 60000)
                backoff = 60000;
        }
    }
}
