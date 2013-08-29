# Copyright (c) 2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import sys, os.path


def main(argv):
    if os.path.basename(argv[0]) == 'pymailtagsfs':
        print >>sys.stderr, (
          'Warning: '
          'using mail extension; '
          'invocation may change in the future (see NEWS)'
        )

        from pytagsfs.fs.mail import PyMailTagsFileSystem
        fs = PyMailTagsFileSystem()
    else:
        from pytagsfs.fs import PyTagsFileSystem
        fs = PyTagsFileSystem()
    return fs.main(argv)
