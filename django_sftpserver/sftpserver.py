# coding: utf-8
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function

import io
import os
import paramiko

from django.contrib.auth import get_user_model
from . import models


class StubServer(paramiko.ServerInterface):

    def set_username(self, username):
        root, branch = None, None
        if ':' in username:
            username, root = username.split(':')
            if '/' in root:
                root, branch = root.split('/')
        self.username = username
        self.user = get_user_model().objects.get(username=username)
        self.root_name = root
        self.branch_name = branch

    def check_auth_publickey(self, username, key):
        self.set_username(username)
        for public_key in models.AuthorizedKey.objects.filter(user=self.user):
            if key.get_base64() == public_key.key:
                return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def get_allowed_auths(self, username):
        return "publickey"


class StubSFTPHandle(paramiko.SFTPHandle):

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
        self.readfile = self._bytesio
        self.writefile = self._bytesio

    def close(self):
        super(StubSFTPHandle, self).close()
        if not self._read_only:
            self._fileobj.data = self._bytesio.getvalue()
            self._fileobj.save()

    def stat(self):
        return paramiko.sftp.SFTPAttributes.from_stat(self.fileobj.stat)

    def chattr(self, attr):
        return paramiko.sftp.SFTP_OP_UNSUPPORTED


class StubSFTPServer(paramiko.sftp.SFTPServerInterface):

    def __init__(self, server, *largs, **kwargs):
        super(StubSFTPServer, self).__init__(server, *largs, **kwargs)
        self.server = server

    def session_started(self):
        pass

    def session_ended(self):
        pass

    def list_folder(self, path):
        root, path = self._resolve(path)
        result = []
        for fobj in root.ls(path):
            attr = paramiko.sftp.SFTPAttributes.from_stat(fobj.stat)
            attr.filename = fobj.filename
            result.append(attr)
        return result

    def stat(self, path):
        root, path = self._resolve(path)
        return paramiko.sftp.SFTPAttributes.from_stat(root.get(path).stat)

    def lstat(self, path):
        return self.stat(path)

    def open(self, path, flags, attr):
        root, path = self._resolve(path)
        if (not (flags & os.O_WRONLY)) and (
                not ((flags & os.O_RDWR) and (flags & os.O_APPEND))):
            if not root.exists(path):
                return paramiko.sftp.SFTP_NO_SUCH_FILE
        if not root.exists(path):
            root.create(path)
        return StubSFTPHandle(self, root, path, flags)

    def remove(self, path):
        root, path = self._resolve(path)
        root.remove(path)

    def rename(self, oldpath, newpath):
        oldroot, oldpath = self._resolve(oldpath)
        newroot, newpath = self._resolve(newpath)
        if oldroot != newroot:
            return paramiko.sftp.SFTP_OP_UNSUPPORTED
        else:
            oldroot.rename(oldpath, newpath)
        return paramiko.sftp.SFTP_OK

    def mkdir(self, path, attr):
        root, path = self._resolve(path)
        root.mkdir(path)
        return paramiko.sftp.SFTP_OK

    def rmdir(self, path):
        root, path = self._resolve(path)
        root.remove(path)
        return paramiko.sftp.SFTP_OK

    def chattr(self, path, attr):
        return paramiko.sftp.SFTP_OP_UNSUPPORTED

    def symlink(self, target_path, path):
        return paramiko.sftp.SFTP_OP_UNSUPPORTED

    def readlink(self, path):
        return paramiko.sftp.SFTP_OP_UNSUPPORTED
