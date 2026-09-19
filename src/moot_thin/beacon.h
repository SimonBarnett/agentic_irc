#ifndef AIRC_BEACON_H
#define AIRC_BEACON_H

#include "config.h"

#define INVITE_KIND "airc-invite"

typedef struct InviteDoc {
    int v;
    char host[128];
    int port;
    char channel[64];
    char moot_id[ID_MAX + 4];
    char pair_id[ID_MAX + 4];
    char pin[8];
    char chair[NICK_MAX + 4];
    unsigned long expires_unix;
} InviteDoc;

int invite_parse_json(const char *text, InviteDoc *out);
int invite_expired(const InviteDoc *inv, unsigned long now);
int invite_apply(ThinConfig *c, const InviteDoc *inv, unsigned long now);
int invite_write_files(const ThinConfig *c, const InviteDoc *inv);
int invite_load_sibling(ThinConfig *c, const char *exe_dir);
int invite_fetch_https(const char *url, char *out, int outlen);
int read_first_https_url(const char *path, char *out, int outlen);

#endif
