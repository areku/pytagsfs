# Copyright (c) 2008-2009 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import os

from pytagsfs.file import File
from pytagsfs.util import (
  return_errno,
  join_path_abs,
)
from pytagsfs.exceptions import InvalidArgument
from pytagsfs.debug import log_debug


def delegated_class_method(name):
    def fn(self, fake_path, *args, **kwargs):
        try:
            cls = self._special_file_classes_by_path[fake_path]
        except KeyError:
            return getattr(super(SpecialFileFileSystemMixin, self), name)(
              fake_path, *args, **kwargs)
        log_debug(
          u'delegated_class_method: name=%r, fake_path=%r: delegating to %s',
          name,
          fake_path,
          cls.__name__,
        )
        return getattr(cls, name)(fake_path, *args, **kwargs)
    return fn


class SpecialFileFileSystemMixin(object):
    special_file_classes = None
    _special_file_classes_by_path = None

    def get_read_only_file_instance(self, fake_path, flags, truncate_to):
        try:
            cls = self._special_file_classes_by_path[fake_path]
        except KeyError:
            return super(
              SpecialFileFileSystemMixin, self
            ).get_read_only_file_instance(fake_path, flags, truncate_to)

        return cls.ReadOnly(self, fake_path, flags, truncate_to)

    def get_read_write_file_instance(self, fake_path, flags, truncate_to):
        try:
            cls = self._special_file_classes_by_path[fake_path]
        except KeyError:
            return super(
              SpecialFileFileSystemMixin, self
            ).get_read_write_file_instance(fake_path, flags, truncate_to)

        return cls.ReadWrite(self, fake_path, flags, truncate_to)

################################################################################

    access = return_errno(delegated_class_method('access'))
    # bmap: TBD
    chmod = return_errno(delegated_class_method('chmod'))
    chown = return_errno(delegated_class_method('chown'))
    create = return_errno(delegated_class_method('create'))
    # destroy: not needed

    # fgetattr: handled by sub-class -> file instance

    # flush: handled by sub-class -> file instance
    # fsync: handled by sub-class -> file instance
    # fsyncdir: handled by sub-class -> file instance
    # ftruncate: handled by sub-class -> file instance

    _getattr = delegated_class_method('getattr')

    @return_errno
    def getattr(self, fake_path):
        stat_result = self._getattr(fake_path)
        if fake_path == os.path.sep:
            # Increase st_nlink by len(self.special_file_classes).
            # Can't use any fancy tricks treating stat_result as a tuple
            # because we'd lose atime, mtime, ctime floats.
            stat_result = os.stat_result((
              stat_result.st_mode,      #st_mode
              stat_result.st_ino,       #st_ino
              stat_result.st_dev,       #st_dev
              (                         #st_nlink
                stat_result.st_nlink +
                len(self.special_file_classes)
              ),
              stat_result.st_uid,       #st_uid
              stat_result.st_gid,       #st_gid
              stat_result.st_size,      #st_size
              stat_result.st_atime,     #st_atime
              stat_result.st_mtime,     #st_mtime
              stat_result.st_ctime,     #st_ctime
            ))
        return stat_result

    getxattr = return_errno(delegated_class_method('getxattr'))

    def init(self):
        self._special_file_classes_by_path = {}
        for cls in self.special_file_classes:
            self._special_file_classes_by_path[
              join_path_abs([cls.filename])] = cls
            cls.filesystem = self
        log_debug(
          'SpecialFileFileSystemMixin: _special_file_classes_by_path = %r',
          self._special_file_classes_by_path,
        )
        return super(SpecialFileFileSystemMixin, self).init()

    # link: not relevant
    listxattr = return_errno(delegated_class_method('listxattr'))
    # lock: TBD
    # mkdir: not relevant
    # mknod: not relevant
    # open: handled by sub-class -> file instance
    # opendir: not relevant
    # read: handled by sub-class -> file instance

    _readdir = delegated_class_method('readdir')

    @return_errno
    def readdir(self, fake_path, fh):
        result = self._readdir(fake_path, fh)
        if fake_path == os.path.sep:
            new_result = [
              self.encode_fake_path(cls.filename)
              for cls in self.special_file_classes
            ]
            new_result.extend(result)
            result = new_result
        return result

    readlink = return_errno(delegated_class_method('readlink'))
    # release: handled by sub-class -> file instance
    # releasedir: not relevant
    removexattr = return_errno(delegated_class_method('removexattr'))
    rename = return_errno(delegated_class_method('rename'))
    rmdir = return_errno(delegated_class_method('rmdir'))
    setxattr = return_errno(delegated_class_method('setxattr'))
    # statfs: not relevant
    # symlink: not relevant
    truncate = return_errno(delegated_class_method('truncate'))
    # unlink: not relevant
    utimens = return_errno(delegated_class_method('utimens'))
    # write: handled by sub-class -> file instance


def not_implemented(*args, **kwargs):
    raise NotImplementedError


class SpecialFile(File):
    filename = None

    filesystem = None

    def __init__(self, filesystem, fake_path, flags, truncate_to):
        self.filesystem = filesystem
        self.fake_path = fake_path
        self.flags = flags
        self.truncate_to = truncate_to

    @classmethod
    def ReadOnly(cls, filesystem, fake_path, flags, truncate_to):
        return cls(filesystem, fake_path, flags, truncate_to)

    @classmethod
    def ReadWrite(cls, filesystem, fake_path, flags, truncate_to):
        return cls(filesystem, fake_path, flags, truncate_to)

################################################################################

    access = classmethod(return_errno(not_implemented))
    # bmap: TBD
    chmod = classmethod(return_errno(not_implemented))
    chown = classmethod(return_errno(not_implemented))
    # create: not relevant
    # destroy: not relevant
    # fgetattr: inherited
    # flush: inherited
    # fsync: inherited
    # ftruncate: inherited
    getattr = classmethod(return_errno(not_implemented))
    getxattr = classmethod(return_errno(not_implemented))
    # init: not relevant
    listxattr = classmethod(return_errno(not_implemented))
    # lock: TBD
    # mkdir: not relevant
    # mknod: not relevant
    # open: inherited
    # opendir: not relevant
    # read: inherited
    # readdir: not relevant
    readlink = classmethod(return_errno(not_implemented))
    # release: inherited
    # releasedir: not relevant
    removexattr = classmethod(return_errno(not_implemented))
    # rename: not relevant
    # rmdir: not relevant
    setxattr = classmethod(return_errno(not_implemented))
    # statfs: not relevant
    # symlink: not relevant
    truncate = classmethod(return_errno(not_implemented))
    # unlink: not relevant
    utimens = classmethod(return_errno(not_implemented))
    # write: inherited
