#include "aes256gcm.h"

static const uint8_t sbox[256] = {
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16
};

static const uint8_t rcon[11] = {0x00,0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36};

static uint8_t xtime(uint8_t x) { return (uint8_t)((x << 1) ^ ((x & 0x80) ? 0x1b : 0)); }

typedef struct {
    uint8_t rk[15][16];
} aes256_ctx;

static void sub_word(uint8_t *w)
{
    w[0] = sbox[w[0]];
    w[1] = sbox[w[1]];
    w[2] = sbox[w[2]];
    w[3] = sbox[w[3]];
}

static void aes256_init(aes256_ctx *c, const uint8_t key[32])
{
    uint8_t w[60 * 4];
    int i;
    memcpy(w, key, 32);
    for (i = 8; i < 60; i++) {
        uint8_t temp[4];
        memcpy(temp, w + (i - 1) * 4, 4);
        if (i % 8 == 0) {
            uint8_t t = temp[0];
            temp[0] = temp[1];
            temp[1] = temp[2];
            temp[2] = temp[3];
            temp[3] = t;
            sub_word(temp);
            temp[0] ^= rcon[i / 8];
        } else if (i % 8 == 4) {
            sub_word(temp);
        }
        w[i * 4 + 0] = (uint8_t)(w[(i - 8) * 4 + 0] ^ temp[0]);
        w[i * 4 + 1] = (uint8_t)(w[(i - 8) * 4 + 1] ^ temp[1]);
        w[i * 4 + 2] = (uint8_t)(w[(i - 8) * 4 + 2] ^ temp[2]);
        w[i * 4 + 3] = (uint8_t)(w[(i - 8) * 4 + 3] ^ temp[3]);
    }
    for (i = 0; i < 15; i++)
        memcpy(c->rk[i], w + i * 16, 16);
}

static void mix_columns(uint8_t *s)
{
    int c;
    for (c = 0; c < 4; c++) {
        uint8_t *col = s + c * 4;
        uint8_t a0 = col[0], a1 = col[1], a2 = col[2], a3 = col[3];
        col[0] = (uint8_t)(xtime(a0) ^ xtime(a1) ^ a1 ^ a2 ^ a3);
        col[1] = (uint8_t)(a0 ^ xtime(a1) ^ xtime(a2) ^ a2 ^ a3);
        col[2] = (uint8_t)(a0 ^ a1 ^ xtime(a2) ^ xtime(a3) ^ a3);
        col[3] = (uint8_t)(xtime(a0) ^ a0 ^ a1 ^ a2 ^ xtime(a3));
    }
}

static void aes256_encrypt_block(const aes256_ctx *c, const uint8_t in[16], uint8_t out[16])
{
    uint8_t s[16];
    int r, i;
    memcpy(s, in, 16);
    for (i = 0; i < 16; i++)
        s[i] ^= c->rk[0][i];
    for (r = 1; r < 14; r++) {
        uint8_t t[16];
        for (i = 0; i < 16; i++)
            s[i] = sbox[s[i]];
        /* ShiftRows — state is column-major: s[r+4c] */
        t[0] = s[0]; t[4] = s[4]; t[8] = s[8]; t[12] = s[12];
        t[1] = s[5]; t[5] = s[9]; t[9] = s[13]; t[13] = s[1];
        t[2] = s[10]; t[6] = s[14]; t[10] = s[2]; t[14] = s[6];
        t[3] = s[15]; t[7] = s[3]; t[11] = s[7]; t[15] = s[11];
        memcpy(s, t, 16);
        mix_columns(s);
        for (i = 0; i < 16; i++)
            s[i] ^= c->rk[r][i];
    }
    {
        uint8_t t[16];
        for (i = 0; i < 16; i++)
            s[i] = sbox[s[i]];
        t[0] = s[0]; t[4] = s[4]; t[8] = s[8]; t[12] = s[12];
        t[1] = s[5]; t[5] = s[9]; t[9] = s[13]; t[13] = s[1];
        t[2] = s[10]; t[6] = s[14]; t[10] = s[2]; t[14] = s[6];
        t[3] = s[15]; t[7] = s[3]; t[11] = s[7]; t[15] = s[11];
        memcpy(s, t, 16);
        for (i = 0; i < 16; i++)
            s[i] ^= c->rk[14][i];
    }
    memcpy(out, s, 16);
}

