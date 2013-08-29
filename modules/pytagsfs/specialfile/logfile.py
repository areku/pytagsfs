# Copyright (c) 2007-2009 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import os, errno, stat, traceback, sys

try:
    from functools import wraps
except ImportError:
    from sclapp.legacy_support import wraps

from pytagsfs.util import (
  now,
  join_path_abs,
)
from pytagsfs.exceptions import InvalidArgument
from pytagsfs.specialfile import SpecialFile


class RingCharacterBuffer(object):
    max_length = None
    buffer = None
    len = None

    def __init__(self, max_length):
        self.max_length = max_length
        self.buffer = []
        self.len = 0

    def write(self, s):
        if not isinstance(s, str):
            raise AssertionError(
              'RingCharacterBuffer.write: argument should be a byte string.'
            )

        self.buffer.extend(list(s))
        self.len = self.len + len(s)

        if self.len > self.max_length:
            del self.buffer[0:self.len - self.max_length]
            self.len = self.max_length
            self.__class__ = FullRingCharacterBuffer

    def tell(self):
        return self.len

    def getvalue(self):
        return ''.join(self.buffer)


class FullRingCharacterBuffer(RingCharacterBuffer):
    def write(self, s):
        if not isinstance(s, str):
            raise AssertionError(
              'RingCharacterBuffer.write: argument should be a byte string.')

        self.buffer.extend(list(s))
        del self.buffer[0:len(s)]


class VirtualLogFile(SpecialFile):
    # class
    filename = u'.log'
    encoding = 'utf-8'
    file_obj = RingCharacterBuffer(1024 * 1024)

    init_time = now()
    atime = init_time
    mtime = init_time
    ctime = init_time

    log_file_highest_fd = 0
    log_file_open_files = {}

################################################################################

    @classmethod
    def set_max_length(cls, bytes):
        cls.file_obj.max_length = bytes

    @classmethod
    def log_write(cls, s):
        if isinstance(s, unicode):
            s = s.encode(cls.encoding)
        cls.file_obj.write(s)
        cls.mtime = now()

    @classmethod
    def ReadOnly(cls, filesystem, fake_path, flags, truncate_to):
        if truncate_to is not None:
            raise InvalidArgument()
        return super(VirtualLogFile, cls).ReadOnly(
          filesystem,
          fake_path,
          flags,
          truncate_to,
        )

    @classmethod
    def ReadWrite(cls, filesystem, fake_path, flags, truncate_to):
        raise InvalidArgument()

################################################################################

    # access
    # bmap: TBD
    # chmod
    # chown
    # create: not relevant
    # destroy: not relevant

    def fgetattr(self):
        return self.getattr(join_path_abs([self.filename]))

    def flush(self):
        pass

    def fsync(self, datasync):
        pass

    # ftruncate

    @classmethod
    def getattr(cls, path):
        root_statinfo = cls.filesystem.getattr(os.path.sep)
        st_dev = root_statinfo.st_dev
        st_uid = root_statinfo.st_uid
        st_gid = root_statinfo.st_gid

        return os.stat_result((
          (stat.S_IFREG | 0444),    #st_mode
          0,                        #st_ino
          st_dev,                   #st_dev
          1,                        #st_nlink
          st_uid,                   #st_uid
          st_gid,                   #st_gid
          cls.file_obj.tell(),      #st_size
          cls.atime,                #st_atime
          cls.mtime,                #st_mtime
          cls.ctime,                #st_ctime
        ))

    # getxattr
    # init: not relevant
    # listxattr
    # lock: TBD
    # mkdir: not relevant
    # mknod: not relevant
    # open: inherited
    # opendir: not relevant

    def read(self, length, offset):
        try:
            return self.file_obj.getvalue()[offset:offset+length]
        except:
            print >>sys.stderr, traceback.format_exc()
            raise

    # readdir: not relevant
    # readlink
    # release: inherited
    # releasedir: not relevant
    # removexattr
    # rename: not relevant
    # rmdir: not relevant
    # setxattr
    # statfs: not relevant
    # symlink: not relevant
    # truncate
    # unlink: not relevant

    @classmethod
    def utimens(cls, path, times):
        try:
            cls.atime, cls.mtime = times
        except (TypeError, ValueError):
            cls.atime = now()
            cls.mtime = cls.atime

    # write
