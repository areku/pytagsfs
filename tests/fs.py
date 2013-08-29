# Copyright (c) 2007-2009 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import os, errno, stat, time

from pytagsfs.fs import PyTagsFileSystem
from pytagsfs.util import join_path_abs
from pytagsfs.exceptions import FuseError

from manager import manager
from common import mixin_unicode, TestWithDir


ENCODING = 'utf-8'


class _BaseFileSystemTestCase(TestWithDir):
    test_dir_prefix = 'fs'

    filesystem = None
    source_dir = None

    def p(self, s):
        return unicode(s)

    def setUp(self):
        super(_BaseFileSystemTestCase, self).setUp()
        self.build_source_tree()
        self.filesystem = self.create_filesystem()
        self.filesystem.parse()
        self.filesystem.pre_init()
        self.filesystem.init()

    def tearDown(self):
        self.filesystem.destroy()
        del self.filesystem
        self.remove_source_tree()
        super(_BaseFileSystemTestCase, self).tearDown()

    def build_source_tree(self):
        self.source_dir = os.path.join(self.test_dir, 'source')
        os.mkdir(self.source_dir)

    def remove_source_tree(self):
        os.rmdir(self.source_dir)
        del self.source_dir

    def create_filesystem(self):
        raise NotImplementedError

    def read_virtual_file(self, fake_path, flags = os.O_RDONLY):
        fh = self.filesystem.open(fake_path, flags)
        try:
            content = self.filesystem.read(fake_path, 1024, 0, fh)
        finally:
            self.assertEqual(self.filesystem.release(fake_path, flags, fh), 0)
        return content

    def assertVirtualFileContent(
      self, fake_path, content, flags = os.O_RDONLY):
        self.assertEqual(self.read_virtual_file(fake_path, flags), content)


class _BasePyTagsFileSystemTestCase(_BaseFileSystemTestCase):
    def create_filesystem(self):
        fs = PyTagsFileSystem()
        fs.argv = self.get_argv()
        return fs

    def get_argv(self):
        return [
          'pytagsfs',
          '-o',
          'format=/%f',
          self.source_dir.encode(ENCODING),
          'mnt',
        ]


class _BaseSingleFileOperationTestCase(_BasePyTagsFileSystemTestCase):
    filename = None
    source_file = None
    dest_file = None
    dest_file_encoded = None
    content = None

    def build_source_tree(self):
        super(_BaseSingleFileOperationTestCase, self).build_source_tree()

        self.filename = self.p('foo')
        self.source_file = os.path.join(self.source_dir, self.filename)
        self.dest_file = join_path_abs([self.filename])
        self.dest_file_encoded = self.dest_file.encode(ENCODING)
        self.content = self.get_content()

        f = open(self.source_file, 'w')
        try:
            f.write(self.content)
        finally:
            f.close()

    def get_content(self):
        return 'foo\nbar\nbaz\n'

    def remove_source_tree(self):
        os.unlink(self.source_file)
        del self.content
        del self.dest_file
        del self.source_file
        del self.filename

        super(_BaseSingleFileOperationTestCase, self).remove_source_tree()


class _BaseDirectoryOperationTestCase(_BasePyTagsFileSystemTestCase):
    def get_argv(self):
        return [
          'pytagsfs',
          '-o',
          'format=/%f/%f',
          self.source_dir.encode(ENCODING),
          'mnt',
        ]


class AccessTestCase(_BaseSingleFileOperationTestCase):
    def test_not_supported(self):
        self.assertEqual(self.filesystem.access(self.dest_file, os.F_OK), 0)

manager.add_test_case_class(AccessTestCase)
manager.add_test_case_class(mixin_unicode(AccessTestCase))


class BmapTestCase(_BasePyTagsFileSystemTestCase):
    def test_not_supported(self):
        try:
            self.filesystem.bmap(None, None, None)
        except FuseError, e:
            self.assertEqual(e.errno, errno.ENOSYS)

