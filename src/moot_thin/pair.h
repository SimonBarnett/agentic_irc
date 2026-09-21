#ifndef AIRC_PAIR_H
#define AIRC_PAIR_H

#include "util.h"
#include "config.h"

#define PAIR_TTL_S 600
#define PAIR_OFFER_MS 30000
#define PAIR_HELLO_MAX_FAIL 5
#define PAIR_DEFAULT_CHANNEL "#airc-moot"

#define PAIR_NONE 0
#define PAIR_THIN 1
#define PAIR_CHAIR 2

typedef struct PairLine {
    char verb[12];
    char moot_id[ID_MAX + 4];
    char pair_id[ID_MAX + 4];
    char extra[400];
} PairLine;

typedef struct PairSess {
    int role;
    int done;
    int hello_fails;
    unsigned long expires_unix;
    char pair_id[ID_MAX + 4];
    char pin[8];
    uint8_t wrap[32];
    int have_wrap;
    uint8_t psk[32];
    int have_psk;
    char chair_nick[NICK_MAX + 4];
    char thin_nick[NICK_MAX + 4];
    DWORD last_offer;
    DWORD wait0;
} PairSess;

int pin_ok(const char *p);
int pair_wrap_key(const char *pin, const char *pair_id, const char *channel,
                  const char *moot_id, uint8_t key[32]);
int pair_random_id(char out[ID_MAX + 1]);
int pair_random_pin(char out[8]);
int parse_pair_line(const char *body, PairLine *out);
void pair_offer_line(const char *moot_id, const char *pair_id, unsigned long expires,
                     char *out, int outlen);
void pair_ack_line(const char *moot_id, const char *pair_id, char *out, int outlen);
void chair_invite_line(const char *pin, const char *channel, const char *moot_id,
                       const char *host, int port, char *out, int outlen);
void chair_print_banner(const char *pin, const char *channel, const char *moot_id,
                        const char *host, int port);
int pair_hello_seal(const uint8_t wrap[32], const char *channel, const char *moot_id,
                    const char *pair_id, const char *nick, uint8_t *out, int outcap, int *out_len);
int pair_hello_open(const uint8_t wrap[32], const char *channel, const char *moot_id,
                    const char *pair_id, const uint8_t *blob, int blob_len,
                    char *nick, int nickcap);
int pair_grant_seal(const uint8_t wrap[32], const char *channel, const char *moot_id,
                    const char *pair_id, const char *thin_nick, const char *chair_nick,
                    const uint8_t psk[32], uint8_t *out, int outcap, int *out_len);
int pair_grant_open(const uint8_t wrap[32], const char *channel, const char *moot_id,
                    const char *pair_id, const char *thin_nick, const uint8_t *blob, int blob_len,
                    uint8_t psk[32], char *chair, int chaircap, char *moot_out, int mootcap);
int save_connector_key(const char *path, const uint8_t key[32]);
void pair_sess_clear_secrets(PairSess *ps);

#endif
