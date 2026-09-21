#ifndef AIRC_JAIL_H
#define AIRC_JAIL_H

#include "util.h"

#define JAIL_BIN_MAX 32

/* jail_exec status (negative); 0 = subprocess ran */
#define JAIL_EXEC_FAIL     -1
#define JAIL_EXEC_BUSY     -2
#define JAIL_EXEC_BIN      -3
#define JAIL_EXEC_JAIL     -4
#define JAIL_EXEC_TIMEOUT  -5
#define JAIL_EXEC_EMPTY    -6
#define JAIL_EXEC_META     -7

typedef struct Jail {
    char root[MAX_PATH];
    char bins[JAIL_BIN_MAX][64];
    int nbin;
    int busy;
} Jail;

void jail_init(Jail *j, const char *allow_path, const char *extra_bins);
int jail_in(const Jail *j, const char *target);
int jail_bin_ok(const Jail *j, const char *argv0);
int jail_meta_ok(const char *joined);
int jail_exec(Jail *j, char **argv, int argc, const char *cwd, int timeout_s,
              char *out, int outcap, char *err, int errcap, int *rc);
int jail_apply_trunc(const char *home, const char *jid, char *out, char *err, int *truncated);

#endif
