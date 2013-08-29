# coding: utf-8

# Copyright (c) 2011 Raphaël Droz.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import xattr

from pytagsfs.metastore import MetaStore
from pytagsfs.values import Values


class XattrMetaStore(MetaStore):
    def get(self, path):
        d = dict(xattr.get_all(path, namespace = xattr.NS_USER))
        for k in d:
            d[k] = d[k].split(',')
        return Values(d)

    def set(self, path, values):
        for k, v in values.iteritems():
            xattr.set(path, k, ','.join(v), namespace = xattr.NS_USER)
        return values.keys()