manager.add_test_case_class(BmapTestCase)
manager.add_test_case_class(mixin_unicode(BmapTestCase))


class ChmodTestCase(_BaseSingleFileOperationTestCase):
    def test(self):
        stat_result = os.stat(self.source_file)
        self.filesystem.chmod(
          self.dest_file_encoded,
          (stat_result.st_mode & stat.S_IWRITE),
        )
        stat_result = os.stat(self.source_file)
        assert stat_result.st_mode & stat.S_IWRITE
        self.filesystem.chmod(
          self.dest_file_encoded,
          (stat_result.st_mode & ~stat.S_IWRITE),
        )
        stat_result = os.stat(self.source_file)
        assert not (stat_result.st_mode & stat.S_IWRITE)

manager.add_test_case_class(ChmodTestCase)
manager.add_test_case_class(mixin_unicode(ChmodTestCase))


class ChownTestCase(_BaseSingleFileOperationTestCase):
    def test(self):
        # We can't really test side effects of chown, but we can test that it
        # doesn't blow up.
        stat_result = os.stat(self.source_file)
        self.filesystem.chown(
          self.dest_file_encoded,
          stat_result.st_uid,
          stat_result.st_gid,
        )

manager.add_test_case_class(ChownTestCase)
manager.add_test_case_class(mixin_unicode(ChownTestCase))


class CreateTestCase(_BasePyTagsFileSystemTestCase):
    def test_not_supported(self):
        try:
            self.filesystem.create(None, None, None)
        except FuseError, e:
            self.assertEqual(e.errno, errno.ENOSYS)

manager.add_test_case_class(CreateTestCase)
manager.add_test_case_class(mixin_unicode(CreateTestCase))


class FgetattrTestCase(_BaseSingleFileOperationTestCase):
    def test(self):
        flags = os.O_RDONLY
        fh = self.filesystem.open(self.dest_file_encoded, flags)
        try:
            real_stat_result = os.stat(self.source_file)
            fake_stat_result = self.filesystem.fgetattr(
              self.dest_file_encoded, fh)
        finally:
            self.filesystem.release(self.dest_file_encoded, flags, fh)

        self.assertEqual(real_stat_result.st_mode, fake_stat_result.st_mode)
        self.assertEqual(real_stat_result.st_size, fake_stat_result.st_size)
        self.assertEqual(real_stat_result.st_uid, fake_stat_result.st_uid)
        self.assertEqual(real_stat_result.st_gid, fake_stat_result.st_gid)
        self.assertEqual(real_stat_result.st_ctime, fake_stat_result.st_ctime)
        self.assertEqual(real_stat_result.st_mtime, fake_stat_result.st_mtime)
        self.assertEqual(real_stat_result.st_atime, fake_stat_result.st_atime)

        self.assertEqual(fake_stat_result.st_dev, 0)
        self.assertEqual(fake_stat_result.st_ino, 0)

manager.add_test_case_class(FgetattrTestCase)
manager.add_test_case_class(mixin_unicode(FgetattrTestCase))


class FlushTestCase(_BaseSingleFileOperationTestCase):
    def test(self):
        # We can only really test that flush doesn't blow up.
        flags = os.O_WRONLY
        fh = self.filesystem.open(self.dest_file_encoded, flags)
        try:
            self.filesystem.write(self.dest_file_encoded, 'qux\n', 0, fh)
            self.filesystem.flush(self.dest_file_encoded, fh)
        finally:
            self.filesystem.release(self.dest_file_encoded, flags, fh)

manager.add_test_case_class(FlushTestCase)
manager.add_test_case_class(mixin_unicode(FlushTestCase))


