#include "util.h"
#include "config.h"
#include "jail.h"
#include "moot.h"
#include "dumb_job.h"
#include "aes256gcm.h"
#include "irc_tls.h"
#include "pair.h"

#include <time.h>

/* Keep in sync with VERSION */
#define AIRC_THIN_VERSION "0.2.1"

static void usage(void)
{
    info("airc-moot-thin %s — Win32 ANSI thin moot CLI (not an LLM)", AIRC_THIN_VERSION);
    info("usage: airc-moot-thin.exe          (zero-arg: self-heal + PIN prompt)");
    info("       airc-moot-thin.exe --pin NNNNNN");
    info("       airc-moot-thin.exe --chair  (prints copy-paste thin invite; OPEN; PAIR GRANT)");
    info("       airc-moot-thin.exe --nick N --channel #chan --moot 16hex --home DIR --allow-path DIR --operators nicks");
    info("  [--key PATH] [--config FILE.ini] [--host HOST] [--port N] [--hello TEXT] [--once]");
    info("  --selftest   offline checks, no sockets");
    info("  --offline --from-nick N --job-in job.json [--job-out result.json]");
    info("empty --operators is refused for unattended installs. --key remains the air-gap path.");
    info("Does not claim Windows 95 TLS.");
}

static int load_key_or_none(const ThinConfig *cfg, uint8_t key[32], int *have)
{
    char path[MAX_PATH];
    *have = 0;
    if (config_key_path(cfg, path, MAX_PATH) != 0)
        return 0;
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

static int key_file_present(const ThinConfig *cfg)
{
    char path[MAX_PATH];
    if (config_key_path(cfg, path, MAX_PATH) != 0)
        return 0;
    return GetFileAttributesA(path) != INVALID_FILE_ATTRIBUTES;
}

static int persist_psk(ThinConfig *cfg, const uint8_t key[32])
{
    char dir[MAX_PATH], path[MAX_PATH];
    _snprintf(dir, MAX_PATH, "%s\\dumb", cfg->home);
    mkdir_p(dir);
    if (config_key_path(cfg, path, MAX_PATH) != 0)
        return -1;
    if (save_connector_key(path, key) != 0)
        return -1;
    info("INFO key saved");
    return 0;
}

static int stdin_is_console(void)
{
    DWORD mode = 0;
    return GetConsoleMode(GetStdHandle(STD_INPUT_HANDLE), &mode) ? 1 : 0;
}

static int prompt_pin(char *out, int outlen)
{
    char buf[32];
    int n;
    if (!stdin_is_console())
        return -1;
    printf("Enter PIN: ");
    fflush(stdout);
    if (!fgets(buf, (int)sizeof(buf), stdin))
        return -1;
    n = (int)strlen(buf);
    while (n > 0 && (buf[n - 1] == '\n' || buf[n - 1] == '\r' || buf[n - 1] == ' ' || buf[n - 1] == '\t'))
        buf[--n] = 0;
    if (!pin_ok(buf)) {
        memset(buf, 0, sizeof(buf));
        return -1;
    }
    strncpy(out, buf, outlen - 1);
    out[outlen - 1] = 0;
    memset(buf, 0, sizeof(buf));
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

    /* sibling ini without wipe + self-heal */
    {
        ThinConfig c;
        char *av[3];
        char keep_ini[MAX_PATH];
        _snprintf(keep_ini, MAX_PATH, "%s\\keep.ini", jailp);
        {
            const char *keep_body = "[client]\nnick=keep-me\nchannel=#ops\n";
            write_file(keep_ini, (uint8_t *)keep_body, (int)strlen(keep_body));
        }
        config_defaults(&c);
        config_load_ini(&c, keep_ini, err, sizeof(err));
        av[0] = "airc-moot-thin.exe";
        av[1] = "--once";
        av[2] = NULL;
        config_parse_argv(&c, 2, av, err, sizeof(err));
        config_self_heal_ex(&c, jailp, "WALRUS");
        if (strcmp(c.nick, "keep-me") != 0) {
            info("FAIL sibling ini wiped nick=%s", c.nick);
            fails++;
        } else if (strcmp(c.home, jailp) != 0 || !strstr(c.allow_path, "jail")) {
            info("FAIL self-heal home/jail");
            fails++;
        } else {
            info("INFO sibling ini kept nick=keep-me");
            info("INFO self-heal nick=keep-me home=%s jail=%s", c.home, c.allow_path);
        }
    }

    {
        char n1[40], n2[40], n3[40];
        sanitize_hostname("WALRUS", n1, sizeof(n1));
        sanitize_hostname("2012-BOX", n2, sizeof(n2));
        sanitize_hostname("!!!", n3, sizeof(n3));
        if (strcmp(n1, "walrus") != 0 || strcmp(n2, "n2012-box") != 0 || strcmp(n3, "thin-box") != 0) {
            info("FAIL sanitize %s %s %s", n1, n2, n3);
            fails++;
        } else {
            ThinConfig c;
            config_defaults(&c);
            config_self_heal_ex(&c, jailp, "WALRUS");
            if (strcmp(c.nick, "walrus") != 0 || strcmp(c.hello, "walrus-online") != 0) {
                info("FAIL self-heal hostname nick");
                fails++;
            } else
                info("INFO self-heal nick=walrus home=%s jail=%s", c.home, c.allow_path);
        }
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

    /* PIN wrap vector + HELLO/GRANT roundtrip (no sockets, no live PIN) */
    {
        uint8_t wrap[32], wrap_bad[32], psk[32], psk2[32], blob[512];
        char hex[72], nick[40], chair[40], moot[24];
        int bn = 0;
        const char *want_wrap = "eb596292f71481efcbadb09ff76b893a5513505d58570f1fa7a3904190b40245";
        if (pair_wrap_key("482917", "aabbccddeeff0011", "#ops", "0123456789abcdef", wrap) != 0) {
            info("FAIL pin wrap");
            fails++;
        } else {
            hex_encode(wrap, 32, hex, sizeof(hex));
            if (strcmp(hex, want_wrap) != 0) {
                info("FAIL pin wrap %s", hex);
                fails++;
            } else
                info("INFO pin wrap ok");
        }
        pair_wrap_key("000000", "aabbccddeeff0011", "#ops", "0123456789abcdef", wrap_bad);
        if (pair_hello_seal(wrap, "#ops", "0123456789abcdef", "aabbccddeeff0011", "walrus", blob, sizeof(blob), &bn) != 0 ||
            pair_hello_open(wrap, "#ops", "0123456789abcdef", "aabbccddeeff0011", blob, bn, nick, sizeof(nick)) != 0 ||
            strcmp(nick, "walrus") != 0) {
            info("FAIL pair hello");
            fails++;
        } else if (pair_hello_open(wrap_bad, "#ops", "0123456789abcdef", "aabbccddeeff0011", blob, bn, nick, sizeof(nick)) == 0) {
            info("FAIL pin mismatch accepted");
            fails++;
        } else
            info("INFO pin mismatch refused");
        hex_decode("00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff", psk, 32);
        if (pair_grant_seal(wrap, "#ops", "0123456789abcdef", "aabbccddeeff0011", "walrus", "alice",
                            psk, blob, sizeof(blob), &bn) != 0 ||
            pair_grant_open(wrap, "#ops", "0123456789abcdef", "aabbccddeeff0011", "walrus", blob, bn,
                            psk2, chair, sizeof(chair), moot, sizeof(moot)) != 0) {
            info("FAIL pair grant");
            fails++;
        } else if (memcmp(psk, psk2, 32) != 0 || strcmp(chair, "alice") != 0) {
            info("FAIL pair grant fields");
            fails++;
        } else {
            char ops[64];
            ops[0] = 0;
            operators_add(ops, sizeof(ops), chair);
            if (!operator_allowed(ops, "alice")) {
                info("FAIL pair grant operators");
                fails++;
            } else
                info("INFO pair grant operators=alice");
        }
        {
            char invite[LINE_MAX];
            const char *fix_pin = "482917";
            const char *fix_ch = "#ops";
            const char *fix_moot = "0123456789abcdef";
            chair_invite_line(fix_pin, fix_ch, fix_moot, invite, sizeof(invite));
            if (!strstr(invite, "--pin") || !strstr(invite, "--channel") ||
                !strstr(invite, "--moot") || !strstr(invite, fix_pin) ||
                !strstr(invite, fix_moot) || !strstr(invite, fix_ch) ||
                strstr(invite, "psk") || strstr(invite, "connector.key")) {
                info("FAIL chair invite banner %s", invite);
                fails++;
            } else {
                chair_print_banner(fix_pin, fix_ch, fix_moot);
                info("INFO chair invite banner ok");
            }
        }
        {
            PairLine pl;
            pair_offer_line("0123456789abcdef", "aabbccddeeff0011", 1710000000ul, line, sizeof(line));
            if (parse_pair_line(line, &pl) != 0 || strcmp(pl.verb, "OFFER") != 0 ||
                strcmp(pl.extra, "1710000000") != 0) {
                info("FAIL pair offer parse");
                fails++;
            } else
                info("INFO pair offer parse ok");
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
    moot_open_line("0123456789abcdef", "alice", line, sizeof(line));
    if (strncmp(line, "MOOT v1 OPEN 0123456789abcdef alice floor", 41) != 0) {
        info("FAIL moot open");
        fails++;
    } else
        info("INFO moot OPEN ok");

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

static void src_nick(const char *prefix, char *src, int srccap)
{
    const char *bang = strchr(prefix, '!');
    int n;
    if (bang) {
        n = (int)(bang - prefix);
        if (n > srccap - 1)
            n = srccap - 1;
        memcpy(src, prefix, n);
        src[n] = 0;
    } else {
        strncpy(src, prefix, srccap - 1);
        src[srccap - 1] = 0;
    }
}

static void emit_ready(IrcConn *irc, ThinConfig *cfg, int have_key, const char *live, const char *pinflag)
{
    char capa[512], mjoin[128];
    if (cfg->hello[0])
        say(irc, cfg->channel, cfg->hello);
    capa_line(cfg->nick, cfg->allow_path, have_key, capa, sizeof(capa));
    say(irc, cfg->channel, capa);
    if (msgid_ok(cfg->moot_id)) {
        moot_join_line(cfg->moot_id, mjoin, sizeof(mjoin));
        say(irc, cfg->channel, mjoin);
    }
    info("INFO joined as %s moot=%s pin=%s", live, cfg->moot_id[0] ? cfg->moot_id : "-", pinflag);
}

static void chair_send_offer(IrcConn *irc, ThinConfig *cfg, PairSess *ps)
{
    char openl[192], offer[192];
    moot_open_line(cfg->moot_id, cfg->nick, openl, sizeof(openl));
    say(irc, cfg->channel, openl);
    pair_offer_line(cfg->moot_id, ps->pair_id, ps->expires_unix, offer, sizeof(offer));
    say(irc, cfg->channel, offer);
    ps->last_offer = GetTickCount();
}

static int handle_pair(IrcConn *irc, ThinConfig *cfg, PairSess *ps, uint8_t *key, int *have_key,
                       const char *live, const char *src, const char *body)
{
    PairLine pl;
    if (parse_pair_line(body, &pl) != 0)
        return 0;
    if (ps->role == PAIR_NONE)
        return 0;

    if (ps->role == PAIR_THIN && !ps->done && strcmp(pl.verb, "OFFER") == 0) {
        unsigned long exp = strtoul(pl.extra, NULL, 10);
        unsigned long now = (unsigned long)time(NULL);
        uint8_t blob[512];
        char b64[400], line[LINE_MAX];
        int bn = 0;
        if (exp && now > exp) {
            info("INFO pin expired");
            return 0;
        }
        strncpy(cfg->moot_id, pl.moot_id, sizeof(cfg->moot_id) - 1);
        strncpy(ps->pair_id, pl.pair_id, sizeof(ps->pair_id) - 1);
        ps->expires_unix = exp;
        if (pair_wrap_key(ps->pin, ps->pair_id, cfg->channel, cfg->moot_id, ps->wrap) != 0)
            return 0;
        ps->have_wrap = 1;
        if (pair_hello_seal(ps->wrap, cfg->channel, cfg->moot_id, ps->pair_id, cfg->nick,
                            blob, sizeof(blob), &bn) != 0)
            return 0;
        if (b64_encode(blob, bn, b64, sizeof(b64)) < 0)
            return 0;
        _snprintf(line, sizeof(line), "PAIR v1 HELLO %s %s %s", cfg->moot_id, ps->pair_id, b64);
        say(irc, cfg->channel, line);
        info("INFO pair hello sent");
        return 0;
    }

    if (ps->role == PAIR_CHAIR && !ps->done && strcmp(pl.verb, "HELLO") == 0) {
        uint8_t raw[512];
        char hello_nick[40];
        char b64[400], line[LINE_MAX];
        uint8_t blob[512];
        int rn, bn = 0;
        unsigned long now = (unsigned long)time(NULL);
        if (!str_ieq(pl.moot_id, cfg->moot_id) || !str_ieq(pl.pair_id, ps->pair_id))
            return 0;
        if (now > ps->expires_unix) {
            info("INFO pin expired");
            return 0;
        }
        if (ps->hello_fails >= PAIR_HELLO_MAX_FAIL)
            return 0;
        rn = b64_decode(pl.extra, raw, sizeof(raw));
        if (rn < 0 || pair_hello_open(ps->wrap, cfg->channel, cfg->moot_id, ps->pair_id, raw, rn,
                                      hello_nick, sizeof(hello_nick)) != 0) {
            ps->hello_fails++;
            info("INFO pair hello rejected");
            return 0;
        }
        if (!str_ieq(hello_nick, src)) {
            info("INFO pair hello prefix != nick, drop");
            return 0;
        }
        strncpy(ps->thin_nick, hello_nick, sizeof(ps->thin_nick) - 1);
        if (pair_grant_seal(ps->wrap, cfg->channel, cfg->moot_id, ps->pair_id, hello_nick, cfg->nick,
                            ps->psk, blob, sizeof(blob), &bn) != 0)
            return 0;
        if (b64_encode(blob, bn, b64, sizeof(b64)) < 0)
            return 0;
        _snprintf(line, sizeof(line), "PAIR v1 GRANT %s %s %s", cfg->moot_id, ps->pair_id, b64);
        say(irc, cfg->channel, line);
        ps->done = 1;
        pair_sess_clear_secrets(ps);
        info("INFO pin=ok granted to %s", hello_nick);
        return 1;
    }

    if (ps->role == PAIR_THIN && !ps->done && strcmp(pl.verb, "GRANT") == 0) {
        uint8_t raw[512], psk[32];
        char chair[40], moot[24], ack[128], kpath[MAX_PATH];
        int rn;
        if (!ps->have_wrap)
            return 0;
        if (!str_ieq(pl.pair_id, ps->pair_id))
            return 0;
        rn = b64_decode(pl.extra, raw, sizeof(raw));
        if (rn < 0 || pair_grant_open(ps->wrap, cfg->channel, cfg->moot_id, ps->pair_id, cfg->nick,
                                      raw, rn, psk, chair, sizeof(chair), moot, sizeof(moot)) != 0) {
            info("INFO pin rejected");
            return 0;
        }
        memcpy(ps->psk, psk, 32);
        memcpy(key, psk, 32);
        *have_key = 1;
        ps->have_psk = 1;
        strncpy(ps->chair_nick, chair, sizeof(ps->chair_nick) - 1);
        operators_add(cfg->operators, sizeof(cfg->operators), chair);
        if (config_key_path(cfg, kpath, MAX_PATH) == 0)
            persist_psk(cfg, psk);
        config_write_paired(cfg);
        pair_ack_line(cfg->moot_id, ps->pair_id, ack, sizeof(ack));
        say(irc, cfg->channel, ack);
        ps->done = 1;
        pair_sess_clear_secrets(ps);
        emit_ready(irc, cfg, 1, live, "ok");
        info("INFO pin=ok operators=%s", cfg->operators);
        memset(psk, 0, sizeof(psk));
        return 1;
    }
    return 0;
}

static void handle_privmsg(IrcConn *irc, ThinConfig *cfg, Jail *jail, FragStore *frags,
                           uint8_t *key, int *have_key, PairSess *ps, const char *live_nick,
                           const char *prefix, const char *target, const char *body)
{
    char src[64];
    SealLine sl;
    if (_stricmp(target, cfg->channel) != 0)
        return;
    src_nick(prefix, src, sizeof(src));
    if (handle_pair(irc, cfg, ps, key, have_key, live_nick, src, body))
        return;
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
        if (bn < 0 || !*have_key) {
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

static int session(ThinConfig *cfg, Jail *jail, uint8_t *key, int *have_key, PairSess *ps)
{
    IrcConn *irc;
    char err[256], line[1024], capa[512], mjoin[128];
    char live[NICK_MAX + 8];
    int got_001 = 0, got_join = 0;
    DWORD t0, last_capa;
    FragStore frags;
    int use_tls = (cfg->port == 6697);
    int ready = (ps->role == PAIR_NONE) || (ps->role != PAIR_NONE && ps->done);

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
    if (ps->role == PAIR_CHAIR && !ps->done) {
        chair_send_offer(irc, cfg, ps);
        info("INFO lobby chair waiting for HELLO");
    } else if (ps->role == PAIR_THIN && !ps->done) {
        ps->wait0 = GetTickCount();
        info("INFO lobby waiting for PIN pair");
    } else {
        emit_ready(irc, cfg, *have_key, live, "n/a");
        ready = 1;
    }
    last_capa = GetTickCount();
    capa_line(cfg->nick, cfg->allow_path, *have_key, capa, sizeof(capa));
    if (msgid_ok(cfg->moot_id))
        moot_join_line(cfg->moot_id, mjoin, sizeof(mjoin));
    else
        mjoin[0] = 0;
    for (;;) {
        int r = irc_recv_line(irc, line, sizeof(line), 1000);
        if (ps->role == PAIR_CHAIR && !ps->done) {
            unsigned long nowu = (unsigned long)time(NULL);
            if (nowu > ps->expires_unix) {
                info("INFO pin expired");
                irc_free(irc);
                return 2;
            }
            if ((int)(GetTickCount() - ps->last_offer) >= PAIR_OFFER_MS)
                chair_send_offer(irc, cfg, ps);
            if (ps->hello_fails >= PAIR_HELLO_MAX_FAIL) {
                info("INFO pin expired");
                irc_free(irc);
                return 2;
            }
        }
        if (ps->role == PAIR_THIN && !ps->done) {
            if ((int)(GetTickCount() - ps->wait0) > PAIR_TTL_S * 1000) {
                info("INFO pin expired or rejected");
                irc_free(irc);
                return 2;
            }
        }
        if (ps->done)
            ready = 1;
        if (ready && (int)(GetTickCount() - last_capa) >= CAPA_MS) {
            capa_line(cfg->nick, cfg->allow_path, *have_key, capa, sizeof(capa));
            say(irc, cfg->channel, capa);
            if (msgid_ok(cfg->moot_id)) {
                moot_join_line(cfg->moot_id, mjoin, sizeof(mjoin));
                say(irc, cfg->channel, mjoin);
            }
            last_capa = GetTickCount();
        }
        if (cfg->once && ps->role == PAIR_CHAIR && ps->done) {
            irc_free(irc);
            return 0;
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
            handle_privmsg(irc, cfg, jail, &frags, key, have_key, ps, live, prefix, tgt, body);
        }
    }
    irc_free(irc);
    return 0;
}

static int prepare_chair(ThinConfig *cfg, PairSess *ps, uint8_t *key, int *have_key)
{
    char kpath[MAX_PATH];
    if (!cfg->channel[0])
        strncpy(cfg->channel, PAIR_DEFAULT_CHANNEL, sizeof(cfg->channel) - 1);
    if (!msgid_ok(cfg->moot_id)) {
        if (pair_random_id(cfg->moot_id) != 0)
            return -1;
    }
    if (pair_random_id(ps->pair_id) != 0)
        return -1;
    if (pair_random_pin(ps->pin) != 0)
        return -1;
    strncpy(cfg->pin, ps->pin, sizeof(cfg->pin) - 1);
    ps->role = PAIR_CHAIR;
    ps->expires_unix = (unsigned long)time(NULL) + PAIR_TTL_S;
    if (load_key_or_none(cfg, key, have_key) != 0)
        return -1;
    if (!*have_key) {
        if (random_bytes(key, 32) != 0)
            return -1;
        *have_key = 1;
        if (config_key_path(cfg, kpath, MAX_PATH) == 0)
            persist_psk(cfg, key);
        {
            uint8_t fp[32];
            char hex[72];
            sha256(key, 32, fp);
            hex_encode(fp, 32, hex, sizeof(hex));
            info("INFO keyfp=%s", hex);
        }
    }
    memcpy(ps->psk, key, 32);
    ps->have_psk = 1;
    if (pair_wrap_key(ps->pin, ps->pair_id, cfg->channel, cfg->moot_id, ps->wrap) != 0)
        return -1;
    ps->have_wrap = 1;
    chair_print_banner(ps->pin, cfg->channel, cfg->moot_id);
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
    PairSess ps;
    char paired[MAX_PATH];

    memset(&ps, 0, sizeof(ps));
    config_defaults(&cfg);
    config_exe_dir(cfg.exe_dir, sizeof(cfg.exe_dir));
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

    _snprintf(paired, MAX_PATH, "%s\\dumb\\paired.ini", cfg.exe_dir);
    config_try_load_ini(&cfg, paired);
    if (!cfg.config_path[0]) {
        char sib[MAX_PATH];
        _snprintf(sib, MAX_PATH, "%s\\airc-moot-thin.ini", cfg.exe_dir);
        if (GetFileAttributesA(sib) != INVALID_FILE_ATTRIBUTES)
            strncpy(cfg.config_path, sib, sizeof(cfg.config_path) - 1);
    }
    if (cfg.config_path[0]) {
        if (config_load_ini(&cfg, cfg.config_path, err, sizeof(err)) != 0) {
            info("INFO %s", err);
            return 2;
        }
        /* CLI again so flags win over ini. Do NOT config_defaults here:
         * that wiped nick/home and the second load_ini used a cleared path. */
        config_parse_argv(&cfg, argc, argv, err, sizeof(err));
    }
    config_self_heal(&cfg);

    if (cfg.offline)
        return offline_job(&cfg);

    if (cfg.chair) {
        if (prepare_chair(&cfg, &ps, key, &have_key) != 0) {
            info("INFO chair setup failed");
            return 2;
        }
        cfg.pairing = 1;
    } else if (cfg.pin[0] || (operators_empty(cfg.operators) && !key_file_present(&cfg))) {
        cfg.pairing = 1;
        ps.role = PAIR_THIN;
        if (!cfg.channel[0])
            strncpy(cfg.channel, PAIR_DEFAULT_CHANNEL, sizeof(cfg.channel) - 1);
        if (!cfg.pin[0]) {
            if (prompt_pin(cfg.pin, sizeof(cfg.pin)) != 0) {
                info("INFO missing pin (pass --pin NNNNNN or run from a console)");
                return 2;
            }
        }
        if (!pin_ok(cfg.pin)) {
            info("INFO invalid --pin (6 digits)");
            return 2;
        }
        strncpy(ps.pin, cfg.pin, sizeof(ps.pin) - 1);
        memset(cfg.pin, 0, sizeof(cfg.pin));
    }

    if (config_validate(&cfg, err, sizeof(err)) != 0) {
        info("INFO %s", err);
        return 2;
    }
    mkdir_p(cfg.home);
    mkdir_p(cfg.allow_path);
    jail_init(&jail, cfg.allow_path, cfg.allow_bin_extra);
    if (!cfg.chair && !cfg.pairing) {
        if (load_key_or_none(&cfg, key, &have_key) != 0)
            return 2;
        if (!have_key) {
            info("INFO missing key (pass --key PATH or --pin for pairing)");
            return 2;
        }
    }
    info("INFO airc-moot-thin %s nick=%s jail=%s ptr=%d", AIRC_THIN_VERSION, cfg.nick, cfg.allow_path, (int)sizeof(void *));
    if (cfg.once)
        return session(&cfg, &jail, key, &have_key, &ps) == 0 ? 0 : 1;
    {
        int backoff = 1000;
        for (;;) {
            rc = session(&cfg, &jail, key, &have_key, &ps);
            info("INFO session end rc=%d", rc);
            info("INFO reconnect in %d ms", backoff);
            Sleep(backoff);
            backoff *= 2;
            if (backoff > 60000)
                backoff = 60000;
        }
    }
}
