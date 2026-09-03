# Cirax Scoop bucket

Engines that scoop's `main`/`extras` buckets don't carry, curated for Cirax.

    scoop bucket add cirax https://github.com/baselanaya/Cirax
    scoop install cirax/libjxl cirax/libavif cirax/vtracer

`cirax doctor --show-missing` prints these exact commands for anything
your machine is missing. Manifests auto-update from upstream releases
(checkver/autoupdate).
