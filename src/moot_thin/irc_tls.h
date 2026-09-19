#ifndef AIRC_IRC_TLS_H
#define AIRC_IRC_TLS_H

#include "util.h"

typedef struct IrcConn IrcConn;

IrcConn *irc_new(void);
void irc_free(IrcConn *c);
int irc_connect(IrcConn *c, const char *host, int port, int use_tls, char *err, int errlen);
int irc_send_line(IrcConn *c, const char *line);
/* timeout_ms: 0 = poll, <0 = block. Returns 1 if line, 0 timeout, -1 dead. */
int irc_recv_line(IrcConn *c, char *buf, int buflen, int timeout_ms);
void irc_close(IrcConn *c);

#endif
