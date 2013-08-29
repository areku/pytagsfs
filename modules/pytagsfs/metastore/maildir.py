# Copyright (c) 2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import os.path
from mailbox import Maildir, ExternalClashError
import email.header

from pytagsfs.metastore import MetaStore
from pytagsfs.values import Values
from pytagsfs.util import rpartition

from pytagsfs.debug import log_debug


TAG_HEADER = 'X-Pytagsfs-Tag'


class MaildirMetaStore(MetaStore):
    def open_mailbox(self, path):
        mailbox_dir = os.path.dirname(os.path.dirname(path.encode('utf-8')))
        return Maildir(mailbox_dir, None)

    def get_message_key(self, path):
        return rpartition(os.path.basename(path), u':')[0].encode('utf-8')

    def parse_tags(self, message):
        raw_header_values = message.get_all(TAG_HEADER)
        if raw_header_values is None:
            return
        for raw_header_value in raw_header_values:
            yield self.decode_header(raw_header_value)

    def decode_header(self, raw_header_value):
        parts = []
        for content, charset in email.header.decode_header(raw_header_value):
            if charset is None:
                charset = 'ascii'
            parts.append(content.decode(charset))
        return ''.join(parts)

    def encode_header(self, value):
        return email.header.make_header([value.encode('utf-8'), 'utf-8'])

    def get(self, path):
        values = Values()

        message_key = self.get_message_key(path)

        if message_key:
            mailbox = self.open_mailbox(path)
            try:
                message = mailbox.get_message(message_key)
            finally:
                mailbox.close()

            message_tags = list(self.parse_tags(message))

            log_debug(
              u'MaildirMetaStore.get: %s: %s' % (path, repr(message_tags)))

            if message_tags:
                values['maildir_tag'] = message_tags

        return values

    def set(self, path, values):
        message_key = self.get_message_key(path)

        if not message_key:
            return []

        try:
            message_tags = values['maildir_tag']
        except KeyError:
            return []

        if not message_tags:
            return []

        mailbox = self.open_mailbox(path)
        try:
            try:
                mailbox.lock()
            except ExternalClashError:
                return []

            try:
                message = mailbox.get_message(message_key)
                del message[TAG_HEADER]
                for message_tag in message_tags:
                    message[TAG_HEADER] = self.encode_header(message_tag)
                mailbox.update({message_key: message})

            finally:
                mailbox.unlock()

        finally:
            mailbox.close()
