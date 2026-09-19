#include "moot.h"

void moot_join_line(const char *moot_id, char *out, int outlen)
{
    _snprintf(out, outlen, "MOOT v1 JOIN %s", moot_id);
}

void capa_line(const char *nick, const char *jail, int has_psk, char *out, int outlen)
{
    _snprintf(out, outlen,
              "CAPA v1 dumb nick=%s verbs=ping,sysinfo,exec,get,put psk=%d agpk=0 jail=%s",
              nick, has_psk ? 1 : 0, jail);
}
