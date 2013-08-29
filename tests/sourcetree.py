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

from pytagsfs.sourcetree import SourceTree
from pytagsfs.util import unicode_path_sep

from manager import manager


class SourceTreeTestCase(TestCase):
    root = os.path.join(unicode_path_sep, u'foo', u'bar')

    def setUp(self):
        self.source_tree = SourceTree(self.root)

    def tearDown(self):
        del self.source_tree

    def test_get_relative_path(self):
        self.assertEqual(
          self.source_tree.get_relative_path(
            os.path.join(self.root, u'a')),
          os.path.join(unicode_path_sep, u'a'),
        )

        self.assertEqual(
          self.source_tree.get_relative_path(self.root),
          unicode_path_sep,
        )

        # Paths must begin with a slash.
        self.assertRaises(
          ValueError,
          self.source_tree.get_relative_path,
          u'a',
        )

        # Paths must not end with a slash.
        path = os.path.join(unicode_path_sep, u'a', u'')
        self.assertTrue(path.endswith(unicode_path_sep))
        self.assertRaises(
          ValueError,
          self.source_tree.get_relative_path,
          path,
        )

    def test_get_absolute_path(self):
        self.assertEqual(
          self.source_tree.get_absolute_path(
            os.path.join(unicode_path_sep, u'a')),
          os.path.join(self.root, u'a'),
        )

        self.assertEqual(
          self.source_tree.get_absolute_path(unicode_path_sep),
          self.root,
        )

        # Paths must begin with a slash.
        self.assertRaises(
          ValueError,
          self.source_tree.get_absolute_path,
          u'a',
        )

        # Paths must not end with a slash.
        path = os.path.join(unicode_path_sep, u'a', u'')
        self.assertTrue(path.endswith(unicode_path_sep))
        self.assertRaises(
          ValueError,
          self.source_tree.get_absolute_path,
          path,
        )


manager.add_test_case_class(SourceTreeTestCase)


class RootSourceTreeTestCase(SourceTreeTestCase):
    root = unicode_path_sep

manager.add_test_case_class(RootSourceTreeTestCase)
