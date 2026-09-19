#include "util.h"

void info(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    vprintf(fmt, ap);
    va_end(ap);
    fputc('\n', stdout);
    fflush(stdout);
}

char *xstrdup(const char *s)
{
    size_t n;
    char *p;
    if (!s)
        s = "";
    n = strlen(s) + 1;
    p = (char *)malloc(n);
    if (!p)
        return NULL;
    memcpy(p, s, n);
    return p;
}

int str_ieq(const char *a, const char *b)
{
    if (!a || !b)
        return 0;
    while (*a && *b) {
        if (tolower((unsigned char)*a) != tolower((unsigned char)*b))
            return 0;
        a++;
        b++;
    }
    return *a == *b;
}

void str_lower_copy(char *dst, const char *src, int dstlen)
{
    int i = 0;
    if (dstlen <= 0)
        return;
    while (src[i] && i < dstlen - 1) {
        dst[i] = (char)tolower((unsigned char)src[i]);
        i++;
    }
    dst[i] = 0;
}

int nick_ok(const char *n)
{
    int i;
    unsigned char c;
    if (!n || !n[0] || strlen(n) > 32)
        return 0;
    c = (unsigned char)n[0];
    if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || c == '[' || c == ']' || c == '^' || c == '`' || c == '{' || c == '|' || c == '}'))
        return 0;
    for (i = 1; n[i]; i++) {
        c = (unsigned char)n[i];
        if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '[' || c == ']' || c == '^' || c == '`' || c == '{' || c == '|' || c == '}' || c == '_' || c == '-'))
            return 0;
    }
    return 1;
}

int msgid_ok(const char *id)
{
    int i;
    if (!id || strlen(id) != 16)
        return 0;
    for (i = 0; i < 16; i++) {
        char c = id[i];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')))
            return 0;
    }
    return 1;
}

int channel_ok(const char *c)
{
    if (!c || c[0] != '#' || strchr(c, '|') || strlen(c) < 2 || strlen(c) > 50)
        return 0;
    return 1;
}

void hex_encode(const uint8_t *in, int n, char *out, int outlen)
{
    static const char *hexd = "0123456789abcdef";
    int i;
    if (outlen < n * 2 + 1)
        n = (outlen - 1) / 2;
    for (i = 0; i < n; i++) {
        out[i * 2] = hexd[(in[i] >> 4) & 0xf];
        out[i * 2 + 1] = hexd[in[i] & 0xf];
    }
    out[n * 2] = 0;
}

static int hex_nibble(char c)
{
    if (c >= '0' && c <= '9')
        return c - '0';
    if (c >= 'a' && c <= 'f')
        return c - 'a' + 10;
    if (c >= 'A' && c <= 'F')
        return c - 'A' + 10;
    return -1;
}

int hex_decode(const char *hex, uint8_t *out, int outlen)
{
    int n = (int)strlen(hex);
    int i;
    if (n % 2)
        return -1;
    n /= 2;
    if (n > outlen)
        return -1;
    for (i = 0; i < n; i++) {
        int hi = hex_nibble(hex[i * 2]);
        int lo = hex_nibble(hex[i * 2 + 1]);
        if (hi < 0 || lo < 0)
            return -1;
        out[i] = (uint8_t)((hi << 4) | lo);
    }
    return n;
}

