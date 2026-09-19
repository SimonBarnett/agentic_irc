#define SECURITY_WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <schannel.h>
#include <security.h>
#include "irc_tls.h"

#ifndef SP_PROT_TLS1_2_CLIENT
#define SP_PROT_TLS1_2_CLIENT 0x00000800
#endif
#ifndef SP_PROT_TLS1_3_CLIENT
#define SP_PROT_TLS1_3_CLIENT 0x00002000
#endif
#ifndef ISC_REQ_USE_SUPPLIED_CREDS
#define ISC_REQ_USE_SUPPLIED_CREDS 0x00000080
#endif
#ifndef SEC_I_INCOMPLETE_CREDENTIALS
#define SEC_I_INCOMPLETE_CREDENTIALS ((SECURITY_STATUS)0x00090320L)
#endif

#define EXTRA_MAX 16384
#define LINES_MAX 8192
#define IO_MAX 16384

struct IrcConn {
    SOCKET sock;
    CredHandle cred;
    CtxtHandle ctx;
    int have_cred;
    int have_ctx;
    int tls;
    SecPkgContext_StreamSizes sizes;
    char extra[EXTRA_MAX];
    int extra_n;
    char lines[LINES_MAX];
    int lines_n;
};

static int wsa_once(void)
{
    static int done;
    WSADATA w;
    if (done)
        return 0;
    if (WSAStartup(MAKEWORD(2, 2), &w) != 0)
        return -1;
    done = 1;
    return 0;
}

IrcConn *irc_new(void)
{
    IrcConn *c = (IrcConn *)calloc(1, sizeof(IrcConn));
    if (c)
        c->sock = INVALID_SOCKET;
    return c;
}

void irc_close(IrcConn *c)
{
    if (!c)
        return;
    if (c->have_ctx) {
        DeleteSecurityContext(&c->ctx);
        c->have_ctx = 0;
    }
    if (c->have_cred) {
        FreeCredentialsHandle(&c->cred);
        c->have_cred = 0;
    }
    if (c->sock != INVALID_SOCKET) {
        closesocket(c->sock);
        c->sock = INVALID_SOCKET;
    }
}

void irc_free(IrcConn *c)
{
    if (!c)
        return;
    irc_close(c);
    free(c);
}

static int sock_sendall(SOCKET s, const char *p, int n)
{
    int off = 0;
    while (off < n) {
        int k = send(s, p + off, n - off, 0);
        if (k <= 0)
            return -1;
        off += k;
    }
    return 0;
}

static int sock_recv_timeout(SOCKET s, char *buf, int cap, int timeout_ms)
{
    fd_set r;
    struct timeval tv;
    int k;
    FD_ZERO(&r);
    FD_SET(s, &r);
    tv.tv_sec = timeout_ms / 1000;
    tv.tv_usec = (timeout_ms % 1000) * 1000;
    k = select(0, &r, NULL, NULL, timeout_ms < 0 ? NULL : &tv);
    if (k == 0)
        return 0;
    if (k < 0)
        return -1;
    k = recv(s, buf, cap, 0);
    if (k == 0)
        return -1; /* peer closed */
    return k;
}

static SECURITY_STATUS handshake_step(IrcConn *c, const char *host, SecBufferDesc *in, SecBufferDesc *out, DWORD *flags)
{
    /* USE_SUPPLIED_CREDS: Libera (and other public TLS) may send CertificateRequest.
       Combined with SCH_CRED_NO_DEFAULT_CREDS this sends an empty client cert instead
       of stopping on SEC_I_INCOMPLETE_CREDENTIALS. */
    DWORD req = ISC_REQ_SEQUENCE_DETECT | ISC_REQ_REPLAY_DETECT | ISC_REQ_CONFIDENTIALITY |
                ISC_REQ_ALLOCATE_MEMORY | ISC_REQ_STREAM | ISC_REQ_USE_SUPPLIED_CREDS;
    return InitializeSecurityContextA(
        &c->cred,
        c->have_ctx ? &c->ctx : NULL,
        (SEC_CHAR *)host,
        req,
        0,
        0,
        in,
        0,
        c->have_ctx ? NULL : &c->ctx,
        out,
        flags,
        NULL);
}

