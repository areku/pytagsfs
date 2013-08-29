# coding: utf-8

# Copyright (c) 2007-2009 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

from sclapp import locale

import sys, os, time, traceback, stat, shutil, errno, random, glob, string
from subprocess import (
  Popen,
  PIPE,
  STDOUT,
)
from threading import Thread

from sclapp.shell import (
  Shell,
  CommandFailed,
  shinterp,
)
from sclapp.processes import BackgroundCommand

from pytagsfs.fs import UMOUNT_COMMAND
from pytagsfs.metastore.mutagen_ import MutagenFileMetaStore
from pytagsfs.util import unsafe_truncate
from pytagsfs.fuselib import Fuse

from common import (
  PLATFORM,
  DATA_DIR,
  TestWithDir,
  mixin_unicode,
  sleep_until,
)
from manager import manager


PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES_ROOT = os.path.join(PACKAGE_ROOT, 'modules')

PYTHON_EXECUTABLE = sys.executable
PYTAGSFS_EXECUTABLE = os.path.join(PACKAGE_ROOT, 'pytagsfs')

UMOUNT_RETRY_COUNT = 5
UMOUNT_RETRY_DELAY = 5


user_encoding = locale.getpreferredencoding()


def get_returncode_output(args):
    popen = Popen(args, stdout = PIPE, stderr = STDOUT)
    output = popen.stdout.read()
    returncode = popen.wait()
    return returncode, output


class ErrorOnError(Exception):
    def __init__(self, original_traceback, new_traceback):
        self.original_traceback = original_traceback
        self.new_traceback = new_traceback
        Exception.__init__(self, original_traceback, new_traceback)

    def __str__(self):
        return '\n'.join([
          '*** Caught an exception while cleaning up after an exception. ***',
          '',
          '=== Traceback for original exception ===',
          self.original_traceback,
          '',
          '=== Traceback for new exception ===',
          self.new_traceback,
        ])

    mount_parameters = None


class FileNotTaggableError(Exception):
    pass


def add_blackbox_test_class(cls):
    manager.add_test_case_class(cls)
    manager.add_test_case_class(mixin_singlethreaded(cls))


class AudioFormatMixin(object):
    def assertFilesHaveSameAudioContent(self, filename1, filename2):
        if self.get_audio_data(filename1) != self.get_audio_data(filename2):
            raise AssertionError

    def get_audio_data(self, filename):
        f = open(filename, 'rb')
        try:
            data = f.read()
        finally:
            f.close()
        return self.decode_audio_data(data)

    def decode_audio_data(self, data):
        popen = Popen(
          self.decode_args,
          stdin = PIPE,
          stdout = PIPE,
          stderr = PIPE,
        )
        stdoutdata, stderrdata = popen.communicate(data)
        if popen.returncode != 0:
            raise AssertionError(
              'subprocess failed (%u, %r)' % (popen.returncode, stderrdata)
            )
        if stderrdata:
            sys.stderr.write(stderrdata)
        return stdoutdata

    def p(self, s):
        s = super(AudioFormatMixin, self).p(s)
        return s.replace(u'ext', self.ext)


class OggMixin(AudioFormatMixin):
    ext = 'ogg'
    decode_args = [
      'ogg123',
      '--quiet',
      '--device',
      'raw',
      '--file',
      '-',
      '-',
    ]


class FlacMixin(AudioFormatMixin):
    ext = 'flac'
    decode_args = [
      'flac',
      '--silent',
      '--decode',
      '--stdout',
      '-',
    ]


class Mp3Mixin(AudioFormatMixin):
    ext = 'mp3'
    decode_args = [
      'madplay',
      '--quiet',
      '--output',
      'raw:-',
      '-',
    ]


class SingleThreadedMixin(object):
    def get_extra_options(self):
        return ['-s']


def mixin_singlethreaded(cls):
    newcls = type(
      'SingleThreaded%s' % cls.__name__,
      (SingleThreadedMixin, cls),
      {},
    )
    newcls.__module__ = cls.__module__
    return newcls