static const char b64tab[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

int b64_encode(const uint8_t *in, int n, char *out, int outlen)
{
    int i = 0, o = 0;
    while (i < n) {
        int rem = n - i;
        unsigned v = ((unsigned)in[i]) << 16;
        if (rem > 1)
            v |= ((unsigned)in[i + 1]) << 8;
        if (rem > 2)
            v |= (unsigned)in[i + 2];
        if (o + 5 > outlen)
            return -1;
        out[o++] = b64tab[(v >> 18) & 63];
        out[o++] = b64tab[(v >> 12) & 63];
        out[o++] = (rem > 1) ? b64tab[(v >> 6) & 63] : '=';
        out[o++] = (rem > 2) ? b64tab[v & 63] : '=';
        i += 3;
    }
    out[o] = 0;
    return o;
}

int b64_decode(const char *in, uint8_t *out, int outlen)
{
    int val[256];
    int i, n = 0, o = 0, pad = 0;
    unsigned acc = 0;
    int bits = 0;
    memset(val, -1, sizeof(val));
    for (i = 0; i < 64; i++)
        val[(unsigned char)b64tab[i]] = i;
    val[(unsigned char)'='] = 0;
    for (i = 0; in[i]; i++) {
        unsigned char c = (unsigned char)in[i];
        if (c == '\r' || c == '\n' || c == ' ')
            continue;
        if (c == '=') {
            pad++;
            acc <<= 6;
            bits += 6;
        } else {
            if (val[c] < 0 || pad)
                return -1;
            acc = (acc << 6) | (unsigned)val[c];
            bits += 6;
        }
        if (bits >= 8) {
            bits -= 8;
            if (pad && bits < 8) {
                /* leftover from padding — drop */
            } else if (!pad || bits >= 0) {
                if (o >= outlen)
                    return -1;
                if (!(pad && bits < 8 && c == '=')) {
                    /* handled below */
                }
            }
            if (bits >= 0) {
                uint8_t byte = (uint8_t)((acc >> bits) & 0xff);
                /* skip bytes that exist only because of padding */
                int emit = 1;
                if (in[i] == '=' && bits != 0 && pad)
                    emit = 0;
                if (emit) {
                    if (o >= outlen)
                        return -1;
                    out[o++] = byte;
                    n++;
                }
            }
        }
    }
    /* Simpler second pass: standard decode */
    {
        int len = (int)strlen(in);
        int j = 0;
        uint8_t tmp[4];
        int t = 0;
        o = 0;
        pad = 0;
        for (i = 0; i < len; i++) {
            unsigned char c = (unsigned char)in[i];
            int v;
            if (c == '\r' || c == '\n' || c == ' ')
                continue;
            if (c == '=') {
                tmp[t++] = 0;
                pad++;
            } else {
                v = val[c];
                if (v < 0 || pad)
                    return -1;
                tmp[t++] = (uint8_t)v;
            }
            if (t == 4) {
                if (o + 3 > outlen)
                    return -1;
                out[o++] = (uint8_t)((tmp[0] << 2) | (tmp[1] >> 4));
                if (pad < 2)
                    out[o++] = (uint8_t)((tmp[1] << 4) | (tmp[2] >> 2));
                if (pad < 1)
                    out[o++] = (uint8_t)((tmp[2] << 6) | tmp[3]);
                t = 0;
            }
            j++;
        }
        if (t != 0)
            return -1;
        return o;
    }
}

/* SHA-256 */
static uint32_t rotr(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }

void sha256(const uint8_t *in, int n, uint8_t out[32])
{
    static const uint32_t K[64] = {
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
    };
    uint32_t h[8] = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    uint8_t block[64];
    uint64_t bitlen = (uint64_t)n * 8ull;
    int off = 0;
    int i;

    while (n - off >= 64) {
        memcpy(block, in + off, 64);
        {
            uint32_t w[64], a, b, c, d, e, f, g, hh, t1, t2;
            for (i = 0; i < 16; i++)
                w[i] = ((uint32_t)block[i * 4] << 24) | ((uint32_t)block[i * 4 + 1] << 16) | ((uint32_t)block[i * 4 + 2] << 8) | block[i * 4 + 3];
            for (i = 16; i < 64; i++) {
                uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
                uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
                w[i] = w[i - 16] + s0 + w[i - 7] + s1;
            }
            a = h[0]; b = h[1]; c = h[2]; d = h[3]; e = h[4]; f = h[5]; g = h[6]; hh = h[7];
            for (i = 0; i < 64; i++) {
                t1 = hh + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ ((~e) & g)) + K[i] + w[i];
                t2 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
                hh = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
            }
            h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
        }
        off += 64;
    }
    {
        int rem = n - off;
        memset(block, 0, 64);
        if (rem)
            memcpy(block, in + off, rem);
        block[rem] = 0x80;
        if (rem >= 56) {
            uint32_t w[64], a, b, c, d, e, f, g, hh, t1, t2;
            for (i = 0; i < 16; i++)
                w[i] = ((uint32_t)block[i * 4] << 24) | ((uint32_t)block[i * 4 + 1] << 16) | ((uint32_t)block[i * 4 + 2] << 8) | block[i * 4 + 3];
            for (i = 16; i < 64; i++) {
                uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
                uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
                w[i] = w[i - 16] + s0 + w[i - 7] + s1;
            }
            a = h[0]; b = h[1]; c = h[2]; d = h[3]; e = h[4]; f = h[5]; g = h[6]; hh = h[7];
            for (i = 0; i < 64; i++) {
                t1 = hh + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ ((~e) & g)) + K[i] + w[i];
                t2 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
                hh = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
            }
            h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
            memset(block, 0, 64);
        }
        block[56] = (uint8_t)(bitlen >> 56);
        block[57] = (uint8_t)(bitlen >> 48);
        block[58] = (uint8_t)(bitlen >> 40);
        block[59] = (uint8_t)(bitlen >> 32);
        block[60] = (uint8_t)(bitlen >> 24);
        block[61] = (uint8_t)(bitlen >> 16);
        block[62] = (uint8_t)(bitlen >> 8);
        block[63] = (uint8_t)bitlen;
        {
            uint32_t w[64], a, b, c, d, e, f, g, hh, t1, t2;
            for (i = 0; i < 16; i++)
                w[i] = ((uint32_t)block[i * 4] << 24) | ((uint32_t)block[i * 4 + 1] << 16) | ((uint32_t)block[i * 4 + 2] << 8) | block[i * 4 + 3];
            for (i = 16; i < 64; i++) {
                uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
                uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
                w[i] = w[i - 16] + s0 + w[i - 7] + s1;
            }
            a = h[0]; b = h[1]; c = h[2]; d = h[3]; e = h[4]; f = h[5]; g = h[6]; hh = h[7];
            for (i = 0; i < 64; i++) {
                t1 = hh + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ ((~e) & g)) + K[i] + w[i];
                t2 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
                hh = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
            }
            h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
        }
    }
    for (i = 0; i < 8; i++) {
        out[i * 4] = (uint8_t)(h[i] >> 24);
        out[i * 4 + 1] = (uint8_t)(h[i] >> 16);
        out[i * 4 + 2] = (uint8_t)(h[i] >> 8);
        out[i * 4 + 3] = (uint8_t)h[i];
    }
}

