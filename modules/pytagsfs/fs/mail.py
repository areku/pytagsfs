# Copyright (c) 2008-2009 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import os

from pytagsfs.util import return_errno
from pytagsfs.fs import PyTagsFileSystemOptionParser, PyTagsFileSystem


class PyMailTagsFileSystemOptionParser(PyTagsFileSystemOptionParser):
    DEFAULT_MOUNT_OPTIONS = dict(
      PyTagsFileSystemOptionParser.DEFAULT_MOUNT_OPTIONS)
    DEFAULT_MOUNT_OPTIONS['format']['default'] = u'/cur/%{maildir_tag}/%f'
    DEFAULT_MOUNT_OPTIONS['metastores']['default'] = ';'.join([
      'pytagsfs.metastore.path.PathMetaStore',
      'pytagsfs.metastore.maildir.MaildirMetaStore',
    ])


class PyMailTagsFileSystem(PyTagsFileSystem):
    subtype = 'pymailtagsfs'

    def get_cmdline_parser(self):
        return PyMailTagsFileSystemOptionParser()

    def readdir(self, fake_path, fh):
        if fake_path in ('/tmp', '/new'):
            return []

        entries = super(PyMailTagsFileSystem, self).readdir(fake_path, fh)
        if fake_path == '/':
            if 'cur' not in entries:
                entries.append('cur')
            entries.append('tmp')
            entries.append('new')
        return entries

    def getattr(self, fake_path):
        if fake_path in ('/tmp', '/new'):
            stat_result = super(PyMailTagsFileSystem, self).getattr('/cur')
        else:
            stat_result = super(PyMailTagsFileSystem, self).getattr(fake_path)

        st_nlink = stat_result.st_nlink
        if fake_path == '/':
            st_nlink = 5
        elif fake_path in ('/tmp', '/new'):
            st_nlink = 2

        return os.stat_result((
          stat_result.st_mode,
          stat_result.st_ino,
          stat_result.st_dev,
          st_nlink,
          stat_result.st_uid,
          stat_result.st_gid,
          stat_result.st_size,
          stat_result.st_atime,
          stat_result.st_mtime,
          stat_result.st_ctime,
        ))

    @return_errno
    def rmdir(self, fake_path):
        if old_fake_path.count('/') == 1:
            raise InvalidArgument()
        return super(PyMailTagsFileSystem, self).rmdir(fake_path)
