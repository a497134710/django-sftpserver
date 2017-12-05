# coding: utf-8
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function

import socket
import paramiko
import time

from django.core.management.base import BaseCommand
from ... import sftpserver


class Command(BaseCommand):
    HOST = '0.0.0.0'
    PORT = '2222'

    def add_arguments(self, parser):
        parser.add_argument(
            '--host', dest='host', default=self.HOST,
            help='listen on HOST [default: %(default)s]'
        )
        parser.add_argument(
            '-p', '--port', dest='port', type=int, default=self.PORT,
            help='listen on PORT [default: %(default)d]'
        )
        parser.add_argument(
            '-l', '--level', dest='level', default='INFO',
            help='Debug level: WARNING, INFO, DEBUG [default: %(default)s]'
        )
        parser.add_argument(
            '-k', '--keyfile', dest='keyfile', metavar='FILE',
            help='Path to private key, for example /tmp/test_rsa.key'
        )

    def handle(self, *args, **options):
        paramiko_level = getattr(paramiko.common, options['level'])
        paramiko.common.logging.basicConfig(level=paramiko_level)

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        server_socket.bind((options['host'], options['port']))
        server_socket.listen(options['BACKLOG'])

        transport_list = []
        try:
            while True:
                conn, addr = server_socket.accept()
                host_key = paramiko.RSAKey.from_private_key_file(options['keyfile'])
                transport = paramiko.Transport(conn)
                print(transport.server_key_dict, host_key.get_name())
                transport.add_server_key(host_key)
                transport.set_subsystem_handler(
                    'sftp', paramiko.SFTPServer, sftpserver.StubSFTPServer)

                server = sftpserver.StubServer()
                transport.start_server(server=server)
                channel = transport.accept()

                transport_list.append((transport, channel))
        except KeyboardInterrupt:
            for transport, channel in transport_list:
                while transport.is_active():
                    time.sleep(1)