class FsyncTestCase(_BaseSingleFileOperationTestCase):
    def test(self):
        # We can only really test that fsync doesn't blow up.
        flags = os.O_WRONLY
        fh = self.filesystem.open(self.dest_file_encoded, flags)
        try:
            self.filesystem.write(self.dest_file_encoded, 'qux\n', 0, fh)
            self.filesystem.fsync(self.dest_file_encoded, False, fh)
        finally:
            self.filesystem.release(self.dest_file_encoded, flags, fh)

manager.add_test_case_class(FsyncTestCase)
manager.add_test_case_class(mixin_unicode(FsyncTestCase))


class FsyncdirTestCase(_BasePyTagsFileSystemTestCase):
    def test_not_supported(self):
        try:
            self.filesystem.fsyncdir(None, None, None)
        except FuseError, e:
            self.assertEqual(e.errno, errno.ENOSYS)

manager.add_test_case_class(FsyncdirTestCase)
manager.add_test_case_class(mixin_unicode(FsyncdirTestCase))


class FtruncateTestCase(_BaseSingleFileOperationTestCase):
    def test(self):
        flags = os.O_WRONLY
        fh = self.filesystem.open(self.dest_file_encoded, flags)
        try:
            self.filesystem.ftruncate(self.dest_file_encoded, 4, fh)
            stat_result = self.filesystem.fgetattr(self.dest_file_encoded, fh)
            self.assertEqual(stat_result.st_size, 4)
            self.assertFileContent(self.source_file, self.content[:4])
        finally:
            self.filesystem.release(self.dest_file_encoded, flags, fh)

    def test_ftruncate_affects_open_rdonly_file(self):
        fh_rdonly = self.filesystem.open(self.dest_file_encoded, os.O_RDONLY)
        try:
            fh_wronly = self.filesystem.open(
              self.dest_file_encoded, os.O_WRONLY)
            try:
                self.filesystem.ftruncate(self.dest_file_encoded, 4, fh_wronly)
                content = self.filesystem.read(
                  self.dest_file_encoded, 1024, 0, fh_rdonly)
            finally:
                self.filesystem.release(
                  self.dest_file_encoded, os.O_WRONLY, fh_wronly)
        finally:
            self.filesystem.release(
              self.dest_file_encoded, os.O_RDONLY, fh_rdonly)
        self.assertEqual(content, self.content[:4])

manager.add_test_case_class(FtruncateTestCase)
manager.add_test_case_class(mixin_unicode(FtruncateTestCase))


class GetattrTestCase(_BaseSingleFileOperationTestCase):
    def test(self):
        real_stat_result = os.stat(self.source_file)
        fake_stat_result = self.filesystem.getattr(self.dest_file_encoded)
        self.assertEqual(real_stat_result.st_mode, fake_stat_result.st_mode)
        self.assertEqual(real_stat_result.st_size, fake_stat_result.st_size)
        self.assertEqual(real_stat_result.st_uid, fake_stat_result.st_uid)
        self.assertEqual(real_stat_result.st_gid, fake_stat_result.st_gid)
        self.assertEqual(real_stat_result.st_ctime, fake_stat_result.st_ctime)
        self.assertEqual(real_stat_result.st_mtime, fake_stat_result.st_mtime)
        self.assertEqual(real_stat_result.st_atime, fake_stat_result.st_atime)

        self.assertEqual(fake_stat_result.st_dev, 0)
        self.assertEqual(fake_stat_result.st_ino, 0)

        # If not None, st_blksize must be correct.
        if fake_stat_result.st_blksize is not None:
            self.assertEqual(
              real_stat_result.st_blksize, fake_stat_result.st_blksize)

        # If not None, st_blocks must be correct.
        if fake_stat_result.st_blocks is not None:
            self.assertEqual(
              real_stat_result.st_blocks, fake_stat_result.st_blocks)

manager.add_test_case_class(GetattrTestCase)
manager.add_test_case_class(mixin_unicode(GetattrTestCase))