static void xor16(uint8_t *a, const uint8_t *b)
{
    int i;
    for (i = 0; i < 16; i++)
        a[i] ^= b[i];
}

static void gf_mult(const uint8_t *x, const uint8_t *y, uint8_t *z)
{
    uint8_t v[16];
    int i, j;
    memset(z, 0, 16);
    memcpy(v, y, 16);
    for (i = 0; i < 16; i++) {
        for (j = 7; j >= 0; j--) {
            int lsb;
            if (x[i] & (1 << j))
                xor16(z, v);
            lsb = v[15] & 1;
            {
                int k;
                for (k = 15; k > 0; k--)
                    v[k] = (uint8_t)((v[k] >> 1) | ((v[k - 1] & 1) << 7));
                v[0] >>= 1;
            }
            if (lsb)
                v[0] ^= 0xe1;
        }
    }
}

static void ghash(const uint8_t H[16], const uint8_t *aad, int aad_len,
                  const uint8_t *ct, int ct_len, uint8_t s[16])
{
    uint8_t y[16], tmp[16], lenblk[16];
    int i;
    memset(y, 0, 16);
    for (i = 0; i < aad_len; i += 16) {
        int n = aad_len - i;
        memset(tmp, 0, 16);
        memcpy(tmp, aad + i, n > 16 ? 16 : n);
        xor16(y, tmp);
        gf_mult(y, H, tmp);
        memcpy(y, tmp, 16);
    }
    for (i = 0; i < ct_len; i += 16) {
        int n = ct_len - i;
        memset(tmp, 0, 16);
        memcpy(tmp, ct + i, n > 16 ? 16 : n);
        xor16(y, tmp);
        gf_mult(y, H, tmp);
        memcpy(y, tmp, 16);
    }
    memset(lenblk, 0, 16);
    {
        uint64_t al = (uint64_t)aad_len * 8ull;
        uint64_t cl = (uint64_t)ct_len * 8ull;
        lenblk[0] = (uint8_t)(al >> 56);
        lenblk[1] = (uint8_t)(al >> 48);
        lenblk[2] = (uint8_t)(al >> 40);
        lenblk[3] = (uint8_t)(al >> 32);
        lenblk[4] = (uint8_t)(al >> 24);
        lenblk[5] = (uint8_t)(al >> 16);
        lenblk[6] = (uint8_t)(al >> 8);
        lenblk[7] = (uint8_t)al;
        lenblk[8] = (uint8_t)(cl >> 56);
        lenblk[9] = (uint8_t)(cl >> 48);
        lenblk[10] = (uint8_t)(cl >> 40);
        lenblk[11] = (uint8_t)(cl >> 32);
        lenblk[12] = (uint8_t)(cl >> 24);
        lenblk[13] = (uint8_t)(cl >> 16);
        lenblk[14] = (uint8_t)(cl >> 8);
        lenblk[15] = (uint8_t)cl;
    }
    xor16(y, lenblk);
    gf_mult(y, H, tmp);
    memcpy(s, tmp, 16);
}

static void inc32(uint8_t ctr[16])
{
    int i;
    for (i = 15; i >= 12; i--) {
        ctr[i]++;
        if (ctr[i] != 0)
            break;
    }
}

static void gctr(const aes256_ctx *aes, const uint8_t icb[16], const uint8_t *in, int inlen, uint8_t *out)
{
    uint8_t ctr[16], ks[16];
    int i, n;
    memcpy(ctr, icb, 16);
    i = 0;
    while (i < inlen) {
        n = inlen - i;
        if (n > 16)
            n = 16;
        aes256_encrypt_block(aes, ctr, ks);
        {
            int k;
            for (k = 0; k < n; k++)
                out[i + k] = (uint8_t)(in[i + k] ^ ks[k]);
        }
        inc32(ctr);
        i += n;
    }
}

