# Copyright (c) 2007-2009 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import errno

from pytagsfs.metastore import MetaStore
from pytagsfs.values import Values
from pytagsfs.debug import log_loud


encoding = 'utf-8'


class TestLinesMetaStore(MetaStore):
    ord_a = ord('a')
    last_index = 26

    def __init__(self):
        log_loud(
          'WARNING: TestLinesMetaStore is for testing and benchmarking only!')
        log_loud(
          'WARNING: It WILL destroy your files.  Unmount now to avoid this.')

    def get(self, path):
        lines = []
        num_lines = 0
        try:
            f = open(path)
        except IOError:
            pass
        else:
            try:
                content = f.read()
            finally:
                f.close()

            index = content.rfind('\n')
            header = content[:index]

            for line in header.split('\n'):
                try:
                    line = line.decode(encoding)
                except UnicodeDecodeError:
                    line = ''
                lines.append(line)
                num_lines = num_lines + 1
                if num_lines >= self.last_index:
                    break

        keys = [self.index_to_key(index) for index in range(num_lines)]

        d = dict(zip(keys, lines))
        for k in list(iter(d)):
            if not d[k]:
                del d[k]

        return Values.from_flat_dict(d)

    def set(self, path, values):
        d = self.get(path).to_flat_dict()
        d.update(values.to_flat_dict())

        indexes = [self.key_to_index(k) for k in d]

        lines = []
        if indexes:
            max_index = max(indexes)
            for index in range(max_index + 1):
                line = d.get(self.index_to_key(index), '').encode(encoding)
                lines.append(line)

        try:
            f = open(path, 'r')
        except IOError, e:
            if e.errno != errno.ENOENT:
                raise
            content = ''
        else:
            try:
                content = f.read()
            finally:
                f.close()

        index = content.rfind('\n') + 1
        data = content[index:]

        f = open(path, 'w')
        try:
            f.write('\n'.join(lines))
            f.write('\n')
            f.write(data)
        finally:
            f.close()

    def index_to_key(self, index):
        if index < 0:
            raise ValueError(index)
        if index > self.last_index:
            raise ValueError(index)
        return chr(self.ord_a + index)

    def key_to_index(self, key):
        if len(key) != 1:
            raise ValueError(key)
        if key < 'a':
            raise ValueError(key)
        if key > 'z':
            raise ValueError(key)
        return ord(key) - self.ord_a
