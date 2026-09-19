# Optional MinGW-w64 i686 build. Primary toolchain is MSVC x86 (build.bat).
CC ?= gcc
CFLAGS ?= -O2 -Wall -DWIN32 -DWINVER=0x0501 -D_WIN32_WINNT=0x0501
LDFLAGS ?= -lws2_32 -lsecur32 -lcrypt32 -ladvapi32
SRCS = main.c util.c aes256gcm.c config.c jail.c moot.c dumb_job.c irc_tls.c

airc-moot-thin.exe: $(SRCS)
	$(CC) $(CFLAGS) -o $@ $(SRCS) $(LDFLAGS)
