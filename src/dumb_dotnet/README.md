# airc-dumb (.NET 4.5 port)

Python `scripts/dumb_agent.py` is the protocol reference. This tree is the Server 2012 adapter.

Build (modern box with targeting pack):

```
msbuild airc-dumb.csproj /p:Configuration=Release /p:TargetFrameworkVersion=v4.5
```

TLS 1.2 preflight on Server 2012: enable SchUseStrongCrypto per Microsoft docs if SslException. Do not ship a prebuilt exe from CI in v1.

See `airc-dumb.csproj` stub.
