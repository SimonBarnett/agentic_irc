# airc-dumb (.NET 4.5 port)

Python `scripts/dumb_agent.py` is the protocol reference. This tree is the Server 2012 adapter.

**Status (2026-09-19):** stub only. `Program.cs` prints INFO and exits 0. It is **not** a behaviour clone of `dumb_agent.py` (no TcpClient, SslStream, AES-GCM, jail, or CAPA). Phase 5 remains open.

Build (modern box with targeting pack):

```
msbuild airc-dumb.csproj /p:Configuration=Release /p:TargetFrameworkVersion=v4.5
```

Wrapper: `airc-dumb.cmd` next to the exe for a scheduled task.

TLS 1.2 preflight on Server 2012: if connect fails with SslException, apply Microsoft guidance for enabling TLS 1.2 on .NET 4.5 (`SchUseStrongCrypto`). Do not downgrade TLS. Do not ship a prebuilt exe from CI in v1.

Optional pytest: set `DOTNET_DUMB_EXE` to a built `airc-dumb.exe`; otherwise the test is skipped.
