# Copyright (c) 2008-2009 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import os

from pytagsfs.exceptions import (
  PathNotFound,
  InvalidArgument,
)
from pytagsfs.util import ref_self
from pytagsfs.multithreading import token_exchange


# Note: A token refering to a specific file instance is used to protect the
# file's open file descriptor.  It should *not* be acquired when accessing
# other attributes.  That would break assumptions made by code that relies on
# the global lock for data consistency.  truncate_to is of special concern
# because of how it is used in pytagsfs.fs.


class File(object):
    filesystem = None
    fake_path = None
    real_path = None
    flags = None
    truncate_to = None

    def __init__(
      self,
      filesystem,
      fake_path,
      flags,
      truncate_to = None,
    ):
        self.filesystem = filesystem
        self.fake_path = fake_path
        self.real_path = filesystem.source_tree_rep.get_real_path(fake_path)
        self.flags = flags
        self.truncate_to = truncate_to

    def fgetattr(self):
        raise NotImplementedError

    def flush(self):
        raise NotImplementedError

    def fsync(self, datasync):
        raise NotImplementedError

    def ftruncate(self, len):
        raise NotImplementedError

    def read(self, length, offset):
        raise NotImplementedError

    def release(self, flags):
        pass

    def write(self, buf, offset):
        raise NotImplementedError

    def set_truncate_to(self, truncate_to):
        # Note: We deliberately keep the global token here.
        self.truncate_to = truncate_to

    def del_truncate_to(self):
        # Note: We deliberately keep the global token here.
        del self.truncate_to


class ReadOnlyFile(File):
    fd = None
    file = None

    def __init__(self, *args, **kwargs):
        super(ReadOnlyFile, self).__init__(*args, **kwargs)
        self.open_file()

    @token_exchange.token_pushed(ref_self)
    def open_file(self):
        real_path = self.filesystem.encode_real_path(self.real_path)
        self.file = os.fdopen(os.open(real_path, self.flags), 'r')

################################################################################

    def fgetattr(self):
        token_exchange.push_token(self)
        try:
            fd = self.file.fileno()
            stat_result = os.fstat(fd)
        finally:
            token_exchange.pop_token()
        st_size = stat_result.st_size
        if (self.truncate_to is not None) and (st_size > self.truncate_to):
            st_size = self.truncate_to
        return os.stat_result((
          stat_result.st_mode,
          stat_result.st_ino,
          stat_result.st_dev,
          stat_result.st_nlink,
          stat_result.st_uid,
          stat_result.st_gid,
          st_size,
          stat_result.st_atime,
          stat_result.st_mtime,
          stat_result.st_ctime,
        ))

    def ftruncate(self, len):
        raise InvalidArgument

    def read(self, length, offset):
        if self.truncate_to is not None:
            length = self.truncate_to - offset
            if length < 0:
                length = 0
        token_exchange.push_token(self)
        try:
            self.file.seek(offset)
            return self.file.read(length)
        finally:
            token_exchange.pop_token()

    @token_exchange.token_pushed(ref_self)
    def release(self, flags):
        self.file.close()

    def write(self, buf, offset):
        raise InvalidArgument


class ReadWriteFile(File):
    fd = None

    def __init__(self, *args, **kwargs):
        super(ReadWriteFile, self).__init__(*args, **kwargs)
        self.open_file()

    def open_file(self):
        # Note: get value of truncate_to before pushing a new token.
        truncate_to = self.truncate_to
        real_path = self.filesystem.encode_real_path(self.real_path)

        token_exchange.push_token(self)
        try:
            self.fd = os.open(real_path, self.flags)

            if truncate_to is not None:
                os.ftruncate(self.fd, truncate_to)
        finally:
            token_exchange.pop_token()

################################################################################

    @token_exchange.token_pushed(ref_self)
    def read(self, length, offset):
        os.lseek(self.fd, offset, 0)
        return os.read(self.fd, length)

    @token_exchange.token_pushed(ref_self)
    def release(self, flags):
        return os.close(self.fd)

    @token_exchange.token_pushed(ref_self)
    def write(self, buf, offset):
        os.lseek(self.fd, offset, 0)
        return os.write(self.fd, buf)

    @token_exchange.token_pushed(ref_self)
    def fgetattr(self):
        return os.fstat(self.fd)

    @token_exchange.token_pushed(ref_self)
    def flush(self):
        return os.close(os.dup(self.fd))

    @token_exchange.token_pushed(ref_self)
    def fsync(self, datasync):
        if datasync and hasattr(os, 'fdatasync'):
            return os.fdatasync(self.fd)
        else:
            return os.fsync(self.fd)

    @token_exchange.token_pushed(ref_self)
    def ftruncate(self, len):
        return os.ftruncate(self.fd, len)
