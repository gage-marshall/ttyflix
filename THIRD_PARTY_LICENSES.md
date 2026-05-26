# Third-Party Licenses

This project includes or depends on the following third-party software.

---

## FFmpeg (Windows bundle: `ffmpeg.exe`, `ffprobe.exe`)

**Version:** 2026-01-26-git-fe0813d6e2 (full build)
**Provider:** Gyan Doshi — https://www.gyan.dev/ffmpeg/builds/
**Project:** https://ffmpeg.org/

**License: GNU General Public License v2 or later, with version 3 components
(effective license: GPL v3)**

The bundled `ffmpeg.exe` and `ffprobe.exe` are compiled with
`--enable-gpl --enable-version3`, which enables GPL-licensed components
including (but not limited to) libx264, libx265, libxvid, and frei0r.
This makes the combined binary subject to the GNU General Public License
version 3 or later.

**Source code:** Gyan Doshi provides source packages alongside each build at
https://www.gyan.dev/ffmpeg/builds/. The source corresponding to this build
can be obtained from that page or by contacting the build maintainer.

**This does NOT affect the TTYFlix server code**, which is independent
software that invokes ffmpeg as an external process. If you replace the
bundled binaries with your own ffmpeg build (e.g., an LGPL build or a
system-installed package), that binary's own license terms apply instead.

The full text of the GNU General Public License v3 is available at:
https://www.gnu.org/licenses/gpl-3.0.txt

A summary of your rights and obligations under the GPL:
- You may use, study, share, and modify this software.
- If you distribute this software (or any work that incorporates it),
  you must make the source code available under the same GPL terms.
- You must include a copy of the GPL license with any distribution.

---

## Pillow

**Version:** ≥ 10.0.0
**Project:** https://python-pillow.org/
**Source:** https://github.com/python-pillow/Pillow

**License: HPND (Historical Permission Notice and Disclaimer)**

```
The Python Imaging Library (PIL) is

    Copyright © 1997-2011 by Secret Labs AB
    Copyright © 1995-2011 by Fredrik Lundh and contributors

Pillow is the friendly PIL fork. It is

    Copyright © 2010-2024 by Jeffrey A. Clark (Alex) and contributors

Like PIL, Pillow is licensed under the open source HPND License:

By obtaining, using, and/or copying this software and/or its associated
documentation, you agree that you have read, understood, and will comply
with the following terms and conditions:

Permission to use, copy, modify, and distribute this software and its
associated documentation for any purpose and without fee is hereby
granted, provided that the above copyright notice appears in all copies,
and that both that copyright notice and this permission notice appear in
supporting documentation, and that the name of Secret Labs AB or the
author not be used in advertising or publicity pertaining to distribution
of the software without specific, written prior permission.

SECRET LABS AB AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO
THIS SOFTWARE, INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL SECRET LABS AB OR THE AUTHOR BE LIABLE FOR
ANY SPECIAL, INDIRECT OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER
RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF
CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

---

## tomli (optional — Python < 3.11 only)

**Version:** ≥ 2.0.0
**Project:** https://github.com/hukkin/tomli
**Note:** Only required when running on Python 3.10 or earlier.
Python 3.11+ includes `tomllib` in the standard library.

**License: MIT**

```
MIT License

Copyright (c) 2021 Taneli Hukkinen

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Python (Docker image)

The official Docker image uses CPython.

**License: Python Software Foundation License Version 2**
https://docs.python.org/3/license.html

---

## Notes on Docker deployment

When building the Docker image, `ffmpeg` is installed from Debian's package
repositories via `apt`. That package is separately licensed (GPL v2+) and is
not bundled in this repository. The Dockerfile merely instructs the package
manager to install it; no GPL binary is distributed as part of this source.