int random_bytes(uint8_t *p, int n)
{
    HCRYPTPROV h = 0;
    int ok;
    if (!CryptAcquireContextA(&h, NULL, NULL, PROV_RSA_FULL, CRYPT_VERIFYCONTEXT))
        return -1;
    ok = CryptGenRandom(h, (DWORD)n, p) ? 0 : -1;
    CryptReleaseContext(h, 0);
    return ok;
}

int read_file(const char *path, uint8_t *buf, int cap, int *out_n)
{
    HANDLE h;
    DWORD got = 0;
    h = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE)
        return -1;
    if (!ReadFile(h, buf, (DWORD)cap, &got, NULL)) {
        CloseHandle(h);
        return -1;
    }
    CloseHandle(h);
    *out_n = (int)got;
    return 0;
}

int write_file(const char *path, const uint8_t *buf, int n)
{
    HANDLE h;
    DWORD put = 0;
    h = CreateFileA(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE)
        return -1;
    if (!WriteFile(h, buf, (DWORD)n, &put, NULL) || (int)put != n) {
        CloseHandle(h);
        return -1;
    }
    CloseHandle(h);
    return 0;
}

int mkdir_p(const char *path)
{
    char tmp[MAX_PATH];
    int i, n;
    strncpy(tmp, path, MAX_PATH - 1);
    tmp[MAX_PATH - 1] = 0;
    n = (int)strlen(tmp);
    for (i = 3; i < n; i++) {
        if (tmp[i] == '\\' || tmp[i] == '/') {
            char c = tmp[i];
            tmp[i] = 0;
            CreateDirectoryA(tmp, NULL);
            tmp[i] = c;
        }
    }
    CreateDirectoryA(tmp, NULL);
    return 0;
}

const char *path_basename(const char *p)
{
    const char *s = p;
    const char *b = p;
    while (*s) {
        if (*s == '\\' || *s == '/')
            b = s + 1;
        s++;
    }
    return b;
}

