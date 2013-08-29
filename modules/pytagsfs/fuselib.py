# Copyright (c) 2008-2009 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import errno
import traceback

import fuse
from fuse import (
  Fuse as _Fuse,
  FuseFileInfo as _FileInfo,
  Stat as _Stat,
  Direntry as _Direntry,
  StatVfs as _StatVfs,
)

from pytagsfs.debug import log_debug, log_critical
from pytagsfs.util import (
  LazyByteString,
  wraps,
)
from pytagsfs.exceptions import FuseError
from pytagsfs.profiling import profiled
from pytagsfs.multithreading import token_exchange, GLOBAL


fuse.fuse_python_api = (0, 2)


MAX_LEN_REPR_ARG = 512

def repr_arg(arg):
    retval = repr(arg)
    try:
        retval[MAX_LEN_REPR_ARG]
    except IndexError:
        return retval
    return ''.join([retval[:(MAX_LEN_REPR_ARG - 3)], '...'])


def repr_args(args):
    return ', '.join([repr_arg(arg) for arg in args])


def lazy_repr_args(args):
    return LazyByteString(repr_args, args)


def timespec_to_float(timespec):
    return float(timespec.tv_sec) + (float(timespec.tv_nsec) / 1000000000.0)


class FuseReprMixin(object):
    def __repr__(self):
        d = {}
        for name in dir(self):
            if not (name.startswith('__') and name.endswith('__')):
                d[name] = getattr(self, name)
        return '%s(%s)' % (
          self.__class__.__name__,
          repr(d),
        )


class FileInfo(FuseReprMixin, _FileInfo):
    pass


class Stat(FuseReprMixin, _Stat):
    pass


class Direntry(FuseReprMixin, _Direntry):
    pass


class StatVfs(FuseReprMixin, _StatVfs):
    pass