class _BaseBlackboxTestCase(TestWithDir):
    test_dir_prefix = 'blk'

    sh = None

    umount_cmd = None

    # Indicates that the TestCase requires that the system has non-broken mmap
    # semantics:
    requires_nonbroken_mmap = False

    test_method_name = None

    filesystem_process = None

    def __init__(self, methodName = 'runTest'):
        # The unittest module in Python 2.4 saves methodName as
        # __testMethodName, but in Python 2.5, it is _testMethodName.  We skirt
        # this incompatible change by saving it under our own name,
        # test_method_name.
        self.test_method_name = methodName

        super(_BaseBlackboxTestCase, self).__init__(methodName = methodName)

    def setUp(self):
        super(_BaseBlackboxTestCase, self).setUp()

        shell = '/bin/sh'

        returncode, output = get_returncode_output([shell, '--version'])
        if (returncode == 0) and ('bash' in output):
            shell = '%s --posix --noediting' % shell

        python_path_parts = [MODULES_ROOT]
        if 'PYTHONPATH' in os.environ:
            python_path_parts.append(os.environ['PYTHONPATH'])
        os.environ['PYTHONPATH'] = ':'.join(python_path_parts)

        # sh inherits os.environ
        self.sh = Shell(shell = shell, delaybeforesend = 0)

        returncode, output = get_returncode_output(['which', 'fusermount'])
        if returncode == 0:
            self.umount_cmd = 'fusermount -u'
        else:
            returncode, output = get_returncode_output(['which', 'umount'])
            if returncode == 0:
                self.umount_cmd = 'umount'
            else:
                raise AssertionError(
                  'no valid umount command could be determined'
                )

        # Some systems (Mac OSX, for example), have somewhat small limitations
        # on the length of mount point paths.  This caused problems in the past
        # when the test name (which can be quite long) was used as the
        # directory name.  Consequently, our test directory ($PWD, here,
        # created via TestWithDir) must have a reasonably short path.

        test_name = '%s.%s' % (self.__class__.__name__, self.test_method_name)
        self.test_name_file = os.path.join(self.test_dir, 'test_name')

        # Store the test name in a file so that the test tree can be linked
        # to the test that failed for debugging.
        self.sh.execute('echo ? >?', test_name, self.test_name_file)

        self.wd = os.getcwd()
        os.chdir(self.test_dir)
        self.sh.pushd(self.test_dir)

        self.sh.execute('mkdir -p mnt source')
        self.build_tree()

    def tearDown(self):
        os.chdir(self.wd)

        self.sh.popd()
        self.sh.exit()
        del self.sh

        super(_BaseBlackboxTestCase, self).tearDown()

    def p(self, s):
        return unicode(s)

    def get_audio_data(self, filename):
        raise NotImplementedError

    @classmethod
    def get_tags(cls, filename):
        return MutagenFileMetaStore.tags_class(filename)

    @classmethod
    def get_tag(cls, filename, tag):
        return cls.get_tags(filename)[tag]

    @classmethod
    def set_tag(cls, filename, tag, value):
        tags = cls.get_tags(filename)
        if tags is None:
            raise FileNotTaggableError(filename)
        tags[tag] = value
        tags.save()

    def assertFilesHaveSameTags(self, filename1, filename2):
        self.assertEqual(self.get_tags(filename1), self.get_tags(filename2))

    def get_options(self):
        options = [
          '-o',
          ','.join(self.get_mount_options()),
          os.path.join(self.test_dir, 'source'),
          os.path.join(self.test_dir, 'mnt'),
        ]
        options.extend(self.get_extra_options())
        return options

    def get_mount_options(self):
        mount_parameters = dict(self.get_mount_parameters())
        mount_options = ['debug']
        if mount_parameters.get('sourcetreerep', None):
            mount_options.append(
              'sourcetreerep=%s' % mount_parameters['sourcetreerep']
            )
        if mount_parameters.get('sourcetreemon', None):
            mount_options.append(
              'sourcetreemon=%s' % mount_parameters['sourcetreemon']
            )
        if mount_parameters.get('pathstore', None):
            mount_options.append(
              'pathstore=%s' % mount_parameters['pathstore']
            )
        mount_options.extend(self.get_extra_mount_options())
        return mount_options

    def get_extra_options(self):
        return []

    def get_extra_mount_options(self):
        return []

    def get_mount_parameters(self):
        return {}

    def mount(self):
        args = [PYTHON_EXECUTABLE, PYTAGSFS_EXECUTABLE]
        args.extend(self.get_options())

        mount_cmd = shinterp.interpolate(' '.join(len(args) * '?'), *args)
        self.sh.execute('mount_cmd=?', mount_cmd)
        self.sh.execute('echo "${mount_cmd}" >mount_cmd')

        self.filesystem_process = BackgroundCommand(
          PYTHON_EXECUTABLE,
          args,
          stderr = 'logfile',
          stdout = 'logfile',
        )
        self.filesystem_process.run()

        sleep_until(lambda: (
          os.path.exists('mnt/.log')
        ))

        self.assertTrue(self.filesystem_process.isRunning())

        # Check that mnt is accessible:
        os.stat('mnt')

    def umount(self):
        # FIXME: If umount cannot be completed, we should probably send SIGKILL
        # to the filesystem process and make sure the umount succeeds after
        # that.  Otherwise, filesystem processes can persist uncleanly.

        try:
            # Filesystem process should still be running.
            self.assertTrue(self.filesystem_process.isRunning())

            # Check that mnt is accessible:
            os.stat('mnt')

            # Check for spurious tracebacks:
            self.assertFileDoesNotContain('logfile', 'Traceback')

        finally:
            try:
                self.sh.execute(UMOUNT_COMMAND % '"${PWD}/mnt"')
            except CommandFailed:
                for i in range(UMOUNT_RETRY_COUNT):
                    e = None
                    time.sleep(UMOUNT_RETRY_DELAY)
                    try:
                        self.sh.execute(UMOUNT_COMMAND % '"${PWD}/mnt"')
                    except CommandFailed, e:
                        pass
                    else:
                        break
                if e is not None:
                    raise

            sleep_until(lambda: (
              not self.filesystem_process.isRunning()
            ))
            self.assertEqual(self.filesystem_process.getExitStatus(), 0)
            self.assertEqual(self.filesystem_process.getExitSignal(), None)

    def clean_up(self):
        self.sh.execute('rm -f mount_cmd')
        self.sh.execute('rm -f logfile')
        self.sh.execute('rmdir mnt')
        self.sh.execute('rm -fR source')
        self.sh.execute('rm ?', self.test_name_file)


################################################################################


class _BasePathPatternBlackboxTestCase(_BaseBlackboxTestCase):
    def build_tree(self):
        self.sh.execute(u'mkdir -p source/a/b source/a source/x')
        self.sh.execute(u'touch source/a/b/c source/a/• source/x/y')
        self.sh.execute(u'chmod 0644 source/a/b/c source/a/• source/x/y')


class SimpleFilenamePatternTestCase(_BasePathPatternBlackboxTestCase):
    def get_extra_mount_options(self):
        return ['format=/%f']

    def test_read_dir(self):
        self.mount()
        try:
            self.assertEqual(
              set(f for f in os.listdir(u'mnt') if not f.startswith('.')),
              set([u'c', u'y', u'•']),
            )
        finally:
            self.umount()
        self.clean_up()

    def test_add_empty_file(self):
        self.mount()
        try:
            self.sh.execute('touch source/a/b/d')

            sleep_until(lambda: (
              os.path.exists('mnt/d')
            ))

            self.assertFileExists('mnt/d')
        finally:
            self.umount()
        self.clean_up()

add_blackbox_test_class(SimpleFilenamePatternTestCase)


class SourceExcludeTestCase(_BasePathPatternBlackboxTestCase):
    def get_extra_mount_options(self):
        return ['format=/%f', 'srcfilter=!\/c$']

    def test_source_exclusion(self):
        self.mount()
        try:
            filenames = os.listdir(u'mnt')
            assert (u'c' not in filenames), repr(filenames)
        finally:
            self.umount()
        self.clean_up()

add_blackbox_test_class(SourceExcludeTestCase)


