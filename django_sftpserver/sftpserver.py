# coding: utf-8
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function

import io
import os
import logging
import paramiko
import stat as _stat

from django.contrib.auth import get_user_model
from . import models

logger = logging.getLogger(__name__)


def _log_error(f):
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except:
            logger.exception('Unexpected Error')
            raise
    return wrapper


class StubServer(paramiko.ServerInterface):

    def _set_username(self, username):
        root, branch = None, None
        if '/' in username:
            username = username.split('/')
            if len(username) == 2:
                username, root = username
            elif len(username) == 3:
                username, root, branch = username
            else:
                return False
        self.username = username
        self.user = get_user_model().objects.get(username=username)
        self.root_name = root
        self.branch_name = branch
        if self.root_name:
            self.root = models.Root.objects.get(
                name=self.root_name, branch=self.branch_name)
        else:
            self.root = None
        return True

    @_log_error
    def check_auth_publickey(self, username, key):
        logger.debug('authenticating {}'.format(username))
        try:
            if not self._set_username(username):
                return paramiko.AUTH_FAILED
        except get_user_model().DoesNotExist:
            return paramiko.AUTH_FAILED
        except models.Root.DoesNotExist:
            return paramiko.AUTH_FAILED

        if self.root and (not self.root.has_permission(self.user)):
            return paramiko.AUTH_FAILED

        for public_key in models.AuthorizedKey.objects.filter(user=self.user):
            if key.get_base64() == public_key.key:
                return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    @_log_error
    def check_channel_request(self, kind, chanid):
        logger.debug('kind={} => channelid={} channel_request success!!'.format(kind, chanid))
        return paramiko.OPEN_SUCCEEDED

    @_log_error
    def get_allowed_auths(self, username):
        return "publickey"


class StubSFTPHandle(paramiko.SFTPHandle):

    @_log_error
    def __init__(self, server, root, path, flags):
        super(StubSFTPHandle, self).__init__(flags)
        self._fileobj = root.get(path)
        self._bytesio = io.BytesIO(self._fileobj.data)
        # 'ab', 'wb', 'a+b', 'r+b', 'rb'
        self._read_only = False
        if flags & os.O_WRONLY:
            if flags & os.O_APPEND:
                self._bytesio.seek(self._fileobj.size)
            else:
                self._bytesio.seek(0)
        elif flags & os.O_RDWR:
            if flags & os.O_APPEND:
                self._bytesio.seek(self._fileobj.size)
            else:
                self._bytesio.seek(0)
        else:  # O_RDONLY (== 0)
            self._read_only = True
            self._bytesio.seek(0)
        # self.filename = path
        self._modified = False
        self.readfile = self._bytesio
        self.writefile = self._bytesio

    @_log_error
    def close(self):
        if (not self._read_only) and self._modified:
            self._fileobj.data = self._bytesio.getvalue()
            self._fileobj.save()
        super(StubSFTPHandle, self).close()

    @_log_error
    def write(self, offset, data):
        self._modified = True
        return super(StubSFTPHandle, self).write(offset, data)

    @_log_error
    def stat(self):
        return paramiko.SFTPAttributes.from_stat(self._fileobj.stat)

    @_log_error
    def chattr(self, attr):
        return paramiko.SFTP_OP_UNSUPPORTED


