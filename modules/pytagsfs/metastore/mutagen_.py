# coding: utf-8

# Copyright (c) 2007-2009 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import mutagen
from mutagen.id3 import ID3FileType
from mutagen.easyid3 import EasyID3
from mutagen.mp4 import MP4

from pytagsfs.metastore import MetaStore
from pytagsfs.values import Values
from pytagsfs.debug import log_info


class TranslatedMP4(MP4):
    '''
    Wrapper for mutagen.mp4.MP4 that translates funky MP4 keys to standard keys 
    common with other formats.
    '''

    KEYS = (
      (u'©nam'.encode('iso-8859-1'), 'title'),
      (u'titl'.encode('iso-8859-1'), 'title'),

      (u'©ART'.encode('iso-8859-1'), 'artist'),
      (u'arti'.encode('iso-8859-1'), 'artist'),

      (u'©alb'.encode('iso-8859-1'), 'album'),
      (u'albu'.encode('iso-8859-1'), 'album'),

      (u'©wrt'.encode('iso-8859-1'), 'writer'),

      (u'©day'.encode('iso-8859-1'), 'date'),

      (u'©gen'.encode('iso-8859-1'), 'genre'),
      (u'gnre'.encode('iso-8859-1'), 'genre'),

      (u'©too'.encode('iso-8859-1'), 'tool'),
      (u'©cmt'.encode('iso-8859-1'), 'comment'),
      (u'cpil'.encode('iso-8859-1'), 'compilation'),

      (u'trac'.encode('iso-8859-1'), 'tracknumber'),

      (u'disk'.encode('iso-8859-1'), 'disc'),
      (u'covr'.encode('iso-8859-1'), 'cover'),
    )

    def keys(self):
        ks = super(TranslatedMP4, self).keys()
        for k_native, k_translated in self.KEYS:
            if k_translated not in ks:
                if k_native in ks:
                    ks.append(k_translated)
        ks.sort()
        return ks

    def __getitem__(self, key):
        # If key is native, return it.  If it is translated, return the native
        # key value.
        keys = [item[0] for item in self.KEYS if item[1] == key]
        for k in [key] + keys:
            try:
                return super(TranslatedMP4, self).__getitem__(k)
            except KeyError:
                pass
        raise KeyError(key)

    def __setitem__(self, key, value):
        # If the key already exists as-is, maintain it:
        if key in super(TranslatedMP4, self).keys():
            super(TranslatedMP4, self).__setitem__(key, value)
            return

        # Enforce consistency between tracknumber/trac and trkn
        if key in ('tracknumber', 'trac'):
            if 'trkn' in self:
                int_value = int(value)
                if int_value > self['trkn'][0][1]:
                    raise ValueError('track number too big')
                self['trkn'][0] = (int_value, self['trkn'][0][1])

        # Enforce consistency between trkn and tracknumber
        if key == 'trkn':
            if 'tracknumber' in self:
                self['tracknumber'] = unicode(value[0])

        # Set native keys if this key is one of the known translated keys:
        found = False
        for k_native, k_translated in self.KEYS:
            if k_translated == key:
                super(TranslatedMP4, self).__setitem__(k_native, value)
                found = True

        if found:
            return

        # We don't know how to translate this key, so set it directly:
        super(TranslatedMP4, self).__setitem__(key, value)

    def __delitem__(self, key):
        # We actually delete this key and all translated keys known to
        # correspond with it.
        keys = [item[0] for item in self.KEYS if item[1] == key]
        for k in [key] + keys:
            try:
                super(TranslatedMP4, self).__delitem__(k)
            except KeyError:
                pass
        raise KeyError(key)

    def __contains__(self, key):
        return key in self.keys()


def SimpleMutagenFile(filename):
    f = mutagen.File(filename)
    if isinstance(f, ID3FileType):
        f = f.__class__(filename, ID3 = EasyID3)

        # Odd that this is necessary.  Is it a mutagen bug?
        # http://www.listen-project.org/ticket/714
        # http://www.listen-project.org/changeset/841
        if f.tags is None:
            f.tags = EasyID3()
    elif isinstance(f, MP4):
        f.__class__ = TranslatedMP4
    return f


MUTAGEN_FIELD_MAPPING = {
  'n': 'tracknumber',
  'a': 'artist',
  'c': 'composer',
  't': 'title',
  'l': 'album',
  'y': 'date',
  'g': 'genre',
}


def get_field_for_mutagen_field(mutagen_field):
    for field in MUTAGEN_FIELD_MAPPING:
        if MUTAGEN_FIELD_MAPPING[field] == mutagen_field:
            return field
    raise ValueError('No such mutagen field: %s' % mutagen_field)


class _BaseMutagenMetaStore(MetaStore):
    tags_class = None
    error_class = None

    def make_tags_obj(self, path):
        cls = self.tags_class
        return cls(path)

    def get(self, path):
        try:
            tags = self.make_tags_obj(path)
        except self.error_class:
            tags = None
        if tags is None:
            tags = {}
        return self.extract(tags)

    def set(self, path, values):
        tags = self.make_tags_obj(path)
        log_info(u'set: values=%s', unicode(values))
        self.inject(tags, values)
        log_info(u'set: tags=%s', unicode(dict(tags)))
        tags.save()
        return values.keys()

    @classmethod
    def extract(cls, tags):
        values = Values()
        
        for field in tags:
            tag = tags[field]
            try:
                values[field] = cls.get_value_from_tag(field, tags[field])
            except ValueError:
                pass

        for field in MUTAGEN_FIELD_MAPPING:
            mutagen_field = MUTAGEN_FIELD_MAPPING[field]
            if tags.get(mutagen_field, False):
                try:
                    values[field] = cls.get_value_from_tag(
                      mutagen_field, tags[mutagen_field])
                except ValueError:
                    pass

        cls.post_process(values)

        return values

    @classmethod
    def get_value_from_tag(cls, field, tag):
        if not isinstance(tag, (list, tuple)):
            log_info(
              (
                u'_BaseMutagenMetaStore.get_value_from_tag: '
                u'tag value is not a list, dropping: %r, %r'
              ),
              field,
              tag,
            )
            raise ValueError(tag)
        return list(tag)

    @classmethod
    def post_process(cls, values):
        if 'n' in values:
            try:
                values['n'] = ['%u' % int(v) for v in values['n']]
            except ValueError:
                del values['n']
            else:
                values['TRACKNUMBER'] = values['N'] = [
                  '%02u' % int(v) for v in values['n']]

    @classmethod
    def inject(cls, tags, values):
        for field in values:
            if field in MUTAGEN_FIELD_MAPPING:
                mutagen_field = MUTAGEN_FIELD_MAPPING[field]
                tags[mutagen_field] = values[field]
            else:
                tags[field] = values[field]


class MutagenFileMetaStore(_BaseMutagenMetaStore):
    tags_class = staticmethod(SimpleMutagenFile)
    error_class = Exception