def fsmethod(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            ret = func(*args, **kwargs)
            if ret is None:
                ret = 0
        except FuseError, e:
            if e.errno is not None:
                ret = -e.errno
            else:
                ret = -errno.EFAULT
        except:
            log_critical(traceback.format_exc())
            ret = -errno.EFAULT
        return ret
    return wrapper


def logged(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        log_debug(u'%s(%s)', func.__name__, lazy_repr_args(args))
        ret = func(self, *args, **kwargs)
        log_debug(u'%s(...) -> %r', func.__name__, ret)
        return ret
    return wrapper


def logged_noargs(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        log_debug(u'%s(???)', func.__name__)
        ret = func(self, *args, **kwargs)
        log_debug(u'%s(...) -> %r', func.__name__, ret)
        return ret
    return wrapper


def logged_noret(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        log_debug(u'%s(%s)', func.__name__, lazy_repr_args(args))
        ret = func(self, *args, **kwargs)
        log_debug(u'%s(...) -> ???', func.__name__)
        return ret
    return wrapper


class Fuse(_Fuse):
    def __init__(self, filesystem, *args, **kwargs):
        self.filesystem = filesystem
        kwargs.setdefault('dash_s_do', 'setsingle')
        super(Fuse, self).__init__(*args, **kwargs)

    def main(self):
        try:
            return super(Fuse, self).main()
        finally:
            # See comment regarding fsdestroy.
            self.filesystem.destroy()

    @profiled
    @logged
    @fsmethod
    def access(self, path, mode):
        return self.filesystem.access(path, mode)

    @profiled
    @logged
    @fsmethod
    def bmap(self, path, blocksize, idx):
        return self.filesystem.bmap(path, blocksize, idx)

    @profiled
    @logged
    @fsmethod
    def chmod(self, path, mode):
        return self.filesystem.chmod(path, mode)

    @profiled
    @logged
    @fsmethod
    def chown(self, path, uid, gid):
        return self.filesystem.chown(path, uid, gid)

    @profiled
    @logged
    @fsmethod
    def create(self, path, flags, mode):
        return self.filesystem.create(path, flags, mode)

    # FIXME

    # This clean-up is performed at the end of main to work around what appears
    # to be a bug in python-fuse that prevents exit due to a GIL deadlock.  The
    # bug is fixed upstream, but the fix may not have been released yet.  Once
    # it is long gone, we can re-enabled this and remove the destroy call from
    # main.

    #@profiled
    #@logged
    #@fsmethod
    #def fsdestroy(self):
    #    self.filesystem.destroy()

    @profiled
    @logged
    @fsmethod
    def fgetattr(self, path, fi):
        return self._fgetattr(path, fi)

    def _fgetattr(self, path, fi):
        if fi is None:
            stat_result = self.filesystem.getattr(path)
        else:
            stat_result = self.filesystem.fgetattr(path, fi.fh)

        # This is a little bit complicated due to different handling in various
        # python-fuse versions:
        #
        # * Some versions do not handle None values; attributes should not be
        #   specified.
        # * Some versions do not handle missing attributes.
        #
        # Eventually, we should be able to return stat_result directly, but
        # only after python-fuse versions that don't support None for attribute
        # values have been phased out.  In the meantime, for maximum
        # compatibility we should always set a non-None value for all
        # attributes.  Thus, for some attributes we must guess a default using
        # the same heuristics that python-fuse uses for None/missing
        # attributes.

        st = Stat(
          st_dev = stat_result.st_dev,
          st_ino = stat_result.st_ino,
          st_mode = stat_result.st_mode,
          st_nlink = stat_result.st_nlink,
          st_uid = stat_result.st_uid,
          st_gid = stat_result.st_gid,
          #st_rdev = stat_result.st_rdev,
          st_size = stat_result.st_size,
          #st_blksize = stat_result.st_blksize,
          #st_blocks = stat_result.st_blocks,
          st_atime = stat_result.st_atime,
          st_mtime = stat_result.st_mtime,
          st_ctime = stat_result.st_ctime,
        )

        if stat_result.st_rdev is None:
            # I believe this should work with all systems.
            st.st_rdev = 0
        else:
            st.st_rdev = stat_result.st_rdev

        if stat_result.st_blksize is None:
            # Default value used by python-fuse.
            st.st_blksize = 4096
        else:
            st.st_blksize = stat_result.st_blksize

        if stat_result.st_blocks is None:
            # Default value used by python-fuse.
            st.st_blocks = ((stat_result.st_size + 511) / 512)
        else:
            st.st_blocks = stat_result.st_blocks

        return st

    @profiled
    @logged
    @fsmethod
    def flush(self, path, fi = None):
        fh = getattr(fi, 'fh', None)
        return self.filesystem.flush(path, fh)

    @profiled
    @logged
    @fsmethod
    def fsync(self, path, datasync, fi = None):
        fh = getattr(fi, 'fh', None)
        return self.filesystem.fsync(path, datasync, fh)

    @profiled
    @logged
    @fsmethod
    def fsyncdir(self, path, datasync, fi = None):
        fh = getattr(fi, 'fh', None)
        return self.filesystem.fsyncdir(path, datasync, fh)

    @profiled
    @logged
    @fsmethod
    def ftruncate(self, path, length, fi = None):
        fh = getattr(fi, 'fh', None)
        return self.filesystem.ftruncate(path, length, fh)

    @profiled
    @logged
    @fsmethod
    def getattr(self, path):
        return self._fgetattr(path, None)

    @profiled
    @logged
    @fsmethod
    def getxattr(self, path, name, size):
        return self.filesystem.getxattr(path, name, size)

    @profiled
    @logged
    @fsmethod
    def fsinit(self):
        self.filesystem.init()

    @profiled
    @logged
    @fsmethod
    def link(self, source, target):
        return self.filesystem.link(source, target)

    @profiled
    @logged
    @fsmethod
    def listxattr(self, path, size):
        return self.filesystem.listxattr(path, size)

    @profiled
    @logged
    @fsmethod
    def lock(self, path, cmd, owner, fi = None, **kwargs):
        # kwargs: l_type, l_start, l_len, l_pid
        fh = getattr(fi, 'fh', None)
        return self.filesystem.lock(path, cmd, owner, fh, **kwargs)

    @profiled
    @logged
    @fsmethod
    def mkdir(self, path, mode):
        return self.filesystem.mkdir(path, mode)

    @profiled
    @logged
    @fsmethod
    def mknod(self, path, mode, dev):
        return self.filesystem.mknod(path, mode, dev)

    @profiled
    @logged
    @fsmethod
    def open(self, path, flags):
        fh = self.filesystem.open(path, flags)
        # Note: keep_cache is only specified to avoid AttributeErrors in
        # python-fuse, which doesn't handle missing attributes well.  I think
        # that python-fuse's FileInfo class is supposed to specify a default
        # value as a class attribute but it is incorrectly named "keep" instead
        # of "keep_cache".  Bug not yet filed.
        return FileInfo(fh = fh, keep_cache = None)

    @profiled
    @logged
    @fsmethod
    def opendir(self, path):
        return self.filesystem.opendir(path)

    @profiled
    @logged_noret
    @fsmethod
    def read(self, path, size, offset, fi = None):
        fh = getattr(fi, 'fh', None)
        return self.filesystem.read(path, size, offset, fh)

    @profiled
    @logged
    @fsmethod
    def readdir(self, path, offset):
        # FIXME: Our FUSE bindings don't give us fi for readdir, so we fake
        # this as always None.
        fh = None

        entries = []
        for name in self.filesystem.readdir(path, fh):
            entries.append(Direntry(name))
        return entries

    @profiled
    @logged
    @fsmethod
    def readlink(self, path):
        return self.filesystem.readlink(path)

    @profiled
    @logged
    @fsmethod
    def release(self, path, flags, fi = None):
        fh = getattr(fi, 'fh', None)
        return self.filesystem.release(path, flags, fh)

    @profiled
    @logged
    @fsmethod
    def releasedir(self, path, fi = None):
        fh = getattr(fi, 'fh', None)
        return self.filesystem.releasedir(path, fh)

    @profiled
    @logged
    @fsmethod
    def removexattr(self, path, name):
        return self.filesystem.removexattr(path, name)

    @profiled
    @logged
    @fsmethod
    def rename(self, old, new):
        return self.filesystem.rename(old, new)

    @profiled
    @logged
    @fsmethod
    def rmdir(self, path):
        return self.filesystem.rmdir(path)

    @profiled
    @logged
    @fsmethod
    def setxattr(self, path, name, value, size, flags):
        return self.filesystem.setxattr(path, name, value, size, flags)

    @profiled
    @logged
    @fsmethod
    def statfs(self):
        statfs_result = self.filesystem.statfs()
        return StatVfs(
          f_bsize = statfs_result.f_bsize,
          f_frsize = statfs_result.f_frsize,
          f_blocks = statfs_result.f_blocks,
          f_bfree = statfs_result.f_bfree,
          f_bavail = statfs_result.f_bavail,
          f_files = statfs_result.f_files,
          f_ffree = statfs_result.f_ffree,
          f_favail = statfs_result.f_favail,
          f_flag = statfs_result.f_flag,
          f_namemax = statfs_result.f_namemax,
        )

    @profiled
    @logged
    @fsmethod
    def symlink(self, source, target):
        return self.filesystem.symlink(source, target)

    @profiled
    @logged
    @fsmethod
    def truncate(self, path, length):
        return self.filesystem.truncate(path, length)

    @profiled
    @logged
    @fsmethod
    def unlink(self, path):
        return self.filesystem.unlink(path)

    @profiled
    @logged
    @fsmethod
    def utimens(self, path, ts_atime, ts_mtime):
        atime = timespec_to_float(ts_atime)
        mtime = timespec_to_float(ts_mtime)
        return self.filesystem.utimens(path, (atime, mtime))

    @profiled
    @logged_noargs
    @fsmethod
    def write(self, path, buf, offset, fi = None):
        fh = getattr(fi, 'fh', None)
        return self.filesystem.write(path, buf, offset, fh)


class TokenFuse(Fuse):
    def main(self):
        try:
            # Note: calling super with parent class to skip Fuse.main.  We're
            # overriding, not extending.
            return super(Fuse, self).main()
        finally:
            token_exchange.push_token(GLOBAL)
            try:
                # See comment regarding fsdestroy.
                self.filesystem.destroy()
            finally:
                token_exchange.pop_token()

    access = token_exchange.token_pushed(GLOBAL)(Fuse.access)
    bmap = token_exchange.token_pushed(GLOBAL)(Fuse.bmap)
    chmod = token_exchange.token_pushed(GLOBAL)(Fuse.chmod)
    chown = token_exchange.token_pushed(GLOBAL)(Fuse.chown)
    create = token_exchange.token_pushed(GLOBAL)(Fuse.create)
    # XXX: Enable this when Fuse.fsdestroy is enabled.
    #fsdestroy = token_exchange.token_pushed(GLOBAL)(Fuse.fsdestroy)
    fgetattr = token_exchange.token_pushed(GLOBAL)(Fuse.fgetattr)
    flush = token_exchange.token_pushed(GLOBAL)(Fuse.flush)
    fsync = token_exchange.token_pushed(GLOBAL)(Fuse.fsync)
    fsyncdir = token_exchange.token_pushed(GLOBAL)(Fuse.fsyncdir)
    ftruncate = token_exchange.token_pushed(GLOBAL)(Fuse.ftruncate)
    getattr = token_exchange.token_pushed(GLOBAL)(Fuse.getattr)
    getxattr = token_exchange.token_pushed(GLOBAL)(Fuse.getxattr)
    fsinit = token_exchange.token_pushed(GLOBAL)(Fuse.fsinit)
    link = token_exchange.token_pushed(GLOBAL)(Fuse.link)
    listxattr = token_exchange.token_pushed(GLOBAL)(Fuse.listxattr)
    lock = token_exchange.token_pushed(GLOBAL)(Fuse.lock)
    mkdir = token_exchange.token_pushed(GLOBAL)(Fuse.mkdir)
    mknod = token_exchange.token_pushed(GLOBAL)(Fuse.mknod)
    open = token_exchange.token_pushed(GLOBAL)(Fuse.open)
    opendir = token_exchange.token_pushed(GLOBAL)(Fuse.opendir)
    read = token_exchange.token_pushed(GLOBAL)(Fuse.read)
    readdir = token_exchange.token_pushed(GLOBAL)(Fuse.readdir)
    readlink = token_exchange.token_pushed(GLOBAL)(Fuse.readlink)
    release = token_exchange.token_pushed(GLOBAL)(Fuse.release)
    releasedir = token_exchange.token_pushed(GLOBAL)(Fuse.releasedir)
    removexattr = token_exchange.token_pushed(GLOBAL)(Fuse.removexattr)
    rename = token_exchange.token_pushed(GLOBAL)(Fuse.rename)
    rmdir = token_exchange.token_pushed(GLOBAL)(Fuse.rmdir)
    setxattr = token_exchange.token_pushed(GLOBAL)(Fuse.setxattr)
    statfs = token_exchange.token_pushed(GLOBAL)(Fuse.statfs)
    symlink = token_exchange.token_pushed(GLOBAL)(Fuse.symlink)
    truncate = token_exchange.token_pushed(GLOBAL)(Fuse.truncate)
    unlink = token_exchange.token_pushed(GLOBAL)(Fuse.unlink)
    utimens = token_exchange.token_pushed(GLOBAL)(Fuse.utimens)
    write = token_exchange.token_pushed(GLOBAL)(Fuse.write)


class FileSystem(object):
    def access(self, path, mode):
        return 0

    def bmap(self, path, blocksize, idx):
        raise FuseError(errno.ENOSYS)

    def chmod(self, path, mode):
        raise FuseError(errno.ENOSYS)

    def chown(self, path, uid, gid):
        raise FuseError(errno.ENOSYS)

    def create(self, path, flags, mode):
        raise FuseError(errno.ENOSYS)

    def destroy(self):
        pass

    def fgetattr(self, path, fh):
        raise FuseError(errno.ENOSYS)

    def flush(self, path, fh):
        raise FuseError(errno.ENOSYS)

    def fsync(self, path, datasync, fh):
        raise FuseError(errno.ENOSYS)

    def fsyncdir(self, path, datasync, fh):
        raise FuseError(errno.ENOSYS)

    def ftruncate(self, path, length, fh):
        raise FuseError(errno.ENOSYS)

    def getattr(self, path):
        raise FuseError(errno.ENOSYS)

    def getxattr(self, path, name, size):
        raise FuseError(errno.ENOSYS)

    def init(self):
        pass

    def link(self, source, target):
        raise FuseError(errno.ENOSYS)

    def listxattr(self, path, size):
        raise FuseError(errno.ENOSYS)

    def lock(self, path, cmd, owner, fh, **kwargs):
        raise FuseError(errno.ENOSYS)

    def mkdir(self, path, mode):
        raise FuseError(errno.ENOSYS)

    def mknod(self, path, mode, dev):
        raise FuseError(errno.ENOSYS)

    def open(self, path, mode):
        return 0

    def opendir(self, path):
        return 0

    def read(self, path, size, offset, fh):
        raise FuseError(errno.ENOSYS)

    def readdir(self, path, readdir, fh):
        raise FuseError(errno.ENOSYS)

    def readlink(self, path):
        raise FuseError(errno.ENOSYS)

    def release(self, path, fh):
        return 0

    def releasedir(self, path, fh):
        return 0

    def removexattr(self, path, name):
        raise FuseError(errno.ENOSYS)

    def rename(self, old, new):
        raise FuseError(errno.ENOSYS)

    def rmdir(self, path):
        raise FuseError(errno.ENOSYS)

    def setxattr(self, path, name, value, size, flags):
        raise FuseError(errno.ENOSYS)

    def statfs(self):
        raise FuseError(errno.ENOSYS)

    def symlink(self, source, target):
        raise FuseError(errno.ENOSYS)

    def truncate(self, path, length):
        raise FuseError(errno.ENOSYS)

    def unlink(self, path):
        raise FuseError(errno.ENOSYS)

    def utimens(self, path, times):
        raise FuseError(errno.ENOSYS)

    def write(self, path, data, offset, fh):
        raise FuseError(errno.ENOSYS)
