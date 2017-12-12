# coding: utf-8
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function

import sys
import socket
import threading
import multiprocessing
import uuid
import os
import time
import paramiko
import shutil
from contextlib import contextmanager
import moto.server as moto_server
import boto
import yaml
import random

from django.contrib.auth import get_user_model
from django.test import TestCase
# from django.test import SimpleTestCase as TestCase

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

        self.user = get_user_model().objects.create(username=self.username)
        models.AuthorizedKey.objects.create(
            user=self.user, key_type=self.pkey.get_name(), key=self.pkey.get_base64())

    def run_server(self):
        self.__command.handle(level='ERROR', socket_filename=self.socket_filename,
                              storage_mode=self.storage_mode, pkey=self.pkey, accept_timeout=1)

    def stop_server(self):
        time.sleep(1)
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
    root_name_0 = 'root_0'
    root_name_1 = 'root_1'

    def setUp(self):
        super(TestDjango_sftpserver_sftpserver_command, self).setUp()
        self.start_server()
        root = models.Root.objects.create(name=self.root_name_0)
        root.users.add(self.user)
        root = models.Root.objects.create(name=self.root_name_1)
        root.users.add(self.user)

    def tearDown(self):
        self.stop_server()
        super(TestDjango_sftpserver_sftpserver_command, self).tearDown()

    def test_listdir(self):
        # stat, open, remove, rename, mkdir, rmdir
        with self.create_client() as client:
            print(client.listdir(), client.listdir_attr())


class TestDjango_sftpserver_sftpserver_command_filesystemstorage(ServerMixin, TestCase):
    storage_mode = True

    storage_name_0 = 'storage_name_0'

    def setUp(self):
        super(TestDjango_sftpserver_sftpserver_command_filesystemstorage, self).setUp()
        self.start_server()
        self.storage_root_0 = '/tmp/django_sftpserver_test-{}'.format(uuid.uuid4().hex)
        sai = models.StorageAccessInfo.objects.create(
            name=self.storage_name_0,
            storage_class="django.core.files.storage.FileSystemStorage",
            kwargs="location: {}".format(self.storage_root_0))
        sai.users.add(self.user)

    def tearDown(self):
        self.stop_server()
        if os.path.exists(self.storage_root_0):
            shutil.rmtree(self.storage_root_0)
        super(TestDjango_sftpserver_sftpserver_command_filesystemstorage, self).tearDown()

    def test_listdir(self):
        # stat, open, remove, rename, mkdir, rmdir
        with self.create_client() as client:
            print(client.listdir(), client.listdir_attr())


class TestDjango_sftpserver_sftpserver_command_s3storage(ServerMixin, TestCase):
    storage_mode = True

    storage_name_0 = 's3_storage_name_0'

    def setUp(self):
        fake_s3_port = random.randint(10000, 65535)
        main_app = moto_server.DomainDispatcherApplication(
            moto_server.create_backend_app, service='s3')
        main_app.debug = True
        self.__thread = multiprocessing.Process(
            target=moto_server.run_simple,
            args=('127.0.0.1', fake_s3_port, main_app, ),
            kwargs={'threaded': False, 'use_reloader': False, 'ssl_context': None})
        self.__thread.start()

        super(TestDjango_sftpserver_sftpserver_command_s3storage, self).setUp()
        self.start_server()

        # conn = boto.resource('s3', region_name='127.0.0.1')
        # conn.create_bucket(Bucket='testxxxx')

        kwargs = {
            # 'access_key': 'AKIAAAAAAAAAAAAAAAAA',
            # 'secret_key': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
            'bucket_name': 'testxxxx',
            # 'proxy': b'127.0.0.1',
            # 'proxy_port': fake_s3_port,
            # 'host': '127.0.0.1',
            # 'port': fake_s3_port,
            # 'default_acl': 'private',
            'location': 'test_sftp',
            'url_protocol': 'http',
            'secure_urls': False,
            # 'endpoint_url': '127.0.0.1:{}'.format(fake_s3_port),
            'endpoint_url': 'http://localhost:{}'.format(fake_s3_port),
            'auto_create_bucket': True,
        }

        sai = models.StorageAccessInfo.objects.create(
            name=self.storage_name_0,
            storage_class="storages.backends.s3boto3.S3Boto3Storage",
            kwargs=yaml.dump(kwargs))
        sai.users.add(self.user)

        storage = sai.get_storage()
        print(storage.listdir('.'))

    def tearDown(self):
        self.__thread.terminate()
        self.stop_server()
        super(TestDjango_sftpserver_sftpserver_command_s3storage, self).tearDown()

    def test_listdir(self):
        # stat, open, remove, rename, mkdir, rmdir
        with self.create_client() as client:
            print(client.listdir(), client.listdir_attr())
            print(client.listdir('./{}'.format(self.storage_name_0)), client.listdir_attr())


if sys.version_info[0] == 2:
    for i in (x for x in dir() if x.startswith("TestDjango_sftpserver")):
        globals().pop(i)
