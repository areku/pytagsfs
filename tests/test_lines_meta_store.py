# Copyright (c) 2007-2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import os
from unittest import TestCase

from pytagsfs.metastore.testlines import TestLinesMetaStore
from pytagsfs.values import Values

from manager import manager
from common import TestWithDir


class TestLinesMetaStoreTestCase(TestWithDir):
    test_dir_prefix = 'mts'

    def test(self):
        filename = os.path.join(self.test_dir, 'foo')
        store = TestLinesMetaStore()
        store.set(filename, Values.from_flat_dict({'a': 'qux'}))
        try:
            self.assertEqual(store.get(filename), Values({'a': ['qux']}))
        finally:
            os.unlink(filename)

manager.add_test_case_class(TestLinesMetaStoreTestCase)
