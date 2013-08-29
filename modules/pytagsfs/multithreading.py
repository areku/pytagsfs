# Copyright (c) 2009 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

'''
This module implements token-style locking.  This prevents deadlocks by
enforcing that no thread can acquire more than one lock at a time.

Tokens are identified by an arbitrary object.  The GLOBAL object defined here
identifies a global token.

Most code should simply assume that the global token is acquired and need not
be written to be thread safe.  Code that uses blocking I/O should either wrap
such calls with bracketing release_token/reacquire_token or
push_token/pop_token calls.

Generally, use release_token/reacquire_token when the calls are atomic (i.e.
do not use an open file descriptor) and use push_token/pop_token when the calls
are not atomic (i.e. do use an open file descriptor).

push_token/pop_token should be used with a token identifier that uniquely
identifies the resource (usually an object associated with a file descriptor)
being protected.

As little code as possible should sit in the critical section where the global
token is no longer held, since most code will assume that the global token has
been acquired.  Do not call arbitrary functions, if possible, only I/O
functions whose thread safety is known.
'''

from thread import get_ident, allocate_lock

try:
    from functools import wraps
except ImportError:
    from sclapp.legacy_support import wraps


# Note: Do not call logging functions from this module.  Logging functions
# assume that the global token is acquired.  We cannot make that assumption
# here.


GLOBAL = object()


class TokenError(Exception):
    pass


class BaseToken(object):
    _id = None

    def __init__(self, id):
        self._id = id

    def acquire(self):
        raise NotImplementedError()

    def release(self):
        raise NotImplementedError()


class Token(BaseToken):
    _lock = None
    _owner = None

    def __init__(self, id):
        super(Token, self).__init__(id)
        self._lock = allocate_lock()

    def acquire(self):
        owner = get_ident()
        if self._owner == owner:
            # Token may only be acquired once per thread.
            raise TokenError('token already acquired')
        self._lock.acquire()
        self._owner = owner

    def release(self):
        owner = self._owner
        if owner != get_ident():
            raise TokenError('token not acquired')
        del self._owner
        self._lock.release()


class NullToken(BaseToken):
    def acquire(self):
        pass

    def release(self):
        pass


class NullLock(object):
    def acquire(self):
        pass

    def release(self):
        pass


class TokenExchange(object):
    _tokens = None
    _lock = None
    _owner_token_queues = None

    def __init__(self):
        self._tokens = {}
        self._lock = allocate_lock()
        self._owner_token_queues = {}

    def push_token(self, id):
        owner = get_ident()

        self._lock.acquire()
        try:
            try:
                prev_token = self._owner_token_queues[owner][-1]
            except (KeyError, IndexError):
                prev_token = None
            try:
                next_token = self._tokens[id]
            except KeyError:
                next_token = Token(id)
                self._tokens[id] = next_token
            self._owner_token_queues.setdefault(owner, []).append(next_token)
        finally:
            self._lock.release()

        if prev_token is not None:
            prev_token.release()
        next_token.acquire()

    def pop_token(self):
        owner = get_ident()
        self._lock.acquire()
        try:
            prev_token = self._owner_token_queues[owner].pop()
            try:
                next_token = self._owner_token_queues[owner][-1]
            except (KeyError, IndexError):
                next_token = None
        finally:
            self._lock.release()

        prev_token.release()
        if next_token is not None:
            next_token.acquire()

    def token_pushed(self, get_id):
        def decorator(wrapped):
            @wraps(wrapped)
            def fn(*args, **kwargs):
                if callable(get_id):
                    id = get_id(*args, **kwargs)
                else:
                    id = get_id
                self.push_token(id)
                try:
                    return wrapped(*args, **kwargs)
                finally:
                    self.pop_token()
            return fn
        return decorator

    def release_token(self):
        owner = get_ident()
        self._lock.acquire()
        try:
            try:
                token = self._owner_token_queues[owner][-1]
            except (KeyError, IndexError):
                token = None
        finally:
            self._lock.release()
        if token is not None:
            token.release()

    def reacquire_token(self):
        owner = get_ident()
        self._lock.acquire()
        try:
            try:
                token = self._owner_token_queues[owner][-1]
            except (KeyError, IndexError):
                token = None
        finally:
            self._lock.release()
        if token is not None:
            token.acquire()

    def token_released(self, wrapped):
        @wraps(wrapped)
        def fn(*args, **kwargs):
            self.release_token()
            try:
                return wrapped(*args, **kwargs)
            finally:
                self.reacquire_token()
        return fn

token_exchange = TokenExchange()