class GetxattrTestCase(_BasePyTagsFileSystemTestCase):
    def test_not_supported(self):
        try:
            self.filesystem.getxattr(None, None, None)
        except FuseError, e:
            self.assertEqual(e.errno, errno.ENOSYS)

manager.add_test_case_class(GetxattrTestCase)
manager.add_test_case_class(mixin_unicode(GetxattrTestCase))


class LinkTestCase(_BaseSingleFileOperationTestCase):
    def test(self):
        try:
            self.filesystem.link(None, None)
        except FuseError, e:
            self.assertEqual(e.errno, errno.ENOSYS)

manager.add_test_case_class(LinkTestCase)
manager.add_test_case_class(mixin_unicode(LinkTestCase))


class ListxattrTestCase(_BasePyTagsFileSystemTestCase):
    def test_not_supported(self):
        try:
            self.filesystem.listxattr(None, None)
        except FuseError, e:
            self.assertEqual(e.errno, errno.ENOSYS)

manager.add_test_case_class(ListxattrTestCase)
manager.add_test_case_class(mixin_unicode(ListxattrTestCase))


class LockTestCase(_BasePyTagsFileSystemTestCase):
    def test_not_supported(self):
        try:
            self.filesystem.lock(None, None, None, None)
        except FuseError, e:
            self.assertEqual(e.errno, errno.ENOSYS)

manager.add_test_case_class(LockTestCase)
manager.add_test_case_class(mixin_unicode(LockTestCase))


class MkdirTestCase(_BaseDirectoryOperationTestCase):
    def test(self):
        path = self.p('/foo').encode(ENCODING)
        self.filesystem.mkdir(path, 0)
        stat_result = self.filesystem.getattr(path)
        assert stat.S_ISDIR(stat_result.st_mode)

manager.add_test_case_class(MkdirTestCase)
manager.add_test_case_class(mixin_unicode(MkdirTestCase))


class MknodTestCase(_BasePyTagsFileSystemTestCase):
    def test_not_supported(self):
        try:
            self.filesystem.mknod(None, None, None)
        except FuseError, e:
            self.assertEqual(e.errno, errno.ENOSYS)

manager.add_test_case_class(MknodTestCase)
manager.add_test_case_class(mixin_unicode(MknodTestCase))


class OpenTestCase(_BaseSingleFileOperationTestCase):
    # Open is tested extensively elsewhere.  Just target specific corner cases
    # here.
    def test_non_existent_file(self):
        try:
            self.filesystem.open(
              self.p('/qux').encode(ENCODING), os.O_RDONLY)
        except FuseError, e:
            self.assertEqual(e.errno, errno.ENOENT)
        else:
            assert False

manager.add_test_case_class(OpenTestCase)
manager.add_test_case_class(mixin_unicode(OpenTestCase))


class OpendirTestCase(_BasePyTagsFileSystemTestCase):
    def test(self):
        self.assertEqual(self.filesystem.opendir(None), 0)

manager.add_test_case_class(OpendirTestCase)
manager.add_test_case_class(mixin_unicode(OpendirTestCase))


class ReadTestCase(_BaseSingleFileOperationTestCase):
    # This test is somewhat superfluous, but I'd rather have something here
    # than nothing at all.
    def test(self):
        flags = os.O_RDONLY
        fh = self.filesystem.open(self.dest_file_encoded, flags)
        try:
            content = self.filesystem.read(
              self.dest_file_encoded, 1024, 0, fh)
        finally:
            self.filesystem.release(self.dest_file_encoded, flags, fh)
        self.assertEqual(content, self.content)

manager.add_test_case_class(ReadTestCase)
manager.add_test_case_class(mixin_unicode(ReadTestCase))


