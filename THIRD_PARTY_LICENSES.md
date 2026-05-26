# Third-Party Licenses

This project includes or depends on the following third-party software.

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

## paramiko

**Version:** ≥ 3.0.0
**Project:** https://www.paramiko.org/
**Source:** https://github.com/paramiko/paramiko

**License: GNU Lesser General Public License v2.1 or later (LGPL-2.1+)**

Copyright © 2003-2009 Robey Pointer
Copyright © Jeff Forcier and contributors

The full license text is available at:
- https://github.com/paramiko/paramiko/blob/main/LICENSE
- https://www.gnu.org/licenses/old-licenses/lgpl-2.1.txt

Paramiko is declared as a runtime dependency in `requirements.txt` and
installed from PyPI by the end user. It is not modified or redistributed
as part of this repository.

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