static int send_out_token(IrcConn *c, SecBuffer *outb, char *err, int errlen, const char *why)
{
    if (!outb->cbBuffer || !outb->pvBuffer)
        return 0;
    if (sock_sendall(c->sock, (char *)outb->pvBuffer, (int)outb->cbBuffer) != 0) {
        FreeContextBuffer(outb->pvBuffer);
        outb->pvBuffer = NULL;
        outb->cbBuffer = 0;
        _snprintf(err, errlen, "%s", why);
        return -1;
    }
    FreeContextBuffer(outb->pvBuffer);
    outb->pvBuffer = NULL;
    outb->cbBuffer = 0;
    return 0;
}

static int tls_handshake(IrcConn *c, const char *host, char *err, int errlen)
{
    SCHANNEL_CRED sc;
    SECURITY_STATUS ss;
    DWORD flags = 0;
    SecBuffer outb;
    SecBufferDesc outd;
    char inbuf[IO_MAX];
    int inn = 0;

    memset(&sc, 0, sizeof(sc));
    sc.dwVersion = SCHANNEL_CRED_VERSION;
    sc.grbitEnabledProtocols = SP_PROT_TLS1_2_CLIENT | SP_PROT_TLS1_3_CLIENT;
    sc.dwFlags = SCH_CRED_AUTO_CRED_VALIDATION | SCH_CRED_NO_DEFAULT_CREDS;
    ss = AcquireCredentialsHandleA(NULL, UNISP_NAME, SECPKG_CRED_OUTBOUND, NULL, &sc, NULL, NULL, &c->cred, NULL);
    if (ss != SEC_E_OK) {
        _snprintf(err, errlen, "AcquireCredentialsHandle %lx", (unsigned long)ss);
        return -1;
    }
    c->have_cred = 1;

    outb.pvBuffer = NULL;
    outb.BufferType = SECBUFFER_TOKEN;
    outb.cbBuffer = 0;
    outd.ulVersion = SECBUFFER_VERSION;
    outd.cBuffers = 1;
    outd.pBuffers = &outb;

    ss = handshake_step(c, host, NULL, &outd, &flags);
    if (send_out_token(c, &outb, err, errlen, "tls send token") != 0)
        return -1;
    if (ss == SEC_E_OK) {
        c->have_ctx = 1;
        goto done;
    }
    if (ss != SEC_I_CONTINUE_NEEDED) {
        _snprintf(err, errlen, "InitializeSecurityContext %lx", (unsigned long)ss);
        return -1;
    }
    c->have_ctx = 1;

    {
    int cred_tries = 0;
    for (;;) {
        SecBuffer inb[2];
        SecBufferDesc ind;
        SecBufferDesc *pin = NULL;
        int k;
        int cred_retry = (ss == SEC_I_INCOMPLETE_CREDENTIALS);

        if (!cred_retry) {
            if (inn >= IO_MAX) {
                _snprintf(err, errlen, "tls handshake overflow");
                return -1;
            }
            k = sock_recv_timeout(c->sock, inbuf + inn, IO_MAX - inn, 20000);
            if (k <= 0) {
                _snprintf(err, errlen, "tls handshake recv");
                return -1;
            }
            inn += k;
        }
        if (inn > 0) {
            inb[0].pvBuffer = inbuf;
            inb[0].cbBuffer = (unsigned long)inn;
            inb[0].BufferType = SECBUFFER_TOKEN;
            inb[1].pvBuffer = NULL;
            inb[1].cbBuffer = 0;
            inb[1].BufferType = SECBUFFER_EMPTY;
            ind.ulVersion = SECBUFFER_VERSION;
            ind.cBuffers = 2;
            ind.pBuffers = inb;
            pin = &ind;
        }
        outb.pvBuffer = NULL;
        outb.cbBuffer = 0;
        outb.BufferType = SECBUFFER_TOKEN;
        outd.ulVersion = SECBUFFER_VERSION;
        outd.cBuffers = 1;
        outd.pBuffers = &outb;
        ss = handshake_step(c, host, pin, &outd, &flags);
        if (send_out_token(c, &outb, err, errlen, "tls send token2") != 0)
            return -1;
        /* Keep unread bytes on INCOMPLETE_MESSAGE. Zeroing inn here used to
           turn a split ServerHello into SEC_E_INVALID_TOKEN (80090308). */
        if (ss == SEC_E_INCOMPLETE_MESSAGE)
            continue;
        if (pin && inb[1].BufferType == SECBUFFER_EXTRA && inb[1].cbBuffer > 0) {
            int extra = (int)inb[1].cbBuffer;
            memmove(inbuf, inbuf + inn - extra, extra);
            inn = extra;
        } else {
            inn = 0;
        }
        if (ss == SEC_E_OK)
            break;
        if (ss == SEC_I_CONTINUE_NEEDED)
            continue;
        /* Optional client-cert request: retry ISC with no new recv (empty cert). */
        if (ss == SEC_I_INCOMPLETE_CREDENTIALS) {
            if (++cred_tries > 2) {
                _snprintf(err, errlen, "tls handshake %lx", (unsigned long)ss);
                return -1;
            }
            continue;
        }
        _snprintf(err, errlen, "tls handshake %lx", (unsigned long)ss);
        return -1;
    }
    }
    if (inn > 0 && inn < EXTRA_MAX) {
        memcpy(c->extra, inbuf, inn);
        c->extra_n = inn;
    }
done:
    if (QueryContextAttributesA(&c->ctx, SECPKG_ATTR_STREAM_SIZES, &c->sizes) != SEC_E_OK) {
        _snprintf(err, errlen, "stream sizes");
        return -1;
    }
    return 0;
}