class ReaddirTestCase(_BasePyTagsFileSystemTestCase):
    files = None

    def build_source_tree(self):
        super(ReaddirTestCase, self).build_source_tree()
        self.files = [self.p(x) for x in ('foo', 'bar', 'baz')]
        for file in self.files:
            self._create_file(os.path.join(self.source_dir, file))

    def remove_source_tree(self):
        for file in self.files:
            os.unlink(os.path.join(self.source_dir, file))
        del self.files
        super(ReaddirTestCase, self).remove_source_tree()

    def test(self):
        entries = self.filesystem.readdir('/', None)
        for entry in entries:
            self.assertEqual(type(entry), str)
        self.assertEqual(
          set(entries),
          set(['.log'] + [f.encode(ENCODING) for f in self.files]),
        )

manager.add_test_case_class(ReaddirTestCase)
manager.add_test_case_class(mixin_unicode(ReaddirTestCase))


class ReadlinkTestCase(_BasePyTagsFileSystemTestCase):
    def test_not_supported(self):
        try:
            self.filesystem.readlink(None)
        except FuseError, e:
            self.assertEqual(e.errno, errno.ENOSYS)
        else:
            assert False

manager.add_test_case_class(ReadlinkTestCase)
manager.add_test_case_class(mixin_unicode(ReadlinkTestCase))


class ReleaseTestCase(_BaseSingleFileOperationTestCase):
    # Nothing to test.  See ConcurrentFilesTestCase.
    pass


manager.add_test_case_class(ReleaseTestCase)
manager.add_test_case_class(mixin_unicode(ReleaseTestCase))


class ReleasedirTestCase(_BasePyTagsFileSystemTestCase):
    def test(self):
        self.assertEqual(self.filesystem.releasedir(None, None), 0)

manager.add_test_case_class(ReleasedirTestCase)
manager.add_test_case_class(mixin_unicode(ReleasedirTestCase))


class RemovexattrTestCase(_BasePyTagsFileSystemTestCase):
    def test_not_supported(self):
        try:
            self.filesystem.removexattr(None, None)
        except FuseError, e:
            self.assertEqual(e.errno, errno.ENOSYS)
        else:
            assert False

manager.add_test_case_class(RemovexattrTestCase)
manager.add_test_case_class(mixin_unicode(RemovexattrTestCase))


class RenameTestCase(_BaseSingleFileOperationTestCase):
    def get_argv(self):
        return [
          'pytagsfs',
          '-o',
          (
            'metastores=pytagsfs.metastore.testlines.TestLinesMetaStore,'
            'format=/%a'
          ),
          self.source_dir.encode(ENCODING),
          'mnt',
        ]

    def get_content(self):
        return '%s\n' % self.p('foo').encode(ENCODING)

    def test(self):
        qux = self.p(u'qux').encode(ENCODING)
        path = '/%s'.encode(ENCODING) % qux
        self.filesystem.rename(self.dest_file_encoded, path)
        self.assertVirtualFileContent(
          self.dest_file_encoded,
          ''.join([qux, self.content[len(qux):]]),
        )

manager.add_test_case_class(RenameTestCase)
manager.add_test_case_class(mixin_unicode(RenameTestCase))


class RmdirTestCase(_BaseDirectoryOperationTestCase):
    def test(self):
        path = self.p('/foo').encode(ENCODING)
        self.filesystem.mkdir(path, 0)
        self.filesystem.rmdir(path)
        try:
            self.filesystem.getattr(path)
        except FuseError, e:
            self.assertEqual(e.errno, errno.ENOENT)
        else:
            assert False

manager.add_test_case_class(RmdirTestCase)
manager.add_test_case_class(mixin_unicode(RmdirTestCase))


class SetxattrTestCase(_BasePyTagsFileSystemTestCase):
    def test_not_supported(self):
        try:
            self.filesystem.setxattr(None, None, None, None, None)
        except FuseError, e:
            self.assertEqual(e.errno, errno.ENOSYS)
        else:
            assert False

manager.add_test_case_class(SetxattrTestCase)
manager.add_test_case_class(mixin_unicode(SetxattrTestCase))


