# Copyright (c) 2007-2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

from manager import manager

from pytagsfs.pathstore.pytypes import PyTypesPathStore

from pathstore import _PathStoreTestCase
from common import _UnicodePathsMixin


class PyTypesPathStoreTestCase(_PathStoreTestCase):
    path_store_class = PyTypesPathStore

manager.add_test_case_class(PyTypesPathStoreTestCase)


class PyTypesPathStoreUnicodeTestCase(_UnicodePathsMixin, _PathStoreTestCase):
    path_store_class = PyTypesPathStore

manager.add_test_case_class(PyTypesPathStoreUnicodeTestCase)


manager.add_doc_test_cases_from_module(__name__, 'pytagsfs.pathstore.pytypes')
