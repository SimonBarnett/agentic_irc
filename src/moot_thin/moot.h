#ifndef AIRC_MOOT_H
#define AIRC_MOOT_H

#include "util.h"

void moot_join_line(const char *moot_id, char *out, int outlen);
void capa_line(const char *nick, const char *jail, int has_psk, char *out, int outlen);

#endif