class DestExcludeTestCase(_BasePathPatternBlackboxTestCase):
    def get_extra_mount_options(self):
        return ['format=/%f', 'srcfilter=!\/c$']

    def test_dest_exclusion(self):
        self.mount()
        try:
            filenames = os.listdir(u'mnt')
            assert (u'c' not in filenames), repr(filenames)
        finally:
            self.umount()
        self.clean_up()

add_blackbox_test_class(DestExcludeTestCase)


class _BasePathPatternUpdatesTestCase(_BasePathPatternBlackboxTestCase):
    def get_extra_mount_options(self):
        return ['format=/%p/%f']


class PathPatternSourceTreeUpdatesTestCase(_BasePathPatternUpdatesTestCase):
    def test_update_file_contents(self):
        self.mount()
        try:
            content = 'foo\n'

            orig_mtime = os.stat('mnt/b/c').st_mtime

            f = open('source/a/b/c', 'w')
            try:
                f.write(content)
            finally:
                f.close()

            sleep_until(lambda: (
              os.stat('mnt/b/c').st_mtime != orig_mtime
            ))

            self.assertFileContent('mnt/b/c', content)
        finally:
            self.umount()
        self.clean_up()

    def test_update_mtime(self):
        self.mount()
        try:
            stat_a_src = os.stat('source/a/b/c')
            stat_a_dst = os.stat('mnt/b/c')

            stat_a_dst_dir = os.stat('mnt/b')

            self.assertEqual(stat_a_src.st_mtime, stat_a_dst.st_mtime)
            self.assertEqual(stat_a_src.st_mtime, stat_a_dst_dir.st_mtime)

            # Make sure enough time passes for timestamps to change.
            time.sleep(1)

            os.utime('source/a/b/c', None)

            # Wait for dest file mtime to change:
            sleep_until(lambda: (
              os.stat('mnt/b/c').st_mtime != stat_a_dst.st_mtime
            ))

            stat_b_src = os.stat('source/a/b/c')
            stat_b_dst = os.stat('mnt/b/c')

            stat_b_dst_dir = os.stat('mnt/b')

            self.assertEqual(stat_b_src.st_mtime, stat_b_dst.st_mtime)
            self.assertEqual(stat_b_src.st_mtime, stat_b_dst_dir.st_mtime)

            assert stat_a_src.st_mtime < stat_b_src.st_mtime
            assert stat_a_dst.st_mtime < stat_b_dst.st_mtime
        finally:
            self.umount()
        self.clean_up()

    def test_update_mode(self):
        self.mount()
        try:
            stat_a_src = os.stat('source/a/b/c')
            stat_a_dst = os.stat('mnt/b/c')

            mode_a_src = stat.S_IMODE(stat_a_src.st_mode)
            mode_a_dst = stat.S_IMODE(stat_a_dst.st_mode)

            self.assertEqual(mode_a_src, 0644)
            self.assertEqual(mode_a_dst, 0644)

            new_mode = (mode_a_src & 0000) | 0600

            os.chmod('source/a/b/c', new_mode)

            # Wait for dest file mode to change:
            sleep_until(lambda: (
              stat.S_IMODE(os.stat('mnt/b/c').st_mode) != mode_a_dst
            ))

            stat_b_src = os.stat('source/a/b/c')
            stat_b_dst = os.stat('mnt/b/c')

            mode_b_src = stat.S_IMODE(stat_b_src.st_mode)
            mode_b_dst = stat.S_IMODE(stat_b_dst.st_mode)

            self.assertEqual(mode_b_src, 0600)
            self.assertEqual(mode_b_dst, 0600)
        finally:
            self.umount()
        self.clean_up()

    def test_simple_rename(self):
        self.mount()
        try:
            os.makedirs('source/m/n')
            os.rename('source/a/b/c', 'source/m/n/o')

            sleep_until(lambda: (
              os.path.exists('mnt/n/o')
            ))

            self.assertFileDoesNotExist('mnt/b/c')
            self.assertFileExists('mnt/n/o')
        finally:
            self.umount()
        self.clean_up()

add_blackbox_test_class(PathPatternSourceTreeUpdatesTestCase)


# FIXME: Unicode version of this TestCase is necessary.

