# Copyright (c) 2007-2009 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import os, errno

from pytagsfs.util import unicode_path_sep
from pytagsfs.debug import (
  log_debug,
  log_warning,
  log_traceback,
)
from pytagsfs.multithreading import token_exchange


class SourceTree(object):
    root = None
    iocharset = None

    def __init__(self, root, iocharset = 'utf-8'):
        if not os.path.isabs(root):
            raise ValueError('root "%s" is not an absolute path' % root)
        self.root = root
        self.iocharset = iocharset

    def _validate_path(self, path):
        if not path.startswith(unicode_path_sep):
            raise ValueError(u'%s must start with a %s' % (
              repr(path), unicode_path_sep))

        if (path != unicode_path_sep) and path.endswith(unicode_path_sep):
            raise ValueError(u'%s must not end with a %s' % (
              repr(path), unicode_path_sep))

    def get_relative_path(self, abs_path):
        self._validate_path(abs_path)
        if self.root == unicode_path_sep:
            return abs_path
        rel_path = abs_path[len(self.root):]
        if not rel_path:
            rel_path = unicode_path_sep
        return rel_path

    def get_absolute_path(self, rel_path):
        self._validate_path(rel_path)

        if rel_path == unicode_path_sep:
            return self.root

        abs_path = os.path.join(
          self.root,
          rel_path.lstrip(unicode_path_sep)
        )
        return abs_path

    def walk(self, path = None):
        if path is None:
            path = self.root

        # os.walk seems to want encoded input
        path = self.encode(path)

        token_exchange.release_token()
        try:
            iterator = os.walk(path)
        finally:
            token_exchange.reacquire_token()
        while True:
            token_exchange.release_token()
            try:
                try:
                    dirpath, dirnames, filenames = iterator.next()
                except StopIteration:
                    break
            finally:
                token_exchange.reacquire_token()
            dirpath = self.decode(dirpath)
            dirnames = [self.decode(dirname) for dirname in dirnames]
            filenames = [self.decode(filename) for filename in filenames]
            yield (dirpath, dirnames, filenames)

    def decode(self, path):
        try:
            return path.decode(self.iocharset)
        except UnicodeDecodeError:
            log_traceback()
        except UnicodeEncodeError:
            log_traceback()
            if type(path) == unicode:
                log_warning('Warning: tried to decode a unicode string')
        decoded_path = path.decode(self.iocharset, 'replace')
        log_debug(u'Decoded path is "%s".', decoded_path)
        return decoded_path

    def encode(self, path):
        try:
            return path.encode(self.iocharset)
        except UnicodeEncodeError:
            log_traceback()
        except UnicodeDecodeError:
            log_traceback()
            if type(path) == str:
                log_warning('Warning: tried to encode a byte string')
        encoded_path = path.encode(self.iocharset, 'replace')
        log_debug(u'Encoded path is "%s".', encoded_path)
        return encoded_path

    @token_exchange.token_released
    def isreadable(self, path):
        '''
        Return True if an attempt to read a byte from the file does not cause
        an IOError.
        '''
        try:
            f = open(self.encode(path), 'r')
            try:
                f.read(1)
            finally:
                f.close()
        except IOError:
            return False
        return True

    @token_exchange.token_released
    def issymlink(self, path):
        '''
        Return True if readlink succeeds.
        '''
        try:
            os.readlink(self.encode(path))
        except OSError:
            return False
        return True

    @token_exchange.token_released
    def lstat(self, path):
        return os.lstat(self.encode(path))

    @token_exchange.token_released
    def utime(self, path, times):
        return os.utime(self.encode(path), times)
