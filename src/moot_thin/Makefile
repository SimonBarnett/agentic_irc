# Optional MinGW-w64 i686 build. Primary toolchain is MSVC x86 (build.bat).
CC ?= gcc
CFLAGS ?= -O2 -Wall -DWIN32 -DWINVER=0x0501 -D_WIN32_WINNT=0x0501
LDFLAGS ?= -lws2_32 -lsecur32 -lcrypt32 -ladvapi32 -lwininet
SRCS = main.c util.c aes256gcm.c config.c jail.c moot.c dumb_job.c irc_tls.c pair.c beacon.c task_ui.c

airc-moot-thin.exe: $(SRCS) airc-moot-thin.rc airc-moot-thin.ico
	windres airc-moot-thin.rc -O coff -o airc-moot-thin.res
	$(CC) $(CFLAGS) -o $@ $(SRCS) airc-moot-thin.res $(LDFLAGS)