class PathPatternDestTreeUpdatesTestCase(_BasePathPatternUpdatesTestCase):
    def test_write_truncate(self):
        self.mount()
        try:
            f = open('mnt/b/c', 'w')
            f.write('foo\n')
            f.close()
            self.assertFileContent('mnt/b/c', 'foo\n')
        finally:
            self.umount()
        self.clean_up()

    def test_append(self):
        self.mount()
        try:
            f = open('mnt/b/c', 'w')
            f.write('foo\nbar\nbaz\n')
            f.close()
            self.assertFileContent('mnt/b/c', 'foo\nbar\nbaz\n')

            f = open('mnt/b/c', 'a')
            f.write('buz\n')
            f.close()
            self.assertFileContent('mnt/b/c', 'foo\nbar\nbaz\nbuz\n')
        finally:
            self.umount()
        self.clean_up()

    def test_overwrite_section(self):
        self.mount()
        try:
            f = open('mnt/b/c', 'w')
            f.write('foo\nbar\nbaz\n')
            f.close()
            self.assertFileContent('mnt/b/c', 'foo\nbar\nbaz\n')

            fd = os.open('mnt/b/c', os.O_RDWR)
            os.lseek(fd, 4, 0)
            os.write(fd, 'biz\n')
            os.close(fd)
            self.assertFileContent('mnt/b/c', 'foo\nbiz\nbaz\n')
        finally:
            self.umount()
        self.clean_up()

    def test_ftruncate(self):
        initial = 'foo\nbar\nbaz\nbiz\nbang\nboom'
        final = initial[:8]

        f = open('source/a/m', 'w')
        f.write(initial)
        f.close()

        self.mount()
        try:
            self.assertFileContent('mnt/a/m', initial)

            f = open('mnt/a/m', 'r+')
            try:
                self.assertEqual(f.read(), initial)
                f.truncate(8)
                f.seek(0)
                self.assertEqual(f.read(), final)
            finally:
                f.close()

            self.assertFileContent('mnt/a/m', final)
        finally:
            self.umount()
        self.clean_up()

    def test_seek_to_end(self):
        content = 'foo\nbar\nbaz\nbiz\nbang\nboom'

        f = open('source/a/m', 'w')
        try:
            f.write(content)
        finally:
            f.close()

        self.mount()
        try:
            self.assertFileContent('mnt/a/m', content)

            f = open('mnt/a/m', 'rb+')
            try:
                self.assertEqual(f.read(), content)
                f.seek(0, 2)
                self.assertEqual(f.tell(), len(content))
            finally:
                f.close()

            self.assertFileContent('mnt/a/m', content)
        finally:
            self.umount()
        self.clean_up()

    def test_write_past_end_and_seek_to_end(self):
        content = 'foo\nbar\n'
        last = 'baz\n'
        final = content + last

        f = open('source/a/m', 'w')
        try:
            f.write(content)
        finally:
            f.close()

        self.mount()
        try:
            self.assertFileContent('mnt/a/m', content)

            f = open('mnt/a/m', 'rb+')
            try:
                self.assertEqual(f.read(), content)
                f.seek(0, 2)
                f.write(last)
                f.seek(0)
                self.assertEqual(f.read(), final)
                f.seek(0, 2)
                self.assertEqual(f.tell(), len(final))
            finally:
                f.close()

            self.assertFileContent('mnt/a/m', final)
        finally:
            self.umount()
        self.clean_up()

    def test_update_mtime(self):
        self.mount()
        try:
            stat_a_src = os.stat('source/a/b/c')
            stat_a_dst = os.stat('mnt/b/c')

            stat_a_dst_dir = os.stat('mnt/b')

            self.assertEqual(stat_a_src.st_mtime, stat_a_dst.st_mtime)
            self.assertEqual(stat_a_src.st_mtime, stat_a_dst_dir.st_mtime)

            # Make sure enough time passes for timestamps to change.
            time.sleep(1)

            os.utime('mnt/b/c', None)

            stat_b_src = os.stat('source/a/b/c')
            stat_b_dst = os.stat('mnt/b/c')

            stat_b_dst_dir = os.stat('mnt/b')

            self.assertEqual(stat_b_src.st_mtime, stat_b_dst.st_mtime)
            self.assertEqual(stat_b_src.st_mtime, stat_b_dst_dir.st_mtime)

            assert stat_a_src.st_mtime < stat_b_src.st_mtime
            assert stat_a_dst.st_mtime < stat_b_dst.st_mtime
        finally:
            self.umount()
        self.clean_up()

    def test_update_mode(self):
        self.mount()
        try:
            stat_a_src = os.stat('source/a/b/c')
            stat_a_dst = os.stat('mnt/b/c')

            mode_a_src = stat.S_IMODE(stat_a_src.st_mode)
            mode_a_dst = stat.S_IMODE(stat_a_dst.st_mode)

            self.assertEqual(mode_a_src, 0644)
            self.assertEqual(mode_a_dst, 0644)

            new_mode = (mode_a_src & 0000) | 0600

            os.chmod('mnt/b/c', new_mode)

            stat_b_src = os.stat('source/a/b/c')
            stat_b_dst = os.stat('mnt/b/c')

            mode_b_src = stat.S_IMODE(stat_b_src.st_mode)
            mode_b_dst = stat.S_IMODE(stat_b_dst.st_mode)

            self.assertEqual(mode_b_src, 0600)
            self.assertEqual(mode_b_dst, 0600)
        finally:
            self.umount()
        self.clean_up()

add_blackbox_test_class(PathPatternDestTreeUpdatesTestCase)


################################################################################

class _BaseOperationTestCase(_BaseBlackboxTestCase):
    filename = None
    source_file = None
    dest_file = None
    content = None

    def build_tree(self):
        self.filename = self.p('foo')
        self.source_file = os.path.join('source', self.filename)
        self.dest_file = os.path.join('mnt', self.filename)
        self.content = 'foo\nbar\nbaz\n'

        f = open(self.source_file, 'w')
        try:
            f.write(self.content)
        finally:
            f.close()

    def get_extra_mount_options(self):
        return ['format=/%f']


class TruncateTestCase(_BaseOperationTestCase):
    def test_read_from_read_only_file(self):
        self.mount()
        try:
            # We use unsafe_truncate to guarantee use of truncate, not
            # ftruncate.
            unsafe_truncate(self.dest_file.encode(user_encoding), 4)
            # truncate does not affect the source file until the fake path has
            # been opened for writing.
            self.assertFileContent(self.source_file, self.content)
            # truncate should affect dest file immediately.
            self.assertFileContent(self.dest_file, self.content[:4])
            # truncate should not affect the source file even now, because the
            # fake path has not been opened for writing.
            self.assertFileContent(self.source_file, self.content)
        finally:
            self.umount()
        self.clean_up()

    def test_read_from_read_write_file(self):
        self.mount()
        try:
            # We use unsafe_truncate to guarantee use of truncate, not
            # ftruncate.
            unsafe_truncate(self.dest_file.encode(user_encoding), 4)
            # truncate does not affect source file until fake path has been
            # opened for writing.
            self.assertFileContent(self.source_file, self.content)
            # truncate should affect the fake path immediately.
            self.assertFileContent(
              self.dest_file, self.content[:4], mode = 'rb+')
            # truncate should affect the source file now because the fake path
            # was opened for writing.
            self.assertFileContent(self.source_file, self.content[:4])
        finally:
            self.umount()
        self.clean_up()

add_blackbox_test_class(TruncateTestCase)
add_blackbox_test_class(mixin_unicode(TruncateTestCase))


class FtruncateTestCase(_BaseOperationTestCase):
    def test(self):
        self.mount()
        try:
            f = open(self.dest_file.encode(user_encoding), 'rb+')
            try:
                os.ftruncate(f.fileno(), 4)
                self.assertFileContent(self.dest_file, self.content[:4])
                self.assertFileContent(self.source_file, self.content[:4])
            finally:
                f.close()
        finally:
            self.umount()
        self.clean_up()

add_blackbox_test_class(FtruncateTestCase)
add_blackbox_test_class(mixin_unicode(FtruncateTestCase))


