#include "pair.h"
#include "aes256gcm.h"

int pin_ok(const char *p)
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

int pair_wrap_key(const char *pin, const char *pair_id, const char *channel,
                  const char *moot_id, uint8_t key[32])
{
    char buf[256];
    char pid[32], ch[64], mid[32];
    if (!pin_ok(pin) || !msgid_ok(pair_id) || !msgid_ok(moot_id) || !channel_ok(channel))
        return -1;
    str_lower_copy(pid, pair_id, sizeof(pid));
    str_lower_copy(ch, channel, sizeof(ch));
    str_lower_copy(mid, moot_id, sizeof(mid));
    _snprintf(buf, sizeof(buf), "airc-pin-v1|%s|%s|%s|%s", pin, pid, ch, mid);
    sha256((const uint8_t *)buf, (int)strlen(buf), key);
    return 0;
}

int pair_random_id(char out[ID_MAX + 1])
{
    uint8_t raw[8];
    if (random_bytes(raw, 8) != 0)
        return -1;
    hex_encode(raw, 8, out, ID_MAX + 1);
    return 0;
}

int pair_random_pin(char out[8])
{
    uint8_t raw[4];
    unsigned n;
    if (random_bytes(raw, 4) != 0)
        return -1;
    n = ((unsigned)raw[0] << 24) | ((unsigned)raw[1] << 16) | ((unsigned)raw[2] << 8) | (unsigned)raw[3];
    n %= 1000000u;
    _snprintf(out, 8, "%06u", n);
    return 0;
}

int parse_pair_line(const char *body, PairLine *out)
{
    char ver[8], verb[12], moot[24], pair[24], extra[400];
    int n;
    memset(out, 0, sizeof(*out));
    extra[0] = 0;
    if (!body || strncmp(body, "PAIR v1 ", 8) != 0)
        return -1;
    n = sscanf(body, "PAIR %7s %11s %23s %23s %399s", ver, verb, moot, pair, extra);
    if (n < 4 || strcmp(ver, "v1") != 0)
        return -1;
    if (strcmp(verb, "OFFER") != 0 && strcmp(verb, "HELLO") != 0 &&
        strcmp(verb, "GRANT") != 0 && strcmp(verb, "ACK") != 0)
        return -1;
    if (!msgid_ok(moot) || !msgid_ok(pair))
        return -1;
    strncpy(out->verb, verb, sizeof(out->verb) - 1);
    strncpy(out->moot_id, moot, sizeof(out->moot_id) - 1);
    strncpy(out->pair_id, pair, sizeof(out->pair_id) - 1);
    strncpy(out->extra, extra, sizeof(out->extra) - 1);
    return 0;
}

void pair_offer_line(const char *moot_id, const char *pair_id, unsigned long expires,
                     char *out, int outlen)
{
    _snprintf(out, outlen, "PAIR v1 OFFER %s %s %lu", moot_id, pair_id, expires);
}

void pair_ack_line(const char *moot_id, const char *pair_id, char *out, int outlen)
{
    _snprintf(out, outlen, "PAIR v1 ACK %s %s", moot_id, pair_id);
}

void chair_invite_line(const char *pin, const char *channel, const char *moot_id,
                       const char *host, int port, char *out, int outlen)
{
    const char *h;
    if (!out || outlen <= 0)
        return;
    out[0] = 0;
    h = (host && host[0]) ? host : "irc.ntsa.uk";
    if (port > 0 && port != 6697)
        _snprintf(out, outlen, "airc-moot-thin.exe --pin %s --channel \"%s\" --moot %s --host %s --port %d",
                  pin ? pin : "", channel ? channel : "", moot_id ? moot_id : "", h, port);
    else
        _snprintf(out, outlen, "airc-moot-thin.exe --pin %s --channel \"%s\" --moot %s --host %s",
                  pin ? pin : "", channel ? channel : "", moot_id ? moot_id : "", h);
}

void chair_print_banner(const char *pin, const char *channel, const char *moot_id,
                        const char *host, int port)
{
    char invite[LINE_MAX];
    chair_invite_line(pin, channel, moot_id, host, port, invite, sizeof(invite));
    info("INFO PIN %s   moot=%s   channel=%s   expires 10m",
         pin ? pin : "", moot_id ? moot_id : "", channel ? channel : "");
    info("INFO copy-paste thin (expires 10m):");
    info("%s", invite);
}

static void pair_hello_aad(const char *channel, const char *moot_id, const char *pair_id,
                           char *out, int outlen)
{
    char a[64], b[32], c[32];
    str_lower_copy(a, channel, sizeof(a));
    str_lower_copy(b, moot_id, sizeof(b));
    str_lower_copy(c, pair_id, sizeof(c));
    _snprintf(out, outlen, "%s|%s|%s|pair-hello-v1", a, b, c);
}

static void pair_grant_aad(const char *channel, const char *moot_id, const char *pair_id,
                           const char *thin_nick, char *out, int outlen)
{
    char a[64], b[32], c[32], d[40];
    str_lower_copy(a, channel, sizeof(a));
    str_lower_copy(b, moot_id, sizeof(b));
    str_lower_copy(c, pair_id, sizeof(c));
    str_lower_copy(d, thin_nick, sizeof(d));
    _snprintf(out, outlen, "%s|%s|%s|%s|pair-grant-v1", a, b, c, d);
}

