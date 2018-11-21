#!/usr/bin/env python
#
#    Copyright (C) 2017 Kenneth A. Giusti
#
#    Licensed to the Apache Software Foundation (ASF) under one
#    or more contributor license agreements.  See the NOTICE file
#    distributed with this work for additional information
#    regarding copyright ownership.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#

from __future__ import unicode_literals
from __future__ import division
from __future__ import absolute_import
from __future__ import print_function

import argparse
import eventlet
import logging
import os
from oslo_config import cfg
from subprocess import Popen
from subprocess import STDOUT
import sys

from ombt import Controller
from ombt import RPCTestClient
from ombt import RPCTestServer
from ombt import TestListener
from ombt import TestNotifier

VERSION = (3, 0, 0)  # NOTE: update setup.py too!

DEFAULT_LEN = 1024

# flags for running in the background
_DAEMON = False
_PARENT_FD = -1


def _run_as_daemon():
    #
    # run the command in a child process
    #
    cmdline = sys.argv[:]
    cmdline.remove("--daemon")
    cmdline.append("-X-daemon")
    if 'python' not in cmdline[0]:
        # hack to run correctly under virtualenv
        cmdline = [sys.executable] + cmdline

    p = os.pipe()
    Popen(cmdline, bufsize=0, stderr=STDOUT, stdout=p[1])
    out = ""
    while True:
        b = os.read(p[0], 1000).decode()
        # hack, why doesn't os.read() return when the pipe is closed???
        if not b or b[-1] == '\n':
            break
        out += b
    print("%s" % out)


def _do_shutdown(cfg, args):
    controller = Controller(cfg, args.control, args.topic, args.timeout,
                            args.unique, args.idle, args.output)
    controller.start()
    controller.shutdown_clients()
    controller.shutdown()


def _rpc_call_test(cfg, args):
    controller = Controller(cfg, args.control, args.topic, args.timeout,
                            args.unique, args.idle, args.output)
    controller.start()
    controller.run_call_test(args.calls, 'X' * args.length, args.verbose,
                             args.pause)
    controller.shutdown()


def _rpc_cast_test(cfg, args):
    controller = Controller(cfg, args.control, args.topic, args.timeout,
                            args.unique, args.idle, args.output)
    controller.start()
    controller.run_cast_test(args.calls, 'X' * args.length, args.verbose,
                             args.pause, args.delay)
    controller.shutdown()


def _rpc_fanout_test(cfg, args):
    controller = Controller(cfg, args.control, args.topic, args.timeout,
                            args.unique, args.idle, args.output)
    controller.start()
    controller.run_fanout_test(args.calls, 'X' * args.length, args.verbose,
                               args.pause, args.delay)
    controller.shutdown()


def _notify_test(cfg, args):
    controller = Controller(cfg, args.control, args.topic, args.timeout,
                            args.unique, args.idle, args.output)
    controller.start()
    controller.run_notification_test(args.events, 'X' * args.length,
                                     args.severity, args.verbose, args.pause,
                                     args.delay)
    controller.shutdown()


def controller(cfg, args):
    TESTS = {'rpc-call': _rpc_call_test,
             'rpc-cast': _rpc_cast_test,
             'rpc-fanout': _rpc_fanout_test,
             'shutdown': _do_shutdown,
             'notify': _notify_test}
    func = TESTS.get(args.test.lower())
    if func is None:
        print("Error - unrecognized command %s" % args.test)
        print("commands: %s" % [x for x in iter(TESTS)])
        return -1
    return func(cfg, args)


def rpc_standalone(cfg, args):
    server = RPCTestServer(cfg,
                           args.control,
                           args.url,
                           args.topic,
                           args.executor,
                           None,
                           args.timeout)
    server.start()
    client = RPCTestClient(cfg, args.control, args.url, args.topic,
                           None, args.timeout)
    client.start()

    controller = Controller(cfg, args.control, args.topic, args.timeout)
    controller.start()

    if args.do_cast:
        controller.run_cast_test(args.calls, 'X' * args.length, args.verbose,
                                 0.0,   # no pause between sends
                                 0.25)  # delay before polling for results
    else:
        controller.run_call_test(args.calls, 'X' * args.length, args.verbose,
                                 0.0)  # no pause between sends

    controller.shutdown_clients()
    controller.shutdown()


def notify_standalone(cfg, args):
    server = TestListener(cfg,
                          args.control,
                          args.url,
                          args.topic,
                          args.executor,
                          None,
                          args.timeout,
                          args.pool)
    server.start()
    client = TestNotifier(cfg, args.control, args.url, args.topic,
                          None, args.timeout)
    client.start()

    controller = Controller(cfg, args.control, args.topic, args.timeout)
    controller.start()
    controller.run_notification_test(args.calls, 'X' * args.length,
                                     'debug', args.verbose,
                                     0.0,  # no pause between calls
                                     0.250)  # delay before polling results
    controller.shutdown_clients()
    controller.shutdown()