int aes256gcm_encrypt(const uint8_t key[32], const uint8_t nonce[12],
                      const uint8_t *aad, int aad_len,
                      const uint8_t *pt, int pt_len,
                      uint8_t *out, int outcap, int *out_len)
{
    aes256_ctx aes;
    uint8_t H[16], J0[16], icb[16], S[16], tag[16], zero[16];
    if (pt_len + 16 > outcap)
        return -1;
    aes256_init(&aes, key);
    memset(zero, 0, 16);
    aes256_encrypt_block(&aes, zero, H);
    memset(J0, 0, 16);
    memcpy(J0, nonce, 12);
    J0[15] = 1;
    memcpy(icb, J0, 16);
    inc32(icb);
    gctr(&aes, icb, pt, pt_len, out);
    ghash(H, aad, aad_len, out, pt_len, S);
    gctr(&aes, J0, S, 16, tag);
    memcpy(out + pt_len, tag, 16);
    *out_len = pt_len + 16;
    return 0;
}

int aes256gcm_decrypt(const uint8_t key[32], const uint8_t nonce[12],
                      const uint8_t *aad, int aad_len,
                      const uint8_t *ct_and_tag, int ct_and_tag_len,
                      uint8_t *out, int outcap, int *out_len)
{
    aes256_ctx aes;
    uint8_t H[16], J0[16], icb[16], S[16], tag[16], expect[16], zero[16];
    int ct_len;
    int i, diff;
    if (ct_and_tag_len < 16)
        return -1;
    ct_len = ct_and_tag_len - 16;
    if (ct_len > outcap)
        return -1;
    aes256_init(&aes, key);
    memset(zero, 0, 16);
    aes256_encrypt_block(&aes, zero, H);
    memset(J0, 0, 16);
    memcpy(J0, nonce, 12);
    J0[15] = 1;
    memcpy(expect, ct_and_tag + ct_len, 16);
    ghash(H, aad, aad_len, ct_and_tag, ct_len, S);
    gctr(&aes, J0, S, 16, tag);
    diff = 0;
    for (i = 0; i < 16; i++)
        diff |= tag[i] ^ expect[i];
    if (diff)
        return -1;
    memcpy(icb, J0, 16);
    inc32(icb);
    gctr(&aes, icb, ct_and_tag, ct_len, out);
    *out_len = ct_len;
    return 0;
}

void dumb_aad(const char *channel, const char *to_nick, const char *from_nick,
              const char *msg_id, char *out, int outlen)
{
    char a[64], b[64], c[64], d[64];
    str_lower_copy(a, channel, sizeof(a));
    str_lower_copy(b, to_nick, sizeof(b));
    str_lower_copy(c, from_nick, sizeof(c));
    str_lower_copy(d, msg_id, sizeof(d));
    sprintf(out, "%s|%s|%s|%s|dumb-v1", a, b, c, d);
    (void)outlen;
}

int dumb_seal(const uint8_t key[32], const char *channel, const char *to_nick,
              const char *from_nick, const char *msg_id,
              const uint8_t *pt, int pt_len, uint8_t *out, int outcap, int *out_len)
{
    uint8_t nonce[12];
    char aad[AAD_MAX];
    int clen = 0;
    if (outcap < 12 + pt_len + 16)
        return -1;
    if (random_bytes(nonce, 12) != 0)
        return -1;
    dumb_aad(channel, to_nick, from_nick, msg_id, aad, sizeof(aad));
    memcpy(out, nonce, 12);
    if (aes256gcm_encrypt(key, nonce, (uint8_t *)aad, (int)strlen(aad), pt, pt_len, out + 12, outcap - 12, &clen) != 0)
        return -1;
    *out_len = 12 + clen;
    return 0;
}

int dumb_open(const uint8_t key[32], const char *channel, const char *to_nick,
              const char *from_nick, const char *msg_id,
              const uint8_t *blob, int blob_len, uint8_t *out, int outcap, int *out_len)
{
    char aad[AAD_MAX];
    if (blob_len < 12 + 16)
        return -1;
    dumb_aad(channel, to_nick, from_nick, msg_id, aad, sizeof(aad));
    return aes256gcm_decrypt(key, blob, (uint8_t *)aad, (int)strlen(aad), blob + 12, blob_len - 12, out, outcap, out_len);
}