################################################################################


class _BaseSourceTreeUpdatesTestCase(_BaseBlackboxTestCase):
    def get_extra_mount_options(self):
        return ['format=/%{artist} - %t.%e']

    def build_tree(self):
        self.data_file = self.p(os.path.join(DATA_DIR, 'silence.ext'))
        shutil.copy(self.data_file, self.p('source/foo.ext'))
        self.set_tag(self.p('source/foo.ext'), 'artist', self.p('bar'))
        self.set_tag(self.p('source/foo.ext'), 'title', self.p('baz'))

    def test_tag_change_causing_path_change(self):
        self.mount()
        try:
            self.set_tag(self.p('source/foo.ext'), 'artist', self.p('qux'))

            sleep_until(lambda: (
              os.path.exists(self.p('mnt/qux - baz.ext'))
            ))

            self.assertEqual(
              self.get_tag(self.p('mnt/qux - baz.ext'), 'artist'),
              [self.p('qux')],
            )
            self.assertFilesHaveSameAudioContent(
              self.data_file, self.p('mnt/qux - baz.ext'))
        finally:
            self.umount()
        self.clean_up()

    def test_tag_change_causing_new_fake_path(self):
        self.set_tag(self.p('source/foo.ext'), 'artist', [])
        self.mount()
        try:
            self.assertEqual(os.listdir('mnt'), ['.log'])
            self.set_tag(self.p('source/foo.ext'), 'artist', self.p('qux'))

            sleep_until(lambda: (
              os.path.exists(self.p('mnt/qux - baz.ext'))
            ))

            self.assertEqual(
              self.get_tag(self.p('mnt/qux - baz.ext'), 'artist'),
              [self.p('qux')],
            )
            self.assertFilesHaveSameAudioContent(
              self.data_file, self.p('mnt/qux - baz.ext'))
        finally:
            self.umount()
        self.clean_up()


class OggSourceTreeUpdatesTestCase(OggMixin, _BaseSourceTreeUpdatesTestCase):
    pass

add_blackbox_test_class(OggSourceTreeUpdatesTestCase)
add_blackbox_test_class(mixin_unicode(OggSourceTreeUpdatesTestCase))


class FlacSourceTreeUpdatesTestCase(FlacMixin, _BaseSourceTreeUpdatesTestCase):
    pass

add_blackbox_test_class(FlacSourceTreeUpdatesTestCase)
add_blackbox_test_class(mixin_unicode(FlacSourceTreeUpdatesTestCase))


class Mp3SourceTreeUpdatesTestCase(Mp3Mixin, _BaseSourceTreeUpdatesTestCase):
    pass

add_blackbox_test_class(Mp3SourceTreeUpdatesTestCase)
add_blackbox_test_class(mixin_unicode(Mp3SourceTreeUpdatesTestCase))


class _BaseDestTreeUpdatesTestCase(_BaseBlackboxTestCase):
    def get_extra_mount_options(self):
        return ['format=/%{artist} - %t.%e']

    def build_tree(self):
        self.data_file = self.p(os.path.join(DATA_DIR, 'silence.ext'))
        shutil.copy(self.data_file, self.p('source/foo.ext'))
        self.set_tag(self.p('source/foo.ext'), 'artist', self.p('bar'))
        self.set_tag(self.p('source/foo.ext'), 'title', self.p('baz'))

    def test_tag_change_causing_path_change(self):
        self.mount()
        try:
            self.set_tag(self.p('mnt/bar - baz.ext'), 'artist', self.p('qux'))
            self.assertEqual(
              self.get_tag(self.p('source/foo.ext'), 'artist'),
              [self.p('qux')],
            )
            self.assertFilesHaveSameAudioContent(
              self.data_file, self.p('mnt/qux - baz.ext'))
        finally:
            self.umount()
        self.clean_up()

    def test_remove_file(self):
        self.mount()
        try:
            os.unlink(self.p('source/foo.ext'))

            sleep_until(lambda: (
              not os.path.exists(self.p('mnt/bar - baz.ext'))
            ))

            self.assertEqual(os.listdir('mnt'), ['.log'])
        finally:
            self.umount()
        self.clean_up()


class OggDestTreeUpdatesTestCase(OggMixin, _BaseDestTreeUpdatesTestCase):
    pass

add_blackbox_test_class(OggDestTreeUpdatesTestCase)
add_blackbox_test_class(mixin_unicode(OggDestTreeUpdatesTestCase))


class FlacDestTreeUpdatesTestCase(FlacMixin, _BaseDestTreeUpdatesTestCase):
    pass

add_blackbox_test_class(FlacDestTreeUpdatesTestCase)
add_blackbox_test_class(mixin_unicode(FlacDestTreeUpdatesTestCase))


class Mp3DestTreeUpdatesTestCase(Mp3Mixin, _BaseDestTreeUpdatesTestCase):
    pass

add_blackbox_test_class(Mp3DestTreeUpdatesTestCase)
add_blackbox_test_class(mixin_unicode(Mp3DestTreeUpdatesTestCase))


################################################################################


