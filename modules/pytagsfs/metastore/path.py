# Copyright (c) 2007-2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import os.path

from pytagsfs.metastore import MetaStore, UnsettableKeyError
from pytagsfs.util import sorted_items, unicode_path_sep
from pytagsfs.values import Values

class PathMetaStore(MetaStore):
    '''
    >>> store = PathMetaStore()
    >>> path = '/foo/bar.baz'

    >>> sorted(store.get(path).keys())
    ['e', 'extension', 'f', 'filename', 'p', 'parent']

    >>> sorted_items(store.get(path))
    [('e', 'baz'), ('extension', 'baz'), ('f', 'bar.baz'), ('filename', 'bar.baz'), ('p', 'foo'), ('parent', 'foo')]

    >>> store.set(path, Values({'f': 'boink.bonk'}))
    Traceback (most recent call last):
    ...
    UnsettableKeyError: can't set key f
    '''
    keys = ('f', 'filename', 'p', 'parent', 'e', 'extension')

    def get(self, path):
        path = path.rstrip(unicode_path_sep)

        filename = os.path.basename(path)
        parent = os.path.basename(os.path.dirname(path))

        extension = os.path.splitext(path)[1][1:]
        if not extension:
            extension = None

        values = Values()
        if filename:
            values['f'] = values['filename'] = [filename]
        if parent:
            values['p'] = values['parent'] = [parent]
        if extension:
            values['e'] = values['extension'] = [extension]

        return values

    def set(self, path, values):
        for key in self.keys:
            if key in values:
                raise UnsettableKeyError(key)
        return []
