# Copyright (c) 2007-2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import os.path

from pytagsfs.exceptions import ErrorWithMessage, InvalidArgument
from pytagsfs.util import sorted_items
from pytagsfs.values import Values


class UnsettableKeyError(ErrorWithMessage):
    def __init__(self, key):
        self.key = key
        ErrorWithMessage.__init__(self, "can't set key %s" % key)


class MetaStore(object):
    def get(self, path):
        '''
        Return a Values instance containing all key/value pairs for ``path``.
        If path does not exist or no tags can be read from path with this
        MetaStore implementation, return an empty ``Values`` instance.
        '''
        raise NotImplementedError

    def set(self, path, values):
        '''
        Set the metadata for ``path`` according to dict ``values``.  Return a
        list of the keys applied.
        
        If path does not exist or cannot be used to store tag values using this
        ``MetaStore`` implementation, an empty list should always be returned
        to indicate that no tags were stored.

        For some implementations, nothing may actually get stored, but a
        non-empty list of keys may be returned to indicate that those keys are
        "owned" and that the caller should behave as if they had been stored
        (i.e. other ``MetaStore`` implementations should not handle those
        tags).
        '''
        raise NotImplementedError


class DelegateMultiMetaStore(MetaStore):
    def __init__(self, meta_stores):
        self.meta_stores = meta_stores

    def get(self, path):
        values = Values()
        for meta_store in self.meta_stores:
            try:
                values.update(meta_store.get(path))
            except NotImplementedError:
                continue
        return values

    def set(self, path, values):
        values = dict(values)

        keys = []
        for meta_store in self.meta_stores:
            try:
                new_keys = meta_store.set(path, values)
            except NotImplementedError:
                continue
            for key in new_keys:
                del values[key]
            keys.extend(new_keys)
        return keys