class _BaseRenameTestCase(_BaseBlackboxTestCase):
    def build_tree(self):
        shutil.copy(
          self.p(os.path.join(DATA_DIR, 'silence.ext')),
          self.p('source/foo.ext'),
        )
        self.set_tag(self.p('source/foo.ext'), 'artist', self.p('bar'))
        self.set_tag(self.p('source/foo.ext'), 'title', self.p('baz'))

    def get_extra_mount_options(self):
        return ['format=/%a/%t.%e']

    def test_simple_rename(self):
        self.mount()
        try:
            os.rename(
              self.p(os.path.join('mnt', 'bar', 'baz.ext')),
              self.p(os.path.join('mnt', 'bar', 'qux.ext')),
            )
            self.assertFilesHaveSameAudioContent(
              self.p(os.path.join(DATA_DIR, 'silence.ext')),
              self.p(os.path.join('mnt', 'bar', 'qux.ext')),
            )
            tags = self.get_tags(self.p(os.path.join('mnt', 'bar', 'qux.ext')))
            self.assertEqual(tags['artist'], [self.p('bar')])
            self.assertEqual(tags['title'], [self.p('qux')])
        finally:
            self.umount()
        self.clean_up()

    def test_rename_across_directories(self):
        self.mount()
        try:
            os.mkdir(self.p(os.path.join('mnt', 'qux')))
            os.rename(
              self.p(os.path.join('mnt', 'bar', 'baz.ext')),
              self.p(os.path.join('mnt', 'qux', 'baz.ext')),
            )
            self.assertFilesHaveSameAudioContent(
              self.p(os.path.join(DATA_DIR, 'silence.ext')),
              self.p(os.path.join('mnt', 'qux', 'baz.ext')),
            )
            tags = self.get_tags(self.p(os.path.join('mnt', 'qux', 'baz.ext')))
            self.assertEqual(tags['artist'], [self.p('qux')])
            self.assertEqual(tags['title'], [self.p('baz')])
        finally:
            self.umount()
        self.clean_up()

    def test_directory_rename(self):
        self.mount()
        try:
            os.rename(
              self.p(os.path.join('mnt', 'bar')),
              self.p(os.path.join('mnt', 'qux')),
            )
            self.assertFilesHaveSameAudioContent(
              self.p(os.path.join(DATA_DIR, 'silence.ext')),
              self.p(os.path.join('mnt', 'qux', 'baz.ext')),
            )
            tags = self.get_tags(self.p(os.path.join('mnt', 'qux', 'baz.ext')))
            self.assertEqual(tags['artist'], [self.p('qux')])
            self.assertEqual(tags['title'], [self.p('baz')])
        finally:
            self.umount()
        self.clean_up()

    def test_invalid_rename(self):
        self.mount()
        try:
            try:
                os.rename(
                  self.p(os.path.join('mnt', 'bar', 'baz.ext')),
                  self.p(os.path.join('mnt', 'bar', 'qux.boink')),
                )
            except OSError, e:
                self.assertEqual(e.errno, errno.EINVAL)
        finally:
            self.umount()
        self.clean_up()


class OggRenameTestCase(OggMixin, _BaseRenameTestCase):
    pass

add_blackbox_test_class(OggRenameTestCase)
add_blackbox_test_class(mixin_unicode(OggRenameTestCase))


class FlacRenameTestCase(FlacMixin, _BaseRenameTestCase):
    pass

add_blackbox_test_class(FlacRenameTestCase)
add_blackbox_test_class(mixin_unicode(FlacRenameTestCase))


class Mp3RenameTestCase(Mp3Mixin, _BaseRenameTestCase):
    pass

add_blackbox_test_class(Mp3RenameTestCase)
add_blackbox_test_class(mixin_unicode(Mp3RenameTestCase))


################################################################################


class MkdirRmdirTagsTestCase(_BaseBlackboxTestCase):
    def get_extra_mount_options(self):
        return ['format=/%g/%{artist}/%t.%e']

    def build_tree(self):
        data_file = os.path.join(DATA_DIR, 'silence.flac')

        for num in (1, 2, 3, 4):
            self.sh.execute('cp ? ?', data_file, 'source/silence%u.flac' % num)

        for num, artist, title, genre in (
          (1, 'foo', 'bar', 'Rock'),
          (2, 'foo', 'baz', 'Rock'),
          (3, 'bink', 'bonk', 'Rap'),
          (4, 'fink', 'fonk', 'Country'),
        ):
            file = 'source/silence%u.flac' % num
            self.set_tag(file, 'artist', artist)
            self.set_tag(file, 'title', title)
            self.set_tag(file, 'genre', genre)

    def test_mkdir_rmdir(self):
        self.mount()
        try:
            dir = 'mnt/Honky Tonk'
            self.sh.execute('mkdir ?', dir)
            self.assertDirectoryExists(dir)
            self.sh.execute('rmdir ?', dir)
            self.assertDirectoryDoesNotExist(dir)
        finally:
            self.umount()
        self.clean_up()

    def test_rename_empty_dir(self):
        self.mount()
        try:
            dir = 'mnt/Honky Tonk'
            dir2 = 'mnt/Soul'
            self.sh.execute('mkdir ?', dir)
            self.assertDirectoryExists(dir)
            self.sh.execute('mv ? ?', dir, dir2)
            self.assertDirectoryDoesNotExist(dir)
            self.sh.execute('ls ?', dir2)
            self.assertRaises(CommandFailed, self.sh.execute, 'ls ?/*', dir2)
            self.sh.execute('rmdir ?', dir2)
            self.assertDirectoryDoesNotExist(dir2)
        finally:
            self.umount()
        self.clean_up()

    def test_move_files_into_new_directory(self):
        self.mount()
        try:
            self.sh.execute('mkdir mnt/Rock/biz')
            self.assertDirectoryExists('mnt/Rock/biz')

            self.sh.execute('mv mnt/Rock/foo/* mnt/Rock/biz/')
            self.assertDirectoryDoesNotExist('mnt/Rock/foo')

            filenames = os.listdir(u'mnt/Rock/biz')
            self.assertEqual(len(filenames), 2)
            for filename in filenames:
                tags = self.get_tags(os.path.join(u'mnt/Rock/biz', filename))
                self.assertEqual(tags['artist'], [u'biz'])
        finally:
            self.umount()
        self.clean_up()

add_blackbox_test_class(MkdirRmdirTagsTestCase)


################################################################################


