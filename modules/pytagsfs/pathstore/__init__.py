# Copyright (c) 2007-2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

from pytagsfs.util import join_path_abs


class PathStore(object):
    '''
    Abstract base class for path store implementations.

    Sub-classes must override the following methods:

     * ``add_file``
     * ``add_directory``
     * ``remove``
     * ``rename``
     * ``get_real_path``
     * ``get_fake_paths``
     * ``is_file``
     * ``is_dir``
     * ``path_exists``
     * ``get_entries``
     * ``get_real_subpaths``
     * ``set_meta_data``
     * ``get_meta_data``
     * ``unset_meta_data``

    Path stores store path mappings from real paths to fake (virtual) paths.
    Multiple real paths can be associated with a given fake path.  The most
    recently added real path takes precedence over previously added real paths.
    Conceptually, associating a real path with a fake path should behave like a
    stack, such that:

    >>> path_store.add_file(u'/foo', u'/bar')
    >>> path_store.get_real_path(u'/foo')
    u'/bar'
    >>> path_store.add_file(u'/foo', u'/baz')
    >>> path_store.get_real_path(u'/foo')
    u'/baz'
    >>> path_store.remove(u'/foo')
    >>> path_store.get_real_path(u'/foo')
    u'/bar'
    >>> path_store.remove(u'/foo')
    >>> path_store.get_real_path(u'/foo')
    Traceback (most recent call last):
    ...
    FakePathNotFound: /foo
    
    Parent directories of virtual files are implicitly created.  Once all files
    and sub-directories of these directories cease to exist, the directories
    themselves should magically disappear:

    >>> path_store.add_file(u'/foo/bar', u'/baz')
    >>> path_store.get_entries(u'/foo')
    [u'bar']
    >>> path_store.remove(u'/foo/bar')
    >>> path_store.get_entries(u'/foo')
    Traceback (most recent call last):
    ...
    FakePathNotFound: /foo

    Empty directories are handled differently from other directories in that
    they must be explicitly created, and that they are transient, which is to
    say that they cease to exist if they at any point contain entries and those
    entries are removed via ``remove``.

    >>> path_store.add_directory(u'/foo')
    >>> path_store.get_entries(u'/foo')
    []
    >>> path_store.add_file(u'/foo/bar/baz', u'/boink')
    >>> path_store.get_entries(u'/foo')
    [u'bar']
    >>> path_store.remove(u'/foo/bar/baz')
    >>> path_store.get_entries(u'/foo')
    Traceback (most recent call last):
    ...
    FakePathNotFound: /foo

    >>> path_store.add_directory(u'/foo')
    >>> path_store.get_entries(u'/foo')
    []
    >>> path_store.add_directory(u'/foo/bar')
    >>> path_store.get_entries(u'/foo')
    [u'bar']
    >>> path_store.get_entries(u'/foo/bar')
    []
    >>> path_store.remove(u'/foo/bar')
    >>> path_store.get_entries(u'/foo')
    Traceback (most recent call last):
    ...
    FakePathNotFound: /foo

    Another way of thinking about this is that empty directories exist as end
    points only in order to support incrementally building longer paths.  Once
    the need for an empty end point subsides, these directories are handled
    exactly the same as other implicitly-created directories.

    ``set_meta_data`` is expected to accept and store a single arbitrary,
    picklable Python object for later retrieval via ``get_meta_data`` (or
    removal via ``unset_meta_data``).

    Any stored meta-data should be associated with a fake path and the real
    path that was most recently added for that fake path.  Thus, if multiple
    real paths are associated with the same fake path, meta-data is set for
    that fake path, and the most recently added real path is then removed, the
    meta-data should be removed with it.  If meta-data had previously been
    associated with the fake path and the now-current real path, that meta-data
    should be associated with the fake path.

    >>> path_store.add_file(u'/foo', u'/bar')
    >>> path_store.set_meta_data(u'/foo', u'bink')
    >>> path_store.get_meta_data(u'/foo')
    u'bink'
    >>> path_store.add_file(u'/foo', u'/baz')
    >>> path_store.set_meta_data(u'/foo', u'bonk')
    >>> path_store.get_meta_data(u'/foo')
    u'bonk'
    >>> path_store.remove(u'/foo')
    >>> path_store.get_meta_data(u'/foo')
    u'bink'

    If the path store is thread safe, it should also override method
    ``supports_threads`` and return True (possibly only conditionally for the
    duration of the mount).

    All paths (both fake and real) are specified as unicode strings
    exclusively, so implementations don't need to care about character
    encodings at all, except as a matter of internal storage).

    Sub-classes are encouraged to define their class-level docstrings as
    follows in order to test consistency with the assumptions expressed here:

    # class MyPathStoreImplementation(PathStore):
    #     __doc__ = """
    #     Documentation for MyPathStoreImplementation.
    #
    #     >>> path_store = MyPathStoreImplementation()
    #
    #     """ + PathStore.__doc__

    There is also a unit test case that can be sub-classed to more thoroughly
    test the implementation.  See tests/pathstore.py.
    '''

    def add_file(self, real_path, fake_path):
        '''
        Add path mapping ``fake_path`` => ``real_path`` to the path store.
        Note that multiple real paths can be associated with any given fake
        path, with the most recently-added real path being returned by
        ``get_real_path``.  See the class docstring for more information.
        '''
        raise NotImplementedError

    def add_directory(self, fake_path):
        '''
        Create an empty virtual directory by virtual path.  Parent directories
        are implicitly created as for ``add_file``.  If the virtual path already
        exists in the path store, ``PathExists`` should be raised.
        '''
        raise NotImplementedError

    def remove(self, fake_path, real_path = None):
        '''
        Remove the virtual file or empty virtual directory by virtual path.
        For virtual files, this amounts to removing the mapping to the most
        recently added real path from the given fake path.

        If ``real_path`` is specified, the specific path mapping should be
        removed, rather than simply removing the most recently added mapping
        (this is used when a source file disappears from disk).  If
        ``fake_path`` refers to a virtual directory and ``real_path`` is
        specified, ``IsADirectory`` should be raised.

        Raise ``PathNotFound`` if no such path exists, or ``DirectoryNotEmpty``
        if the path is a non-empty directory.  Any meta-data set for this end
        point should also be removed.
        '''
        raise NotImplementedError

    def rename(self, old_fake_path, new_fake_path):
        '''
        Rename end point ``old_fake_path`` to ``new_fake_path``, or raise
        ``NotAnEndPoint`` if ``old_fake_path`` is not an end point (file or
        empty directory).  This is subtly different from calling
        ``remove(old_fake_path)`` followed by ``add_file(new_fake_path,
        real_path)`` or ``add_directory(new_fake_path)`` in that ``rename``
        should not cause the order of entries returned by ``get_entries`` to
        change when ``old_fake_path`` and ``new_fake_path`` refer to virtual
        files within the same virtual directory.  Additionally, ``rename``
        should always be more efficient than this remove/add pattern.  Any
        meta-data associated with ``old_fake_path`` should be removed.
        '''
        raise NotImplementedError

    def get_real_path(self, fake_path):
        '''
        Return the most recently added real path associated with virtual path
        ``fake_path``.  Raise ``FakePathNotFound`` if this virtual path is not
        in the path store.
        '''
        raise NotImplementedError

    def get_fake_paths(self, real_path):
        '''
        Return the fake paths associated with real path ``real_path``.  Raise
        ``RealPathNotFound`` if no such association exists in the path store.
        '''
        raise NotImplementedError

    def is_file(self, fake_path):
        '''
        Return True if virtual path ``fake_path`` refers to a virtual file.
        Return False otherwise, even if ``fake_path`` does not exist in the
        path store.
        '''
        raise NotImplementedError

    def is_dir(self, fake_path):
        '''
        Return True if virtual path ``fake_path`` refers to a virtual
        directory, whether that directory is empty or not.  Return False
        otherwise, even if ``fake_path`` does not exist in the path store.
        '''
        raise NotImplementedError

    def path_exists(self, fake_path):
        '''
        Return True if ``fake_path`` exists in the path store, independent of
        whether that path refers to a file or directory (empty or not).  Return
        False otherwise, even if ``fake_path`` does not exist in the path
        store.
        '''
        raise NotImplementedError

    def get_entries(self, fake_path):
        '''
        Return the names of all file and directories contained by the virtual
        directory with virtual path ``fake_path``.  The order of these entries
        should be consistent across multiple calls to ``get_entries``.  Raise
        ``NotADirectory`` if ``fake_path`` refers to a virtual file rather than
        a virtual directory.  Raise ``FakePathNotFound`` if no such fake path
        exists in the path store.
        '''
        raise NotImplementedError

    def get_real_subpaths(self, real_path):
        '''
        Return all real sub-paths of ``real_path``, not limited to the most
        recently added paths.
        '''
        raise NotImplementedError

    def set_meta_data(self, fake_path, meta_data):
        '''
        Store ``meta_data`` for ``fake_path``.  Raise ``PathNotFound`` if
        ``fake_path`` does not exist.  Raise ``NotAnEndPoint`` if ``fake_path``
        does not refer to an end point.
        '''
        raise NotImplementedError

    def get_meta_data(self, fake_path):
        '''
        Get meta-data for ``fake_path``.  Raise ``PathNotFound`` if
        ``fake_path`` does not exist.  Raise ``NoMetaDataExists`` if meta-data
        has not been set for this file.  Raise ``NotAnEndPoint`` if
        ``fake_path`` does not refer to an end point.
        '''
        raise NotImplementedError

    def unset_meta_data(self, fake_path):
        '''
        Remove meta-data for ``fake_path``.  Raise ``PathNotFound`` if
        ``fake_path`` does not exist.  Raise ``NoMetaDataExists`` if meta-data
        has not been set for this file.  Raise ``NotAnEndPoint`` if
        ``fake_path`` does not refer to an end point.
        '''
        raise NotImplementedError

    def supports_threads(self):
        '''
        Return True if the path store is thread-safe under current run-time
        conditions.  The result of this call should not vary over the course of
        a single mount.  In most cases, it will unconditionally return True or
        False to indicate the thread-safety of the specific path store
        implementation.  The default implementation returns False
        unconditionally.
        '''
        return False

################################################################################

    def get_end_points(self, fake_path):
        if self.is_file(fake_path):
            return [fake_path]

        entries = self.get_entries(fake_path)
        if entries == []:
            return [fake_path]

        end_points = []
        for entry in entries:
            entry_path = join_path_abs([fake_path, entry])
            end_points.extend(self.get_end_points(entry_path))
        return end_points