int irc_connect(IrcConn *c, const char *host, int port, int use_tls, char *err, int errlen)
{
    char portstr[16];
    struct addrinfo hints, *res = NULL, *p;
    if (wsa_once() != 0) {
        _snprintf(err, errlen, "WSAStartup");
        return -1;
    }
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    _snprintf(portstr, sizeof(portstr), "%d", port);
    if (getaddrinfo(host, portstr, &hints, &res) != 0) {
        _snprintf(err, errlen, "getaddrinfo");
        return -1;
    }
    c->sock = INVALID_SOCKET;
    for (p = res; p; p = p->ai_next) {
        SOCKET s = socket(p->ai_family, p->ai_socktype, p->ai_protocol);
        if (s == INVALID_SOCKET)
            continue;
        if (connect(s, p->ai_addr, (int)p->ai_addrlen) == 0) {
            c->sock = s;
            break;
        }
        closesocket(s);
    }
    freeaddrinfo(res);
    if (c->sock == INVALID_SOCKET) {
        _snprintf(err, errlen, "connect failed");
        return -1;
    }
    c->tls = use_tls;
    if (use_tls)
        return tls_handshake(c, host, err, errlen);
    return 0;
}

static int tls_encrypt_send(IrcConn *c, const char *data, int n)
{
    SecBuffer bufs[4];
    SecBufferDesc d;
    SECURITY_STATUS ss;
    char *mem;
    int total;
    if (n > (int)c->sizes.cbMaximumMessage)
        n = (int)c->sizes.cbMaximumMessage;
    total = (int)c->sizes.cbHeader + n + (int)c->sizes.cbTrailer;
    mem = (char *)malloc(total);
    if (!mem)
        return -1;
    memcpy(mem + c->sizes.cbHeader, data, n);
    bufs[0].BufferType = SECBUFFER_STREAM_HEADER;
    bufs[0].pvBuffer = mem;
    bufs[0].cbBuffer = c->sizes.cbHeader;
    bufs[1].BufferType = SECBUFFER_DATA;
    bufs[1].pvBuffer = mem + c->sizes.cbHeader;
    bufs[1].cbBuffer = (unsigned long)n;
    bufs[2].BufferType = SECBUFFER_STREAM_TRAILER;
    bufs[2].pvBuffer = mem + c->sizes.cbHeader + n;
    bufs[2].cbBuffer = c->sizes.cbTrailer;
    bufs[3].BufferType = SECBUFFER_EMPTY;
    bufs[3].pvBuffer = NULL;
    bufs[3].cbBuffer = 0;
    d.ulVersion = SECBUFFER_VERSION;
    d.cBuffers = 4;
    d.pBuffers = bufs;
    ss = EncryptMessage(&c->ctx, 0, &d, 0);
    if (ss != SEC_E_OK) {
        free(mem);
        return -1;
    }
    {
        int m = (int)(bufs[0].cbBuffer + bufs[1].cbBuffer + bufs[2].cbBuffer);
        int rc = sock_sendall(c->sock, mem, m);
        free(mem);
        return rc;
    }
}

int irc_send_line(IrcConn *c, const char *line)
{
    char buf[LINE_MAX + 4];
    int n;
    _snprintf(buf, sizeof(buf), "%s\r\n", line);
    n = (int)strlen(buf);
    if (c->tls)
        return tls_encrypt_send(c, buf, n);
    return sock_sendall(c->sock, buf, n);
}

