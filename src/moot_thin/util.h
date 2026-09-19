#ifndef AIRC_UTIL_H
#define AIRC_UTIL_H

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef WINVER
#define WINVER 0x0501
#endif
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0501
#endif
#ifdef UNICODE
#undef UNICODE
#endif
#ifdef _UNICODE
#undef _UNICODE
#endif

#include <windows.h>
#include <wincrypt.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <stdarg.h>
#include <stdint.h>

#ifndef _MSC_VER
#ifndef _snprintf
#define _snprintf snprintf
#endif
#ifndef _stricmp
#define _stricmp strcasecmp
#endif
#ifndef _strnicmp
#define _strnicmp strncasecmp
#endif
#endif

#define RESULT_BYTES_MAX 8192
#define DUMB_CHUNK 300
#define DUMB_MAX_N 64
#define FLOOD_MS 800
#define CAPA_MS 600000
#define BAG_TTL_MS 120000
#define LINE_MAX 512
#define JSON_MAX 16384
#define AAD_MAX 256
#define NICK_MAX 32
#define ID_MAX 16

void info(const char *fmt, ...);
char *xstrdup(const char *s);
int str_ieq(const char *a, const char *b);
void str_lower_copy(char *dst, const char *src, int dstlen);
int nick_ok(const char *n);
int msgid_ok(const char *id);
int channel_ok(const char *c);
void hex_encode(const uint8_t *in, int n, char *out, int outlen);
int hex_decode(const char *hex, uint8_t *out, int outlen);
int b64_encode(const uint8_t *in, int n, char *out, int outlen);
int b64_decode(const char *in, uint8_t *out, int outlen);
void sha256(const uint8_t *in, int n, uint8_t out[32]);
int random_bytes(uint8_t *p, int n);
int read_file(const char *path, uint8_t *buf, int cap, int *out_n);
int write_file(const char *path, const uint8_t *buf, int n);
int mkdir_p(const char *path);
const char *path_basename(const char *p);
int json_escape(const char *s, char *out, int outlen);
int json_get_string(const char *json, const char *key, char *out, int outlen);
int json_get_int(const char *json, const char *key, int *out);
int json_get_string_array(const char *json, const char *key, char **argv, int maxn);
int dpapi_unprotect(const uint8_t *in, int n, uint8_t *out, int cap, int *out_n);

#endif
