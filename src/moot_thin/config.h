#ifndef AIRC_CONFIG_H
#define AIRC_CONFIG_H

#include "util.h"

typedef struct ThinConfig {
    char nick[NICK_MAX + 4];
    char channel[64];
    char moot_id[ID_MAX + 4];
    char home[MAX_PATH];
    char allow_path[MAX_PATH];
    char operators[512];
    char key_path[MAX_PATH];
    char host[128];
    char hello[200];
    char realname[64];
    char config_path[MAX_PATH];
    char job_in[MAX_PATH];
    char job_out[MAX_PATH];
    char from_nick[NICK_MAX + 4];
    char allow_bin_extra[256];
    int port;
    int once;
    int selftest;
    int offline;
    int help;
    int version;
} ThinConfig;

void config_defaults(ThinConfig *c);
int config_load_ini(ThinConfig *c, const char *path, char *err, int errlen);
int config_parse_argv(ThinConfig *c, int argc, char **argv, char *err, int errlen);
int config_validate(const ThinConfig *c, char *err, int errlen);
int operators_empty(const char *ops);
int operator_allowed(const char *ops, const char *nick);

#endif