class StatvfsTestCase(_BasePathPatternBlackboxTestCase):
    def get_extra_mount_options(self):
        return ['format=/%f']

    def assertAlmostEqualInt(self, a, b):
        self.assertTrue(int(0.9 * b) <= a <= int(1.1 * b))

    def test(self):
        # Some statvfs values may be slightly different because they may have
        # changed between statvfs calls on source and mnt (mostly those related
        # to free space).  For these, we use assertAlmostEqualInt instead of
        # assertEqual.

        self.mount()
        try:
            statvfs_source = os.statvfs('source')
            statvfs_mnt = os.statvfs('mnt')
            self.assertEqual(statvfs_source.f_bsize, statvfs_mnt.f_bsize)
            self.assertEqual(statvfs_source.f_frsize, statvfs_mnt.f_frsize)
            self.assertEqual(statvfs_source.f_blocks, statvfs_mnt.f_blocks)
            self.assertAlmostEqualInt(
              statvfs_mnt.f_bfree,
              statvfs_source.f_bfree,
            )
            self.assertAlmostEqualInt(
              statvfs_mnt.f_bavail,
              statvfs_source.f_bavail,
            )
            self.assertEqual(statvfs_source.f_files, statvfs_mnt.f_files)
            self.assertAlmostEqualInt(
              statvfs_mnt.f_ffree,
              statvfs_source.f_ffree,
            )
            self.assertAlmostEqualInt(
              statvfs_mnt.f_favail,
              statvfs_source.f_favail,
            )
            #f_fsid is not supported by os.statvfs_result
            self.assertTrue(type(statvfs_mnt.f_flag), int)
            self.assertEqual(statvfs_source.f_namemax, statvfs_mnt.f_namemax)
        finally:
            self.umount()
        self.clean_up()

add_blackbox_test_class(StatvfsTestCase)


################################################################################


class LogFileTestCase(_BasePathPatternBlackboxTestCase):
    def get_extra_mount_options(self):
        return ['verbosity=debug']

    def test_log_file_exists(self):
        self.mount()
        try:
            self.assertFileExists('mnt/.log')
        finally:
            self.umount()
        self.clean_up()

    def test_log_file_receives_messages(self):
        self.mount()
        try:
            from pytagsfs import __version__ as version
            self.assertFileContains('mnt/.log', 'pytagsfs version %s' % version)
        finally:
            self.umount()
        self.clean_up()

add_blackbox_test_class(LogFileTestCase)


class LogSizeTestCase(_BasePathPatternBlackboxTestCase):
    logsize = 8

    def get_extra_mount_options(self):
        return ['verbosity=debug', 'logsize=%u' % self.logsize]

    def test_log_size(self):
        self.mount()
        try:
            f = open('mnt/.log', 'r')
            length = len(f.read())
            try:
                assert length == self.logsize, (
                  'Expected length to be %u, got %u instead.' % (
                    self.logsize, length))
            finally:
                f.close()
        finally:
            self.umount()
        self.clean_up()

add_blackbox_test_class(LogSizeTestCase)


class ProfilingTestCase(_BasePathPatternBlackboxTestCase):
    def get_extra_mount_options(self):
        return ['profile']

    def test(self):
        self.mount()
        try:
            f = open('mnt/.log', 'r')
            length = os.stat('mnt/.log').st_size
            try:
                content = f.read(length).decode('utf-8', 'replace')
            finally:
                f.close()
            lines = content.split('\n')
            for line in reversed(lines):
                if 'PROF' in line:
                    break
            parts = line.split()
            self.assertEqual(parts[1], 'PROF')
            self.assertTrue(hasattr(Fuse, parts[3]))
        finally:
            self.umount()
        self.clean_up()

add_blackbox_test_class(ProfilingTestCase)


################################################################################


class _BaseMmapTestCase(_BaseBlackboxTestCase):
    content = 'foo\nbar\n'
    file_obj = None
    map = None

    def get_extra_mount_options(self):
        return ['format=/%f']

    def build_tree(self):
        f = open('source/foo.txt', 'w')
        try:
            f.write(self.content)
        finally:
            f.close()

    def _open_file(self):
        raise NotImplementedError

    def _mmap(self, fileno, filesize):
        raise NotImplementedError

    def _init_mmap(self):
        self.file_obj = self._open_file()
        try:
            self.file_obj.seek(0, 2)
            filesize = self.file_obj.tell()
            self.map = self._mmap(
              self.file_obj.fileno(),
              filesize,
            )
        except:
            self._de_init_mmap()
            raise

    def _de_init_mmap(self):
        try:
            if self.map:
                self.map.close()
                del self.map
        finally:
            if self.file_obj:
                self.file_obj.close()
                del self.file_obj


class ReadOnlyMmapTestCase(_BaseMmapTestCase):
    def _open_file(self):
        return open('mnt/foo.txt', 'rb')

    def _mmap(self, fileno, filesize):
        import mmap
        return mmap.mmap(
          fileno,
          filesize,
          access = mmap.ACCESS_READ,
        )

    def test_read(self):
        self.mount()
        try:
            self._init_mmap()
            try:
                self.assertEqual(self.map[:], self.content)
            finally:
                self._de_init_mmap()
        finally:
            self.umount()
        self.clean_up()

add_blackbox_test_class(ReadOnlyMmapTestCase)


class _BaseReadWriteMmapTestCase(_BaseMmapTestCase):
    def _open_file(self):
        return open('mnt/foo.txt', 'rb+')

    def test_range_assignment(self):
        self.mount()
        try:
            self._init_mmap()
            try:
                content = self.map[:]
                self.assertEqual(content, self.content)
                self.map[0:4] = 'baz\n'
                self.assertEqual(self.map[:], 'baz\nbar\n')
            finally:
                self._de_init_mmap()
        finally:
            self.umount()
        self.clean_up()


class CopyOnWriteReadWriteMmapTestCase(_BaseReadWriteMmapTestCase):
    def _mmap(self, fileno, filesize):
        import mmap
        return mmap.mmap(
          fileno,
          filesize,
          access = mmap.ACCESS_COPY,
        )

add_blackbox_test_class(CopyOnWriteReadWriteMmapTestCase)


# I don't know of any platforms that support this currently, but it
# should be implemented on most eventually.

class WriteThroughReadWriteMmapTestCase(_BaseReadWriteMmapTestCase):
    def _mmap(self, fileno, filesize):
        import mmap
        return mmap.mmap(
          fileno,
          filesize,
          access = mmap.ACCESS_WRITE,
        )


class WriteThroughNoSuchDeviceMmapTestCase(_BaseMmapTestCase):
    def _open_file(self):
        return open('mnt/foo.txt', 'rb+')

    def _mmap(self, fileno, filesize):
        import mmap
        return mmap.mmap(
          fileno,
          filesize,
          access = mmap.ACCESS_WRITE,
        )

    def test_init_mmap(self):
        self.mount()
        try:
            try:
                try:
                    self._init_mmap()
                except EnvironmentError, e:
                    if e.errno != errno.ENODEV:
                        raise
            finally:
                self._de_init_mmap()
        finally:
            self.umount()
        self.clean_up()