static int pair_seal(const uint8_t wrap[32], const char *aad, const uint8_t *pt, int pt_len,
                     uint8_t *out, int outcap, int *out_len)
{
    uint8_t nonce[12];
    int clen = 0;
    if (outcap < 12 + pt_len + 16)
        return -1;
    if (random_bytes(nonce, 12) != 0)
        return -1;
    memcpy(out, nonce, 12);
    if (aes256gcm_encrypt(wrap, nonce, (const uint8_t *)aad, (int)strlen(aad),
                          pt, pt_len, out + 12, outcap - 12, &clen) != 0)
        return -1;
    *out_len = 12 + clen;
    return 0;
}

static int pair_open(const uint8_t wrap[32], const char *aad, const uint8_t *blob, int blob_len,
                     uint8_t *out, int outcap, int *out_len)
{
    if (blob_len < 12 + 16)
        return -1;
    return aes256gcm_decrypt(wrap, blob, (const uint8_t *)aad, (int)strlen(aad),
                             blob + 12, blob_len - 12, out, outcap, out_len);
}

int pair_hello_seal(const uint8_t wrap[32], const char *channel, const char *moot_id,
                    const char *pair_id, const char *nick, uint8_t *out, int outcap, int *out_len)
{
    char aad[AAD_MAX], pt[160];
    if (!nick_ok(nick))
        return -1;
    pair_hello_aad(channel, moot_id, pair_id, aad, sizeof(aad));
    _snprintf(pt, sizeof(pt), "{\"v\":1,\"op\":\"hello\",\"nick\":\"%s\"}", nick);
    return pair_seal(wrap, aad, (uint8_t *)pt, (int)strlen(pt), out, outcap, out_len);
}

int pair_hello_open(const uint8_t wrap[32], const char *channel, const char *moot_id,
                    const char *pair_id, const uint8_t *blob, int blob_len,
                    char *nick, int nickcap)
{
    char aad[AAD_MAX];
    uint8_t pt[192];
    int pn = 0;
    char op[16];
    pair_hello_aad(channel, moot_id, pair_id, aad, sizeof(aad));
    if (pair_open(wrap, aad, blob, blob_len, pt, sizeof(pt) - 1, &pn) != 0)
        return -1;
    pt[pn] = 0;
    op[0] = 0;
    nick[0] = 0;
    json_get_string((char *)pt, "op", op, sizeof(op));
    json_get_string((char *)pt, "nick", nick, nickcap);
    if (strcmp(op, "hello") != 0 || !nick_ok(nick))
        return -1;
    return 0;
}

int pair_grant_seal(const uint8_t wrap[32], const char *channel, const char *moot_id,
                    const char *pair_id, const char *thin_nick, const char *chair_nick,
                    const uint8_t psk[32], uint8_t *out, int outcap, int *out_len)
{
    char aad[AAD_MAX], pt[256], hex[72];
    if (!nick_ok(thin_nick) || !nick_ok(chair_nick) || !msgid_ok(moot_id))
        return -1;
    hex_encode(psk, 32, hex, sizeof(hex));
    pair_grant_aad(channel, moot_id, pair_id, thin_nick, aad, sizeof(aad));
    _snprintf(pt, sizeof(pt),
              "{\"v\":1,\"op\":\"grant\",\"psk\":\"%s\",\"chair\":\"%s\",\"moot\":\"%s\"}",
              hex, chair_nick, moot_id);
    return pair_seal(wrap, aad, (uint8_t *)pt, (int)strlen(pt), out, outcap, out_len);
}

int pair_grant_open(const uint8_t wrap[32], const char *channel, const char *moot_id,
                    const char *pair_id, const char *thin_nick, const uint8_t *blob, int blob_len,
                    uint8_t psk[32], char *chair, int chaircap, char *moot_out, int mootcap)
{
    char aad[AAD_MAX];
    uint8_t pt[320];
    int pn = 0;
    char op[16], hex[80], moot[24];
    pair_grant_aad(channel, moot_id, pair_id, thin_nick, aad, sizeof(aad));
    if (pair_open(wrap, aad, blob, blob_len, pt, sizeof(pt) - 1, &pn) != 0)
        return -1;
    pt[pn] = 0;
    op[0] = 0;
    hex[0] = 0;
    chair[0] = 0;
    moot[0] = 0;
    json_get_string((char *)pt, "op", op, sizeof(op));
    json_get_string((char *)pt, "psk", hex, sizeof(hex));
    json_get_string((char *)pt, "chair", chair, chaircap);
    json_get_string((char *)pt, "moot", moot, sizeof(moot));
    if (strcmp(op, "grant") != 0 || !nick_ok(chair) || hex_decode(hex, psk, 32) != 32)
        return -1;
    if (moot[0] && !str_ieq(moot, moot_id))
        return -1;
    if (moot_out && mootcap > 0) {
        strncpy(moot_out, moot[0] ? moot : moot_id, mootcap - 1);
        moot_out[mootcap - 1] = 0;
    }
    return 0;
}

int save_connector_key(const char *path, const uint8_t key[32])
{
    return write_file(path, key, 32);
}

void pair_sess_clear_secrets(PairSess *ps)
{
    if (!ps)
        return;
    memset(ps->pin, 0, sizeof(ps->pin));
    memset(ps->wrap, 0, sizeof(ps->wrap));
    ps->have_wrap = 0;
}
