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
    char exe_dir[MAX_PATH];
    char pin[8];
    char pair_id[ID_MAX + 4];
    char beacon_url[512];
    unsigned long expires_unix;
    int port;
    int once;
    int selftest;
    int offline;
    int help;
    int version;
    int chair;
    int pairing;
} ThinConfig;

void config_defaults(ThinConfig *c);
void config_exe_dir(char *out, int outlen);
void sanitize_hostname(const char *host, char *out, int outlen);
void config_self_heal_ex(ThinConfig *c, const char *exe_dir, const char *hostname);
void config_self_heal(ThinConfig *c);
int config_try_load_ini(ThinConfig *c, const char *path);
int config_load_ini(ThinConfig *c, const char *path, char *err, int errlen);
int config_parse_argv(ThinConfig *c, int argc, char **argv, char *err, int errlen);
int config_validate(const ThinConfig *c, char *err, int errlen);
int config_write_paired(const ThinConfig *c);
int operators_empty(const char *ops);
int operator_allowed(const char *ops, const char *nick);
void operators_add(char *ops, int cap, const char *nick);
int config_key_path(const ThinConfig *c, char *out, int outlen);

#endif