class StatfsTestCase(_BasePyTagsFileSystemTestCase):
    copied_attributes = (
      'f_bsize',
      'f_frsize',
      'f_bavail',
      'f_files',
      'f_ffree',
      'f_favail',
      'f_namemax',
    )
    other_attributes = (
      'f_fsid',
      'f_flag',
    )

    def get_argv(self):
        return [
          'pytagsfs',
          '-o',
          'format=/%f/%f',
          self.source_dir.encode(ENCODING),
          'mnt',
        ]

    def test(self):
        statfs_result = self.filesystem.statfs()
        statvfs_result = os.statvfs(self.source_dir.encode(ENCODING))
        for name in self.copied_attributes:
            self.assertEqual(
              getattr(statfs_result, name),
              getattr(statvfs_result, name),
            )
        self.assertTrue(type(statfs_result.f_flag), int)

manager.add_test_case_class(StatfsTestCase)
manager.add_test_case_class(mixin_unicode(StatfsTestCase))


class SymlinkTestCase(_BasePyTagsFileSystemTestCase):
    def test_not_supported(self):
        try:
            self.filesystem.symlink(None, None)
        except FuseError, e:
            self.assertEqual(e.errno, errno.ENOSYS)
        else:
            assert False

manager.add_test_case_class(SymlinkTestCase)
manager.add_test_case_class(mixin_unicode(SymlinkTestCase))


class TruncateTestCase(_BaseSingleFileOperationTestCase):
    def test_read_from_read_only_file(self):
        self.filesystem.truncate(self.dest_file_encoded, 4)
        stat_result = self.filesystem.getattr(self.dest_file_encoded)
        self.assertEqual(stat_result.st_size, 4)
        self.assertFileContent(self.source_file, self.content)
        self.assertVirtualFileContent(
          self.dest_file_encoded, self.content[:4])
        # Another read should give the same result.
        self.assertVirtualFileContent(
          self.dest_file_encoded, self.content[:4])

    def test_read_from_read_write_file(self):
        self.filesystem.truncate(self.dest_file_encoded, 4)
        stat_result = self.filesystem.getattr(self.dest_file_encoded)
        self.assertEqual(stat_result.st_size, 4)
        self.assertFileContent(self.source_file, self.content, mode = 'rb+')
        self.assertVirtualFileContent(
          self.dest_file_encoded,
          self.content[:4],
          os.O_RDWR,
        )
        # Another read should give the same result.
        self.assertVirtualFileContent(
          self.dest_file_encoded,
          self.content[:4],
          os.O_RDWR,
        )

    def test_truncate_affects_open_rdonly_file(self):
        flags = os.O_RDONLY
        fh = self.filesystem.open(self.dest_file_encoded, flags)
        try:
            self.filesystem.truncate(self.dest_file_encoded, 4)
            content = self.filesystem.read(self.dest_file_encoded, 1024, 0, fh)
        finally:
            self.filesystem.release(self.dest_file_encoded, flags, fh)
        self.assertEqual(content, self.content[:4])

    def test_truncate_affects_source_file_if_virtual_file_is_opened_for_writing(
      self):
        flags = os.O_RDWR
        fh = self.filesystem.open(self.dest_file_encoded, flags)
        try:
            self.filesystem.truncate(self.dest_file_encoded, 4)
            self.assertFileContent(self.source_file, self.content[:4])
        finally:
            self.filesystem.release(self.dest_file_encoded, flags, fh)

    def test_write_affects_truncated_open_rdonly_file(self):
        self.filesystem.truncate(self.dest_file_encoded, 4)

        fh_rdonly = self.filesystem.open(self.dest_file_encoded, os.O_RDONLY)
        try:
            fh_wronly = self.filesystem.open(
              self.dest_file_encoded, os.O_WRONLY | os.O_APPEND)
            try:
                self.filesystem.write(
                  self.dest_file_encoded, 'qux\n', 0, fh_wronly)
                content = self.filesystem.read(
                  self.dest_file_encoded, 1024, 0, fh_rdonly)
            finally:
                self.filesystem.release(
                  self.dest_file_encoded, os.O_WRONLY, fh_wronly)
        finally:
            self.filesystem.release(
              self.dest_file_encoded, os.O_RDONLY, fh_rdonly)

        self.assertEqual(content, self.content[:4] + 'qux\n')

    def test_read_from_already_open_read_write_file(self):
        flags = os.O_RDONLY
        fh = self.filesystem.open(self.dest_file_encoded, flags)
        try:
            self.filesystem.truncate(self.dest_file_encoded, 4)
            self.assertEqual(
              self.filesystem.read(self.dest_file_encoded, 1024, 0, fh),
              self.content[:4],
            )
        finally:
            self.filesystem.release(self.dest_file_encoded, flags, fh)

    def test_truncate_open_rdonly_open_wronly_twice(self):
        self.filesystem.truncate(self.dest_file_encoded, 4)
        fh_rdonly = self.filesystem.open(self.dest_file_encoded, os.O_RDONLY)
        try:
            fh_wronly1 = self.filesystem.open(
              self.dest_file_encoded,
              os.O_WRONLY,
            )
            try:

                fh_wronly2 = self.filesystem.open(
                  self.dest_file_encoded,
                  os.O_WRONLY,
                )
                self.filesystem.release(
                  self.dest_file_encoded,
                  os.O_WRONLY,
                  fh_wronly2,
                )

            finally:
                self.filesystem.release(
                  self.dest_file_encoded,
                  os.O_WRONLY,
                  fh_wronly1,
                )

        finally:
            self.filesystem.release(
              self.dest_file_encoded,
              os.O_RDONLY,
              fh_rdonly,
            )

