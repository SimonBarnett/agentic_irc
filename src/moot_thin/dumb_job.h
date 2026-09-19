#ifndef AIRC_DUMB_JOB_H
#define AIRC_DUMB_JOB_H

#include "util.h"
#include "jail.h"
#include "config.h"

typedef struct SealLine {
    char to_nick[NICK_MAX + 4];
    char from_nick[NICK_MAX + 4];
    char msg_id[ID_MAX + 4];
    int i, n;
    char chunk[DUMB_CHUNK + 8];
} SealLine;

typedef struct FragStore {
    struct {
        char from[NICK_MAX + 4];
        char id[ID_MAX + 4];
        int n;
        int have;
        DWORD t0;
        char *parts[DUMB_MAX_N];
        int used;
    } bags[8];
} FragStore;

int parse_dumb_line(const char *body, SealLine *out);
void frag_init(FragStore *s);
char *frag_add(FragStore *s, const SealLine *ln); /* malloc b64 payload or NULL */

int load_connector_key(const char *path, uint8_t key[32]);
int run_job_json(const char *job_json, const char *from_nick, const ThinConfig *cfg, Jail *jail,
                 char *result, int resultcap);
int dumb_irc_lines(const uint8_t *blob, int blob_len, const char *to_nick, const char *from_nick,
                   const char *msg_id, char lines[][LINE_MAX], int max_lines);

#endif