class StubSFTPServer(paramiko.SFTPServerInterface):

    @_log_error
    def __init__(self, server, *largs, **kwargs):
        super(StubSFTPServer, self).__init__(server, *largs, **kwargs)
        self.server = server
        self.user = self.server.user
        self.root = self.server.root
        logger.debug("initialized")

    @_log_error
    def session_started(self):
        logger.debug("started")

    @_log_error
    def session_ended(self):
        logger.debug("session ended")
        self.server = None

    def _resolve(self, path):
        if self.root:
            return self.root, path
        else:
            l = path.split(os.path.sep)
            if not l[1]:
                return None, '/'
            else:
                r = models.Root.objects.get(name=l[1])
                return r, '/' + os.path.sep.join(l[2:])

    def _directory_attr(self, filename):
        attr = paramiko.SFTPAttributes()
        attr.filename = filename
        attr.st_size = 0
        attr.st_uid = 0
        attr.st_gid = 0
        attr.st_mode = _stat.S_IFDIR | _stat.S_IRUSR | _stat.S_IXUSR | _stat.S_IRGRP | _stat.S_IXGRP
        attr.st_atime = 0
        attr.st_mtime = 0
        return attr

    @_log_error
    def list_folder(self, path):
        logger.debug('list folder : {}'.format(path))
        root, path = self._resolve(path)
        result = []
        if root is None:
            for r in models.Root.objects.all():
                if not r.has_permission(self.user):
                    continue
                result.append(self._directory_attr(r.name))
        else:
            for fobj in root.ls(path):
                attr = paramiko.SFTPAttributes.from_stat(fobj.stat)
                attr.filename = fobj.filename
                result.append(attr)
        return result

    @_log_error
    def stat(self, path):
        logger.debug('stat: {}'.format(path))
        root, path = self._resolve(path)
        if not root:
            return self._directory_attr('/')
        if not root.exists(path):
            return paramiko.SFTP_NO_SUCH_FILE
        return paramiko.SFTPAttributes.from_stat(root.get(path).stat)

    @_log_error
    def lstat(self, path):
        logger.debug('lstat: {}'.format(path))
        return self.stat(path)

    @_log_error
    def open(self, path, flags, attr):
        logger.debug('open: {}'.format(path))
        root, path = self._resolve(path)
        if not root:
            return paramiko.SFTP_PERMISSION_DENIED
        if root.exists(path) and root.get(path).isdir:
            return paramiko.SFTP_PERMISSION_DENIED
        if (not (flags & os.O_WRONLY)) and (
                not ((flags & os.O_RDWR) and (flags & os.O_APPEND))):
            if not root.exists(path):
                return paramiko.SFTP_NO_SUCH_FILE
        if not root.exists(path):
            root.create(path)
        return StubSFTPHandle(self, root, path, flags)

    @_log_error
    def remove(self, path):
        logger.debug("remove: {}".format(path))
        root, path = self._resolve(path)
        if not root:
            return paramiko.SFTP_PERMISSION_DENIED
        root.remove(path)

    @_log_error
    def rename(self, oldpath, newpath):
        logger.debug("rnemae {} -> {}".format(oldpath, newpath))
        oldroot, oldpath = self._resolve(oldpath)
        newroot, newpath = self._resolve(newpath)
        if oldroot != newroot:
            return paramiko.SFTP_OP_UNSUPPORTED
        else:
            oldroot.rename(oldpath, newpath)
        return paramiko.SFTP_OK

    @_log_error
    def mkdir(self, path, attr):
        logger.debug("mkdir: {}".format(path))
        root, path = self._resolve(path)
        if not root:
            return paramiko.SFTP_PERMISSION_DENIED
        root.mkdir(path)
        return paramiko.SFTP_OK

    @_log_error
    def rmdir(self, path):
        logger.debug("rmdir: {}".format(path))
        root, path = self._resolve(path)
        if not root:
            return paramiko.SFTP_PERMISSION_DENIED
        root.remove(path)
        return paramiko.SFTP_OK

    @_log_error
    def chattr(self, path, attr):
        logger.debug("chattr '{}' '{}'".format(path, attr))
        return paramiko.SFTP_OP_UNSUPPORTED

    @_log_error
    def symlink(self, target_path, path):
        logger.debug("symlink '{}' '{}'".format(target_path, path))
        return paramiko.SFTP_OP_UNSUPPORTED

    @_log_error
    def readlink(self, path):
        logger.debug("readlink '{}'".format(path))
        return paramiko.SFTP_OP_UNSUPPORTED
