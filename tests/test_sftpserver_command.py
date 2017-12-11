# coding: utf-8
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function

import socket
import threading
import uuid
import os
import time
import paramiko
from contextlib import contextmanager

from django.contrib.auth import get_user_model
from django.test import TestCase

from django_sftpserver.management.commands.django_sftpserver_run import Command
from django_sftpserver import models


class ServerMixin(object):
    username = 'username'
    storage_mode = False

    class SFTPClient(object):
        def __enter__(self):
            pass

        def __exit__(self, *args, **kwargs):
            pass

    def start_server(self):
        self.pkey = paramiko.RSAKey.generate(4096)
        # import sys
        # key.write_private_key(sys.stdout)
        # print(key.get_base64())

        self.__command = Command()
        self.socket_filename = '/tmp/{}.sock'.format(uuid.uuid4().hex)
        self.__thread = threading.Thread(target=self.run_server, args=())
        self.__thread.start()
        while not os.path.exists(self.socket_filename):
            time.sleep(0.1)

    def run_server(self):
        self.__command.handle(level='INFO', socket_filename=self.socket_filename,
                              storage_mode=self.storage_mode, pkey=self.pkey, accept_timeout=1)

    def stop_server(self):
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(self.socket_filename)
        self.__command.cont = False
        self.__thread.join()

    @contextmanager
    def create_client(self, username=None):
        client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client_socket.connect(self.socket_filename)

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.WarningPolicy)
        ssh.connect('localhost',
                    username=username if username else self.username,
                    pkey=self.pkey, sock=client_socket)
        sftp = ssh.open_sftp()

        try:
            yield sftp
        finally:
            sftp.close()
            ssh.close()


class TestDjango_sftpserver_sftpserver_command(ServerMixin, TestCase):
    root_name = 'root'

    def setUp(self):
        self.start_server()
        self.user = get_user_model().objects.create(username=self.username)
        models.AuthorizedKey.objects.create(
            user=self.user, key_type=self.pkey.get_name(), key=self.pkey.get_base64())
        root = models.Root.objects.create(name=self.root_name)
        root.users.add(self.user)

    def tearDown(self):
        self.stop_server()

    def test_login(self):
        with self.create_client() as client:
            print(client.listdir())
