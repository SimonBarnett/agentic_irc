#ifndef AIRC_AES256GCM_H
#define AIRC_AES256GCM_H

#include "util.h"

/* out = ciphertext || tag(16). Does not prepend nonce. */
int aes256gcm_encrypt(const uint8_t key[32], const uint8_t nonce[12],
                      const uint8_t *aad, int aad_len,
                      const uint8_t *pt, int pt_len,
                      uint8_t *out, int outcap, int *out_len);

int aes256gcm_decrypt(const uint8_t key[32], const uint8_t nonce[12],
                      const uint8_t *aad, int aad_len,
                      const uint8_t *ct_and_tag, int ct_and_tag_len,
                      uint8_t *out, int outcap, int *out_len);

int dumb_seal(const uint8_t key[32], const char *channel, const char *to_nick,
              const char *from_nick, const char *msg_id,
              const uint8_t *pt, int pt_len, uint8_t *out, int outcap, int *out_len);

int dumb_open(const uint8_t key[32], const char *channel, const char *to_nick,
              const char *from_nick, const char *msg_id,
              const uint8_t *blob, int blob_len, uint8_t *out, int outcap, int *out_len);

void dumb_aad(const char *channel, const char *to_nick, const char *from_nick,
              const char *msg_id, char *out, int outlen);

#endif
