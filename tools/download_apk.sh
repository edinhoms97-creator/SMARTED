#!/bin/bash
echo "Downloading SMARTEDTV.apk from Dropbox..."
curl -L --max-time 300 -o SMARTEDTV-original.apk 'https://uc85bb2e180f4d63e1abd349e75a.dl.dropboxusercontent.com/cd/0/get/DMzZJcqe3ih0vtTcJLZ_BqqK1V3nm3u6CaLtT8G7fYC-NGaaIjnZUfEoYZtoD1YNSKpkMgM2J9Bazf2GmvP65-lL7oF1IM-D4ROxDqpuY9H5jYt-StbYwDxHxZhswbwGvU-jnK7J-4vMLK7phGWjqvtQQISjG_WXOPHOW18gIxUmUg/file?c_luid=83fff3ca'
SIZE=$(stat -c%s SMARTEDTV-original.apk)
SHA=$(sha256sum SMARTEDTV-original.apk | awk '{print $1}')
echo "Size: $SIZE bytes"
echo "SHA256: $SHA"