manager.add_test_case_class(TruncateTestCase)
manager.add_test_case_class(mixin_unicode(TruncateTestCase))


class UnlinkTestCase(_BasePyTagsFileSystemTestCase):
    def test_not_supported(self):
        try:
            self.filesystem.unlink(None)
        except FuseError, e:
            self.assertEqual(e.errno, errno.ENOSYS)
        else:
            assert False

manager.add_test_case_class(UnlinkTestCase)
manager.add_test_case_class(mixin_unicode(UnlinkTestCase))


class UtimensTestCase(_BaseSingleFileOperationTestCase):
    def test(self):
        now = time.time()
        self.filesystem.utimens(self.dest_file_encoded, (now, 0))
        stat_result = os.stat(self.source_file)
        self.assertEqual(int(stat_result.st_mtime), 0)
        self.assertEqual(int(stat_result.st_atime), int(now))

        now = time.time()
        self.filesystem.utimens(self.dest_file_encoded, (0, now))
        stat_result = os.stat(self.source_file)
        self.assertEqual(int(stat_result.st_mtime), int(now))
        self.assertEqual(int(stat_result.st_atime), 0)

manager.add_test_case_class(UtimensTestCase)
manager.add_test_case_class(mixin_unicode(UtimensTestCase))


class WriteTestCase(_BaseSingleFileOperationTestCase):
    def test(self):
        content = 'abc\ndef\nghi\n'
        flags = os.O_RDWR
        fh = self.filesystem.open(self.dest_file_encoded, flags)
        try:
            self.filesystem.write(
              self.dest_file_encoded,
              content,
              0,
              fh,
            )
            read_content = self.filesystem.read(
              self.dest_file_encoded,
              1024,
              0,
              fh,
            )
        finally:
            self.filesystem.release(self.dest_file_encoded, flags, fh)
        self.assertEqual(content, read_content)

manager.add_test_case_class(WriteTestCase)
manager.add_test_case_class(mixin_unicode(WriteTestCase))


###