int json_escape(const char *s, char *out, int outlen)
{
    int o = 0;
    if (!s)
        s = "";
    while (*s) {
        unsigned char c = (unsigned char)*s++;
        const char *rep = NULL;
        char hex[8];
        if (c == '"')
            rep = "\\\"";
        else if (c == '\\')
            rep = "\\\\";
        else if (c == '\n')
            rep = "\\n";
        else if (c == '\r')
            rep = "\\r";
        else if (c == '\t')
            rep = "\\t";
        else if (c < 0x20) {
            sprintf(hex, "\\u%04x", c);
            rep = hex;
        }
        if (rep) {
            int k = (int)strlen(rep);
            if (o + k >= outlen)
                return -1;
            memcpy(out + o, rep, k);
            o += k;
        } else {
            if (o + 1 >= outlen)
                return -1;
            out[o++] = (char)c;
        }
    }
    out[o] = 0;
    return o;
}

static const char *json_find_key(const char *json, const char *key)
{
    char pat[80];
    const char *p;
    sprintf(pat, "\"%s\"", key);
    p = json;
    while ((p = strstr(p, pat)) != NULL) {
        const char *q = p + strlen(pat);
        while (*q == ' ' || *q == '\t' || *q == '\n' || *q == '\r')
            q++;
        if (*q == ':')
            return q + 1;
        p++;
    }
    return NULL;
}

int json_get_string(const char *json, const char *key, char *out, int outlen)
{
    const char *p = json_find_key(json, key);
    int o = 0;
    if (!p)
        return -1;
    while (*p == ' ' || *p == '\t')
        p++;
    if (*p != '"')
        return -1;
    p++;
    while (*p && *p != '"') {
        if (*p == '\\' && p[1]) {
            p++;
            if (o + 1 >= outlen)
                return -1;
            if (*p == 'n')
                out[o++] = '\n';
            else if (*p == 'r')
                out[o++] = '\r';
            else if (*p == 't')
                out[o++] = '\t';
            else
                out[o++] = *p;
            p++;
        } else {
            if (o + 1 >= outlen)
                return -1;
            out[o++] = *p++;
        }
    }
    out[o] = 0;
    return o;
}

int json_get_int(const char *json, const char *key, int *out)
{
    const char *p = json_find_key(json, key);
    if (!p)
        return -1;
    while (*p == ' ' || *p == '\t')
        p++;
    if (!*p || *p == '"' || *p == '{' || *p == '[')
        return -1;
    *out = atoi(p);
    return 0;
}

int json_get_string_array(const char *json, const char *key, char **argv, int maxn)
{
    const char *p = json_find_key(json, key);
    int n = 0;
    if (!p)
        return -1;
    while (*p == ' ' || *p == '\t')
        p++;
    if (*p != '[')
        return -1;
    p++;
    while (*p && *p != ']' && n < maxn) {
        char buf[512];
        int o = 0;
        while (*p == ' ' || *p == '\t' || *p == ',')
            p++;
        if (*p == ']')
            break;
        if (*p != '"')
            return -1;
        p++;
        while (*p && *p != '"') {
            if (*p == '\\' && p[1]) {
                p++;
                if (o < (int)sizeof(buf) - 1)
                    buf[o++] = *p;
                p++;
            } else {
                if (o < (int)sizeof(buf) - 1)
                    buf[o++] = *p;
                p++;
            }
        }
        if (*p == '"')
            p++;
        buf[o] = 0;
        argv[n] = xstrdup(buf);
        n++;
    }
    return n;
}

int dpapi_unprotect(const uint8_t *in, int n, uint8_t *out, int cap, int *out_n)
{
    DATA_BLOB bin, bout;
    bin.cbData = (DWORD)n;
    bin.pbData = (BYTE *)(uintptr_t)in;
    memset(&bout, 0, sizeof(bout));
    if (!CryptUnprotectData(&bin, NULL, NULL, NULL, NULL, 0, &bout))
        return -1;
    if ((int)bout.cbData > cap) {
        LocalFree(bout.pbData);
        return -1;
    }
    memcpy(out, bout.pbData, bout.cbData);
    *out_n = (int)bout.cbData;
    LocalFree(bout.pbData);
    return 0;
}
