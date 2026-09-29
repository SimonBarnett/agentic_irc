WiX Toolset v3 binaries (candle/light/heat) are downloaded by scripts/Fetch-Wix.ps1
into third_party/wix/bin for packing airc-console MSI (issue #305).

Do not commit the zip or extracted binaries — they are large and regenerated on pack.
Source: https://github.com/wixtoolset/wix3/releases/tag/wix3112rtm
