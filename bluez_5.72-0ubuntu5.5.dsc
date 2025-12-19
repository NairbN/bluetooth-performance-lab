-----BEGIN PGP SIGNED MESSAGE-----
Hash: SHA512

Format: 3.0 (quilt)
Source: bluez
Binary: libbluetooth3, libbluetooth-dev, bluetooth, bluez, bluez-cups, bluez-obexd, bluez-meshd, bluez-hcidump, bluez-test-tools, bluez-test-scripts, bluez-source
Architecture: linux-any all
Version: 5.72-0ubuntu5.5
Maintainer: Ubuntu Developers <ubuntu-devel-discuss@lists.ubuntu.com>
Uploaders: Nobuhiro Iwamatsu <iwamatsu@debian.org>
Homepage: http://www.bluez.org
Standards-Version: 4.6.1
Vcs-Browser: https://git.launchpad.net/~bluetooth/bluez
Vcs-Git: https://git.launchpad.net/~bluetooth/bluez
Testsuite: autopkgtest
Testsuite-Triggers: python3-aptdaemon.test, python3-dbus
Build-Depends: debhelper-compat (= 13), flex, bison, libdbus-1-dev (>= 1.6), libglib2.0-dev, libdw-dev, libudev-dev, libreadline-dev, libical-dev, libasound2-dev, libell-dev (>= 0.39), libjson-c-dev (>= 0.13), python3-docutils, python3-pygments, udev, check <!nocheck>, systemd, systemd-dev
Package-List:
 bluetooth deb admin optional arch=all
 bluez deb admin optional arch=linux-any
 bluez-cups deb admin optional arch=linux-any
 bluez-hcidump deb admin optional arch=linux-any
 bluez-meshd deb admin optional arch=linux-any
 bluez-obexd deb admin optional arch=linux-any
 bluez-source deb admin optional arch=all
 bluez-test-scripts deb admin optional arch=all
 bluez-test-tools deb admin optional arch=linux-any
 libbluetooth-dev deb libdevel optional arch=linux-any
 libbluetooth3 deb libs optional arch=linux-any
Checksums-Sha1:
 6c73541f2cd27543b66741d16d520970d8877940 2390792 bluez_5.72.orig.tar.xz
 1a658af32178d27b76ca819dfb18594e04506f98 59784 bluez_5.72-0ubuntu5.5.debian.tar.xz
Checksums-Sha256:
 499d7fa345a996c1bb650f5c6749e1d929111fa6ece0be0e98687fee6124536e 2390792 bluez_5.72.orig.tar.xz
 cb88d8977950f8fe567e28daf0a5f688ceb866e7cdf366e992d24736454972e5 59784 bluez_5.72-0ubuntu5.5.debian.tar.xz
Files:
 fcacd4d6d65f7da141977a2beb1ba78f 2390792 bluez_5.72.orig.tar.xz
 f2ff275cab4a2e5bbfda1b7fbbeb0d3d 59784 bluez_5.72-0ubuntu5.5.debian.tar.xz
Original-Maintainer: Debian Bluetooth Maintainers <team+pkg-bluetooth@tracker.debian.org>

-----BEGIN PGP SIGNATURE-----

iQJSBAEBCgA8FiEEe36CAb2OUpFsR+d1yqruyKy2bB0FAmjl/NAeHGRhbmllbC52
YW4udnVndEBjYW5vbmljYWwuY29tAAoJEMqq7sistmwd35cQALS9GqXKPWwknJcm
L4SwbMy+oxV7ZAu5YQ+AGXq7fv2uAvub+WMhuYmLgUZcXUm3nzut99tBrUIWgAPd
4HPv+hSYqwEP3CSMmS4nN35qhPUL8Ez0UBhFw0GU8QEg3dU7dIn68tuwjQegli9+
MgAi7b6U0cV5JrSX+PjR5NsUZivfCstTxRK3iYm6IAqWaRl0NzarGdz3aJWN3114
ElrXPLmmRIIlFbMiwe8cREkKNgK7MJiJZfkAuAkL/mnTNoKim72NMus5V9hXeN9u
h0mMl+2Ipmrz1659t4N9WnAA0MblTHH7nKHh+/N2/yDN09bzYf7hCaQlG3qN5pe5
w6CDestC6vI38eZV9xxGgMg8awfP7TlRxnz2A9lO25l9NYTB3IkuWOY63b4FhHif
mpv3Poy2jJqgyZsWqNfLuE7e+p3AZcz2tXQ7Gbfcd/D3Hn71BVJ+CxieemTFkDwJ
niAP1k3/tKkP6YrLOr/CxBFjOYYsO0z867roUXXFFHGb7PpWC/tnkR2XYvtE2rgp
iW/YqIj8lznIb3DeysDLYYTkcVmOzx/W6OGs/d3CVSbIasuERadni2qnXlDyHzbH
D7wa4e13kqU7KJjRZs6DQNDQcfY+xQR30NHb/KbqEmosJmyWvVK0GvR6nL0IpSLO
Kw+U26M38kUJVMk+a9yZlPhMkML0
=Ir4o
-----END PGP SIGNATURE-----