def rpc_server(cfg, args):
    server = RPCTestServer(cfg, args.control, args.url, args.topic,
                           args.executor, args.name, args.timeout,
                           args.unique, args.output)
    server.start()
    if _DAEMON:
        msg = "RPC server %s is ready\n" % server.name
        os.write(_PARENT_FD, msg.encode())
        os.close(_PARENT_FD)
    server.wait()


def rpc_client(cfg, args):
    client = RPCTestClient(cfg, args.control, args.url, args.topic,
                           args.name, args.timeout,
                           args.unique, args.output)
    client.start()
    if _DAEMON:
        msg = "RPC client %s is ready\n" % client.name
        os.write(_PARENT_FD, msg.encode())
        os.close(_PARENT_FD)
    client.wait()


def listener(cfg, args):
    listener = TestListener(cfg, args.control, args.url, args.topic,
                            args.executor, args.name, args.timeout,
                            args.pool, args.output)
    listener.start()
    if _DAEMON:
        msg = "Listener %s is ready\n" % listener.name
        os.write(_PARENT_FD, msg.encode())
        os.close(_PARENT_FD)
    listener.wait()


def notifier(cfg, args):
    notifier = TestNotifier(cfg, args.control, args.url, args.topic,
                            args.name, args.timeout, args.output)
    notifier.start()
    if _DAEMON:
        msg = "Notifier %s is ready\n" % notifier.name
        os.write(_PARENT_FD, msg.encode())
        os.close(_PARENT_FD)
    notifier.wait()