static int tls_decrypt_more(IrcConn *c, int timeout_ms)
{
    char raw[IO_MAX];
    int k;
    SecBuffer bufs[4];
    SecBufferDesc d;
    SECURITY_STATUS ss;
    char *msg;
    int msglen;
    int i;
    if (c->extra_n == 0) {
        k = sock_recv_timeout(c->sock, raw, sizeof(raw), timeout_ms);
        if (k == 0)
            return 0;
        if (k < 0)
            return -1;
        if (k > EXTRA_MAX)
            return -1;
        memcpy(c->extra, raw, k);
        c->extra_n = k;
    }
    msg = (char *)malloc(c->extra_n);
    if (!msg)
        return -1;
    memcpy(msg, c->extra, c->extra_n);
    msglen = c->extra_n;
    bufs[0].BufferType = SECBUFFER_DATA;
    bufs[0].pvBuffer = msg;
    bufs[0].cbBuffer = (unsigned long)msglen;
    bufs[1].BufferType = SECBUFFER_EMPTY;
    bufs[2].BufferType = SECBUFFER_EMPTY;
    bufs[3].BufferType = SECBUFFER_EMPTY;
    d.ulVersion = SECBUFFER_VERSION;
    d.cBuffers = 4;
    d.pBuffers = bufs;
    ss = DecryptMessage(&c->ctx, &d, 0, NULL);
    if (ss == SEC_E_INCOMPLETE_MESSAGE) {
        free(msg);
        k = sock_recv_timeout(c->sock, raw, sizeof(raw), timeout_ms);
        if (k == 0)
            return 0;
        if (k < 0)
            return -1;
        if (c->extra_n + k > EXTRA_MAX)
            return -1;
        memcpy(c->extra + c->extra_n, raw, k);
        c->extra_n += k;
        return 1;
    }
    if (ss != SEC_E_OK && ss != SEC_I_RENEGOTIATE) {
        free(msg);
        return -1;
    }
    c->extra_n = 0;
    for (i = 0; i < 4; i++) {
        if (bufs[i].BufferType == SECBUFFER_DATA && bufs[i].pvBuffer && bufs[i].cbBuffer) {
            int room = LINES_MAX - c->lines_n;
            int n = (int)bufs[i].cbBuffer;
            if (n > room)
                n = room;
            memcpy(c->lines + c->lines_n, bufs[i].pvBuffer, n);
            c->lines_n += n;
        } else if (bufs[i].BufferType == SECBUFFER_EXTRA && bufs[i].pvBuffer && bufs[i].cbBuffer) {
            int n = (int)bufs[i].cbBuffer;
            if (n > EXTRA_MAX)
                n = EXTRA_MAX;
            memcpy(c->extra, bufs[i].pvBuffer, n);
            c->extra_n = n;
        }
    }
    free(msg);
    return 1;
}

static int extract_line(IrcConn *c, char *buf, int buflen)
{
    int i;
    for (i = 0; i < c->lines_n; i++) {
        if (c->lines[i] == '\n') {
            int n = i;
            if (n > 0 && c->lines[n - 1] == '\r')
                n--;
            if (n >= buflen)
                n = buflen - 1;
            memcpy(buf, c->lines, n);
            buf[n] = 0;
            i++;
            memmove(c->lines, c->lines + i, c->lines_n - i);
            c->lines_n -= i;
            return 1;
        }
    }
    return 0;
}

int irc_recv_line(IrcConn *c, char *buf, int buflen, int timeout_ms)
{
    if (extract_line(c, buf, buflen))
        return 1;
    if (c->tls) {
        int r = tls_decrypt_more(c, timeout_ms < 0 ? 30000 : timeout_ms);
        if (r <= 0)
            return r;
        return extract_line(c, buf, buflen) ? 1 : 0;
    } else {
        char raw[1024];
        int k = sock_recv_timeout(c->sock, raw, sizeof(raw), timeout_ms < 0 ? 30000 : timeout_ms);
        if (k == 0)
            return 0;
        if (k < 0)
            return -1;
        if (c->lines_n + k > LINES_MAX)
            return -1;
        memcpy(c->lines + c->lines_n, raw, k);
        c->lines_n += k;
        return extract_line(c, buf, buflen) ? 1 : 0;
    }
}
