# Copyright (c) 2007-2009 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import os.path, errno

try:
    from functools import wraps
except ImportError:
    from sclapp.legacy_support import wraps

from pytagsfs.exceptions import (
  PathNotFound,
  NotADirectory,
  PathExists,
  DirectoryNotEmpty,
  InvalidArgument,
)
from pytagsfs.exceptions import FuseError


unicode_path_sep = unicode(os.path.sep)


def now():
    import time
    return int(time.time())


def unique(iter):
    '''
    Generator; iterates over iter and yields each item that has not been seen
    already.  This algorithm prefers items toward the beginning of the list.

    >>> list(unique([1, 2, 5, 4, 5, 2, 3, 6, 2]))
    [1, 2, 5, 4, 3, 6]
    '''
    seen = []
    for item in iter:
        if item not in seen:
            yield item
        seen.append(item)


def last_unique(iter):
    '''
    Like unique, but prefer items toward the end of the list.  Also, returns
    a list rather than an iterator object.

    Given a list l, last_unique(l) is functionally equivalent to
    list(reversed(list(unique(reversed(l))))).

    >>> last_unique([1, 2, 5, 4, 5, 2, 3, 6, 2])
    [1, 4, 5, 3, 6, 2]
    '''
    result = []
    for item in iter:
        try:
            result.remove(item)
        except ValueError:
            pass
        result.append(item)
    return result


def sorted_items(d):
    return [(k, d[k]) for k in sorted(d.keys())]


def merge_dicts(*dicts):
    '''
    >>> d1 = {'a': 'x', 'b': 'y'}
    >>> d2 = {'b': 'm', 'c': 'n'}
    >>> sorted_items(merge_dicts(d1, d2))
    [('a', 'x'), ('b', 'm'), ('c', 'n')]
    '''
    result = {}
    for d in dicts:
        result.update(d)
    return result


def ref_self(self, *args, **kwargs):
    return self


def rpartition(s, by):
    '''
    In Python 2.4, str's have no method "rpartition".  This function tries to
    use Python 2.5's str method, and falls back to a custom implementation.
    '''
    if (
      isinstance(s, unicode) and not isinstance(by, unicode)
    ) or (
      isinstance(by, unicode) and not isinstance(s, unicode)
    ):
        raise TypeError('both arguments must be unicode or str')

    try:
        return s.rpartition(by)
    except AttributeError:
        pass
    parts = s.split(by)
    if len(parts) == 1:
        return ('', '', s)
    return (by.join(parts[:-1]), by, parts[-1])


def get_obj_by_dotted_name(dotted_name):
    from sclapp.util import importName

    # Note: both arguments to rpartition must be of same type (unicode, str).
    modname, dot, objname = rpartition(dotted_name, type(dotted_name)('.'))
    mod = importName(modname)
    return getattr(mod, objname)


def return_errno(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except PathNotFound:
            raise FuseError(errno.ENOENT)
        except NotADirectory:
            raise FuseError(errno.ENOTDIR)
        except PathExists:
            raise FuseError(errno.EEXIST)
        except DirectoryNotEmpty:
            raise FuseError(errno.ENOTEMPTY)
        except InvalidArgument:
            raise FuseError(errno.EINVAL)
        except NotImplementedError:
            raise FuseError(errno.ENOSYS)
        except (IOError, OSError), e:
            if hasattr(e, 'errno') and e.errno > 0:
                raise FuseError(e.errno)
            raise
    return wrapper


def split_path(path):
    if path.endswith(unicode_path_sep):
        raise ValueError(path)

    parts = []
    while True:
        path, part = os.path.split(path)
        if not part:
            break
        parts.append(part)

    return list(reversed(parts))


def join_path(path_parts):
    return os.path.join(*path_parts)


def join_path_rel(path_parts):
    path = os.path.join(*path_parts)
    return path.lstrip(unicode_path_sep)


def join_path_abs(path_parts):
    all_path_parts = [unicode_path_sep]
    all_path_parts.extend(path_parts)
    return os.path.join(*all_path_parts)


class LazyString(object):
    evaluator = None
    args = None
    kargs = None

    def __init__(self, evaluator, *args, **kwargs):
        self.evaluator = evaluator
        self.args = args
        self.kwargs = kwargs

    def __str__(self):
        raise NotImplementedError

    def __unicode__(self):
        raise NotImplementedError


class LazyByteString(LazyString):
    def __str__(self):
        return self.evaluator(*self.args, **self.kwargs)

    def __unicode__(self):
        return unicode(str(self))


class LazyUnicodeString(LazyString):
    def __str__(self):
        return str(unicode(self))

    def __unicode__(self):
        return self.evaluator(*self.args, **self.kwargs)


def ftruncate_path(path, length):
    # See unsafe_truncate to understand why this exists.
    f = open(path, 'r+')
    try:
        f.truncate(length)
    finally:
        f.close()


def unsafe_truncate(path, length):
    import ctypes
    from ctypes.util import find_library

    libc = ctypes.CDLL(find_library('libc'))

    # XXX: This is the unsafe assumption here.
    c_off_t = ctypes.c_int64

    path_type = type(path)
    if path_type is not str:
        raise TypeError('path must be of type str, not %s' % repr(path_type))
    libc.truncate(path, c_off_t(length))