def _main():
    eventlet.monkey_patch()
    parser = argparse.ArgumentParser(
        description=('Benchmark tool for oslo.messaging (v%d.%d.%d)'
                     % VERSION))

    parser.add_argument("--url",
                        default='rabbit://localhost:5672',
                        help="The address of the messaging service under test")
    parser.add_argument("--control",
                        default=None,
                        help="The address of the messaging service used for"
                        " control of ombt2. Defaults to --url value.")
    parser.add_argument("--oslo-config",
                        help="oslo.messaging configuration file")
    parser.add_argument('--topic', default='test-topic',
                        help='service address to use')
    parser.add_argument('--unique', action='store_true',
                        help="Force a single controller for all topics")
    parser.add_argument('--debug', action='store_true',
                        help='Enable DEBUG logging')
    parser.add_argument("--timeout", type=int, default=60,
                        help='fail test after timeout seconds')
    parser.add_argument("--logfile-prefix", type=str, default=None,
                        help="File for logging. The filename is created from"
                        " appending the process id (pid) to the prefix.")

    subparsers = parser.add_subparsers(dest='mode',
                                       description='operational mode')
    # RPC Standalone
    sp = subparsers.add_parser('rpc',
                               description='standalone RPC test')
    sp.add_argument("--calls", type=int, default=1,
                    help="number of RPC calls to perform")
    sp.add_argument("--length", type=int, default=DEFAULT_LEN,
                    help='length in bytes of payload string')
    sp.add_argument("--cast", dest='do_cast', action='store_true',
                    help='RPC cast instead of RPC call')
    sp.add_argument("--executor", default="threading",
                    help="type of executor the server will use")
    sp.add_argument('--verbose', type=bool, default=False,
                    help='turn on verbose logging')

    # Notification Standalone
    sp = subparsers.add_parser('notify',
                               description='standalone notification test')
    sp.add_argument("--calls", type=int, default=1,
                    help="number of notifications to send")
    sp.add_argument("--length", type=int, default=DEFAULT_LEN,
                    help='length in bytes of payload string')
    sp.add_argument("--executor", default="threading",
                    help="type of executor the server will use")
    sp.add_argument('--verbose', type=bool, default=False,
                    help='turn on verbose logging')
    sp.add_argument("--pool", type=str,
                    help="Pool name to assign listener")

    # RPC Server
    sp = subparsers.add_parser('rpc-server',
                               description='RPC Server mode')
    sp.add_argument("--daemon", action='store_true',
                    help='Run the server in the background')
    sp.add_argument("--executor", default="threading",
                    help="type of executor the server will use")
    sp.add_argument("--name", type=str,
                    help="Uniquely identifies this server")
    sp.add_argument("--output", type=str,
                    help="Write detailed output to file")

    # RPC Client
    sp = subparsers.add_parser('rpc-client',
                               description='RPC Client mode')
    sp.add_argument("--daemon", action='store_true',
                    help='Run the client in the background')
    sp.add_argument("--name", type=str,
                    help="Uniquely identifies this client")
    sp.add_argument("--output", type=str,
                    help="Write detailed output to file")

    # Listener
    sp = subparsers.add_parser('listener',
                               description='Notification listener mode')
    sp.add_argument("--executor", default="threading",
                    help="type of executor the server will use")
    sp.add_argument("--daemon", action='store_true',
                    help='Run the listener in the background')
    sp.add_argument("--name", type=str,
                    help="Uniquely identifies this listener")
    sp.add_argument("--output", type=str,
                    help="Write detailed output to file")
    sp.add_argument("--pool", type=str,
                    help="Pool name to assign listener")

    # Notifier
    sp = subparsers.add_parser('notifier',
                               description='Notifier mode')
    sp.add_argument("--daemon", action='store_true',
                    help='Run the notifier in the background')
    sp.add_argument("--name", type=str,
                    help="Uniquely identifies this notifier")
    sp.add_argument("--output", type=str,
                    help="Write detailed output to file")

    # Test controller
    sp = subparsers.add_parser('controller',
                               description='Controller mode')
    sp.add_argument("--idle", type=int, default=2,
                    help="Time in seconds the controller will block"
                    " waiting for client poll to finish")
    sp.add_argument('--verbose', type=bool, default=False,
                    help='turn on verbose logging')
    sp.add_argument("--output", type=str,
                    help="Write detailed output to file")

    sub2 = sp.add_subparsers(dest='test',
                             description='the test to run')

    sp = sub2.add_parser('rpc-call',
                         description='run RPC call test')
    sp.add_argument('--length', type=int, default=DEFAULT_LEN,
                    help='payload size in bytes')
    sp.add_argument('--calls', type=int, default=1,
                    help='number of calls to make')
    sp.add_argument('--pause', type=float, default=0.0,
                    help='Limit the rate of RPC calls by pausing FLOAT seconds'
                    ' between issuing each call')

    sp = sub2.add_parser('rpc-cast',
                         description='run RPC cast test')
    sp.add_argument('--length', type=int, default=DEFAULT_LEN,
                    help='payload size in bytes')
    sp.add_argument('--calls', type=int, default=1,
                    help='number of calls to make')
    sp.add_argument('--pause', type=float, default=0.0,
                    help='Limit the rate of RPC calls by pausing FLOAT seconds'
                    ' between issuing each call')
    sp.add_argument('--delay', type=float, default=0.250,
                    help='delay FLOAT seconds after the test'
                    ' completes before polling for server results.'
                    ' Delay should be at least 2x propagation time.')

    sp = sub2.add_parser('rpc-fanout',
                         description='run RPC fanout test')
    sp.add_argument('--length', type=int, default=DEFAULT_LEN,
                    help='payload size in bytes')
    sp.add_argument('--calls', type=int, default=1,
                    help='number of calls to make')
    sp.add_argument('--pause', type=float, default=0.0,
                    help='Limit the rate of RPC calls by pausing FLOAT seconds'
                    ' between issuing each call')
    sp.add_argument('--delay', type=float, default=0.250,
                    help='delay FLOAT seconds after the test'
                    ' completes before polling for server results.'
                    ' Delay should be at least 2x propagation time.')

    sp = sub2.add_parser('notify',
                         description='run notification test')
    sp.add_argument('--length', type=int, default=DEFAULT_LEN,
                    help='payload size in bytes')
    sp.add_argument('--events', type=int, default=1,
                    help='number of events to issue')
    sp.add_argument('--pause', type=float, default=0.0,
                    help='Limit the rate of notifications by pausing FLOAT'
                    ' seconds between issuing each notification')
    sp.add_argument('--severity', type=str, default='debug',
                    help='Notification severity')
    sp.add_argument('--delay', type=float, default=0.250,
                    help='delay FLOAT seconds after the test'
                    ' completes before polling for server results.'
                    ' Delay should be at least 2x propagation time.')

    sp = sub2.add_parser('shutdown',
                         description='shutdown all test clients')

    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARN,
                        filename=args.logfile_prefix + str(os.getpid())
                        if args.logfile_prefix else None)

    # run in the background if specified:
    if getattr(args, 'daemon', False):
        return _run_as_daemon()

    if args.oslo_config:
        cfg.CONF(["--config-file", args.oslo_config])

    args.control = args.control or args.url

    {'controller': controller,
     'rpc': rpc_standalone,
     'rpc-server': rpc_server,
     'rpc-client': rpc_client,
     'notify': notify_standalone,
     'listener': listener,
     'notifier': notifier}[args.mode](cfg, args)

    return None


def main():

    # determine if this command is running in
    # the background:
    if '-X-daemon' in sys.argv:
        global _DAEMON
        global _PARENT_FD
        _DAEMON = True

        # the parent process is waiting for this process to print that it is
        # ready on stdout so it can block until the child is done initializing
        # re-direct stdio to devnull to avoid any spurious output from causing
        # the parent to unblock prematurely

        _PARENT_FD = os.dup(sys.stdout.fileno())
        os.dup2(os.open(os.devnull, os.O_RDONLY), sys.stdin.fileno())
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stderr.fileno())
        sys.argv.remove('-X-daemon')

    sys.exit(_main())