if PLATFORM in ('Linux', 'Darwin', 'BSD'):
    add_blackbox_test_class(WriteThroughNoSuchDeviceMmapTestCase)
else:
    add_blackbox_test_class(WriteThroughReadWriteMmapTestCase)


class MutagenMmapTestCase(_BaseMmapTestCase):
    def _open_file(self):
        return open('mnt/foo.txt', 'r+')

    def _mmap(self, fileno, filesize):
        return None

    def test_insert_bytes(self):
        from mutagen._util import insert_bytes

        expected_content = 'foo\nbaz\nbar\n'

        self.mount()
        try:
            self._init_mmap()
            try:
                insert_bytes(self.file_obj, 4, 4)
                self.file_obj.seek(4)
                self.file_obj.write('baz\n')
                self.file_obj.seek(0)
                content = self.file_obj.read()
                self.assertEqual(content, expected_content)

                self.file_obj.close()
                self.file_obj = self._open_file()
                content = self.file_obj.read()
                self.assertEqual(content, expected_content)
            finally:
                self._de_init_mmap()
        finally:
            self.umount()
        self.clean_up()

    def test_delete_bytes(self):
        from mutagen._util import delete_bytes

        expected_content = 'foo\n'

        self.mount()
        try:
            self._init_mmap()
            try:
                delete_bytes(self.file_obj, 4, 4)
                self.file_obj.seek(0)
                content = self.file_obj.read()
                self.assertEqual(content, expected_content)
                self.file_obj.close()

                self.file_obj = self._open_file()
                content = self.file_obj.read()
                self.assertEqual(content, expected_content)
            finally:
                self._de_init_mmap()
        finally:
            self.umount()
        self.clean_up()

add_blackbox_test_class(MutagenMmapTestCase)


class FuzzThread(Thread):
    _killed = None

    def kill(self):
        self._killed = True

    def sleep_random(self):
        time.sleep(random.random())

    def _select_random_path(self, root, predicate = (lambda path: True)):
        root = root.rstrip('/')
        all_files = []
        for dirpath, dirnames, filenames in os.walk(root):
            paths = [os.path.join(dirpath, dirname) for dirname in dirnames]
            paths.extend([
              os.path.join(dirpath, filename) for filename in filenames
            ])
            for path in paths:
                if predicate(path):
                    all_files.append(path)
        return random.choice(all_files)

    def select_random_virtual_file(self):
        return self._select_random_path(
          'mnt',
          (lambda path: ((path != 'mnt/.log') and os.path.isfile(path))),
        )

    def select_random_real_file(self):
        return self._select_random_path(
          'source',
          (lambda path: os.path.isfile(path)),
        )

    def select_random_virtual_directory(self):
        return self._select_random_path(
          'mnt',
          (lambda path: os.path.isdir(path)),
        )

    def select_random_real_directory(self):
        return self._select_random_path(
          'source',
          (lambda path: os.path.isdir(path)),
        )

    def run(self):
        while True:
            self.sleep_random()
            self.do_action()
            if self._killed:
                break


class StatFuzzThread(FuzzThread):
    def do_action(self):
        filename = self.select_random_virtual_file()
        try:
            os.stat(filename)
        except (OSError, IOError):
            pass


class ReadFuzzThread(FuzzThread):
    def do_action(self):
        filename = self.select_random_virtual_file()
        try:
            f = open(filename, 'r')
            try:
                f.seek(0, 2)
                size = f.tell()
                f.seek(random.randint(0, 2 * size))
                f.read(random.randint(0, 2 * size))
            finally:
                f.close()
        except (OSError, IOError):
            pass


class UtimeFuzzThread(FuzzThread):
    def do_action(self):
        filename = self.select_random_virtual_file()
        try:
            os.utime(filename, None)
        except (OSError, IOError):
            pass


class SetTagFuzzThread(FuzzThread):
    tags = ('artist', 'album', 'title')

    def do_action(self):
        filename = self.get_filename()
        try:
            _BaseBlackboxTestCase.set_tag(
              filename,
              random.choice(self.tags),
              ConcurrentFuzzTestCase.get_random_string(),
            )
        except (OSError, IOError, FileNotTaggableError):
            pass


class SetTagOnVirtualFileFuzzThread(SetTagFuzzThread):
    def get_filename(self):
        return self.select_random_virtual_file()


class SetTagOnRealFileFuzzThread(SetTagFuzzThread):
    def get_filename(self):
        return self.select_random_real_file()


class ConcurrentFuzzTestCase(_BaseBlackboxTestCase):
    num_threads = 10
    duration = 10
    thread_classes = (
      StatFuzzThread,
      ReadFuzzThread,
      UtimeFuzzThread,
      SetTagOnVirtualFileFuzzThread,
      SetTagOnRealFileFuzzThread,
    )

    def get_opts(self):
        return 'format=/%a/%l/%t.%e'

    @classmethod
    def get_random_string(cls):
        return ''.join([random.choice(string.letters) for i in range(16)])

    def build_tree(self):
        for source_path in glob.glob(os.path.join(DATA_DIR, '*')):
            dest_path = os.path.join(
              'source',
              os.path.basename(source_path),
            )
            shutil.copy(source_path, dest_path)
            try:
                self.set_tag(dest_path, 'artist', self.get_random_string())
                self.set_tag(dest_path, 'album', self.get_random_string())
                self.set_tag(dest_path, 'title', self.get_random_string())
            except FileNotTaggableError:
                # Note: file is left in place even though it won't appear in
                # mount tree.
                pass

    def test(self):
        self.mount()
        try:
            threads = []
            for i in range(self.num_threads):
                thread_cls = random.choice(self.thread_classes)
                threads.append(thread_cls())
            for thread in threads:
                thread.start()
            time.sleep(self.duration)
            for thread in threads:
                thread.kill()
                thread.join()
        finally:
            self.umount()
        self.clean_up()

add_blackbox_test_class(ConcurrentFuzzTestCase)