class FrozenPathTestCase(_BaseSingleFileOperationTestCase):
    def get_argv(self):
        return [
          'pytagsfs',
          '-o',
          (
            'metastores=pytagsfs.metastore.testlines.TestLinesMetaStore,'
            'format=/%a'
          ),
          self.source_dir.encode(ENCODING),
          'mnt',
        ]

    def get_content(self):
        return '%s\n' % self.p('foo').encode(ENCODING)

    def test_open_writable_once(self):
        flags = os.O_RDWR
        qux = self.p(u'qux').encode(ENCODING)

        fh = self.filesystem.open(self.dest_file_encoded, flags)
        try:

            # File should be reachable via old fake path.
            self.filesystem.getattr(self.dest_file_encoded)

            # Write the new content -- will eventually cause the file's fake
            # path to change.
            self.filesystem.write(
              self.dest_file_encoded,
              '%s\n' % qux,
              0,
              fh,
            )

            # The file can now be reached via two different fake paths.
            # One is frozen, the other is the new fake path.
            self.filesystem.getattr(self.dest_file_encoded)
            self.filesystem.getattr('/%s' % qux)

        finally:
            self.filesystem.release(self.dest_file_encoded, flags, fh)

        # Now the file can only be reached via the new fake path.
        self.assertRaises(
          FuseError,
          self.filesystem.getattr,
          self.dest_file_encoded,
        )
        self.filesystem.getattr('/%s' % qux)

    def test_open_writable_twice(self):
        flags = os.O_RDWR
        qux = self.p(u'qux').encode(ENCODING)

        fh1 = self.filesystem.open(self.dest_file_encoded, flags)
        try:

            fh2 = self.filesystem.open(self.dest_file_encoded, flags)
            try:

                # File should be reachable via old fake path.
                self.filesystem.getattr(self.dest_file_encoded)

                # Write the new content -- will eventually cause the file's
                # fake path to change.
                self.filesystem.write(
                  self.dest_file_encoded,
                  '%s\n' % qux,
                  0,
                  fh2,
                )

                # The file can now be reached via two different fake paths.
                # One is frozen, the other is the new fake path.
                self.filesystem.getattr(self.dest_file_encoded)
                self.filesystem.getattr('/%s' % qux)

            finally:
                self.filesystem.release(self.dest_file_encoded, flags, fh2)

            # The file can now be reached via two different fake paths.
            # One is frozen, the other is the new fake path.
            self.filesystem.getattr(self.dest_file_encoded)
            self.filesystem.getattr('/%s' % qux)

        finally:
            self.filesystem.release(self.dest_file_encoded, flags, fh1)

        # Now the file can only be reached via the new fake path.
        self.assertRaises(
          FuseError,
          self.filesystem.getattr,
          self.dest_file_encoded,
        )
        self.filesystem.getattr('/%s' % qux)

manager.add_test_case_class(FrozenPathTestCase)
manager.add_test_case_class(mixin_unicode(FrozenPathTestCase))


class GetattrWithSymlinkTestCase(_BasePyTagsFileSystemTestCase):
    filename = None
    source_file = None
    dest_file = None
    dest_file_encoded = None

    def build_source_tree(self):
        super(GetattrWithSymlinkTestCase, self).build_source_tree()
        self.filename = self.p('foo')
        self.source_file = os.path.join(self.source_dir, self.filename)
        self.dest_file = join_path_abs([self.filename])
        self.dest_file_encoded = self.dest_file.encode(ENCODING)
        os.symlink('/dev/null', self.source_file)

    def remove_source_tree(self):
        os.unlink(self.source_file)
        super(GetattrWithSymlinkTestCase, self).remove_source_tree()

    def test(self):
        # Symlinks are rejected.  This file should not appear in the virtual
        # tree.
        self.assertRaises(
          FuseError,
          self.filesystem.getattr,
          self.dest_file_encoded,
        )

manager.add_test_case_class(GetattrWithSymlinkTestCase)
manager.add_test_case_class(mixin_unicode(GetattrWithSymlinkTestCase))
